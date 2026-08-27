#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "ui/AirspaceGuardPresenter.h"

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__,      \
                         __LINE__, #condition);                                 \
            std::abort();                                                       \
        }                                                                       \
    } while (false)

namespace {

using namespace leshy1::apps::guard;
using namespace leshy1::services::guard;
using namespace leshy1::ui;

constexpr std::array<std::uint8_t, 6> kSource{
    0x02, 0x11, 0x22, 0x33, 0x44, 0x55};

AirspaceGuardReport makeFindingReport(std::size_t evidenceCount = 6U) {
    AirspaceGuardReport report{};
    report.status = AirspaceGuardStatus::Finding;
    report.findingCount = 1;
    report.sourceFramesObserved = 20;
    report.framesAvailable = 20;
    report.framesInspected = 20;
    report.disconnectFrames = 6;
    AirspaceFinding& finding = report.findings[0];
    finding.confidence = AirspaceConfidence::High;
    finding.detectorVersion = AirspaceFinding::kDetectorVersion;
    finding.threshold = 4;
    finding.observed = 6;
    finding.deauthenticationFrames = 4;
    finding.disassociationFrames = 2;
    finding.transmitter = kSource;
    finding.firstUs = 1000000ULL;
    finding.lastUs = 1600000ULL;
    finding.evidenceCount = evidenceCount;
    for (std::size_t index = 0; index < evidenceCount; ++index) {
        AirspaceEvidenceRef& evidence = finding.evidence[index];
        evidence.frameIndex = 10U + index;
        evidence.monotonicUs = 1000000ULL + 100000ULL * index;
        evidence.channel = static_cast<std::uint8_t>(1U + index);
        evidence.rssiDbm = static_cast<std::int16_t>(-40 - index);
    }
    return report;
}

void testFindingShowsOnlyActionableUserFacts() {
    AirspaceGuardController controller;
    CHECK(controller.load(makeFindingReport()) ==
          AirspaceGuardLoadStatus::Ready);
    const AirspaceGuardUiModel model =
        presentAirspaceGuard(controller, UiLanguage::English);
    CHECK(model.headline == UiTextId::AirspaceGuardFinding);
    CHECK(model.tone == AirspaceGuardUiTone::Finding);
    CHECK(model.openable);
    CHECK(model.rowCount == 4);
    CHECK(std::strcmp(model.context.data(),
                      "MAC 02:11:22:33:44:55") == 0);
    CHECK(std::strcmp(model.rows[0].text.data(), "FINDING 1 OF 1") == 0);
    CHECK(std::strcmp(model.rows[1].text.data(),
                      "HIGH · DETECTOR V1") == 0);
    CHECK(std::strcmp(model.rows[2].text.data(),
                      "6 EVENTS · LIMIT 4") == 0);
    CHECK(std::strcmp(model.rows[3].text.data(),
                      "DEAUTH 4 · DISASSOC 2") == 0);
}

void testEvidenceListUsesFourStableTouchRows() {
    AirspaceGuardController controller;
    CHECK(controller.load(makeFindingReport()) ==
          AirspaceGuardLoadStatus::Ready);
    CHECK(controller.openSelected());
    for (std::size_t index = 0; index < 5; ++index) CHECK(controller.next());
    const AirspaceGuardUiModel model =
        presentAirspaceGuard(controller, UiLanguage::English);
    CHECK(model.headline == UiTextId::AirspaceGuardEvidenceTitle);
    CHECK(model.openable);
    CHECK(model.rowCount == 4);
    CHECK(std::strcmp(model.rows[0].text.data(), "#12 · CH 3 · -42 DBM") == 0);
    CHECK(std::strcmp(model.rows[3].text.data(), "#15 · CH 6 · -45 DBM") == 0);
    CHECK(!model.rows[0].selected);
    CHECK(model.rows[3].selected);
}

void testEvidenceDetailRetainsExactReference() {
    AirspaceGuardController controller;
    CHECK(controller.load(makeFindingReport()) ==
          AirspaceGuardLoadStatus::Ready);
    CHECK(controller.openSelected());
    CHECK(controller.next());
    CHECK(controller.openSelected());
    const AirspaceGuardUiModel model =
        presentAirspaceGuard(controller, UiLanguage::English);
    CHECK(model.headline == UiTextId::AirspaceGuardEvidenceDetailTitle);
    CHECK(!model.openable);
    CHECK(std::strcmp(model.rows[0].text.data(), "SOURCE FRAME #11") == 0);
    CHECK(std::strcmp(model.rows[1].text.data(), "CHANNEL 2 · -41 DBM") == 0);
    CHECK(std::strcmp(model.rows[2].text.data(),
                      "+100 ms FROM BURST START") == 0);
    CHECK(std::strcmp(model.rows[3].text.data(),
                      "HIGH · DETECTOR V1") == 0);
}

void testRussianInconclusiveExplainsIncompleteEvidence() {
    AirspaceGuardReport report{};
    report.status = AirspaceGuardStatus::Inconclusive;
    report.sourceFramesObserved = 65;
    report.framesAvailable = 65;
    report.framesInspected = 63;
    report.sourceReadFailures = 1;
    report.malformedFrames = 2;
    report.inspectionTruncated = true;
    AirspaceGuardController controller;
    CHECK(controller.load(report) == AirspaceGuardLoadStatus::Ready);
    const AirspaceGuardUiModel model =
        presentAirspaceGuard(controller, UiLanguage::Russian);
    CHECK(model.headline == UiTextId::AirspaceGuardInconclusive);
    CHECK(model.note == UiTextId::AirspaceGuardEvidenceIncomplete);
    CHECK(model.tone == AirspaceGuardUiTone::Caution);
    CHECK(model.evidenceIncomplete);
    CHECK(std::strcmp(model.rows[0].text.data(),
                      u8"ПРИНЯТО 65 · ПРОВЕРЕНО 63") == 0);
    CHECK(std::strcmp(model.rows[1].text.data(),
                      u8"НЕ ПРОЧТЕНО 1 · СБОЙ 2") == 0);
    CHECK(std::strcmp(model.rows[2].text.data(),
                      u8"ДОСТИГНУТ ЛИМИТ ПРОВЕРКИ") == 0);
    CHECK(model.rowCount == 3);
}

void testEmptyCaptureIsExplicitlyIncomplete() {
    AirspaceGuardReport report{};
    report.status = AirspaceGuardStatus::Inconclusive;
    AirspaceGuardController controller;
    CHECK(controller.load(report) == AirspaceGuardLoadStatus::Ready);
    const AirspaceGuardUiModel model =
        presentAirspaceGuard(controller, UiLanguage::English);
    CHECK(model.evidenceIncomplete);
    CHECK(model.note == UiTextId::AirspaceGuardEvidenceIncomplete);
    CHECK(std::strcmp(model.context.data(), "CAPTURE HAS NOT STARTED") == 0);
    CHECK(model.rowCount == 1);
    CHECK(std::strcmp(model.rows[0].text.data(),
                      "OBSERVED 0 · CHECKED 0") == 0);
}

void testClearOutcomeUsesTheOtherwiseEmptyRowsForCoverage() {
    AirspaceGuardReport report{};
    report.status = AirspaceGuardStatus::Clear;
    report.sourceFramesObserved = 314;
    report.framesAvailable = 1;
    report.framesInspected = 1;
    AirspaceGuardController controller;
    CHECK(controller.load(report) == AirspaceGuardLoadStatus::Ready);
    const AirspaceGuardUiModel model =
        presentAirspaceGuard(controller, UiLanguage::English);
    CHECK(model.headline == UiTextId::AirspaceGuardClear);
    CHECK(model.rowCount == 2U);
    CHECK(std::strcmp(model.rows[0].text.data(),
                      "OBSERVED 314 · CHECKED 1") == 0);
    CHECK(std::strcmp(model.rows[1].text.data(),
                      "EVIDENCE KEPT 1") == 0);
}

void testDroppedFindingCountReplacesLessImportantMix() {
    AirspaceGuardReport report = makeFindingReport();
    report.findingsDropped = 1;
    AirspaceGuardController controller;
    CHECK(controller.load(report) == AirspaceGuardLoadStatus::Ready);
    const AirspaceGuardUiModel model =
        presentAirspaceGuard(controller, UiLanguage::English);
    CHECK(model.evidenceIncomplete);
    CHECK(std::strcmp(model.rows[3].text.data(),
                      "FINDINGS OMITTED 1") == 0);
}

void testCaptureLossIsShownBeforeFindingMix() {
    AirspaceGuardReport report = makeFindingReport();
    report.sourceFramesDropped = 3;
    AirspaceGuardController controller;
    CHECK(controller.load(report) == AirspaceGuardLoadStatus::Ready);
    const AirspaceGuardUiModel model =
        presentAirspaceGuard(controller, UiLanguage::English);
    CHECK(model.evidenceIncomplete);
    CHECK(std::strcmp(model.rows[3].text.data(), "CAPTURE LOSS 3") == 0);
}

void testMalformedReportHasNoInventedEvidence() {
    AirspaceGuardController controller;
    AirspaceGuardReport report{};
    report.status = AirspaceGuardStatus::Finding;
    CHECK(controller.load(report) == AirspaceGuardLoadStatus::InvalidReport);
    const AirspaceGuardUiModel model =
        presentAirspaceGuard(controller, UiLanguage::English);
    CHECK(model.headline == UiTextId::AirspaceGuardReportRejected);
    CHECK(model.tone == AirspaceGuardUiTone::Error);
    CHECK(model.rowCount == 0);
    CHECK(!model.openable);
}

}  // namespace

int main() {
    testFindingShowsOnlyActionableUserFacts();
    testEvidenceListUsesFourStableTouchRows();
    testEvidenceDetailRetainsExactReference();
    testRussianInconclusiveExplainsIncompleteEvidence();
    testEmptyCaptureIsExplicitlyIncomplete();
    testClearOutcomeUsesTheOtherwiseEmptyRowsForCoverage();
    testDroppedFindingCountReplacesLessImportantMix();
    testCaptureLossIsShownBeforeFindingMix();
    testMalformedReportHasNoInventedEvidence();
    std::puts("Airspace Guard presenter tests passed");
    return 0;
}
