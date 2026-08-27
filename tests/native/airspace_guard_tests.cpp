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
    std::array<std::uint8_t, 32> payload{};
    std::uint16_t length = 24;
    std::uint64_t monotonicUs = 0;
    std::int16_t rssiDbm = -60;
    std::uint8_t channel = 6;
    WifiFrameKind kind = WifiFrameKind::Management;
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

    FixtureFrame& mutableAt(std::size_t index) {
        CHECK(index < size_);
        return frames_[index];
    }

    std::size_t frameCount() const override { return size_; }
    std::uint16_t snapLength() const override { return 32; }
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
        output->fcsIncluded = false;
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

    const AirspaceGuardReport report = guard.inspectWifi(empty);
    CHECK(report.status == AirspaceGuardStatus::Inconclusive);
    CHECK(report.framesAvailable == 0);
    CHECK(report.findingCount == 0);
}

void testIngressClassifierOnlyReservesDisconnectManagementFrames() {
    const std::array<std::uint8_t, 2> deauth{0xc0, 0x00};
    const std::array<std::uint8_t, 2> disassoc{0xa0, 0x00};
    const std::array<std::uint8_t, 2> beacon{0x80, 0x00};
    const std::array<std::uint8_t, 2> data{0x08, 0x00};
    CHECK(isWifiDisconnectFrameCandidate(deauth.data(), deauth.size()));
    CHECK(isWifiDisconnectFrameCandidate(disassoc.data(), disassoc.size()));
    CHECK(!isWifiDisconnectFrameCandidate(beacon.data(), beacon.size()));
    CHECK(!isWifiDisconnectFrameCandidate(data.data(), data.size()));
    CHECK(!isWifiDisconnectFrameCandidate(nullptr, 0U));
    CHECK(!isWifiDisconnectFrameCandidate(deauth.data(), 1U));
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
    CHECK(std::strcmp(airspaceConfidenceName(AirspaceConfidence::Medium),
                      "medium") == 0);
}

}  // namespace

int main() {
    testPolicyAndEmptyEvidenceFailClosed();
    testIngressClassifierOnlyReservesDisconnectManagementFrames();
    testExternalCaptureLossMakesClearEvidenceInconclusive();
    testBenignAndSparseDisconnectFramesStayClear();
    testDisconnectBurstRetainsExactEvidence();
    testSourcesAreNeverMergedAndConfidenceIsBounded();
    testMalformedFailedAndTruncatedEvidenceIsInconclusive();
    testStableNames();
    std::puts("Airspace Guard detector tests passed");
    return 0;
}
