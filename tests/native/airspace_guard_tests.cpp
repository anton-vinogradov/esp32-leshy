#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "services/guard/AirspaceGuard.h"

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__,      \
                         __LINE__, #condition);                                 \
            std::abort();                                                       \
        }                                                                       \
    } while (false)

namespace {

using leshy1::domain::captures::WifiFrameKind;
using leshy1::domain::captures::WifiFrameSource;
using leshy1::domain::captures::WifiFrameView;
using namespace leshy1::services::guard;

struct FixtureFrame final {
    std::array<std::uint8_t, 96> payload{};
    std::uint16_t length = 24;
    std::uint64_t monotonicUs = 0;
    std::int16_t rssiDbm = -60;
    std::uint8_t channel = 6;
    WifiFrameKind kind = WifiFrameKind::Management;
    bool fcsIncluded = false;
    bool readable = true;
};

class FixtureSource final : public WifiFrameSource {
public:
    static constexpr std::size_t kCapacity = 80;

    void add(std::uint8_t subtype, std::uint64_t monotonicUs,
             const std::array<std::uint8_t, 6>& transmitter,
             std::uint8_t channel = 6, std::int16_t rssiDbm = -60) {
        CHECK(size_ < frames_.size());
        FixtureFrame& frame = frames_[size_++];
        frame = {};
        frame.length = 24;
        frame.monotonicUs = monotonicUs;
        frame.channel = channel;
        frame.rssiDbm = rssiDbm;
        frame.payload[0] = static_cast<std::uint8_t>(subtype << 4U);
        frame.payload[1] = 0;
        std::memcpy(frame.payload.data() + 10U, transmitter.data(),
                    transmitter.size());
    }

    void addIdentityAdvertisement(
        std::uint8_t subtype, std::uint64_t monotonicUs,
        const std::array<std::uint8_t, 6>& transmitter,
        const char* networkName, AirspaceWifiSecurity security,
        std::uint8_t channel = 6, std::int16_t rssiDbm = -60) {
        CHECK(size_ < frames_.size());
        CHECK(networkName != nullptr);
        const std::size_t nameLength = std::strlen(networkName);
        CHECK(nameLength <= AirspaceFinding::kNetworkNameCapacity);
        FixtureFrame& frame = frames_[size_++];
        frame = {};
        frame.monotonicUs = monotonicUs;
        frame.channel = channel;
        frame.rssiDbm = rssiDbm;
        frame.payload[0] = static_cast<std::uint8_t>(subtype << 4U);
        std::memcpy(frame.payload.data() + 10U, transmitter.data(),
                    transmitter.size());
        std::memcpy(frame.payload.data() + 16U, transmitter.data(),
                    transmitter.size());
        if (security != AirspaceWifiSecurity::Open) {
            frame.payload[34] = 0x10U;
        }
        std::size_t offset = 36U;
        frame.payload[offset++] = 0U;
        frame.payload[offset++] = static_cast<std::uint8_t>(nameLength);
        std::memcpy(frame.payload.data() + offset, networkName, nameLength);
        offset += nameLength;
        if (security == AirspaceWifiSecurity::Rsn) {
            frame.payload[offset++] = 48U;
            frame.payload[offset++] = 2U;
            frame.payload[offset++] = 1U;
            frame.payload[offset++] = 0U;
        } else if (security == AirspaceWifiSecurity::Wpa) {
            frame.payload[offset++] = 221U;
            frame.payload[offset++] = 4U;
            frame.payload[offset++] = 0x00U;
            frame.payload[offset++] = 0x50U;
            frame.payload[offset++] = 0xf2U;
            frame.payload[offset++] = 0x01U;
        }
        frame.length = static_cast<std::uint16_t>(offset);
    }

    FixtureFrame& mutableAt(std::size_t index) {
        CHECK(index < size_);
        return frames_[index];
    }

    std::size_t frameCount() const override { return size_; }
    std::uint16_t snapLength() const override { return 96; }
    bool frameView(std::size_t index, WifiFrameView* output) const override {
        if (output == nullptr || index >= size_ || !frames_[index].readable) {
            return false;
        }
        const FixtureFrame& frame = frames_[index];
        output->monotonicUs = frame.monotonicUs;
        output->capturedLength = frame.length;
        output->originalLength = frame.length;
        output->rssiDbm = frame.rssiDbm;
        output->channel = frame.channel;
        output->kind = frame.kind;
        output->fcsIncluded = frame.fcsIncluded;
        output->payload = frame.payload.data();
        return true;
    }

private:
    std::array<FixtureFrame, kCapacity> frames_{};
    std::size_t size_ = 0;
};

constexpr std::array<std::uint8_t, 6> kTransmitterA{
    0x02, 0x11, 0x22, 0x33, 0x44, 0x55};
constexpr std::array<std::uint8_t, 6> kTransmitterB{
    0x06, 0xaa, 0xbb, 0xcc, 0xdd, 0xee};

void testPolicyAndEmptyEvidenceFailClosed() {
    AirspaceGuard guard;
    FixtureSource empty;
    AirspaceGuardPolicy invalid{};
    invalid.disconnectBurstThreshold = 1;
    CHECK(!validateAirspaceGuardPolicy(invalid));
    CHECK(guard.inspectWifi(empty, invalid).status ==
          AirspaceGuardStatus::InvalidPolicy);
    invalid = {};
    invalid.disconnectWindowUs = 99999;
    CHECK(!validateAirspaceGuardPolicy(invalid));
    invalid = {};
    invalid.ssidSecurityConflictWindowUs = 10000001ULL;
    CHECK(!validateAirspaceGuardPolicy(invalid));

    const AirspaceGuardReport report = guard.inspectWifi(empty);
    CHECK(report.status == AirspaceGuardStatus::Inconclusive);
    CHECK(report.framesAvailable == 0);
    CHECK(report.findingCount == 0);
}

void testIngressClassifiersStayManagementOnly() {
    const std::array<std::uint8_t, 2> deauth{0xc0, 0x00};
    const std::array<std::uint8_t, 2> disassoc{0xa0, 0x00};
    const std::array<std::uint8_t, 2> beacon{0x80, 0x00};
    const std::array<std::uint8_t, 2> probeResponse{0x50, 0x00};
    const std::array<std::uint8_t, 2> data{0x08, 0x00};
    CHECK(isWifiDisconnectFrameCandidate(deauth.data(), deauth.size()));
    CHECK(isWifiDisconnectFrameCandidate(disassoc.data(), disassoc.size()));
    CHECK(!isWifiDisconnectFrameCandidate(beacon.data(), beacon.size()));
    CHECK(!isWifiDisconnectFrameCandidate(data.data(), data.size()));
    CHECK(!isWifiDisconnectFrameCandidate(nullptr, 0U));
    CHECK(!isWifiDisconnectFrameCandidate(deauth.data(), 1U));
    CHECK(isWifiIdentityAdvertisementCandidate(beacon.data(), beacon.size()));
    CHECK(isWifiIdentityAdvertisementCandidate(
        probeResponse.data(), probeResponse.size()));
    CHECK(!isWifiIdentityAdvertisementCandidate(
        deauth.data(), deauth.size()));
    CHECK(!isWifiIdentityAdvertisementCandidate(nullptr, 0U));
}

AirspaceGuardPolicy identityPolicy() {
    AirspaceGuardPolicy policy{};
    policy.ssidSecurityConflictEnabled = true;
    return policy;
}

void testIdentityConflictIsOptInUntilLiveRetentionIsComplete() {
    FixtureSource source;
    source.addIdentityAdvertisement(8U, 1000000ULL, kTransmitterA,
                                    "Workshop", AirspaceWifiSecurity::Open);
    source.addIdentityAdvertisement(5U, 1200000ULL, kTransmitterB,
                                    "Workshop", AirspaceWifiSecurity::Rsn);
    const AirspaceGuardReport report = AirspaceGuard{}.inspectWifi(source);
    CHECK(report.status == AirspaceGuardStatus::Clear);
    CHECK(report.identityAdvertisementFrames == 0U);
    CHECK(report.findingCount == 0U);
}

void testIdentityConflictRetainsTwoExactAdvertisements() {
    FixtureSource source;
    source.addIdentityAdvertisement(8U, 1000000ULL, kTransmitterA,
                                    "Workshop", AirspaceWifiSecurity::Open,
                                    1U, -35);
    source.addIdentityAdvertisement(5U, 1200000ULL, kTransmitterB,
                                    "Workshop", AirspaceWifiSecurity::Rsn,
                                    11U, -52);
    const AirspaceGuardReport report =
        AirspaceGuard{}.inspectWifi(source, identityPolicy());
    CHECK(report.status == AirspaceGuardStatus::Finding);
    CHECK(report.identityAdvertisementFrames == 2U);
    CHECK(report.findingCount == 1U);
    const AirspaceFinding& finding = report.findings[0];
    CHECK(finding.kind ==
          AirspaceFindingKind::WifiSsidSecurityConflict);
    CHECK(finding.confidence == AirspaceConfidence::Medium);
    CHECK(finding.detectorVersion ==
          AirspaceFinding::kWifiIdentityDetectorVersion);
    CHECK(finding.threshold == 2U);
    CHECK(finding.observed == 2U);
    CHECK(finding.transmitter == kTransmitterA);
    CHECK(finding.relatedTransmitter == kTransmitterB);
    CHECK(finding.networkNameLength == 8U);
    CHECK(std::memcmp(finding.networkName.data(), "Workshop", 8U) == 0);
    CHECK(finding.primarySecurity == AirspaceWifiSecurity::Open);
    CHECK(finding.relatedSecurity == AirspaceWifiSecurity::Rsn);
    CHECK(finding.firstUs == 1000000ULL);
    CHECK(finding.lastUs == 1200000ULL);
    CHECK(finding.evidenceCount == 2U);
    CHECK(finding.evidence[0].frameIndex == 0U);
    CHECK(finding.evidence[0].channel == 1U);
    CHECK(finding.evidence[0].rssiDbm == -35);
    CHECK(finding.evidence[1].frameIndex == 1U);
    CHECK(finding.evidence[1].channel == 11U);
    CHECK(finding.evidence[1].rssiDbm == -52);
}

void testIdentityDetectorRejectsLookalikesAndMalformedEvidence() {
    FixtureSource sameSecurity;
    sameSecurity.addIdentityAdvertisement(
        8U, 1000000ULL, kTransmitterA, "Workshop",
        AirspaceWifiSecurity::Rsn);
    sameSecurity.addIdentityAdvertisement(
        8U, 1100000ULL, kTransmitterB, "Workshop",
        AirspaceWifiSecurity::Rsn);
    CHECK(AirspaceGuard{}.inspectWifi(sameSecurity, identityPolicy()).status ==
          AirspaceGuardStatus::Clear);

    FixtureSource differentNames;
    differentNames.addIdentityAdvertisement(
        8U, 1000000ULL, kTransmitterA, "Workshop",
        AirspaceWifiSecurity::Open);
    differentNames.addIdentityAdvertisement(
        8U, 1100000ULL, kTransmitterB, "Workshop-Guest",
        AirspaceWifiSecurity::Rsn);
    CHECK(AirspaceGuard{}.inspectWifi(differentNames, identityPolicy()).status ==
          AirspaceGuardStatus::Clear);

    FixtureSource outsideWindow;
    outsideWindow.addIdentityAdvertisement(
        8U, 1000000ULL, kTransmitterA, "Workshop",
        AirspaceWifiSecurity::Open);
    outsideWindow.addIdentityAdvertisement(
        8U, 12000000ULL, kTransmitterB, "Workshop",
        AirspaceWifiSecurity::Rsn);
    CHECK(AirspaceGuard{}.inspectWifi(outsideWindow, identityPolicy()).status ==
          AirspaceGuardStatus::Clear);

    FixtureSource malformed;
    malformed.addIdentityAdvertisement(
        8U, 1000000ULL, kTransmitterA, "Workshop",
        AirspaceWifiSecurity::Open);
    malformed.mutableAt(0).length = 37U;
    const AirspaceGuardReport malformedReport =
        AirspaceGuard{}.inspectWifi(malformed, identityPolicy());
    CHECK(malformedReport.status == AirspaceGuardStatus::Inconclusive);
    CHECK(malformedReport.malformedFrames == 1U);
}

void testIdentityParserExcludesCapturedFcsFromInformationElements() {
    FixtureSource source;
    source.addIdentityAdvertisement(8U, 1000000ULL, kTransmitterA,
                                    "Workshop", AirspaceWifiSecurity::Open);
    FixtureFrame& frame = source.mutableAt(0);
    frame.fcsIncluded = true;
    frame.length = static_cast<std::uint16_t>(frame.length + 4U);
    const AirspaceGuardReport report =
        AirspaceGuard{}.inspectWifi(source, identityPolicy());
    CHECK(report.status == AirspaceGuardStatus::Clear);
    CHECK(report.identityAdvertisementFrames == 1U);
    CHECK(report.malformedFrames == 0U);
}

void testExternalCaptureLossMakesClearEvidenceInconclusive() {
    FixtureSource source;
    source.add(8U, 1000000ULL, kTransmitterA, 1U, -40);
    AirspaceGuard guard;
    const AirspaceGuardReport report = guard.inspectWifi(source, {}, 3U);
    CHECK(report.status == AirspaceGuardStatus::Inconclusive);
    CHECK(report.sourceFramesDropped == 3U);
    CHECK(report.framesInspected == 1U);
}

void testBenignAndSparseDisconnectFramesStayClear() {
    AirspaceGuard guard;
    FixtureSource source;
    source.add(8, 1000000, kTransmitterA);
    source.add(12, 1100000, kTransmitterA);
    source.add(10, 1500000, kTransmitterA);
    source.add(12, 2900000, kTransmitterA);
    source.add(12, 4000000, kTransmitterA);
    source.mutableAt(0).kind = WifiFrameKind::Data;

    const AirspaceGuardReport report = guard.inspectWifi(source);
    CHECK(report.status == AirspaceGuardStatus::Clear);
    CHECK(report.framesInspected == 5);
    CHECK(report.disconnectFrames == 4);
    CHECK(report.findingCount == 0);
}

void testDisconnectBurstRetainsExactEvidence() {
    AirspaceGuard guard;
    FixtureSource source;
    source.add(8, 900000, kTransmitterB, 1, -80);
    source.add(12, 1000000, kTransmitterA, 6, -40);
    source.add(10, 1200000, kTransmitterA, 6, -42);
    source.add(12, 1500000, kTransmitterA, 11, -44);
    source.add(10, 1900000, kTransmitterA, 11, -46);

    const AirspaceGuardReport report = guard.inspectWifi(source);
    CHECK(report.status == AirspaceGuardStatus::Finding);
    CHECK(report.findingCount == 1);
    const AirspaceFinding& finding = report.findings[0];
    CHECK(finding.kind == AirspaceFindingKind::WifiDisconnectBurst);
    CHECK(finding.confidence == AirspaceConfidence::Medium);
    CHECK(finding.detectorVersion == 1);
    CHECK(finding.threshold == 4);
    CHECK(finding.observed == 4);
    CHECK(finding.deauthenticationFrames == 2);
    CHECK(finding.disassociationFrames == 2);
    CHECK(finding.transmitter == kTransmitterA);
    CHECK(finding.firstUs == 1000000);
    CHECK(finding.lastUs == 1900000);
    CHECK(finding.evidenceCount == 4);
    CHECK(finding.evidence[0].frameIndex == 1);
    CHECK(finding.evidence[1].frameIndex == 2);
    CHECK(finding.evidence[2].frameIndex == 3);
    CHECK(finding.evidence[3].frameIndex == 4);
    CHECK(finding.evidence[2].channel == 11);
    CHECK(finding.evidence[3].rssiDbm == -46);
}

void testSourcesAreNeverMergedAndConfidenceIsBounded() {
    AirspaceGuard guard;
    FixtureSource split;
    split.add(12, 1000000, kTransmitterA);
    split.add(12, 1100000, kTransmitterA);
    split.add(12, 1200000, kTransmitterB);
    split.add(12, 1300000, kTransmitterB);
    CHECK(guard.inspectWifi(split).status == AirspaceGuardStatus::Clear);

    FixtureSource high;
    for (std::size_t index = 0; index < 8; ++index) {
        high.add(index % 2U == 0U ? 12 : 10,
                 2000000 + index * 100000, kTransmitterA);
    }
    const AirspaceGuardReport report = guard.inspectWifi(high);
    CHECK(report.status == AirspaceGuardStatus::Finding);
    CHECK(report.findingCount == 1);
    CHECK(report.findings[0].confidence == AirspaceConfidence::High);
    CHECK(report.findings[0].observed == 8);
    CHECK(report.findings[0].evidenceCount == 8);
}

void testMalformedFailedAndTruncatedEvidenceIsInconclusive() {
    AirspaceGuard guard;
    FixtureSource malformed;
    malformed.add(12, 1000000, kTransmitterA);
    malformed.mutableAt(0).length = 10;
    CHECK(guard.inspectWifi(malformed).status ==
          AirspaceGuardStatus::Inconclusive);

    FixtureSource failed;
    failed.add(12, 1000000, kTransmitterA);
    failed.mutableAt(0).readable = false;
    const AirspaceGuardReport failedReport = guard.inspectWifi(failed);
    CHECK(failedReport.status == AirspaceGuardStatus::Inconclusive);
    CHECK(failedReport.sourceReadFailures == 1);

    FixtureSource truncated;
    for (std::size_t index = 0; index < 65; ++index) {
        truncated.add(8, 1000000 + index, kTransmitterA);
    }
    const AirspaceGuardReport truncatedReport = guard.inspectWifi(truncated);
    CHECK(truncatedReport.status == AirspaceGuardStatus::Inconclusive);
    CHECK(truncatedReport.framesInspected == 64);
    CHECK(truncatedReport.inspectionTruncated);
}

void testStableNames() {
    CHECK(std::strcmp(airspaceGuardStatusName(AirspaceGuardStatus::Finding),
                      "finding") == 0);
    CHECK(std::strcmp(airspaceFindingKindName(
                          AirspaceFindingKind::WifiDisconnectBurst),
                      "wifi_disconnect_burst") == 0);
    CHECK(std::strcmp(airspaceFindingKindName(
                          AirspaceFindingKind::WifiSsidSecurityConflict),
                      "wifi_ssid_security_conflict") == 0);
    CHECK(std::strcmp(airspaceWifiSecurityName(AirspaceWifiSecurity::Rsn),
                      "rsn") == 0);
    CHECK(std::strcmp(airspaceConfidenceName(AirspaceConfidence::Medium),
                      "medium") == 0);
}

}  // namespace

int main() {
    testPolicyAndEmptyEvidenceFailClosed();
    testIngressClassifiersStayManagementOnly();
    testIdentityConflictIsOptInUntilLiveRetentionIsComplete();
    testIdentityConflictRetainsTwoExactAdvertisements();
    testIdentityDetectorRejectsLookalikesAndMalformedEvidence();
    testIdentityParserExcludesCapturedFcsFromInformationElements();
    testExternalCaptureLossMakesClearEvidenceInconclusive();
    testBenignAndSparseDisconnectFramesStayClear();
    testDisconnectBurstRetainsExactEvidence();
    testSourcesAreNeverMergedAndConfidenceIsBounded();
    testMalformedFailedAndTruncatedEvidenceIsInconclusive();
    testStableNames();
    std::puts("Airspace Guard detector tests passed");
    return 0;
}
