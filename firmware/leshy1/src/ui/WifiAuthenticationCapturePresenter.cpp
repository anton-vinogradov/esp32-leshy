#include "WifiAuthenticationCapturePresenter.h"

#include <algorithm>
#include <limits>
#include <type_traits>

namespace leshy1::ui {
namespace {

using apps::auth::WifiAuthenticationCaptureAction;
using apps::auth::WifiAuthenticationCaptureController;
using apps::auth::WifiAuthenticationCaptureView;
using services::auth::WifiAuthenticationCaptureOutcome;
using services::auth::WifiAuthenticationCaptureReport;
using services::auth::WifiAuthenticationEvidence;
using services::auth::WifiAuthenticationPeer;
using services::auth::WifiAuthenticationUncertainty;

static_assert(
    std::is_trivially_copyable_v<WifiAuthenticationCaptureUiModel>,
    "authentication presentation must remain allocation-free");
static_assert(WifiAuthenticationCaptureUiModel::kVisibleRowCapacity <= 8U,
              "row repaint mask is too narrow");

constexpr std::uint16_t kKnownUncertaintyMask =
    static_cast<std::uint16_t>(
        services::auth::WifiAuthenticationUncertaintyInvalidInput) |
    static_cast<std::uint16_t>(
        services::auth::WifiAuthenticationUncertaintyCaptureIncomplete) |
    static_cast<std::uint16_t>(
        services::auth::WifiAuthenticationUncertaintyCaptureLoss) |
    static_cast<std::uint16_t>(
        services::auth::WifiAuthenticationUncertaintySourceRead) |
    static_cast<std::uint16_t>(
        services::auth::WifiAuthenticationUncertaintyMalformed) |
    static_cast<std::uint16_t>(
        services::auth::WifiAuthenticationUncertaintyTruncated) |
    static_cast<std::uint16_t>(
        services::auth::WifiAuthenticationUncertaintyCapacity) |
    static_cast<std::uint16_t>(
        services::auth::WifiAuthenticationUncertaintyNoEvidence) |
    static_cast<std::uint16_t>(
        services::auth::WifiAuthenticationUncertaintyUnsupported);

std::uint32_t saturatingAdd(std::uint32_t left, std::uint32_t right) {
    constexpr std::uint32_t kMaximum =
        std::numeric_limits<std::uint32_t>::max();
    return right > kMaximum - left ? kMaximum : left + right;
}

bool hasUncertainty(std::uint16_t mask,
                    WifiAuthenticationUncertainty uncertainty) {
    return (mask & static_cast<std::uint16_t>(uncertainty)) != 0U;
}

bool liveProgressValid(const WifiAuthenticationCaptureLiveProgress& progress) {
    if (progress.durationMs == 0U ||
        progress.elapsedMs > progress.durationMs ||
        progress.channel < 1U || progress.channel > 14U) {
        return false;
    }
    const std::uint64_t accounted =
        static_cast<std::uint64_t>(progress.framesAccepted) +
        progress.framesDroppedCapacity + progress.framesDroppedInvalid;
    const std::uint64_t candidates =
        static_cast<std::uint64_t>(progress.framesAccepted) +
        progress.framesDroppedCapacity;
    return accounted == progress.framesReported &&
        candidates == progress.candidateFrames;
}

bool liveProgressEmpty(const WifiAuthenticationCaptureLiveProgress& progress) {
    return progress.elapsedMs == 0U && progress.durationMs == 0U &&
        progress.framesReported == 0U && progress.framesAccepted == 0U &&
        progress.candidateFrames == 0U &&
        progress.framesDroppedCapacity == 0U &&
        progress.framesDroppedInvalid == 0U && progress.channel == 0U;
}

bool reportShapeValid(const WifiAuthenticationCaptureReport& report) {
    if (report.evidenceCount > report.evidence.size() ||
        report.peerCount > report.peers.size() ||
        report.pmkidCount > report.pmkids.size()) {
        return false;
    }
    const auto& counters = report.counters;
    const std::uint32_t inspectCapacity = static_cast<std::uint32_t>(
        WifiAuthenticationCaptureReport::kSourceFrameInspectionCapacity);
    const std::uint32_t maximumRead =
        counters.sourceFrames < inspectCapacity
            ? counters.sourceFrames : inspectCapacity;
    if (counters.framesRead > maximumRead ||
        counters.dataFrames > counters.framesRead ||
        counters.eapolFrames > counters.framesRead ||
        counters.eapolKeyFrames > counters.eapolFrames ||
        counters.classifiedKeyFrames > counters.eapolKeyFrames) {
        return false;
    }
    const std::uint64_t classified =
        static_cast<std::uint64_t>(counters.classifiedKeyFrames) +
        counters.unclassifiedKeyFrames + counters.unsupportedKeyFrames;
    if (classified != counters.eapolKeyFrames ||
        report.evidenceCount > counters.eapolKeyFrames) {
        return false;
    }
    const std::uint64_t captureAccounted =
        static_cast<std::uint64_t>(counters.captureFramesAccepted) +
        counters.captureFramesDroppedCapacity +
        counters.captureFramesDroppedInvalid;
    const bool captureMismatch =
        counters.captureFramesAccepted != counters.sourceFrames ||
        captureAccounted != counters.captureFramesReported;
    if (captureMismatch &&
        !hasUncertainty(report.uncertainty,
                        services::auth::
                            WifiAuthenticationUncertaintyInvalidInput)) {
        return false;
    }
    const bool captureLoss = counters.captureFramesDroppedCapacity != 0U ||
        counters.captureFramesDroppedInvalid != 0U;
    if (captureLoss &&
        !hasUncertainty(report.uncertainty,
                        services::auth::
                            WifiAuthenticationUncertaintyCaptureLoss)) {
        return false;
    }
    if (counters.sourceFrames > inspectCapacity &&
        !hasUncertainty(report.uncertainty,
                        services::auth::
                            WifiAuthenticationUncertaintyCapacity)) {
        return false;
    }
    if ((report.uncertainty &
         static_cast<std::uint16_t>(~kKnownUncertaintyMask)) != 0U) {
        return false;
    }

    std::size_t completePeerCount = 0U;
    for (std::size_t peerIndex = 0U; peerIndex < report.peerCount;
         ++peerIndex) {
        const WifiAuthenticationPeer& peer = report.peers[peerIndex];
        if ((peer.messageMask & 0xf0U) != 0U) return false;
        for (const std::uint8_t evidenceIndex : peer.evidenceIndices) {
            if (evidenceIndex != WifiAuthenticationPeer::kMissingEvidence &&
                evidenceIndex >= report.evidenceCount) {
                return false;
            }
        }
        if (peer.complete) {
            if (peer.messageMask != 0x0fU ||
                !peer.authenticatorNonceSet ||
                peer.authenticatorNonceMismatch ||
                !peer.sequenceConsistent ||
                !peer.replayCountersConsistent ||
                !peer.keyMaterialConsistent) {
                return false;
            }
            ++completePeerCount;
        }
    }
    for (std::size_t index = 0U; index < report.evidenceCount; ++index) {
        const WifiAuthenticationEvidence& evidence = report.evidence[index];
        if (evidence.sourceFrameIndex >= counters.sourceFrames ||
            evidence.monotonicUs == 0U || evidence.channel < 1U ||
            evidence.channel > 14U) {
            return false;
        }
    }
    for (std::size_t index = 0U; index < report.pmkidCount; ++index) {
        if (report.pmkids[index].sourceFrameIndex >= counters.sourceFrames ||
            report.pmkids[index].monotonicUs == 0U) {
            return false;
        }
    }

    if (report.outcome == WifiAuthenticationCaptureOutcome::Complete) {
        return report.uncertainty == 0U && completePeerCount != 0U;
    }
    if (report.outcome == WifiAuthenticationCaptureOutcome::Incomplete) {
        return report.uncertainty == 0U && completePeerCount == 0U;
    }
    return report.outcome == WifiAuthenticationCaptureOutcome::Inconclusive &&
        report.uncertainty != 0U;
}

std::uint32_t completePeers(const WifiAuthenticationCaptureReport& report) {
    std::uint32_t count = 0U;
    for (std::size_t index = 0U; index < report.peerCount; ++index) {
        if (report.peers[index].complete) ++count;
    }
    return count;
}

std::uint32_t partialPeers(const WifiAuthenticationCaptureReport& report) {
    std::uint32_t count = 0U;
    for (std::size_t index = 0U; index < report.peerCount; ++index) {
        if (!report.peers[index].complete &&
            report.peers[index].messageMask != 0U) {
            ++count;
        }
    }
    return count;
}

bool hasPartialPeer(const WifiAuthenticationCaptureReport& report) {
    return partialPeers(report) != 0U;
}

UiTextId uncertaintyText(std::uint16_t mask) {
    if (hasUncertainty(
            mask, services::auth::WifiAuthenticationUncertaintyInvalidInput)) {
        return UiTextId::WifiAuthReasonInvalid;
    }
    if (hasUncertainty(
            mask,
            services::auth::WifiAuthenticationUncertaintyCaptureIncomplete)) {
        return UiTextId::WifiAuthReasonInterrupted;
    }
    if (hasUncertainty(
            mask, services::auth::WifiAuthenticationUncertaintyCaptureLoss)) {
        return UiTextId::WifiAuthReasonLoss;
    }
    if (hasUncertainty(
            mask, services::auth::WifiAuthenticationUncertaintySourceRead)) {
        return UiTextId::WifiAuthReasonSource;
    }
    if (hasUncertainty(
            mask, services::auth::WifiAuthenticationUncertaintyMalformed)) {
        return UiTextId::WifiAuthReasonMalformed;
    }
    if (hasUncertainty(
            mask, services::auth::WifiAuthenticationUncertaintyTruncated) ||
        hasUncertainty(
            mask, services::auth::WifiAuthenticationUncertaintyCapacity)) {
        return UiTextId::WifiAuthReasonLimit;
    }
    if (hasUncertainty(
            mask, services::auth::WifiAuthenticationUncertaintyNoEvidence)) {
        return UiTextId::WifiAuthReasonNoData;
    }
    return UiTextId::WifiAuthReasonUnsupported;
}

UiTextId metricText(WifiAuthenticationCaptureUiMetric metric,
                    std::uint32_t primary) {
    switch (metric) {
        case WifiAuthenticationCaptureUiMetric::TimeRemainingSeconds:
            return UiTextId::WifiAuthTimeRemainingFormat;
        case WifiAuthenticationCaptureUiMetric::ChannelAndCandidateFrames:
            return UiTextId::WifiAuthChannelCandidatesFormat;
        case WifiAuthenticationCaptureUiMetric::RetainedAndDroppedFrames:
            return UiTextId::WifiAuthKeptLostFormat;
        case WifiAuthenticationCaptureUiMetric::TerminalAnalysisPending:
            return UiTextId::WifiAuthExactAfterStop;
        case WifiAuthenticationCaptureUiMetric::CompleteAndPartialPeers:
            return UiTextId::WifiAuthPeersFormat;
        case WifiAuthenticationCaptureUiMetric::PmkidsAndEapolFrames:
            return UiTextId::WifiAuthPmkidEapolFormat;
        case WifiAuthenticationCaptureUiMetric::SelectedPeerMask:
        case WifiAuthenticationCaptureUiMetric::PeerMessageMask:
            return UiTextId::WifiAuthPeerMaskFormat;
        case WifiAuthenticationCaptureUiMetric::EvidenceAndSourceFrames:
            return UiTextId::WifiAuthEvidenceFormat;
        case WifiAuthenticationCaptureUiMetric::LossAndRejectedFrames:
            return UiTextId::WifiAuthLossFormat;
        case WifiAuthenticationCaptureUiMetric::UncertaintyMask:
            return uncertaintyText(static_cast<std::uint16_t>(primary));
        case WifiAuthenticationCaptureUiMetric::ActionDetails:
            return UiTextId::WifiAuthActionDetails;
        case WifiAuthenticationCaptureUiMetric::ActionRepeat:
            return UiTextId::WifiAuthActionRepeat;
        case WifiAuthenticationCaptureUiMetric::PeerPosition:
            return UiTextId::WifiAuthPeerPositionFormat;
        case WifiAuthenticationCaptureUiMetric::PeerState:
            switch (primary) {
                case 1U: return UiTextId::WifiAuthPeerSequenceOk;
                case 2U: return UiTextId::WifiAuthPeerVerified;
                case 3U: return UiTextId::WifiAuthPeerNonceMismatch;
                default: return UiTextId::WifiAuthPeerNotVerified;
            }
        case WifiAuthenticationCaptureUiMetric::PeerEvidenceCount:
            return UiTextId::WifiAuthPeerEvidenceFormat;
        case WifiAuthenticationCaptureUiMetric::EvidenceListRow:
            return UiTextId::WifiAuthEvidenceListRowFormat;
        case WifiAuthenticationCaptureUiMetric::EvidenceMessageAndFrame:
            return UiTextId::WifiAuthEvidenceFrameFormat;
        case WifiAuthenticationCaptureUiMetric::EvidenceChannelAndSignal:
            return UiTextId::WifiAuthEvidenceSignalFormat;
        case WifiAuthenticationCaptureUiMetric::EvidenceReplayCounter:
            return UiTextId::WifiAuthEvidenceReplayFormat;
        case WifiAuthenticationCaptureUiMetric::EvidenceDescriptor:
            return UiTextId::WifiAuthEvidenceDescriptorFormat;
        case WifiAuthenticationCaptureUiMetric::FailureCode:
            switch (static_cast<WifiAuthenticationCaptureUiFailure>(primary)) {
                case WifiAuthenticationCaptureUiFailure::StartFailed:
                    return UiTextId::WifiAuthFailureStart;
                case WifiAuthenticationCaptureUiFailure::RuntimeFailed:
                    return UiTextId::WifiAuthFailureRuntime;
                case WifiAuthenticationCaptureUiFailure::ResultBeforeCleanup:
                    return UiTextId::WifiAuthFailureCleanup;
                case WifiAuthenticationCaptureUiFailure::ReportRejected:
                    return UiTextId::WifiAuthFailureReport;
                case WifiAuthenticationCaptureUiFailure::None:
                case WifiAuthenticationCaptureUiFailure::
                    InvalidPresentationInput:
                    return UiTextId::WifiAuthFailureInvalid;
            }
            return UiTextId::WifiAuthFailureInvalid;
        case WifiAuthenticationCaptureUiMetric::None:
            return UiTextId::WifiAuthFailureInvalid;
    }
    return UiTextId::WifiAuthFailureInvalid;
}

void setRow(WifiAuthenticationCaptureUiModel& model, std::size_t index,
            WifiAuthenticationCaptureUiMetric metric,
            std::uint32_t primary = 0U, std::uint32_t secondary = 0U,
            bool warning = false, bool selected = false,
            std::uint64_t exact = 0U) {
    if (index >= model.rows.size()) return;
    WifiAuthenticationCaptureUiRow& row = model.rows[index];
    row.metric = metric;
    row.text = metricText(metric, primary);
    row.primary = primary;
    row.secondary = secondary;
    row.exact = exact;
    row.warning = warning;
    row.selected = selected;
    if (model.rowCount <= index) model.rowCount = index + 1U;
}

WifiAuthenticationCaptureUiModel failedModel(
    WifiAuthenticationCaptureUiFailure failure, bool cleanupComplete) {
    WifiAuthenticationCaptureUiModel model{};
    model.failure = failure;
    model.cleanupComplete = cleanupComplete;
    model.note = cleanupComplete ? UiTextId::CaptureFailureNote
                                 : UiTextId::AirspaceGuardEvidenceIncomplete;
    setRow(model, 0U, WifiAuthenticationCaptureUiMetric::FailureCode,
           static_cast<std::uint32_t>(failure), 0U, true);
    return model;
}

WifiAuthenticationCaptureUiModel transitionModel(
    WifiAuthenticationCaptureUiPhase phase) {
    WifiAuthenticationCaptureUiModel model{};
    model.failure = WifiAuthenticationCaptureUiFailure::None;
    model.evidenceIncomplete = false;
    model.cleanupComplete = false;
    if (phase == WifiAuthenticationCaptureUiPhase::Preparing) {
        model.title = UiTextId::WifiAuthPreparingTitle;
        model.headline = UiTextId::WifiAuthPreparingHeadline;
        model.note = UiTextId::WifiAuthPreparingNote;
        model.view = WifiAuthenticationCaptureUiView::Preparing;
        model.tone = WifiAuthenticationCaptureUiTone::Neutral;
    } else {
        model.title = UiTextId::WifiAuthCancellingTitle;
        model.headline = UiTextId::WifiAuthCancellingHeadline;
        model.note = UiTextId::WifiAuthCancellingNote;
        model.view = WifiAuthenticationCaptureUiView::Cancelling;
        model.tone = WifiAuthenticationCaptureUiTone::Caution;
    }
    return model;
}

WifiAuthenticationCaptureUiModel runningModel(
    const WifiAuthenticationCaptureLiveProgress& progress) {
    WifiAuthenticationCaptureUiModel model{};
    model.title = UiTextId::CaptureRunning;
    model.headline = UiTextId::CaptureRecordingUser;
    model.note = UiTextId::RunningPassive;
    model.view = WifiAuthenticationCaptureUiView::Running;
    model.tone = WifiAuthenticationCaptureUiTone::Neutral;
    model.failure = WifiAuthenticationCaptureUiFailure::None;
    model.evidenceIncomplete = false;
    model.cleanupComplete = false;
    const std::uint32_t remainingMs =
        progress.durationMs - progress.elapsedMs;
    const std::uint32_t remainingSeconds =
        remainingMs == 0U ? 0U : (remainingMs + 999U) / 1000U;
    const std::uint32_t dropped = saturatingAdd(
        progress.framesDroppedCapacity, progress.framesDroppedInvalid);
    setRow(model, 0U,
           WifiAuthenticationCaptureUiMetric::TimeRemainingSeconds,
           remainingSeconds);
    setRow(model, 1U,
           WifiAuthenticationCaptureUiMetric::ChannelAndCandidateFrames,
           progress.channel, progress.candidateFrames);
    setRow(model, 2U,
           WifiAuthenticationCaptureUiMetric::RetainedAndDroppedFrames,
           progress.framesAccepted, dropped, dropped != 0U);
    setRow(model, 3U,
           WifiAuthenticationCaptureUiMetric::TerminalAnalysisPending);
    return model;
}

WifiAuthenticationCaptureUiModel baseReportModel(
    const WifiAuthenticationCaptureController& controller) {
    WifiAuthenticationCaptureUiModel model{};
    model.failure = WifiAuthenticationCaptureUiFailure::None;
    model.cleanupComplete = true;
    model.reportOpenable = controller.reportOpenable();
    model.exportEligibility =
        WifiAuthenticationCaptureExportEligibility::NotEvaluated;
    return model;
}

WifiAuthenticationCaptureUiModel outcomeModel(
    const WifiAuthenticationCaptureReport& report,
    const WifiAuthenticationCaptureController& controller) {
    WifiAuthenticationCaptureUiModel model = baseReportModel(controller);
    model.title = UiTextId::CaptureResult;
    model.note = UiTextId::WifiAuthVolatileNote;
    const std::uint32_t complete = completePeers(report);
    const std::uint32_t partial = partialPeers(report);

    if (report.outcome == WifiAuthenticationCaptureOutcome::Inconclusive) {
        model.view = WifiAuthenticationCaptureUiView::Inconclusive;
        model.headline = UiTextId::WifiAuthInconclusiveHeadline;
        model.note = UiTextId::AirspaceGuardEvidenceIncomplete;
        model.tone = WifiAuthenticationCaptureUiTone::Caution;
        model.evidenceIncomplete = true;
    } else if (complete != 0U) {
        model.view = WifiAuthenticationCaptureUiView::Result;
        model.headline = UiTextId::WifiAuthFullHandshakeHeadline;
        model.tone = WifiAuthenticationCaptureUiTone::Positive;
        model.evidenceIncomplete = false;
    } else if (report.pmkidCount != 0U) {
        model.view = WifiAuthenticationCaptureUiView::Result;
        model.headline = UiTextId::WifiAuthPmkidHeadline;
        model.tone = WifiAuthenticationCaptureUiTone::Positive;
        model.evidenceIncomplete = false;
    } else if (hasPartialPeer(report)) {
        model.view = WifiAuthenticationCaptureUiView::Result;
        model.headline = UiTextId::WifiAuthPartialHandshakeHeadline;
        model.tone = WifiAuthenticationCaptureUiTone::Caution;
        model.evidenceIncomplete = false;
    } else {
        model.view = WifiAuthenticationCaptureUiView::Result;
        model.headline = UiTextId::WifiAuthDataHeadline;
        model.tone = WifiAuthenticationCaptureUiTone::Caution;
        model.evidenceIncomplete = false;
    }
    setRow(model, 0U,
           WifiAuthenticationCaptureUiMetric::CompleteAndPartialPeers,
           complete, partial, partial != 0U);
    setRow(model, 1U,
           WifiAuthenticationCaptureUiMetric::PmkidsAndEapolFrames,
           static_cast<std::uint32_t>(report.pmkidCount),
           report.counters.eapolFrames);
    const WifiAuthenticationPeer* peer = controller.selectedPeer();
    if (peer != nullptr) {
        setRow(model, 2U,
               WifiAuthenticationCaptureUiMetric::SelectedPeerMask,
               peer->messageMask);
    } else {
        setRow(model, 2U,
               WifiAuthenticationCaptureUiMetric::EvidenceAndSourceFrames,
               static_cast<std::uint32_t>(report.evidenceCount),
               report.counters.sourceFrames);
    }
    if (report.outcome == WifiAuthenticationCaptureOutcome::Inconclusive) {
        setRow(model, 3U,
               WifiAuthenticationCaptureUiMetric::UncertaintyMask,
               report.uncertainty, 0U, true);
    } else {
        setRow(model, 3U,
               WifiAuthenticationCaptureUiMetric::EvidenceAndSourceFrames,
               static_cast<std::uint32_t>(report.evidenceCount),
               report.counters.sourceFrames);
    }
    return model;
}

WifiAuthenticationCaptureUiModel actionsModel(
    const WifiAuthenticationCaptureController& controller) {
    WifiAuthenticationCaptureUiModel model = baseReportModel(controller);
    model.title = UiTextId::WifiAuthActionsHeadline;
    model.headline = UiTextId::WifiAuthActionsHeadline;
    model.note = UiTextId::WifiAuthVolatileNote;
    model.view = WifiAuthenticationCaptureUiView::Actions;
    model.tone = WifiAuthenticationCaptureUiTone::Neutral;
    model.evidenceIncomplete = false;
    for (std::size_t index = 0U; index < controller.actionCount(); ++index) {
        const WifiAuthenticationCaptureAction action =
            controller.hasDetails() && index == 0U
                ? WifiAuthenticationCaptureAction::Details
                : WifiAuthenticationCaptureAction::Repeat;
        setRow(model, index,
               action == WifiAuthenticationCaptureAction::Details
                   ? WifiAuthenticationCaptureUiMetric::ActionDetails
                   : WifiAuthenticationCaptureUiMetric::ActionRepeat,
               0U, 0U, false, controller.actionSelection() == index);
    }
    return model;
}

WifiAuthenticationCaptureUiModel peerModel(
    const WifiAuthenticationCaptureController& controller) {
    const WifiAuthenticationCaptureReport* report = controller.report();
    const WifiAuthenticationPeer* peer = controller.selectedPeer();
    if (report == nullptr || peer == nullptr) {
        return failedModel(
            WifiAuthenticationCaptureUiFailure::ReportRejected, true);
    }
    WifiAuthenticationCaptureUiModel model = baseReportModel(controller);
    model.title = UiTextId::WifiAuthPeerTitle;
    model.headline = UiTextId::WifiAuthPeerHeadline;
    model.note = UiTextId::WifiAuthVolatileNote;
    model.view = WifiAuthenticationCaptureUiView::PeerDetail;
    model.tone = peer->complete ? WifiAuthenticationCaptureUiTone::Positive
                                : WifiAuthenticationCaptureUiTone::Caution;
    model.evidenceIncomplete = false;
    setRow(model, 0U, WifiAuthenticationCaptureUiMetric::PeerPosition,
           static_cast<std::uint32_t>(
               controller.selectedPeerPosition() + 1U),
           static_cast<std::uint32_t>(controller.peerCount()));
    setRow(model, 1U, WifiAuthenticationCaptureUiMetric::PeerMessageMask,
           peer->messageMask);
    std::uint32_t state = 0U;
    if (peer->complete) {
        state = 2U;
    } else if (peer->authenticatorNonceMismatch) {
        state = 3U;
    } else if (peer->sequenceConsistent && peer->messageMask != 0U) {
        state = 1U;
    }
    setRow(model, 2U, WifiAuthenticationCaptureUiMetric::PeerState,
           state, 0U, state == 0U || state == 3U);
    setRow(model, 3U, WifiAuthenticationCaptureUiMetric::PeerEvidenceCount,
           static_cast<std::uint32_t>(
               controller.selectedPeerEvidenceCount()));
    return model;
}

std::uint32_t packEvidenceRow(const WifiAuthenticationEvidence& evidence,
                              bool pmkid) {
    const std::uint32_t signal = static_cast<std::uint8_t>(evidence.rssiDbm);
    const std::uint32_t message = static_cast<std::uint8_t>(evidence.message);
    return static_cast<std::uint32_t>(evidence.channel) |
        (signal << 8U) | (message << 16U) |
        (pmkid ? (1UL << 24U) : 0U);
}

WifiAuthenticationCaptureUiModel evidenceListModel(
    const WifiAuthenticationCaptureController& controller) {
    if (controller.evidenceCount() == 0U) {
        return failedModel(
            WifiAuthenticationCaptureUiFailure::ReportRejected, true);
    }
    WifiAuthenticationCaptureUiModel model = baseReportModel(controller);
    model.title = UiTextId::WifiAuthEvidenceTitle;
    model.headline = UiTextId::WifiAuthEvidenceHeadline;
    model.note = UiTextId::WifiAuthEvidenceOrderNote;
    model.view = WifiAuthenticationCaptureUiView::EvidenceList;
    model.tone = WifiAuthenticationCaptureUiTone::Neutral;
    model.evidenceIncomplete = false;
    const std::size_t selection = controller.evidenceSelection();
    const std::size_t first =
        selection < WifiAuthenticationCaptureUiModel::kVisibleRowCapacity
            ? 0U
            : selection -
                  WifiAuthenticationCaptureUiModel::kVisibleRowCapacity + 1U;
    const std::size_t end = std::min(
        controller.evidenceCount(),
        first + WifiAuthenticationCaptureUiModel::kVisibleRowCapacity);
    for (std::size_t ordered = first; ordered < end; ++ordered) {
        const WifiAuthenticationEvidence* evidence =
            controller.evidenceAt(ordered);
        if (evidence == nullptr) {
            return failedModel(
                WifiAuthenticationCaptureUiFailure::ReportRejected, true);
        }
        setRow(model, ordered - first,
               WifiAuthenticationCaptureUiMetric::EvidenceListRow,
               evidence->sourceFrameIndex,
               packEvidenceRow(
                   *evidence, controller.evidenceHasPmkid(ordered)),
               false, ordered == selection);
    }
    return model;
}

WifiAuthenticationCaptureUiModel evidenceDetailModel(
    const WifiAuthenticationCaptureController& controller) {
    const WifiAuthenticationEvidence* evidence =
        controller.selectedEvidence();
    if (evidence == nullptr) {
        return failedModel(
            WifiAuthenticationCaptureUiFailure::ReportRejected, true);
    }
    WifiAuthenticationCaptureUiModel model = baseReportModel(controller);
    model.title = UiTextId::WifiAuthEvidenceDetailTitle;
    model.headline = UiTextId::WifiAuthEvidenceDetailHeadline;
    model.note = controller.selectedEvidenceHasPmkid()
        ? UiTextId::WifiAuthPmkidEvidenceNote
        : UiTextId::WifiAuthVolatileNote;
    model.view = WifiAuthenticationCaptureUiView::EvidenceDetail;
    model.tone = WifiAuthenticationCaptureUiTone::Neutral;
    model.evidenceIncomplete = false;
    setRow(model, 0U,
           WifiAuthenticationCaptureUiMetric::EvidenceMessageAndFrame,
           evidence->sourceFrameIndex,
           static_cast<std::uint32_t>(evidence->message), false, false,
           controller.selectedEvidenceHasPmkid() ? 1U : 0U);
    setRow(model, 1U,
           WifiAuthenticationCaptureUiMetric::EvidenceChannelAndSignal,
           evidence->channel,
           static_cast<std::uint32_t>(
               static_cast<std::int32_t>(evidence->rssiDbm)));
    setRow(model, 2U,
           WifiAuthenticationCaptureUiMetric::EvidenceReplayCounter,
           0U, 0U, false, false, evidence->replayCounter);
    setRow(model, 3U,
           WifiAuthenticationCaptureUiMetric::EvidenceDescriptor,
           evidence->eapolVersion, evidence->descriptorType, false, false,
           evidence->descriptorVersion);
    return model;
}

WifiAuthenticationCaptureUiModel reportModel(
    const WifiAuthenticationCaptureReport& report,
    const WifiAuthenticationCaptureController& controller) {
    switch (controller.view()) {
        case WifiAuthenticationCaptureView::Outcome:
            return outcomeModel(report, controller);
        case WifiAuthenticationCaptureView::Actions:
            return actionsModel(controller);
        case WifiAuthenticationCaptureView::PeerDetail:
            return peerModel(controller);
        case WifiAuthenticationCaptureView::EvidenceList:
            return evidenceListModel(controller);
        case WifiAuthenticationCaptureView::EvidenceDetail:
            return evidenceDetailModel(controller);
    }
    return failedModel(
        WifiAuthenticationCaptureUiFailure::ReportRejected, true);
}

bool sameRow(const WifiAuthenticationCaptureUiRow& left,
             const WifiAuthenticationCaptureUiRow& right) {
    return left.metric == right.metric && left.text == right.text &&
        left.primary == right.primary && left.secondary == right.secondary &&
        left.exact == right.exact && left.warning == right.warning &&
        left.selected == right.selected;
}

}  // namespace

WifiAuthenticationCaptureUiModel presentWifiAuthenticationCapture(
    const WifiAuthenticationCaptureUiInput& input) {
    switch (input.phase) {
        case WifiAuthenticationCaptureUiPhase::Preparing:
        case WifiAuthenticationCaptureUiPhase::Cancelling:
            if (input.report != nullptr || input.controller != nullptr ||
                input.cleanupComplete ||
                input.synthetic ||
                input.failure != WifiAuthenticationCaptureUiFailure::None ||
                !liveProgressEmpty(input.progress)) {
                return failedModel(
                    WifiAuthenticationCaptureUiFailure::
                        InvalidPresentationInput,
                    input.cleanupComplete);
            }
            return transitionModel(input.phase);
        case WifiAuthenticationCaptureUiPhase::Running:
            if (input.report != nullptr || input.controller != nullptr ||
                input.cleanupComplete ||
                input.synthetic ||
                input.failure != WifiAuthenticationCaptureUiFailure::None ||
                !liveProgressValid(input.progress)) {
                return failedModel(
                    WifiAuthenticationCaptureUiFailure::
                        InvalidPresentationInput,
                    input.cleanupComplete);
            }
            return runningModel(input.progress);
        case WifiAuthenticationCaptureUiPhase::Report:
            if (!input.cleanupComplete) {
                return failedModel(
                    WifiAuthenticationCaptureUiFailure::ResultBeforeCleanup,
                    false);
            }
            if (input.report == nullptr || input.controller == nullptr ||
                input.failure != WifiAuthenticationCaptureUiFailure::None ||
                !input.controller->ready() ||
                input.controller->report() != input.report ||
                !reportShapeValid(*input.report)) {
                return failedModel(
                    WifiAuthenticationCaptureUiFailure::ReportRejected,
                    true);
            }
            {
                WifiAuthenticationCaptureUiModel model =
                    reportModel(*input.report, *input.controller);
                model.synthetic = input.synthetic;
                if (input.synthetic) model.note = UiTextId::SimulatedData;
                return model;
            }
        case WifiAuthenticationCaptureUiPhase::Failed:
            if (input.report != nullptr || input.controller != nullptr ||
                input.synthetic ||
                input.failure == WifiAuthenticationCaptureUiFailure::None) {
                return failedModel(
                    WifiAuthenticationCaptureUiFailure::
                        InvalidPresentationInput,
                    input.cleanupComplete);
            }
            return failedModel(input.failure, input.cleanupComplete);
    }
    return failedModel(
        WifiAuthenticationCaptureUiFailure::InvalidPresentationInput,
        input.cleanupComplete);
}

WifiAuthenticationCaptureUiDelta diffWifiAuthenticationCaptureUi(
    const WifiAuthenticationCaptureUiModel& previous,
    const WifiAuthenticationCaptureUiModel& current) {
    WifiAuthenticationCaptureUiDelta delta{};
    const bool toneChanged = previous.tone != current.tone;
    if (previous.title != current.title || previous.view != current.view ||
        toneChanged) {
        delta.fixedRegionMask = static_cast<std::uint8_t>(
            delta.fixedRegionMask | kWifiAuthenticationTitleRegion);
    }
    if (previous.headline != current.headline ||
        previous.evidenceIncomplete != current.evidenceIncomplete ||
        previous.reportOpenable != current.reportOpenable ||
        previous.exportEligibility != current.exportEligibility ||
        toneChanged) {
        delta.fixedRegionMask = static_cast<std::uint8_t>(
            delta.fixedRegionMask | kWifiAuthenticationHeadlineRegion);
    }
    if (previous.note != current.note ||
        previous.cleanupComplete != current.cleanupComplete ||
        previous.failure != current.failure ||
        previous.synthetic != current.synthetic) {
        delta.fixedRegionMask = static_cast<std::uint8_t>(
            delta.fixedRegionMask | kWifiAuthenticationNoteRegion);
    }
    for (std::size_t index = 0U; index < current.rows.size(); ++index) {
        const bool previouslyVisible = index < previous.rowCount;
        const bool currentlyVisible = index < current.rowCount;
        if (previouslyVisible != currentlyVisible ||
            (currentlyVisible && toneChanged) ||
            (currentlyVisible &&
             !sameRow(previous.rows[index], current.rows[index]))) {
            delta.rowMask = static_cast<std::uint8_t>(
                delta.rowMask | static_cast<std::uint8_t>(1U << index));
        }
    }
    return delta;
}

}  // namespace leshy1::ui
