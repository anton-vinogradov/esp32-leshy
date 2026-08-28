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

struct BleFixtureRecord final {
    leshy1::domain::observations::Observation observation{};
    bool readable = true;
};

class BleFixtureSource final : public BleObservationSource {
public:
    static constexpr std::size_t kCapacity = 80;

    void add(const std::array<std::uint8_t, 6>& identity,
             std::uint64_t monotonicUs,
             AirspaceBleTrackerProtocol protocol,
             std::int16_t rssiDbm = -60,
             std::uint8_t addressType = 1U) {
        CHECK(size_ < records_.size());
        auto& record = records_[size_++];
        record = {};
        auto& observation = record.observation;
        observation.radio =
            leshy1::domain::observations::RadioKind::Ble;
        observation.monotonicUs = monotonicUs;
        observation.rssiDbm = rssiDbm;
        observation.identity = identity;
        observation.identityLength = observation.identity.size();
        auto& facts = observation.bleAdvertisement;
        facts.present = true;
        facts.addressType = addressType;
        facts.payloadLength = 18U;
        switch (protocol) {
            case AirspaceBleTrackerProtocol::FindMy:
                facts.companyKnown = true;
                facts.companyId = 0x004cU;
                facts.appleContinuityType = 0x12U;
                break;
            case AirspaceBleTrackerProtocol::SmartTag:
                facts.knownServiceMask =
                    leshy1::domain::observations::BleAdvertisementFacts::
                        kServiceSmartTag;
                break;
            case AirspaceBleTrackerProtocol::Tile:
                facts.knownServiceMask =
                    leshy1::domain::observations::BleAdvertisementFacts::
                        kServiceTile;
                break;
            case AirspaceBleTrackerProtocol::None:
                break;
        }
    }

    BleFixtureRecord& mutableAt(std::size_t index) {
        CHECK(index < size_);
        return records_[index];
    }

    std::size_t observationCount() const override { return size_; }
    bool observationAt(
        std::size_t index,
        leshy1::domain::observations::Observation* output) const override {
        if (output == nullptr || index >= size_ || !records_[index].readable) {
            return false;
        }
        *output = records_[index].observation;
        return true;
    }

private:
    std::array<BleFixtureRecord, kCapacity> records_{};
    std::size_t size_ = 0U;
};

constexpr std::array<std::uint8_t, 6> kTransmitterA{
    0x02, 0x11, 0x22, 0x33, 0x44, 0x55};
constexpr std::array<std::uint8_t, 6> kTransmitterB{
    0x06, 0xaa, 0xbb, 0xcc, 0xdd, 0xee};
constexpr std::array<std::uint8_t, 6> kTransmitterC{
    0x72, 0x10, 0x20, 0x30, 0x40, 0x50};

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
    invalid = {};
    invalid.ssidChurnThreshold = 2U;
    CHECK(!validateAirspaceGuardPolicy(invalid));
    invalid = {};
    invalid.ssidChurnThreshold = 9U;
    CHECK(!validateAirspaceGuardPolicy(invalid));
    invalid = {};
    invalid.ssidChurnWindowUs = 99999ULL;
    CHECK(!validateAirspaceGuardPolicy(invalid));
    invalid = {};
    invalid.elevatedNoiseFloorDbm = -101;
    CHECK(!validateAirspaceGuardPolicy(invalid));
    invalid = {};
    invalid.elevatedNoiseFloorDbm = -29;
    CHECK(!validateAirspaceGuardPolicy(invalid));
    invalid = {};
    invalid.elevatedNoiseThreshold = 1U;
    CHECK(!validateAirspaceGuardPolicy(invalid));
    invalid = {};
    invalid.elevatedNoiseWindowUs = 10000001ULL;
    CHECK(!validateAirspaceGuardPolicy(invalid));
    invalid = {};
    invalid.bleTrackerPresenceThreshold = 1U;
    CHECK(!validateAirspaceGuardPolicy(invalid));
    invalid = {};
    invalid.bleTrackerPresenceThreshold = 9U;
    CHECK(!validateAirspaceGuardPolicy(invalid));
    invalid = {};
    invalid.bleTrackerPresenceWindowUs = 60000001ULL;
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

AirspaceGuardPolicy churnPolicy() {
    AirspaceGuardPolicy policy{};
    policy.ssidChurnEnabled = true;
    return policy;
}

AirspaceGuardPolicy noisePolicy() {
    AirspaceGuardPolicy policy{};
    policy.elevatedNoiseEnabled = true;
    return policy;
}

WifiNoiseFloorSample noiseSample(std::size_t observationIndex,
                                 std::uint64_t monotonicUs,
                                 std::uint8_t channel,
                                 std::int16_t rssiDbm,
                                 std::int16_t noiseFloorDbm) {
    return {observationIndex, monotonicUs, channel, rssiDbm,
            noiseFloorDbm};
}

AirspaceGuardPolicy bleTrackerPolicy() {
    AirspaceGuardPolicy policy{};
    policy.bleTrackerPresenceEnabled = true;
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

void testLiveIdentityRetentionKeyIsExactAndFailClosed() {
    FixtureSource source;
    source.addIdentityAdvertisement(8U, 1000000ULL, kTransmitterA,
                                    "Workshop", AirspaceWifiSecurity::Rsn);
    FixtureFrame& first = source.mutableAt(0U);
    WifiIdentityRetentionKey firstKey{};
    CHECK(wifiIdentityRetentionKey(
              first.payload.data(), first.length, false, &firstKey) ==
          WifiIdentityIngressStatus::RetainableAdvertisement);
    CHECK(firstKey.transmitter == kTransmitterA);
    CHECK(firstKey.networkNameLength == 8U);
    CHECK(firstKey.security == AirspaceWifiSecurity::Rsn);

    std::array<std::uint8_t, kWifiIdentityProjectionCapacity> projection{};
    const std::size_t projectionLength =
        writeWifiIdentityRetentionProjection(
            firstKey, projection.data(), projection.size());
    CHECK(projectionLength > 0U);
    CHECK(projectionLength <= projection.size());
    WifiIdentityRetentionKey projectedKey{};
    CHECK(wifiIdentityRetentionKey(
              projection.data(), projectionLength, true, &projectedKey) ==
          WifiIdentityIngressStatus::RetainableAdvertisement);
    CHECK(sameWifiIdentityRetentionKey(firstKey, projectedKey));
    CHECK(writeWifiIdentityRetentionProjection(
              firstKey, projection.data(), projectionLength - 1U) == 0U);

    FixtureSource duplicate;
    duplicate.addIdentityAdvertisement(5U, 1100000ULL, kTransmitterA,
                                       "Workshop",
                                       AirspaceWifiSecurity::Rsn);
    FixtureFrame& second = duplicate.mutableAt(0U);
    WifiIdentityRetentionKey secondKey{};
    CHECK(wifiIdentityRetentionKey(
              second.payload.data(), second.length, false, &secondKey) ==
          WifiIdentityIngressStatus::RetainableAdvertisement);
    CHECK(sameWifiIdentityRetentionKey(firstKey, secondKey));

    second.payload[34] = 0U;
    second.length = 46U;
    WifiIdentityRetentionKey changedKey{};
    CHECK(wifiIdentityRetentionKey(
              second.payload.data(), second.length, false, &changedKey) ==
          WifiIdentityIngressStatus::RetainableAdvertisement);
    CHECK(!sameWifiIdentityRetentionKey(firstKey, changedKey));

    FixtureSource hidden;
    hidden.addIdentityAdvertisement(8U, 1200000ULL, kTransmitterB, "",
                                    AirspaceWifiSecurity::Open);
    FixtureFrame& hiddenFrame = hidden.mutableAt(0U);
    WifiIdentityRetentionKey ignored{};
    CHECK(wifiIdentityRetentionKey(hiddenFrame.payload.data(),
                                   hiddenFrame.length, false, &ignored) ==
          WifiIdentityIngressStatus::IgnoredAdvertisement);

    first.length = 37U;
    CHECK(wifiIdentityRetentionKey(first.payload.data(), first.length, false,
                                   &firstKey) ==
          WifiIdentityIngressStatus::MalformedElements);
    CHECK(wifiIdentityIngressMalformed(
        WifiIdentityIngressStatus::MalformedElements));
    CHECK(wifiIdentityRetentionKey(nullptr, 0U, false, &firstKey) ==
          WifiIdentityIngressStatus::NotAdvertisement);
    CHECK(wifiIdentityRetentionKey(first.payload.data(), first.length, false,
                                   nullptr) ==
          WifiIdentityIngressStatus::MalformedEnvelope);

    first.length = 50U;
    std::memcpy(first.payload.data() + 16U, kTransmitterB.data(),
                kTransmitterB.size());
    CHECK(wifiIdentityRetentionKey(first.payload.data(), first.length, false,
                                   &firstKey) ==
          WifiIdentityIngressStatus::RetainableAdvertisement);
    CHECK(firstKey.transmitter == kTransmitterB);
    first.payload[16] |= 0x01U;
    CHECK(wifiIdentityRetentionKey(first.payload.data(), first.length, false,
                                   &firstKey) ==
          WifiIdentityIngressStatus::MalformedAddressing);
}

void testCompactIdentityRetentionKeepsDetectorCapacity() {
    constexpr std::size_t total = 16U;
    CHECK(wifiDisconnectRetentionSlotAvailable(total, 8U, 0U));
    CHECK(wifiDisconnectRetentionSlotAvailable(total, 15U, 7U));
    CHECK(!wifiDisconnectRetentionSlotAvailable(total, 16U, 7U));
    CHECK(!wifiDisconnectRetentionSlotAvailable(total, 15U, 8U));

    WifiIdentityProjectionRetention retention;
    CHECK(retention.accept({}, 1U, -50, 1U) ==
          WifiIdentityLiveRetentionDisposition::Invalid);
    for (std::size_t index = 0U;
         index < kWifiIdentityLiveRetentionCapacity; ++index) {
        WifiIdentityRetentionKey key{};
        key.transmitter = {0x02U, 0x00U, 0x00U, 0x00U,
                           static_cast<std::uint8_t>(index >> 8U),
                           static_cast<std::uint8_t>(index)};
        const int length = std::snprintf(
            reinterpret_cast<char*>(key.networkName.data()),
            key.networkName.size(), "N%02u",
            static_cast<unsigned>(index));
        CHECK(length > 0);
        key.networkNameLength = static_cast<std::uint8_t>(length);
        key.security = AirspaceWifiSecurity::Rsn;
        CHECK(retention.accept(key, 1000000ULL + index, -50, 6U) ==
              WifiIdentityLiveRetentionDisposition::Retained);
        CHECK(retention.accept(key, 2000000ULL + index, -40, 11U) ==
              WifiIdentityLiveRetentionDisposition::Duplicate);
    }
    CHECK(retention.size() == kWifiIdentityLiveRetentionCapacity);

    WifiIdentityRetentionKey overflow{};
    overflow.transmitter = {0x02U, 0xaaU, 0xbbU, 0xccU, 0xddU, 0xeeU};
    overflow.networkName[0] = 'X';
    overflow.networkNameLength = 1U;
    overflow.security = AirspaceWifiSecurity::Open;
    CHECK(retention.accept(overflow, 3000000ULL, -60, 1U) ==
          WifiIdentityLiveRetentionDisposition::Full);

    WifiFrameView projected{};
    CHECK(retention.frameView(0U, &projected));
    CHECK(projected.capturedLength <= kWifiIdentityProjectionCapacity);
    CHECK(projected.fcsIncluded);
    CHECK(projected.payload != nullptr);
    CHECK(!retention.frameView(retention.size(), &projected));

    FixtureSource disconnect;
    disconnect.add(12U, 500000ULL, kTransmitterB);
    CompositeWifiFrameSource source(disconnect, retention);
    CHECK(source.frameCount() ==
          1U + kWifiIdentityLiveRetentionCapacity);
    CHECK(source.frameCount() <= AirspaceGuard::kFrameInspectionCapacity);
    CHECK(source.frameView(0U, &projected));
    CHECK(projected.payload[0] == 0xc0U);
    CHECK(source.frameView(1U, &projected));
    CHECK(projected.payload[0] == 0x80U);
    CHECK(!source.frameView(source.frameCount(), &projected));
}

void testElevatedNoiseIsLowConfidenceExactAndOptIn() {
    FixtureSource source;
    for (std::size_t index = 0U; index < 4U; ++index) {
        source.add(8U, 1000000ULL + index * 300000ULL, kTransmitterA,
                   6U, static_cast<std::int16_t>(-45 - index));
    }
    const std::array<WifiNoiseFloorSample, 4> samples{
        noiseSample(0U, 1000000ULL, 6U, -45, -72),
        noiseSample(1U, 1300000ULL, 6U, -46, -70),
        noiseSample(2U, 1600000ULL, 6U, -47, -69),
        noiseSample(3U, 1900000ULL, 6U, -48, -71),
    };

    const AirspaceGuardReport disabled = AirspaceGuard{}.inspectWifi(
        source, {}, 0U, source.frameCount(), samples.data(), samples.size(),
        0U, samples.size());
    CHECK(disabled.status == AirspaceGuardStatus::Clear);
    CHECK(disabled.wifiNoiseSamplesInspected == samples.size());
    CHECK(disabled.findingCount == 0U);

    const AirspaceGuardReport report = AirspaceGuard{}.inspectWifi(
        source, noisePolicy(), 0U, source.frameCount(), samples.data(),
        samples.size(), 0U, samples.size());
    CHECK(report.status == AirspaceGuardStatus::Finding);
    CHECK(report.wifiNoiseSamplesObserved == samples.size());
    CHECK(report.wifiNoiseSamplesAvailable == samples.size());
    CHECK(report.wifiNoiseSamplesInspected == samples.size());
    CHECK(report.wifiNoiseSamplesDropped == 0U);
    CHECK(report.wifiNoiseSamplesMalformed == 0U);
    CHECK(report.findingCount == 1U);
    const AirspaceFinding& finding = report.findings[0];
    CHECK(finding.kind == AirspaceFindingKind::WifiElevatedNoise);
    CHECK(finding.confidence == AirspaceConfidence::Low);
    CHECK(finding.detectorVersion ==
          AirspaceFinding::kWifiElevatedNoiseDetectorVersion);
    CHECK(finding.threshold == 4U);
    CHECK(finding.observed == 4U);
    CHECK(finding.noiseFloorThresholdDbm == -75);
    CHECK((finding.transmitter == std::array<std::uint8_t, 6>{}));
    CHECK(finding.firstUs == 1000000ULL);
    CHECK(finding.lastUs == 1900000ULL);
    CHECK(finding.evidenceCount == 4U);
    for (std::size_t index = 0U; index < samples.size(); ++index) {
        CHECK(finding.evidence[index].frameIndex == index);
        CHECK(finding.evidence[index].channel == 6U);
        CHECK(finding.evidence[index].rssiDbm == samples[index].rssiDbm);
        CHECK(finding.evidence[index].noiseFloorDbm ==
              samples[index].noiseFloorDbm);
    }
}

void testElevatedNoiseRejectsWeakSplitStaleAndMalformedEvidence() {
    FixtureSource source;
    for (std::size_t index = 0U; index < 8U; ++index) {
        source.add(8U, 1000000ULL + index * 1000000ULL, kTransmitterA,
                   6U, -50);
    }
    const std::array<WifiNoiseFloorSample, 8> noBurst{
        noiseSample(0U, 1000000ULL, 6U, -50, -80),
        noiseSample(1U, 1200000ULL, 6U, -50, -76),
        noiseSample(2U, 1400000ULL, 1U, -50, -70),
        noiseSample(3U, 1600000ULL, 1U, -50, -71),
        noiseSample(4U, 4000000ULL, 1U, -50, -69),
        noiseSample(5U, 7000000ULL, 1U, -50, -68),
        noiseSample(6U, 7200000ULL, 11U, -50, -70),
        noiseSample(7U, 7400000ULL, 11U, -50, -71),
    };
    const AirspaceGuardReport clear = AirspaceGuard{}.inspectWifi(
        source, noisePolicy(), 0U, source.frameCount(), noBurst.data(),
        noBurst.size(), 0U, noBurst.size());
    CHECK(clear.status == AirspaceGuardStatus::Clear);
    CHECK(clear.findingCount == 0U);

    auto malformed = noBurst;
    malformed[0].channel = 0U;
    const AirspaceGuardReport bad = AirspaceGuard{}.inspectWifi(
        source, noisePolicy(), 0U, source.frameCount(), malformed.data(),
        malformed.size(), 0U, malformed.size());
    CHECK(bad.status == AirspaceGuardStatus::Inconclusive);
    CHECK(bad.wifiNoiseSamplesInspected == malformed.size() - 1U);
    CHECK(bad.wifiNoiseSamplesMalformed == 1U);
    CHECK(bad.findingCount == 0U);

    const AirspaceGuardReport dropped = AirspaceGuard{}.inspectWifi(
        source, noisePolicy(), 0U, source.frameCount(), noBurst.data(),
        noBurst.size(), 1U, noBurst.size() + 1U);
    CHECK(dropped.status == AirspaceGuardStatus::Inconclusive);
    CHECK(dropped.wifiNoiseSamplesDropped == 1U);
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

void testSsidChurnRetainsDistinctNamesFromOneBssid() {
    FixtureSource source;
    source.addIdentityAdvertisement(8U, 1000000ULL, kTransmitterA,
                                    "Cafe", AirspaceWifiSecurity::Open,
                                    1U, -35);
    source.addIdentityAdvertisement(5U, 1050000ULL, kTransmitterA,
                                    "Cafe", AirspaceWifiSecurity::Rsn,
                                    1U, -36);
    source.addIdentityAdvertisement(8U, 1100000ULL, kTransmitterA,
                                    "Airport", AirspaceWifiSecurity::Rsn,
                                    6U, -42);
    source.addIdentityAdvertisement(8U, 1200000ULL, kTransmitterA,
                                    "Hotel", AirspaceWifiSecurity::Wpa,
                                    11U, -48);
    source.addIdentityAdvertisement(5U, 1300000ULL, kTransmitterA,
                                    "Free WiFi", AirspaceWifiSecurity::Open,
                                    13U, -53);

    const AirspaceGuardReport report =
        AirspaceGuard{}.inspectWifi(source, churnPolicy());
    CHECK(report.status == AirspaceGuardStatus::Finding);
    CHECK(report.identityAdvertisementFrames == 5U);
    CHECK(report.findingCount == 1U);
    const AirspaceFinding& finding = report.findings[0];
    CHECK(finding.kind == AirspaceFindingKind::WifiSsidChurn);
    CHECK(finding.confidence == AirspaceConfidence::Medium);
    CHECK(finding.detectorVersion ==
          AirspaceFinding::kWifiSsidChurnDetectorVersion);
    CHECK(finding.threshold == 4U);
    CHECK(finding.observed == 4U);
    CHECK(finding.transmitter == kTransmitterA);
    CHECK((finding.relatedTransmitter ==
           std::array<std::uint8_t, 6>{}));
    CHECK(finding.networkNameLength == 0U);
    CHECK(finding.firstUs == 1000000ULL);
    CHECK(finding.lastUs == 1300000ULL);
    CHECK(finding.evidenceCount == 4U);
    CHECK(finding.evidence[0].frameIndex == 0U);
    CHECK(finding.evidence[1].frameIndex == 2U);
    CHECK(finding.evidence[2].frameIndex == 3U);
    CHECK(finding.evidence[3].frameIndex == 4U);
    CHECK(finding.evidence[3].channel == 13U);
    CHECK(finding.evidence[3].rssiDbm == -53);
}

void testSsidChurnRejectsLookalikesAndIncompleteEvidence() {
    FixtureSource belowThreshold;
    belowThreshold.addIdentityAdvertisement(
        8U, 1000000ULL, kTransmitterA, "One", AirspaceWifiSecurity::Open);
    belowThreshold.addIdentityAdvertisement(
        8U, 1100000ULL, kTransmitterA, "Two", AirspaceWifiSecurity::Rsn);
    belowThreshold.addIdentityAdvertisement(
        8U, 1200000ULL, kTransmitterA, "Three", AirspaceWifiSecurity::Wpa);
    CHECK(AirspaceGuard{}.inspectWifi(belowThreshold, churnPolicy()).status ==
          AirspaceGuardStatus::Clear);

    FixtureSource splitTransmitters;
    splitTransmitters.addIdentityAdvertisement(
        8U, 1000000ULL, kTransmitterA, "One", AirspaceWifiSecurity::Open);
    splitTransmitters.addIdentityAdvertisement(
        8U, 1100000ULL, kTransmitterA, "Two", AirspaceWifiSecurity::Open);
    splitTransmitters.addIdentityAdvertisement(
        8U, 1200000ULL, kTransmitterB, "Three", AirspaceWifiSecurity::Open);
    splitTransmitters.addIdentityAdvertisement(
        8U, 1300000ULL, kTransmitterB, "Four", AirspaceWifiSecurity::Open);
    CHECK(AirspaceGuard{}.inspectWifi(splitTransmitters, churnPolicy()).status ==
          AirspaceGuardStatus::Clear);

    FixtureSource outsideWindow;
    outsideWindow.addIdentityAdvertisement(
        8U, 1000000ULL, kTransmitterA, "One", AirspaceWifiSecurity::Open);
    outsideWindow.addIdentityAdvertisement(
        8U, 12000000ULL, kTransmitterA, "Two", AirspaceWifiSecurity::Open);
    outsideWindow.addIdentityAdvertisement(
        8U, 23000000ULL, kTransmitterA, "Three", AirspaceWifiSecurity::Open);
    outsideWindow.addIdentityAdvertisement(
        8U, 34000000ULL, kTransmitterA, "Four", AirspaceWifiSecurity::Open);
    CHECK(AirspaceGuard{}.inspectWifi(outsideWindow, churnPolicy()).status ==
          AirspaceGuardStatus::Clear);

    FixtureSource repeatedName;
    repeatedName.addIdentityAdvertisement(
        8U, 1000000ULL, kTransmitterA, "Workshop",
        AirspaceWifiSecurity::Open);
    repeatedName.addIdentityAdvertisement(
        5U, 1100000ULL, kTransmitterA, "Workshop",
        AirspaceWifiSecurity::LegacyPrivacy);
    repeatedName.addIdentityAdvertisement(
        8U, 1200000ULL, kTransmitterA, "Workshop",
        AirspaceWifiSecurity::Wpa);
    repeatedName.addIdentityAdvertisement(
        5U, 1300000ULL, kTransmitterA, "Workshop",
        AirspaceWifiSecurity::Rsn);
    CHECK(AirspaceGuard{}.inspectWifi(repeatedName, churnPolicy()).status ==
          AirspaceGuardStatus::Clear);

    FixtureSource malformed;
    malformed.addIdentityAdvertisement(
        8U, 1000000ULL, kTransmitterA, "One", AirspaceWifiSecurity::Open);
    malformed.mutableAt(0U).length = 37U;
    const AirspaceGuardReport malformedReport =
        AirspaceGuard{}.inspectWifi(malformed, churnPolicy());
    CHECK(malformedReport.status == AirspaceGuardStatus::Inconclusive);
    CHECK(malformedReport.malformedFrames == 1U);
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

void testBleTrackerPresenceIsOptInAndRetainsExactEvidence() {
    BleFixtureSource source;
    source.add(kTransmitterA, 1000000ULL,
               AirspaceBleTrackerProtocol::FindMy, -58);
    source.add(kTransmitterB, 1050000ULL,
               AirspaceBleTrackerProtocol::None, -72);
    source.add(kTransmitterA, 1300000ULL,
               AirspaceBleTrackerProtocol::FindMy, -55);
    source.add(kTransmitterA, 1600000ULL,
               AirspaceBleTrackerProtocol::FindMy, -53);

    const AirspaceGuardReport disabled = AirspaceGuard{}.inspectBle(source);
    CHECK(disabled.status == AirspaceGuardStatus::Clear);
    CHECK(disabled.bleAdvertisementRecords == 4U);
    CHECK(disabled.findingCount == 0U);

    const AirspaceGuardReport report =
        AirspaceGuard{}.inspectBle(source, bleTrackerPolicy());
    CHECK(report.status == AirspaceGuardStatus::Finding);
    CHECK(report.sourceFramesObserved == 4U);
    CHECK(report.framesInspected == 4U);
    CHECK(report.bleAdvertisementRecords == 4U);
    CHECK(report.findingCount == 1U);
    const AirspaceFinding& finding = report.findings[0];
    CHECK(finding.kind == AirspaceFindingKind::BleTrackerPresence);
    CHECK(finding.confidence == AirspaceConfidence::Medium);
    CHECK(finding.detectorVersion ==
          AirspaceFinding::kBleTrackerPresenceDetectorVersion);
    CHECK(finding.threshold == 3U);
    CHECK(finding.observed == 3U);
    CHECK(finding.transmitter == kTransmitterA);
    CHECK(finding.bleTrackerProtocol ==
          AirspaceBleTrackerProtocol::FindMy);
    CHECK(finding.bleAddressType == 1U);
    CHECK(finding.firstUs == 1000000ULL);
    CHECK(finding.lastUs == 1600000ULL);
    CHECK(finding.evidenceCount == 3U);
    CHECK(finding.evidence[0].frameIndex == 0U);
    CHECK(finding.evidence[1].frameIndex == 2U);
    CHECK(finding.evidence[2].frameIndex == 3U);
    CHECK(finding.evidence[0].channel == 0U);
    CHECK(finding.evidence[2].rssiDbm == -53);
}

void testBleTrackerPresenceRejectsLookalikesAndStaleEvidence() {
    const AirspaceGuardPolicy policy = bleTrackerPolicy();

    BleFixtureSource belowThreshold;
    belowThreshold.add(kTransmitterA, 1000000ULL,
                       AirspaceBleTrackerProtocol::Tile);
    belowThreshold.add(kTransmitterA, 1200000ULL,
                       AirspaceBleTrackerProtocol::Tile);
    CHECK(AirspaceGuard{}.inspectBle(belowThreshold, policy).status ==
          AirspaceGuardStatus::Clear);

    BleFixtureSource splitIdentities;
    splitIdentities.add(kTransmitterA, 1000000ULL,
                        AirspaceBleTrackerProtocol::SmartTag);
    splitIdentities.add(kTransmitterA, 1100000ULL,
                        AirspaceBleTrackerProtocol::SmartTag);
    splitIdentities.add(kTransmitterB, 1200000ULL,
                        AirspaceBleTrackerProtocol::SmartTag);
    CHECK(AirspaceGuard{}.inspectBle(splitIdentities, policy).status ==
          AirspaceGuardStatus::Clear);

    BleFixtureSource splitProtocols;
    splitProtocols.add(kTransmitterA, 1000000ULL,
                       AirspaceBleTrackerProtocol::FindMy);
    splitProtocols.add(kTransmitterA, 1100000ULL,
                       AirspaceBleTrackerProtocol::SmartTag);
    splitProtocols.add(kTransmitterA, 1200000ULL,
                       AirspaceBleTrackerProtocol::Tile);
    CHECK(AirspaceGuard{}.inspectBle(splitProtocols, policy).status ==
          AirspaceGuardStatus::Clear);

    BleFixtureSource splitAddressTypes;
    splitAddressTypes.add(kTransmitterA, 1000000ULL,
                          AirspaceBleTrackerProtocol::Tile, -60, 0U);
    splitAddressTypes.add(kTransmitterA, 1100000ULL,
                          AirspaceBleTrackerProtocol::Tile, -60, 0U);
    splitAddressTypes.add(kTransmitterA, 1200000ULL,
                          AirspaceBleTrackerProtocol::Tile, -60, 1U);
    CHECK(AirspaceGuard{}.inspectBle(splitAddressTypes, policy).status ==
          AirspaceGuardStatus::Clear);

    BleFixtureSource stale;
    stale.add(kTransmitterA, 1000000ULL,
              AirspaceBleTrackerProtocol::FindMy);
    stale.add(kTransmitterA, 12000000ULL,
              AirspaceBleTrackerProtocol::FindMy);
    stale.add(kTransmitterA, 23000000ULL,
              AirspaceBleTrackerProtocol::FindMy);
    CHECK(AirspaceGuard{}.inspectBle(stale, policy).status ==
          AirspaceGuardStatus::Clear);
}

void testBleTrackerProtocolsRemainDistinct() {
    AirspaceGuardPolicy policy = bleTrackerPolicy();
    policy.bleTrackerPresenceThreshold = 2U;
    BleFixtureSource source;
    for (std::size_t repeat = 0U; repeat < 2U; ++repeat) {
        const std::uint64_t time = 1000000ULL + repeat * 100000ULL;
        source.add(kTransmitterA, time,
                   AirspaceBleTrackerProtocol::FindMy);
        source.add(kTransmitterB, time,
                   AirspaceBleTrackerProtocol::SmartTag);
        source.add(kTransmitterC, time,
                   AirspaceBleTrackerProtocol::Tile);
    }
    const AirspaceGuardReport report =
        AirspaceGuard{}.inspectBle(source, policy);
    CHECK(report.status == AirspaceGuardStatus::Finding);
    CHECK(report.findingCount == 3U);
    CHECK(report.findings[0].bleTrackerProtocol ==
          AirspaceBleTrackerProtocol::FindMy);
    CHECK(report.findings[1].bleTrackerProtocol ==
          AirspaceBleTrackerProtocol::SmartTag);
    CHECK(report.findings[2].bleTrackerProtocol ==
          AirspaceBleTrackerProtocol::Tile);
    CHECK(report.findings[0].transmitter == kTransmitterA);
    CHECK(report.findings[1].transmitter == kTransmitterB);
    CHECK(report.findings[2].transmitter == kTransmitterC);
}

void testBleTrackerPresenceFailsClosedOnIncompleteEvidence() {
    const AirspaceGuardPolicy policy = bleTrackerPolicy();

    BleFixtureSource ambiguous;
    ambiguous.add(kTransmitterA, 1000000ULL,
                  AirspaceBleTrackerProtocol::FindMy);
    ambiguous.mutableAt(0).observation.bleAdvertisement.knownServiceMask |=
        leshy1::domain::observations::BleAdvertisementFacts::kServiceTile;
    const AirspaceGuardReport ambiguousReport =
        AirspaceGuard{}.inspectBle(ambiguous, policy);
    CHECK(ambiguousReport.status == AirspaceGuardStatus::Inconclusive);
    CHECK(ambiguousReport.malformedFrames == 1U);
    CHECK(ambiguousReport.findingCount == 0U);

    BleFixtureSource failed;
    failed.add(kTransmitterA, 1000000ULL,
               AirspaceBleTrackerProtocol::Tile);
    failed.mutableAt(0).readable = false;
    const AirspaceGuardReport failedReport =
        AirspaceGuard{}.inspectBle(failed, policy);
    CHECK(failedReport.status == AirspaceGuardStatus::Inconclusive);
    CHECK(failedReport.sourceReadFailures == 1U);

    BleFixtureSource dropped;
    dropped.add(kTransmitterA, 1000000ULL,
                AirspaceBleTrackerProtocol::None);
    const AirspaceGuardReport droppedReport =
        AirspaceGuard{}.inspectBle(dropped, policy, 2U, 3U);
    CHECK(droppedReport.status == AirspaceGuardStatus::Inconclusive);
    CHECK(droppedReport.sourceFramesDropped == 2U);

    BleFixtureSource truncated;
    for (std::size_t index = 0U; index < 65U; ++index) {
        truncated.add(kTransmitterA, 1000000ULL + index,
                      AirspaceBleTrackerProtocol::None);
    }
    const AirspaceGuardReport truncatedReport =
        AirspaceGuard{}.inspectBle(truncated, policy);
    CHECK(truncatedReport.status == AirspaceGuardStatus::Inconclusive);
    CHECK(truncatedReport.framesInspected == 64U);
    CHECK(truncatedReport.inspectionTruncated);
}

void testLiveBleRetentionKeepsCoverageThenAllTrackerRepeats() {
    CHECK(sizeof(AirspaceGuardBleRetention) <= 2048U);
    AirspaceGuardBleRetention retention;
    BleFixtureSource fixture;
    fixture.add(kTransmitterA, 1000000ULL,
                AirspaceBleTrackerProtocol::None);
    CHECK(retention.accept(fixture.mutableAt(0).observation) ==
          BleLiveRetentionDisposition::Retained);
    CHECK(retention.observationCount() == 1U);
    CHECK(retention.stats().coverageOnly);

    fixture.add(kTransmitterB, 1100000ULL,
                AirspaceBleTrackerProtocol::None);
    CHECK(retention.accept(fixture.mutableAt(1).observation) ==
          BleLiveRetentionDisposition::Ignored);
    CHECK(retention.observationCount() == 1U);

    fixture.add(kTransmitterA, 1200000ULL,
                AirspaceBleTrackerProtocol::FindMy, -58, 1U);
    fixture.add(kTransmitterA, 1300000ULL,
                AirspaceBleTrackerProtocol::FindMy, -56, 1U);
    fixture.add(kTransmitterA, 1400000ULL,
                AirspaceBleTrackerProtocol::FindMy, -54, 1U);
    for (std::size_t index = 2U; index < 5U; ++index) {
        CHECK(retention.accept(fixture.mutableAt(index).observation) ==
              BleLiveRetentionDisposition::Retained);
    }
    CHECK(retention.observationCount() == 3U);
    CHECK(!retention.stats().coverageOnly);
    CHECK(retention.stats().recordsObserved == 5U);
    CHECK(retention.stats().validAdvertisements == 5U);
    CHECK(retention.stats().trackerAdvertisements == 3U);
    CHECK(retention.stats().recordsRetained == 3U);
    CHECK(retention.stats().advertisementsIgnored == 1U);
    CHECK(retention.stats().complete());

    AirspaceGuardPolicy policy = bleTrackerPolicy();
    const AirspaceGuardReport report = AirspaceGuard{}.inspectBle(
        retention, policy, 0U, retention.stats().recordsObserved);
    CHECK(report.status == AirspaceGuardStatus::Finding);
    CHECK(report.findingCount == 1U);
    CHECK(report.findings[0].observed == 3U);
    CHECK(report.findings[0].evidenceCount == 3U);
}

void testLiveBleRetentionFailsClosedOnMalformedOrCapacityLoss() {
    AirspaceGuardBleRetention retention;
    BleFixtureSource fixture;
    fixture.add(kTransmitterA, 1000000ULL,
                AirspaceBleTrackerProtocol::FindMy);
    fixture.mutableAt(0).observation.identity.fill(0U);
    CHECK(retention.accept(fixture.mutableAt(0).observation) ==
          BleLiveRetentionDisposition::Malformed);
    CHECK(!retention.stats().complete());
    CHECK(retention.observationCount() == 0U);

    retention.reset();
    BleFixtureSource redundant;
    for (std::size_t index = 0U;
         index < AirspaceFinding::kEvidenceCapacity + 3U; ++index) {
        redundant.add(kTransmitterA, 1500000ULL + index,
                      AirspaceBleTrackerProtocol::Tile);
        const BleLiveRetentionDisposition disposition =
            retention.accept(redundant.mutableAt(index).observation);
        CHECK(disposition ==
              (index < AirspaceFinding::kEvidenceCapacity
                   ? BleLiveRetentionDisposition::Retained
                   : BleLiveRetentionDisposition::Ignored));
    }
    CHECK(retention.observationCount() ==
          AirspaceFinding::kEvidenceCapacity);
    CHECK(retention.stats().advertisementsIgnored == 3U);
    CHECK(retention.stats().capacityDrops == 0U);
    CHECK(retention.stats().complete());

    retention.reset();
    BleFixtureSource repeats;
    for (std::size_t index = 0U;
         index < kBleTrackerLiveRetentionCapacity + 1U; ++index) {
        const std::array<std::uint8_t, 6> uniqueIdentity{
            0x02U, 0x11U, 0x22U, 0x33U,
            static_cast<std::uint8_t>(index >> 8U),
            static_cast<std::uint8_t>(index)};
        repeats.add(uniqueIdentity, 2000000ULL + index,
                    AirspaceBleTrackerProtocol::Tile);
        const BleLiveRetentionDisposition disposition =
            retention.accept(repeats.mutableAt(index).observation);
        CHECK(disposition ==
              (index < kBleTrackerLiveRetentionCapacity
                   ? BleLiveRetentionDisposition::Retained
                   : BleLiveRetentionDisposition::Full));
    }
    CHECK(retention.observationCount() ==
          kBleTrackerLiveRetentionCapacity);
    CHECK(retention.stats().capacityDrops == 1U);
    CHECK(!retention.stats().complete());
}

void testCompletedWifiAndBleReportsMergeWithoutInventingEvidence() {
    FixtureSource wifiSource;
    wifiSource.add(8U, 1000000ULL, kTransmitterB, 6U, -62);
    const AirspaceGuardReport wifi = AirspaceGuard{}.inspectWifi(wifiSource);
    CHECK(wifi.status == AirspaceGuardStatus::Clear);

    BleFixtureSource bleSource;
    bleSource.add(kTransmitterA, 2000000ULL,
                  AirspaceBleTrackerProtocol::SmartTag, -59, 1U);
    bleSource.add(kTransmitterA, 2100000ULL,
                  AirspaceBleTrackerProtocol::SmartTag, -57, 1U);
    bleSource.add(kTransmitterA, 2200000ULL,
                  AirspaceBleTrackerProtocol::SmartTag, -55, 1U);
    const AirspaceGuardReport ble = AirspaceGuard{}.inspectBle(
        bleSource, bleTrackerPolicy());
    CHECK(ble.status == AirspaceGuardStatus::Finding);

    AirspaceGuardReport merged{};
    CHECK(mergeAirspaceGuardReports(wifi, ble, &merged));
    CHECK(merged.status == AirspaceGuardStatus::Finding);
    CHECK(merged.framesAvailable == 4U);
    CHECK(merged.framesInspected == 4U);
    CHECK(merged.bleAdvertisementRecords == 3U);
    CHECK(merged.findingCount == 1U);
    CHECK(merged.findings[0].kind ==
          AirspaceFindingKind::BleTrackerPresence);
    CHECK(merged.findings[0].evidence[0].frameIndex == 0U);
    CHECK(merged.findings[0].evidence[0].channel == 0U);

    AirspaceGuardReport wrongSource = ble;
    wrongSource.disconnectFrames = 1U;
    CHECK(!mergeAirspaceGuardReports(wifi, wrongSource, &merged));
    CHECK(!mergeAirspaceGuardReports(wifi, ble, nullptr));
}

void testCompletedWifiAndBleReportsUseIndependentInspectionBudgets() {
    AirspaceGuardReport wifi{};
    wifi.status = AirspaceGuardStatus::Clear;
    wifi.sourceFramesObserved = AirspaceGuard::kFrameInspectionCapacity;
    wifi.framesAvailable = AirspaceGuard::kFrameInspectionCapacity;
    wifi.framesInspected = AirspaceGuard::kFrameInspectionCapacity;

    AirspaceGuardReport ble{};
    ble.status = AirspaceGuardStatus::Clear;
    ble.sourceFramesObserved = AirspaceGuard::kFrameInspectionCapacity;
    ble.framesAvailable = AirspaceGuard::kFrameInspectionCapacity;
    ble.framesInspected = AirspaceGuard::kFrameInspectionCapacity;
    ble.bleAdvertisementRecords = AirspaceGuard::kFrameInspectionCapacity;

    AirspaceGuardReport merged{};
    CHECK(mergeAirspaceGuardReports(wifi, ble, &merged));
    CHECK(merged.framesAvailable ==
          AirspaceGuard::kMergedFrameInspectionCapacity);
    CHECK(merged.framesInspected ==
          AirspaceGuard::kMergedFrameInspectionCapacity);
    CHECK(merged.status == AirspaceGuardStatus::Clear);

    ++ble.sourceFramesObserved;
    ++ble.framesAvailable;
    ++ble.framesInspected;
    ++ble.bleAdvertisementRecords;
    CHECK(!mergeAirspaceGuardReports(wifi, ble, &merged));
}

void testIncompleteWifiStillMergesCompleteBleEvidenceFailClosed() {
    FixtureSource wifiSource;
    wifiSource.add(8U, 1000000ULL, kTransmitterB, 6U, -62);
    const AirspaceGuardReport wifi =
        AirspaceGuard{}.inspectWifi(wifiSource, {}, 2U, 3U);
    CHECK(wifi.status == AirspaceGuardStatus::Inconclusive);
    CHECK(wifi.sourceFramesDropped == 2U);

    BleFixtureSource bleSource;
    bleSource.add(kTransmitterA, 2000000ULL,
                  AirspaceBleTrackerProtocol::None, -59, 1U);
    const AirspaceGuardReport ble = AirspaceGuard{}.inspectBle(
        bleSource, bleTrackerPolicy());
    CHECK(ble.status == AirspaceGuardStatus::Clear);

    AirspaceGuardReport merged{};
    CHECK(mergeAirspaceGuardReports(wifi, ble, &merged));
    CHECK(merged.status == AirspaceGuardStatus::Inconclusive);
    CHECK(merged.framesAvailable == 2U);
    CHECK(merged.framesInspected == 2U);
    CHECK(merged.bleAdvertisementRecords == 1U);
    CHECK(merged.sourceFramesDropped == 2U);
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
    CHECK(std::strcmp(airspaceFindingKindName(
                          AirspaceFindingKind::WifiSsidChurn),
                      "wifi_ssid_churn") == 0);
    CHECK(std::strcmp(airspaceFindingKindName(
                          AirspaceFindingKind::BleTrackerPresence),
                      "ble_tracker_presence") == 0);
    CHECK(std::strcmp(airspaceWifiSecurityName(AirspaceWifiSecurity::Rsn),
                      "rsn") == 0);
    CHECK(std::strcmp(airspaceConfidenceName(AirspaceConfidence::Medium),
                      "medium") == 0);
    CHECK(std::strcmp(airspaceBleTrackerProtocolName(
                          AirspaceBleTrackerProtocol::SmartTag),
                      "smart_tag") == 0);
}

}  // namespace

int main() {
    testPolicyAndEmptyEvidenceFailClosed();
    testIngressClassifiersStayManagementOnly();
    testIdentityConflictIsOptInUntilLiveRetentionIsComplete();
    testLiveIdentityRetentionKeyIsExactAndFailClosed();
    testCompactIdentityRetentionKeepsDetectorCapacity();
    testElevatedNoiseIsLowConfidenceExactAndOptIn();
    testElevatedNoiseRejectsWeakSplitStaleAndMalformedEvidence();
    testIdentityConflictRetainsTwoExactAdvertisements();
    testSsidChurnRetainsDistinctNamesFromOneBssid();
    testSsidChurnRejectsLookalikesAndIncompleteEvidence();
    testIdentityDetectorRejectsLookalikesAndMalformedEvidence();
    testIdentityParserExcludesCapturedFcsFromInformationElements();
    testExternalCaptureLossMakesClearEvidenceInconclusive();
    testBenignAndSparseDisconnectFramesStayClear();
    testDisconnectBurstRetainsExactEvidence();
    testSourcesAreNeverMergedAndConfidenceIsBounded();
    testMalformedFailedAndTruncatedEvidenceIsInconclusive();
    testBleTrackerPresenceIsOptInAndRetainsExactEvidence();
    testBleTrackerPresenceRejectsLookalikesAndStaleEvidence();
    testBleTrackerProtocolsRemainDistinct();
    testBleTrackerPresenceFailsClosedOnIncompleteEvidence();
    testLiveBleRetentionKeepsCoverageThenAllTrackerRepeats();
    testLiveBleRetentionFailsClosedOnMalformedOrCapacityLoss();
    testCompletedWifiAndBleReportsMergeWithoutInventingEvidence();
    testCompletedWifiAndBleReportsUseIndependentInspectionBudgets();
    testIncompleteWifiStillMergesCompleteBleEvidenceFailClosed();
    testStableNames();
    std::puts("Airspace Guard detector tests passed");
    return 0;
}
