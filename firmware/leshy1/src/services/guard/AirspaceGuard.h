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
    MalformedAdvertisement,
};

struct WifiIdentityRetentionKey final {
    static constexpr std::size_t kNetworkNameCapacity = 32;

    std::array<std::uint8_t, 6> transmitter{};
    std::array<std::uint8_t, kNetworkNameCapacity> networkName{};
    std::uint8_t networkNameLength = 0;
    AirspaceWifiSecurity security = AirspaceWifiSecurity::Unknown;
};

inline constexpr std::size_t kWifiDisconnectLiveRetentionCapacity = 8;
inline constexpr std::size_t kWifiIdentityLiveRetentionCapacity = 8;
inline constexpr std::size_t kBleTrackerLiveRetentionCapacity = 32;

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
    // BLE tracker-compatible presence is off until a caller proves complete
    // bounded retention of individual passive advertisements. Repeated
    // protocol markers establish presence only, never unwanted tracking.
    bool bleTrackerPresenceEnabled = false;
    std::uint8_t bleTrackerPresenceThreshold = 3;
    std::uint64_t bleTrackerPresenceWindowUs = 10000000ULL;
};

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
bool sameWifiIdentityRetentionKey(const WifiIdentityRetentionKey& left,
                                  const WifiIdentityRetentionKey& right);
bool wifiDisconnectRetentionSlotAvailable(std::size_t totalCapacity,
                                          std::size_t retainedFrames,
                                          std::size_t disconnectFrames);
bool wifiIdentityRetentionSlotAvailable(std::size_t totalCapacity,
                                        std::size_t retainedFrames,
                                        std::size_t disconnectFrames,
                                        std::size_t identityProfiles);
BleTrackerIngressStatus bleTrackerIngressStatus(
    const domain::observations::Observation& observation);

struct AirspaceEvidenceRef final {
    std::size_t frameIndex = 0;
    std::uint64_t monotonicUs = 0;
    std::uint8_t channel = 0;
    std::int16_t rssiDbm = 0;
};

struct AirspaceFinding final {
    static constexpr std::size_t kEvidenceCapacity = 8;
    static constexpr std::size_t kNetworkNameCapacity = 32;
    static constexpr std::uint16_t kWifiDisconnectDetectorVersion = 1;
    static constexpr std::uint16_t kWifiIdentityDetectorVersion = 1;
    static constexpr std::uint16_t kWifiSsidChurnDetectorVersion = 1;
    static constexpr std::uint16_t kBleTrackerPresenceDetectorVersion = 1;
    static constexpr std::uint16_t kDetectorVersion =
        kWifiDisconnectDetectorVersion;

    AirspaceFindingKind kind = AirspaceFindingKind::WifiDisconnectBurst;
    AirspaceConfidence confidence = AirspaceConfidence::Low;
    std::uint16_t detectorVersion = kDetectorVersion;
    std::uint16_t threshold = 0;
    std::uint16_t observed = 0;
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
    static constexpr std::size_t kFindingCapacity = 8;

    AirspaceGuardStatus status = AirspaceGuardStatus::Inconclusive;
    std::array<AirspaceFinding, kFindingCapacity> findings{};
    std::size_t findingCount = 0;
    std::size_t sourceFramesObserved = 0;
    std::size_t framesAvailable = 0;
    std::size_t framesInspected = 0;
    std::size_t disconnectFrames = 0;
    std::size_t identityAdvertisementFrames = 0;
    std::size_t bleAdvertisementRecords = 0;
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
// arrives; it is then replaced so all 32 slots remain available for repeated
// exact identity/protocol observations. Irrelevant valid advertisements are
// counted but do not consume detector capacity.
class AirspaceGuardBleRetention final : public BleObservationSource {
public:
    void reset();
    BleLiveRetentionDisposition accept(
        const domain::observations::Observation& observation);

    std::size_t observationCount() const override { return size_; }
    bool observationAt(
        std::size_t index,
        domain::observations::Observation* output) const override;
    const AirspaceGuardBleRetentionStats& stats() const { return stats_; }

private:
    std::array<domain::observations::Observation,
               kBleTrackerLiveRetentionCapacity> records_{};
    AirspaceGuardBleRetentionStats stats_{};
    std::size_t size_ = 0;
};

// Combines independently completed Wi-Fi and BLE reports without erasing the
// source-local evidence index carried by each finding kind. The current live
// capacities sum to at most the detector's 64-record validation boundary.
bool mergeAirspaceGuardReports(const AirspaceGuardReport& wifi,
                               const AirspaceGuardReport& ble,
                               AirspaceGuardReport* output);

// A bounded, allocation-free, receive-evidence-only detector. It never owns a
// radio driver or an action path: callers decide when to capture and how to
// present an indicator, while every finding retains exact source-record indices.
class AirspaceGuard final {
public:
    static constexpr std::size_t kFrameInspectionCapacity = 64;

    AirspaceGuardReport inspectWifi(
        const domain::captures::WifiFrameSource& source,
        const AirspaceGuardPolicy& policy = {},
        std::size_t sourceFramesDropped = 0U,
        std::size_t sourceFramesObserved = 0U) const;

    AirspaceGuardReport inspectBle(
        const BleObservationSource& source,
        const AirspaceGuardPolicy& policy = {},
        std::size_t sourceRecordsDropped = 0U,
        std::size_t sourceRecordsObserved = 0U) const;
};

}  // namespace leshy1::services::guard
