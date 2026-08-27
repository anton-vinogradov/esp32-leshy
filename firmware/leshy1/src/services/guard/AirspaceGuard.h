#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/captures/WifiFrame.h"

namespace leshy1::services::guard {

enum class AirspaceGuardStatus : std::uint8_t {
    Clear,
    Finding,
    Inconclusive,
    InvalidPolicy,
};

enum class AirspaceFindingKind : std::uint8_t {
    WifiDisconnectBurst,
};

enum class AirspaceConfidence : std::uint8_t {
    Low,
    Medium,
    High,
};

const char* airspaceGuardStatusName(AirspaceGuardStatus status);
const char* airspaceFindingKindName(AirspaceFindingKind kind);
const char* airspaceConfidenceName(AirspaceConfidence confidence);

struct AirspaceGuardPolicy final {
    std::uint8_t disconnectBurstThreshold = 4;
    std::uint64_t disconnectWindowUs = 2000000ULL;
};

bool validateAirspaceGuardPolicy(const AirspaceGuardPolicy& policy);

struct AirspaceEvidenceRef final {
    std::size_t frameIndex = 0;
    std::uint64_t monotonicUs = 0;
    std::uint8_t channel = 0;
    std::int16_t rssiDbm = 0;
};

struct AirspaceFinding final {
    static constexpr std::size_t kEvidenceCapacity = 8;
    static constexpr std::uint16_t kDetectorVersion = 1;

    AirspaceFindingKind kind = AirspaceFindingKind::WifiDisconnectBurst;
    AirspaceConfidence confidence = AirspaceConfidence::Low;
    std::uint16_t detectorVersion = kDetectorVersion;
    std::uint16_t threshold = 0;
    std::uint16_t observed = 0;
    std::uint16_t deauthenticationFrames = 0;
    std::uint16_t disassociationFrames = 0;
    std::array<std::uint8_t, 6> transmitter{};
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
    std::size_t framesAvailable = 0;
    std::size_t framesInspected = 0;
    std::size_t disconnectFrames = 0;
    std::size_t malformedFrames = 0;
    std::size_t sourceReadFailures = 0;
    std::size_t findingsDropped = 0;
    bool inspectionTruncated = false;
};

// A bounded, allocation-free, receive-evidence-only detector. It never owns a
// radio driver or an action path: callers decide when to capture and how to
// present an indicator, while every finding retains exact source-frame indices.
class AirspaceGuard final {
public:
    static constexpr std::size_t kFrameInspectionCapacity = 64;

    AirspaceGuardReport inspectWifi(
        const domain::captures::WifiFrameSource& source,
        const AirspaceGuardPolicy& policy = {}) const;
};

}  // namespace leshy1::services::guard
