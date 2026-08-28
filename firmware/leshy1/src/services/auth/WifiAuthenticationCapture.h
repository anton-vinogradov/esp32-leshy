#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/captures/WifiFrame.h"

namespace leshy1::services::auth {

enum class WifiAuthenticationCaptureOutcome : std::uint8_t {
    Inconclusive,
    Incomplete,
    Complete,
};

enum class WifiEapolKeyMessage : std::uint8_t {
    Unknown,
    Message1,
    Message2,
    Message3,
    Message4,
};

enum class WifiAuthenticationKeyProfile : std::uint8_t {
    Unsupported,
    RsnWpa2,
};

enum WifiAuthenticationUncertainty : std::uint16_t {
    WifiAuthenticationUncertaintyNone = 0,
    WifiAuthenticationUncertaintyInvalidInput = 1U << 0U,
    WifiAuthenticationUncertaintyCaptureIncomplete = 1U << 1U,
    WifiAuthenticationUncertaintyCaptureLoss = 1U << 2U,
    WifiAuthenticationUncertaintySourceRead = 1U << 3U,
    WifiAuthenticationUncertaintyMalformed = 1U << 4U,
    WifiAuthenticationUncertaintyTruncated = 1U << 5U,
    WifiAuthenticationUncertaintyCapacity = 1U << 6U,
    WifiAuthenticationUncertaintyNoEvidence = 1U << 7U,
    WifiAuthenticationUncertaintyUnsupported = 1U << 8U,
};

const char* wifiAuthenticationCaptureOutcomeName(
    WifiAuthenticationCaptureOutcome outcome);
const char* wifiEapolKeyMessageName(WifiEapolKeyMessage message);

struct WifiAuthenticationCaptureInput final {
    const domain::captures::WifiFrameSource* source = nullptr;
    bool captureComplete = false;
    std::uint32_t framesReported = 0;
    std::uint32_t framesAccepted = 0;
    std::uint32_t framesDroppedCapacity = 0;
    std::uint32_t framesDroppedInvalid = 0;
};

struct WifiAuthenticationCaptureCounters final {
    std::uint32_t sourceFrames = 0;
    std::uint32_t framesRead = 0;
    std::uint32_t dataFrames = 0;
    std::uint32_t framesIgnored = 0;
    std::uint32_t eapolFrames = 0;
    std::uint32_t eapolKeyFrames = 0;
    std::uint32_t classifiedKeyFrames = 0;
    std::uint32_t unclassifiedKeyFrames = 0;
    std::uint32_t unsupportedKeyFrames = 0;
    std::uint32_t sequenceRejected = 0;
    std::uint32_t malformedFrames = 0;
    std::uint32_t truncatedFrames = 0;
    std::uint32_t sourceReadFailures = 0;
    std::uint32_t evidenceDropped = 0;
    std::uint32_t peersDropped = 0;
    std::uint32_t pmkidsDropped = 0;
    std::uint32_t captureFramesReported = 0;
    std::uint32_t captureFramesAccepted = 0;
    std::uint32_t captureFramesDroppedCapacity = 0;
    std::uint32_t captureFramesDroppedInvalid = 0;
};

struct WifiAuthenticationEvidence final {
    std::uint64_t monotonicUs = 0;
    std::uint64_t replayCounter = 0;
    std::uint16_t sourceFrameIndex = 0;
    std::int16_t rssiDbm = 0;
    std::uint16_t keyInfo = 0;
    std::uint8_t channel = 0;
    WifiEapolKeyMessage message = WifiEapolKeyMessage::Unknown;
    std::uint8_t eapolVersion = 0;
    std::uint8_t descriptorType = 0;
    std::uint8_t descriptorVersion = 0;
    WifiAuthenticationKeyProfile profile =
        WifiAuthenticationKeyProfile::Unsupported;
    std::array<std::uint8_t, 6> accessPoint{};
    std::array<std::uint8_t, 6> station{};
};

struct WifiAuthenticationPeer final {
    static constexpr std::uint8_t kMissingEvidence = 0xffU;

    std::array<std::uint8_t, 6> accessPoint{};
    std::array<std::uint8_t, 6> station{};
    std::array<std::uint64_t, 4> replayCounters{};
    std::array<std::uint8_t, 4> descriptorVersions{};
    std::array<std::uint8_t, 4> evidenceIndices{
        kMissingEvidence, kMissingEvidence, kMissingEvidence,
        kMissingEvidence};
    std::array<std::uint8_t, 32> authenticatorNonce{};
    std::array<std::uint8_t, 32> stationNonce{};
    std::uint8_t messageMask = 0;
    std::uint8_t descriptorType = 0;
    bool authenticatorNonceSet = false;
    bool authenticatorNonceMismatch = false;
    bool sequenceConsistent = false;
    bool replayCountersConsistent = false;
    bool keyMaterialConsistent = false;
    bool complete = false;
};

struct WifiPmkidEvidence final {
    std::uint64_t monotonicUs = 0;
    std::uint16_t sourceFrameIndex = 0;
    std::array<std::uint8_t, 6> accessPoint{};
    std::array<std::uint8_t, 6> station{};
    std::array<std::uint8_t, 16> pmkid{};
};

struct WifiAuthenticationCaptureReport final {
    static constexpr std::size_t kSourceFrameInspectionCapacity = 64;
    static constexpr std::size_t kEvidenceCapacity = 16;
    static constexpr std::size_t kPeerCapacity = 4;
    static constexpr std::size_t kPmkidCapacity = 4;

    WifiAuthenticationCaptureOutcome outcome =
        WifiAuthenticationCaptureOutcome::Inconclusive;
    std::uint16_t uncertainty = WifiAuthenticationUncertaintyNone;
    WifiAuthenticationCaptureCounters counters{};
    std::array<WifiAuthenticationEvidence, kEvidenceCapacity> evidence{};
    std::array<WifiAuthenticationPeer, kPeerCapacity> peers{};
    std::array<WifiPmkidEvidence, kPmkidCapacity> pmkids{};
    std::size_t evidenceCount = 0;
    std::size_t peerCount = 0;
    std::size_t pmkidCount = 0;
};

static_assert(
    WifiAuthenticationCaptureReport::kSourceFrameInspectionCapacity <=
        UINT16_MAX,
    "authentication evidence source index is too narrow");
static_assert(sizeof(WifiAuthenticationCaptureReport) <= 1536U,
              "authentication report exceeds its bounded stack envelope");

// Reads a bounded immutable source and never owns a radio, driver, lease, storage,
// or response path. A successful call may still produce Inconclusive when the
// supplied evidence or its accounting is incomplete.
bool analyzeWifiAuthenticationCapture(
    const WifiAuthenticationCaptureInput& input,
    WifiAuthenticationCaptureReport* output);

}  // namespace leshy1::services::auth
