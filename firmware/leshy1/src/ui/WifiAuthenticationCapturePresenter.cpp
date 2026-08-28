#include "WifiAuthenticationCapturePresenter.h"

#include <limits>
#include <type_traits>

namespace leshy1::ui {
namespace {

using services::auth::WifiAuthenticationCaptureOutcome;
using services::auth::WifiAuthenticationCaptureReport;
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

std::uint32_t saturatingSumLoss(
    const services::auth::WifiAuthenticationCaptureCounters& counters) {
    std::uint32_t total = 0;
    total = saturatingAdd(total, counters.captureFramesDroppedCapacity);
    total = saturatingAdd(total, counters.captureFramesDroppedInvalid);
    total = saturatingAdd(total, counters.sourceReadFailures);
    total = saturatingAdd(total, counters.malformedFrames);
    total = saturatingAdd(total, counters.truncatedFrames);
    total = saturatingAdd(total, counters.evidenceDropped);
    total = saturatingAdd(total, counters.peersDropped);
    total = saturatingAdd(total, counters.pmkidsDropped);
    return total;
}

std::uint32_t saturatingSumRejected(
    const services::auth::WifiAuthenticationCaptureCounters& counters) {
    std::uint32_t total = counters.sequenceRejected;
    total = saturatingAdd(total, counters.unclassifiedKeyFrames);
    total = saturatingAdd(total, counters.unsupportedKeyFrames);
    return total;
}

bool hasUncertainty(std::uint16_t mask,
                    WifiAuthenticationUncertainty uncertainty) {
    return (mask & static_cast<std::uint16_t>(uncertainty)) != 0U;
}

bool liveProgressValid(const WifiAuthenticationCaptureLiveProgress& progress) {
    if (progress.durationMs == 0U ||
        progress.elapsedMs > progress.durationMs ||
        progress.channel < 1U || progress.channel > 14U ||
        progress.eapolKeyFrames > progress.eapolFrames ||
        progress.eapolFrames > progress.framesAccepted) {
        return false;
    }
    const std::uint64_t accounted =
        static_cast<std::uint64_t>(progress.framesAccepted) +
        progress.framesDroppedCapacity + progress.framesDroppedInvalid;
    return accounted == progress.framesReported;
}

bool liveProgressEmpty(const WifiAuthenticationCaptureLiveProgress& progress) {
    return progress.elapsedMs == 0U && progress.durationMs == 0U &&
        progress.framesReported == 0U && progress.framesAccepted == 0U &&
        progress.framesDroppedCapacity == 0U &&
        progress.framesDroppedInvalid == 0U && progress.eapolFrames == 0U &&
        progress.eapolKeyFrames == 0U && progress.channel == 0U;
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

    std::size_t completePeerCount = 0;
    for (std::size_t peerIndex = 0; peerIndex < report.peerCount;
         ++peerIndex) {
        const auto& peer = report.peers[peerIndex];
        if ((peer.messageMask & 0xf0U) != 0U) return false;
        for (std::uint8_t evidenceIndex : peer.evidenceIndices) {
            if (evidenceIndex !=
                    services::auth::WifiAuthenticationPeer::kMissingEvidence &&
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
    for (std::size_t evidenceIndex = 0;
         evidenceIndex < report.evidenceCount; ++evidenceIndex) {
        const auto& evidence = report.evidence[evidenceIndex];
        if (evidence.sourceFrameIndex >= counters.sourceFrames ||
            evidence.monotonicUs == 0U || evidence.channel < 1U ||
            evidence.channel > 14U) {
            return false;
        }
    }
    for (std::size_t pmkidIndex = 0; pmkidIndex < report.pmkidCount;
         ++pmkidIndex) {
        if (report.pmkids[pmkidIndex].sourceFrameIndex >=
                counters.sourceFrames ||
            report.pmkids[pmkidIndex].monotonicUs == 0U) {
            return false;
        }
    }

    switch (report.outcome) {
        case WifiAuthenticationCaptureOutcome::Complete:
            return report.uncertainty == 0U && completePeerCount != 0U;
        case WifiAuthenticationCaptureOutcome::Incomplete:
            return report.uncertainty == 0U && completePeerCount == 0U;
        case WifiAuthenticationCaptureOutcome::Inconclusive:
            return report.uncertainty != 0U;
    }
    return false;
}

std::uint32_t completePeers(const WifiAuthenticationCaptureReport& report) {
    std::uint32_t count = 0;
    for (std::size_t index = 0; index < report.peerCount; ++index) {
        if (report.peers[index].complete) ++count;
    }
    return count;
}

UiTextId metricText(WifiAuthenticationCaptureUiMetric metric,
                    std::uint32_t primary) {
    switch (metric) {
        case WifiAuthenticationCaptureUiMetric::TimeProgressMs:
            return UiTextId::WifiAuthTimeFormat;
        case WifiAuthenticationCaptureUiMetric::ChannelAndReportedFrames:
            return UiTextId::WifiAuthChannelFramesFormat;
        case WifiAuthenticationCaptureUiMetric::RetainedAndDroppedFrames:
            return UiTextId::WifiAuthKeptLostFormat;
        case WifiAuthenticationCaptureUiMetric::EapolAndKeyFrames:
            return UiTextId::WifiAuthEapolKeysFormat;
        case WifiAuthenticationCaptureUiMetric::CompleteAndPartialPeers:
            return UiTextId::WifiAuthPeersFormat;
        case WifiAuthenticationCaptureUiMetric::EapolKeysAndPmkids:
            return UiTextId::WifiAuthKeysPmkidFormat;
        case WifiAuthenticationCaptureUiMetric::EvidenceAndSourceFrames:
            return UiTextId::WifiAuthEvidenceFormat;
        case WifiAuthenticationCaptureUiMetric::LossAndRejectedFrames:
            return UiTextId::WifiAuthLossFormat;
        case WifiAuthenticationCaptureUiMetric::UncertaintyMask: {
            const auto mask = static_cast<std::uint16_t>(primary);
            if (hasUncertainty(
                    mask, services::auth::
                              WifiAuthenticationUncertaintyInvalidInput)) {
                return UiTextId::WifiAuthReasonInvalid;
            }
            if (hasUncertainty(
                    mask, services::auth::
                              WifiAuthenticationUncertaintyCaptureIncomplete)) {
                return UiTextId::WifiAuthReasonInterrupted;
            }
            if (hasUncertainty(
                    mask, services::auth::
                              WifiAuthenticationUncertaintyCaptureLoss)) {
                return UiTextId::WifiAuthReasonLoss;
            }
            if (hasUncertainty(
                    mask, services::auth::
                              WifiAuthenticationUncertaintySourceRead)) {
                return UiTextId::WifiAuthReasonSource;
            }
            if (hasUncertainty(
                    mask, services::auth::
                              WifiAuthenticationUncertaintyMalformed)) {
                return UiTextId::WifiAuthReasonMalformed;
            }
            if (hasUncertainty(
                    mask, services::auth::
                              WifiAuthenticationUncertaintyTruncated) ||
                hasUncertainty(
                    mask, services::auth::
                              WifiAuthenticationUncertaintyCapacity)) {
                return UiTextId::WifiAuthReasonLimit;
            }
            if (hasUncertainty(
                    mask, services::auth::
                              WifiAuthenticationUncertaintyNoEvidence)) {
                return UiTextId::WifiAuthReasonNoData;
            }
            return UiTextId::WifiAuthReasonUnsupported;
        }
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
                case WifiAuthenticationCaptureUiFailure::InvalidPresentationInput:
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
            std::uint32_t primary, std::uint32_t secondary,
            bool warning = false) {
    if (index >= model.rows.size()) return;
    model.rows[index].metric = metric;
    model.rows[index].text = metricText(metric, primary);
    model.rows[index].primary = primary;
    model.rows[index].secondary = secondary;
    model.rows[index].warning = warning;
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
    model.reportOpenable = false;
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
    const std::uint32_t dropped = saturatingAdd(
        progress.framesDroppedCapacity, progress.framesDroppedInvalid);
    setRow(model, 0U, WifiAuthenticationCaptureUiMetric::TimeProgressMs,
           remainingMs, progress.durationMs);
    setRow(model, 1U,
           WifiAuthenticationCaptureUiMetric::ChannelAndReportedFrames,
           progress.channel, progress.framesReported);
    setRow(model, 2U,
           WifiAuthenticationCaptureUiMetric::RetainedAndDroppedFrames,
           progress.framesAccepted, dropped, dropped != 0U);
    setRow(model, 3U,
           WifiAuthenticationCaptureUiMetric::EapolAndKeyFrames,
           progress.eapolFrames, progress.eapolKeyFrames);
    return model;
}

WifiAuthenticationCaptureUiModel reportModel(
    const WifiAuthenticationCaptureReport& report) {
    WifiAuthenticationCaptureUiModel model{};
    model.title = UiTextId::CaptureResult;
    model.headline = UiTextId::CaptureResult;
    model.note = UiTextId::AirspaceGuardResultAfterCleanup;
    model.failure = WifiAuthenticationCaptureUiFailure::None;
    model.cleanupComplete = true;
    const std::uint32_t complete = completePeers(report);
    const std::uint32_t peerCount =
        static_cast<std::uint32_t>(report.peerCount);
    const std::uint32_t partial = peerCount - complete;
    const std::uint32_t loss = saturatingSumLoss(report.counters);
    const std::uint32_t rejected = saturatingSumRejected(report.counters);

    if (report.outcome == WifiAuthenticationCaptureOutcome::Complete) {
        model.view = WifiAuthenticationCaptureUiView::Result;
        model.tone = WifiAuthenticationCaptureUiTone::Positive;
        model.evidenceIncomplete = false;
    } else if (report.outcome ==
               WifiAuthenticationCaptureOutcome::Incomplete) {
        model.view = WifiAuthenticationCaptureUiView::Result;
        model.tone = WifiAuthenticationCaptureUiTone::Caution;
        model.evidenceIncomplete = false;
        model.note = UiTextId::AirspaceGuardPassiveOnly;
    } else {
        model.view = WifiAuthenticationCaptureUiView::Inconclusive;
        model.headline = UiTextId::AirspaceGuardInconclusive;
        model.note = UiTextId::AirspaceGuardEvidenceIncomplete;
        model.tone = WifiAuthenticationCaptureUiTone::Caution;
        model.evidenceIncomplete = true;
    }
    // Evidence navigation is a separate bounded slice. Do not promise an action
    // that the current product screen cannot perform.
    model.reportOpenable = false;
    setRow(model, 0U,
           WifiAuthenticationCaptureUiMetric::CompleteAndPartialPeers,
           complete, partial, partial != 0U);
    setRow(model, 1U,
           WifiAuthenticationCaptureUiMetric::EapolKeysAndPmkids,
           report.counters.eapolKeyFrames,
           static_cast<std::uint32_t>(report.pmkidCount));
    if (model.view == WifiAuthenticationCaptureUiView::Inconclusive) {
        setRow(model, 2U,
               WifiAuthenticationCaptureUiMetric::LossAndRejectedFrames,
               loss, rejected, true);
        setRow(model, 3U,
               WifiAuthenticationCaptureUiMetric::UncertaintyMask,
               report.uncertainty, 0U, true);
    } else {
        setRow(model, 2U,
               WifiAuthenticationCaptureUiMetric::EvidenceAndSourceFrames,
               static_cast<std::uint32_t>(report.evidenceCount),
               report.counters.sourceFrames);
        setRow(model, 3U,
               WifiAuthenticationCaptureUiMetric::LossAndRejectedFrames,
               loss, rejected, loss != 0U || rejected != 0U);
    }
    return model;
}

bool sameRow(const WifiAuthenticationCaptureUiRow& left,
             const WifiAuthenticationCaptureUiRow& right) {
    return left.metric == right.metric && left.text == right.text &&
        left.primary == right.primary && left.secondary == right.secondary &&
        left.warning == right.warning;
}

}  // namespace

WifiAuthenticationCaptureUiModel presentWifiAuthenticationCapture(
    const WifiAuthenticationCaptureUiInput& input) {
    switch (input.phase) {
        case WifiAuthenticationCaptureUiPhase::Preparing:
        case WifiAuthenticationCaptureUiPhase::Cancelling:
            if (input.report != nullptr || input.cleanupComplete ||
                input.failure != WifiAuthenticationCaptureUiFailure::None ||
                !liveProgressEmpty(input.progress)) {
                return failedModel(
                    WifiAuthenticationCaptureUiFailure::
                        InvalidPresentationInput,
                    input.cleanupComplete);
            }
            return transitionModel(input.phase);
        case WifiAuthenticationCaptureUiPhase::Running:
            if (input.report != nullptr || input.cleanupComplete ||
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
            if (input.report == nullptr ||
                input.failure != WifiAuthenticationCaptureUiFailure::None ||
                !reportShapeValid(*input.report)) {
                return failedModel(
                    WifiAuthenticationCaptureUiFailure::ReportRejected,
                    true);
            }
            return reportModel(*input.report);
        case WifiAuthenticationCaptureUiPhase::Failed:
            if (input.report != nullptr ||
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
    if (previous.title != current.title || previous.view != current.view ||
        previous.tone != current.tone) {
        delta.fixedRegionMask = static_cast<std::uint8_t>(
            delta.fixedRegionMask | kWifiAuthenticationTitleRegion);
    }
    if (previous.headline != current.headline ||
        previous.evidenceIncomplete != current.evidenceIncomplete ||
        previous.reportOpenable != current.reportOpenable) {
        delta.fixedRegionMask = static_cast<std::uint8_t>(
            delta.fixedRegionMask | kWifiAuthenticationHeadlineRegion);
    }
    if (previous.note != current.note ||
        previous.cleanupComplete != current.cleanupComplete ||
        previous.failure != current.failure) {
        delta.fixedRegionMask = static_cast<std::uint8_t>(
            delta.fixedRegionMask | kWifiAuthenticationNoteRegion);
    }
    for (std::size_t index = 0; index < current.rows.size(); ++index) {
        const bool previouslyVisible = index < previous.rowCount;
        const bool currentlyVisible = index < current.rowCount;
        if (previouslyVisible != currentlyVisible ||
            (currentlyVisible && !sameRow(previous.rows[index],
                                          current.rows[index]))) {
            delta.rowMask = static_cast<std::uint8_t>(
                delta.rowMask | static_cast<std::uint8_t>(1U << index));
        }
    }
    return delta;
}

}  // namespace leshy1::ui
