#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/captures/WifiFrame.h"
#include "domain/observations/Observation.h"

namespace leshy1::services::guard {

enum class AirspaceGuardStatus : std::uint8_t {
    Clear,
    Finding,
    Inconclusive,
    InvalidPolicy,
};

enum class AirspaceFindingKind : std::uint8_t {
    WifiDisconnectBurst,
    WifiSsidSecurityConflict,
    WifiSsidChurn,
    WifiElevatedNoise,
    BleTrackerPresence,
};

enum class AirspaceConfidence : std::uint8_t {
    Low,
    Medium,
    High,
};

enum class AirspaceWifiSecurity : std::uint8_t {
    Unknown,
    Open,
    LegacyPrivacy,
    Wpa,
    Rsn,
};

enum class AirspaceBleTrackerProtocol : std::uint8_t {
    None,
    FindMy,
    SmartTag,
    Tile,
};

enum class BleTrackerIngressStatus : std::uint8_t {
    CoverageAdvertisement,
    TrackerAdvertisement,
    MalformedAdvertisement,
};

enum class BleLiveRetentionDisposition : std::uint8_t {
    Retained,
    Ignored,
    Malformed,
    Full,
};

enum class WifiIdentityIngressStatus : std::uint8_t {
    NotAdvertisement,
    IgnoredAdvertisement,
    RetainableAdvertisement,
    MalformedEnvelope,
    MalformedAddressing,
    MalformedElements,
};

enum class WifiIdentityLiveRetentionDisposition : std::uint8_t {
    Retained,
    Duplicate,
    Invalid,
    Full,
};

constexpr bool wifiIdentityIngressMalformed(
    WifiIdentityIngressStatus status) {
    return status == WifiIdentityIngressStatus::MalformedEnvelope ||
        status == WifiIdentityIngressStatus::MalformedAddressing ||
        status == WifiIdentityIngressStatus::MalformedElements;
}

struct WifiIdentityRetentionKey final {
    static constexpr std::size_t kNetworkNameCapacity = 32;

    std::array<std::uint8_t, 6> transmitter{};
    std::array<std::uint8_t, kNetworkNameCapacity> networkName{};
    std::uint8_t networkNameLength = 0;
    AirspaceWifiSecurity security = AirspaceWifiSecurity::Unknown;
};

inline constexpr std::size_t kWifiDisconnectLiveRetentionCapacity = 8;
// The detector inspects at most 64 observations. Reserve eight full-payload
// slots for disconnect evidence and retain the remaining identity evidence as
// compact projections rather than 256-byte capture frames.
inline constexpr std::size_t kWifiIdentityLiveRetentionCapacity = 56;
inline constexpr std::size_t kWifiIdentityProjectionCapacity = 80;
inline constexpr std::size_t kWifiNoiseFloorLiveRetentionCapacity = 8;
// The report can surface eight tracker identities with eight exact evidence
// references each. Match that complete representable set; a 65th retained
// tracker observation still fails closed rather than being silently omitted.
inline constexpr std::size_t kBleTrackerLiveRetentionCapacity = 64;
inline constexpr std::int16_t kWifiNoiseFloorIngressThresholdDbm = -85;

const char* airspaceGuardStatusName(AirspaceGuardStatus status);
const char* airspaceFindingKindName(AirspaceFindingKind kind);
const char* airspaceConfidenceName(AirspaceConfidence confidence);
const char* airspaceWifiSecurityName(AirspaceWifiSecurity security);
const char* airspaceBleTrackerProtocolName(
    AirspaceBleTrackerProtocol protocol);

struct AirspaceGuardPolicy final {
    std::uint8_t disconnectBurstThreshold = 4;
    std::uint64_t disconnectWindowUs = 2000000ULL;
    // Identity indicators are off by default: a caller may enable them only
    // after proving that its source retains a complete bounded set of identity
    // advertisements. The live adapter decides after cleanup; imported sources
    // opt in explicitly without weakening clear-result semantics.
    bool ssidSecurityConflictEnabled = false;
    std::uint64_t ssidSecurityConflictWindowUs = 10000000ULL;
    bool ssidChurnEnabled = false;
    std::uint8_t ssidChurnThreshold = 4;
    std::uint64_t ssidChurnWindowUs = 10000000ULL;
    // A raised noise floor is only a low-confidence interference indicator.
    // It cannot identify a jammer or trigger a response. The live adapter
    // retains only normalized RX metadata at or above the ingress threshold.
    bool elevatedNoiseEnabled = false;
    std::int16_t elevatedNoiseFloorDbm = -75;
    std::uint8_t elevatedNoiseThreshold = 4;
    std::uint64_t elevatedNoiseWindowUs = 2000000ULL;
    // BLE tracker-compatible presence is off until a caller proves complete
    // bounded retention of individual passive advertisements. Repeated
    // protocol markers establish presence only, never unwanted tracking.
    bool bleTrackerPresenceEnabled = false;
    std::uint8_t bleTrackerPresenceThreshold = 3;
    std::uint64_t bleTrackerPresenceWindowUs = 10000000ULL;
};

// Named profiles describe the surroundings in the user's language. They only
// tune evidence thresholds: callers must still prove complete bounded
// retention before enabling optional identity, noise or tracker detectors.
enum class AirspaceGuardProfile : std::uint8_t {
    Everyday,
    QuietPlace,
    BusyPlace,
};

inline constexpr std::uint8_t kAirspaceGuardProfileVersion = 1U;

const char* airspaceGuardProfileName(AirspaceGuardProfile profile);
AirspaceGuardPolicy airspaceGuardPolicyForProfile(
    AirspaceGuardProfile profile);

bool validateAirspaceGuardPolicy(const AirspaceGuardPolicy& policy);

// Cheap ingress classifiers for bounded passive adapters. Full structural
// validation remains the detector's responsibility; a caller must not enable an
// identity detector unless its retention policy keeps complete evidence for
// that class.
bool isWifiDisconnectFrameCandidate(const std::uint8_t* payload,
                                    std::size_t length);
bool isWifiIdentityAdvertisementCandidate(const std::uint8_t* payload,
                                          std::size_t length);
WifiIdentityIngressStatus wifiIdentityRetentionKey(
    const std::uint8_t* payload, std::size_t length, bool fcsIncluded,
    WifiIdentityRetentionKey* output);
std::size_t writeWifiIdentityRetentionProjection(
    const WifiIdentityRetentionKey& key, std::uint8_t* output,
    std::size_t capacity);
bool sameWifiIdentityRetentionKey(const WifiIdentityRetentionKey& left,
                                  const WifiIdentityRetentionKey& right);
bool wifiDisconnectRetentionSlotAvailable(std::size_t totalCapacity,
                                          std::size_t retainedFrames,
                                          std::size_t disconnectFrames);

class WifiIdentityProjectionRetention final
    : public domain::captures::WifiFrameSource {
public:
    WifiIdentityLiveRetentionDisposition accept(
        const WifiIdentityRetentionKey& key, std::uint64_t monotonicUs,
        std::int16_t rssiDbm, std::uint8_t channel);
    void reset();

    std::size_t size() const { return size_; }
    std::size_t frameCount() const override { return size_; }
    std::uint16_t snapLength() const override {
        return static_cast<std::uint16_t>(kWifiIdentityProjectionCapacity);
    }
    bool frameView(std::size_t index,
                   domain::captures::WifiFrameView* output) const override;

private:
    struct Observation final {
        WifiIdentityRetentionKey key{};
        std::uint64_t monotonicUs = 0;
        std::int16_t rssiDbm = -127;
        std::uint8_t channel = 0;
    };

    std::array<Observation, kWifiIdentityLiveRetentionCapacity>
        observations_{};
    std::size_t size_ = 0;
    mutable std::array<std::uint8_t, kWifiIdentityProjectionCapacity>
        projection_{};
};

class CompositeWifiFrameSource final
    : public domain::captures::WifiFrameSource {
public:
    CompositeWifiFrameSource(
        const domain::captures::WifiFrameSource& first,
        const domain::captures::WifiFrameSource& second)
        : first_(first), second_(second) {}

    std::size_t frameCount() const override;
    std::uint16_t snapLength() const override;
    bool frameView(std::size_t index,
                   domain::captures::WifiFrameView* output) const override;

private:
    const domain::captures::WifiFrameSource& first_;
    const domain::captures::WifiFrameSource& second_;
};
constexpr bool isWifiNoiseFloorCandidate(std::int16_t noiseFloorDbm) {
    // Zero and implausibly high/low values are unavailable driver metadata,
    // never RF evidence. Ingress stays broader than the detector policy.
    return noiseFloorDbm >= kWifiNoiseFloorIngressThresholdDbm &&
        noiseFloorDbm <= -30;
}
BleTrackerIngressStatus bleTrackerIngressStatus(
    const domain::observations::Observation& observation);

struct AirspaceEvidenceRef final {
    std::size_t frameIndex = 0;
    std::uint64_t monotonicUs = 0;
    std::uint8_t channel = 0;
    std::int16_t rssiDbm = 0;
    std::int16_t noiseFloorDbm = -127;
};

// Exact receive metadata for one high-noise packet callback. The observation
// index is source-local and remains stable in the published report; no payload
// from a malformed or failed receive is treated as evidence.
struct WifiNoiseFloorSample final {
    std::size_t observationIndex = 0;
    std::uint64_t monotonicUs = 0;
    std::uint8_t channel = 0;
    std::int16_t rssiDbm = -127;
    std::int16_t noiseFloorDbm = -127;
};

struct AirspaceFinding final {
    static constexpr std::size_t kEvidenceCapacity = 8;
    static constexpr std::size_t kNetworkNameCapacity = 32;
    static constexpr std::uint16_t kWifiDisconnectDetectorVersion = 1;
    static constexpr std::uint16_t kWifiIdentityDetectorVersion = 1;
    static constexpr std::uint16_t kWifiSsidChurnDetectorVersion = 1;
    static constexpr std::uint16_t kWifiElevatedNoiseDetectorVersion = 1;
    static constexpr std::uint16_t kBleTrackerPresenceDetectorVersion = 1;
    static constexpr std::uint16_t kDetectorVersion =
        kWifiDisconnectDetectorVersion;

    AirspaceFindingKind kind = AirspaceFindingKind::WifiDisconnectBurst;
    AirspaceConfidence confidence = AirspaceConfidence::Low;
    std::uint16_t detectorVersion = kDetectorVersion;
    std::uint16_t threshold = 0;
    std::uint16_t observed = 0;
    std::int16_t noiseFloorThresholdDbm = -127;
    std::uint16_t deauthenticationFrames = 0;
    std::uint16_t disassociationFrames = 0;
    std::array<std::uint8_t, 6> transmitter{};
    std::array<std::uint8_t, 6> relatedTransmitter{};
    std::array<std::uint8_t, kNetworkNameCapacity> networkName{};
    std::uint8_t networkNameLength = 0;
    AirspaceWifiSecurity primarySecurity = AirspaceWifiSecurity::Unknown;
    AirspaceWifiSecurity relatedSecurity = AirspaceWifiSecurity::Unknown;
    AirspaceBleTrackerProtocol bleTrackerProtocol =
        AirspaceBleTrackerProtocol::None;
    std::uint8_t bleAddressType = 0xffU;
    std::uint64_t firstUs = 0;
    std::uint64_t lastUs = 0;
    std::array<AirspaceEvidenceRef, kEvidenceCapacity> evidence{};
    std::size_t evidenceCount = 0;
};

struct AirspaceGuardReport final {
    // A dense real BLE environment on board-01 produced eleven independent
    // threshold-qualified tracker identities in one complete 64-record
    // detector window. Keep enough exact findings for that observed bound
    // without returning to full-Observation retention or dynamic allocation.
    static constexpr std::size_t kFindingCapacity = 16;

    AirspaceGuardStatus status = AirspaceGuardStatus::Inconclusive;
    std::array<AirspaceFinding, kFindingCapacity> findings{};
    std::size_t findingCount = 0;
    std::size_t sourceFramesObserved = 0;
    std::size_t framesAvailable = 0;
    std::size_t framesInspected = 0;
    std::size_t disconnectFrames = 0;
    std::size_t identityAdvertisementFrames = 0;
    std::size_t bleAdvertisementRecords = 0;
    std::size_t wifiNoiseSamplesObserved = 0;
    std::size_t wifiNoiseSamplesAvailable = 0;
    std::size_t wifiNoiseSamplesInspected = 0;
    std::size_t wifiNoiseSamplesDropped = 0;
    std::size_t wifiNoiseSamplesMalformed = 0;
    std::size_t malformedFrames = 0;
    std::size_t sourceReadFailures = 0;
    std::size_t sourceFramesDropped = 0;
    std::size_t findingsDropped = 0;
    bool inspectionTruncated = false;
};

// Read-only normalized BLE evidence. A live adapter and imported Session page
// can implement the same bounded interface without giving the detector any
// ownership of a radio, platform callback, scan lifecycle or response path.
class BleObservationSource {
public:
    virtual ~BleObservationSource() = default;
    virtual std::size_t observationCount() const = 0;
    virtual bool observationAt(
        std::size_t index,
        domain::observations::Observation* output) const = 0;
};

struct AirspaceGuardBleRetentionStats final {
    std::size_t recordsObserved = 0;
    std::size_t validAdvertisements = 0;
    std::size_t trackerAdvertisements = 0;
    std::size_t recordsRetained = 0;
    std::size_t advertisementsIgnored = 0;
    std::size_t malformedRecords = 0;
    std::size_t capacityDrops = 0;
    bool coverageOnly = false;

    bool complete() const {
        return malformedRecords == 0U && capacityDrops == 0U;
    }
};

// Complete bounded live evidence for the BLE tracker detector. One benign
// advertisement is retained as coverage until tracker-compatible evidence
// arrives; it is then replaced. At most the detector's eight evidence slots
// are retained per exact identity/protocol/address-type, so redundant repeats
// cannot starve other tracker candidates. Irrelevant and redundant valid
// advertisements are counted but do not consume detector capacity.
class AirspaceGuardBleRetention final : public BleObservationSource {
public:
    void reset();
    // A diagnostic may reduce the live window before the first record arrives
    // to exercise the real Full admission path. The physical production bound
    // remains the default and the limit cannot change once a scan has started.
    bool configureEffectiveCapacity(std::size_t capacity);
    BleLiveRetentionDisposition accept(
        const domain::observations::Observation& observation);

    std::size_t observationCount() const override { return size_; }
    bool observationAt(
        std::size_t index,
        domain::observations::Observation* output) const override;
    const AirspaceGuardBleRetentionStats& stats() const { return stats_; }

private:
    // Keep only detector inputs. A full Observation is 144 bytes and retaining
    // 64 of them starves the zero-PSRAM board when the BLE stack starts.
    struct RetainedRecord final {
        std::uint64_t monotonicUs = 0;
        std::array<std::uint8_t, 6> identity{};
        std::int16_t rssiDbm = 0;
        AirspaceBleTrackerProtocol protocol =
            AirspaceBleTrackerProtocol::None;
        std::uint8_t addressType = 0xffU;
    };

    std::array<RetainedRecord, kBleTrackerLiveRetentionCapacity> records_{};
    AirspaceGuardBleRetentionStats stats_{};
    std::size_t size_ = 0;
    std::size_t effectiveCapacity_ = kBleTrackerLiveRetentionCapacity;
};

// Combines independently completed Wi-Fi and BLE reports without erasing the
// source-local evidence index carried by each finding kind. Each input has
// already passed its own 64-record detector boundary; their aggregate may
// therefore contain up to 128 independently inspected source records.
bool mergeAirspaceGuardReports(const AirspaceGuardReport& wifi,
                               const AirspaceGuardReport& ble,
                               AirspaceGuardReport* output);

// A bounded, allocation-free, receive-evidence-only detector. It never owns a
// radio driver or an action path: callers decide when to capture and how to
// present an indicator, while every finding retains exact source-record indices.
class AirspaceGuard final {
public:
    static constexpr std::size_t kFrameInspectionCapacity = 64;
    static constexpr std::size_t kMergedFrameInspectionCapacity =
        kFrameInspectionCapacity * 2U;

    AirspaceGuardReport inspectWifi(
        const domain::captures::WifiFrameSource& source,
        const AirspaceGuardPolicy& policy = {},
        std::size_t sourceFramesDropped = 0U,
        std::size_t sourceFramesObserved = 0U,
        const WifiNoiseFloorSample* noiseSamples = nullptr,
        std::size_t noiseSampleCount = 0U,
        std::size_t noiseSamplesDropped = 0U,
        std::size_t noiseSamplesObserved = 0U) const;

    // Product firmware supplies static report storage so the C++ aggregate
    // return ABI cannot materialize a multi-kilobyte temporary on Arduino's
    // bounded loop stack. The value-returning API remains for host callers.
    bool writeWifiReport(
        const domain::captures::WifiFrameSource& source,
        const AirspaceGuardPolicy& policy,
        std::size_t sourceFramesDropped,
        std::size_t sourceFramesObserved,
        const WifiNoiseFloorSample* noiseSamples,
        std::size_t noiseSampleCount,
        std::size_t noiseSamplesDropped,
        std::size_t noiseSamplesObserved,
        AirspaceGuardReport* output) const;

    AirspaceGuardReport inspectBle(
        const BleObservationSource& source,
        const AirspaceGuardPolicy& policy = {},
        std::size_t sourceRecordsDropped = 0U,
        std::size_t sourceRecordsObserved = 0U) const;

    // Same bounded-stack rule as writeWifiReport(): the worker owns static
    // event storage and the detector fills it without an aggregate ABI copy.
    bool writeBleReport(
        const BleObservationSource& source,
        const AirspaceGuardPolicy& policy,
        std::size_t sourceRecordsDropped,
        std::size_t sourceRecordsObserved,
        AirspaceGuardReport* output) const;
};

}  // namespace leshy1::services::guard
