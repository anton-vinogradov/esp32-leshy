#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <type_traits>

#include "ui/WifiAuthenticationCapturePresenter.h"

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__,      \
                         __LINE__, #condition);                                 \
            std::abort();                                                       \
        }                                                                       \
    } while (false)

namespace {

using namespace leshy1::services::auth;
using namespace leshy1::ui;

WifiAuthenticationCaptureUiInput runningInput() {
    WifiAuthenticationCaptureUiInput input{};
    input.phase = WifiAuthenticationCaptureUiPhase::Running;
    input.progress.elapsedMs = 1250U;
    input.progress.durationMs = 10000U;
    input.progress.framesReported = 9U;
    input.progress.framesAccepted = 8U;
    input.progress.framesDroppedCapacity = 1U;
    input.progress.eapolFrames = 3U;
    input.progress.eapolKeyFrames = 2U;
    input.progress.channel = 6U;
    return input;
}

WifiAuthenticationCaptureUiInput transitionInput(
    WifiAuthenticationCaptureUiPhase phase) {
    WifiAuthenticationCaptureUiInput input{};
    input.phase = phase;
    return input;
}

WifiAuthenticationCaptureReport completeReport() {
    WifiAuthenticationCaptureReport report{};
    report.outcome = WifiAuthenticationCaptureOutcome::Complete;
    report.counters.sourceFrames = 4U;
    report.counters.framesRead = 4U;
    report.counters.dataFrames = 4U;
    report.counters.eapolFrames = 4U;
    report.counters.eapolKeyFrames = 4U;
    report.counters.classifiedKeyFrames = 4U;
    report.counters.captureFramesReported = 4U;
    report.counters.captureFramesAccepted = 4U;
    report.evidenceCount = 4U;
    report.peerCount = 1U;
    report.pmkidCount = 1U;
    for (std::size_t index = 0U; index < report.evidenceCount; ++index) {
        auto& evidence = report.evidence[index];
        evidence.monotonicUs = 1000000ULL +
            static_cast<std::uint64_t>(index) * 100000ULL;
        evidence.sourceFrameIndex = static_cast<std::uint16_t>(index);
        evidence.channel = 6U;
        evidence.message = static_cast<WifiEapolKeyMessage>(index + 1U);
        report.peers[0].evidenceIndices[index] =
            static_cast<std::uint8_t>(index);
    }
    report.peers[0].messageMask = 0x0fU;
    report.peers[0].authenticatorNonceSet = true;
    report.peers[0].sequenceConsistent = true;
    report.peers[0].replayCountersConsistent = true;
    report.peers[0].keyMaterialConsistent = true;
    report.peers[0].complete = true;
    report.pmkids[0].monotonicUs = 1000000ULL;
    report.pmkids[0].sourceFrameIndex = 0U;
    return report;
}

WifiAuthenticationCaptureReport incompleteReport() {
    WifiAuthenticationCaptureReport report{};
    report.outcome = WifiAuthenticationCaptureOutcome::Incomplete;
    report.counters.sourceFrames = 1U;
    report.counters.framesRead = 1U;
    report.counters.dataFrames = 1U;
    report.counters.eapolFrames = 1U;
    report.counters.eapolKeyFrames = 1U;
    report.counters.classifiedKeyFrames = 1U;
    report.counters.captureFramesReported = 1U;
    report.counters.captureFramesAccepted = 1U;
    report.evidenceCount = 1U;
    report.peerCount = 1U;
    report.evidence[0].monotonicUs = 1000000ULL;
    report.evidence[0].sourceFrameIndex = 0U;
    report.evidence[0].channel = 1U;
    report.evidence[0].message = WifiEapolKeyMessage::Message1;
    report.peers[0].messageMask = 0x01U;
    report.peers[0].evidenceIndices[0] = 0U;
    report.peers[0].authenticatorNonceSet = true;
    return report;
}

WifiAuthenticationCaptureUiInput reportInput(
    const WifiAuthenticationCaptureReport& report) {
    WifiAuthenticationCaptureUiInput input{};
    input.phase = WifiAuthenticationCaptureUiPhase::Report;
    input.report = &report;
    input.cleanupComplete = true;
    return input;
}

void testRunningUsesFourStableBoundedMetrics() {
    const WifiAuthenticationCaptureUiModel model =
        presentWifiAuthenticationCapture(runningInput());
    CHECK(model.view == WifiAuthenticationCaptureUiView::Running);
    CHECK(model.title == UiTextId::CaptureRunning);
    CHECK(model.headline == UiTextId::CaptureRecordingUser);
    CHECK(model.note == UiTextId::RunningPassive);
    CHECK(model.tone == WifiAuthenticationCaptureUiTone::Neutral);
    CHECK(model.rowCount == 4U);
    CHECK(model.rows[0].metric ==
          WifiAuthenticationCaptureUiMetric::TimeProgressMs);
    CHECK(model.rows[0].text == UiTextId::WifiAuthTimeFormat);
    CHECK(model.rows[0].primary == 8750U);
    CHECK(model.rows[0].secondary == 10000U);
    CHECK(model.rows[1].metric ==
          WifiAuthenticationCaptureUiMetric::ChannelAndReportedFrames);
    CHECK(model.rows[1].text == UiTextId::WifiAuthChannelFramesFormat);
    CHECK(model.rows[1].primary == 6U);
    CHECK(model.rows[1].secondary == 9U);
    CHECK(model.rows[2].metric ==
          WifiAuthenticationCaptureUiMetric::RetainedAndDroppedFrames);
    CHECK(model.rows[2].text == UiTextId::WifiAuthKeptLostFormat);
    CHECK(model.rows[2].primary == 8U);
    CHECK(model.rows[2].secondary == 1U);
    CHECK(model.rows[2].warning);
    CHECK(model.rows[3].metric ==
          WifiAuthenticationCaptureUiMetric::EapolAndKeyFrames);
    CHECK(model.rows[3].text == UiTextId::WifiAuthEapolKeysFormat);
    CHECK(model.rows[3].primary == 3U);
    CHECK(model.rows[3].secondary == 2U);
    CHECK(!model.reportOpenable);
    CHECK(!model.cleanupComplete);
}

void testPreparingDoesNotClaimReceiverIsRunning() {
    const auto model = presentWifiAuthenticationCapture(
        transitionInput(WifiAuthenticationCaptureUiPhase::Preparing));
    CHECK(model.view == WifiAuthenticationCaptureUiView::Preparing);
    CHECK(model.title == UiTextId::WifiAuthPreparingTitle);
    CHECK(model.headline == UiTextId::WifiAuthPreparingHeadline);
    CHECK(model.note == UiTextId::WifiAuthPreparingNote);
    CHECK(model.tone == WifiAuthenticationCaptureUiTone::Neutral);
    CHECK(model.rowCount == 0U);
    CHECK(!model.reportOpenable);
    CHECK(!model.cleanupComplete);
}

void testCancellingDoesNotClaimCleanupIsComplete() {
    const auto model = presentWifiAuthenticationCapture(
        transitionInput(WifiAuthenticationCaptureUiPhase::Cancelling));
    CHECK(model.view == WifiAuthenticationCaptureUiView::Cancelling);
    CHECK(model.title == UiTextId::WifiAuthCancellingTitle);
    CHECK(model.headline == UiTextId::WifiAuthCancellingHeadline);
    CHECK(model.note == UiTextId::WifiAuthCancellingNote);
    CHECK(model.tone == WifiAuthenticationCaptureUiTone::Caution);
    CHECK(model.rowCount == 0U);
    CHECK(!model.reportOpenable);
    CHECK(!model.cleanupComplete);
}

void testTransitionStateRejectsInventedLiveProgress() {
    WifiAuthenticationCaptureUiInput input =
        transitionInput(WifiAuthenticationCaptureUiPhase::Preparing);
    input.progress.channel = 6U;
    const auto model = presentWifiAuthenticationCapture(input);
    CHECK(model.view == WifiAuthenticationCaptureUiView::Failed);
    CHECK(model.failure ==
          WifiAuthenticationCaptureUiFailure::InvalidPresentationInput);
}

void testRunningTimerRepaintsOnlyOneRowWithoutClearing() {
    WifiAuthenticationCaptureUiInput first = runningInput();
    WifiAuthenticationCaptureUiInput second = first;
    second.progress.elapsedMs = 1350U;
    const auto previous = presentWifiAuthenticationCapture(first);
    const auto current = presentWifiAuthenticationCapture(second);
    const auto delta = diffWifiAuthenticationCaptureUi(previous, current);
    CHECK(delta.any());
    CHECK(delta.fixedRegionMask == 0U);
    CHECK(delta.rowMask == 0x01U);
    CHECK(!delta.fullScreenClear);
}

void testCompleteResultShowsHandshakePmkidAndEvidenceCounts() {
    const WifiAuthenticationCaptureReport report = completeReport();
    const auto model = presentWifiAuthenticationCapture(reportInput(report));
    CHECK(model.view == WifiAuthenticationCaptureUiView::Result);
    CHECK(model.title == UiTextId::CaptureResult);
    CHECK(model.headline == UiTextId::CaptureResult);
    CHECK(model.note == UiTextId::AirspaceGuardResultAfterCleanup);
    CHECK(model.tone == WifiAuthenticationCaptureUiTone::Positive);
    CHECK(!model.evidenceIncomplete);
    CHECK(!model.reportOpenable);
    CHECK(model.cleanupComplete);
    CHECK(model.rows[0].metric ==
          WifiAuthenticationCaptureUiMetric::CompleteAndPartialPeers);
    CHECK(model.rows[0].text == UiTextId::WifiAuthPeersFormat);
    CHECK(model.rows[0].primary == 1U);
    CHECK(model.rows[0].secondary == 0U);
    CHECK(model.rows[1].metric ==
          WifiAuthenticationCaptureUiMetric::EapolKeysAndPmkids);
    CHECK(model.rows[1].text == UiTextId::WifiAuthKeysPmkidFormat);
    CHECK(model.rows[1].primary == 4U);
    CHECK(model.rows[1].secondary == 1U);
    CHECK(model.rows[2].metric ==
          WifiAuthenticationCaptureUiMetric::EvidenceAndSourceFrames);
    CHECK(model.rows[2].text == UiTextId::WifiAuthEvidenceFormat);
    CHECK(model.rows[2].primary == 4U);
    CHECK(model.rows[2].secondary == 4U);
    CHECK(model.rows[3].primary == 0U);
    CHECK(model.rows[3].secondary == 0U);
    CHECK(!model.rows[3].warning);
}

void testIncompleteHandshakeIsAResultNotMissingEvidence() {
    const WifiAuthenticationCaptureReport report = incompleteReport();
    const auto model = presentWifiAuthenticationCapture(reportInput(report));
    CHECK(model.view == WifiAuthenticationCaptureUiView::Result);
    CHECK(model.tone == WifiAuthenticationCaptureUiTone::Caution);
    CHECK(!model.evidenceIncomplete);
    CHECK(model.note == UiTextId::AirspaceGuardPassiveOnly);
    CHECK(model.rows[0].primary == 0U);
    CHECK(model.rows[0].secondary == 1U);
    CHECK(!model.reportOpenable);
}

void testLossIsInconclusiveAndShowsExactUncertainty() {
    WifiAuthenticationCaptureReport report = incompleteReport();
    report.outcome = WifiAuthenticationCaptureOutcome::Inconclusive;
    report.uncertainty = static_cast<std::uint16_t>(
        WifiAuthenticationUncertaintyCaptureLoss);
    report.counters.captureFramesReported = 3U;
    report.counters.captureFramesDroppedCapacity = 2U;
    const auto model = presentWifiAuthenticationCapture(reportInput(report));
    CHECK(model.view == WifiAuthenticationCaptureUiView::Inconclusive);
    CHECK(model.headline == UiTextId::AirspaceGuardInconclusive);
    CHECK(model.note == UiTextId::AirspaceGuardEvidenceIncomplete);
    CHECK(model.tone == WifiAuthenticationCaptureUiTone::Caution);
    CHECK(model.evidenceIncomplete);
    CHECK(!model.reportOpenable);
    CHECK(model.rows[2].metric ==
          WifiAuthenticationCaptureUiMetric::LossAndRejectedFrames);
    CHECK(model.rows[2].text == UiTextId::WifiAuthLossFormat);
    CHECK(model.rows[2].primary == 2U);
    CHECK(model.rows[2].warning);
    CHECK(model.rows[3].metric ==
          WifiAuthenticationCaptureUiMetric::UncertaintyMask);
    CHECK(model.rows[3].text == UiTextId::WifiAuthReasonLoss);
    CHECK(model.rows[3].primary == static_cast<std::uint32_t>(
              WifiAuthenticationUncertaintyCaptureLoss));
}

void testResultBeforeCleanupFailsClosed() {
    const WifiAuthenticationCaptureReport report = completeReport();
    WifiAuthenticationCaptureUiInput input = reportInput(report);
    input.cleanupComplete = false;
    const auto model = presentWifiAuthenticationCapture(input);
    CHECK(model.view == WifiAuthenticationCaptureUiView::Failed);
    CHECK(model.failure ==
          WifiAuthenticationCaptureUiFailure::ResultBeforeCleanup);
    CHECK(!model.cleanupComplete);
    CHECK(model.note == UiTextId::AirspaceGuardEvidenceIncomplete);
    CHECK(model.rows[0].text == UiTextId::WifiAuthFailureCleanup);
    CHECK(!model.reportOpenable);
}

void testMalformedReportIsRejectedWithoutPublishingMetrics() {
    WifiAuthenticationCaptureReport report = completeReport();
    report.peers[0].complete = false;
    const auto model = presentWifiAuthenticationCapture(reportInput(report));
    CHECK(model.view == WifiAuthenticationCaptureUiView::Failed);
    CHECK(model.failure ==
          WifiAuthenticationCaptureUiFailure::ReportRejected);
    CHECK(model.rowCount == 1U);
    CHECK(model.rows[0].metric ==
          WifiAuthenticationCaptureUiMetric::FailureCode);
    CHECK(model.rows[0].text == UiTextId::WifiAuthFailureReport);
    CHECK(!model.reportOpenable);
}

void testInvalidRunningAccountingFailsClosed() {
    WifiAuthenticationCaptureUiInput input = runningInput();
    input.progress.framesReported = 8U;
    const auto model = presentWifiAuthenticationCapture(input);
    CHECK(model.view == WifiAuthenticationCaptureUiView::Failed);
    CHECK(model.failure ==
          WifiAuthenticationCaptureUiFailure::InvalidPresentationInput);
    CHECK(model.rows[0].text == UiTextId::WifiAuthFailureInvalid);
}

void testFailureDistinguishesCleanupWithoutInventingRelease() {
    WifiAuthenticationCaptureUiInput input{};
    input.phase = WifiAuthenticationCaptureUiPhase::Failed;
    input.failure = WifiAuthenticationCaptureUiFailure::RuntimeFailed;
    auto model = presentWifiAuthenticationCapture(input);
    CHECK(model.view == WifiAuthenticationCaptureUiView::Failed);
    CHECK(model.note == UiTextId::AirspaceGuardEvidenceIncomplete);
    CHECK(model.rows[0].text == UiTextId::WifiAuthFailureRuntime);
    CHECK(!model.cleanupComplete);
    input.cleanupComplete = true;
    model = presentWifiAuthenticationCapture(input);
    CHECK(model.note == UiTextId::CaptureFailureNote);
    CHECK(model.cleanupComplete);
}

void testStartFailureUsesAUserFacingMessage() {
    WifiAuthenticationCaptureUiInput input{};
    input.phase = WifiAuthenticationCaptureUiPhase::Failed;
    input.failure = WifiAuthenticationCaptureUiFailure::StartFailed;
    input.cleanupComplete = true;
    const auto model = presentWifiAuthenticationCapture(input);
    CHECK(model.view == WifiAuthenticationCaptureUiView::Failed);
    CHECK(model.rows[0].text == UiTextId::WifiAuthFailureStart);
    CHECK(model.cleanupComplete);
}

void testViewTransitionStillForbidsFullScreenClear() {
    const auto running = presentWifiAuthenticationCapture(runningInput());
    const WifiAuthenticationCaptureReport report = completeReport();
    const auto result = presentWifiAuthenticationCapture(reportInput(report));
    const auto delta = diffWifiAuthenticationCaptureUi(running, result);
    CHECK(delta.fixedRegionMask != 0U);
    CHECK(delta.rowMask == 0x0fU);
    CHECK(!delta.fullScreenClear);
}

void testPreparingAndCancellingTransitionsStayIncremental() {
    const auto preparing = presentWifiAuthenticationCapture(
        transitionInput(WifiAuthenticationCaptureUiPhase::Preparing));
    const auto cancelling = presentWifiAuthenticationCapture(
        transitionInput(WifiAuthenticationCaptureUiPhase::Cancelling));
    const auto cancelled = diffWifiAuthenticationCaptureUi(
        preparing, cancelling);
    CHECK(cancelled.fixedRegionMask != 0U);
    CHECK(cancelled.rowMask == 0U);
    CHECK(!cancelled.fullScreenClear);

    const auto running = presentWifiAuthenticationCapture(runningInput());
    const auto started = diffWifiAuthenticationCaptureUi(preparing, running);
    CHECK(started.fixedRegionMask != 0U);
    CHECK(started.rowMask == 0x0fU);
    CHECK(!started.fullScreenClear);
}

void testIdenticalModelsNeedNoRepaint() {
    const auto model = presentWifiAuthenticationCapture(runningInput());
    const auto delta = diffWifiAuthenticationCaptureUi(model, model);
    CHECK(!delta.any());
    CHECK(!delta.fullScreenClear);
}

static_assert(std::is_trivially_copyable_v<WifiAuthenticationCaptureUiModel>);
static_assert(sizeof(WifiAuthenticationCaptureUiModel) <= 128U);

}  // namespace

int main() {
    testRunningUsesFourStableBoundedMetrics();
    testPreparingDoesNotClaimReceiverIsRunning();
    testCancellingDoesNotClaimCleanupIsComplete();
    testTransitionStateRejectsInventedLiveProgress();
    testRunningTimerRepaintsOnlyOneRowWithoutClearing();
    testCompleteResultShowsHandshakePmkidAndEvidenceCounts();
    testIncompleteHandshakeIsAResultNotMissingEvidence();
    testLossIsInconclusiveAndShowsExactUncertainty();
    testResultBeforeCleanupFailsClosed();
    testMalformedReportIsRejectedWithoutPublishingMetrics();
    testInvalidRunningAccountingFailsClosed();
    testFailureDistinguishesCleanupWithoutInventingRelease();
    testStartFailureUsesAUserFacingMessage();
    testViewTransitionStillForbidsFullScreenClear();
    testPreparingAndCancellingTransitionsStayIncremental();
    testIdenticalModelsNeedNoRepaint();
    std::puts("Wi-Fi authentication capture presenter tests passed");
    return 0;
}
