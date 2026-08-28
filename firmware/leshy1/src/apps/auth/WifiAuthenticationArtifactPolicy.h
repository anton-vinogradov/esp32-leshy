#pragma once

#include <cstddef>
#include <cstdint>

#include "services/auth/WifiAuthenticationCapture.h"
#include "storage/SessionCodec.h"

namespace leshy1::apps::auth {

using services::auth::WifiAuthenticationCaptureOutcome;
using services::auth::WifiAuthenticationCaptureReport;

enum class WifiAuthenticationPcapAvailabilityReason : std::uint8_t {
    Available,
    AccountingMismatch,
    NoPersistedFrames,
};

enum class WifiAuthenticationStandardArtifactReason : std::uint8_t {
    ReadyPmkid,
    ReadyMessagePair,
    PcapUnavailable,
    InvalidReport,
    CaptureUncertain,
    PurposeNotAuthentication,
    SsidUnavailable,
    SsidInvalid,
    TargetMismatch,
    NoValidatedEvidence,
};

struct WifiAuthenticationPcapAvailability final {
    bool available = false;
    WifiAuthenticationPcapAvailabilityReason reason =
        WifiAuthenticationPcapAvailabilityReason::AccountingMismatch;
};

struct WifiAuthenticationStandardArtifactReadiness final {
    bool ready = false;
    WifiAuthenticationStandardArtifactReason reason =
        WifiAuthenticationStandardArtifactReason::PcapUnavailable;
};

// Capture outcome describes what the analyzer observed. Artifact readiness is
// evaluated independently from the immutable persisted-frame accounting and
// the exact evidence retained in the report.
struct WifiAuthenticationArtifactPolicyResult final {
    WifiAuthenticationCaptureOutcome outcome =
        WifiAuthenticationCaptureOutcome::Inconclusive;
    WifiAuthenticationPcapAvailability pcap{};
    WifiAuthenticationStandardArtifactReadiness standard{};
};

// Pure bounded policy: no allocation, serialization, I/O, radio, credentials,
// or ownership changes.
WifiAuthenticationArtifactPolicyResult evaluateWifiAuthenticationArtifacts(
    const WifiAuthenticationCaptureReport& report,
    const storage::AuthenticationCaptureProvenance& provenance,
    std::size_t persistedFrameCount);

}  // namespace leshy1::apps::auth
