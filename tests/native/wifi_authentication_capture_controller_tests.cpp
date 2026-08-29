#include <cstdio>
#include <cstdlib>
#include <type_traits>

#include "apps/auth/WifiAuthenticationCaptureController.h"

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

WifiAuthenticationCaptureReport reportFixture() {
    WifiAuthenticationCaptureReport report{};
    report.outcome = WifiAuthenticationCaptureOutcome::Complete;
    report.counters.sourceFrames = 6U;
    report.counters.framesRead = 6U;
    report.counters.dataFrames = 6U;
    report.counters.eapolFrames = 6U;
    report.counters.eapolKeyFrames = 6U;
    report.counters.classifiedKeyFrames = 6U;
    report.counters.captureFramesReported = 6U;
    report.counters.captureFramesAccepted = 6U;
    report.evidenceCount = 6U;
    report.peerCount = 2U;
    report.pmkidCount = 1U;
    const std::array<std::uint16_t, 6> sourceOrder{4U, 1U, 5U, 2U, 0U, 3U};
    for (std::size_t index = 0U; index < report.evidenceCount; ++index) {
        WifiAuthenticationEvidence& evidence = report.evidence[index];
        evidence.sourceFrameIndex =
            static_cast<std::uint8_t>(sourceOrder[index]);
        evidence.monotonicUs = 1000000ULL +
            static_cast<std::uint64_t>(sourceOrder[index]) * 100000ULL;
        evidence.channel = 6U;
        evidence.rssiDbm = static_cast<std::int8_t>(-40 -
            static_cast<std::int8_t>(index));
        evidence.message = static_cast<WifiEapolKeyMessage>(
            index < 4U ? index + 1U : 1U);
    }
    WifiAuthenticationPeer& partial = report.peers[0];
    partial.messageMask = 0x03U;
    partial.sequenceConsistent = true;
    partial.evidenceIndices[0] = 0U;
    partial.evidenceIndices[1] = 1U;
    WifiAuthenticationPeer& complete = report.peers[1];
    complete.messageMask = 0x0fU;
    complete.authenticatorNonceSet = true;
    complete.sequenceConsistent = true;
    complete.replayCountersConsistent = true;
    complete.keyMaterialConsistent = true;
    complete.complete = true;
    complete.evidenceIndices = {2U, 3U, 4U, 5U};
    report.pmkids[0].sourceFrameIndex = 0U;
    report.pmkids[0].monotonicUs = 1000000ULL;
    return report;
}

void testLoadSelectsMostUsefulPeerWithoutCopyingReport() {
    WifiAuthenticationCaptureReport report = reportFixture();
    WifiAuthenticationCaptureController controller;
    CHECK(controller.load(report) ==
          WifiAuthenticationCaptureLoadStatus::Ready);
    CHECK(controller.report() == &report);
    CHECK(controller.view() == WifiAuthenticationCaptureView::Outcome);
    CHECK(controller.peerSelection() == 1U);
    CHECK(controller.selectedPeerPosition() == 1U);
    CHECK(controller.peerCount() == 2U);
    CHECK(controller.selectedPeer() == &report.peers[1]);
    CHECK(controller.reportOpenable());
    CHECK(controller.hasDetails());
}

void testResultActionsAndPeerNavigationAreBounded() {
    WifiAuthenticationCaptureReport report = reportFixture();
    WifiAuthenticationCaptureController controller;
    CHECK(controller.load(report) ==
          WifiAuthenticationCaptureLoadStatus::Ready);
    CHECK(controller.openSelected());
    CHECK(controller.view() == WifiAuthenticationCaptureView::Actions);
    CHECK(controller.actionCount() == 2U);
    CHECK(controller.selectedAction() ==
          WifiAuthenticationCaptureAction::Details);
    CHECK(!controller.previous());
    CHECK(controller.next());
    CHECK(controller.selectedAction() ==
          WifiAuthenticationCaptureAction::Repeat);
    CHECK(!controller.next());
    CHECK(controller.previous());
    CHECK(controller.openSelected());
    CHECK(controller.view() == WifiAuthenticationCaptureView::PeerDetail);
    CHECK(controller.peerSelection() == 1U);
    CHECK(controller.previous());
    CHECK(controller.peerSelection() == 0U);
    CHECK(controller.next());
    CHECK(controller.peerSelection() == 1U);
    CHECK(!controller.next());
}

void testEvidenceOrderIsStableAndBackRestoresEveryLevel() {
    WifiAuthenticationCaptureReport report = reportFixture();
    WifiAuthenticationCaptureController controller;
    CHECK(controller.load(report) ==
          WifiAuthenticationCaptureLoadStatus::Ready);
    CHECK(controller.openSelected());
    CHECK(controller.openSelected());
    CHECK(controller.openSelected());
    CHECK(controller.view() == WifiAuthenticationCaptureView::EvidenceList);
    CHECK(controller.selectedEvidence()->sourceFrameIndex == 0U);
    CHECK(controller.selectedEvidenceReportIndex() == 4U);
    CHECK(controller.selectedEvidenceHasPmkid());
    CHECK(controller.next());
    CHECK(controller.selectedEvidence()->sourceFrameIndex == 1U);
    CHECK(!controller.selectedEvidenceHasPmkid());
    CHECK(controller.openSelected());
    CHECK(controller.view() ==
          WifiAuthenticationCaptureView::EvidenceDetail);
    CHECK(controller.back());
    CHECK(controller.view() == WifiAuthenticationCaptureView::EvidenceList);
    CHECK(controller.back());
    CHECK(controller.view() == WifiAuthenticationCaptureView::PeerDetail);
    CHECK(controller.back());
    CHECK(controller.view() == WifiAuthenticationCaptureView::Actions);
    CHECK(controller.back());
    CHECK(controller.view() == WifiAuthenticationCaptureView::Outcome);
    CHECK(!controller.back());
}

void testNoEvidenceReportOpensActionsButCannotInventDetails() {
    WifiAuthenticationCaptureReport report{};
    report.outcome = WifiAuthenticationCaptureOutcome::Inconclusive;
    report.uncertainty = static_cast<std::uint16_t>(
        WifiAuthenticationUncertaintyNoEvidence);
    WifiAuthenticationCaptureController controller;
    CHECK(controller.load(report) ==
          WifiAuthenticationCaptureLoadStatus::Ready);
    CHECK(controller.reportOpenable());
    CHECK(!controller.hasDetails());
    CHECK(controller.openSelected());
    CHECK(controller.actionCount() == 1U);
    CHECK(controller.selectedAction() ==
          WifiAuthenticationCaptureAction::Repeat);
    CHECK(!controller.openSelected());
}

void testZeroMaskPeerIsNotPresentedAsHandshakePeer() {
    WifiAuthenticationCaptureReport report{};
    report.outcome = WifiAuthenticationCaptureOutcome::Incomplete;
    report.counters.sourceFrames = 1U;
    report.evidenceCount = 1U;
    report.peerCount = 1U;
    report.evidence[0].sourceFrameIndex = 0U;
    report.evidence[0].monotonicUs = 1U;
    report.evidence[0].channel = 6U;
    report.peers[0].messageMask = 0U;
    WifiAuthenticationCaptureController controller;
    CHECK(controller.load(report) ==
          WifiAuthenticationCaptureLoadStatus::Ready);
    CHECK(controller.peerCount() == 0U);
    CHECK(controller.selectedPeer() == nullptr);
    CHECK(controller.openSelected());
    CHECK(controller.view() == WifiAuthenticationCaptureView::Actions);
    CHECK(controller.openSelected());
    CHECK(controller.view() == WifiAuthenticationCaptureView::EvidenceList);
}

void testInvalidReportsFailClosed() {
    WifiAuthenticationCaptureReport report = reportFixture();
    report.peers[1].evidenceIndices[3] = 99U;
    WifiAuthenticationCaptureController controller;
    CHECK(controller.load(report) ==
          WifiAuthenticationCaptureLoadStatus::InvalidReport);
    CHECK(!controller.ready());
    CHECK(controller.report() == nullptr);
    CHECK(!controller.openSelected());

    report = reportFixture();
    report.outcome = WifiAuthenticationCaptureOutcome::Incomplete;
    CHECK(controller.load(report) ==
          WifiAuthenticationCaptureLoadStatus::InvalidReport);
}

static_assert(
    std::is_trivially_copyable_v<WifiAuthenticationCaptureController>);
static_assert(sizeof(WifiAuthenticationCaptureController) <= 64U);

}  // namespace

int main() {
    testLoadSelectsMostUsefulPeerWithoutCopyingReport();
    testResultActionsAndPeerNavigationAreBounded();
    testEvidenceOrderIsStableAndBackRestoresEveryLevel();
    testNoEvidenceReportOpensActionsButCannotInventDetails();
    testZeroMaskPeerIsNotPresentedAsHandshakePeer();
    testInvalidReportsFailClosed();
    std::puts("Wi-Fi authentication capture controller tests passed");
    return 0;
}
