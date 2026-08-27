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
constexpr std::array<std::uint8_t, 6> kRelated{
    0x06, 0xaa, 0xbb, 0xcc, 0xdd, 0xee};

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

AirspaceGuardReport makeIdentityFindingReport() {
    AirspaceGuardReport report{};
    report.status = AirspaceGuardStatus::Finding;
    report.findingCount = 1U;
    report.sourceFramesObserved = 4U;
    report.framesAvailable = 4U;
    report.framesInspected = 4U;
    report.identityAdvertisementFrames = 2U;
    AirspaceFinding& finding = report.findings[0];
    finding.kind = AirspaceFindingKind::WifiSsidSecurityConflict;
    finding.confidence = AirspaceConfidence::Medium;
    finding.detectorVersion = AirspaceFinding::kWifiIdentityDetectorVersion;
    finding.threshold = 2U;
    finding.observed = 2U;
    finding.transmitter = kSource;
    finding.relatedTransmitter = kRelated;
    constexpr char kName[] = "Workshop";
    finding.networkNameLength = sizeof(kName) - 1U;
    std::memcpy(finding.networkName.data(), kName,
                finding.networkNameLength);
    finding.primarySecurity = AirspaceWifiSecurity::Open;
    finding.relatedSecurity = AirspaceWifiSecurity::Rsn;
    finding.firstUs = 1000000ULL;
    finding.lastUs = 1200000ULL;
    finding.evidenceCount = 2U;
    finding.evidence[0] = {1U, 1000000ULL, 1U, -35};
    finding.evidence[1] = {2U, 1200000ULL, 11U, -52};
    return report;
}

AirspaceGuardReport makeChurnFindingReport() {
    AirspaceGuardReport report{};
    report.status = AirspaceGuardStatus::Finding;
    report.findingCount = 1U;
    report.sourceFramesObserved = 4U;
    report.framesAvailable = 4U;
    report.framesInspected = 4U;
    report.identityAdvertisementFrames = 4U;
    AirspaceFinding& finding = report.findings[0];
    finding.kind = AirspaceFindingKind::WifiSsidChurn;
    finding.confidence = AirspaceConfidence::Medium;
    finding.detectorVersion = AirspaceFinding::kWifiSsidChurnDetectorVersion;
    finding.threshold = 4U;
    finding.observed = 4U;
    finding.transmitter = kSource;
    finding.firstUs = 1000000ULL;
    finding.lastUs = 1300000ULL;
    finding.evidenceCount = 4U;
    finding.evidence[0] = {0U, 1000000ULL, 1U, -35};
    finding.evidence[1] = {1U, 1100000ULL, 6U, -42};
    finding.evidence[2] = {2U, 1200000ULL, 11U, -48};
    finding.evidence[3] = {3U, 1300000ULL, 13U, -53};
    return report;
}

AirspaceGuardReport makeBleTrackerFindingReport() {
    AirspaceGuardReport report{};
    report.status = AirspaceGuardStatus::Finding;
    report.findingCount = 1U;
    report.sourceFramesObserved = 3U;
    report.framesAvailable = 3U;
    report.framesInspected = 3U;
    report.bleAdvertisementRecords = 3U;
    AirspaceFinding& finding = report.findings[0];
    finding.kind = AirspaceFindingKind::BleTrackerPresence;
    finding.confidence = AirspaceConfidence::Medium;
    finding.detectorVersion =
        AirspaceFinding::kBleTrackerPresenceDetectorVersion;
    finding.threshold = 3U;
    finding.observed = 3U;
    finding.transmitter = {0xc1, 0x12, 0x23, 0x34, 0x45, 0x56};
    finding.bleTrackerProtocol = AirspaceBleTrackerProtocol::FindMy;
    finding.bleAddressType = 1U;
    finding.firstUs = 1000000ULL;
    finding.lastUs = 1300000ULL;
    finding.evidenceCount = 3U;
    finding.evidence[0] = {0U, 1000000ULL, 0U, -42};
    finding.evidence[1] = {1U, 1100000ULL, 0U, -48};
    finding.evidence[2] = {2U, 1300000ULL, 0U, -53};
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

void testIdentityConflictExplainsIndicatorWithoutClaimingProof() {
    AirspaceGuardController controller;
    CHECK(controller.load(makeIdentityFindingReport()) ==
          AirspaceGuardLoadStatus::Ready);
    AirspaceGuardUiModel model =
        presentAirspaceGuard(controller, UiLanguage::English);
    CHECK(model.headline == UiTextId::AirspaceGuardIdentityConflict);
    CHECK(model.note == UiTextId::AirspaceGuardPassiveOnly);
    CHECK(std::strcmp(model.context.data(), "SSID Workshop") == 0);
    CHECK(std::strcmp(model.rows[1].text.data(),
                      "MEDIUM · DETECTOR V1") == 0);
    CHECK(std::strcmp(model.rows[2].text.data(),
                      "SECURITY OPEN / WPA2/3") == 0);
    CHECK(std::strcmp(model.rows[3].text.data(),
                      "AP 33:44:55 / CC:DD:EE") == 0);

    CHECK(controller.openSelected());
    CHECK(controller.next());
    CHECK(controller.openSelected());
    model = presentAirspaceGuard(controller, UiLanguage::English);
    CHECK(std::strcmp(model.context.data(),
                      "MAC 06:AA:BB:CC:DD:EE") == 0);
    CHECK(std::strcmp(model.rows[0].text.data(),
                      "SOURCE FRAME #2") == 0);
    CHECK(std::strcmp(model.rows[1].text.data(),
                      "WPA2/3 · CH 11 · -52 DBM") == 0);
    CHECK(std::strcmp(model.rows[2].text.data(),
                      "+200 ms FROM FINDING START") == 0);
}

void testSsidChurnExplainsIndicatorWithoutClaimingPineap() {
    AirspaceGuardController controller;
    CHECK(controller.load(makeChurnFindingReport()) ==
          AirspaceGuardLoadStatus::Ready);
    AirspaceGuardUiModel model =
        presentAirspaceGuard(controller, UiLanguage::English);
    CHECK(model.headline == UiTextId::AirspaceGuardSsidChurn);
    CHECK(model.note == UiTextId::AirspaceGuardPassiveOnly);
    CHECK(std::strcmp(model.context.data(),
                      "MAC 02:11:22:33:44:55") == 0);
    CHECK(std::strcmp(model.rows[1].text.data(),
                      "MEDIUM · DETECTOR V1") == 0);
    CHECK(std::strcmp(model.rows[2].text.data(),
                      "4 EVENTS · LIMIT 4") == 0);
    CHECK(std::strcmp(model.rows[3].text.data(),
                      "ONE BSSID · 0.3 S") == 0);

    CHECK(controller.openSelected());
    CHECK(controller.next());
    CHECK(controller.openSelected());
    model = presentAirspaceGuard(controller, UiLanguage::English);
    CHECK(std::strcmp(model.context.data(),
                      "MAC 02:11:22:33:44:55") == 0);
    CHECK(std::strcmp(model.rows[0].text.data(),
                      "SOURCE FRAME #1") == 0);
    CHECK(std::strcmp(model.rows[1].text.data(),
                      "CHANNEL 6 · -42 DBM") == 0);
    CHECK(std::strcmp(model.rows[2].text.data(),
                      "+100 ms FROM FINDING START") == 0);
}

void testBleTrackerPresenceNeverInventsAChannelOrOwner() {
    AirspaceGuardController controller;
    CHECK(controller.load(makeBleTrackerFindingReport()) ==
          AirspaceGuardLoadStatus::Ready);
    AirspaceGuardUiModel model =
        presentAirspaceGuard(controller, UiLanguage::English);
    CHECK(model.headline == UiTextId::AirspaceGuardBleTrackerPresence);
    CHECK(model.note == UiTextId::AirspaceGuardBlePresenceOnly);
    CHECK(std::strcmp(model.context.data(),
                      "BLE ID C1:12:23:34:45:56") == 0);
    CHECK(std::strcmp(model.rows[1].text.data(),
                      "MEDIUM · DETECTOR V1") == 0);
    CHECK(std::strcmp(model.rows[2].text.data(),
                      "3 EVENTS · LIMIT 3") == 0);
    CHECK(std::strcmp(model.rows[3].text.data(),
                      "FIND MY · 0.3 S") == 0);

    CHECK(controller.openSelected());
    model = presentAirspaceGuard(controller, UiLanguage::English);
    CHECK(std::strcmp(model.rows[0].text.data(), "#0 · -42 DBM") == 0);
    CHECK(std::strstr(model.rows[0].text.data(), "CH") == nullptr);
    CHECK(controller.next());
    CHECK(controller.openSelected());
    model = presentAirspaceGuard(controller, UiLanguage::English);
    CHECK(std::strcmp(model.rows[0].text.data(),
                      "SOURCE RECORD #1") == 0);
    CHECK(std::strcmp(model.rows[1].text.data(),
                      "FIND MY · -48 DBM") == 0);
    CHECK(std::strcmp(model.rows[2].text.data(),
                      "+100 ms FROM FINDING START") == 0);

    CHECK(controller.back());
    CHECK(controller.back());
    model = presentAirspaceGuard(controller, UiLanguage::Russian);
    CHECK(std::strcmp(uiText(UiLanguage::Russian, model.note),
                      u8"СИГНАЛ · ВЛАДЕЛЕЦ НЕИЗВЕСТЕН") == 0);
    CHECK(std::strcmp(model.context.data(),
                      "BLE ID C1:12:23:34:45:56") == 0);
}

void testInvalidSsidBytesUseStableNonInventedIdentifier() {
    AirspaceGuardReport report = makeIdentityFindingReport();
    report.findings[0].networkName.fill(0U);
    report.findings[0].networkName[0] = 0xffU;
    report.findings[0].networkNameLength = 1U;
    AirspaceGuardController controller;
    CHECK(controller.load(report) == AirspaceGuardLoadStatus::Ready);
    const AirspaceGuardUiModel model =
        presentAirspaceGuard(controller, UiLanguage::English);
    CHECK(std::strncmp(model.context.data(), "SSID ID ", 8U) == 0);
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
    testIdentityConflictExplainsIndicatorWithoutClaimingProof();
    testSsidChurnExplainsIndicatorWithoutClaimingPineap();
    testBleTrackerPresenceNeverInventsAChannelOrOwner();
    testInvalidSsidBytesUseStableNonInventedIdentifier();
    testRussianInconclusiveExplainsIncompleteEvidence();
    testEmptyCaptureIsExplicitlyIncomplete();
    testClearOutcomeUsesTheOtherwiseEmptyRowsForCoverage();
    testDroppedFindingCountReplacesLessImportantMix();
    testCaptureLossIsShownBeforeFindingMix();
    testMalformedReportHasNoInventedEvidence();
    std::puts("Airspace Guard presenter tests passed");
    return 0;
}
