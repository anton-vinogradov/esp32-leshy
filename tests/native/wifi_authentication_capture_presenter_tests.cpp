#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <type_traits>

#include "apps/auth/WifiAuthenticationCaptureController.h"
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

using namespace leshy1::apps::auth;
using namespace leshy1::services::auth;
using namespace leshy1::ui;

WifiAuthenticationCaptureUiInput runningInput() {
    WifiAuthenticationCaptureUiInput input{};
    input.phase = WifiAuthenticationCaptureUiPhase::Running;
    input.progress.elapsedMs = 1250U;
    input.progress.durationMs = 10000U;
    input.progress.framesReported = 9U;
    input.progress.candidateFrames = 9U;
    input.progress.framesAccepted = 8U;
    input.progress.framesDroppedCapacity = 1U;
    input.progress.channel = 6U;
    return input;
}

WifiAuthenticationCaptureUiInput transitionInput(
    WifiAuthenticationCaptureUiPhase phase) {
    WifiAuthenticationCaptureUiInput input{};
    input.phase = phase;
    return input;
}

void setEvidence(WifiAuthenticationCaptureReport& report, std::size_t index,
                 WifiEapolKeyMessage message, std::uint16_t sourceFrame) {
    auto& evidence = report.evidence[index];
    evidence.monotonicUs = 1000000ULL +
        static_cast<std::uint64_t>(sourceFrame) * 100000ULL;
    evidence.sourceFrameIndex = static_cast<std::uint8_t>(sourceFrame);
    evidence.channel = 6U;
    evidence.rssiDbm = static_cast<std::int16_t>(
        -42 - static_cast<std::int16_t>(index));
    evidence.message = message;
    evidence.eapolVersion = 2U;
    evidence.descriptorType = 2U;
    evidence.descriptorVersion = 2U;
    evidence.replayCounter = 700U + index;
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
        setEvidence(report, index,
                    static_cast<WifiEapolKeyMessage>(index + 1U),
                    static_cast<std::uint16_t>(index));
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

WifiAuthenticationCaptureReport partialReport() {
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
    setEvidence(report, 0U, WifiEapolKeyMessage::Message1, 0U);
    report.peers[0].messageMask = 0x01U;
    report.peers[0].evidenceIndices[0] = 0U;
    report.peers[0].authenticatorNonceSet = true;
    return report;
}

WifiAuthenticationCaptureReport multiPeerReport() {
    WifiAuthenticationCaptureReport report = completeReport();
    report.peerCount = 2U;
    report.peers[1].messageMask = 0x01U;
    report.peers[1].authenticatorNonceSet = true;
    report.peers[1].evidenceIndices[0] = 0U;
    return report;
}

WifiAuthenticationCaptureReport pmkidM1Report() {
    WifiAuthenticationCaptureReport report = partialReport();
    report.pmkidCount = 1U;
    report.pmkids[0].monotonicUs = report.evidence[0].monotonicUs;
    report.pmkids[0].sourceFrameIndex = 0U;
    return report;
}

WifiAuthenticationCaptureReport pmkidWithZeroMaskPeerReport() {
    WifiAuthenticationCaptureReport report = pmkidM1Report();
    report.peers[0].messageMask = 0U;
    report.peers[0].authenticatorNonceSet = false;
    report.peers[0].evidenceIndices[0] =
        WifiAuthenticationPeer::kMissingEvidence;
    return report;
}

WifiAuthenticationCaptureUiInput reportInput(
    const WifiAuthenticationCaptureReport& report,
    const WifiAuthenticationCaptureController& controller) {
    WifiAuthenticationCaptureUiInput input{};
    input.phase = WifiAuthenticationCaptureUiPhase::Report;
    input.report = &report;
    input.controller = &controller;
    input.cleanupComplete = true;
    return input;
}

void testRunningUsesHonestCandidateMetrics() {
    const auto model = presentWifiAuthenticationCapture(runningInput());
    CHECK(model.view == WifiAuthenticationCaptureUiView::Running);
    CHECK(model.rowCount == 4U);
    CHECK(model.rows[0].metric ==
          WifiAuthenticationCaptureUiMetric::TimeRemainingSeconds);
    CHECK(model.rows[0].primary == 9U);
    CHECK(model.rows[1].metric ==
          WifiAuthenticationCaptureUiMetric::ChannelAndCandidateFrames);
    CHECK(model.rows[1].secondary == 9U);
    CHECK(model.rows[2].metric ==
          WifiAuthenticationCaptureUiMetric::RetainedAndDroppedFrames);
    CHECK(model.rows[2].primary == 8U);
    CHECK(model.rows[2].secondary == 1U);
    CHECK(model.rows[2].warning);
    CHECK(model.rows[3].metric ==
          WifiAuthenticationCaptureUiMetric::TerminalAnalysisPending);
    CHECK(model.rows[3].text == UiTextId::WifiAuthExactAfterStop);
    CHECK(!model.reportOpenable);
}

void testPreparingAndCancellingAreHonest() {
    const auto preparing = presentWifiAuthenticationCapture(
        transitionInput(WifiAuthenticationCaptureUiPhase::Preparing));
    CHECK(preparing.view == WifiAuthenticationCaptureUiView::Preparing);
    CHECK(preparing.note == UiTextId::WifiAuthPreparingNote);
    CHECK(!preparing.cleanupComplete);
    const auto cancelling = presentWifiAuthenticationCapture(
        transitionInput(WifiAuthenticationCaptureUiPhase::Cancelling));
    CHECK(cancelling.view == WifiAuthenticationCaptureUiView::Cancelling);
    CHECK(cancelling.note == UiTextId::WifiAuthCancellingNote);
    CHECK(!cancelling.cleanupComplete);
}

void testRunningTimerRepaintsOnlyOneRowWithoutClearing() {
    auto second = runningInput();
    second.progress.elapsedMs = 2250U;
    const auto delta = diffWifiAuthenticationCaptureUi(
        presentWifiAuthenticationCapture(runningInput()),
        presentWifiAuthenticationCapture(second));
    CHECK(delta.fixedRegionMask == 0U);
    CHECK(delta.rowMask == 0x01U);
    CHECK(!delta.fullScreenClear);
}

void testHeadlinePriorityAndIndependentCounts() {
    WifiAuthenticationCaptureReport full = completeReport();
    WifiAuthenticationCaptureController fullController;
    CHECK(fullController.load(full) ==
          WifiAuthenticationCaptureLoadStatus::Ready);
    const auto fullModel = presentWifiAuthenticationCapture(
        reportInput(full, fullController));
    CHECK(fullModel.headline == UiTextId::WifiAuthFullHandshakeHeadline);
    CHECK(fullModel.rows[0].primary == 1U);
    CHECK(fullModel.rows[0].secondary == 0U);
    CHECK(fullModel.rows[1].primary == 1U);
    CHECK(fullModel.rows[1].secondary == 4U);
    CHECK(fullModel.rows[2].primary == 0x0fU);
    CHECK(fullModel.reportOpenable);
    CHECK(fullModel.exportEligibility ==
          WifiAuthenticationCaptureExportEligibility::NotEvaluated);

    WifiAuthenticationCaptureReport partial = partialReport();
    WifiAuthenticationCaptureController partialController;
    CHECK(partialController.load(partial) ==
          WifiAuthenticationCaptureLoadStatus::Ready);
    const auto partialModel = presentWifiAuthenticationCapture(
        reportInput(partial, partialController));
    CHECK(partialModel.headline ==
          UiTextId::WifiAuthPartialHandshakeHeadline);
    CHECK(partialModel.rows[0].primary == 0U);
    CHECK(partialModel.rows[0].secondary == 1U);

    WifiAuthenticationCaptureReport pmkid = pmkidM1Report();
    WifiAuthenticationCaptureController pmkidController;
    CHECK(pmkidController.load(pmkid) ==
          WifiAuthenticationCaptureLoadStatus::Ready);
    const auto pmkidModel = presentWifiAuthenticationCapture(
        reportInput(pmkid, pmkidController));
    CHECK(pmkidModel.headline == UiTextId::WifiAuthPmkidHeadline);
    CHECK(pmkidModel.rows[0].primary == 0U);
    CHECK(pmkidModel.rows[0].secondary == 1U);
    CHECK(pmkidModel.rows[1].primary == 1U);
    CHECK(pmkidModel.rows[1].secondary == 1U);

    WifiAuthenticationCaptureReport zeroMask =
        pmkidWithZeroMaskPeerReport();
    WifiAuthenticationCaptureController zeroMaskController;
    CHECK(zeroMaskController.load(zeroMask) ==
          WifiAuthenticationCaptureLoadStatus::Ready);
    const auto zeroMaskModel = presentWifiAuthenticationCapture(
        reportInput(zeroMask, zeroMaskController));
    CHECK(zeroMaskModel.headline == UiTextId::WifiAuthPmkidHeadline);
    CHECK(zeroMaskModel.rows[0].secondary == 0U);
    CHECK(zeroMaskModel.rows[2].metric ==
          WifiAuthenticationCaptureUiMetric::EvidenceAndSourceFrames);
}

void testInconclusiveShowsExactReason() {
    WifiAuthenticationCaptureReport report = partialReport();
    report.outcome = WifiAuthenticationCaptureOutcome::Inconclusive;
    report.uncertainty = WifiAuthenticationUncertaintyCaptureLoss;
    report.counters.captureFramesReported = 2U;
    report.counters.captureFramesDroppedCapacity = 1U;
    WifiAuthenticationCaptureController controller;
    CHECK(controller.load(report) ==
          WifiAuthenticationCaptureLoadStatus::Ready);
    const auto model = presentWifiAuthenticationCapture(
        reportInput(report, controller));
    CHECK(model.headline == UiTextId::WifiAuthInconclusiveHeadline);
    CHECK(model.evidenceIncomplete);
    CHECK(model.rows[3].metric ==
          WifiAuthenticationCaptureUiMetric::UncertaintyMask);
    CHECK(model.rows[3].text == UiTextId::WifiAuthReasonLoss);
    CHECK(model.rows[3].primary == WifiAuthenticationUncertaintyCaptureLoss);
}

void testResultActionsPeerAndEvidenceDrilldown() {
    WifiAuthenticationCaptureReport report = completeReport();
    WifiAuthenticationCaptureController controller;
    CHECK(controller.load(report) ==
          WifiAuthenticationCaptureLoadStatus::Ready);
    const auto outcome = presentWifiAuthenticationCapture(
        reportInput(report, controller));
    CHECK(controller.openSelected());
    const auto actions = presentWifiAuthenticationCapture(
        reportInput(report, controller));
    CHECK(actions.view == WifiAuthenticationCaptureUiView::Actions);
    CHECK(actions.title == UiTextId::WifiAuthActionsHeadline);
    const auto outcomeToActions = diffWifiAuthenticationCaptureUi(
        outcome, actions);
    CHECK((outcomeToActions.fixedRegionMask &
           kWifiAuthenticationTitleRegion) != 0U);
    CHECK(!outcomeToActions.fullScreenClear);
    CHECK(actions.rowCount == 2U);
    CHECK(actions.rows[0].selected);
    CHECK(actions.rows[0].metric ==
          WifiAuthenticationCaptureUiMetric::ActionDetails);
    CHECK(controller.next());
    const auto actionsNext = presentWifiAuthenticationCapture(
        reportInput(report, controller));
    const auto actionDelta = diffWifiAuthenticationCaptureUi(
        actions, actionsNext);
    CHECK(actionDelta.fixedRegionMask == 0U);
    CHECK(actionDelta.rowMask == 0x03U);
    CHECK(!actionDelta.fullScreenClear);
    CHECK(controller.previous());
    CHECK(controller.openSelected());
    const auto peer = presentWifiAuthenticationCapture(
        reportInput(report, controller));
    CHECK(peer.view == WifiAuthenticationCaptureUiView::PeerDetail);
    CHECK(peer.rows[1].metric ==
          WifiAuthenticationCaptureUiMetric::PeerMessageMask);
    CHECK(peer.rows[1].primary == 0x0fU);
    CHECK(controller.openSelected());
    const auto evidence = presentWifiAuthenticationCapture(
        reportInput(report, controller));
    CHECK(evidence.view == WifiAuthenticationCaptureUiView::EvidenceList);
    CHECK(evidence.rows[0].selected);
    CHECK(evidence.rows[0].metric ==
          WifiAuthenticationCaptureUiMetric::EvidenceListRow);
    CHECK(controller.openSelected());
    const auto detail = presentWifiAuthenticationCapture(
        reportInput(report, controller));
    CHECK(detail.view == WifiAuthenticationCaptureUiView::EvidenceDetail);
    CHECK(detail.rows[0].metric ==
          WifiAuthenticationCaptureUiMetric::EvidenceMessageAndFrame);
    CHECK(detail.rows[2].exact == 700U);
}

void testPeerToneChangeRepaintsColoredRegionsWithoutClearing() {
    WifiAuthenticationCaptureReport report = multiPeerReport();
    WifiAuthenticationCaptureController controller;
    CHECK(controller.load(report) ==
          WifiAuthenticationCaptureLoadStatus::Ready);
    CHECK(controller.openSelected());
    CHECK(controller.openSelected());
    const auto completePeer = presentWifiAuthenticationCapture(
        reportInput(report, controller));
    CHECK(completePeer.tone == WifiAuthenticationCaptureUiTone::Positive);
    CHECK(controller.next());
    const auto partialPeer = presentWifiAuthenticationCapture(
        reportInput(report, controller));
    CHECK(partialPeer.tone == WifiAuthenticationCaptureUiTone::Caution);
    const auto delta = diffWifiAuthenticationCaptureUi(
        completePeer, partialPeer);
    CHECK((delta.fixedRegionMask &
           kWifiAuthenticationHeadlineRegion) != 0U);
    CHECK(delta.rowMask == 0x0fU);
    CHECK(!delta.fullScreenClear);
}

void testSyntheticHilReportIsVisiblyAndStructurallyDistinct() {
    WifiAuthenticationCaptureReport report = completeReport();
    WifiAuthenticationCaptureController controller;
    CHECK(controller.load(report) ==
          WifiAuthenticationCaptureLoadStatus::Ready);
    const auto ambient = presentWifiAuthenticationCapture(
        reportInput(report, controller));
    auto syntheticInput = reportInput(report, controller);
    syntheticInput.synthetic = true;
    const auto synthetic = presentWifiAuthenticationCapture(syntheticInput);
    CHECK(!ambient.synthetic);
    CHECK(synthetic.synthetic);
    CHECK(ambient.note == UiTextId::WifiAuthVolatileNote);
    CHECK(synthetic.note == UiTextId::SimulatedData);
    const auto delta = diffWifiAuthenticationCaptureUi(ambient, synthetic);
    CHECK((delta.fixedRegionMask & kWifiAuthenticationNoteRegion) != 0U);
    CHECK(!delta.fullScreenClear);

    auto invalidRunning = runningInput();
    invalidRunning.synthetic = true;
    CHECK(presentWifiAuthenticationCapture(invalidRunning).failure ==
          WifiAuthenticationCaptureUiFailure::InvalidPresentationInput);
}

void testFailClosedInputs() {
    auto invalidRunning = runningInput();
    invalidRunning.progress.framesReported = 8U;
    CHECK(presentWifiAuthenticationCapture(invalidRunning).failure ==
          WifiAuthenticationCaptureUiFailure::InvalidPresentationInput);

    WifiAuthenticationCaptureReport report = partialReport();
    WifiAuthenticationCaptureController controller;
    CHECK(controller.load(report) ==
          WifiAuthenticationCaptureLoadStatus::Ready);
    auto early = reportInput(report, controller);
    early.cleanupComplete = false;
    CHECK(presentWifiAuthenticationCapture(early).failure ==
          WifiAuthenticationCaptureUiFailure::ResultBeforeCleanup);

    report.evidence[0].channel = 0U;
    CHECK(presentWifiAuthenticationCapture(
              reportInput(report, controller)).failure ==
          WifiAuthenticationCaptureUiFailure::ReportRejected);
}

static_assert(std::is_trivially_copyable_v<WifiAuthenticationCaptureUiModel>);
static_assert(sizeof(WifiAuthenticationCaptureUiModel) <= 192U);

}  // namespace

int main() {
    testRunningUsesHonestCandidateMetrics();
    testPreparingAndCancellingAreHonest();
    testRunningTimerRepaintsOnlyOneRowWithoutClearing();
    testHeadlinePriorityAndIndependentCounts();
    testInconclusiveShowsExactReason();
    testResultActionsPeerAndEvidenceDrilldown();
    testPeerToneChangeRepaintsColoredRegionsWithoutClearing();
    testSyntheticHilReportIsVisiblyAndStructurallyDistinct();
    testFailClosedInputs();
    std::puts("Wi-Fi authentication capture presenter tests passed");
    return 0;
}
