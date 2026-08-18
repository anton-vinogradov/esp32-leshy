#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <string>
#include <utility>
#include <vector>

#include "apps/capture/RadiotapPcap.h"
#include "apps/capture/WifiFrameCapture.h"
#include "apps/survey/SurveyController.h"
#include "apps/survey/ProductSurveyAdmission.h"
#include "apps/survey/SurveyPipeline.h"
#include "apps/survey/SurveySourceController.h"
#include "apps/survey/SurveyWorkflow.h"
#include "apps/library/LibraryController.h"
#include "apps/library/SessionCatalog.h"
#include "apps/self_test/SelfTestController.h"
#include "apps/spectrum/Cc1101SpectrumController.h"
#include "apps/spectrum/Nrf24SpectrumController.h"
#include "domain/apps/AppCatalog.h"
#include "domain/hardware/HardwareInventory.h"
#include "drivers/ble/BlePassiveContract.h"
#include "drivers/radio/ShieldReceiverIdentity.h"
#include "drivers/radio/Cc1101PassiveSpectrum.h"
#include "drivers/radio/Nrf24PassiveSpectrum.h"
#include "drivers/wifi/WifiPassiveContract.h"
#include "kernel/runtime/AppRuntime.h"
#include "kernel/runtime/ResourceBroker.h"
#include "platform/arduino/RamSessionStoreIo.h"
#include "services/diagnostics/BootReport.h"
#include "services/diagnostics/HilSession.h"
#include "services/survey/IngressTiming.h"
#include "services/survey/ObservationQueue.h"
#include "services/survey/SessionBatchPolicy.h"
#include "services/survey/SourceDegradation.h"
#include "services/survey/SourceTimeline.h"
#include "services/survey/SurveySession.h"
#include "storage/AtomicHead.h"
#include "storage/MediaDiscovery.h"
#include "storage/MountPolicy.h"
#include "storage/ProductStorePolicy.h"
#include "storage/ProductBootRetry.h"
#include "storage/ProductStartRetry.h"
#include "storage/SdReadOnlyProtocol.h"
#include "storage/SdIdentification.h"
#include "storage/SdIdentificationTransport.h"
#include "storage/SdSectorInspection.h"
#include "storage/SdSpiWireCodec.h"
#include "storage/SessionCodec.h"
#include "storage/SessionStore.h"
#include "storage/SessionStoreBoundary.h"
#include "storage/SessionStoreIoRouter.h"
#include "storage/StorageGuard.h"
#include "storage/StorageTiming.h"
#include "ui/Pcf8574ButtonInput.h"
#include "ui/LanguageController.h"
#include "ui/UiController.h"
#include "ui/UiStrings.h"
#include "ui/VisualTheme.h"
#include "ui/UiComponents.h"

using namespace leshy1::domain::apps;
using namespace leshy1::domain::hardware;
using namespace leshy1::domain::observations;
using namespace leshy1::drivers::wifi;
using namespace leshy1::drivers::radio;
using namespace leshy1::kernel::runtime;
using namespace leshy1::services::diagnostics;
using namespace leshy1::services::survey;
using namespace leshy1::storage;
using namespace leshy1::ui;
using namespace leshy1::apps::survey;
using namespace leshy1::apps::library;
using namespace leshy1::apps::self_test;
using namespace leshy1::apps::capture;
using namespace leshy1::apps::spectrum;

namespace {

int failures = 0;

#define CHECK(expression)                                                                       \
    do {                                                                                        \
        if (!(expression)) {                                                                    \
            std::cerr << __FILE__ << ':' << __LINE__ << ": check failed: " #expression << '\n'; \
            ++failures;                                                                         \
        }                                                                                       \
    } while (false)

void testVisualThemeContract() {
    using leshy1::ui::visual::Layout;
    using leshy1::ui::visual::Palette;
    using leshy1::ui::visual::rgb565;

    CHECK(Layout::ScreenWidth == 240);
    CHECK(Layout::ScreenHeight == 320);
    CHECK(Layout::Edge * 2 + Layout::ContentWidth == Layout::ScreenWidth);
    CHECK(Layout::ContentTop + 3 * (Layout::RowHeight + Layout::RowGap) <
          Layout::FooterDividerY);
    CHECK(Layout::ContentTop + 5 * Layout::HomeRowHeight +
              4 * Layout::HomeRowGap < Layout::FooterDividerY);
    CHECK(Palette::Canvas == rgb565(7, 16, 12));
    CHECK(Palette::Header != Palette::Canvas);
    CHECK(Palette::Surface != Palette::SurfaceFocus);
    CHECK(Palette::TextPrimary != Palette::TextSecondary);
    CHECK(Palette::Focus != Palette::Positive);
    CHECK(Palette::Warning != Palette::Danger);
}

void testUiComponentGeometryContract() {
    using leshy1::ui::visual::Components;
    using leshy1::ui::visual::Layout;
    using leshy1::ui::visual::Rect;
    using leshy1::ui::visual::beforeFooter;
    using leshy1::ui::visual::contains;
    using leshy1::ui::visual::insideScreen;
    using leshy1::ui::visual::overlaps;

    CHECK(insideScreen(Components::header()));
    CHECK(insideScreen(Components::title()));
    for (std::uint8_t index = 0; index < 5; ++index) {
        const Rect row = Components::homeRow(index);
        CHECK(beforeFooter(row));
        CHECK(contains(row, Components::focusMarker(row)));
        if (index != 0) {
            const Rect previous = Components::homeRow(index - 1);
            CHECK(!overlaps(previous, row));
            CHECK(row.y - previous.y ==
                  Layout::HomeRowHeight + Layout::HomeRowGap);
        }
    }
    CHECK(!overlaps(Components::choiceRow(0), Components::choiceRow(1)));
    CHECK(beforeFooter(Components::choiceRow(1)));
    CHECK(beforeFooter(Components::metricRow(4)));
    CHECK(beforeFooter(Components::stateCard()));
    CHECK(!overlaps(Components::footerDivider(), Components::inputStatus()));
    CHECK(!overlaps(Components::inputStatus(), Components::footerHint()));
    for (std::uint8_t index = 0; index < 3; ++index) {
        CHECK(insideScreen(Components::navigationCell(index)));
        CHECK(contains(Components::footerHint(),
                       Components::navigationCell(index)));
        if (index != 0) {
            CHECK(!overlaps(Components::navigationCell(index - 1),
                            Components::navigationCell(index)));
        }
    }
}

void testLanguageCatalogAndControllerAreBounded() {
    CHECK(kUiTextCount > 80);
    for (std::size_t index = 0; index < kUiTextCount; ++index) {
        const UiTextSpec& spec = uiTextSpec(static_cast<UiTextId>(index));
        CHECK(spec.english != nullptr && spec.english[0] != '\0');
        CHECK(spec.russian != nullptr && spec.russian[0] != '\0');
        CHECK(spec.maximumPixels > 0 && spec.maximumPixels <= 212);
    }
    CHECK(std::strcmp(uiText(UiLanguage::English, UiTextId::AppSelfTest),
                      "SELF-TEST") == 0);
    CHECK(std::strcmp(uiText(UiLanguage::Russian, UiTextId::AppSelfTest),
                      u8"САМОПРОВЕРКА") == 0);
    CHECK(std::strcmp(uiText(UiLanguage::Russian, UiTextId::NavBack),
                      u8"НАЗАД") == 0);
    CHECK(std::strcmp(uiText(UiLanguage::Russian, UiTextId::NavSelect),
                      u8"ВЫБОР") == 0);
    CHECK(std::strcmp(uiText(UiLanguage::Russian, UiTextId::NavEnter),
                      u8"ВХОД") == 0);

    UiLanguage parsed = UiLanguage::English;
    CHECK(uiLanguageFromName("ru", &parsed));
    CHECK(parsed == UiLanguage::Russian);
    CHECK(!uiLanguageFromName("de", &parsed));

    LanguageController controller;
    CHECK(controller.active() == UiLanguage::English);
    CHECK(controller.selection() == 0);
    CHECK(controller.next());
    CHECK(controller.selected() == UiLanguage::Russian);
    CHECK(controller.apply());
    CHECK(controller.active() == UiLanguage::Russian);
    controller.enter();
    CHECK(controller.selection() == 1);
    CHECK(controller.previous());
    CHECK(controller.apply());
    CHECK(controller.active() == UiLanguage::English);
    controller.restore(UiLanguage::Russian);
    CHECK(controller.active() == UiLanguage::Russian);
    CHECK(controller.selection() == 1);
}

void testSelfTestQuickIsReadOnlyBoundedAndFullFailsClosed() {
    SelfTestFacts healthy;
    healthy.buildIdentityPresent = true;
    healthy.profileMatched = true;
    healthy.displayReady = true;
    healthy.inputFrontendReady = true;
    healthy.inputQueueHealthy = true;
    healthy.buzzerInactive = true;
    healthy.resourceScopeClean = true;
    healthy.heapFree = 220U * 1024U;
    healthy.heapMinimum = 180U * 1024U;
    healthy.inputQueueDrops = 0;
    healthy.activeResources = resourceMask(Resource::UiForeground);
    healthy.persistentSurveyReady = true;
    healthy.passiveBleReady = true;
    healthy.passiveWifiCaptureReady = true;
    healthy.enrolledStorageReady = true;
    healthy.persistentLibraryReady = true;
    healthy.persistentWifiCaptureReady = true;
    healthy.shieldReceiversApplicable = true;
    healthy.shieldReceiverProbeComplete = true;
    healthy.shieldReceiverProbePassed = true;
    healthy.nrf24SpectrumExerciseComplete = true;
    healthy.nrf24SpectrumExercisePassed = true;
    healthy.cc1101SpectrumExerciseComplete = true;
    healthy.cc1101SpectrumExercisePassed = true;

    SelfTestController controller;
    CHECK(controller.view() == SelfTestView::ModeMenu);
    CHECK(controller.selection() == 0);
    CHECK(controller.selectedMode() == SelfTestMode::Quick);
    CHECK(!controller.previousMode());
    CHECK(controller.activate(healthy, 100));
    CHECK(controller.runAwaitingFinish());
    controller.finishRun(125);
    CHECK(!controller.runAwaitingFinish());
    CHECK(controller.view() == SelfTestView::Result);
    CHECK(controller.hasReport());
    const SelfTestReport& quick = controller.report();
    CHECK(quick.mode == SelfTestMode::Quick);
    CHECK(quick.status == SelfTestResultStatus::Pass);
    CHECK(quick.checkCount == 8);
    CHECK(quick.passed == 8);
    CHECK(quick.failed == 0);
    CHECK(quick.blocked == 0);
    CHECK(quick.readOnly);
    CHECK(quick.durationUs == 25);
    CHECK(std::strcmp(quick.checks[0].id, "quick.build.identity") == 0);
    CHECK(std::strcmp(quick.checks[7].id, "quick.resource.scope") == 0);

    CHECK(controller.back());
    CHECK(controller.nextMode());
    CHECK(controller.selectedMode() == SelfTestMode::FullGuided);
    CHECK(controller.activate(healthy, 200));
    CHECK(controller.view() == SelfTestView::Preflight);
    CHECK(!controller.runAwaitingFinish());
    CHECK(controller.activate(healthy, 210));
    CHECK(controller.view() == SelfTestView::VisualCheck);
    CHECK(controller.runAwaitingFinish());
    CHECK(controller.visualState() == 0);
    CHECK(std::strcmp(selfTestVisualStateName(controller.visualState()),
                      "dialog_confirm") == 0);
    for (std::uint8_t state = 1; state < SelfTestController::kVisualStateCount;
         ++state) {
        CHECK(controller.activate(healthy, 220 + state));
        CHECK(controller.view() == SelfTestView::VisualCheck);
        CHECK(controller.visualState() == state);
    }
    CHECK(controller.activate(healthy, 230));
    CHECK(controller.view() == SelfTestView::ActiveChecks);
    CHECK(controller.completeActiveChecks(healthy, 240));
    CHECK(controller.view() == SelfTestView::Result);
    CHECK(std::strcmp(selfTestVisualStateName(1), "unavailable") == 0);
    CHECK(std::strcmp(selfTestVisualStateName(2), "degraded") == 0);
    CHECK(std::strcmp(selfTestVisualStateName(3), "error") == 0);
    CHECK(std::strcmp(selfTestVisualStateName(4), "running") == 0);
    CHECK(std::strcmp(selfTestVisualStateName(5), "none") == 0);
    const SelfTestReport& full = controller.report();
    CHECK(full.mode == SelfTestMode::FullGuided);
    CHECK(full.status == SelfTestResultStatus::Blocked);
    CHECK(!full.readOnly);
    CHECK(full.sequence == 2);
    CHECK(full.checkCount == 22);
    CHECK(full.passed == 18);
    CHECK(full.failed == 0);
    CHECK(full.blocked == 1);
    CHECK(full.notApplicable == 3);
    CHECK(std::strcmp(full.checks[8].id, "full.ui.common_states") == 0);
    CHECK(std::strcmp(full.checks[9].id,
                      "full.s3.survey.persistence") == 0);
    CHECK(std::strcmp(full.checks[14].id,
                      "full.s4.capture.persistence") == 0);
    CHECK(std::strcmp(full.checks[15].id, "full.assembly.gps") == 0);
    CHECK(full.checks[15].status == SelfTestResultStatus::NotApplicable);
    CHECK(std::strcmp(full.checks[18].id,
                      "full.s4.shield.receivers") == 0);
    CHECK(full.checks[18].status == SelfTestResultStatus::Pass);
    CHECK(std::strcmp(full.checks[19].id,
                      "full.s4.spectrum.nrf24.receive") == 0);
    CHECK(full.checks[19].status == SelfTestResultStatus::Pass);
    CHECK(std::strcmp(full.checks[20].id,
                      "full.s4.spectrum.cc1101.receive") == 0);
    CHECK(full.checks[20].status == SelfTestResultStatus::Pass);
    CHECK(std::strcmp(full.checks[21].id,
                      "full.capability.coverage") == 0);
    CHECK(std::strcmp(selfTestResultStatusName(
                          SelfTestResultStatus::NotApplicable),
                      "not_applicable") == 0);
    CHECK(SelfTestReport::kPlanVersion == 5);

    CHECK(controller.back());
    CHECK(controller.previousMode());
    SelfTestFacts failed = healthy;
    failed.buzzerInactive = false;
    failed.inputQueueDrops = 1;
    CHECK(controller.activate(failed, 300));
    controller.finishRun(290);
    CHECK(controller.report().status == SelfTestResultStatus::Fail);
    CHECK(controller.report().failed == 2);
    CHECK(controller.report().durationUs == 0);
    CHECK(!controller.activate(healthy, 400));

    SelfTestFacts incomplete = healthy;
    incomplete.passiveBleReady = false;
    incomplete.gpsDeclared = true;
    SelfTestController coverageFailure;
    CHECK(coverageFailure.nextMode());
    CHECK(coverageFailure.activate(incomplete, 500));
    CHECK(coverageFailure.activate(incomplete, 510));
    for (std::uint8_t state = 1;
         state < SelfTestController::kVisualStateCount; ++state) {
        CHECK(coverageFailure.activate(incomplete, 510 + state));
    }
    CHECK(coverageFailure.activate(incomplete, 520));
    CHECK(coverageFailure.view() == SelfTestView::ActiveChecks);
    CHECK(coverageFailure.completeActiveChecks(incomplete, 530));
    const SelfTestReport& incompleteReport = coverageFailure.report();
    CHECK(incompleteReport.status == SelfTestResultStatus::Fail);
    CHECK(incompleteReport.passed == 17);
    CHECK(incompleteReport.failed == 1);
    CHECK(incompleteReport.blocked == 2);
    CHECK(incompleteReport.notApplicable == 2);

    SelfTestFacts unprobed = healthy;
    unprobed.shieldReceiverProbeComplete = false;
    unprobed.shieldReceiverProbePassed = false;
    SelfTestController blockedProbe;
    CHECK(blockedProbe.nextMode());
    CHECK(blockedProbe.activate(unprobed, 600));
    CHECK(blockedProbe.activate(unprobed, 610));
    for (std::uint8_t state = 1;
         state < SelfTestController::kVisualStateCount; ++state) {
        CHECK(blockedProbe.activate(unprobed, 610 + state));
    }
    CHECK(blockedProbe.activate(unprobed, 620));
    CHECK(blockedProbe.completeActiveChecks(unprobed, 630));
    CHECK(blockedProbe.report().passed == 17);
    CHECK(blockedProbe.report().failed == 0);
    CHECK(blockedProbe.report().blocked == 2);
    CHECK(blockedProbe.report().notApplicable == 3);

    SelfTestFacts failedRf = healthy;
    failedRf.cc1101SpectrumExercisePassed = false;
    SelfTestController activeFailure;
    CHECK(activeFailure.nextMode());
    CHECK(activeFailure.activate(failedRf, 700));
    CHECK(activeFailure.activate(failedRf, 710));
    for (std::uint8_t state = 1;
         state < SelfTestController::kVisualStateCount; ++state) {
        CHECK(activeFailure.activate(failedRf, 710 + state));
    }
    CHECK(activeFailure.activate(failedRf, 720));
    CHECK(activeFailure.view() == SelfTestView::ActiveChecks);
    CHECK(activeFailure.completeActiveChecks(failedRf, 730));
    CHECK(activeFailure.report().status == SelfTestResultStatus::Fail);
    CHECK(activeFailure.report().passed == 17);
    CHECK(activeFailure.report().failed == 1);
    CHECK(activeFailure.report().blocked == 1);

    SelfTestFacts cancelled = healthy;
    SelfTestController activeCancel;
    CHECK(activeCancel.nextMode());
    CHECK(activeCancel.activate(cancelled, 800));
    CHECK(activeCancel.activate(cancelled, 810));
    for (std::uint8_t state = 1;
         state < SelfTestController::kVisualStateCount; ++state) {
        CHECK(activeCancel.activate(cancelled, 810 + state));
    }
    CHECK(activeCancel.activate(cancelled, 820));
    CHECK(activeCancel.back());
    CHECK(activeCancel.view() == SelfTestView::Preflight);
    CHECK(activeCancel.report().cancelled);
    CHECK(!activeCancel.runAwaitingFinish());
}

void testShieldReceiverIdentityContractFailsClosed() {
    ShieldReceiverProbeReport passing;
    passing.profileDeclared = true;
    passing.gpsExcludedByProfile = true;
    passing.pn532ExcludedByProfile = true;
    passing.resourceAcquired = true;
    passing.gpio21StableHigh = true;
    passing.cleanupComplete = true;
    passing.nrfRegisterReads = 8;
    passing.ccStatusReads = 2;
    passing.spiBytesClocked = 20;
    passing.nrf[0] = {0x0E, 0x08, 2, 0x0E, 0, false};
    passing.nrf[1] = {0x0E, 0x08, 40, 0x0E, 0, false};
    passing.cc1101 = {0x0F, 0x00, 0x14, true, false};
    finalizeShieldReceiverProbe(&passing);
    CHECK(passing.status == ShieldReceiverProbeStatus::Pass);
    CHECK(passing.detectedReceivers == 3);
    CHECK(passing.nrf[0].detected && passing.nrf[1].detected);
    CHECK(passing.cc1101.detected);
    CHECK(std::strcmp(shieldReceiverProbeStatusName(passing.status), "pass") == 0);

    ShieldReceiverProbeReport floating = passing;
    floating.nrf[0] = {};
    floating.nrf[1] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, false};
    floating.cc1101 = {0xFF, 0xFF, 0xFF, false, false};
    finalizeShieldReceiverProbe(&floating);
    CHECK(floating.status == ShieldReceiverProbeStatus::Failed);
    CHECK(floating.detectedReceivers == 0);

    ShieldReceiverProbeReport partial = passing;
    partial.nrf[1] = {};
    finalizeShieldReceiverProbe(&partial);
    CHECK(partial.status == ShieldReceiverProbeStatus::Partial);
    CHECK(partial.detectedReceivers == 2);

    ShieldReceiverProbeReport unsafe = passing;
    unsafe.nrfCeHighEvents = 1;
    finalizeShieldReceiverProbe(&unsafe);
    CHECK(unsafe.status == ShieldReceiverProbeStatus::Failed);
    unsafe = passing;
    unsafe.ccCommandStrobes = 1;
    finalizeShieldReceiverProbe(&unsafe);
    CHECK(unsafe.status == ShieldReceiverProbeStatus::Failed);
    unsafe = passing;
    unsafe.radioTxCommands = 1;
    finalizeShieldReceiverProbe(&unsafe);
    CHECK(unsafe.status == ShieldReceiverProbeStatus::Failed);
    unsafe = passing;
    unsafe.gpio21StableHigh = false;
    finalizeShieldReceiverProbe(&unsafe);
    CHECK(unsafe.status == ShieldReceiverProbeStatus::Failed);

    ShieldReceiverProbeReport refused = passing;
    refused.gpsExcludedByProfile = false;
    finalizeShieldReceiverProbe(&refused);
    CHECK(refused.status == ShieldReceiverProbeStatus::RefusedProfile);
    ShieldReceiverProbeReport busy = passing;
    busy.resourceAcquired = false;
    finalizeShieldReceiverProbe(&busy);
    CHECK(busy.status == ShieldReceiverProbeStatus::Busy);
}

void testNrf24PassiveSpectrumContractAndControllerAreBounded() {
    const Nrf24PassiveSpectrumPlan plan =
        defaultNrf24PassiveSpectrumPlan();
    CHECK(validateNrf24PassiveSpectrumPlan(plan));
    CHECK(plan.firstChannel == 2);
    CHECK(plan.lastChannel == 84);
    CHECK(plan.dwellUs == 200);
    Nrf24PassiveSpectrumPlan unsafePlan = plan;
    unsafePlan.maximumModules = 3;
    CHECK(!validateNrf24PassiveSpectrumPlan(unsafePlan));
    unsafePlan = plan;
    unsafePlan.dwellUs = 100;
    CHECK(!validateNrf24PassiveSpectrumPlan(unsafePlan));

    Nrf24PassiveSpectrumReport report;
    report.status = Nrf24PassiveSpectrumStatus::Ready;
    report.profileDeclared = true;
    report.gpsExcludedByProfile = true;
    report.pn532ExcludedByProfile = true;
    report.resourceOwned = true;
    report.gpio21StableHigh = true;
    report.detectedModules = 2;
    report.cleanupComplete = false;
    CHECK(validateNrf24PassiveSpectrumReport(report, false));
    CHECK(!validateNrf24PassiveSpectrumReport(report, true));
    report.cleanupComplete = true;
    CHECK(validateNrf24PassiveSpectrumReport(report, true));
    Nrf24PassiveSpectrumReport unsafe = report;
    unsafe.txModeEntries = 1;
    CHECK(!validateNrf24PassiveSpectrumReport(unsafe, true));
    unsafe = report;
    unsafe.txPayloadCommands = 1;
    CHECK(!validateNrf24PassiveSpectrumReport(unsafe, true));
    unsafe = report;
    unsafe.nrfSlot3Gated = false;
    CHECK(!validateNrf24PassiveSpectrumReport(unsafe, true));
    unsafe = report;
    unsafe.status = Nrf24PassiveSpectrumStatus::Fault;
    CHECK(!validateNrf24PassiveSpectrumReport(unsafe, true));

    Nrf24SpectrumController controller;
    CHECK(controller.start(2, 1000));
    CHECK(controller.state() == Nrf24SpectrumViewState::Running);
    Nrf24PassiveSweep sweep;
    sweep.modules = 2;
    sweep.startedUs = 1000;
    sweep.endedUs = 2000;
    sweep.valid = true;
    sweep.hits[10] = 1;
    sweep.hits[40] = 1;
    CHECK(controller.ingest(sweep));
    CHECK(controller.sweeps() == 1);
    CHECK(controller.totalHits() == 2);
    CHECK(controller.activeBins() == 2);
    CHECK(controller.intensity(10) == 64);
    CHECK(controller.hottestChannel() == 12);
    CHECK(controller.togglePause());
    CHECK(controller.state() == Nrf24SpectrumViewState::Paused);
    CHECK(!controller.ingest(sweep));
    CHECK(controller.togglePause());
    sweep.startedUs = 2001;
    sweep.endedUs = 3000;
    sweep.hits.fill(0);
    CHECK(controller.ingest(sweep));
    CHECK(controller.intensity(10) == 56);
    CHECK(controller.stop());
    CHECK(controller.state() == Nrf24SpectrumViewState::Idle);
    CHECK(!controller.start(3, 4000));
}

void testCc1101PassiveSpectrumContractAndControllerAreBounded() {
    const auto plan315 = cc1101PassiveSpectrumPlan(
        Cc1101SpectrumBand::Band315);
    const auto plan433 = cc1101PassiveSpectrumPlan(
        Cc1101SpectrumBand::Band433);
    const auto plan868 = cc1101PassiveSpectrumPlan(
        Cc1101SpectrumBand::Band868);
    const auto plan915 = cc1101PassiveSpectrumPlan(
        Cc1101SpectrumBand::Band915);
    CHECK(validateCc1101PassiveSpectrumPlan(plan315));
    CHECK(validateCc1101PassiveSpectrumPlan(plan433));
    CHECK(validateCc1101PassiveSpectrumPlan(plan868));
    CHECK(validateCc1101PassiveSpectrumPlan(plan915));
    CHECK(cc1101SpectrumFrequencyKHz(plan433, 0) == 433050);
    CHECK(cc1101SpectrumFrequencyKHz(plan433, 63) == 434790);
    Cc1101PassiveSpectrumPlan unsafePlan = plan433;
    unsafePlan.firstKHz = 348001;
    CHECK(!validateCc1101PassiveSpectrumPlan(unsafePlan));
    unsafePlan = plan433;
    unsafePlan.settleUs = 100;
    CHECK(!validateCc1101PassiveSpectrumPlan(unsafePlan));

    Cc1101PassiveSpectrumReport report;
    report.status = Cc1101PassiveSpectrumStatus::Ready;
    report.profileDeclared = true;
    report.gpsExcludedByProfile = true;
    report.pn532ExcludedByProfile = true;
    report.resourceOwned = true;
    report.gpio21StableHigh = true;
    report.receiverDetected = true;
    report.partNumber = 0;
    report.version = 0x14;
    report.commandStrobes = 7;
    report.resetStrobes = 1;
    report.receiveStrobes = 2;
    report.idleStrobes = 4;
    report.cleanupComplete = false;
    CHECK(validateCc1101PassiveSpectrumReport(report, false));
    CHECK(!validateCc1101PassiveSpectrumReport(report, true));
    report.cleanupComplete = true;
    CHECK(validateCc1101PassiveSpectrumReport(report, true));
    Cc1101PassiveSpectrumReport unsafe = report;
    unsafe.txStrobes = 1;
    CHECK(!validateCc1101PassiveSpectrumReport(unsafe, true));
    unsafe = report;
    unsafe.paTableWrites = 1;
    CHECK(!validateCc1101PassiveSpectrumReport(unsafe, true));
    unsafe = report;
    unsafe.commandStrobes = 8;
    CHECK(!validateCc1101PassiveSpectrumReport(unsafe, true));

    Cc1101SpectrumController controller;
    CHECK(controller.start(1000));
    CHECK(controller.state() == Cc1101SpectrumViewState::Running);
    CHECK(controller.band() == Cc1101SpectrumBand::Band433);
    Cc1101PassiveSample sample;
    sample.band = Cc1101SpectrumBand::Band433;
    sample.bin = 0;
    sample.frequencyKHz = cc1101SpectrumFrequencyKHz(plan433, 0);
    sample.rssiDbm = -90;
    sample.startedUs = 1000;
    sample.endedUs = 1100;
    sample.valid = true;
    CHECK(controller.ingest(sample));
    CHECK(controller.nextBin() == 1);
    CHECK(controller.samples() == 1);
    CHECK(controller.intensity(0) == 28);
    CHECK(controller.peakKHz() == 433050);
    CHECK(controller.peakRssiDbm() == -90);
    CHECK(!controller.ingest(sample));
    for (std::uint8_t bin = 1; bin < 64; ++bin) {
        sample.bin = bin;
        sample.frequencyKHz = cc1101SpectrumFrequencyKHz(plan433, bin);
        sample.rssiDbm = static_cast<std::int16_t>(-100 + bin / 4);
        sample.startedUs = 1100 + static_cast<std::uint64_t>(bin) * 100;
        sample.endedUs = sample.startedUs + 50;
        CHECK(controller.ingest(sample));
    }
    CHECK(controller.sweeps() == 1);
    CHECK(controller.nextBin() == 0);
    CHECK(controller.samples() == 64);
    CHECK(controller.togglePause());
    CHECK(controller.state() == Cc1101SpectrumViewState::Paused);
    CHECK(!controller.ingest(sample));
    CHECK(controller.nextBand());
    CHECK(controller.band() == Cc1101SpectrumBand::Band868);
    CHECK(controller.sweeps() == 0);
    CHECK(controller.samples() == 0);
    CHECK(controller.previousBand());
    CHECK(controller.band() == Cc1101SpectrumBand::Band433);
    CHECK(controller.togglePause());
    CHECK(controller.stop());
    CHECK(controller.state() == Cc1101SpectrumViewState::Idle);
}

void testProductBootRetryIsNarrowAndBounded() {
    CHECK(isProductBootRetryReset(true, false, false));
    CHECK(isProductBootRetryReset(true, true, false));
    CHECK(isProductBootRetryReset(false, true, true));
    CHECK(!isProductBootRetryReset(false, true, false));
    CHECK(!isProductBootRetryReset(false, false, true));
    CHECK(!shouldResetProductBootRetryState(true, true, true, true));
    CHECK(shouldResetProductBootRetryState(false, true, true, true));
    CHECK(shouldResetProductBootRetryState(true, false, true, true));
    CHECK(shouldResetProductBootRetryState(true, true, false, true));
    CHECK(shouldResetProductBootRetryState(true, true, true, false));
    CHECK(kProductBootRecoveryWatchdogMs == 4000);
    CHECK(kProductBootRecoveryHardwareWatchdogMs == 5000);
    CHECK(kProductBootMaximumAttempts == 8);
    CHECK(kSdMaxR1PollBytes == 16);

    ProductBootRetryEvidence evidence;
    evidence.identityFailed = true;
    evidence.enrolled = true;
    evidence.expectedFingerprintValid = true;
    evidence.observedFingerprintEmpty = true;
    evidence.missingMedia = true;
    evidence.cleanupComplete = true;
    CHECK(shouldRetryProductBootRecovery(evidence, 1));
    CHECK(shouldRetryProductBootRecovery(evidence, 2));
    CHECK(shouldRetryProductBootRecovery(evidence, 3));
    CHECK(shouldRetryProductBootRecovery(evidence, 7));
    CHECK(!shouldRetryProductBootRecovery(evidence, 0));
    CHECK(!shouldRetryProductBootRecovery(evidence, 8));
    CHECK(productBootRetryDelayMs(0) == 0);
    CHECK(productBootRetryDelayMs(1) == 250);
    CHECK(productBootRetryDelayMs(2) == 500);
    CHECK(productBootRetryDelayMs(3) == 750);
    CHECK(productBootRetryDelayMs(7) == 1750);
    CHECK(productBootRetryDelayMs(8) == 0);

    ProductBootRetryEvidence mutated = evidence;
    mutated.identityFailed = false;
    CHECK(!shouldRetryProductBootRecovery(mutated, 1));
    mutated = evidence;
    mutated.enrolled = false;
    CHECK(!shouldRetryProductBootRecovery(mutated, 1));
    mutated = evidence;
    mutated.expectedFingerprintValid = false;
    CHECK(!shouldRetryProductBootRecovery(mutated, 1));
    mutated = evidence;
    mutated.observedFingerprintEmpty = false;
    CHECK(!shouldRetryProductBootRecovery(mutated, 1));
    mutated = evidence;
    mutated.fingerprintMatched = true;
    CHECK(!shouldRetryProductBootRecovery(mutated, 1));
    mutated = evidence;
    mutated.mountedReadOnly = true;
    CHECK(!shouldRetryProductBootRecovery(mutated, 1));
    mutated = evidence;
    mutated.rootExists = true;
    CHECK(!shouldRetryProductBootRecovery(mutated, 1));
    mutated = evidence;
    mutated.opened = true;
    CHECK(!shouldRetryProductBootRecovery(mutated, 1));
    mutated = evidence;
    mutated.catalogAdmitted = true;
    CHECK(!shouldRetryProductBootRecovery(mutated, 1));
    mutated = evidence;
    mutated.missingMedia = false;
    CHECK(!shouldRetryProductBootRecovery(mutated, 1));
    mutated = evidence;
    mutated.blockedWriteAttempts = 1;
    CHECK(!shouldRetryProductBootRecovery(mutated, 1));
    mutated = evidence;
    mutated.ownedAfter = 12;
    CHECK(!shouldRetryProductBootRecovery(mutated, 1));
    mutated = evidence;
    mutated.cleanupComplete = false;
    CHECK(!shouldRetryProductBootRecovery(mutated, 1));
}

void testProductStartIdentityRetryStopsBeforeFilesystem() {
    ProductStartIdentityRetryEvidence evidence;
    evidence.explicitStart = true;
    evidence.enrolled = true;
    evidence.expectedFingerprintValid = true;
    evidence.requiredResourcesHeld = true;
    evidence.physicalSpiStarted = true;
    evidence.identityStatus = SdTransportRunStatus::ExchangeFailed;
    evidence.observedFingerprintEmpty = true;
    evidence.identityCleanupComplete = true;
    for (std::uint8_t attempt = 1;
         attempt < kProductStartMaximumIdentityAttempts; ++attempt) {
        CHECK(shouldRetryProductStartIdentity(evidence, attempt));
    }
    CHECK(!shouldRetryProductStartIdentity(evidence, 0));
    CHECK(!shouldRetryProductStartIdentity(
        evidence, kProductStartMaximumIdentityAttempts));
    CHECK(productStartIdentityRetryDelayMs(0) == 0);
    CHECK(productStartIdentityRetryDelayMs(1) == 250);
    CHECK(productStartIdentityRetryDelayMs(2) == 500);
    CHECK(productStartIdentityRetryDelayMs(7) == 1750);
    CHECK(productStartIdentityRetryDelayMs(8) == 0);
    evidence.identityStatus = SdTransportRunStatus::InitTimeout;
    CHECK(shouldRetryProductStartIdentity(evidence, 1));
    evidence.identityStatus = SdTransportRunStatus::ParseRejected;
    CHECK(shouldRetryProductStartIdentity(evidence, 1));

    ProductStartIdentityRetryEvidence mutated = evidence;
    mutated.explicitStart = false;
    CHECK(!shouldRetryProductStartIdentity(mutated, 1));
    mutated = evidence;
    mutated.enrolled = false;
    CHECK(!shouldRetryProductStartIdentity(mutated, 1));
    mutated = evidence;
    mutated.expectedFingerprintValid = false;
    CHECK(!shouldRetryProductStartIdentity(mutated, 1));
    mutated = evidence;
    mutated.requiredResourcesHeld = false;
    CHECK(!shouldRetryProductStartIdentity(mutated, 1));
    mutated = evidence;
    mutated.physicalSpiStarted = false;
    CHECK(!shouldRetryProductStartIdentity(mutated, 1));
    mutated = evidence;
    mutated.identityStatus = SdTransportRunStatus::InvalidPlan;
    CHECK(!shouldRetryProductStartIdentity(mutated, 1));
    mutated = evidence;
    mutated.observedFingerprintEmpty = false;
    CHECK(!shouldRetryProductStartIdentity(mutated, 1));
    mutated = evidence;
    mutated.identityCleanupComplete = false;
    CHECK(!shouldRetryProductStartIdentity(mutated, 1));
    mutated = evidence;
    mutated.filesystemAttempted = true;
    CHECK(!shouldRetryProductStartIdentity(mutated, 1));
}

void testStorageTimingSummaryUsesNearestRank() {
    std::array<std::uint64_t, 20> timings{};
    for (std::size_t index = 0; index < timings.size(); ++index) {
        timings[index] = static_cast<std::uint64_t>((timings.size() - index) * 10U);
    }
    StorageTimingSummary summary = summarizeStorageTimings(timings.data(), timings.size());
    CHECK(summary.valid);
    CHECK(summary.samples == 20);
    CHECK(summary.totalUs == 2100);
    CHECK(summary.minimumUs == 10);
    CHECK(summary.p50Us == 100);
    CHECK(summary.p95Us == 190);
    CHECK(summary.p99Us == 200);
    CHECK(summary.maximumUs == 200);
    CHECK(!summarizeStorageTimings(nullptr, 1).valid);
    timings[0] = 0;
    CHECK(!summarizeStorageTimings(timings.data(), timings.size()).valid);
}

void testIngressRateSummaryUsesNearestRankAndRejectsZero() {
    std::array<std::uint64_t, 20> rates{};
    for (std::size_t index = 0; index < rates.size(); ++index) {
        rates[index] = static_cast<std::uint64_t>((rates.size() - index) * 100U);
    }
    const IngressRateSummary summary =
        summarizeIngressRates(rates.data(), rates.size());
    CHECK(summary.valid);
    CHECK(summary.samples == rates.size());
    CHECK(summary.minimumBytesPerSecond == 100);
    CHECK(summary.p50BytesPerSecond == 1000);
    CHECK(summary.p95BytesPerSecond == 1900);
    CHECK(summary.p99BytesPerSecond == 2000);
    CHECK(summary.maximumBytesPerSecond == 2000);
    CHECK(!summarizeIngressRates(nullptr, 1).valid);
    rates[0] = 0;
    CHECK(!summarizeIngressRates(rates.data(), rates.size()).valid);
    CHECK(!summarizeIngressRates(
        rates.data(), kIngressTimingMaxSamples + 1U).valid);
}

void testObservationQueueIsBoundedFifoAndScrubbable() {
    ObservationQueue queue;
    Observation observation;
    for (std::size_t index = 0; index < ObservationQueue::kCapacity; ++index) {
        observation.sequence = index + 1U;
        observation.identity[0] = static_cast<std::uint8_t>(index + 1U);
        observation.identityLength = 1;
        CHECK(queue.push(observation));
    }
    CHECK(queue.full());
    CHECK(queue.size() == ObservationQueue::kCapacity);
    CHECK(queue.highWater() == ObservationQueue::kCapacity);
    CHECK(queue.pushed() == ObservationQueue::kCapacity);

    observation.sequence = 999;
    CHECK(!queue.push(observation));
    CHECK(queue.dropped() == 1);
    CHECK(queue.size() == ObservationQueue::kCapacity);

    Observation popped;
    for (std::size_t index = 0; index < 8; ++index) {
        CHECK(queue.pop(&popped));
        CHECK(popped.sequence == index + 1U);
        CHECK(popped.identityLength == 1);
    }
    CHECK(queue.size() == ObservationQueue::kCapacity - 8U);
    CHECK(queue.popped() == 8);

    for (std::size_t index = 0; index < 8; ++index) {
        observation = Observation{};
        observation.sequence = 100U + index;
        CHECK(queue.push(observation));
    }
    CHECK(queue.full());
    for (std::size_t index = 8; index < ObservationQueue::kCapacity; ++index) {
        CHECK(queue.pop(&popped));
        CHECK(popped.sequence == index + 1U);
    }
    for (std::size_t index = 0; index < 8; ++index) {
        CHECK(queue.pop(&popped));
        CHECK(popped.sequence == 100U + index);
    }
    CHECK(queue.empty());
    CHECK(!queue.pop(&popped));
    CHECK(!queue.pop(nullptr));
    CHECK(queue.pushed() == ObservationQueue::kCapacity + 8U);
    CHECK(queue.popped() == ObservationQueue::kCapacity + 8U);

    queue.reset();
    CHECK(queue.empty());
    CHECK(queue.highWater() == 0);
    CHECK(queue.pushed() == 0);
    CHECK(queue.popped() == 0);
    CHECK(queue.dropped() == 0);
}

void testSessionBatchPolicyMeetsMeasuredRateAndFlushesBoundedly() {
    const SessionBatchPolicy policy;
    CHECK(validateSessionBatchPolicy(policy));
    CHECK(policy.observationCapacity == ObservationQueue::kCapacity);
    CHECK(minimumBatchBytesForRate(546, 4, 591651) == 1293);
    CHECK(minimumBatchBytesForRate(0, 4, 591651) == 0);
    CHECK(minimumBatchBytesForRate(546, 0, 591651) == 0);
    CHECK(minimumBatchBytesForRate(546, 4, 0) == 0);
    CHECK(minimumBatchBytesForRate(UINT64_MAX, 2, 1) == 0);
    CHECK(minimumBatchBytesForRate(UINT64_MAX / 2U, 1, 3) == 0);

    SessionBatchPolicy invalid = policy;
    invalid.observationCapacity = 0;
    CHECK(!validateSessionBatchPolicy(invalid));
    invalid = policy;
    invalid.observationCapacity = ObservationQueue::kCapacity + 1U;
    CHECK(!validateSessionBatchPolicy(invalid));
    invalid = policy;
    invalid.targetEncodedBytes = kSegmentFooterBytes;
    CHECK(!validateSessionBatchPolicy(invalid));
    invalid = policy;
    invalid.maximumLatencyUs = 0;
    CHECK(!validateSessionBatchPolicy(invalid));

    CHECK(sessionBatchTrigger(policy, 0, 0, 0, 0, false, false) ==
          SessionBatchTrigger::None);
    CHECK(sessionBatchTrigger(policy, 1, 1024, 1000, 2000, false, false) ==
          SessionBatchTrigger::None);
    CHECK(sessionBatchTrigger(policy, policy.observationCapacity, 1024,
                              1000, 2000, false, false) ==
          SessionBatchTrigger::Capacity);
    CHECK(sessionBatchTrigger(policy, 1, policy.targetEncodedBytes,
                              1000, 2000, false, false) ==
          SessionBatchTrigger::EncodedSize);
    CHECK(sessionBatchTrigger(policy, 1, 1024, 1000,
                              1000 + policy.maximumLatencyUs,
                              false, false) == SessionBatchTrigger::Latency);
    CHECK(sessionBatchTrigger(policy, 1, policy.targetEncodedBytes,
                              1000, 1000 + policy.maximumLatencyUs,
                              true, false) == SessionBatchTrigger::Stop);
    CHECK(sessionBatchTrigger(policy, policy.observationCapacity,
                              policy.targetEncodedBytes, 1000,
                              1000 + policy.maximumLatencyUs,
                              true, true) == SessionBatchTrigger::SafeShutdown);
    CHECK(std::strcmp(sessionBatchTriggerName(SessionBatchTrigger::Capacity),
                      "capacity") == 0);
}

void testInventoryIsFixedAndRejectsDuplicates() {
    HardwareInventory inventory;
    CHECK(inventory.add({"board.profile", CapabilityState::Available, "runtime", "match"}));
    CHECK(!inventory.add({"board.profile", CapabilityState::Fault, "runtime", "duplicate"}));
    CHECK(inventory.size() == 1);
    CHECK(inventory.find("missing") == nullptr);
    CHECK(inventory.find("board.profile") != nullptr);
    CHECK(std::strcmp(capabilityStateName(CapabilityState::Conflicted), "conflicted") == 0);
}

void testBootReportIsBoundedAndMachineReadable() {
    BootMetrics metrics;
    metrics.version = "0.1.0-measure";
    metrics.profile = "esp32-div-v2-n16";
    metrics.profileRevision = "S1-test";
    metrics.appElfSha256 =
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    metrics.setupEnterUs = 10;
    metrics.runtimeReadyUs = 20;
    metrics.displayReadyUs = 30;
    metrics.inputReadyUs = 40;
    metrics.interactiveReadyUs = 50;
    metrics.resetReason = 1;
    metrics.flashBytes = 16777216;
    metrics.heapTotal = 387360;
    metrics.heapFree = 300000;
    metrics.heapMinimum = 290000;
    metrics.buzzerSafetyConfigured = true;
    metrics.buzzerInactive = true;
    metrics.inputDetected = true;
    metrics.inputRaw = 255;
    metrics.inputProbeAttempts = 2;
    metrics.inputProbeTransientRetries = 1;
    char output[768] = {};
    CHECK(formatBootMetrics(metrics, output, sizeof(output)));
    CHECK(std::strstr(output, "\"legacy_sources\":false") != nullptr);
    CHECK(std::strstr(output,
                      "\"app_elf_sha256\":\"0123456789abcdef0123456789abcdef"
                      "0123456789abcdef0123456789abcdef\"") != nullptr);
    CHECK(std::strstr(output, "\"flash_bytes\":16777216") != nullptr);
    CHECK(std::strstr(output, "\"interactive_ready_us\":50") != nullptr);
    CHECK(std::strstr(output, "\"buzzer_safety_configured\":true") != nullptr);
    CHECK(std::strstr(output, "\"buzzer_inactive\":true") != nullptr);
    CHECK(std::strstr(output, "\"input_detected\":true") != nullptr);
    CHECK(std::strstr(output, "\"input_probe_attempts\":2") != nullptr);
    CHECK(std::strstr(output, "\"input_probe_transient_retries\":1") != nullptr);

    char tooSmall[8] = {};
    CHECK(!formatBootMetrics(metrics, tooSmall, sizeof(tooSmall)));

    const CapabilityRecord record{"storage.sd", CapabilityState::Unknown, "HW-U06",
                                  "explicit_mount_not_run"};
    CHECK(formatCapability(record, output, sizeof(output)));
    CHECK(std::strstr(output, "\"state\":\"unknown\"") != nullptr);
}

void testHilSessionBindsOneRunToTheRunningAppIdentity() {
    constexpr const char* sessionOne = "0123456789abcdef0123456789abcdef";
    constexpr const char* sessionTwo = "fedcba9876543210fedcba9876543210";
    constexpr const char* identity =
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    constexpr const char* otherIdentity =
        "1123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    HilSession session;
    CHECK(session.begin("short", identity, identity) ==
          HilSessionStatus::InvalidSessionId);
    CHECK(session.begin(sessionOne, "invalid", identity) ==
          HilSessionStatus::InvalidAppIdentity);
    CHECK(session.begin(sessionOne, otherIdentity, identity) ==
          HilSessionStatus::AppIdentityMismatch);
    CHECK(session.begin(sessionOne, identity, identity) == HilSessionStatus::Begun);
    CHECK(session.active());
    CHECK(std::strcmp(session.id(), sessionOne) == 0);
    CHECK(session.begin(sessionTwo, identity, identity) ==
          HilSessionStatus::AlreadyActive);
    CHECK(session.end(sessionTwo) == HilSessionStatus::SessionMismatch);
    CHECK(session.active());
    CHECK(session.end(sessionOne) == HilSessionStatus::Ended);
    CHECK(!session.active());
    CHECK(session.end(sessionOne) == HilSessionStatus::NotActive);
    CHECK(session.begin(sessionTwo, identity, identity) == HilSessionStatus::Begun);
    CHECK(std::strcmp(hilSessionStatusName(HilSessionStatus::Begun), "begun") == 0);
}

void testPhysicalAndDiagnosticActionsShareNavigation() {
    UiController controller;
    CHECK(controller.isRoot());
    CHECK(controller.selection() == 0);
    CHECK(uiActionFromName("down") == UiAction::Down);
    CHECK(uiActionFromName("invalid") == UiAction::Unknown);

    CHECK(controller.apply(UiAction::Down, 3, true));
    CHECK(controller.selection() == 1);
    CHECK(!controller.apply(uiActionFromName("select"), 3, false));
    CHECK(controller.isRoot());
    CHECK(controller.revision() == 2);
    CHECK(controller.apply(uiActionFromName("select"), 3, true));
    CHECK(controller.page() == 2);
    CHECK(std::strcmp(probePageName(controller.page()), "survey") == 0);
    CHECK(controller.apply(uiActionFromName("back"), 3, true));
    CHECK(controller.isRoot());
    CHECK(controller.selection() == 1);
    CHECK(controller.revision() == 4);
    controller.recordHandledAction(UiAction::Right);
    CHECK(controller.revision() == 5);
    controller.recordHandledAction(UiAction::Unknown);
    CHECK(controller.revision() == 5);
}

void testPhysicalButtonFrontendDebouncesAndMapsEveryKey() {
    Pcf8574ButtonInput input;
    input.reset(0xFF, 100);
    CHECK(Pcf8574ButtonInput::kPollPeriodMs == 5);
    CHECK(Pcf8574ButtonInput::kDebounceMs == 12);
    CHECK(Pcf8574ButtonInput::kButtonMask == 0xF8);

    // A short pulse and an invalid I2C sample cannot create an action.
    CHECK(input.sample(true, 0xBF, 105) == UiAction::Unknown);
    CHECK(input.sample(false, 0x00, 110) == UiAction::Unknown);
    CHECK(input.sample(true, 0xFF, 115) == UiAction::Unknown);
    CHECK(input.sample(true, 0xFF, 130) == UiAction::Unknown);
    CHECK(input.metrics().pressEvents == 0);
    CHECK(input.metrics().readErrors == 1);

    struct Mapping final {
        std::uint8_t raw;
        UiAction action;
    };
    constexpr Mapping mappings[] = {
        {0xBF, UiAction::Select}, {0x7F, UiAction::Up},
        {0xDF, UiAction::Down},   {0xF7, UiAction::Left},
        {0xEF, UiAction::Right},
    };
    std::uint32_t now = 140;
    for (const Mapping& mapping : mappings) {
        CHECK(input.sample(true, mapping.raw, now) == UiAction::Unknown);
        CHECK(input.sample(true, mapping.raw, now + 5) == UiAction::Unknown);
        CHECK(input.sample(true, mapping.raw, now + 15) == mapping.action);
        CHECK(input.stableRaw() == mapping.raw);

        // A held key emits exactly once, including across an invalid read.
        CHECK(input.sample(false, 0xFF, now + 20) == UiAction::Unknown);
        CHECK(input.sample(true, mapping.raw, now + 25) == UiAction::Unknown);
        CHECK(input.sample(true, 0xFF, now + 30) == UiAction::Unknown);
        CHECK(input.sample(true, 0xFF, now + 35) == UiAction::Unknown);
        CHECK(input.sample(true, 0xFF, now + 45) == UiAction::Unknown);
        CHECK(input.stableRaw() == 0xFF);
        now += 60;
    }
    CHECK(input.metrics().pressEvents == 5);
    CHECK(input.metrics().selectPresses == 1);
    CHECK(input.metrics().upPresses == 1);
    CHECK(input.metrics().downPresses == 1);
    CHECK(input.metrics().leftPresses == 1);
    CHECK(input.metrics().rightPresses == 1);
    CHECK(input.metrics().releaseEvents == 5);
    CHECK(input.metrics().stableTransitions == 10);
    CHECK(input.metrics().readErrors == 6);
    CHECK(input.metrics().maximumSampleGapMs >= 10);
}

void testPhysicalButtonFrontendRejectsAmbiguousPressesAndRecovers() {
    Pcf8574ButtonInput input;
    input.reset(0xFF, 0xFFFFFFF0U);
    const std::uint8_t selectAndUp = 0x3F;
    CHECK(input.sample(true, selectAndUp, 0xFFFFFFF5U) == UiAction::Unknown);
    CHECK(input.sample(true, selectAndUp, 0x00000005U) == UiAction::Unknown);
    CHECK(input.metrics().ambiguousPresses == 1);
    CHECK(input.metrics().pressEvents == 0);

    CHECK(input.sample(true, 0xFF, 20) == UiAction::Unknown);
    CHECK(input.sample(true, 0xFF, 35) == UiAction::Unknown);
    CHECK(input.sample(true, 0xBF, 40) == UiAction::Unknown);
    CHECK(input.sample(true, 0xBF, 55) == UiAction::Select);
    CHECK(input.metrics().pressEvents == 1);
}

void testAppCatalogProjectsCapabilityStatesBeforeLaunch() {
    HardwareInventory constrained;
    CHECK(constrained.add({"board.profile", CapabilityState::Available, "runtime", "match"}));
    CHECK(constrained.add({"radio.wifi", CapabilityState::Declared, "builtin", "not_started"}));
    CHECK(constrained.add({"storage.sd", CapabilityState::Unknown, "probe", "not_mounted"}));
    AppCatalog catalog;
    catalog.rebuild(constrained);
    CHECK(catalog.size() == 6);
    CHECK(catalog.get(0) != nullptr && catalog.get(0)->enabled);
    CHECK(std::strcmp(catalog.get(0)->id, "diagnostics") == 0);
    CHECK(catalog.get(1) != nullptr && !catalog.get(1)->enabled);
    CHECK(!catalog.get(1)->simulated);
    CHECK(std::strcmp(catalog.get(1)->reason, "passive source unavailable") == 0);
    CHECK(catalog.get(2) != nullptr && !catalog.get(2)->enabled);
    CHECK(std::strcmp(catalog.get(2)->reason, "storage unavailable") == 0);
    CHECK(catalog.get(0)->resources == resourceMask(Resource::UiForeground));
    CHECK((catalog.get(1)->resources & resourceMask(Resource::EspRf)) != 0);
    CHECK((catalog.get(2)->resources & resourceMask(Resource::Storage)) != 0);
    CHECK(catalog.get(3) != nullptr && !catalog.get(3)->enabled);
    CHECK(std::strcmp(catalog.get(3)->id, "capture") == 0);
    CHECK(catalog.get(3)->page == 4);
    CHECK(catalog.get(4) != nullptr && catalog.get(4)->enabled);
    CHECK(std::strcmp(catalog.get(4)->id, "language") == 0);
    CHECK(catalog.get(4)->page == 5);
    CHECK(catalog.get(4)->resources == resourceMask(Resource::UiForeground));
    CHECK(catalog.get(5) != nullptr && catalog.get(5)->enabled);
    CHECK(std::strcmp(catalog.get(5)->id, "self-test") == 0);
    CHECK(std::strcmp(catalog.get(5)->label, "SELF-TEST") == 0);
    CHECK(catalog.get(5)->page == 6);
    CHECK(catalog.get(5)->resources == resourceMask(Resource::UiForeground));

    HardwareInventory availableInventory;
    CHECK(availableInventory.add(
        {"board.profile", CapabilityState::Available, "runtime", "match"}));
    CHECK(availableInventory.add(
        {"radio.wifi", CapabilityState::Available, "probe", "ready"}));
    CHECK(availableInventory.add(
        {"capture.wifi_passive", CapabilityState::Available, "adapter", "ready"}));
    CHECK(availableInventory.add({"storage.sd", CapabilityState::Available, "probe", "ready"}));
    catalog.rebuild(availableInventory);
    CHECK(catalog.get(0)->enabled);
    CHECK(catalog.get(1)->enabled);
    CHECK(catalog.get(2)->enabled);
    CHECK(catalog.get(3)->enabled);
    CHECK((catalog.get(3)->resources & resourceMask(Resource::EspRf)) != 0);

    HardwareInventory simulatedInventory;
    CHECK(simulatedInventory.add(
        {"board.profile", CapabilityState::Available, "runtime", "match"}));
    CHECK(simulatedInventory.add(
        {"radio.wifi", CapabilityState::Declared, "builtin", "not_started"}));
    CHECK(simulatedInventory.add(
        {"survey.simulated", CapabilityState::Available, "golden", "rf_off"}));
    catalog.rebuild(simulatedInventory);
    CHECK(catalog.get(1)->enabled);
    CHECK(catalog.get(1)->simulated);
    CHECK(std::strcmp(catalog.get(1)->reason, "simulated / rf off") == 0);
    CHECK(catalog.get(1)->resources == resourceMask(Resource::UiForeground));

    HardwareInventory persistentSurveyInventory;
    CHECK(persistentSurveyInventory.add(
        {"board.profile", CapabilityState::Available, "runtime", "match"}));
    CHECK(persistentSurveyInventory.add(
        {"radio.wifi", CapabilityState::Declared, "builtin", "not_started"}));
    CHECK(persistentSurveyInventory.add(
        {"survey.simulated", CapabilityState::Available, "golden", "rf_off"}));
    CHECK(persistentSurveyInventory.add(
        {"survey.persistent_passive", CapabilityState::Available,
         "product_catalog", "exact_media"}));
    catalog.rebuild(persistentSurveyInventory);
    CHECK(catalog.get(1)->enabled);
    CHECK(!catalog.get(1)->simulated);
    CHECK(std::strcmp(catalog.get(1)->reason,
                      "passive / persistent") == 0);
    CHECK(catalog.get(1)->resources ==
          (resourceMask(Resource::UiForeground) |
           resourceMask(Resource::EspRf) |
           resourceMask(Resource::Storage) |
           resourceMask(Resource::RadioSpi)));

    HardwareInventory simulatedLibraryInventory;
    CHECK(simulatedLibraryInventory.add(
        {"board.profile", CapabilityState::Available, "runtime", "match"}));
    CHECK(simulatedLibraryInventory.add(
        {"library.simulated", CapabilityState::Available, "ram", "volatile"}));
    catalog.rebuild(simulatedLibraryInventory);
    CHECK(catalog.get(2)->enabled);
    CHECK(catalog.get(2)->simulated);
    CHECK(std::strcmp(catalog.get(2)->reason, "simulated / ram only") == 0);
    CHECK(catalog.get(2)->resources == resourceMask(Resource::UiForeground));

    HardwareInventory recoveredLibraryInventory;
    CHECK(recoveredLibraryInventory.add(
        {"board.profile", CapabilityState::Available, "runtime", "match"}));
    CHECK(recoveredLibraryInventory.add(
        {"library.simulated", CapabilityState::Available, "ram", "volatile"}));
    CHECK(recoveredLibraryInventory.add(
        {"library.persistent_session", CapabilityState::Available,
         "recovery", "validated_session_open"}));
    catalog.rebuild(recoveredLibraryInventory);
    CHECK(catalog.get(2)->enabled);
    CHECK(!catalog.get(2)->simulated);
    CHECK(std::strcmp(catalog.get(2)->reason, "ready") == 0);
    CHECK((catalog.get(2)->resources & resourceMask(Resource::Storage)) != 0);
    CHECK(!catalog.get(3)->enabled);
    CHECK(catalog.get(4)->enabled);
}

void testRuntimeAcquiresAtomicallyAndBackReleasesEverything() {
    ResourceBroker broker;
    const ResourceMask ui = resourceMask(Resource::UiForeground);
    const ResourceMask storage = resourceMask(Resource::Storage);
    CHECK(broker.acquire(2, ui));
    CHECK(!broker.acquire(3, ui | storage));
    CHECK(broker.ownerOf(Resource::UiForeground) == 2);
    CHECK(broker.ownerOf(Resource::Storage) == kNoOwner);
    broker.releaseAll(2);

    AppRuntime runtime(broker);
    CHECK(runtime.launch("survey", false, ui | resourceMask(Resource::EspRf)) ==
          LaunchStatus::Disabled);
    CHECK(!runtime.running());
    CHECK(runtime.activeResources() == 0);

    CHECK(broker.acquire(2, ui));
    CHECK(runtime.launch("diagnostics", true, ui) == LaunchStatus::Busy);
    CHECK(!runtime.running());
    broker.releaseAll(2);

    CHECK(runtime.launch("diagnostics", true, ui) == LaunchStatus::Started);
    CHECK(runtime.running());
    CHECK(std::strcmp(runtime.activeApp(), "diagnostics") == 0);
    CHECK(runtime.activeResources() == ui);
    CHECK(runtime.launch("library", true, ui | storage) == LaunchStatus::AlreadyRunning);
    CHECK(runtime.activeResources() == ui);
    CHECK(runtime.stop());
    CHECK(!runtime.running());
    CHECK(runtime.activeResources() == 0);
    CHECK(!runtime.stop());
    CHECK(runtime.launch("", true, ui) == LaunchStatus::InvalidDescriptor);
    CHECK(runtime.launch("diagnostics", true, 0) == LaunchStatus::InvalidDescriptor);
}

void testWifiIngressIsPassiveOnlyAndNormalizesObservations() {
    WifiScanPlan plan = defaultPassivePlan();
    CHECK(validatePassivePlan(plan));
    CHECK(plan.passive);
    CHECK(!kActiveProbeAllowed);
    CHECK(!kDriverStartedInMeasureTarget);

    plan.passive = false;
    CHECK(!validatePassivePlan(plan));
    plan = defaultPassivePlan();
    plan.directedSsid = "directed-probe";
    CHECK(!validatePassivePlan(plan));
    plan = defaultPassivePlan();
    plan.channel = 15;
    CHECK(!validatePassivePlan(plan));
    plan = defaultPassivePlan();
    plan.maxMsPerChannel = kMinimumDwellMs - 1;
    CHECK(!validatePassivePlan(plan));

    WifiScanRecord record;
    record.bssid = {0x02, 0x11, 0x22, 0x33, 0x44, 0x55};
    record.channel = 6;
    record.rssiDbm = -67;
    record.ssid = "field-ap";
    record.ssidLength = 8;
    Observation observation;
    CHECK(normalizePassiveRecord(record, 2000, &observation));
    CHECK(observation.radio == RadioKind::Wifi);
    CHECK(observation.frequencyKhz == 2437000);
    CHECK(observation.channel == 6);
    CHECK(observation.rssiDbm == -67);
    CHECK(observation.identityLength == 6);
    CHECK(observation.identity == record.bssid);
    CHECK(std::strcmp(observation.label.data(), "field-ap") == 0);

    record.channel = 0;
    CHECK(!normalizePassiveRecord(record, 2000, &observation));
    record.channel = 14;
    CHECK(channelFrequencyKhz(record.channel) == 2484000);
    record.rssiDbm = 1;
    CHECK(!normalizePassiveRecord(record, 2000, &observation));
    record.rssiDbm = -67;
    record.bssid = {};
    CHECK(!normalizePassiveRecord(record, 2000, &observation));
}

void testBleIngressIsReceiveOnlyBoundedAndNormalizesObservations() {
    using leshy1::drivers::ble::BleAdvertisementRecord;
    using leshy1::drivers::ble::BleScanPlan;

    BleScanPlan plan = leshy1::drivers::ble::defaultPassivePlan();
    CHECK(leshy1::drivers::ble::validatePassivePlan(plan));
    CHECK(plan.passive);
    CHECK(plan.windowMs <= plan.intervalMs);

    plan.passive = false;
    CHECK(!leshy1::drivers::ble::validatePassivePlan(plan));
    plan = leshy1::drivers::ble::defaultPassivePlan();
    plan.durationMs = 1500;
    CHECK(!leshy1::drivers::ble::validatePassivePlan(plan));
    plan = leshy1::drivers::ble::defaultPassivePlan();
    plan.windowMs = static_cast<std::uint16_t>(plan.intervalMs + 1U);
    CHECK(!leshy1::drivers::ble::validatePassivePlan(plan));
    plan = leshy1::drivers::ble::defaultPassivePlan();
    plan.maximumRecords = 129;
    CHECK(!leshy1::drivers::ble::validatePassivePlan(plan));

    BleAdvertisementRecord record;
    record.address = {0xc0, 0x98, 0xe5, 0x44, 0x33, 0x22};
    record.addressType = 1;
    record.rssiDbm = -61;
    record.name = "field-tag";
    record.nameLength = 9;
    Observation observation;
    CHECK(leshy1::drivers::ble::normalizePassiveRecord(
        record, 3000, &observation));
    CHECK(observation.radio == RadioKind::Ble);
    CHECK(observation.frequencyKhz == 0);
    CHECK(observation.channel == 0);
    CHECK(observation.rssiDbm == -61);
    CHECK(observation.identityLength == 6);
    CHECK(observation.identity == record.address);
    CHECK(std::strcmp(observation.label.data(), "field-tag") == 0);

    record.address = {};
    CHECK(!leshy1::drivers::ble::normalizePassiveRecord(
        record, 3000, &observation));
    record.address.fill(0xff);
    CHECK(!leshy1::drivers::ble::normalizePassiveRecord(
        record, 3000, &observation));
    record.address = {1, 2, 3, 4, 5, 6};
    record.rssiDbm = 21;
    CHECK(!leshy1::drivers::ble::normalizePassiveRecord(
        record, 3000, &observation));
    record.rssiDbm = -61;
    record.name = nullptr;
    CHECK(!leshy1::drivers::ble::normalizePassiveRecord(
        record, 3000, &observation));
}

void testSurveySessionIsOrderedBoundedAndStopIsIdempotent() {
    SurveySession session;
    Observation observation;
    observation.monotonicUs = 2000;
    CHECK(session.append(observation) == SessionStatus::NotRunning);
    CHECK(session.start("", 1000) == SessionStatus::InvalidSession);
    CHECK(session.start("bad/id", 1000) == SessionStatus::InvalidSession);
    CHECK(session.start("session-001", 1000) == SessionStatus::Started);
    CHECK(session.start("session-002", 1001) == SessionStatus::AlreadyStarted);
    CHECK(std::strcmp(session.id(), "session-001") == 0);

    for (std::size_t index = 0; index < SurveySession::kObservationCapacity; ++index) {
        observation.monotonicUs = 2000 + index;
        CHECK(session.append(observation) == SessionStatus::Appended);
    }
    CHECK(session.size() == SurveySession::kObservationCapacity);
    CHECK(session.get(0) != nullptr && session.get(0)->sequence == 1);
    CHECK(session.get(session.size() - 1) != nullptr &&
          session.get(session.size() - 1)->sequence == SurveySession::kObservationCapacity);
    CHECK(session.get(session.size()) == nullptr);

    observation.monotonicUs = 3000;
    CHECK(session.append(observation) == SessionStatus::Full);
    CHECK(session.dropped() == 1);
    CHECK(session.stop(1900) == SessionStatus::OutOfOrder);
    CHECK(session.stop(4000) == SessionStatus::Stopped);
    CHECK(session.stop(4001) == SessionStatus::AlreadyStopped);
    CHECK(session.append(observation) == SessionStatus::NotRunning);
    CHECK(std::strcmp(sessionStatusName(SessionStatus::Full), "full") == 0);
}

void testSourceDegradationKeepsOnlyCompatibleSourcesRunning() {
    using leshy1::services::survey::SourceFailureClass;
    const std::uint8_t wifi = sourceMask(RadioKind::Wifi);
    const std::uint8_t ble = sourceMask(RadioKind::Ble);

    const auto bleUnavailable = decideSourceDegradation(
        wifi | ble, 0, RadioKind::Ble, SourceFailureClass::Unavailable);
    CHECK(bleUnavailable.valid);
    CHECK(bleUnavailable.continueSession);
    CHECK(bleUnavailable.activeSourceMask == wifi);
    CHECK(bleUnavailable.unavailableSourceMask == ble);
    CHECK(bleUnavailable.windowState == SourceWindowState::Unavailable);
    CHECK(bleUnavailable.windowReason == SourceWindowReason::DriverUnavailable);
    CHECK(std::strcmp(bleUnavailable.status, "source_degraded") == 0);

    const auto wifiFault = decideSourceDegradation(
        wifi, ble, RadioKind::Wifi, SourceFailureClass::Fault);
    CHECK(wifiFault.valid);
    CHECK(!wifiFault.continueSession);
    CHECK(wifiFault.activeSourceMask == 0);
    CHECK(wifiFault.unavailableSourceMask == (wifi | ble));
    CHECK(wifiFault.windowState == SourceWindowState::Fault);
    CHECK(wifiFault.windowReason == SourceWindowReason::DriverFault);
    CHECK(std::strcmp(wifiFault.status, "all_sources_failed") == 0);

    const auto duplicateFailure = decideSourceDegradation(
        wifi, ble, RadioKind::Ble, SourceFailureClass::Unavailable);
    CHECK(!duplicateFailure.valid);
    CHECK(!duplicateFailure.continueSession);
}

void testSourceTimelineStreamsHonestDutyWindowsAndDrops() {
    SourceTimeline timeline;
    const std::uint8_t wifi = sourceMask(RadioKind::Wifi);
    const std::uint8_t ble = sourceMask(RadioKind::Ble);
    CHECK(kSupportedSourceMask == (wifi | ble));
    CHECK(timeline.start(0, 100) == SourceTimelineStatus::InvalidMask);
    CHECK(timeline.start(static_cast<std::uint8_t>(1U << 7U), 100) ==
          SourceTimelineStatus::InvalidMask);
    CHECK(timeline.start(wifi | ble, 100) == SourceTimelineStatus::Started);
    CHECK(timeline.state() == SourceTimelineState::Running);
    CHECK(timeline.selectedMask() == (wifi | ble));
    CHECK(timeline.source(RadioKind::Wifi) != nullptr &&
          timeline.source(RadioKind::Wifi)->state ==
              SourceWindowState::Scheduled);
    CHECK(timeline.recordObservation(RadioKind::Wifi, true, 105) ==
          SourceTimelineStatus::InvalidState);
    CHECK(timeline.transition(RadioKind::Wifi, SourceWindowState::Active,
                              SourceWindowReason::DutyCycle, 110) ==
          SourceTimelineStatus::InvalidReason);

    CHECK(timeline.transition(RadioKind::Wifi, SourceWindowState::Active,
                              SourceWindowReason::None, 110) ==
          SourceTimelineStatus::Transitioned);
    CHECK(timeline.recordObservation(RadioKind::Wifi, true, 120) ==
          SourceTimelineStatus::ObservationRecorded);
    CHECK(timeline.recordObservation(RadioKind::Wifi, false, 125) ==
          SourceTimelineStatus::ObservationRecorded);
    CHECK(timeline.transition(RadioKind::Ble,
                              SourceWindowState::Unavailable,
                              SourceWindowReason::DriverUnavailable, 130) ==
          SourceTimelineStatus::Transitioned);
    CHECK(timeline.transition(RadioKind::Wifi, SourceWindowState::Scheduled,
                              SourceWindowReason::DutyCycle, 140) ==
          SourceTimelineStatus::Transitioned);
    CHECK(timeline.transition(RadioKind::Ble, SourceWindowState::Active,
                              SourceWindowReason::None, 150) ==
          SourceTimelineStatus::Transitioned);
    CHECK(timeline.recordObservation(RadioKind::Ble, true, 160) ==
          SourceTimelineStatus::ObservationRecorded);
    CHECK(timeline.transition(RadioKind::Wifi, SourceWindowState::Active,
                              SourceWindowReason::None, 159) ==
          SourceTimelineStatus::OutOfOrder);
    CHECK(timeline.stop(200) == SourceTimelineStatus::Stopped);
    CHECK(timeline.state() == SourceTimelineState::Stopped);
    CHECK(timeline.queuedWindows() == 6);
    CHECK(timeline.windowHighWater() == 6);
    CHECK(timeline.overflowEvents() == 0);

    const SourceRuntimeSummary* wifiSummary = timeline.source(RadioKind::Wifi);
    const SourceRuntimeSummary* bleSummary = timeline.source(RadioKind::Ble);
    CHECK(wifiSummary != nullptr && wifiSummary->scheduledUs == 70);
    CHECK(wifiSummary != nullptr && wifiSummary->activeUs == 30);
    CHECK(wifiSummary != nullptr && wifiSummary->accepted == 1);
    CHECK(wifiSummary != nullptr && wifiSummary->dropped == 1);
    CHECK(wifiSummary != nullptr && wifiSummary->windows == 3);
    CHECK(wifiSummary != nullptr && wifiSummary->transitions == 2);
    CHECK(bleSummary != nullptr && bleSummary->scheduledUs == 30);
    CHECK(bleSummary != nullptr && bleSummary->unavailableUs == 20);
    CHECK(bleSummary != nullptr && bleSummary->activeUs == 50);
    CHECK(bleSummary != nullptr && bleSummary->accepted == 1);
    CHECK(bleSummary != nullptr && bleSummary->dropped == 0);
    CHECK(timeline.dutyPermille(RadioKind::Wifi, 200) == 300);
    CHECK(timeline.dutyPermille(RadioKind::Ble, 200) == 500);

    static constexpr std::array<RadioKind, 6> kExpectedSources{{
        RadioKind::Wifi, RadioKind::Ble, RadioKind::Wifi,
        RadioKind::Ble, RadioKind::Wifi, RadioKind::Ble,
    }};
    static constexpr std::array<SourceWindowState, 6> kExpectedStates{{
        SourceWindowState::Scheduled, SourceWindowState::Scheduled,
        SourceWindowState::Active, SourceWindowState::Unavailable,
        SourceWindowState::Scheduled, SourceWindowState::Active,
    }};
    for (std::size_t index = 0; index < kExpectedSources.size(); ++index) {
        SourceWindow window;
        CHECK(timeline.pop(&window) ==
              SourceTimelineStatus::WindowDequeued);
        CHECK(window.source == kExpectedSources[index]);
        CHECK(window.state == kExpectedStates[index]);
        CHECK(window.endedUs >= window.startedUs);
    }
    SourceWindow empty;
    CHECK(timeline.pop(&empty) == SourceTimelineStatus::Empty);
    CHECK(std::strcmp(sourceWindowStateName(SourceWindowState::Unavailable),
                      "unavailable") == 0);
    CHECK(std::strcmp(sourceWindowReasonName(
                          SourceWindowReason::DriverUnavailable),
                      "driver_unavailable") == 0);
    CHECK(std::strcmp(sourceTimelineStateName(SourceTimelineState::Stopped),
                      "stopped") == 0);
    CHECK(std::strcmp(sourceTimelineStatusName(SourceTimelineStatus::Full),
                      "full") == 0);
}

void testSourceTimelineOverflowRejectsStateChangeAndCanDrain() {
    SourceTimeline timeline;
    CHECK(timeline.start(sourceMask(RadioKind::Wifi), 1) ==
          SourceTimelineStatus::Started);
    SourceWindowState next = SourceWindowState::Active;
    for (std::size_t index = 0; index < SourceTimeline::kWindowCapacity;
         ++index) {
        CHECK(timeline.transition(RadioKind::Wifi, next,
                                  next == SourceWindowState::Active
                                      ? SourceWindowReason::None
                                      : SourceWindowReason::DutyCycle,
                                  2 + index) ==
              SourceTimelineStatus::Transitioned);
        next = next == SourceWindowState::Active
            ? SourceWindowState::Scheduled : SourceWindowState::Active;
    }
    CHECK(timeline.queuedWindows() == SourceTimeline::kWindowCapacity);
    const SourceWindowState stateBefore =
        timeline.source(RadioKind::Wifi)->state;
    CHECK(timeline.transition(RadioKind::Wifi, next,
                              next == SourceWindowState::Active
                                  ? SourceWindowReason::None
                                  : SourceWindowReason::DutyCycle,
                              18) == SourceTimelineStatus::Full);
    CHECK(timeline.source(RadioKind::Wifi)->state == stateBefore);
    CHECK(timeline.overflowEvents() == 1);
    CHECK(timeline.stop(19) == SourceTimelineStatus::Full);
    CHECK(timeline.state() == SourceTimelineState::Running);
    CHECK(timeline.overflowEvents() == 2);

    SourceWindow drained;
    CHECK(timeline.pop(&drained) == SourceTimelineStatus::WindowDequeued);
    CHECK(timeline.transition(RadioKind::Wifi, next,
                              next == SourceWindowState::Active
                                  ? SourceWindowReason::None
                                  : SourceWindowReason::DutyCycle,
                              18) == SourceTimelineStatus::Transitioned);
    CHECK(timeline.pop(&drained) == SourceTimelineStatus::WindowDequeued);
    CHECK(timeline.stop(19) == SourceTimelineStatus::Stopped);
    CHECK(timeline.source(RadioKind::Wifi)->state ==
          SourceWindowState::Stopped);
}

void testSessionTimelinePersistsBoundedHistoryAndExactAggregates() {
    const std::uint8_t wifiMask = sourceMask(RadioKind::Wifi);
    const std::uint8_t bleMask = sourceMask(RadioKind::Ble);
    SurveySession original;
    CHECK(original.start("timeline-v2", 1000) == SessionStatus::Started);
    CHECK(original.startTimeline(wifiMask | bleMask, 1000) ==
          SessionTimelineStatus::Started);

    Observation observation;
    observation.monotonicUs = 1500;
    observation.radio = RadioKind::Wifi;
    observation.frequencyKhz = 2437000;
    observation.channel = 6;
    observation.rssiDbm = -60;
    observation.identity = {0x02, 0x00, 0x00, 0x00, 0x00, 0x01};
    observation.identityLength = 6;
    std::memcpy(observation.label.data(), "ap", 3);
    observation.labelLength = 2;
    CHECK(original.append(observation) == SessionStatus::Appended);

    static constexpr std::array<SourceWindow, 5> kWindows{{
        {RadioKind::Ble, SourceWindowState::Scheduled,
         SourceWindowReason::DutyCycle, 1000, 1050, 0, 0},
        {RadioKind::Wifi, SourceWindowState::Scheduled,
         SourceWindowReason::DutyCycle, 1000, 1100, 0, 0},
        {RadioKind::Wifi, SourceWindowState::Active,
         SourceWindowReason::None, 1100, 1900, 1, 0},
        {RadioKind::Ble, SourceWindowState::Unavailable,
         SourceWindowReason::DriverUnavailable, 1050, 2000, 0, 0},
        {RadioKind::Wifi, SourceWindowState::Scheduled,
         SourceWindowReason::DutyCycle, 1900, 2000, 0, 0},
    }};
    for (const SourceWindow& window : kWindows) {
        CHECK(original.appendTimelineWindow(window) ==
              SessionTimelineStatus::Appended);
    }

    SourceRuntimeSummary wifi;
    wifi.selected = true;
    wifi.state = SourceWindowState::Stopped;
    wifi.scheduledUs = 200;
    wifi.activeUs = 800;
    wifi.accepted = 1;
    wifi.windows = 3;
    wifi.transitions = 2;
    SourceRuntimeSummary ble;
    ble.selected = true;
    ble.state = SourceWindowState::Stopped;
    ble.scheduledUs = 50;
    ble.unavailableUs = 950;
    ble.windows = 2;
    ble.transitions = 1;
    CHECK(original.stop(2100) == SessionStatus::TimelineIncomplete);
    CHECK(original.finalizeTimeline(2000, wifi, ble, 0) ==
          SessionTimelineStatus::Finalized);
    CHECK(original.stop(2100) == SessionStatus::Stopped);

    std::array<std::uint8_t, kSessionSegmentMaxBytes> segment{};
    std::array<std::uint8_t, kSessionManifestMaxBytes> manifest{};
    std::size_t segmentSize = 0;
    std::size_t manifestSize = 0;
    CHECK(encodeObservationSegment(original, segment.data(), segment.size(),
                                   &segmentSize) == SessionCodecStatus::Valid);
    CHECK(encodeSessionManifest(original, segment.data(), segmentSize,
                                manifest.data(), manifest.size(),
                                &manifestSize) == SessionCodecStatus::Valid);
    SessionManifest decodedManifest;
    CHECK(decodeSessionManifest(manifest.data(), manifestSize,
                                &decodedManifest) == SessionCodecStatus::Valid);
    CHECK(decodedManifest.schemaVersion == kTimelineSessionSchemaVersion);

    SurveySession reopened;
    CHECK(reopenSession(manifest.data(), manifestSize, segment.data(),
                        segmentSize, &reopened) == SessionCodecStatus::Valid);
    CHECK(reopened.timeline().present && reopened.timeline().finalized);
    CHECK(reopened.timeline().selectedMask == (wifiMask | bleMask));
    CHECK(reopened.timeline().totalWindows == 5);
    CHECK(reopened.timeline().evictedWindows == 0);
    CHECK(reopened.timelineWindowCount() == 5);
    CHECK(reopened.timeline().sources[0].activeUs == 800);
    CHECK(reopened.timeline().sources[0].accepted == 1);
    CHECK(reopened.timeline().sources[1].unavailableUs == 950);
    CHECK(reopened.timelineWindow(0) != nullptr &&
          reopened.timelineWindow(0)->source == RadioKind::Ble);

    char summary[768] = {};
    CHECK(formatSessionJsonSummary(reopened, summary, sizeof(summary)));
    CHECK(std::strstr(summary, "leshy.session.summary.v2") != nullptr);
    CHECK(std::strstr(summary, "\"windows\":5") != nullptr);
    CHECK(std::strstr(summary, "\"duty_permille\":800") != nullptr);

    LibraryController library;
    CHECK(library.add(reopened, 73, SessionIntegrity::Valid, true, false));
    CHECK(library.openSelected());
    CHECK(library.requestExport());
    char artifact[4096] = {};
    const LibraryExportResult exported =
        library.formatSelectedJsonExport(artifact, sizeof(artifact));
    CHECK(exported.valid());
    CHECK(std::strstr(artifact, "leshy.library.export.v1") != nullptr);
    CHECK(std::strstr(artifact, "leshy.session.summary.v2") != nullptr);
    CHECK(std::strstr(artifact, "\"windows\":5") != nullptr);
    CHECK(std::strstr(artifact, "\"retained\":5") != nullptr);
    CHECK(std::strstr(artifact, "\"timeline_windows\":[") != nullptr);
    CHECK(std::strstr(artifact, "\"source\":\"ble\"") != nullptr);
    CHECK(std::strstr(artifact, "\"reason\":\"driver_unavailable\"") != nullptr);

    for (std::size_t index = 0; index < segmentSize; ++index) {
        segment[index] ^= 1U;
        CHECK(reopenSession(manifest.data(), manifestSize, segment.data(),
                            segmentSize, &reopened) != SessionCodecStatus::Valid);
        segment[index] ^= 1U;
    }

    SurveySession bounded;
    CHECK(bounded.start("timeline-ring", 1000) == SessionStatus::Started);
    CHECK(bounded.startTimeline(wifiMask, 1000) ==
          SessionTimelineStatus::Started);
    for (std::size_t index = 0; index < 20; ++index) {
        const SourceWindow window{
            RadioKind::Wifi, SourceWindowState::Scheduled,
            SourceWindowReason::DutyCycle, 1000 + index * 10,
            1010 + index * 10, 0, 0};
        CHECK(bounded.appendTimelineWindow(window) ==
              SessionTimelineStatus::Appended);
    }
    wifi = {};
    wifi.selected = true;
    wifi.state = SourceWindowState::Stopped;
    wifi.scheduledUs = 200;
    wifi.windows = 20;
    wifi.transitions = 19;
    ble = {};
    CHECK(bounded.finalizeTimeline(1200, wifi, ble, 0) ==
          SessionTimelineStatus::Finalized);
    CHECK(bounded.stop(1200) == SessionStatus::Stopped);
    CHECK(bounded.timeline().totalWindows == 20);
    CHECK(bounded.timeline().evictedWindows == 4);
    CHECK(bounded.timelineWindowCount() == 16);
    CHECK(bounded.timelineWindow(0) != nullptr &&
          bounded.timelineWindow(0)->startedUs == 1040);
}

SurveySession stoppedSessionWithId(const char* id, std::uint64_t stoppedUs) {
    SurveySession session;
    CHECK(session.start(id, 1000) == SessionStatus::Started);
    static constexpr std::array<std::array<std::uint8_t, 6>, 3> kBssids{{
        {0x02, 0x00, 0x00, 0x00, 0x00, 0x01},
        {0x02, 0x00, 0x00, 0x00, 0x00, 0x02},
        {0x02, 0x00, 0x00, 0x00, 0x00, 0x03},
    }};
    static constexpr std::array<std::uint8_t, 3> kChannels{{1, 6, 11}};
    static constexpr std::array<std::int16_t, 3> kRssi{{-71, -55, -83}};
    static constexpr std::array<const char*, 3> kSsids{{"alpha", "bravo", "charlie"}};
    for (std::size_t index = 0; index < kBssids.size(); ++index) {
        WifiScanRecord record;
        record.bssid = kBssids[index];
        record.channel = kChannels[index];
        record.rssiDbm = kRssi[index];
        record.ssid = kSsids[index];
        record.ssidLength = std::strlen(kSsids[index]);
        Observation observation;
        CHECK(normalizePassiveRecord(record, 2000 + index, &observation));
        CHECK(session.append(observation) == SessionStatus::Appended);
    }
    CHECK(session.stop(stoppedUs) == SessionStatus::Stopped);
    return session;
}

SurveySession goldenStoppedSession() {
    return stoppedSessionWithId("golden-wifi-001", 3000);
}

void testOfflineLibraryControllerIsBoundedAndPreservesProvenance() {
    LibraryController library;
    CHECK(library.size() == 0);
    CHECK(library.view() == LibraryView::SessionList);
    CHECK(!library.openSelected());

    const SurveySession first = goldenStoppedSession();
    const SurveySession second = stoppedSessionWithId("golden-wifi-002", 4000);
    CHECK(library.add(first, 1, SessionIntegrity::RecoveredFallback, false, true));
    CHECK(!library.add(first, 1, SessionIntegrity::Valid, false, true));
    CHECK(library.add(second, 2, SessionIntegrity::Valid, false, true));
    CHECK(library.size() == 2);
    CHECK(library.selected() != nullptr);
    CHECK(library.selected()->generation == 1);
    CHECK(library.selected()->simulated);
    CHECK(!library.selected()->persistent);
    CHECK(library.selected()->integrity == SessionIntegrity::RecoveredFallback);
    CHECK(library.next());
    CHECK(library.selection() == 1);
    CHECK(!library.next());
    CHECK(library.openSelected());
    CHECK(library.view() == LibraryView::SessionDetail);
    CHECK(!library.previous());
    CHECK(library.requestExport());
    CHECK(library.view() == LibraryView::ExportReady);
    char exported[640] = {};
    const LibraryExportResult exportResult =
        library.formatSelectedJsonExport(exported, sizeof(exported));
    CHECK(exportResult.valid());
    CHECK(exportResult.bytes == std::strlen(exported));
    CHECK(std::strcmp(
              exported,
              "{\"schema\":\"leshy.library.export.v1\",\"kind\":\"artifact\","
              "\"status\":\"valid\",\"generation\":2,\"integrity\":\"valid\","
              "\"simulated\":true,\"persistent\":false,"
              "\"transport\":\"serial_ndjson\",\"storage_backend\":\"bounded_ram\","
              "\"radio_touched\":false,\"session\":{"
              "\"schema\":\"leshy.session.summary.v1\",\"id\":\"golden-wifi-002\","
              "\"started_us\":1000,\"stopped_us\":4000,\"observations\":3,"
              "\"dropped\":0,\"sources\":{\"wifi\":3}}}") == 0);
    char exportTooSmall[32] = {};
    CHECK(library.formatSelectedJsonExport(exportTooSmall, sizeof(exportTooSmall)).status ==
          LibraryExportStatus::BufferTooSmall);
    CHECK(exportTooSmall[0] == '\0');
    CHECK(library.back());
    CHECK(library.view() == LibraryView::SessionDetail);
    CHECK(library.back());
    CHECK(library.view() == LibraryView::SessionList);
    CHECK(library.previous());
    CHECK(library.selection() == 0);
    CHECK(std::strcmp(sessionIntegrityName(SessionIntegrity::Valid), "valid") == 0);

    SurveySession running;
    CHECK(running.start("running", 1) == SessionStatus::Started);
    CHECK(!library.add(running, 3, SessionIntegrity::Valid, false, true));
    library.clear();
    CHECK(library.size() == 0);
    CHECK(library.selection() == 0);
    CHECK(library.view() == LibraryView::SessionList);
    CHECK(!library.requestExport());
    CHECK(library.formatSelectedJsonExport(exported, sizeof(exported)).status ==
          LibraryExportStatus::SessionUnavailable);
    CHECK(std::strcmp(libraryExportStatusName(LibraryExportStatus::Valid), "valid") == 0);
}

void testSessionCatalogRecoversReadOnlyAndMarksFallbackIntegrity() {
    leshy1::platform::arduino::RamSessionStoreIo io;
    SessionStoreWorkspace workspace;
    SessionCatalog catalog;
    LibraryController library;
    SurveySession recovered;

    io.reset();
    SessionCatalogResult result = catalog.recoverLatest(
        io, workspace, recovered, library, true, false);
    CHECK(result.status == SessionCatalogStatus::Empty);
    CHECK(result.storeStatus == SessionStoreStatus::Empty);
    CHECK(library.size() == 0);

    const SurveySession first = stoppedSessionWithId("catalog-first", 3000);
    const SurveySession second = stoppedSessionWithId("catalog-second", 4000);
    CHECK(commitNextSession(io, workspace, first).complete());
    CHECK(commitNextSession(io, workspace, second).complete());
    const std::size_t fileSyncs = io.fileSyncs();
    const std::size_t directorySyncs = io.directorySyncs();
    CHECK(io.flipSegmentByte(2, 0));
    result = catalog.recoverLatest(io, workspace, recovered, library, true,
                                   false);
    CHECK(result.admitted());
    CHECK(result.generation == 1);
    CHECK(result.observations == 3);
    CHECK(result.integrity == SessionIntegrity::RecoveredFallback);
    CHECK(library.size() == 1);
    CHECK(library.selected() != nullptr && library.selected()->persistent);
    CHECK(library.selected() != nullptr && !library.selected()->simulated);
    CHECK(library.selected() != nullptr && library.selected()->integrity ==
                                              SessionIntegrity::RecoveredFallback);
    CHECK(library.selected() != nullptr && library.selected()->session != nullptr &&
          std::strcmp(library.selected()->session->id(), "catalog-first") == 0);
    CHECK(io.fileSyncs() == fileSyncs);
    CHECK(io.directorySyncs() == directorySyncs);
    CHECK(std::strcmp(sessionCatalogStatusName(result.status), "admitted") == 0);

    result = catalog.recoverLatest(io, workspace, recovered, library, true,
                                   false);
    CHECK(result.status == SessionCatalogStatus::Admitted);
    CHECK(library.size() == 1);

    const SessionStoreRecoveryResult duplicateRecovery =
        recoverSession(io, workspace, &workspace.validationSession);
    CHECK(duplicateRecovery.valid());
    result = catalog.admitRecovered(workspace.validationSession,
                                    duplicateRecovery, library, true, false);
    CHECK(result.status == SessionCatalogStatus::AdmissionRejected);
    CHECK(library.size() == 1);
}

void testSessionCodecCommitsCanonicalDataAndReopensOffline() {
    const SurveySession original = goldenStoppedSession();
    std::array<std::uint8_t, kSessionSegmentMaxBytes> segment{};
    std::array<std::uint8_t, kSessionManifestMaxBytes> manifest{};
    std::size_t segmentSize = 0;
    std::size_t manifestSize = 0;
    CHECK(encodeObservationSegment(original, segment.data(), segment.size(), &segmentSize) ==
          SessionCodecStatus::Valid);
    CHECK(encodeSessionManifest(original, segment.data(), segmentSize, manifest.data(),
                                manifest.size(), &manifestSize) == SessionCodecStatus::Valid);
    CHECK(manifestSize == 41);
    CHECK(crc32c(manifest.data(), manifestSize) == 0x5C35401EU);
    CHECK(segmentSize == 155);
    CHECK(crc32c(segment.data(), segmentSize) == 0x6A421EA4U);

    SessionManifest decodedManifest;
    CHECK(decodeSessionManifest(manifest.data(), manifestSize, &decodedManifest) ==
          SessionCodecStatus::Valid);
    CHECK(std::strcmp(decodedManifest.sessionId.data(), "golden-wifi-001") == 0);
    CHECK(decodedManifest.observationCount == 3);
    CHECK(decodedManifest.segmentLength == segmentSize);
    CHECK(decodedManifest.segmentCrc32c == crc32c(segment.data(), segmentSize));

    SurveySession reopened;
    CHECK(reopenSession(manifest.data(), manifestSize, segment.data(), segmentSize, &reopened) ==
          SessionCodecStatus::Valid);
    CHECK(reopened.state() == SessionState::Stopped);
    CHECK(reopened.size() == original.size());
    CHECK(std::strcmp(reopened.id(), original.id()) == 0);
    for (std::size_t index = 0; index < original.size(); ++index) {
        const Observation* expected = original.get(index);
        const Observation* actual = reopened.get(index);
        CHECK(expected != nullptr && actual != nullptr);
        if (expected != nullptr && actual != nullptr) {
            CHECK(actual->sequence == expected->sequence);
            CHECK(actual->monotonicUs == expected->monotonicUs);
            CHECK(actual->frequencyKhz == expected->frequencyKhz);
            CHECK(actual->channel == expected->channel);
            CHECK(actual->rssiDbm == expected->rssiDbm);
            CHECK(actual->identity == expected->identity);
            CHECK(std::strcmp(actual->label.data(), expected->label.data()) == 0);
        }
    }

    char summary[256] = {};
    CHECK(formatSessionJsonSummary(reopened, summary, sizeof(summary)));
    CHECK(std::strcmp(summary,
                      "{\"schema\":\"leshy.session.summary.v1\","
                      "\"id\":\"golden-wifi-001\",\"started_us\":1000,"
                      "\"stopped_us\":3000,\"observations\":3,\"dropped\":0,"
                      "\"sources\":{\"wifi\":3}}") == 0);
    char tooSmall[16] = {};
    CHECK(!formatSessionJsonSummary(reopened, tooSmall, sizeof(tooSmall)));

    HeadRecord head{1, static_cast<std::uint32_t>(manifestSize),
                    crc32c(manifest.data(), manifestSize)};
    std::uint8_t headWire[kHeadWireSize] = {};
    CHECK(encodeHead(head, headWire, sizeof(headWire)));
    const RecoveryResult recovery =
        recoverHead({headWire, sizeof(headWire),
                     {true, static_cast<std::uint32_t>(manifestSize),
                      crc32c(manifest.data(), manifestSize)}},
                    {});
    CHECK(recovery.choice == RecoveryChoice::A);

    for (std::size_t byte = 0; byte < manifestSize; ++byte) {
        for (std::uint8_t bit = 0; bit < 8; ++bit) {
            manifest[byte] ^= static_cast<std::uint8_t>(1U << bit);
            const RecoveryResult corrupted =
                recoverHead({headWire, sizeof(headWire),
                             {true, static_cast<std::uint32_t>(manifestSize),
                              crc32c(manifest.data(), manifestSize)}},
                            {});
            CHECK(corrupted.choice == RecoveryChoice::None);
            manifest[byte] ^= static_cast<std::uint8_t>(1U << bit);
        }
    }

    for (std::size_t size = 0; size < segmentSize; ++size) {
        CHECK(reopenSession(manifest.data(), manifestSize, segment.data(), size, &reopened) !=
              SessionCodecStatus::Valid);
    }
    for (std::size_t index = 0; index < segmentSize; ++index) {
        segment[index] ^= 1U;
        CHECK(reopenSession(manifest.data(), manifestSize, segment.data(), segmentSize,
                            &reopened) != SessionCodecStatus::Valid);
        segment[index] ^= 1U;
    }

    std::array<std::uint8_t, kSessionManifestMaxBytes> futureManifest = manifest;
    CHECK(manifestSize > 2);
    futureManifest[2] = kWifiFrameSessionSchemaVersion + 1U;
    CHECK(decodeSessionManifest(futureManifest.data(), manifestSize, &decodedManifest) ==
          SessionCodecStatus::UnsupportedSchema);
    futureManifest = manifest;
    futureManifest[manifestSize] = 0;
    CHECK(decodeSessionManifest(futureManifest.data(), manifestSize + 1, &decodedManifest) ==
          SessionCodecStatus::TrailingData);

    std::size_t ignored = 0;
    CHECK(encodeObservationSegment(original, segment.data(), 8, &ignored) ==
          SessionCodecStatus::BufferTooSmall);
    CHECK(encodeSessionManifest(original, segment.data(), segmentSize, manifest.data(), 8,
                                &ignored) == SessionCodecStatus::BufferTooSmall);
    CHECK(std::strcmp(sessionCodecStatusName(SessionCodecStatus::ChecksumMismatch),
                      "checksum_mismatch") == 0);
}

void testSessionCodecRoundTripsBleWithoutInventingWifiFields() {
    SurveySession original;
    CHECK(original.start("ble-codec", 1000) == SessionStatus::Started);
    Observation advertisement;
    advertisement.monotonicUs = 2000;
    advertisement.radio = RadioKind::Ble;
    advertisement.frequencyKhz = 0;
    advertisement.channel = 0;
    advertisement.rssiDbm = -61;
    advertisement.identity = {1, 2, 3, 4, 5, 6};
    advertisement.identityLength = 6;
    std::memcpy(advertisement.label.data(), "field-tag", 10);
    advertisement.labelLength = 9;
    CHECK(original.append(advertisement) == SessionStatus::Appended);
    CHECK(original.stop(3000) == SessionStatus::Stopped);

    std::array<std::uint8_t, kSessionSegmentMaxBytes> segment{};
    std::array<std::uint8_t, kSessionManifestMaxBytes> manifest{};
    std::size_t segmentSize = 0;
    std::size_t manifestSize = 0;
    CHECK(encodeObservationSegment(original, segment.data(), segment.size(),
                                   &segmentSize) == SessionCodecStatus::Valid);
    CHECK(encodeSessionManifest(original, segment.data(), segmentSize,
                                manifest.data(), manifest.size(),
                                &manifestSize) == SessionCodecStatus::Valid);

    SurveySession reopened;
    CHECK(reopenSession(manifest.data(), manifestSize, segment.data(),
                        segmentSize, &reopened) == SessionCodecStatus::Valid);
    CHECK(reopened.size() == 1);
    const Observation* restored = reopened.get(0);
    CHECK(restored != nullptr && restored->radio == RadioKind::Ble);
    CHECK(restored != nullptr && restored->frequencyKhz == 0);
    CHECK(restored != nullptr && restored->channel == 0);
    CHECK(restored != nullptr && restored->identity == advertisement.identity);
    CHECK(restored != nullptr &&
          std::strcmp(restored->label.data(), "field-tag") == 0);
}

void testCaptureMetadataV3AndCsvExportAreCanonical() {
    const std::uint8_t wifiMask = sourceMask(RadioKind::Wifi);
    const std::uint8_t bleMask = sourceMask(RadioKind::Ble);
    SurveySession original;
    CHECK(original.start("capture-v3", 1000) == SessionStatus::Started);
    CaptureMetadata metadata;
    metadata.present = true;
    metadata.passive = true;
    metadata.wifiShowHidden = true;
    metadata.selectedSourceMask = wifiMask | bleMask;
    metadata.wifiMaxMsPerChannel = 120;
    metadata.wifiChannel = 0;
    metadata.bleDurationMs = 2000;
    metadata.bleIntervalMs = 100;
    metadata.bleWindowMs = 90;
    metadata.bleMaximumRecords = 64;
    metadata.appIdentityLength = metadata.appIdentity.size();
    for (std::size_t index = 0; index < metadata.appIdentity.size(); ++index) {
        metadata.appIdentity[index] = static_cast<std::uint8_t>(index + 1U);
    }
    CHECK(original.configureCaptureMetadata(metadata) ==
          CaptureMetadataStatus::Configured);
    CHECK(original.configureCaptureMetadata(metadata) ==
          CaptureMetadataStatus::AlreadyConfigured);
    CHECK(original.startTimeline(wifiMask | bleMask, 1000) ==
          SessionTimelineStatus::Started);

    Observation wifi;
    wifi.monotonicUs = 1200;
    wifi.radio = RadioKind::Wifi;
    wifi.frequencyKhz = 2437000;
    wifi.channel = 6;
    wifi.rssiDbm = -51;
    wifi.identity = {1, 2, 3, 4, 5, 6};
    wifi.identityLength = 6;
    std::memcpy(wifi.label.data(), "alpha", 6);
    wifi.labelLength = 5;
    CHECK(original.append(wifi) == SessionStatus::Appended);
    Observation ble;
    ble.monotonicUs = 1300;
    ble.radio = RadioKind::Ble;
    ble.rssiDbm = -70;
    ble.identity = {10, 11, 12, 13, 14, 15};
    ble.identityLength = 6;
    std::memcpy(ble.label.data(), "beacon", 7);
    ble.labelLength = 6;
    CHECK(original.append(ble) == SessionStatus::Appended);

    static constexpr std::array<SourceWindow, 5> kWindows{{
        {RadioKind::Wifi, SourceWindowState::Scheduled,
         SourceWindowReason::DutyCycle, 1000, 1100, 0, 0},
        {RadioKind::Wifi, SourceWindowState::Active,
         SourceWindowReason::None, 1100, 1400, 1, 0},
        {RadioKind::Ble, SourceWindowState::Scheduled,
         SourceWindowReason::DutyCycle, 1000, 1400, 0, 0},
        {RadioKind::Wifi, SourceWindowState::Scheduled,
         SourceWindowReason::DutyCycle, 1400, 1600, 0, 0},
        {RadioKind::Ble, SourceWindowState::Active,
         SourceWindowReason::None, 1400, 1600, 1, 0},
    }};
    for (const SourceWindow& window : kWindows) {
        CHECK(original.appendTimelineWindow(window) ==
              SessionTimelineStatus::Appended);
    }
    SourceRuntimeSummary wifiSummary;
    wifiSummary.selected = true;
    wifiSummary.state = SourceWindowState::Stopped;
    wifiSummary.scheduledUs = 300;
    wifiSummary.activeUs = 300;
    wifiSummary.accepted = 1;
    wifiSummary.windows = 3;
    wifiSummary.transitions = 2;
    SourceRuntimeSummary bleSummary;
    bleSummary.selected = true;
    bleSummary.state = SourceWindowState::Stopped;
    bleSummary.scheduledUs = 400;
    bleSummary.activeUs = 200;
    bleSummary.accepted = 1;
    bleSummary.windows = 2;
    bleSummary.transitions = 1;
    CHECK(original.finalizeTimeline(1600, wifiSummary, bleSummary, 0) ==
          SessionTimelineStatus::Finalized);
    CHECK(original.stop(1700) == SessionStatus::Stopped);

    std::array<std::uint8_t, kSessionSegmentMaxBytes> segment{};
    std::array<std::uint8_t, kSessionManifestMaxBytes> manifest{};
    std::size_t segmentSize = 0;
    std::size_t manifestSize = 0;
    CHECK(encodeObservationSegment(original, segment.data(), segment.size(),
                                   &segmentSize) == SessionCodecStatus::Valid);
    CHECK(encodeSessionManifest(original, segment.data(), segmentSize,
                                manifest.data(), manifest.size(),
                                &manifestSize) == SessionCodecStatus::Valid);
    SessionManifest decodedManifest;
    CHECK(decodeSessionManifest(manifest.data(), manifestSize,
                                &decodedManifest) == SessionCodecStatus::Valid);
    CHECK(decodedManifest.schemaVersion == kSessionSchemaVersion);

    SurveySession reopened;
    CHECK(reopenSession(manifest.data(), manifestSize, segment.data(),
                        segmentSize, &reopened) == SessionCodecStatus::Valid);
    CHECK(reopened.captureMetadata().present);
    CHECK(reopened.captureMetadata().selectedSourceMask == (wifiMask | bleMask));
    CHECK(reopened.captureMetadata().wifiShowHidden);
    CHECK(reopened.captureMetadata().wifiMaxMsPerChannel == 120);
    CHECK(reopened.captureMetadata().bleDurationMs == 2000);
    CHECK(reopened.captureMetadata().bleIntervalMs == 100);
    CHECK(reopened.captureMetadata().bleWindowMs == 90);
    CHECK(reopened.captureMetadata().bleMaximumRecords == 64);
    CHECK(reopened.captureMetadata().appIdentity == metadata.appIdentity);
    CHECK(!reopened.captureMetadata().framePayloadCaptured);
    CHECK(reopened.captureMetadata().framePayloadBytes == 0);

    LibraryController library;
    CHECK(library.add(reopened, 82, SessionIntegrity::Valid, true, false));
    CHECK(library.openSelected());
    CHECK(library.requestExport());
    char capture[1600] = {};
    CHECK(library.formatSelectedCaptureMetadata(
              capture, sizeof(capture)).valid());
    CHECK(std::strstr(capture, "leshy.capture.metadata.v1") != nullptr);
    CHECK(std::strstr(capture, "\"immutable\":true") != nullptr);
    CHECK(std::strstr(capture, "\"wifi\":1,\"ble\":1") != nullptr);
    CHECK(std::strstr(capture, "0102030405060708090a0b0c0d0e0f10") != nullptr);
    CHECK(std::strstr(capture, "\"csv_observations\":\"available\"") != nullptr);
    CHECK(std::strstr(capture, "\"pcap\":\"unavailable_no_frame_payload\"") != nullptr);

    char csv[256] = {};
    const auto header = library.formatSelectedCsvHeader(csv, sizeof(csv));
    CHECK(header.valid());
    CHECK(std::strcmp(
              csv,
              "session_id,sequence,monotonic_us,radio,frequency_khz,channel,"
              "rssi_dbm,identity_hex,label_hex\r\n") == 0);
    CHECK(library.formatSelectedCsvRow(0, csv, sizeof(csv)).valid());
    CHECK(std::strcmp(csv,
                      "capture-v3,1,1200,wifi,2437000,6,-51,"
                      "010203040506,616c706861\r\n") == 0);
    CHECK(library.formatSelectedCsvRow(1, csv, sizeof(csv)).valid());
    CHECK(std::strcmp(csv,
                      "capture-v3,2,1300,ble,0,0,-70,"
                      "0a0b0c0d0e0f,626561636f6e\r\n") == 0);
    CHECK(library.formatSelectedCsvRow(2, csv, sizeof(csv)).status ==
          LibraryExportStatus::RecordOutOfRange);
    CHECK(library.formatSelectedPcapStatus(csv, sizeof(csv)).valid());
    CHECK(std::strstr(csv, "unavailable_no_frame_payload") != nullptr);

    CaptureMetadata invalid = metadata;
    invalid.framePayloadCaptured = true;
    invalid.framePayloadBytes = 1;
    SurveySession rejected;
    CHECK(rejected.start("capture-invalid", 1) == SessionStatus::Started);
    CHECK(rejected.configureCaptureMetadata(invalid) ==
          CaptureMetadataStatus::InvalidMetadata);
    CHECK(std::strcmp(captureMetadataStatusName(
                          CaptureMetadataStatus::Configured),
                      "configured") == 0);
}

struct PcapMemorySink final {
    std::vector<std::uint8_t> bytes;
};

bool appendPcapBytes(const std::uint8_t* data, std::size_t size, void* context) {
    auto* sink = static_cast<PcapMemorySink*>(context);
    if (sink == nullptr || (data == nullptr && size != 0U)) return false;
    sink->bytes.insert(sink->bytes.end(), data, data + size);
    return true;
}

void testWifiFrameCaptureExportsByteExactRadiotapPcap() {
    WifiFrameCapture capture;
    WifiFrameCapturePlan invalid;
    invalid.channel = 14;
    CHECK(!capture.begin(invalid, 1000000));

    WifiFrameCapturePlan plan;
    plan.channel = 0;
    plan.durationMs = 10000;
    plan.channelDwellMs = 120;
    plan.snapLength = 64;
    plan.maximumFrames = 2;
    CHECK(validateWifiFrameCapturePlan(plan));
    CHECK(capture.begin(plan, 1000000));
    CHECK(capture.stats().state == WifiFrameCaptureState::Running);

    std::array<std::uint8_t, 80> management{};
    for (std::size_t index = 0; index < management.size(); ++index) {
        management[index] = static_cast<std::uint8_t>(index);
    }
    const std::array<std::uint8_t, 4> control{{0xD4, 0x00, 0x00, 0x00}};
    CHECK(capture.append(management.data(), management.size(), 1500000, -42,
                         6, WifiFrameKind::Management, true));
    CHECK(capture.append(control.data(), control.size(), 1750000, -70, 1,
                         WifiFrameKind::Control, true));
    CHECK(!capture.append(control.data(), control.size(), 1800000, -71, 1,
                          WifiFrameKind::Control, true));
    CHECK(capture.stats().framesReported == 3);
    CHECK(capture.stats().framesAccepted == 2);
    CHECK(capture.stats().framesDroppedCapacity == 1);
    CHECK(capture.stats().framesDroppedInvalid == 0);
    CHECK(capture.stats().payloadBytes == 68);
    CHECK(capture.frame(0) != nullptr &&
          capture.frame(0)->capturedLength == 64);
    CHECK(capture.frame(0) != nullptr &&
          capture.frame(0)->originalLength == 80);
    CHECK(radiotapPcapSize(capture) == 0);
    CHECK(capture.complete(2000000));

    PcapMemorySink sink;
    const PcapExportResult result =
        writeRadiotapPcap(capture, appendPcapBytes, &sink);
    CHECK(result.valid);
    CHECK(result.framesWritten == 2);
    CHECK(result.bytesWritten == 154);
    CHECK(radiotapPcapSize(capture) == result.bytesWritten);
    CHECK(sink.bytes.size() == result.bytesWritten);
    CHECK(sink.bytes[0] == 0xD4 && sink.bytes[1] == 0xC3 &&
          sink.bytes[2] == 0xB2 && sink.bytes[3] == 0xA1);
    CHECK(sink.bytes[4] == 2 && sink.bytes[6] == 4);
    CHECK(sink.bytes[20] == 127 && sink.bytes[21] == 0);
    CHECK(sink.bytes[24] == 1 && sink.bytes[28] == 0x20 &&
          sink.bytes[29] == 0xA1 && sink.bytes[30] == 0x07);
    CHECK(sink.bytes[32] == 79 && sink.bytes[36] == 95);
    CHECK(sink.bytes[40] == 0 && sink.bytes[42] == 15);
    CHECK(sink.bytes[44] == 0x2A && sink.bytes[48] == 0x10);
    CHECK(sink.bytes[50] == 0x85 && sink.bytes[51] == 0x09);
    CHECK(sink.bytes[54] == static_cast<std::uint8_t>(-42));
    CHECK(sink.bytes[55] == 0 && sink.bytes[56] == 1);
    CHECK(std::strcmp(wifiFrameKindName(WifiFrameKind::Data), "data") == 0);
    CHECK(std::strcmp(wifiFrameCaptureStateName(capture.stats().state),
                      "complete") == 0);

    SurveySession artifact;
    CHECK(artifact.start("wifi-frames-01", 1000000) == SessionStatus::Started);
    CaptureMetadata metadata;
    metadata.present = true;
    metadata.passive = true;
    metadata.selectedSourceMask = sourceMask(RadioKind::Wifi);
    metadata.wifiMaxMsPerChannel = plan.channelDwellMs;
    metadata.wifiChannel = plan.channel;
    metadata.framePayloadCaptured = true;
    metadata.framePayloadBytes = capture.stats().payloadBytes;
    metadata.framePayloadRecords = capture.size();
    metadata.framePayloadSnapLength = plan.snapLength;
    metadata.framePayloadFormat = FramePayloadFormat::Ieee80211;
    metadata.appIdentity.fill(0xAB);
    metadata.appIdentityLength = metadata.appIdentity.size();
    CHECK(artifact.configureCaptureMetadata(metadata) ==
          CaptureMetadataStatus::Configured);
    CHECK(artifact.stop(2000000) == SessionStatus::Stopped);

    std::array<std::uint8_t, kSessionSegmentMaxBytes> segment{};
    std::array<std::uint8_t, kSessionManifestMaxBytes> manifest{};
    std::size_t segmentSize = 0;
    std::size_t manifestSize = 0;
    CHECK(encodeWifiFrameCaptureSegment(
              artifact, capture, segment.data(), segment.size(), &segmentSize) ==
          SessionCodecStatus::Valid);
    CHECK(encodeSessionManifest(
              artifact, segment.data(), segmentSize, manifest.data(),
              manifest.size(), &manifestSize) == SessionCodecStatus::Valid);
    SessionManifest decodedManifest;
    CHECK(decodeSessionManifest(manifest.data(), manifestSize,
                                &decodedManifest) == SessionCodecStatus::Valid);
    CHECK(decodedManifest.schemaVersion == kWifiFrameSessionSchemaVersion);
    SurveySession reopened;
    CHECK(reopenSession(manifest.data(), manifestSize, segment.data(),
                        segmentSize, &reopened) == SessionCodecStatus::Valid);
    CHECK(reopened.captureMetadata().framePayloadCaptured);
    CHECK(reopened.captureMetadata().framePayloadRecords == 2);
    std::array<char, 768> captureSummary{};
    CHECK(formatSessionJsonSummary(reopened, captureSummary.data(),
                                   captureSummary.size()));
    CHECK(std::strstr(captureSummary.data(), "leshy.capture.summary.v1") != nullptr);
    CHECK(std::strstr(captureSummary.data(), "\"frames\":2") != nullptr);
    PersistedWifiFrameCaptureView persisted;
    CHECK(openPersistedWifiFrameCapture(reopened, segment.data(), segmentSize,
                                        &persisted) == SessionCodecStatus::Valid);
    CHECK(persisted.frameCount() == capture.size());
    PcapMemorySink persistedSink;
    const PcapExportResult persistedPcap = writeRadiotapPcap(
        static_cast<const leshy1::domain::captures::WifiFrameSource&>(persisted),
        appendPcapBytes, &persistedSink);
    CHECK(persistedPcap.valid);
    CHECK(persistedSink.bytes == sink.bytes);
    segment[100] ^= 0x01U;
    CHECK(openPersistedWifiFrameCapture(reopened, segment.data(), segmentSize,
                                        &persisted) ==
          SessionCodecStatus::ChecksumMismatch);

    capture.reset();
    CHECK(capture.stats().state == WifiFrameCaptureState::Idle);
    CHECK(capture.size() == 0 && capture.frame(0) == nullptr);
}

class MemorySessionStoreIo final : public SessionStoreIo {
public:
    bool writeFile(const char* path, const std::uint8_t* data, std::size_t size) override {
        if (path == nullptr || (data == nullptr && size != 0)) return false;
        files[path] = std::vector<std::uint8_t>(data, data + size);
        return true;
    }

    ReadStatus readFile(const char* path, std::uint8_t* output, std::size_t capacity,
                        std::size_t* outputSize) override {
        if (path == nullptr || output == nullptr || outputSize == nullptr) {
            return ReadStatus::IoError;
        }
        const auto found = files.find(path);
        if (found == files.end()) return ReadStatus::NotFound;
        if (found->second.size() > capacity) return ReadStatus::TooLarge;
        std::memcpy(output, found->second.data(), found->second.size());
        *outputSize = found->second.size();
        return ReadStatus::Ok;
    }

    bool syncFile(const char*) override {
        if (failNextSync) {
            failNextSync = false;
            return false;
        }
        ++fileSyncs;
        return true;
    }
    bool syncDirectory() override {
        ++directorySyncs;
        return true;
    }

    std::map<std::string, std::vector<std::uint8_t>> files;
    std::size_t fileSyncs = 0;
    std::size_t directorySyncs = 0;
    bool failNextSync = false;
};

void testBoundedSessionStoreCommitsRecoversAndFallsBack() {
    char path[kSessionStorePathMax] = {};
    CHECK(formatSessionStorePath(StoreFileKind::Segment, 7, path, sizeof(path)));
    CHECK(std::strcmp(path, "segment-00000007.bin") == 0);
    CHECK(formatSessionStorePath(StoreFileKind::Manifest, UINT32_MAX, path, sizeof(path)));
    CHECK(std::strcmp(path, "manifest-4294967295.bin") == 0);
    char tooSmall[8] = {};
    CHECK(!formatSessionStorePath(StoreFileKind::Segment, 1, tooSmall, sizeof(tooSmall)));

    MemorySessionStoreIo io;
    SessionStoreWorkspace workspace;
    SurveySession reopened;
    SessionStoreRecoveryResult recovered = recoverSession(io, workspace, &reopened);
    CHECK(recovered.status == SessionStoreStatus::Empty);
    const SurveySession generationOne = goldenStoppedSession();
    SessionStoreCommitResult committed =
        commitNextSession(io, workspace, generationOne);
    CHECK(committed.complete());
    CHECK(committed.stage == CommitStage::Complete);
    CHECK(committed.publishedSlot == HeadSlot::A);
    recovered = recoverSession(io, workspace, &reopened);
    CHECK(recovered.valid());
    CHECK(recovered.choice == RecoveryChoice::A);
    CHECK(recovered.generation == 1);
    CHECK(recovered.observations == 3);
    CHECK(std::strcmp(reopened.id(), "golden-wifi-001") == 0);

    const SurveySession generationTwo = stoppedSessionWithId("golden-wifi-002", 4000);
    committed = commitNextSession(io, workspace, generationTwo);
    CHECK(committed.complete());
    recovered = recoverSession(io, workspace, &reopened);
    CHECK(recovered.valid());
    CHECK(recovered.choice == RecoveryChoice::B);
    CHECK(recovered.generation == 2);
    CHECK(std::strcmp(reopened.id(), "golden-wifi-002") == 0);
    CHECK(io.fileSyncs == 6);
    CHECK(io.directorySyncs == 6);

    std::vector<std::uint8_t>& newestSegment = io.files["segment-00000002.bin"];
    CHECK(!newestSegment.empty());
    newestSegment[0] ^= 1U;
    recovered = recoverSession(io, workspace, &reopened);
    CHECK(recovered.valid());
    CHECK(recovered.generation == 1);
    CHECK(recovered.bStatus == CandidateStatus::InvalidPayload);
    CHECK(std::strcmp(reopened.id(), "golden-wifi-001") == 0);
    newestSegment[0] ^= 1U;

    std::vector<std::uint8_t>& newestManifest = io.files["manifest-00000002.bin"];
    CHECK(!newestManifest.empty());
    newestManifest[0] ^= 1U;
    recovered = recoverSession(io, workspace, &reopened);
    CHECK(recovered.valid());
    CHECK(recovered.generation == 1);
    CHECK(recovered.bStatus == CandidateStatus::ManifestMismatch);
    newestManifest[0] ^= 1U;

    io.failNextSync = true;
    committed = commitNextSession(io, workspace, generationTwo);
    CHECK(!committed.complete());
    CHECK(committed.status == SessionStoreStatus::SyncError);
    CHECK(committed.stage == CommitStage::SyncPayloads);
    recovered = recoverSession(io, workspace, &reopened);
    CHECK(recovered.valid());
    CHECK(recovered.generation == 2);

    SurveySession running;
    CHECK(running.start("running", 1) == SessionStatus::Started);
    CHECK(commitSession(io, workspace, running, 4, HeadSlot::A).status ==
          SessionStoreStatus::SessionNotStopped);
    CHECK(recoverSession(io, workspace, nullptr).status ==
          SessionStoreStatus::InvalidArgument);
    CHECK(std::strcmp(sessionStoreStatusName(SessionStoreStatus::CorruptGeneration),
                      "corrupt_generation") == 0);

    MemorySessionStoreIo rolloverIo;
    SessionStoreWorkspace rolloverWorkspace;
    CHECK(commitSession(rolloverIo, rolloverWorkspace, generationOne, UINT32_MAX,
                        HeadSlot::A).complete());
    committed = commitNextSession(rolloverIo, rolloverWorkspace, generationTwo);
    CHECK(committed.complete());
    CHECK(committed.generation == 0);
    CHECK(committed.publishedSlot == HeadSlot::B);
    recovered = recoverSession(rolloverIo, rolloverWorkspace, &reopened);
    CHECK(recovered.valid());
    CHECK(recovered.generation == 0);
    CHECK(std::strcmp(reopened.id(), "golden-wifi-002") == 0);

    MemorySessionStoreIo corruptIo;
    corruptIo.files["head-a.bin"] = std::vector<std::uint8_t>(kHeadWireSize, 0xA5);
    SessionStoreWorkspace corruptWorkspace;
    recovered = recoverSession(corruptIo, corruptWorkspace, &reopened);
    CHECK(recovered.status == SessionStoreStatus::NoGeneration);
    const std::size_t corruptFileCount = corruptIo.files.size();
    committed = commitNextSession(corruptIo, corruptWorkspace, generationOne);
    CHECK(committed.status == SessionStoreStatus::NoGeneration);
    CHECK(corruptIo.files.size() == corruptFileCount);

    MemorySessionStoreIo sustainedIo;
    SessionStoreWorkspace sustainedWorkspace;
    for (std::uint32_t generation = 1; generation <= 32; ++generation) {
        const SessionStoreCommitResult next =
            commitNextSession(sustainedIo, sustainedWorkspace, generationOne);
        CHECK(next.complete());
        CHECK(next.generation == generation);
    }
    recovered = recoverSession(sustainedIo, sustainedWorkspace, &reopened);
    CHECK(recovered.valid());
    CHECK(recovered.generation == 32);
    CHECK(sustainedIo.files["head-a.bin"].size() == kHeadWireSize);
    CHECK(sustainedIo.files["head-b.bin"].size() == kHeadWireSize);
    CHECK(sustainedIo.fileSyncs == 96);
    CHECK(sustainedIo.directorySyncs == 96);
}

struct BoundaryHookRecord final {
    std::size_t calls = 0;
    CommitStage stage = CommitStage::Complete;
};

void recordBoundaryHook(void* context, CommitStage stage) {
    auto* record = static_cast<BoundaryHookRecord*>(context);
    if (record == nullptr) return;
    ++record->calls;
    record->stage = stage;
}

void testSessionStoreBoundaryWrapperStopsAfterEachSuccessfulBoundary() {
    static constexpr std::array<CommitStage, 6> kBoundaries{{
        CommitStage::WritePayloads,
        CommitStage::SyncPayloads,
        CommitStage::WriteManifest,
        CommitStage::SyncManifest,
        CommitStage::WriteHead,
        CommitStage::SyncHead,
    }};
    const SurveySession generationOne = goldenStoppedSession();
    const SurveySession generationTwo = stoppedSessionWithId("reset-next", 4000);

    for (std::size_t index = 0; index < kBoundaries.size(); ++index) {
        MemorySessionStoreIo io;
        SessionStoreWorkspace workspace;
        CHECK(commitNextSession(io, workspace, generationOne).complete());
        const auto priorSegment = io.files["segment-00000001.bin"];
        const auto priorManifest = io.files["manifest-00000001.bin"];

        BoundaryHookRecord hook;
        SessionStoreBoundaryIo injecting(io, kBoundaries[index],
                                         recordBoundaryHook, &hook);
        const SessionStoreCommitResult interrupted =
            commitNextSession(injecting, workspace, generationTwo);
        CHECK(injecting.armed());
        CHECK(injecting.stopped());
        CHECK(injecting.sequenceValid());
        CHECK(injecting.boundariesReached() == index + 1);
        CHECK(injecting.lastReached() == kBoundaries[index]);
        CHECK(hook.calls == 1);
        CHECK(hook.stage == kBoundaries[index]);
        CHECK(!interrupted.complete());
        CHECK(interrupted.stage == kBoundaries[index]);

        SurveySession reopened;
        const SessionStoreRecoveryResult recovered =
            recoverSession(io, workspace, &reopened);
        CHECK(recovered.valid());
        const std::uint32_t expectedGeneration = index < 4 ? 1U : 2U;
        CHECK(recovered.generation == expectedGeneration);
        CHECK(recovered.observations == 3);
        CHECK(io.files["segment-00000001.bin"] == priorSegment);
        CHECK(io.files["manifest-00000001.bin"] == priorManifest);
        CHECK(std::strcmp(sessionStoreBoundaryName(kBoundaries[index]),
                          index == 0 ? "write_payloads" :
                          index == 1 ? "sync_payloads" :
                          index == 2 ? "write_manifest" :
                          index == 3 ? "sync_manifest" :
                          index == 4 ? "write_head" : "sync_head") == 0);
    }

    MemorySessionStoreIo passthroughIo;
    SessionStoreWorkspace passthroughWorkspace;
    SessionStoreBoundaryIo passthrough(passthroughIo, CommitStage::Complete);
    CHECK(!passthrough.armed());
    CHECK(commitNextSession(passthrough, passthroughWorkspace,
                            generationOne).complete());
    CHECK(!passthrough.stopped());
    CHECK(passthrough.sequenceValid());
    CHECK(passthrough.boundariesReached() == 6);
    CHECK(std::strcmp(sessionStoreBoundaryName(CommitStage::Complete),
                      "complete") == 0);
}

void testRamSessionStoreAdapterMatchesBoardFixtureContract() {
    leshy1::platform::arduino::RamSessionStoreIo io;
    io.reset();
    SessionStoreWorkspace workspace;
    const SurveySession session = goldenStoppedSession();
    CHECK(commitNextSession(io, workspace, session).complete());
    CHECK(commitNextSession(io, workspace, session).complete());
    SurveySession reopened;
    SessionStoreRecoveryResult recovered = recoverSession(io, workspace, &reopened);
    CHECK(recovered.valid());
    CHECK(recovered.generation == 2);
    CHECK(recovered.observations == 3);
    CHECK(io.fileSyncs() == 6);
    CHECK(io.directorySyncs() == 6);

    CHECK(io.flipSegmentByte(2, 0));
    recovered = recoverSession(io, workspace, &reopened);
    CHECK(recovered.valid());
    CHECK(recovered.generation == 1);
    CHECK(recovered.bStatus == CandidateStatus::InvalidPayload);
    CHECK(io.flipSegmentByte(2, 0));

    const SessionStoreCommitResult full = commitNextSession(io, workspace, session);
    CHECK(!full.complete());
    CHECK(full.status == SessionStoreStatus::IoError);
    CHECK(full.stage == CommitStage::WritePayloads);
    recovered = recoverSession(io, workspace, &reopened);
    CHECK(recovered.valid());
    CHECK(recovered.generation == 2);

    io.reset();
    recovered = recoverSession(io, workspace, &reopened);
    CHECK(recovered.status == SessionStoreStatus::Empty);
}

void testGoldenSurveyTraceUsesListDetailBackAndExplicitStop() {
    SurveySession session;
    SurveyController controller(session);
    CHECK(controller.start("golden-wifi-001", 1000) == SessionStatus::Started);

    static constexpr std::array<std::array<std::uint8_t, 6>, 3> kBssids{{
        {0x02, 0x00, 0x00, 0x00, 0x00, 0x01},
        {0x02, 0x00, 0x00, 0x00, 0x00, 0x02},
        {0x02, 0x00, 0x00, 0x00, 0x00, 0x03},
    }};
    static constexpr std::array<std::uint8_t, 3> kChannels{{1, 6, 11}};
    static constexpr std::array<std::int16_t, 3> kRssi{{-71, -55, -83}};
    static constexpr std::array<const char*, 3> kSsids{{"alpha", "bravo", "charlie"}};

    for (std::size_t index = 0; index < kBssids.size(); ++index) {
        WifiScanRecord record;
        record.bssid = kBssids[index];
        record.channel = kChannels[index];
        record.rssiDbm = kRssi[index];
        record.ssid = kSsids[index];
        record.ssidLength = std::strlen(kSsids[index]);
        Observation observation;
        CHECK(normalizePassiveRecord(record, 2000 + index, &observation));
        CHECK(controller.publish(observation) == SessionStatus::Appended);
    }

    CHECK(controller.session().size() == 3);
    CHECK(controller.view() == SurveyView::List);
    CHECK(controller.selection() == 0);
    CHECK(controller.selected() != nullptr && controller.selected()->channel == 1);
    CHECK(controller.next());
    CHECK(controller.selected() != nullptr && controller.selected()->frequencyKhz == 2437000);
    CHECK(controller.openSelected());
    CHECK(controller.view() == SurveyView::Detail);
    CHECK(!controller.next());
    CHECK(controller.back());
    CHECK(controller.view() == SurveyView::List);
    CHECK(controller.session().state() == SessionState::Running);
    CHECK(!controller.back());
    CHECK(controller.stop(3000) == SessionStatus::Stopped);
    CHECK(controller.stop(3001) == SessionStatus::AlreadyStopped);
    CHECK(controller.session().size() == 3);
}

void testSurveyBrowserFiltersSourcesAndBuildsBoundedRssiHistory() {
    SurveySession session;
    SurveyController controller(session);
    CHECK(controller.start("browser-001", 1000) == SessionStatus::Started);

    const std::array<std::uint8_t, 6> wifiIdentity{{1, 2, 3, 4, 5, 6}};
    const std::array<std::uint8_t, 6> bleIdentity{{6, 5, 4, 3, 2, 1}};
    const auto append = [&](RadioKind radio,
                            const std::array<std::uint8_t, 6>& identity,
                            std::int16_t rssi, std::uint64_t atUs) {
        Observation observation;
        observation.monotonicUs = atUs;
        observation.radio = radio;
        observation.identity = identity;
        observation.identityLength = 6;
        observation.rssiDbm = rssi;
        CHECK(controller.publish(observation) == SessionStatus::Appended);
    };
    append(RadioKind::Wifi, wifiIdentity, -70, 1100);
    append(RadioKind::Ble, bleIdentity, -82, 1200);
    append(RadioKind::Wifi, wifiIdentity, -55, 1300);
    append(RadioKind::Ble, bleIdentity, -61, 1400);

    CHECK(controller.visibleSize() == 4);
    CHECK(controller.filter() == SurveyFilter::All);
    CHECK(std::strcmp(surveyViewName(controller.view()), "list") == 0);
    CHECK(std::strcmp(surveyFilterName(controller.filter()), "all") == 0);
    CHECK(controller.previous());
    CHECK(controller.filterFocused());
    CHECK(controller.selected() == nullptr);
    CHECK(controller.openSelected());
    CHECK(controller.view() == SurveyView::Filter);
    CHECK(controller.next());
    CHECK(controller.draftFilter() == SurveyFilter::Wifi);
    CHECK(controller.activateFilter());
    CHECK(controller.filter() == SurveyFilter::Wifi);
    CHECK(controller.visibleSize() == 2);
    CHECK(controller.filterFocused());
    CHECK(controller.next());
    CHECK(!controller.filterFocused());
    CHECK(controller.selected() != nullptr &&
          controller.selected()->radio == RadioKind::Wifi);
    ObservationHistory history = controller.selectedHistory();
    CHECK(history.valid);
    CHECK(history.sampleCount == 2);
    CHECK(history.retainedSamples == 2);
    CHECK(history.minimumRssiDbm == -70);
    CHECK(history.maximumRssiDbm == -55);
    CHECK(history.latestRssiDbm == -55);
    CHECK(history.samples[0] == -70 && history.samples[1] == -55);

    CHECK(controller.previous());
    CHECK(controller.filterFocused());
    CHECK(controller.openSelected());
    CHECK(controller.next());
    CHECK(controller.draftFilter() == SurveyFilter::Ble);
    CHECK(controller.activateFilter());
    CHECK(controller.visibleSize() == 2);
    CHECK(controller.next());
    CHECK(controller.openSelected());
    CHECK(controller.view() == SurveyView::Detail);
    history = controller.selectedHistory();
    CHECK(history.valid && history.sampleCount == 2);
    CHECK(history.minimumRssiDbm == -82);
    CHECK(history.maximumRssiDbm == -61);
    CHECK(history.latestRssiDbm == -61);
    CHECK(controller.back());
    CHECK(controller.view() == SurveyView::List);
}

void testSurveySourcePlanProjectsAvailabilityAndRequiresSelection() {
    HardwareInventory inventory;
    CHECK(inventory.add({"radio.wifi", CapabilityState::Declared,
                         "builtin", "driver_not_started"}));
    CHECK(inventory.add({"survey.persistent_passive",
                         CapabilityState::Available, "worker",
                         "wifi_worker_ready"}));
    CHECK(inventory.add({"radio.ble", CapabilityState::Declared,
                         "builtin", "driver_not_implemented"}));

    SurveySourceController controller;
    controller.rebuild(inventory);
    CHECK(controller.view() == SurveySetupView::Plan);
    CHECK(controller.selection() == 0);
    CHECK(controller.selectedCount() == 1);
    CHECK(controller.selectedMask() == 1);
    CHECK(controller.canStart());
    const SurveySourceOption* wifi = controller.find(SurveySourceKind::Wifi);
    const SurveySourceOption* ble = controller.find(SurveySourceKind::Ble);
    CHECK(wifi != nullptr && wifi->available() && wifi->selected);
    CHECK(wifi != nullptr && std::strcmp(wifi->reason, "wifi_worker_ready") == 0);
    CHECK(ble != nullptr && !ble->available() && !ble->selected);
    CHECK(ble != nullptr &&
          std::strcmp(ble->reason, "driver_not_implemented") == 0);

    CHECK(controller.activate() == SurveySetupActivation::OpenedSources);
    CHECK(controller.view() == SurveySetupView::Sources);
    CHECK(controller.activate() == SurveySetupActivation::SourceChanged);
    CHECK(!controller.canStart());
    CHECK(controller.next());
    CHECK(controller.activate() == SurveySetupActivation::SourceUnavailable);
    CHECK(controller.selectedMask() == 0);
    CHECK(controller.back());
    CHECK(controller.view() == SurveySetupView::Plan);
    CHECK(controller.next());
    CHECK(controller.activate() == SurveySetupActivation::OpenedSpectrum);
    CHECK(controller.next());
    CHECK(controller.activate() == SurveySetupActivation::StartBlocked);
    CHECK(controller.previous());
    CHECK(controller.previous());
    CHECK(controller.activate() == SurveySetupActivation::OpenedSources);
    CHECK(controller.activate() == SurveySetupActivation::SourceChanged);
    CHECK(controller.back());
    CHECK(controller.next());
    CHECK(controller.activate() == SurveySetupActivation::OpenedSpectrum);
    CHECK(controller.next());
    CHECK(controller.activate() == SurveySetupActivation::StartRequested);

    HardwareInventory bleOnly;
    CHECK(bleOnly.add({"radio.wifi", CapabilityState::Fault, "builtin",
                       "wifi_fault"}));
    CHECK(bleOnly.add({"radio.ble", CapabilityState::Available, "builtin",
                       "ble_ready"}));
    controller.rebuild(bleOnly);
    CHECK(controller.selectedCount() == 1);
    CHECK(controller.selectedMask() == 2);
    CHECK(controller.find(SurveySourceKind::Wifi) != nullptr &&
          controller.find(SurveySourceKind::Wifi)->state ==
              SurveySourceState::Fault);
    CHECK(controller.find(SurveySourceKind::Ble) != nullptr &&
          controller.find(SurveySourceKind::Ble)->selected);
    CHECK(std::strcmp(surveySetupViewName(SurveySetupView::Sources),
                      "sources") == 0);
    CHECK(std::strcmp(surveySourceKindName(SurveySourceKind::Ble), "ble") == 0);
    CHECK(std::strcmp(surveySourceStateName(SurveySourceState::Conflicted),
                      "conflicted") == 0);

    HardwareInventory previewInventory;
    SurveySourceController preview;
    preview.rebuild(previewInventory, true);
    CHECK(preview.simulatedPreview());
    CHECK(preview.selectedCount() == 0);
    CHECK(preview.canStart());
    CHECK(preview.activate() == SurveySetupActivation::OpenedSources);
    CHECK(preview.back());
    CHECK(preview.next());
    CHECK(preview.activate() == SurveySetupActivation::OpenedSpectrum);
    CHECK(preview.next());
    CHECK(preview.activate() == SurveySetupActivation::StartRequested);
}

void testSurveyWorkflowCommitsOnceAndPreservesPriorLibraryOnFailure() {
    leshy1::platform::arduino::RamSessionStoreIo io;
    io.reset();
    SessionStoreWorkspace workspace;
    SurveySession active;
    SurveySession reopened;
    SurveyController controller(active);
    LibraryController library;
    SurveyWorkflow workflow(controller, io, workspace, reopened, library,
                            false, true);

    CHECK(workflow.state() == SurveyWorkflowState::Setup);
    CHECK(workflow.lastStatus() == SurveyWorkflowStatus::Ready);
    CHECK(workflow.configure(true, true) ==
          SurveyWorkflowStatus::InvalidState);
    CHECK(workflow.configure(false, true) == SurveyWorkflowStatus::Ready);
    CHECK(std::strcmp(surveyWorkflowStateName(workflow.state()), "setup") == 0);
    CHECK(workflow.cancel() == SurveyWorkflowStatus::Cancelled);
    CHECK(io.fileSyncs() == 0);
    CHECK(io.directorySyncs() == 0);
    CHECK(workflow.start("product-wifi-001", 1000) ==
          SurveyWorkflowStatus::Started);
    CHECK(workflow.state() == SurveyWorkflowState::Running);
    CHECK(workflow.start("duplicate", 1001) ==
          SurveyWorkflowStatus::InvalidState);

    const SurveySession golden = goldenStoppedSession();
    for (std::size_t index = 0; index < golden.size(); ++index) {
        const Observation* source = golden.get(index);
        CHECK(source != nullptr);
        if (source != nullptr) {
            CHECK(workflow.publish(*source) == SurveyWorkflowStatus::Appended);
        }
    }
    CHECK(controller.openSelected());
    CHECK(controller.back());
    CHECK(workflow.state() == SurveyWorkflowState::Running);
    CHECK(workflow.stopAndCommit(3000) == SurveyWorkflowStatus::Committed);
    CHECK(workflow.state() == SurveyWorkflowState::Result);
    CHECK(workflow.generation() == 1);
    CHECK(workflow.lastStoreStatus() == SessionStoreStatus::Valid);
    CHECK(!workflow.persistent());
    CHECK(workflow.simulated());
    CHECK(library.size() == 1);
    CHECK(library.selected() != nullptr);
    CHECK(library.selected() != nullptr && library.selected()->generation == 1);
    CHECK(library.selected() != nullptr && library.selected()->simulated);
    CHECK(library.selected() != nullptr && !library.selected()->persistent);
    CHECK(library.selected() != nullptr && library.selected()->session != nullptr &&
          std::strcmp(library.selected()->session->id(), "product-wifi-001") == 0);
    const std::size_t firstFileSyncs = io.fileSyncs();
    const std::size_t firstDirectorySyncs = io.directorySyncs();
    CHECK(workflow.stopAndCommit(3001) ==
          SurveyWorkflowStatus::AlreadyCommitted);
    CHECK(io.fileSyncs() == firstFileSyncs);
    CHECK(io.directorySyncs() == firstDirectorySyncs);

    CHECK(workflow.resetToSetup() == SurveyWorkflowStatus::Ready);
    CHECK(library.size() == 1);
    CHECK(workflow.start("product-wifi-002", 5000) ==
          SurveyWorkflowStatus::Started);
    Observation next = *golden.get(0);
    next.monotonicUs = 6000;
    CHECK(workflow.publish(next) == SurveyWorkflowStatus::Appended);
    CHECK(workflow.stopAndCommit(7000) == SurveyWorkflowStatus::Committed);
    CHECK(workflow.generation() == 2);
    CHECK(library.size() == 1);
    CHECK(library.selected() != nullptr && library.selected()->generation == 2);
    CHECK(library.selected() != nullptr && library.selected()->session != nullptr &&
          std::strcmp(library.selected()->session->id(), "product-wifi-002") == 0);

    CHECK(workflow.resetToSetup() == SurveyWorkflowStatus::Ready);
    CHECK(workflow.configure(true, false) == SurveyWorkflowStatus::Ready);
    CHECK(workflow.start("product-wifi-aborted", 7500) ==
          SurveyWorkflowStatus::Started);
    CHECK(workflow.configure(false, true) ==
          SurveyWorkflowStatus::InvalidState);
    CHECK(workflow.cancel() == SurveyWorkflowStatus::Cancelled);
    CHECK(workflow.state() == SurveyWorkflowState::Setup);
    CHECK(library.size() == 1);
    CHECK(library.selected() != nullptr && library.selected()->generation == 2);

    CHECK(workflow.configure(false, true) == SurveyWorkflowStatus::Ready);
    CHECK(workflow.start("product-wifi-003", 8000) ==
          SurveyWorkflowStatus::Started);
    next.monotonicUs = 9000;
    CHECK(workflow.publish(next) == SurveyWorkflowStatus::Appended);
    CHECK(workflow.stopAndCommit(10000) ==
          SurveyWorkflowStatus::StoreRejected);
    CHECK(workflow.state() == SurveyWorkflowState::Error);
    CHECK(workflow.lastStoreStatus() == SessionStoreStatus::IoError);
    CHECK(library.size() == 1);
    CHECK(library.selected() != nullptr && library.selected()->generation == 2);
    CHECK(library.selected() != nullptr && library.selected()->session != nullptr &&
          std::strcmp(library.selected()->session->id(), "product-wifi-002") == 0);
    CHECK(std::strcmp(surveyWorkflowStatusName(workflow.lastStatus()),
                      "store_rejected") == 0);
}

void testSessionStoreIoRouterSwitchesOnlyTheSelectedBackend() {
    leshy1::platform::arduino::RamSessionStoreIo first;
    leshy1::platform::arduino::RamSessionStoreIo second;
    first.reset();
    second.reset();
    leshy1::storage::SessionStoreIoRouter router(first);
    CHECK(router.boundTo(first));

    SessionStoreWorkspace workspace;
    const SurveySession source = goldenStoppedSession();
    CHECK(leshy1::storage::commitNextSession(router, workspace, source).complete());
    CHECK(first.fileSyncs() == 3);
    CHECK(second.fileSyncs() == 0);

    CHECK(router.bind(second));
    CHECK(router.boundTo(second));
    CHECK(leshy1::storage::commitNextSession(router, workspace, source).complete());
    CHECK(first.fileSyncs() == 3);
    CHECK(second.fileSyncs() == 3);
}

void testSurveyPipelineQueuesDrainsDropsAndCommitsWithStopPolicy() {
    leshy1::platform::arduino::RamSessionStoreIo io;
    io.reset();
    SessionStoreWorkspace workspace;
    SurveySession active;
    SurveySession reopened;
    SurveyController controller(active);
    LibraryController library;
    SurveyWorkflow workflow(controller, io, workspace, reopened, library,
                            false, true);
    ObservationQueue queue;
    SurveyPipeline pipeline(workflow, queue);

    CHECK(pipeline.resetToSetup() == SurveyPipelineStatus::Ready);
    CHECK(pipeline.start("pipeline-first", 1000) ==
          SurveyPipelineStatus::Started);
    const SurveySession golden = goldenStoppedSession();
    for (std::size_t index = 0; index < golden.size(); ++index) {
        const Observation* source = golden.get(index);
        CHECK(source != nullptr);
        if (source != nullptr) {
            CHECK(pipeline.enqueue(*source) == SurveyPipelineStatus::Queued);
        }
    }
    SurveyPipelineProgress progress = pipeline.progress();
    CHECK(progress.received == 3);
    CHECK(progress.queued == 3);
    CHECK(progress.forwarded == 0);
    CHECK(progress.dropped == 0);
    CHECK(progress.queueDepth == 3);
    CHECK(progress.queueHighWater == 3);
    CHECK(progress.trigger == SessionBatchTrigger::None);
    CHECK(pipeline.drain(2) == SurveyPipelineStatus::Drained);
    progress = pipeline.progress();
    CHECK(progress.forwarded == 2);
    CHECK(progress.queueDepth == 1);
    CHECK(pipeline.drain(0) == SurveyPipelineStatus::InvalidState);
    CHECK(pipeline.drain(ObservationQueue::kCapacity) ==
          SurveyPipelineStatus::Drained);
    CHECK(pipeline.stopAndCommit(4000) == SurveyPipelineStatus::Committed);
    progress = pipeline.progress();
    CHECK(progress.forwarded == 3);
    CHECK(progress.queueDepth == 0);
    CHECK(progress.trigger == SessionBatchTrigger::Stop);
    CHECK(workflow.generation() == 1);
    CHECK(library.size() == 1);
    const std::size_t fileSyncs = io.fileSyncs();
    const std::size_t directorySyncs = io.directorySyncs();
    CHECK(pipeline.stopAndCommit(4001) ==
          SurveyPipelineStatus::AlreadyCommitted);
    CHECK(io.fileSyncs() == fileSyncs);
    CHECK(io.directorySyncs() == directorySyncs);

    CHECK(pipeline.resetToSetup() == SurveyPipelineStatus::Ready);
    CHECK(pipeline.start("pipeline-capacity", 5000) ==
          SurveyPipelineStatus::Started);
    Observation observation = *golden.get(0);
    for (std::size_t index = 0;
         index < SurveySession::kObservationCapacity + 1U; ++index) {
        observation.monotonicUs = 6000 + index;
        const SurveyPipelineStatus status = pipeline.enqueue(observation);
        CHECK(status == (index < SurveySession::kObservationCapacity
                             ? SurveyPipelineStatus::Queued
                             : SurveyPipelineStatus::Dropped));
    }
    progress = pipeline.progress();
    CHECK(progress.received == SurveySession::kObservationCapacity + 1U);
    CHECK(progress.queued == SurveySession::kObservationCapacity);
    CHECK(progress.dropped == 1);
    CHECK(progress.queueDepth == SurveySession::kObservationCapacity);
    CHECK(progress.queueHighWater == SurveySession::kObservationCapacity);
    CHECK(pipeline.stopAndCommit(8000) == SurveyPipelineStatus::Committed);
    progress = pipeline.progress();
    CHECK(progress.forwarded == SurveySession::kObservationCapacity);
    CHECK(progress.dropped == 1);
    CHECK(progress.rejected == 0);
    CHECK(progress.trigger == SessionBatchTrigger::Stop);
    CHECK(workflow.generation() == 2);
    CHECK(library.selected() != nullptr &&
          library.selected()->session != nullptr &&
          library.selected()->session->size() ==
              SurveySession::kObservationCapacity);
    CHECK(std::strcmp(surveyPipelineStatusName(pipeline.lastStatus()),
                      "committed") == 0);
}

void testProductStorePolicySeparatesReadOnlyBootFromExplicitWrites() {
    constexpr ResourceMask storeResources =
        resourceMask(Resource::Storage) | resourceMask(Resource::RadioSpi);
    MediaIdentity media{true, MediaKind::Sd, "0123456789ABCDEF", 1024U * 1024U,
                        768U * 1024U};
    ProductStoreRequest recovery;
    recovery.operation = ProductStoreOperation::RecoverCatalog;
    recovery.expectedFingerprint = "0123456789ABCDEF";
    recovery.rootPath = kProductSessionStoreRoot;
    recovery.rootExists = true;
    recovery.driverReadOnlyGuaranteed = true;
    recovery.ownedResources = storeResources;

    ProductStorePermit permit = authorizeProductStore(media, recovery);
    CHECK(permit.allowed());
    CHECK(!permit.writable);
    CHECK(permit.byteLimit == 0);
    CHECK(permit.operation == ProductStoreOperation::RecoverCatalog);
    CHECK(permit.requiredResources == storeResources);
    CHECK(std::strcmp(permit.rootPath, "/leshy/sessions/v1") == 0);
    CHECK(std::strcmp(productStoreOperationName(permit.operation),
                      "recover_catalog") == 0);

    ProductStoreRequest rejected = recovery;
    MediaIdentity missing = media;
    missing.present = false;
    CHECK(authorizeProductStore(missing, rejected).status ==
          ProductStoreAccessStatus::MissingMedia);
    MediaIdentity invalidGeometry = media;
    invalidGeometry.capacityBytes = 0;
    CHECK(authorizeProductStore(invalidGeometry, rejected).status ==
          ProductStoreAccessStatus::InvalidMediaGeometry);
    rejected.expectedFingerprint = "FEDCBA9876543210";
    CHECK(authorizeProductStore(media, rejected).status ==
          ProductStoreAccessStatus::FingerprintMismatch);
    rejected = recovery;
    rejected.rootPath = "/leshy/sessions/v10";
    CHECK(authorizeProductStore(media, rejected).status ==
          ProductStoreAccessStatus::InvalidRoot);
    rejected = recovery;
    rejected.rootExists = false;
    CHECK(authorizeProductStore(media, rejected).status ==
          ProductStoreAccessStatus::RootMissing);
    rejected = recovery;
    rejected.driverReadOnlyGuaranteed = false;
    CHECK(authorizeProductStore(media, rejected).status ==
          ProductStoreAccessStatus::ReadOnlyDriverRequired);
    rejected = recovery;
    rejected.driverWriteEnabled = true;
    CHECK(authorizeProductStore(media, rejected).status ==
          ProductStoreAccessStatus::ReadOnlyDriverRequired);
    rejected = recovery;
    rejected.formatRequested = true;
    CHECK(authorizeProductStore(media, rejected).status ==
          ProductStoreAccessStatus::FormatForbidden);
    rejected = recovery;
    rejected.ownedResources = resourceMask(Resource::Storage);
    CHECK(authorizeProductStore(media, rejected).status ==
          ProductStoreAccessStatus::ResourcesMissing);
    rejected = recovery;
    rejected.conflictingOwner = true;
    CHECK(authorizeProductStore(media, rejected).status ==
          ProductStoreAccessStatus::ResourceConflict);

    ProductStoreRequest initialize;
    initialize.operation = ProductStoreOperation::InitializeStore;
    initialize.explicitlySelected = true;
    initialize.expectedFingerprint = recovery.expectedFingerprint;
    initialize.rootPath = kProductSessionStoreRoot;
    initialize.rootExists = false;
    initialize.driverWriteEnabled = true;
    initialize.requiredBytes = 65536;
    initialize.reserveBytes = 65536;
    initialize.ownedResources = storeResources;
    permit = authorizeProductStore(media, initialize);
    CHECK(permit.allowed());
    CHECK(permit.writable);
    CHECK(permit.byteLimit == 65536);
    CHECK(permit.operation == ProductStoreOperation::InitializeStore);

    rejected = initialize;
    rejected.explicitlySelected = false;
    CHECK(authorizeProductStore(media, rejected).status ==
          ProductStoreAccessStatus::ExplicitSelectionRequired);
    rejected = initialize;
    rejected.rootExists = true;
    CHECK(authorizeProductStore(media, rejected).status ==
          ProductStoreAccessStatus::RootAlreadyExists);
    rejected = initialize;
    rejected.driverWriteEnabled = false;
    CHECK(authorizeProductStore(media, rejected).status ==
          ProductStoreAccessStatus::WritableDriverRequired);
    rejected = initialize;
    rejected.requiredBytes = 0;
    CHECK(authorizeProductStore(media, rejected).status ==
          ProductStoreAccessStatus::InvalidSize);
    rejected = initialize;
    rejected.requiredBytes = media.freeBytes;
    rejected.reserveBytes = 1;
    CHECK(authorizeProductStore(media, rejected).status ==
          ProductStoreAccessStatus::InsufficientSpace);

    ProductStoreRequest commit = initialize;
    commit.operation = ProductStoreOperation::CommitSession;
    commit.rootExists = true;
    permit = authorizeProductStore(media, commit);
    CHECK(permit.allowed());
    CHECK(permit.writable);
    CHECK(permit.operation == ProductStoreOperation::CommitSession);
    CHECK(std::strcmp(productStoreAccessStatusName(permit.status),
                      "permitted") == 0);
}

void testProductSurveyAdmissionNeverFallsBackToSimulatedOrRam() {
    constexpr ResourceMask storeResources =
        resourceMask(Resource::Storage) | resourceMask(Resource::RadioSpi);
    constexpr ResourceMask surveyResources =
        storeResources | resourceMask(Resource::EspRf);
    MediaIdentity media{true, MediaKind::Sd, "0123456789ABCDEF", 1024U * 1024U,
                        768U * 1024U};
    ProductStoreRequest storeRequest;
    storeRequest.operation = ProductStoreOperation::CommitSession;
    storeRequest.explicitlySelected = true;
    storeRequest.expectedFingerprint = "0123456789ABCDEF";
    storeRequest.rootPath = kProductSessionStoreRoot;
    storeRequest.rootExists = true;
    storeRequest.driverWriteEnabled = true;
    storeRequest.requiredBytes = 65536;
    storeRequest.reserveBytes = 65536;
    storeRequest.ownedResources = storeResources;
    const ProductStorePermit store = authorizeProductStore(media, storeRequest);
    CHECK(store.allowed());

    ProductSurveyRequest request;
    request.explicitStart = true;
    request.sourceAvailable = true;
    request.scanPlan = defaultPassivePlan();
    request.storePermit = store;
    request.ownedResources = surveyResources;
    ProductSurveyPermit permit = authorizeProductSurvey(request);
    CHECK(permit.allowed());
    CHECK(permit.passive);
    CHECK(permit.persistent);
    CHECK(!permit.simulated);
    CHECK(permit.requiredResources == surveyResources);
    CHECK(permit.selectedSourceMask == 1);
    CHECK(permit.availableSourceMask == 1);
    CHECK(permit.degradedSourceMask == 0);

    request.selectedSourceMask = 3;
    request.availableSourceMask = 1;
    permit = authorizeProductSurvey(request);
    CHECK(permit.allowed());
    CHECK(permit.selectedSourceMask == 3);
    CHECK(permit.availableSourceMask == 1);
    CHECK(permit.degradedSourceMask == 2);
    request.availableSourceMask = 3;
    permit = authorizeProductSurvey(request);
    CHECK(permit.allowed());
    request.selectedSourceMask = 2;
    request.availableSourceMask = 2;
    request.scanPlan.passive = false;
    permit = authorizeProductSurvey(request);
    CHECK(permit.allowed());
    request.scanPlan = defaultPassivePlan();
    request.selectedSourceMask = 3;
    request.availableSourceMask = 3;

    ProductSurveyRequest rejected = request;
    rejected.explicitStart = false;
    CHECK(authorizeProductSurvey(rejected).status ==
          ProductSurveyAdmissionStatus::ExplicitStartRequired);
    rejected = request;
    rejected.sourceAvailable = false;
    CHECK(authorizeProductSurvey(rejected).status ==
          ProductSurveyAdmissionStatus::SourceUnavailable);
    rejected = request;
    rejected.selectedSourceMask = 0;
    rejected.availableSourceMask = 0;
    CHECK(authorizeProductSurvey(rejected).status ==
          ProductSurveyAdmissionStatus::SourceUnavailable);
    rejected = request;
    rejected.availableSourceMask = 4;
    CHECK(authorizeProductSurvey(rejected).status ==
          ProductSurveyAdmissionStatus::SourceUnavailable);
    rejected = request;
    rejected.scanPlan.passive = false;
    CHECK(authorizeProductSurvey(rejected).status ==
          ProductSurveyAdmissionStatus::PassivePlanRejected);
    rejected = request;
    rejected.bleScanPlan.passive = false;
    CHECK(authorizeProductSurvey(rejected).status ==
          ProductSurveyAdmissionStatus::PassivePlanRejected);
    rejected = request;
    rejected.storePermit.status = ProductStoreAccessStatus::MissingMedia;
    CHECK(authorizeProductSurvey(rejected).status ==
          ProductSurveyAdmissionStatus::StoreRejected);
    rejected = request;
    rejected.storePermit.rootPath = "/leshy/sessions/v10";
    CHECK(authorizeProductSurvey(rejected).status ==
          ProductSurveyAdmissionStatus::StoreRejected);
    rejected = request;
    rejected.storePermit.requiredResources = resourceMask(Resource::Storage);
    CHECK(authorizeProductSurvey(rejected).status ==
          ProductSurveyAdmissionStatus::StoreRejected);
    rejected = request;
    rejected.storePermit.byteLimit = 0;
    CHECK(authorizeProductSurvey(rejected).status ==
          ProductSurveyAdmissionStatus::StoreRejected);
    rejected = request;
    rejected.storePermit.operation = ProductStoreOperation::RecoverCatalog;
    rejected.storePermit.writable = false;
    CHECK(authorizeProductSurvey(rejected).status ==
          ProductSurveyAdmissionStatus::WritableStoreRequired);
    rejected = request;
    rejected.ownedResources = storeResources;
    CHECK(authorizeProductSurvey(rejected).status ==
          ProductSurveyAdmissionStatus::ResourcesMissing);
    rejected = request;
    rejected.conflictingOwner = true;
    CHECK(authorizeProductSurvey(rejected).status ==
          ProductSurveyAdmissionStatus::ResourceConflict);
    CHECK(std::strcmp(productSurveyAdmissionStatusName(
                          ProductSurveyAdmissionStatus::StoreRejected),
                      "store_rejected") == 0);
}

HeadCandidate candidate(const std::uint8_t* wire, const HeadRecord& record,
                        bool present = true, bool matching = true) {
    return {wire,
            kHeadWireSize,
            {present, record.manifestLength,
             matching ? record.manifestCrc32c
                      : static_cast<std::uint32_t>(record.manifestCrc32c ^ 1U)}};
}

void testHeadEncodingAndRecoveryRejectsUncommittedData() {
    static constexpr std::uint8_t kCrcVector[] = {'1', '2', '3', '4', '5', '6', '7', '8', '9'};
    CHECK(crc32c(kCrcVector, sizeof(kCrcVector)) == 0xE3069283U);

    const HeadRecord a{10, 1200, 0x11223344U};
    const HeadRecord b{11, 1300, 0x55667788U};
    std::uint8_t aWire[kHeadWireSize] = {};
    std::uint8_t bWire[kHeadWireSize] = {};
    CHECK(encodeHead(a, aWire, sizeof(aWire)));
    CHECK(encodeHead(b, bWire, sizeof(bWire)));

    HeadRecord decoded;
    CHECK(decodeHead(aWire, sizeof(aWire), &decoded) == HeadDecodeStatus::Valid);
    CHECK(decoded.generation == 10);
    for (std::size_t size = 0; size < kHeadWireSize; ++size) {
        CHECK(decodeHead(aWire, size, &decoded) == HeadDecodeStatus::TooShort);
    }
    for (std::size_t byte = 0; byte < kHeadWireSize; ++byte) {
        for (std::uint8_t bit = 0; bit < 8; ++bit) {
            std::uint8_t corrupted[kHeadWireSize] = {};
            std::memcpy(corrupted, aWire, sizeof(corrupted));
            corrupted[byte] ^= static_cast<std::uint8_t>(1U << bit);
            CHECK(decodeHead(corrupted, sizeof(corrupted), &decoded) != HeadDecodeStatus::Valid);
        }
    }
    aWire[12] ^= 1U;
    CHECK(decodeHead(aWire, sizeof(aWire), &decoded) == HeadDecodeStatus::ChecksumMismatch);
    aWire[12] ^= 1U;

    RecoveryResult recovery = recoverHead(candidate(aWire, a), candidate(bWire, b));
    CHECK(recovery.choice == RecoveryChoice::B);
    CHECK(recovery.selected.generation == 11);

    recovery = recoverHead(candidate(aWire, a), candidate(bWire, b, false));
    CHECK(recovery.choice == RecoveryChoice::A);
    CHECK(recovery.bStatus == CandidateStatus::MissingManifest);
    recovery = recoverHead(candidate(aWire, a), candidate(bWire, b, true, false));
    CHECK(recovery.choice == RecoveryChoice::A);
    CHECK(recovery.bStatus == CandidateStatus::ManifestMismatch);

    const HeadRecord conflicting{10, 1400, 0xABCDEF01U};
    CHECK(encodeHead(conflicting, bWire, sizeof(bWire)));
    recovery = recoverHead(candidate(aWire, a), candidate(bWire, conflicting));
    CHECK(recovery.choice == RecoveryChoice::Conflict);

    const HeadRecord wrapped{0, 100, 1};
    const HeadRecord beforeWrap{0xFFFFFFFFU, 100, 1};
    CHECK(encodeHead(wrapped, aWire, sizeof(aWire)));
    CHECK(encodeHead(beforeWrap, bWire, sizeof(bWire)));
    recovery = recoverHead(candidate(aWire, wrapped), candidate(bWire, beforeWrap));
    CHECK(recovery.choice == RecoveryChoice::A);

    const HeadRecord ambiguous{0x80000000U, 100, 1};
    CHECK(encodeHead(ambiguous, aWire, sizeof(aWire)));
    const HeadRecord zero{0, 100, 1};
    CHECK(encodeHead(zero, bWire, sizeof(bWire)));
    recovery = recoverHead(candidate(aWire, ambiguous), candidate(bWire, zero));
    CHECK(recovery.choice == RecoveryChoice::Conflict);
}

class FaultBackend final : public CommitBackend {
public:
    explicit FaultBackend(CommitStage failure) : failure_(failure) {
        encodeHead(oldB_, persistedB_, sizeof(persistedB_));
    }

    bool writePayloads() override { return succeeds(CommitStage::WritePayloads); }
    bool syncPayloads() override { return succeeds(CommitStage::SyncPayloads); }
    bool writeManifest() override { return succeeds(CommitStage::WriteManifest); }
    bool syncManifest() override {
        if (!succeeds(CommitStage::SyncManifest)) return false;
        newManifestSynced_ = true;
        return true;
    }
    bool writeOlderHead(const std::uint8_t* wire, std::size_t size) override {
        if (size != kHeadWireSize) return false;
        std::memcpy(pending_, wire, size);
        if (failure_ == CommitStage::WriteHead) {
            std::memcpy(persistedB_, pending_, kHeadWireSize / 2);
            return false;
        }
        return true;
    }
    bool syncHead() override {
        if (failure_ == CommitStage::SyncHead) {
            std::memcpy(persistedB_, pending_, kHeadWireSize / 2);
            return false;
        }
        std::memcpy(persistedB_, pending_, kHeadWireSize);
        return true;
    }

    HeadCandidate bCandidate(const HeadRecord& next) const {
        HeadRecord decoded;
        if (decodeHead(persistedB_, sizeof(persistedB_), &decoded) != HeadDecodeStatus::Valid) {
            return {persistedB_, sizeof(persistedB_), {false, 0, 0}};
        }
        if (decoded.generation == next.generation && newManifestSynced_) {
            return candidate(persistedB_, next);
        }
        return candidate(persistedB_, oldB_);
    }

private:
    bool succeeds(CommitStage stage) const { return failure_ != stage; }

    CommitStage failure_;
    bool newManifestSynced_ = false;
    const HeadRecord oldB_{9, 900, 0x09090909U};
    std::uint8_t pending_[kHeadWireSize] = {};
    std::uint8_t persistedB_[kHeadWireSize] = {};
};

void testEveryCommitBoundaryPreservesAValidGeneration() {
    const HeadRecord current{10, 1000, 0x10101010U};
    const HeadRecord next{11, 1100, 0x11111111U};
    std::uint8_t currentWire[kHeadWireSize] = {};
    CHECK(encodeHead(current, currentWire, sizeof(currentWire)));
    static constexpr CommitStage kFailureStages[] = {
        CommitStage::WritePayloads, CommitStage::SyncPayloads, CommitStage::WriteManifest,
        CommitStage::SyncManifest, CommitStage::WriteHead, CommitStage::SyncHead};

    for (CommitStage stage : kFailureStages) {
        FaultBackend backend(stage);
        const CommitResult result = commitGeneration(backend, next);
        CHECK(!result.complete);
        CHECK(result.stage == stage);
        const RecoveryResult recovery =
            recoverHead(candidate(currentWire, current), backend.bCandidate(next));
        CHECK(recovery.choice == RecoveryChoice::A);
        CHECK(recovery.selected.generation == current.generation);
    }

    FaultBackend backend(CommitStage::Complete);
    const CommitResult result = commitGeneration(backend, next);
    CHECK(result.complete);
    CHECK(result.stage == CommitStage::Complete);
    const RecoveryResult recovery =
        recoverHead(candidate(currentWire, current), backend.bCandidate(next));
    CHECK(recovery.choice == RecoveryChoice::B);
    CHECK(recovery.selected.generation == next.generation);
}

void testStorageWritesRequireExactDisposableScope() {
    const MediaIdentity media{true, MediaKind::Sd, "CID-A1B2C3", 16U * 1024U * 1024U,
                              12U * 1024U * 1024U};
    const WriteRequest valid{true, "CID-A1B2C3", "run_20260816", false,
                             2U * 1024U * 1024U, 2U * 1024U * 1024U};
    WritePermit permit = authorizeScratchWrite(media, valid);
    CHECK(permit.allowed());
    CHECK(permit.status == PermitStatus::Permitted);
    CHECK(std::strcmp(permit.scratchPath, "/leshy-hil/run_20260816") == 0);
    CHECK(permit.byteLimit == valid.requiredBytes);

    MediaIdentity changedMedia = media;
    changedMedia.present = false;
    CHECK(authorizeScratchWrite(changedMedia, valid).status == PermitStatus::MissingMedia);

    WriteRequest changed = valid;
    changed.explicitlyDisposable = false;
    CHECK(authorizeScratchWrite(media, changed).status ==
          PermitStatus::ExplicitAuthorizationRequired);
    changed = valid;
    changed.expectedFingerprint = "CID/INVALID";
    CHECK(authorizeScratchWrite(media, changed).status == PermitStatus::InvalidFingerprint);
    changed = valid;
    changed.expectedFingerprint = "CID-DIFFERENT";
    CHECK(authorizeScratchWrite(media, changed).status == PermitStatus::FingerprintMismatch);
    changed = valid;
    changed.runId = "../escape";
    CHECK(authorizeScratchWrite(media, changed).status == PermitStatus::InvalidRunId);
    changed = valid;
    changed.scratchExists = true;
    CHECK(authorizeScratchWrite(media, changed).status == PermitStatus::ScratchAlreadyExists);
    changed = valid;
    changed.requiredBytes = 0;
    CHECK(authorizeScratchWrite(media, changed).status == PermitStatus::InvalidSize);
    changed = valid;
    changed.reserveBytes = UINT64_MAX;
    CHECK(authorizeScratchWrite(media, changed).status == PermitStatus::InvalidSize);
    changed = valid;
    changed.requiredBytes = 11U * 1024U * 1024U;
    CHECK(authorizeScratchWrite(media, changed).status == PermitStatus::InsufficientSpace);

    changedMedia = media;
    changedMedia.capacityBytes = changedMedia.freeBytes - 1U;
    CHECK(authorizeScratchWrite(changedMedia, valid).status == PermitStatus::InsufficientSpace);
    CHECK(std::strcmp(permitStatusName(PermitStatus::FingerprintMismatch),
                      "fingerprint_mismatch") == 0);

    ExistingScratchReadRequest readRequest;
    readRequest.explicitlySelected = true;
    readRequest.expectedFingerprint = "CID-A1B2C3";
    readRequest.runId = "run_20260816";
    readRequest.scratchExists = true;
    ReadPermit readPermit = authorizeExistingScratchRead(media, readRequest);
    CHECK(readPermit.allowed());
    CHECK(std::strcmp(readPermit.scratchPath,
                      "/leshy-hil/run_20260816") == 0);
    ExistingScratchReadRequest changedRead = readRequest;
    changedRead.explicitlySelected = false;
    CHECK(authorizeExistingScratchRead(media, changedRead).status ==
          ReadPermitStatus::ExplicitAuthorizationRequired);
    changedRead = readRequest;
    changedRead.expectedFingerprint = "CID-DIFFERENT";
    CHECK(authorizeExistingScratchRead(media, changedRead).status ==
          ReadPermitStatus::FingerprintMismatch);
    changedRead = readRequest;
    changedRead.runId = "../escape";
    CHECK(authorizeExistingScratchRead(media, changedRead).status ==
          ReadPermitStatus::InvalidRunId);
    changedRead = readRequest;
    changedRead.scratchExists = false;
    CHECK(authorizeExistingScratchRead(media, changedRead).status ==
          ReadPermitStatus::ScratchMissing);
    CHECK(std::strcmp(readPermitStatusName(ReadPermitStatus::ScratchMissing),
                      "scratch_missing") == 0);
}

class FakeReadOnlyMediaAdapter final : public ReadOnlyMediaAdapter {
public:
    explicit FakeReadOnlyMediaAdapter(MediaDiscovery discovery) : discovery_(discovery) {}
    MediaDiscovery discoverReadOnly() override { return discovery_; }

private:
    MediaDiscovery discovery_;
};

void testMediaDiscoveryBoundaryIsReadOnlyAndFailClosed() {
    MediaDiscovery boardLike;
    boardLike.kind = MediaKind::Sd;
    boardLike.status = MediaDiscoveryStatus::Unknown;
    boardLike.slotDeclared = true;
    boardLike.detectPin = 38;
    boardLike.detectSampled = true;
    boardLike.detectLevel = 1;
    boardLike.detectAuthoritative = false;
    boardLike.reason = "polarity_unverified_no_mount";
    FakeReadOnlyMediaAdapter adapter(boardLike);
    const MediaDiscovery discovered = adapter.discoverReadOnly();
    CHECK(validateMediaDiscovery(discovered) == MediaDiscoveryValidation::Valid);
    char report[768] = {};
    CHECK(formatMediaDiscoveryJson(discovered, report, sizeof(report)));
    CHECK(std::strcmp(
              report,
              "{\"schema\":\"leshy.storage.discovery.v1\",\"kind\":\"report\","
              "\"validation\":\"valid\",\"media_kind\":\"sd\","
              "\"status\":\"unknown\",\"slot_declared\":true,\"detect_pin\":38,"
              "\"detect_sampled\":true,\"detect_level\":1,"
              "\"detect_authoritative\":false,\"mount_attempted\":false,"
              "\"mounted_read_only\":false,\"filesystem\":\"unknown\","
              "\"fingerprint\":null,\"capacity_bytes\":0,\"free_bytes\":0,"
              "\"write_enabled\":false,\"guard_required\":true,"
              "\"reason\":\"polarity_unverified_no_mount\"}") == 0);

    MediaDiscovery detected = boardLike;
    detected.status = MediaDiscoveryStatus::Detected;
    detected.detectAuthoritative = true;
    detected.mountAttempted = true;
    detected.mountedReadOnly = true;
    detected.filesystem = FilesystemKind::Fat;
    detected.fingerprint = "CID-A1B2C3";
    detected.capacityBytes = 16U * 1024U * 1024U;
    detected.freeBytes = 12U * 1024U * 1024U;
    detected.reason = "read_only_mount_valid";
    CHECK(validateMediaDiscovery(detected) == MediaDiscoveryValidation::Valid);
    CHECK(formatMediaDiscoveryJson(detected, report, sizeof(report)));
    CHECK(std::strstr(report, "\"fingerprint\":\"CID-A1B2C3\"") != nullptr);

    MediaDiscovery invalid = detected;
    invalid.writeEnabled = true;
    CHECK(validateMediaDiscovery(invalid) == MediaDiscoveryValidation::WriteEnabled);
    invalid = detected;
    invalid.detectAuthoritative = false;
    CHECK(validateMediaDiscovery(invalid) ==
          MediaDiscoveryValidation::UnauthoritativePresenceClaim);
    invalid = detected;
    invalid.mountAttempted = false;
    CHECK(validateMediaDiscovery(invalid) == MediaDiscoveryValidation::MountStateInvalid);
    invalid = detected;
    invalid.fingerprint = nullptr;
    CHECK(validateMediaDiscovery(invalid) ==
          MediaDiscoveryValidation::DetectedMetadataMissing);
    invalid = detected;
    invalid.freeBytes = invalid.capacityBytes + 1;
    CHECK(validateMediaDiscovery(invalid) == MediaDiscoveryValidation::CapacityInvalid);
    invalid = boardLike;
    invalid.detectLevel = -1;
    CHECK(validateMediaDiscovery(invalid) ==
          MediaDiscoveryValidation::InvalidDetectSample);
    invalid = boardLike;
    invalid.reason = "invalid reason";
    CHECK(validateMediaDiscovery(invalid) == MediaDiscoveryValidation::InvalidReason);
    CHECK(!formatMediaDiscoveryJson(invalid, report, sizeof(report)));
    CHECK(report[0] == '\0');
    CHECK(std::strcmp(mediaDiscoveryValidationName(
                          MediaDiscoveryValidation::UnauthoritativePresenceClaim),
                      "unauthoritative_presence_claim") == 0);
}

void testReadOnlyMountAuthorizationRequiresSelectionDriverAndLeases() {
    MediaDiscovery discovery;
    discovery.kind = MediaKind::Sd;
    discovery.status = MediaDiscoveryStatus::Unknown;
    discovery.slotDeclared = true;
    discovery.detectPin = 38;
    discovery.detectSampled = true;
    discovery.detectLevel = 0;
    discovery.detectAuthoritative = false;
    discovery.reason = "polarity_unverified_no_mount";
    const ResourceMask required = resourceMask(Resource::Storage) |
                                  resourceMask(Resource::RadioSpi);
    ReadOnlyMountRequest request;
    request.explicitlySelected = true;
    request.driverReadOnlyGuaranteed = true;
    request.ownedResources = required;
    ReadOnlyMountPermit permit = authorizeReadOnlyMountAttempt(discovery, request);
    CHECK(permit.allowed());
    CHECK(permit.requiredResources == required);

    ReadOnlyMountRequest changed = request;
    changed.explicitlySelected = false;
    CHECK(authorizeReadOnlyMountAttempt(discovery, changed).status ==
          ReadOnlyMountStatus::ExplicitTargetRequired);
    changed = request;
    changed.driverReadOnlyGuaranteed = false;
    CHECK(authorizeReadOnlyMountAttempt(discovery, changed).status ==
          ReadOnlyMountStatus::DriverNotReadOnly);
    changed = request;
    changed.formatRequested = true;
    CHECK(authorizeReadOnlyMountAttempt(discovery, changed).status ==
          ReadOnlyMountStatus::FormatForbidden);
    changed = request;
    changed.ownedResources = resourceMask(Resource::Storage);
    CHECK(authorizeReadOnlyMountAttempt(discovery, changed).status ==
          ReadOnlyMountStatus::ResourcesMissing);
    changed = request;
    changed.conflictingOwner = true;
    CHECK(authorizeReadOnlyMountAttempt(discovery, changed).status ==
          ReadOnlyMountStatus::ResourceConflict);

    MediaDiscovery changedDiscovery = discovery;
    changedDiscovery.mountAttempted = true;
    CHECK(authorizeReadOnlyMountAttempt(changedDiscovery, request).status ==
          ReadOnlyMountStatus::AlreadyAttempted);
    changedDiscovery = discovery;
    changedDiscovery.slotDeclared = false;
    CHECK(authorizeReadOnlyMountAttempt(changedDiscovery, request).status ==
          ReadOnlyMountStatus::SlotUnavailable);
    changedDiscovery = discovery;
    changedDiscovery.reason = nullptr;
    CHECK(authorizeReadOnlyMountAttempt(changedDiscovery, request).status ==
          ReadOnlyMountStatus::InvalidDiscovery);
    CHECK(std::strcmp(readOnlyMountStatusName(ReadOnlyMountStatus::DriverNotReadOnly),
                      "driver_not_read_only") == 0);
}

void testSdIdentificationProtocolCannotDriftIntoWrites() {
    SdReadOnlyPlan plan = defaultSdIdentificationPlan();
    CHECK(validateSdIdentificationPlan(plan) == SdReadOnlyPlanStatus::Valid);
    char report[512] = {};
    CHECK(formatSdReadOnlyProtocolJson(plan, report, sizeof(report)));
    CHECK(std::strstr(report, "\"commands\":[0,8,55,41,58,10,9]") != nullptr);
    CHECK(std::strstr(report, "\"write_commands\":false") != nullptr);
    CHECK(std::strstr(report, "\"execution_enabled\":false") != nullptr);

    static constexpr std::array<std::uint8_t, 11> kMutatingCommands{
        24, 25, 26, 27, 28, 29, 32, 33, 38, 42, 56};
    for (const std::uint8_t command : kMutatingCommands) {
        SdReadOnlyPlan changed = plan;
        changed.commands[3] = command;
        CHECK(isMutatingSdCommand(command));
        CHECK(validateSdIdentificationPlan(changed) ==
              SdReadOnlyPlanStatus::MutatingCommand);
    }
    SdReadOnlyPlan changed = plan;
    changed.commandCount = plan.commandCount - 1;
    CHECK(validateSdIdentificationPlan(changed) == SdReadOnlyPlanStatus::InvalidCount);
    changed = plan;
    changed.commands[1] = 13;
    CHECK(validateSdIdentificationPlan(changed) ==
          SdReadOnlyPlanStatus::InvalidSequence);
    changed = plan;
    changed.maxInitAttempts = 0;
    CHECK(validateSdIdentificationPlan(changed) ==
          SdReadOnlyPlanStatus::InvalidInitBound);
    changed = plan;
    changed.maxInitAttempts = kSdMaxInitAttempts + 1;
    CHECK(validateSdIdentificationPlan(changed) ==
          SdReadOnlyPlanStatus::InvalidInitBound);
    changed = plan;
    changed.executionEnabled = true;
    CHECK(validateSdIdentificationPlan(changed) ==
          SdReadOnlyPlanStatus::ExecutionEnabled);
    CHECK(!formatSdReadOnlyProtocolJson(changed, report, sizeof(report)));
    CHECK(report[0] == '\0');
}

void testSdIdentificationParserRejectsTranscriptFaults() {
    const SdReadOnlyPlan plan = defaultSdIdentificationPlan();
    const SdIdentificationTranscript golden = goldenSdIdentificationTranscript();
    SdIdentity identity;
    CHECK(parseSdIdentification(plan, golden, &identity) == SdIdentificationStatus::Valid);
    CHECK(identity.capacityBytes == 16U * 1024U * 1024U);
    CHECK(identity.highCapacity);
    CHECK(identity.initAttempts == 3);
    const std::uint8_t crcVector[] = {'1', '2', '3', '4', '5', '6', '7', '8', '9'};
    CHECK(sdCrc16(crcVector, sizeof(crcVector)) == 0x31C3U);
    char report[640] = {};
    CHECK(formatSdIdentificationJson(identity, report, sizeof(report)));
    CHECK(std::strstr(report, "\"transport\":\"golden_fake\"") != nullptr);
    CHECK(std::strstr(report, "\"physical_spi_executed\":false") != nullptr);
    CHECK(std::strstr(report, "\"capacity_bytes\":16777216") != nullptr);

    for (std::size_t byte = 0; byte < golden.cid.size(); ++byte) {
        for (std::uint8_t bit = 0; bit < 8; ++bit) {
            SdIdentificationTranscript changed = golden;
            changed.cid[byte] ^= static_cast<std::uint8_t>(1U << bit);
            CHECK(parseSdIdentification(plan, changed, &identity) ==
                  SdIdentificationStatus::CidChecksumInvalid);
        }
    }
    for (std::size_t byte = 0; byte < golden.csd.size(); ++byte) {
        for (std::uint8_t bit = 0; bit < 8; ++bit) {
            SdIdentificationTranscript changed = golden;
            changed.csd[byte] ^= static_cast<std::uint8_t>(1U << bit);
            CHECK(parseSdIdentification(plan, changed, &identity) ==
                  SdIdentificationStatus::CsdChecksumInvalid);
        }
    }

    SdIdentificationTranscript changed = golden;
    changed.cmd0R1 = 0;
    CHECK(parseSdIdentification(plan, changed, &identity) ==
          SdIdentificationStatus::ResponseInvalid);
    changed = golden;
    changed.cmd8Echo = 0;
    CHECK(parseSdIdentification(plan, changed, &identity) ==
          SdIdentificationStatus::VoltageEchoInvalid);
    changed = golden;
    changed.initAttempts = plan.maxInitAttempts + 1;
    CHECK(parseSdIdentification(plan, changed, &identity) ==
          SdIdentificationStatus::InitAttemptsInvalid);
    changed = golden;
    changed.ocr = 0;
    CHECK(parseSdIdentification(plan, changed, &identity) ==
          SdIdentificationStatus::OcrInvalid);
    changed = golden;
    changed.cid.fill(0);
    changed.cidCrc16 = sdCrc16(changed.cid.data(), changed.cid.size());
    CHECK(parseSdIdentification(plan, changed, &identity) ==
          SdIdentificationStatus::CidInvalid);
    changed = golden;
    changed.csd[0] = 0;
    changed.csdCrc16 = sdCrc16(changed.csd.data(), changed.csd.size());
    CHECK(parseSdIdentification(plan, changed, &identity) ==
          SdIdentificationStatus::CsdUnsupported);
    SdReadOnlyPlan invalidPlan = plan;
    invalidPlan.executionEnabled = true;
    CHECK(parseSdIdentification(invalidPlan, golden, &identity) ==
          SdIdentificationStatus::InvalidPlan);
}

void testSdIdentificationStateMachineIsBoundedAndFakeOnly() {
    const SdReadOnlyPlan plan = defaultSdIdentificationPlan();
    GoldenFakeSdTransport golden;
    const SdTransportRunResult result = runSdIdentificationStateMachine(plan, golden);
    CHECK(result.status == SdTransportRunStatus::Valid);
    CHECK(result.parseStatus == SdIdentificationStatus::Valid);
    CHECK(result.commandsAttempted == 11);
    CHECK(result.commandsCompleted == 11);
    CHECK(result.identity.initAttempts == 3);
    CHECK(result.identity.capacityBytes == 16U * 1024U * 1024U);
    CHECK(golden.exchanges() == 11);
    CHECK(!golden.sequenceViolation());
    char report[512] = {};
    CHECK(formatSdTransportRunJson(result, report, sizeof(report)));
    CHECK(std::strstr(report, "\"transport\":\"golden_fake\"") != nullptr);
    CHECK(std::strstr(report, "\"commands_completed\":11") != nullptr);
    CHECK(std::strstr(report, "\"physical_spi_executed\":false") != nullptr);

    for (std::uint16_t failure = 1; failure <= 11; ++failure) {
        GoldenFakeSdTransport failing(3, failure);
        const SdTransportRunResult failed =
            runSdIdentificationStateMachine(plan, failing);
        CHECK(failed.status == SdTransportRunStatus::ExchangeFailed);
        CHECK(failed.commandsAttempted == failure);
        CHECK(failed.commandsCompleted == failure - 1);
    }

    GoldenFakeSdTransport neverReady(kSdMaxInitAttempts + 1);
    const SdTransportRunResult timedOut =
        runSdIdentificationStateMachine(plan, neverReady);
    CHECK(timedOut.status == SdTransportRunStatus::InitTimeout);
    CHECK(timedOut.commandsAttempted == 2 + 2 * kSdMaxInitAttempts);
    CHECK(timedOut.commandsCompleted == timedOut.commandsAttempted);

    SdReadOnlyPlan invalidPlan = plan;
    invalidPlan.commands[0] = 24;
    GoldenFakeSdTransport unused;
    CHECK(runSdIdentificationStateMachine(invalidPlan, unused).status ==
          SdTransportRunStatus::InvalidPlan);
    CHECK(unused.exchanges() == 0);

    class PhysicalStub final : public SdIdentificationTransport {
    public:
        bool isPhysical() const override { return true; }
        bool exchange(std::uint8_t, std::uint32_t, SdCommandResponse*) override {
            ++calls;
            return true;
        }
        std::uint16_t calls = 0;
    } physical;
    CHECK(runSdIdentificationStateMachine(plan, physical).status ==
          SdTransportRunStatus::PhysicalTransportRejected);
    CHECK(physical.calls == 0);

    class PhysicalGolden final : public SdIdentificationTransport {
    public:
        bool isPhysical() const override { return true; }
        bool exchange(std::uint8_t command, std::uint32_t argument,
                      SdCommandResponse* response) override {
            return fake.exchange(command, argument, response);
        }
        GoldenFakeSdTransport fake;
    } permittedPhysical;
    SdTransportRunPolicy policy;
    policy.allowPhysical = true;
    CHECK(runSdIdentificationStateMachine(plan, permittedPhysical, policy).status ==
          SdTransportRunStatus::PhysicalTargetRequired);
    CHECK(permittedPhysical.fake.exchanges() == 0);
    policy.explicitlySelected = true;
    CHECK(runSdIdentificationStateMachine(plan, permittedPhysical, policy).status ==
          SdTransportRunStatus::ReadOnlyContractRequired);
    CHECK(permittedPhysical.fake.exchanges() == 0);
    policy.identificationOnly = true;
    CHECK(runSdIdentificationStateMachine(plan, permittedPhysical, policy).status ==
          SdTransportRunStatus::ResourcesMissing);
    CHECK(permittedPhysical.fake.exchanges() == 0);
    policy.ownedResources = kSdIdentificationResources;
    policy.conflictingOwner = true;
    CHECK(runSdIdentificationStateMachine(plan, permittedPhysical, policy).status ==
          SdTransportRunStatus::ResourceConflict);
    CHECK(permittedPhysical.fake.exchanges() == 0);
    policy.conflictingOwner = false;
    const SdTransportRunResult physicalResult =
        runSdIdentificationStateMachine(plan, permittedPhysical, policy);
    CHECK(physicalResult.status == SdTransportRunStatus::Valid);
    CHECK(physicalResult.physicalTransport);
    CHECK(permittedPhysical.fake.exchanges() == 11);
    CHECK(formatSdTransportRunJson(physicalResult, report, sizeof(report)));
    CHECK(std::strstr(report, "\"transport\":\"physical_spi\"") != nullptr);
    CHECK(std::strstr(report, "\"physical_spi_executed\":true") != nullptr);

    GoldenFakeSdTransport wrongSequence;
    SdCommandResponse response;
    CHECK(!wrongSequence.exchange(1, 0, &response));
    CHECK(wrongSequence.sequenceViolation());
}

void testSdSpiWireCodecIsBoundedAndReadOnly() {
    const SdReadOnlyPlan plan = defaultSdIdentificationPlan();
    SdCommandFrame frame;
    CHECK(encodeSdIdentificationCommand(plan, 0, 0, &frame) == SdWireStatus::Valid);
    const std::array<std::uint8_t, 6> expectedCmd0{0x40, 0, 0, 0, 0, 0x95};
    CHECK(frame.bytes == expectedCmd0);
    CHECK(encodeSdIdentificationCommand(plan, 8, 0x1AAU, &frame) ==
          SdWireStatus::Valid);
    const std::array<std::uint8_t, 6> expectedCmd8{0x48, 0, 0, 0x01, 0xAA, 0x87};
    CHECK(frame.bytes == expectedCmd8);
    CHECK(sdCrc7(expectedCmd0.data(), 5) == 0x4AU);
    CHECK(sdCrc7(expectedCmd8.data(), 5) == 0x43U);
    CHECK(encodeSdIdentificationCommand(plan, 8, 0, &frame) ==
          SdWireStatus::ArgumentInvalid);
    static constexpr std::array<std::uint8_t, 11> kMutatingCommands{
        24, 25, 26, 27, 28, 29, 32, 33, 38, 42, 56};
    for (const std::uint8_t command : kMutatingCommands) {
        CHECK(encodeSdIdentificationCommand(plan, command, 0, &frame) ==
              SdWireStatus::CommandNotAllowed);
    }
    SdReadOnlyPlan invalidPlan = plan;
    invalidPlan.executionEnabled = true;
    CHECK(encodeSdIdentificationCommand(invalidPlan, 0, 0, &frame) ==
          SdWireStatus::InvalidPlan);

    class VectorByteSource final : public SdByteSource {
    public:
        explicit VectorByteSource(std::vector<std::uint8_t> input)
            : input_(std::move(input)) {}
        bool readByte(std::uint8_t* value) override {
            if (value == nullptr || offset_ >= input_.size()) return false;
            *value = input_[offset_++];
            return true;
        }
    private:
        std::vector<std::uint8_t> input_;
        std::size_t offset_ = 0;
    };

    std::uint8_t r1 = 0xFF;
    VectorByteSource delayedR1({0xFF, 0xFF, 0x01});
    CHECK(readSdR1(delayedR1, 3, &r1) == SdWireStatus::Valid);
    CHECK(r1 == 0x01);
    VectorByteSource timeoutR1(std::vector<std::uint8_t>(kSdMaxR1PollBytes, 0xFF));
    CHECK(readSdR1(timeoutR1, kSdMaxR1PollBytes, &r1) ==
          SdWireStatus::ResponseTimeout);
    VectorByteSource invalidR1({0x80});
    CHECK(readSdR1(invalidR1, 1, &r1) == SdWireStatus::ResponseInvalid);
    VectorByteSource noR1({});
    CHECK(readSdR1(noR1, 1, &r1) == SdWireStatus::IoError);
    VectorByteSource unusedR1({0x01});
    CHECK(readSdR1(unusedR1, 0, &r1) == SdWireStatus::InvalidBound);

    VectorByteSource trailing({0x12, 0x34, 0x56, 0x78});
    std::uint32_t trailingValue = 0;
    CHECK(readSdTrailing32(trailing, &trailingValue) == SdWireStatus::Valid);
    CHECK(trailingValue == 0x12345678U);
    VectorByteSource shortTrailing({0x12, 0x34, 0x56});
    CHECK(readSdTrailing32(shortTrailing, &trailingValue) == SdWireStatus::IoError);

    const SdIdentificationTranscript golden = goldenSdIdentificationTranscript();
    std::vector<std::uint8_t> dataFrame{0xFF, 0xFE};
    dataFrame.insert(dataFrame.end(), golden.cid.begin(), golden.cid.end());
    dataFrame.push_back(static_cast<std::uint8_t>(golden.cidCrc16 >> 8U));
    dataFrame.push_back(static_cast<std::uint8_t>(golden.cidCrc16));
    VectorByteSource validData(dataFrame);
    std::array<std::uint8_t, 16> decoded{};
    std::uint16_t receivedCrc = 0;
    CHECK(readSdData16(validData, 2, &decoded, &receivedCrc) == SdWireStatus::Valid);
    CHECK(decoded == golden.cid);
    CHECK(receivedCrc == golden.cidCrc16);
    dataFrame[2] ^= 1U;
    VectorByteSource corruptData(dataFrame);
    CHECK(readSdData16(corruptData, 2, &decoded, &receivedCrc) ==
          SdWireStatus::DataChecksumInvalid);
    VectorByteSource invalidToken({0x00});
    CHECK(readSdData16(invalidToken, 1, &decoded, &receivedCrc) ==
          SdWireStatus::DataTokenInvalid);
    VectorByteSource tokenTimeout(
        std::vector<std::uint8_t>(kSdMaxDataTokenPollBytes, 0xFF));
    CHECK(readSdData16(tokenTimeout, kSdMaxDataTokenPollBytes, &decoded,
                       &receivedCrc) == SdWireStatus::DataTokenTimeout);

    char report[512] = {};
    CHECK(formatSdWireContractJson(report, sizeof(report)));
    CHECK(std::strstr(report, "\"cmd0_frame\":\"400000000095\"") != nullptr);
    CHECK(std::strstr(report, "\"cmd8_frame\":\"48000001AA87\"") != nullptr);
    CHECK(std::strstr(report, "\"physical_spi_executed\":false") != nullptr);
}

void testSdSector0ReadIsSingleBoundedAndParseOnly() {
    SdSectorReadRequest request;
    CHECK(authorizeSdSector0Read(request) ==
          SdSectorReadStatus::ExplicitTargetRequired);
    request.explicitlySelected = true;
    CHECK(authorizeSdSector0Read(request) == SdSectorReadStatus::ReadOnlyRequired);
    request.readOnly = true;
    CHECK(authorizeSdSector0Read(request) ==
          SdSectorReadStatus::HighCapacityRequired);
    request.highCapacity = true;
    CHECK(authorizeSdSector0Read(request) == SdSectorReadStatus::CapacityInvalid);
    request.capacityBytes = 64ULL * 1024U * 1024U;
    request.lba = 1;
    CHECK(authorizeSdSector0Read(request) == SdSectorReadStatus::LbaForbidden);
    request.lba = 0;
    request.blockCount = 2;
    CHECK(authorizeSdSector0Read(request) ==
          SdSectorReadStatus::BlockCountInvalid);
    request.blockCount = 1;
    CHECK(authorizeSdSector0Read(request) == SdSectorReadStatus::ResourcesMissing);
    request.ownedResources = kSdIdentificationResources;
    request.conflictingOwner = true;
    CHECK(authorizeSdSector0Read(request) == SdSectorReadStatus::ResourceConflict);
    request.conflictingOwner = false;
    CHECK(authorizeSdSector0Read(request) == SdSectorReadStatus::Permitted);

    SdCommandFrame frame;
    CHECK(encodeSdReadSingleBlockCommand(0, &frame) == SdWireStatus::Valid);
    const std::array<std::uint8_t, 6> expectedCmd17{0x51, 0, 0, 0, 0, 0x55};
    CHECK(frame.bytes == expectedCmd17);

    class VectorByteSource final : public SdByteSource {
    public:
        explicit VectorByteSource(std::vector<std::uint8_t> input)
            : input_(std::move(input)) {}
        bool readByte(std::uint8_t* value) override {
            if (value == nullptr || offset_ >= input_.size()) return false;
            *value = input_[offset_++];
            return true;
        }
    private:
        std::vector<std::uint8_t> input_;
        std::size_t offset_ = 0;
    };

    std::array<std::uint8_t, 512> mbr{};
    mbr[446] = 0x80;
    mbr[450] = 0x0C;
    mbr[454] = 0x00;
    mbr[455] = 0x08;
    mbr[458] = 0xE8;
    mbr[459] = 0x03;
    mbr[510] = 0x55;
    mbr[511] = 0xAA;
    const std::uint16_t wireCrc = sdCrc16(mbr.data(), mbr.size());
    std::vector<std::uint8_t> wire{0xFF, 0xFE};
    wire.insert(wire.end(), mbr.begin(), mbr.end());
    wire.push_back(static_cast<std::uint8_t>(wireCrc >> 8U));
    wire.push_back(static_cast<std::uint8_t>(wireCrc));
    VectorByteSource source(wire);
    std::array<std::uint8_t, 512> decoded{};
    std::uint16_t receivedCrc = 0;
    CHECK(readSdData512(source, 2, &decoded, &receivedCrc) == SdWireStatus::Valid);
    CHECK(decoded == mbr);
    CHECK(receivedCrc == wireCrc);
    wire[2] ^= 1U;
    VectorByteSource corruptBlock(wire);
    CHECK(readSdData512(corruptBlock, 2, &decoded, &receivedCrc) ==
          SdWireStatus::DataChecksumInvalid);

    const SdSector0Inspection inspected =
        inspectSdSector0(mbr, request.capacityBytes);
    CHECK(inspected.kind == SdSector0Kind::PartitionedMbr);
    CHECK(inspected.signatureValid);
    CHECK(inspected.partitionCount == 1);
    CHECK(inspected.firstPartitionType == 0x0C);
    CHECK(inspected.firstPartitionLba == 2048);
    CHECK(inspected.firstPartitionSectors == 1000);
    char report[512] = {};
    CHECK(formatSdSector0Json(inspected, report, sizeof(report)));
    CHECK(std::strstr(report, "\"sector_kind\":\"partitioned_mbr\"") != nullptr);

    std::array<std::uint8_t, 512> protective = mbr;
    protective[450] = 0xEE;
    CHECK(inspectSdSector0(protective, request.capacityBytes).kind ==
          SdSector0Kind::ProtectiveMbr);
    std::array<std::uint8_t, 512> exfat{};
    std::memcpy(exfat.data() + 3, "EXFAT   ", 8);
    exfat[510] = 0x55;
    exfat[511] = 0xAA;
    CHECK(inspectSdSector0(exfat, request.capacityBytes).kind ==
          SdSector0Kind::ExfatBoot);
    std::array<std::uint8_t, 512> fat{};
    fat[0] = 0xEB;
    fat[11] = 0x00;
    fat[12] = 0x02;
    fat[13] = 8;
    fat[14] = 32;
    fat[16] = 2;
    fat[510] = 0x55;
    fat[511] = 0xAA;
    CHECK(inspectSdSector0(fat, request.capacityBytes).kind ==
          SdSector0Kind::FatBoot);
    fat[510] = 0;
    CHECK(inspectSdSector0(fat, request.capacityBytes).kind ==
          SdSector0Kind::InvalidSignature);

    request.lba = inspected.firstPartitionLba;
    CHECK(authorizeSdPartitionBootRead(inspected, request) ==
          SdSectorReadStatus::Permitted);
    request.lba = inspected.firstPartitionLba + 1;
    CHECK(authorizeSdPartitionBootRead(inspected, request) ==
          SdSectorReadStatus::LbaForbidden);
    request.lba = inspected.firstPartitionLba;
    request.blockCount = 2;
    CHECK(authorizeSdPartitionBootRead(inspected, request) ==
          SdSectorReadStatus::BlockCountInvalid);
    request.blockCount = 1;

    std::array<std::uint8_t, 512> fat32{};
    fat32[0] = 0xEB;
    std::memcpy(fat32.data() + 3, "MSDOS5.0", 8);
    fat32[11] = 0x00;
    fat32[12] = 0x02;
    fat32[13] = 8;
    fat32[14] = 32;
    fat32[16] = 2;
    fat32[21] = 0xF8;
    fat32[32] = 0xE8;
    fat32[33] = 0x03;
    fat32[36] = 10;
    fat32[44] = 2;
    fat32[48] = 1;
    fat32[50] = 6;
    fat32[67] = 0x78;
    fat32[68] = 0x56;
    fat32[69] = 0x34;
    fat32[70] = 0x12;
    std::memcpy(fat32.data() + 71, "LESHY TEST ", 11);
    fat32[510] = 0x55;
    fat32[511] = 0xAA;
    const SdFilesystemBootInspection boot =
        inspectSdFilesystemBoot(fat32, inspected.firstPartitionSectors);
    CHECK(boot.kind == SdFilesystemBootKind::Fat32);
    CHECK(boot.geometryValid);
    CHECK(boot.bytesPerSector == 512);
    CHECK(boot.rootCluster == 2);
    CHECK(boot.reservedSectors == 32);
    CHECK(boot.fatCount == 2);
    CHECK(boot.mediaDescriptor == 0xF8);
    CHECK(boot.fsInfoSector == 1);
    CHECK(boot.backupBootSector == 6);
    CHECK(boot.volumeSerial == 0x12345678U);
    CHECK(std::strcmp(boot.volumeLabel.data(), "LESHY TEST ") == 0);
    CHECK(formatSdFilesystemBootJson(boot, report, sizeof(report)));
    CHECK(std::strstr(report, "\"filesystem\":\"fat32\"") != nullptr);

    std::uint32_t rootDirectoryLba = 0;
    CHECK(calculateSdFat32RootDirectoryLba(
        inspected, boot, &rootDirectoryLba));
    CHECK(rootDirectoryLba == 2100);
    request.lba = rootDirectoryLba;
    CHECK(authorizeSdFat32RootDirectoryRead(inspected, boot, request) ==
          SdSectorReadStatus::Permitted);
    request.lba = rootDirectoryLba + 1;
    CHECK(authorizeSdFat32RootDirectoryRead(inspected, boot, request) ==
          SdSectorReadStatus::LbaForbidden);
    request.lba = rootDirectoryLba;
    request.blockCount = 2;
    CHECK(authorizeSdFat32RootDirectoryRead(inspected, boot, request) ==
          SdSectorReadStatus::BlockCountInvalid);
    request.blockCount = 1;
    request.lba = rootDirectoryLba + 1;
    CHECK(authorizeSdFat32RootDirectorySectorRead(
              inspected, boot, 1, request) == SdSectorReadStatus::Permitted);
    request.lba = rootDirectoryLba + 2;
    CHECK(authorizeSdFat32RootDirectorySectorRead(
              inspected, boot, 1, request) == SdSectorReadStatus::LbaForbidden);
    request.lba = rootDirectoryLba + 8;
    CHECK(authorizeSdFat32RootDirectorySectorRead(
              inspected, boot, 8, request) == SdSectorReadStatus::LbaForbidden);
    request.lba = rootDirectoryLba;

    std::array<std::uint8_t, 512> directory{};
    std::memcpy(directory.data(), "SECRET  TXT", 11);
    directory[11] = 0x20;
    std::memcpy(directory.data() + 32, "PRIVATE    ", 11);
    directory[32 + 11] = 0x10;
    std::memcpy(directory.data() + 64, "MY VOLUME  ", 11);
    directory[64 + 11] = 0x08;
    directory[96] = 0x41;
    directory[96 + 1] = 'P';
    directory[96 + 3] = 'r';
    directory[96 + 5] = 'i';
    directory[96 + 7] = 'v';
    directory[96 + 9] = 'a';
    directory[96 + 11] = 0x0F;
    directory[128] = 0xE5;
    directory[160] = 'X';
    directory[160 + 11] = 0xC0;
    directory[192] = 0x00;
    const SdFat32DirectoryInspection directoryInspection =
        inspectSdFat32DirectoryMetadata(directory);
    CHECK(directoryInspection.entriesExamined == 7);
    CHECK(directoryInspection.activeEntries == 5);
    CHECK(directoryInspection.deletedEntries == 1);
    CHECK(directoryInspection.longNameEntries == 1);
    CHECK(directoryInspection.volumeLabelEntries == 1);
    CHECK(directoryInspection.directoryEntries == 1);
    CHECK(directoryInspection.fileEntries == 1);
    CHECK(directoryInspection.invalidEntries == 1);
    CHECK(directoryInspection.endMarkerSeen);
    char directoryReport[512] = {};
    CHECK(formatSdFat32DirectoryMetadataJson(
        directoryInspection, directoryReport, sizeof(directoryReport)));
    CHECK(std::strstr(directoryReport,
                      "\"privacy_policy\":\"counts_hash_only\"") != nullptr);
    CHECK(std::strstr(directoryReport, "\"names_retained\":false") != nullptr);
    CHECK(std::strstr(directoryReport, "SECRET") == nullptr);
    CHECK(std::strstr(directoryReport, "PRIVATE") == nullptr);
    CHECK(std::strstr(directoryReport, "MY VOLUME") == nullptr);

    std::array<std::uint8_t, 512> fullDirectory{};
    for (std::size_t offset = 0; offset < fullDirectory.size(); offset += 32) {
        fullDirectory[offset] = 'A';
        fullDirectory[offset + 11] = 0x20;
    }
    SdFat32DirectoryAggregate aggregate;
    CHECK(appendSdFat32DirectoryMetadata(fullDirectory, &aggregate));
    CHECK(!aggregate.endMarkerSeen);
    CHECK(appendSdFat32DirectoryMetadata(directory, &aggregate));
    CHECK(aggregate.sectorsInspected == 2);
    CHECK(aggregate.entriesExamined == 23);
    CHECK(aggregate.activeEntries == 21);
    CHECK(aggregate.endMarkerSeen);
    CHECK(!appendSdFat32DirectoryMetadata(directory, &aggregate));
    std::array<std::uint8_t, 1024> combined{};
    std::memcpy(combined.data(), fullDirectory.data(), fullDirectory.size());
    std::memcpy(combined.data() + fullDirectory.size(),
                directory.data(), directory.size());
    CHECK(aggregate.crc32c == crc32c(combined.data(), combined.size()));
    CHECK(formatSdFat32DirectoryAggregateJson(
        aggregate, directoryReport, sizeof(directoryReport)));
    CHECK(std::strstr(directoryReport, "\"sectors_inspected\":2") != nullptr);
    CHECK(std::strstr(directoryReport, "SECRET") == nullptr);

    std::uint32_t fsInfoLba = 0;
    CHECK(calculateSdFat32FsInfoLba(inspected, boot, &fsInfoLba));
    CHECK(fsInfoLba == 2049);
    request.lba = fsInfoLba;
    CHECK(authorizeSdFat32FsInfoRead(inspected, boot, request) ==
          SdSectorReadStatus::Permitted);
    request.lba = fsInfoLba + 1;
    CHECK(authorizeSdFat32FsInfoRead(inspected, boot, request) ==
          SdSectorReadStatus::LbaForbidden);
    request.lba = fsInfoLba;

    std::array<std::uint8_t, 512> fsInfo{};
    fsInfo[0] = 0x52;
    fsInfo[1] = 0x52;
    fsInfo[2] = 0x61;
    fsInfo[3] = 0x41;
    fsInfo[484] = 0x72;
    fsInfo[485] = 0x72;
    fsInfo[486] = 0x41;
    fsInfo[487] = 0x61;
    fsInfo[488] = 100;
    fsInfo[492] = 5;
    fsInfo[510] = 0x55;
    fsInfo[511] = 0xAA;
    SdFat32FsInfoInspection fsInfoInspection =
        inspectSdFat32FsInfo(fsInfo, boot);
    CHECK(fsInfoInspection.signaturesValid);
    CHECK(fsInfoInspection.hintsValid);
    CHECK(fsInfoInspection.dataClusters == 118);
    CHECK(fsInfoInspection.freeCountKnown);
    CHECK(fsInfoInspection.freeClusters == 100);
    CHECK(fsInfoInspection.nextFreeKnown);
    CHECK(fsInfoInspection.nextFreeCluster == 5);
    CHECK(formatSdFat32FsInfoJson(
        fsInfoInspection, directoryReport, sizeof(directoryReport)));
    CHECK(std::strstr(directoryReport,
                      "\"technical_metadata_only\":true") != nullptr);
    std::array<std::uint8_t, 512> unknownFsInfo = fsInfo;
    std::memset(unknownFsInfo.data() + 488, 0xFF, 8);
    fsInfoInspection = inspectSdFat32FsInfo(unknownFsInfo, boot);
    CHECK(fsInfoInspection.hintsValid);
    CHECK(!fsInfoInspection.freeCountKnown);
    CHECK(!fsInfoInspection.nextFreeKnown);
    std::array<std::uint8_t, 512> invalidFsInfo = fsInfo;
    invalidFsInfo[0] = 0;
    CHECK(!inspectSdFat32FsInfo(invalidFsInfo, boot).hintsValid);
    invalidFsInfo = fsInfo;
    invalidFsInfo[488] = 119;
    CHECK(!inspectSdFat32FsInfo(invalidFsInfo, boot).hintsValid);
    SdFilesystemBootInspection invalidFsInfoBoot = boot;
    invalidFsInfoBoot.fsInfoSector = invalidFsInfoBoot.reservedSectors;
    CHECK(!calculateSdFat32FsInfoLba(
        inspected, invalidFsInfoBoot, &fsInfoLba));

    std::uint32_t firstFatLba = 0;
    CHECK(calculateSdFat32FirstFatLba(inspected, boot, &firstFatLba));
    CHECK(firstFatLba == 2080);
    request.lba = firstFatLba;
    CHECK(authorizeSdFat32FirstFatSectorRead(inspected, boot, request) ==
          SdSectorReadStatus::Permitted);
    request.lba = firstFatLba + 1;
    CHECK(authorizeSdFat32FirstFatSectorRead(inspected, boot, request) ==
          SdSectorReadStatus::LbaForbidden);
    request.lba = firstFatLba;
    request.blockCount = 2;
    CHECK(authorizeSdFat32FirstFatSectorRead(inspected, boot, request) ==
          SdSectorReadStatus::BlockCountInvalid);
    request.blockCount = 1;

    std::array<std::uint8_t, 512> fatSector{};
    fatSector[0] = 0xF8;
    fatSector[1] = 0xFF;
    fatSector[2] = 0xFF;
    fatSector[3] = 0x0F;
    fatSector[4] = 0xFF;
    fatSector[5] = 0xFF;
    fatSector[6] = 0xFF;
    fatSector[7] = 0x0F;
    fatSector[8] = 0xFF;
    fatSector[9] = 0xFF;
    fatSector[10] = 0xFF;
    fatSector[11] = 0x0F;
    SdFat32ReservedInspection fatInspection =
        inspectSdFat32ReservedAndRootEntries(fatSector, boot);
    CHECK(fatInspection.fat0Valid);
    CHECK(fatInspection.fat1ReservedBitsValid);
    CHECK(fatInspection.cleanShutdown);
    CHECK(fatInspection.noHardError);
    CHECK(fatInspection.rootEntryKind == SdFat32EntryKind::EndOfChain);
    CHECK(fatInspection.rootEntryValid);
    CHECK(!fatInspection.rootChainContinues);
    CHECK(fatInspection.structureValid);
    CHECK(formatSdFat32ReservedInspectionJson(
        fatInspection, directoryReport, sizeof(directoryReport)));
    CHECK(std::strstr(directoryReport, "\"entries_inspected\":3") != nullptr);
    CHECK(std::strstr(directoryReport, "\"fat_chain_followed\":false") != nullptr);

    SdFat32FsInfoCrossCheck crossCheck =
        crossCheckSdFat32FsInfoWithReservedEntries(
            inspectSdFat32FsInfo(fsInfo, boot), fatInspection, boot);
    CHECK(crossCheck.available);
    CHECK(crossCheck.freeHintCompatible);
    CHECK(crossCheck.nextFreeHintCompatible);
    CHECK(crossCheck.compatible);

    std::array<std::uint8_t, 512> changedFat = fatSector;
    changedFat[7] &= static_cast<std::uint8_t>(~0x08U);
    fatInspection = inspectSdFat32ReservedAndRootEntries(changedFat, boot);
    CHECK(fatInspection.structureValid);
    CHECK(!fatInspection.cleanShutdown);
    CHECK(fatInspection.noHardError);
    changedFat = fatSector;
    changedFat[7] &= static_cast<std::uint8_t>(~0x04U);
    fatInspection = inspectSdFat32ReservedAndRootEntries(changedFat, boot);
    CHECK(fatInspection.structureValid);
    CHECK(fatInspection.cleanShutdown);
    CHECK(!fatInspection.noHardError);
    changedFat = fatSector;
    changedFat[8] = 5;
    changedFat[9] = 0;
    changedFat[10] = 0;
    changedFat[11] = 0;
    fatInspection = inspectSdFat32ReservedAndRootEntries(changedFat, boot);
    CHECK(fatInspection.rootEntryKind == SdFat32EntryKind::Data);
    CHECK(fatInspection.rootChainContinues);
    CHECK(fatInspection.rootEntryValid);
    crossCheck = crossCheckSdFat32FsInfoWithReservedEntries(
        inspectSdFat32FsInfo(fsInfo, boot), fatInspection, boot);
    CHECK(crossCheck.available);
    CHECK(!crossCheck.nextFreeHintCompatible);
    CHECK(!crossCheck.compatible);
    changedFat[8] = 2;
    fatInspection = inspectSdFat32ReservedAndRootEntries(changedFat, boot);
    CHECK(!fatInspection.rootEntryValid);
    changedFat = fatSector;
    changedFat[0] = 0xF0;
    CHECK(!inspectSdFat32ReservedAndRootEntries(changedFat, boot).structureValid);
    changedFat = fatSector;
    std::memset(changedFat.data() + 8, 0, 4);
    fatInspection = inspectSdFat32ReservedAndRootEntries(changedFat, boot);
    CHECK(fatInspection.rootEntryKind == SdFat32EntryKind::Free);
    CHECK(!fatInspection.rootEntryValid);
    crossCheck = crossCheckSdFat32FsInfoWithReservedEntries(
        inspectSdFat32FsInfo(fsInfo, boot), fatInspection, boot);
    CHECK(!crossCheck.available);

    std::array<std::uint8_t, 512> incompatibleFsInfo = fsInfo;
    incompatibleFsInfo[488] = 118;
    fatInspection = inspectSdFat32ReservedAndRootEntries(fatSector, boot);
    crossCheck = crossCheckSdFat32FsInfoWithReservedEntries(
        inspectSdFat32FsInfo(incompatibleFsInfo, boot), fatInspection, boot);
    CHECK(crossCheck.available);
    CHECK(!crossCheck.freeHintCompatible);
    CHECK(!crossCheck.compatible);
    incompatibleFsInfo = fsInfo;
    incompatibleFsInfo[492] = 2;
    crossCheck = crossCheckSdFat32FsInfoWithReservedEntries(
        inspectSdFat32FsInfo(incompatibleFsInfo, boot), fatInspection, boot);
    CHECK(crossCheck.available);
    CHECK(!crossCheck.nextFreeHintCompatible);
    CHECK(!crossCheck.compatible);

    SdFilesystemBootInspection invalidRoot = boot;
    invalidRoot.rootCluster = 0xFFFFFFFFU;
    CHECK(!calculateSdFat32RootDirectoryLba(
        inspected, invalidRoot, &rootDirectoryLba));
    CHECK(authorizeSdFat32RootDirectoryRead(inspected, invalidRoot, request) ==
          SdSectorReadStatus::LbaForbidden);
    fat32[510] = 0;
    CHECK(inspectSdFilesystemBoot(fat32, inspected.firstPartitionSectors).kind ==
          SdFilesystemBootKind::Invalid);
}

}  // namespace

int main() {
    testVisualThemeContract();
    testUiComponentGeometryContract();
    testLanguageCatalogAndControllerAreBounded();
    testSelfTestQuickIsReadOnlyBoundedAndFullFailsClosed();
    testShieldReceiverIdentityContractFailsClosed();
    testNrf24PassiveSpectrumContractAndControllerAreBounded();
    testCc1101PassiveSpectrumContractAndControllerAreBounded();
    testProductBootRetryIsNarrowAndBounded();
    testProductStartIdentityRetryStopsBeforeFilesystem();
    testStorageTimingSummaryUsesNearestRank();
    testIngressRateSummaryUsesNearestRankAndRejectsZero();
    testObservationQueueIsBoundedFifoAndScrubbable();
    testSessionBatchPolicyMeetsMeasuredRateAndFlushesBoundedly();
    testInventoryIsFixedAndRejectsDuplicates();
    testBootReportIsBoundedAndMachineReadable();
    testHilSessionBindsOneRunToTheRunningAppIdentity();
    testPhysicalAndDiagnosticActionsShareNavigation();
    testPhysicalButtonFrontendDebouncesAndMapsEveryKey();
    testPhysicalButtonFrontendRejectsAmbiguousPressesAndRecovers();
    testAppCatalogProjectsCapabilityStatesBeforeLaunch();
    testRuntimeAcquiresAtomicallyAndBackReleasesEverything();
    testWifiIngressIsPassiveOnlyAndNormalizesObservations();
    testBleIngressIsReceiveOnlyBoundedAndNormalizesObservations();
    testSurveySessionIsOrderedBoundedAndStopIsIdempotent();
    testSourceDegradationKeepsOnlyCompatibleSourcesRunning();
    testSourceTimelineStreamsHonestDutyWindowsAndDrops();
    testSourceTimelineOverflowRejectsStateChangeAndCanDrain();
    testSessionTimelinePersistsBoundedHistoryAndExactAggregates();
    testGoldenSurveyTraceUsesListDetailBackAndExplicitStop();
    testSurveyBrowserFiltersSourcesAndBuildsBoundedRssiHistory();
    testSurveySourcePlanProjectsAvailabilityAndRequiresSelection();
    testSurveyWorkflowCommitsOnceAndPreservesPriorLibraryOnFailure();
    testSessionStoreIoRouterSwitchesOnlyTheSelectedBackend();
    testSurveyPipelineQueuesDrainsDropsAndCommitsWithStopPolicy();
    testProductStorePolicySeparatesReadOnlyBootFromExplicitWrites();
    testProductSurveyAdmissionNeverFallsBackToSimulatedOrRam();
    testSessionCodecCommitsCanonicalDataAndReopensOffline();
    testSessionCodecRoundTripsBleWithoutInventingWifiFields();
    testCaptureMetadataV3AndCsvExportAreCanonical();
    testWifiFrameCaptureExportsByteExactRadiotapPcap();
    testOfflineLibraryControllerIsBoundedAndPreservesProvenance();
    testSessionCatalogRecoversReadOnlyAndMarksFallbackIntegrity();
    testBoundedSessionStoreCommitsRecoversAndFallsBack();
    testSessionStoreBoundaryWrapperStopsAfterEachSuccessfulBoundary();
    testRamSessionStoreAdapterMatchesBoardFixtureContract();
    testHeadEncodingAndRecoveryRejectsUncommittedData();
    testEveryCommitBoundaryPreservesAValidGeneration();
    testStorageWritesRequireExactDisposableScope();
    testMediaDiscoveryBoundaryIsReadOnlyAndFailClosed();
    testReadOnlyMountAuthorizationRequiresSelectionDriverAndLeases();
    testSdIdentificationProtocolCannotDriftIntoWrites();
    testSdIdentificationParserRejectsTranscriptFaults();
    testSdIdentificationStateMachineIsBoundedAndFakeOnly();
    testSdSpiWireCodecIsBoundedAndReadOnly();
    testSdSector0ReadIsSingleBoundedAndParseOnly();
    if (failures != 0) return EXIT_FAILURE;
    std::cout << "clean 1.x target contract tests passed\n";
    return EXIT_SUCCESS;
}
