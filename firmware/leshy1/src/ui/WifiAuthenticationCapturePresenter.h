#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "apps/auth/WifiAuthenticationCaptureController.h"
#include "services/auth/WifiAuthenticationCapture.h"
#include "ui/UiStrings.h"

namespace leshy1::ui {

enum class WifiAuthenticationCaptureUiPhase : std::uint8_t {
    Preparing,
    Cancelling,
    Running,
    Report,
    Failed,
};

enum class WifiAuthenticationCaptureUiView : std::uint8_t {
    Preparing,
    Cancelling,
    Running,
    Result,
    Inconclusive,
    Actions,
    PeerDetail,
    EvidenceList,
    EvidenceDetail,
    Failed,
};

enum class WifiAuthenticationCaptureUiTone : std::uint8_t {
    Neutral,
    Positive,
    Caution,
    Error,
};

// Rows keep semantic identity and a localized catalog key without allocating
// rendered text or taking renderer ownership here.
enum class WifiAuthenticationCaptureUiMetric : std::uint8_t {
    None,
    TimeRemainingSeconds,
    ChannelAndCandidateFrames,
    RetainedAndDroppedFrames,
    TerminalAnalysisPending,
    CompleteAndPartialPeers,
    PmkidsAndEapolFrames,
    SelectedPeerMask,
    EvidenceAndSourceFrames,
    LossAndRejectedFrames,
    UncertaintyMask,
    ActionDetails,
    ActionRepeat,
    PeerPosition,
    PeerMessageMask,
    PeerState,
    PeerEvidenceCount,
    EvidenceListRow,
    EvidenceMessageAndFrame,
    EvidenceChannelAndSignal,
    EvidenceReplayCounter,
    EvidenceDescriptor,
    FailureCode,
};

enum class WifiAuthenticationCaptureExportEligibility : std::uint8_t {
    NotEvaluated,
    Eligible,
    Ineligible,
};

enum class WifiAuthenticationCaptureUiFailure : std::uint8_t {
    None,
    InvalidPresentationInput,
    StartFailed,
    RuntimeFailed,
    ResultBeforeCleanup,
    ReportRejected,
};

struct WifiAuthenticationCaptureLiveProgress final {
    std::uint32_t elapsedMs = 0;
    std::uint32_t durationMs = 0;
    std::uint32_t framesReported = 0;
    std::uint32_t candidateFrames = 0;
    std::uint32_t framesAccepted = 0;
    std::uint32_t framesDroppedCapacity = 0;
    std::uint32_t framesDroppedInvalid = 0;
    std::uint8_t channel = 0;
};

struct WifiAuthenticationCaptureUiInput final {
    WifiAuthenticationCaptureUiPhase phase =
        WifiAuthenticationCaptureUiPhase::Failed;
    WifiAuthenticationCaptureLiveProgress progress{};
    const services::auth::WifiAuthenticationCaptureReport* report = nullptr;
    const apps::auth::WifiAuthenticationCaptureController* controller =
        nullptr;
    WifiAuthenticationCaptureUiFailure failure =
        WifiAuthenticationCaptureUiFailure::None;
    bool cleanupComplete = false;
};

struct WifiAuthenticationCaptureUiRow final {
    WifiAuthenticationCaptureUiMetric metric =
        WifiAuthenticationCaptureUiMetric::None;
    UiTextId text = UiTextId::WifiAuthFailureInvalid;
    std::uint32_t primary = 0;
    std::uint32_t secondary = 0;
    std::uint64_t exact = 0;
    bool warning = false;
    bool selected = false;
};

// Four fixed rows match the established product touch geometry. The model is
// allocation-free and renderer-independent; title/headline/note reuse the shared
// localization catalog, including the user-facing metric row labels.
struct WifiAuthenticationCaptureUiModel final {
    static constexpr std::size_t kVisibleRowCapacity = 4;

    UiTextId title = UiTextId::CaptureError;
    UiTextId headline = UiTextId::CaptureRecordFailedUser;
    UiTextId note = UiTextId::AirspaceGuardEvidenceIncomplete;
    WifiAuthenticationCaptureUiView view =
        WifiAuthenticationCaptureUiView::Failed;
    WifiAuthenticationCaptureUiTone tone =
        WifiAuthenticationCaptureUiTone::Error;
    std::array<WifiAuthenticationCaptureUiRow, kVisibleRowCapacity> rows{};
    std::size_t rowCount = 0;
    WifiAuthenticationCaptureUiFailure failure =
        WifiAuthenticationCaptureUiFailure::None;
    WifiAuthenticationCaptureExportEligibility exportEligibility =
        WifiAuthenticationCaptureExportEligibility::NotEvaluated;
    bool evidenceIncomplete = true;
    bool reportOpenable = false;
    bool cleanupComplete = false;
};

// A renderer consumes this delta by repainting only changed fixed regions. There
// is deliberately no whole-screen-clear request in this contract.
struct WifiAuthenticationCaptureUiDelta final {
    std::uint8_t fixedRegionMask = 0;
    std::uint8_t rowMask = 0;
    bool fullScreenClear = false;

    bool any() const {
        return fixedRegionMask != 0U || rowMask != 0U;
    }
};

constexpr std::uint8_t kWifiAuthenticationTitleRegion = 1U << 0U;
constexpr std::uint8_t kWifiAuthenticationHeadlineRegion = 1U << 1U;
constexpr std::uint8_t kWifiAuthenticationNoteRegion = 1U << 2U;

WifiAuthenticationCaptureUiModel presentWifiAuthenticationCapture(
    const WifiAuthenticationCaptureUiInput& input);

WifiAuthenticationCaptureUiDelta diffWifiAuthenticationCaptureUi(
    const WifiAuthenticationCaptureUiModel& previous,
    const WifiAuthenticationCaptureUiModel& current);

}  // namespace leshy1::ui
