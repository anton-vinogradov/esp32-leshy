#include <Arduino.h>
#include <Preferences.h>
#include <SPI.h>
#include <TFT_eSPI.h>
#include <Wire.h>

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

#include <esp_system.h>
#include <esp_task_wdt.h>
#include <esp_timer.h>
#include <esp_app_desc.h>
#include <esp_attr.h>
#include <esp_private/system_internal.h>
#include <soc/gpio_struct.h>
#include <mbedtls/sha256.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

#include "apps/library/LibraryController.h"
#include "apps/library/SessionCatalog.h"
#include "apps/capture/RadiotapPcap.h"
#include "apps/capture/InfraredCapture.h"
#include "apps/capture/InfraredCsv.h"
#include "apps/capture/SubGhzRawCapture.h"
#include "apps/capture/SubGhzRawCsv.h"
#include "apps/capture/WifiFrameCapture.h"
#include "apps/self_test/SelfTestController.h"
#include "apps/spectrum/Cc1101SpectrumController.h"
#include "apps/spectrum/Nrf24SpectrumController.h"
#include "apps/spectrum/SpectrumViewport.h"
#include "apps/survey/ProductSurveyAdmission.h"
#include "apps/survey/SurveyController.h"
#include "apps/survey/SurveyPipeline.h"
#include "apps/survey/SurveySourceController.h"
#include "apps/survey/SurveyWorkflow.h"
#include "apps/ble/BleDeviceCatalog.h"
#include "apps/wifi/WifiNetworkCatalog.h"
#include "apps/wifi/WifiNetworkNavigationOrder.h"
#include "apps/wifi/WifiDeviceCatalog.h"
#include "apps/wifi/WifiDeviceNavigationOrder.h"
#include "apps/wifi/WifiOuiDatabase.h"
#include "boards/esp32_div_v2/BoardProfile.h"
#include "domain/apps/AppCatalog.h"
#include "domain/hardware/HardwareInventory.h"
#include "domain/observations/Observation.h"
#include "drivers/ble/BlePassiveContract.h"
#include "drivers/radio/Cc1101PassiveSpectrum.h"
#include "drivers/radio/Nrf24PassiveSpectrum.h"
#include "drivers/radio/ShieldReceiverIdentity.h"
#include "drivers/wifi/WifiPassiveContract.h"
#include "kernel/runtime/AppRuntime.h"
#include "kernel/runtime/ResourceBroker.h"
#include "kernel/safety/SafetySupervisor.h"
#include "platform/arduino/BoardSafeOutputs.h"
#include "platform/arduino/BoardInfraredReceiver.h"
#include "platform/arduino/BoardCc1101PassiveSpectrum.h"
#include "platform/arduino/BoardNrf24PassiveSpectrum.h"
#include "platform/arduino/BoardShieldReceiverProbe.h"
#include "platform/arduino/ArduinoFsSessionStoreIo.h"
#include "platform/arduino/ArduinoLittleFsSessionStoreIo.h"
#include "platform/arduino/BoardSdFilesystem.h"
#include "platform/arduino/BoardStorageAdapter.h"
#include "platform/arduino/BoardTouchInput.h"
#include "platform/arduino/BoardBlePassiveScanner.h"
#include "platform/arduino/BoardSdSpiTransport.h"
#include "platform/arduino/BoardWifiPassiveScanner.h"
#include "platform/arduino/BoardWifiPassiveCapture.h"
#include "platform/arduino/DisposableOtaLittleFs.h"
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
#include "ui/TouchTargets.h"
#include "ui/LanguageController.h"
#include "ui/UiComponents.h"
#include "ui/UiController.h"
#include "ui/UiStrings.h"
#include "ui/VisualTheme.h"
#include "ui/fonts/RobotoCondensedGfx.h"

namespace {

extern const std::uint8_t wifiOuiAssetStart[]
    asm("_binary_assets_oui_bin_start");
extern const std::uint8_t wifiOuiAssetEnd[]
    asm("_binary_assets_oui_bin_end");

using leshy1::boards::esp32_div_v2::BoardProfile;
using leshy1::apps::library::LibraryController;
using leshy1::apps::library::LibraryEntry;
using leshy1::apps::library::LibraryView;
using leshy1::apps::library::SessionCatalog;
using leshy1::apps::library::SessionIntegrity;
using leshy1::apps::capture::PcapExportResult;
using leshy1::apps::capture::InfraredCapture;
using leshy1::apps::capture::InfraredCapturePlan;
using leshy1::apps::capture::InfraredCaptureState;
using leshy1::apps::capture::SubGhzRawCapture;
using leshy1::apps::capture::SubGhzRawCapturePlan;
using leshy1::apps::capture::SubGhzRawCaptureState;
using leshy1::apps::capture::SubGhzRawRssiSample;
using leshy1::apps::capture::WifiFrameCapturePlan;
using leshy1::apps::capture::WifiFrameCaptureState;
using leshy1::apps::self_test::SelfTestController;
using leshy1::apps::self_test::SelfTestFacts;
using leshy1::apps::self_test::SelfTestMode;
using leshy1::apps::self_test::SelfTestReport;
using leshy1::apps::self_test::SelfTestResultStatus;
using leshy1::apps::self_test::SelfTestView;
using leshy1::apps::spectrum::Cc1101SpectrumController;
using leshy1::apps::spectrum::Cc1101SpectrumViewState;
using leshy1::apps::spectrum::Nrf24SpectrumController;
using leshy1::apps::spectrum::Nrf24SpectrumMetric;
using leshy1::apps::spectrum::Nrf24SpectrumViewState;
using leshy1::apps::spectrum::SpectrumDisplayMode;
using leshy1::apps::spectrum::SpectrumViewport;
using leshy1::apps::survey::SurveyController;
using leshy1::apps::survey::ObservationHistory;
using leshy1::apps::survey::SurveyFilter;
using leshy1::apps::survey::SurveyPipeline;
using leshy1::apps::survey::SurveyPipelineProgress;
using leshy1::apps::survey::SurveyPipelineStatus;
using leshy1::apps::survey::SurveySetupActivation;
using leshy1::apps::survey::SurveySetupView;
using leshy1::apps::survey::SurveySourceController;
using leshy1::apps::survey::SurveySourceKind;
using leshy1::apps::survey::SurveySourceOption;
using leshy1::apps::survey::SurveySourceScope;
using leshy1::apps::survey::SurveySourceState;
using leshy1::apps::survey::SurveyView;
using leshy1::apps::survey::SurveyWorkflow;
using leshy1::apps::survey::SurveyWorkflowState;
using leshy1::apps::survey::SurveyWorkflowStatus;
using leshy1::apps::ble::BleDeviceCatalog;
using leshy1::apps::wifi::WifiNetworkCatalog;
using leshy1::apps::wifi::WifiNetworkNavigationOrder;
using leshy1::apps::wifi::WifiDeviceCatalog;
using leshy1::apps::wifi::WifiDeviceObservation;
using leshy1::apps::wifi::WifiDeviceRecord;
using leshy1::apps::wifi::WifiDeviceNavigationOrder;
using leshy1::apps::wifi::WifiOuiDatabase;
using leshy1::apps::wifi::WifiDeviceGeneration;
using leshy1::apps::wifi::WifiDeviceState;
using leshy1::apps::wifi::WifiChannelLoadSnapshot;
using leshy1::domain::apps::AppCatalog;
using leshy1::domain::apps::AppMenuItem;
using leshy1::domain::hardware::CapabilityRecord;
using leshy1::domain::hardware::CapabilityState;
using leshy1::domain::hardware::HardwareInventory;
using leshy1::domain::observations::Observation;
using leshy1::domain::observations::RadioKind;
using leshy1::drivers::ble::BleAdvertisementRecord;
using leshy1::drivers::radio::ShieldReceiverProbeReport;
using leshy1::drivers::radio::ShieldReceiverProbeStatus;
using leshy1::drivers::radio::Cc1101PassiveSample;
using leshy1::drivers::radio::Cc1101PassiveSpectrumPlan;
using leshy1::drivers::radio::Cc1101PassiveSpectrumReport;
using leshy1::drivers::radio::Cc1101PassiveSpectrumStatus;
using leshy1::drivers::radio::Nrf24PassiveSpectrumPlan;
using leshy1::drivers::radio::Nrf24PassiveSpectrumReport;
using leshy1::drivers::radio::Nrf24PassiveSpectrumStatus;
using leshy1::drivers::radio::Nrf24PassiveSweep;
using leshy1::drivers::wifi::WifiScanRecord;
using leshy1::kernel::runtime::AppRuntime;
using leshy1::kernel::runtime::LaunchStatus;
using leshy1::kernel::runtime::Resource;
using leshy1::kernel::runtime::ResourceBroker;
using leshy1::kernel::safety::SafetyReason;
using leshy1::kernel::safety::SafetyRetainedRecord;
using leshy1::kernel::safety::SafetyState;
using leshy1::kernel::safety::SafetySupervisor;
using leshy1::platform::arduino::BoardSafeOutputs;
using leshy1::platform::arduino::BoardInfraredReceiver;
using leshy1::platform::arduino::InfraredReceiverReport;
using leshy1::platform::arduino::BoardCc1101PassiveSpectrum;
using leshy1::platform::arduino::BoardNrf24PassiveSpectrum;
using leshy1::platform::arduino::BoardShieldReceiverProbe;
using leshy1::platform::arduino::ArduinoFsSessionStoreIo;
using leshy1::platform::arduino::ArduinoFsSessionStoreWorkspace;
using leshy1::platform::arduino::ArduinoLittleFsSessionStoreIo;
using leshy1::platform::arduino::BoardSdFilesystem;
using leshy1::platform::arduino::BoardStorageAdapter;
using leshy1::platform::arduino::BoardTouchInput;
using leshy1::platform::arduino::TouchCalibrationSource;
using leshy1::platform::arduino::BoardBlePassiveScanner;
using leshy1::platform::arduino::BoardBlePassiveScanResult;
using leshy1::platform::arduino::BleRecordDisposition;
using leshy1::platform::arduino::BoardSdSpiTransport;
using leshy1::platform::arduino::BoardWifiPassiveScanner;
using leshy1::platform::arduino::BoardWifiPassiveCapture;
using leshy1::platform::arduino::BoardWifiPassiveScanResult;
using leshy1::platform::arduino::DisposableOtaLittleFs;
using leshy1::platform::arduino::WifiRecordDisposition;
using leshy1::platform::arduino::RamSessionStoreIo;
using leshy1::services::diagnostics::BootMetrics;
using leshy1::services::diagnostics::HilSession;
using leshy1::services::diagnostics::HilSessionStatus;
using leshy1::services::survey::SessionState;
using leshy1::services::survey::SessionStatus;
using leshy1::services::survey::CaptureMetadata;
using leshy1::services::survey::CaptureMetadataStatus;
using leshy1::services::survey::FramePayloadFormat;
using leshy1::services::survey::SourceFailureClass;
using leshy1::services::survey::SourceTimeline;
using leshy1::services::survey::SourceTimelineState;
using leshy1::services::survey::SourceTimelineStatus;
using leshy1::services::survey::SourceWindow;
using leshy1::services::survey::SourceWindowReason;
using leshy1::services::survey::SourceWindowState;
using leshy1::services::survey::SurveySession;
using leshy1::ui::UiAction;
using leshy1::ui::UiController;
using leshy1::ui::UiLanguage;
using leshy1::ui::UiTextId;
using leshy1::ui::UiTextRole;
using leshy1::ui::LanguageController;
using leshy1::ui::Pcf8574ButtonInput;
using leshy1::ui::TouchPoint;
using leshy1::ui::TouchTarget;
using leshy1::ui::TouchTargetLayout;
using leshy1::ui::visual::Layout;
using leshy1::ui::visual::Palette;
using leshy1::ui::visual::Components;
using leshy1::ui::visual::Rect;
using leshy1::ui::visual::Tone;

constexpr std::uint32_t kConsoleBaud = 115200;
constexpr std::uint32_t kI2cHz = 100000;
constexpr std::uint8_t kInputProbeMaxAttempts = 8;
constexpr std::uint32_t kInputProbeRetryDelayMs = 5;
constexpr leshy1::kernel::runtime::ResourceOwner kSdIdentificationOwner = 2;
constexpr leshy1::kernel::runtime::ResourceOwner kWifiIngressOwner = 3;
constexpr leshy1::kernel::runtime::ResourceOwner kBootCatalogOwner = 4;
constexpr leshy1::kernel::runtime::ResourceOwner kLittleFsHilOwner = 5;
constexpr std::size_t kSdThroughputSamples = 32;
constexpr std::size_t kWifiIngressMaxSamples = 32;
constexpr std::uint64_t kWifiIngressP99EncodedBytesPerSecond = 546;
constexpr std::uint32_t kStorageRateSafetyMultiplier = 4;
constexpr std::uint64_t kStorageRequiredEncodedBytesPerSecond =
    kWifiIngressP99EncodedBytesPerSecond * kStorageRateSafetyMultiplier;
constexpr std::uint64_t kProductSurveyCommitBytes = 64U * 1024U;
constexpr std::uint64_t kProductSurveyReserveBytes = 1024U * 1024U;
constexpr unsigned kWifiPersistMaxScans = 8;
constexpr const char* kFullGuidedDisposableRunId = "full-guided-v7";
constexpr std::uint64_t kFullGuidedDisposableBytes = 64U * 1024U;
constexpr std::uint64_t kFullGuidedDisposableReserve = 1024U * 1024U;
constexpr const char* kSdSessionStorePrefix =
    "storage.sd.session-store disposable-write ";
constexpr const char* kSdSessionThroughputPrefix =
    "storage.sd.session-store throughput disposable-write ";
constexpr const char* kSdSessionBatchThroughputPrefix =
    "storage.sd.session-store batch-throughput disposable-write ";
constexpr const char* kWifiPersistPrefix =
    "survey.wifi.passive-persist disposable-write ";
constexpr const char* kSdSessionResetPrefix =
    "storage.sd.session-store reset disposable-write ";
constexpr const char* kSdSessionRecoverPrefix =
    "storage.sd.session-store recover disposable-read-only ";
constexpr const char* kSdSessionPowerCutPrefix =
    "storage.sd.session-store power-cut disposable-write ";
constexpr const char* kSdSessionPowerCutRecoverPrefix =
    "storage.sd.session-store power-cut-recover disposable-read-only ";
constexpr const char* kSdReadOnlyMountPrefix =
    "storage.sd.readonly-mount disposable-read-only ";
constexpr const char* kWifiIngressPrefix =
    "survey.wifi.passive-ingress measure passive-only ";
constexpr const char* kProductBootstrapPrefix =
    "storage.product.bootstrap disposable-write ";
constexpr const char* kProductEnrollPrefix =
    "storage.product.enroll disposable-read-only ";
constexpr const char* kLittleFsParityPrefix =
    "storage.littlefs.parity disposable-ota1 ";
constexpr const char* kLittleFsResetPrefix =
    "storage.littlefs.reset disposable-ota1 ";
constexpr const char* kLittleFsResetRecoverPrefix =
    "storage.littlefs.reset recover read-only ";
constexpr const char* kProductEnrollmentNamespace = "leshy1";
constexpr const char* kProductEnrollmentKey = "sd.cid.v1";
constexpr const char* kUiPreferencesNamespace = "leshy1-ui";
constexpr const char* kUiLanguageKey = "lang.v1";
HardwareInventory inventory;
AppCatalog appCatalog;
ResourceBroker resourceBroker;
AppRuntime appRuntime(resourceBroker);
SurveySession surveySession;
SurveyController surveyController(surveySession);
SurveySourceController surveySourceController;
SurveySession librarySession;
SurveySession littleFsResetSession;
LibraryController libraryController;
SessionCatalog sessionCatalog;
leshy1::services::survey::ObservationQueue surveyIngressQueue;
leshy1::storage::SessionStoreWorkspace sessionStoreWorkspace;
ArduinoFsSessionStoreWorkspace sdSessionStoreIoWorkspace;
ArduinoFsSessionStoreWorkspace productSurveyIoWorkspace;
RamSessionStoreIo ramSessionStore;
leshy1::storage::SessionStoreIoRouter surveyStoreRouter(ramSessionStore);
ArduinoFsSessionStoreIo productSurveyStore(productSurveyIoWorkspace);
BoardSdFilesystem productSurveyFilesystem;
SurveyWorkflow surveyWorkflow(surveyController, surveyStoreRouter,
                              sessionStoreWorkspace, librarySession,
                              libraryController, false, true);
SurveyPipeline surveyPipeline(surveyWorkflow, surveyIngressQueue);
SourceTimeline productSurveyTimeline;
BoardStorageAdapter boardStorageAdapter;
leshy1::storage::MediaDiscovery storageDiscovery;
bool storageDiscoveryReady = false;
bool surveyDemoReady = false;
bool libraryDemoReady = false;
const char* lastRuntimeEvent = "idle";
BootMetrics bootMetrics;
char runningAppElfSha256[65] = {};
HilSession hilSession;
TFT_eSPI display;
BoardTouchInput boardTouchInput;
bool touchCalibrationRequiredAtBoot = false;
bool touchCalibrationSucceededAtBoot = false;
UiController uiController;
LanguageController languageController;
SelfTestController selfTestController;
constexpr std::uint8_t kDevicePage = 9;
constexpr std::uint8_t kAboutPage = 10;
constexpr std::uint8_t kDeviceItemCount = 4;
std::uint8_t deviceSelection = 0;
ShieldReceiverProbeReport shieldReceiverProbeReport;
Nrf24SpectrumController nrf24SpectrumController;
Nrf24PassiveSpectrumReport nrf24SpectrumReport;
BoardNrf24PassiveSpectrum boardNrf24Spectrum;
Cc1101SpectrumController cc1101SpectrumController;
Cc1101PassiveSpectrumReport cc1101SpectrumReport;
BoardCc1101PassiveSpectrum boardCc1101Spectrum;
SpectrumViewport spectrumViewport;
std::array<std::uint8_t, SpectrumViewport::kMaxBins> spectrumIntensity{};
std::array<std::uint16_t, Layout::ScreenWidth> spectrumScanline{};
enum class FullGuidedRfStep : std::uint8_t {
    Idle,
    Nrf24Sweep,
    Cc1101Sweep,
    Complete,
    Failed,
    Cancelled,
};
const char* fullGuidedRfStepName(FullGuidedRfStep step) {
    switch (step) {
        case FullGuidedRfStep::Idle: return "idle";
        case FullGuidedRfStep::Nrf24Sweep: return "nrf24_sweep";
        case FullGuidedRfStep::Cc1101Sweep: return "cc1101_sweep";
        case FullGuidedRfStep::Complete: return "complete";
        case FullGuidedRfStep::Failed: return "failed";
        case FullGuidedRfStep::Cancelled: return "cancelled";
    }
    return "unknown";
}
struct FullGuidedRfState final {
    FullGuidedRfStep step = FullGuidedRfStep::Idle;
    bool resourceAcquired = false;
    bool resourceReleased = true;
    bool cleanupComplete = true;
    bool nrf24Complete = false;
    bool nrf24Passed = false;
    bool cc1101Complete = false;
    bool cc1101Passed = false;
    std::uint8_t cc1101Bins = 0;
};
FullGuidedRfState fullGuidedRfState;
Nrf24PassiveSpectrumReport fullGuidedNrf24Report;
Cc1101PassiveSpectrumReport fullGuidedCc1101Report;
std::uint64_t fullGuidedRfStartAfterUs = 0;
enum class FullGuidedArtifactStep : std::uint8_t {
    Idle,
    Recover,
    LibraryJson,
    LibraryCsv,
    CapturePcap,
    DisposableCommit,
    DisposableRemountExport,
    DisposableCleanup,
    ProductVerify,
    Complete,
    Failed,
    Cancelled,
};
const char* fullGuidedArtifactStepName(FullGuidedArtifactStep step) {
    switch (step) {
        case FullGuidedArtifactStep::Idle: return "idle";
        case FullGuidedArtifactStep::Recover: return "recover";
        case FullGuidedArtifactStep::LibraryJson: return "library_json";
        case FullGuidedArtifactStep::LibraryCsv: return "library_csv";
        case FullGuidedArtifactStep::CapturePcap: return "capture_pcap";
        case FullGuidedArtifactStep::DisposableCommit:
            return "disposable_commit";
        case FullGuidedArtifactStep::DisposableRemountExport:
            return "disposable_remount_export";
        case FullGuidedArtifactStep::DisposableCleanup:
            return "disposable_cleanup";
        case FullGuidedArtifactStep::ProductVerify: return "product_verify";
        case FullGuidedArtifactStep::Complete: return "complete";
        case FullGuidedArtifactStep::Failed: return "failed";
        case FullGuidedArtifactStep::Cancelled: return "cancelled";
    }
    return "unknown";
}
struct FullGuidedArtifactState final {
    FullGuidedArtifactStep step = FullGuidedArtifactStep::Idle;
    char expectedFingerprint[33] = {};
    bool recoveryComplete = false;
    bool recoveryPassed = false;
    bool libraryComplete = false;
    bool libraryPassed = false;
    bool captureComplete = false;
    bool captureApplicable = false;
    bool capturePassed = false;
    bool cleanupComplete = true;
    std::uint32_t generationBefore = 0;
    std::uint32_t generationAfter = 0;
    std::size_t observationsBefore = 0;
    std::size_t observationsAfter = 0;
    std::size_t jsonBytes = 0;
    std::size_t metadataBytes = 0;
    std::size_t csvBytes = 0;
    std::size_t csvRecords = 0;
    std::size_t csvIndex = 0;
    std::size_t pcapBytes = 0;
    std::size_t pcapFrames = 0;
    std::uint32_t pcapFnv1a = 2166136261U;
    std::uint32_t blockedWriteAttempts = 0;
    bool disposableCommitComplete = false;
    bool disposableCommitPassed = false;
    bool disposableRemountComplete = false;
    bool disposableRemountPassed = false;
    bool disposableExportComplete = false;
    bool disposableExportPassed = false;
    bool disposableCleanupComplete = false;
    bool disposableCleanupPassed = false;
    bool productVerifyComplete = false;
    bool productVerifyPassed = false;
    bool disposableResourceAcquired = false;
    bool disposableResourceReleased = true;
    bool disposableIdentityPassed = false;
    bool scratchPreexisting = false;
    bool scratchCreated = false;
    bool scratchRemoved = false;
    bool workflowPassed = true;
    char disposableObservedFingerprint[33] = {};
    char disposableScratchPath[leshy1::storage::kScratchPathMax] = {};
    std::uint32_t disposableGeneration = 0;
    std::size_t disposableObservations = 0;
    std::size_t disposableJsonBytes = 0;
    std::size_t disposableMetadataBytes = 0;
    std::size_t disposableCsvBytes = 0;
    std::size_t disposableCsvRecords = 0;
    std::uint64_t disposableStorageWriteBytes = 0;
    std::uint32_t disposableStorageWriteCalls = 0;
    std::uint32_t disposableFileSyncs = 0;
    std::uint32_t disposableDirectorySyncs = 0;
    std::uint16_t disposableFilesRemoved = 0;
    std::uint32_t productGenerationFinal = 0;
    std::size_t productObservationsFinal = 0;
};
struct FullGuidedPcapSink final {
    std::size_t bytes = 0;
    std::uint32_t fnv1a = 2166136261U;
};
bool writeFullGuidedPcapBytes(const std::uint8_t* data, std::size_t size,
                              void* context) {
    if ((data == nullptr && size != 0) || context == nullptr) return false;
    auto* sink = static_cast<FullGuidedPcapSink*>(context);
    for (std::size_t index = 0; index < size; ++index) {
        sink->fnv1a ^= data[index];
        sink->fnv1a *= 16777619U;
    }
    sink->bytes += size;
    return true;
}
FullGuidedArtifactState fullGuidedArtifactState;
std::uint64_t fullGuidedArtifactStartAfterUs = 0;
enum class RfSpectrumKind : std::uint8_t {
    Nrf24,
    Cc1101,
};
enum class RfSpectrumView : std::uint8_t {
    None,
    SourceMenu,
    SubGhzMenu,
    CcBandMenu,
    SubGhzCaptureBandMenu,
    SubGhzCaptureLive,
    Live,
};
const char* rfSpectrumViewName(RfSpectrumView view) {
    switch (view) {
        case RfSpectrumView::None: return "none";
        case RfSpectrumView::SourceMenu: return "source_menu";
        case RfSpectrumView::SubGhzMenu: return "subghz_menu";
        case RfSpectrumView::CcBandMenu: return "cc_band_menu";
        case RfSpectrumView::SubGhzCaptureBandMenu:
            return "subghz_capture_band_menu";
        case RfSpectrumView::SubGhzCaptureLive:
            return "subghz_capture_live";
        case RfSpectrumView::Live: return "live";
    }
    return "unknown";
}
RfSpectrumView rfSpectrumView = RfSpectrumView::None;
RfSpectrumKind rfSpectrumKind = RfSpectrumKind::Nrf24;
std::uint8_t rfSpectrumSelection = 0;
std::uint8_t subGhzModeSelection = 0;
enum class WifiProductView : std::uint8_t {
    None,
    Menu,
    Networks,
    NetworkDetail,
    Devices,
    DeviceDetail,
    DeviceRadar,
    Channels,
    Capture,
};

const char* wifiProductViewName(WifiProductView view) {
    switch (view) {
        case WifiProductView::Menu: return "menu";
        case WifiProductView::Networks: return "networks";
        case WifiProductView::NetworkDetail: return "network_detail";
        case WifiProductView::Devices: return "devices";
        case WifiProductView::DeviceDetail: return "device_detail";
        case WifiProductView::DeviceRadar: return "device_radar";
        case WifiProductView::Channels: return "channels";
        case WifiProductView::Capture: return "capture";
        case WifiProductView::None:
        default: return "none";
    }
}
WifiProductView wifiProductView = WifiProductView::None;
std::uint8_t wifiProductSelection = 0;
WifiNetworkCatalog wifiNetworkCatalog;
WifiNetworkNavigationOrder wifiNetworkNavigationOrder;
std::size_t wifiNetworkSelection = 0;
Observation wifiNetworkDetail;

std::size_t wifiNetworkVisibleSize() {
    return wifiNetworkNavigationOrder.size(wifiNetworkCatalog);
}

const Observation* wifiNetworkAt(std::size_t index) {
    return wifiNetworkNavigationOrder.at(wifiNetworkCatalog, index);
}
WifiDeviceCatalog wifiDeviceCatalog;
WifiDeviceNavigationOrder wifiDeviceNavigationOrder;
WifiOuiDatabase wifiOuiDatabase(
    wifiOuiAssetStart,
    static_cast<std::size_t>(wifiOuiAssetEnd - wifiOuiAssetStart));
std::size_t wifiDeviceSelection = 0;
WifiDeviceRecord wifiDeviceDetail;
std::uint64_t nextWifiDeviceUiRefreshUs = 0;

std::size_t wifiDeviceVisibleSize() {
    return wifiDeviceNavigationOrder.size(wifiDeviceCatalog);
}

const WifiDeviceRecord* wifiDeviceAt(std::size_t index) {
    return wifiDeviceNavigationOrder.at(wifiDeviceCatalog, index);
}
enum class BleProductView : std::uint8_t {
    None,
    Devices,
    DeviceDetail,
};
const char* bleProductViewName(BleProductView view) {
    switch (view) {
        case BleProductView::Devices: return "devices";
        case BleProductView::DeviceDetail: return "device_detail";
        case BleProductView::None:
        default: return "none";
    }
}
BleProductView bleProductView = BleProductView::None;
BleDeviceCatalog bleDeviceCatalog;
std::size_t bleDeviceSelection = 0;
Observation bleDeviceDetail;
std::array<std::uint16_t, 13> wifiChannelRenderedLoads{};
std::uint8_t wifiChannelRenderedBest = 0xffU;
std::uint32_t wifiCaptureRenderedFrames = UINT32_MAX;
std::uint32_t wifiCaptureRenderedDrops = UINT32_MAX;
std::uint8_t wifiCaptureRenderedChannel = 0xffU;
leshy1::drivers::radio::Cc1101SpectrumBand rfCcBandSelection =
    leshy1::drivers::radio::Cc1101SpectrumBand::Band433;
std::uint64_t nextSpectrumUiRefreshUs = 0;
SubGhzRawCapture subGhzRawCapture;
std::uint64_t nextSubGhzCaptureUiRefreshUs = 0;
std::uint64_t spectrumWaterfallStartedUs = 0;
std::uint64_t spectrumWaterfallCompletedUs = 0;
std::uint32_t spectrumWaterfallRowsEmitted = 0;
std::uint64_t spectrumWaterfallPreviousRowUs = 0;
std::uint64_t spectrumWaterfallRowIntervalTotalUs = 0;
std::uint64_t spectrumWaterfallRowIntervalMaxUs = 0;
std::uint64_t spectrumWaterfallPushTotalUs = 0;
std::uint64_t spectrumWaterfallPushMaxUs = 0;
std::uint64_t spectrumWaterfallRenderTotalUs = 0;
std::uint64_t spectrumWaterfallRenderMaxUs = 0;
std::uint64_t spectrumWaterfallServiceMaxUs = 0;
std::uint64_t nrf24SpectrumChunkMaxUs = 0;
std::uint64_t spectrumLoopPreviousUs = 0;
std::uint64_t spectrumLoopIntervalTotalUs = 0;
std::uint64_t spectrumLoopIntervalMaxUs = 0;
std::uint64_t spectrumLoopCount = 0;
std::uint64_t spectrumTouchPollTotalUs = 0;
std::uint64_t spectrumTouchPollMaxUs = 0;
std::uint64_t spectrumTouchPollCount = 0;
std::uint32_t spectrumWaterfallSourceSweepBaseline = 0;
std::uint32_t spectrumWaterfallLastSourceSweep = 0;
std::uint32_t spectrumWaterfallMeasurementsConsumed = 0;
std::uint32_t spectrumWaterfallMeasurementsSkipped = 0;
std::uint64_t spectrumWaterfallFillElapsedUs() {
    return spectrumWaterfallCompletedUs >= spectrumWaterfallStartedUs
        ? spectrumWaterfallCompletedUs - spectrumWaterfallStartedUs : 0;
}

void resetSpectrumWaterfallTiming() {
    spectrumWaterfallStartedUs = 0;
    spectrumWaterfallCompletedUs = 0;
    spectrumWaterfallRowsEmitted = 0;
    spectrumWaterfallPreviousRowUs = 0;
    spectrumWaterfallRowIntervalTotalUs = 0;
    spectrumWaterfallRowIntervalMaxUs = 0;
    spectrumWaterfallPushTotalUs = 0;
    spectrumWaterfallPushMaxUs = 0;
    spectrumWaterfallRenderTotalUs = 0;
    spectrumWaterfallRenderMaxUs = 0;
    spectrumWaterfallServiceMaxUs = 0;
    spectrumLoopPreviousUs = 0;
    spectrumLoopIntervalTotalUs = 0;
    spectrumLoopIntervalMaxUs = 0;
    spectrumLoopCount = 0;
    spectrumTouchPollTotalUs = 0;
    spectrumTouchPollMaxUs = 0;
    spectrumTouchPollCount = 0;
    spectrumWaterfallSourceSweepBaseline = 0;
    spectrumWaterfallLastSourceSweep = 0;
    spectrumWaterfallMeasurementsConsumed = 0;
    spectrumWaterfallMeasurementsSkipped = 0;
}

void armSpectrumWaterfallForCurrentReceiver();
BoardWifiPassiveCapture wifiFrameCapture;
constexpr WifiFrameCapturePlan kProductWifiFrameCapturePlan{};
std::uint64_t nextCaptureUiRefreshUs = 0;
enum class CaptureView : std::uint8_t {
    SourceMenu,
    Wifi,
    Infrared,
};
CaptureView captureView = CaptureView::SourceMenu;
std::uint8_t captureSourceSelection = 0;
InfraredCapture infraredCapture;
constexpr InfraredCapturePlan kProductInfraredCapturePlan{};
BoardInfraredReceiver boardInfraredReceiver;
InfraredReceiverReport infraredReceiverReport;
enum class CapturePersistState : std::uint8_t {
    Result,
    Confirm,
    Saving,
    Saved,
    Failed,
};
struct CaptureStoreEvent final {
    const char* status = "not_started";
    bool valid = false;
    bool cleanupComplete = false;
    std::uint32_t generation = 0;
    leshy1::storage::SessionStoreStatus storeStatus =
        leshy1::storage::SessionStoreStatus::InvalidArgument;
};
CapturePersistState capturePersistState = CapturePersistState::Result;
const char* capturePersistStatus = "volatile";
std::uint32_t capturePersistGeneration = 0;
QueueHandle_t captureStoreEvents = nullptr;
TaskHandle_t captureStoreTaskHandle = nullptr;
CapturePersistState subGhzCapturePersistState = CapturePersistState::Result;
const char* subGhzCapturePersistStatus = "volatile";
std::uint32_t subGhzCapturePersistGeneration = 0;
QueueHandle_t subGhzCaptureStoreEvents = nullptr;
TaskHandle_t subGhzCaptureStoreTaskHandle = nullptr;
CapturePersistState infraredCapturePersistState = CapturePersistState::Result;
const char* infraredCapturePersistStatus = "volatile";
std::uint32_t infraredCapturePersistGeneration = 0;
QueueHandle_t infraredCaptureStoreEvents = nullptr;
TaskHandle_t infraredCaptureStoreTaskHandle = nullptr;
const char* capturePersistStateName(CapturePersistState state) {
    switch (state) {
        case CapturePersistState::Result: return "volatile";
        case CapturePersistState::Confirm: return "confirm";
        case CapturePersistState::Saving: return "saving";
        case CapturePersistState::Saved: return "saved";
        case CapturePersistState::Failed: return "failed";
    }
    return "failed";
}
constexpr std::size_t kConsoleCommandCapacity = 192;
constexpr char kLongestConsoleCommand[] =
    "storage.littlefs.reset recover read-only "
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff "
    "s3-littlefs-reset-20260818-b6 6";
static_assert(sizeof(kLongestConsoleCommand) <= kConsoleCommandCapacity,
              "console command buffer cannot hold the longest command");
char usbCommand[kConsoleCommandCapacity] = {};
char uartCommand[kConsoleCommandCapacity] = {};
std::size_t usbLength = 0;
std::size_t uartLength = 0;
std::uint8_t lastInputRaw = 0xFF;
Pcf8574ButtonInput physicalButtonInput;

struct PhysicalInputEvent final {
    UiAction action = UiAction::Unknown;
    std::uint8_t raw = 0xFF;
    std::uint32_t atMs = 0;
    std::uint64_t atUs = 0;
};

constexpr UBaseType_t kPhysicalInputQueueCapacity = 64;
QueueHandle_t physicalInputEvents = nullptr;
TaskHandle_t physicalInputTaskHandle = nullptr;
portMUX_TYPE physicalInputMux = portMUX_INITIALIZER_UNLOCKED;
std::uint32_t physicalInputQueueDrops = 0;
std::uint32_t physicalInputQueueHighWater = 0;
std::uint32_t physicalInputDispatchedPresses = 0;
UiAction lastPhysicalInputAction = UiAction::Unknown;
bool lastPhysicalInputChanged = false;
std::uint64_t lastPhysicalInputQueueUs = 0;
std::uint64_t maximumPhysicalInputQueueUs = 0;
std::uint64_t lastPhysicalInputRenderUs = 0;
std::uint64_t lastPhysicalInputEndToEndUs = 0;
std::uint64_t maximumPhysicalInputEndToEndUs = 0;
bool physicalInputTaskStarted = false;
std::uint32_t touchHandledPresses = 0;
std::uint32_t touchMissedPresses = 0;
std::uint32_t syntheticTouchPresses = 0;
TouchPoint lastTouchPoint{};
bool lastTouchChanged = false;

struct ProductBootRecoveryState final {
    const char* status = "not_started";
    char expectedFingerprint[33] = {};
    char observedFingerprint[33] = {};
    bool enrolled = false;
    bool fingerprintMatched = false;
    bool mountedReadOnly = false;
    bool readOnlyGuaranteed = false;
    bool rootExists = false;
    bool opened = false;
    bool catalogAdmitted = false;
    bool cleanupComplete = false;
    leshy1::storage::ProductStoreAccessStatus permitStatus =
        leshy1::storage::ProductStoreAccessStatus::MissingMedia;
    leshy1::apps::library::SessionCatalogResult catalog{};
    std::uint32_t ownedDuring = 0;
    std::uint32_t ownedAfter = 0;
    std::uint32_t blockedWriteAttempts = 0;
    std::uint8_t attempts = 0;
    std::uint8_t transientRetries = 0;
    std::uint8_t timeoutRestarts = 0;
};

ProductBootRecoveryState productBootRecovery;
constexpr std::uint32_t kProductBootRetryRtcMagic = 0x4C425231U;
constexpr std::uint32_t kProductBootWatchdogTestRtcMagic = 0x4C425754U;
RTC_NOINIT_ATTR std::uint32_t productBootRetryRtcMagic;
RTC_NOINIT_ATTR volatile std::uint32_t productBootRetryRestarts;
RTC_NOINIT_ATTR std::uint32_t productBootRetryAppIdentity;
RTC_NOINIT_ATTR volatile std::uint32_t productBootRetryTimeouts;
RTC_NOINIT_ATTR std::uint32_t productBootWatchdogTestRtcState;
RTC_NOINIT_ATTR volatile SafetyRetainedRecord safetyRetainedRtc;
volatile std::uint32_t runtimeSafetyWatchdogArmed = 0;
volatile std::uint32_t runtimeSafetyAppIdentity = 0;
volatile std::uint32_t runtimeSafetyNextTripCount = 1;
volatile std::uint32_t runtimeSafetyNextQuiesceCount = 1;
SafetySupervisor safetySupervisor;
std::uint32_t runningAppIdentity = 0;
bool runtimeSafetyWatchdogReady = false;
constexpr std::uint32_t kLittleFsResetRtcMagic = 0x4C465231U;
struct LittleFsResetRtcState final {
    std::uint32_t magic;
    std::uint32_t boundary;
    std::uint8_t token[32];
};
RTC_NOINIT_ATTR LittleFsResetRtcState littleFsResetRtcState;
TaskHandle_t productBootRecoveryWatchdogTask = nullptr;
bool productBootRecoveryTaskWatchdogAdded = false;
volatile std::uint32_t productBootRecoveryWatchdogArmed = 0;

static_assert(CONFIG_ESP_TASK_WDT_EN && CONFIG_ESP_TASK_WDT_INIT &&
                  CONFIG_ESP_TASK_WDT_PANIC,
              "boot recovery requires the panic-enabled Task WDT");
static_assert(
    leshy1::storage::kProductBootRecoveryHardwareWatchdogMs ==
        CONFIG_ESP_TASK_WDT_TIMEOUT_S * 1000U,
    "boot recovery hardware watchdog policy must match the SDK configuration");

struct ProductSurveyRuntimeState final {
    const char* status = "idle";
    bool selected = false;
    bool backendOpen = false;
    bool identityCleanupComplete = true;
    bool filesystemAttempted = false;
    bool scannerCleanupComplete = true;
    bool cleanupComplete = true;
    std::uint8_t identityAttempts = 0;
    std::uint8_t identityTransientRetries = 0;
    leshy1::storage::SdTransportRunStatus identityStatus =
        leshy1::storage::SdTransportRunStatus::InvalidPlan;
    char expectedFingerprint[33] = {};
    char observedFingerprint[33] = {};
    std::uint64_t cardCapacityBytes = 0;
    std::uint64_t cachedFreeBytes = 0;
    leshy1::storage::ProductStoreAccessStatus storeStatus =
        leshy1::storage::ProductStoreAccessStatus::MissingMedia;
    leshy1::apps::survey::ProductSurveyAdmissionStatus admissionStatus =
        leshy1::apps::survey::ProductSurveyAdmissionStatus::ExplicitStartRequired;
    BoardWifiPassiveScanResult scan{};
    BoardBlePassiveScanResult bleScan{};
    bool workerReady = false;
    bool sourceActive = false;
    bool sourceStartAttempted = false;
    bool sourceFailureInjected = false;
    bool runtimeSourceFailureInjected = false;
    std::uint8_t runtimeSourceFailureInjectedMask = 0;
    bool storeOpenAttempted = false;
    std::uint64_t storeBytesWritten = 0;
    bool cancelRequestedDuringScan = false;
    std::uint32_t scanCycles = 0;
    std::uint32_t wifiScanCycles = 0;
    std::uint32_t bleScanCycles = 0;
    std::uint64_t startActionUs = 0;
    std::uint64_t stopActionUs = 0;
    std::uint8_t selectedSourceMask = 0;
    std::uint8_t activeSourceMask = 0;
    std::uint8_t unavailableSourceMask = 0;
    const char* timelineStatus = "idle";
    const char* timelineArchiveStatus = "idle";
    const char* timelineFailureStatus = "none";
    const char* timelineFailureStage = "none";
    std::uint64_t timelineFailureEventUs = 0;
    std::uint64_t timelineFailureLatestUs = 0;
    bool timelineHealthy = true;
    std::uint32_t timelineArchivedWindows = 0;
};

ProductSurveyRuntimeState productSurveyRuntime;

enum class ProductSurveyWorkerControl : std::uint8_t {
    Idle,
    Starting,
    Running,
    Paused,
    PauseRequested,
    StopRequested,
    CancelRequested,
};

enum class ProductSurveyWorkerEventKind : std::uint8_t {
    Prepared,
    ScanStarted,
    Scan,
    SourceUnavailable,
    Paused,
    Stopped,
    Cancelled,
    Failed,
};

struct ProductSurveyWorkerReport final {
    const char* status = "idle";
    bool backendOpen = false;
    bool identityCleanupComplete = true;
    bool filesystemAttempted = false;
    bool scannerCleanupComplete = true;
    bool cleanupComplete = true;
    bool sourceActive = false;
    bool sourceStartAttempted = false;
    bool sourceFailureInjected = false;
    bool runtimeSourceFailureInjected = false;
    std::uint8_t runtimeSourceFailureInjectedMask = 0;
    bool storeOpenAttempted = false;
    std::uint64_t storeBytesWritten = 0;
    std::uint8_t identityAttempts = 0;
    std::uint8_t identityTransientRetries = 0;
    leshy1::storage::SdTransportRunStatus identityStatus =
        leshy1::storage::SdTransportRunStatus::InvalidPlan;
    char expectedFingerprint[33] = {};
    char observedFingerprint[33] = {};
    std::uint64_t cardCapacityBytes = 0;
    std::uint64_t cachedFreeBytes = 0;
    leshy1::storage::ProductStoreAccessStatus storeStatus =
        leshy1::storage::ProductStoreAccessStatus::MissingMedia;
    leshy1::apps::survey::ProductSurveyAdmissionStatus admissionStatus =
        leshy1::apps::survey::ProductSurveyAdmissionStatus::ExplicitStartRequired;
    std::uint8_t selectedSourceMask = 0;
    std::uint8_t activeSourceMask = 0;
    std::uint8_t unavailableSourceMask = 0;
};

struct ProductSurveyWorkerEvent final {
    ProductSurveyWorkerEventKind kind = ProductSurveyWorkerEventKind::Failed;
    ProductSurveyWorkerReport report{};
    RadioKind source = RadioKind::Wifi;
    BoardWifiPassiveScanResult scan{};
    BoardBlePassiveScanResult bleScan{};
    std::uint32_t scanCycles = 0;
    std::uint32_t sourceScanCycles = 0;
    std::uint64_t eventUs = 0;
    std::uint64_t scanStartedUs = 0;
    std::uint64_t scanEndedUs = 0;
    std::uint16_t scanDropped = 0;
    SourceWindowState failureState = SourceWindowState::Fault;
    SourceWindowReason failureReason = SourceWindowReason::DriverFault;
};

constexpr UBaseType_t kProductSurveyWorkerEventCapacity = 8;
constexpr UBaseType_t kProductSurveyObservationCapacity =
    leshy1::services::survey::SurveySession::kObservationCapacity;
constexpr std::uint32_t kProductSurveyScanIntervalMs = 1000;
QueueHandle_t productSurveyWorkerEvents = nullptr;
QueueHandle_t productSurveyObservations = nullptr;
StaticSemaphore_t productSurveyScanStartGateStorage{};
SemaphoreHandle_t productSurveyScanStartGate = nullptr;
TaskHandle_t productSurveyWorkerTaskHandle = nullptr;
portMUX_TYPE productSurveyWorkerMux = portMUX_INITIALIZER_UNLOCKED;
ProductSurveyWorkerControl productSurveyWorkerControl =
    ProductSurveyWorkerControl::Idle;
std::uint32_t productSurveyWorkerOwnedResources = 0;
bool productSurveyWorkerReady = false;
bool productSurveyWorkerScanActive = false;
bool productSurveySourceUnavailableOnce = false;
std::uint8_t productSurveyRuntimeUnavailableOnceMask = 0;
bool productSurveyIncrementalRefreshPending = false;

void renderInteractiveScreen(bool clearContent = true);
void broadcast(const char* line);

bool lastUiActionUsedIncrementalRender = false;
bool lastUiRenderWasIncremental = false;
std::uint64_t lastUiRenderUs = 0;

struct SdPhysicalEvidenceWorkspace final {
    char line[6144] = {};
    char summaryA[512] = {};
    char summaryB[512] = {};
    char summaryC[512] = {};
    char cidHex[33] = {};
    std::array<std::uint8_t, 512> sectorA{};
    std::array<std::uint8_t, 512> sectorB{};
    std::array<std::uint8_t, 512> sectorC{};
    std::array<std::uint64_t, kSdThroughputSamples> commitUs{};
};

SdPhysicalEvidenceWorkspace sdPhysicalEvidence;
// Diagnostic replies and explicit physical-storage commands run serially on the
// main loop. Reuse their largest scratch line instead of reserving a second 5 KiB
// buffer that would permanently reduce the no-PSRAM product heap.
auto& diagnosticJson = sdPhysicalEvidence.line;

struct StoredGenerationEvidence final {
    std::uint32_t expectedSegmentCrc = 0;
    std::uint32_t observedSegmentCrc = 0;
    std::uint32_t expectedManifestCrc = 0;
    std::uint32_t observedManifestCrc = 0;
    std::size_t expectedSegmentSize = 0;
    std::size_t observedSegmentSize = 0;
    std::size_t expectedManifestSize = 0;
    std::size_t observedManifestSize = 0;
    bool unchanged = false;
};

struct ResetBoundaryHookContext final {
    Stream* reply = nullptr;
    const char* runId = nullptr;
    unsigned boundaryNumber = 0;
};

leshy1::storage::CommitStage resetBoundaryStage(unsigned number);
const char* resetExpectedRecovery(unsigned boundary);
bool resetRecoveredGenerationAllowed(unsigned boundary,
                                     std::uint32_t generation);
bool prepareLittleFsResetFixture();
bool inspectStoredGeneration(
    leshy1::storage::SessionStoreIo& io,
    leshy1::storage::SessionStoreWorkspace& workspace,
    const SurveySession& expected, std::uint32_t generation,
    StoredGenerationEvidence* evidence);
bool armLittleFsResetContinuity(const char* fingerprint, const char* runId,
                                unsigned boundary);
bool littleFsResetContinuityValid(const char* fingerprint, const char* runId,
                                  unsigned boundary);
void restartAtLittleFsSessionStoreBoundary(
    void* rawContext, leshy1::storage::CommitStage boundary);

constexpr std::int32_t kScreenWidth = Layout::ScreenWidth;
constexpr std::int32_t kScreenHeight = Layout::ScreenHeight;
constexpr std::int32_t kCaptureRows = 4;

bool appendGoldenObservations(SurveySession& session) {
    static constexpr std::uint8_t kBssids[3][6] = {
        {0x02, 0x00, 0x00, 0x00, 0x00, 0x01},
        {0x02, 0x00, 0x00, 0x00, 0x00, 0x02},
        {0x02, 0x00, 0x00, 0x00, 0x00, 0x03},
    };
    static constexpr std::uint8_t kChannels[3] = {1, 6, 11};
    static constexpr std::int16_t kRssi[3] = {-71, -55, -83};
    static constexpr const char* kSsids[3] = {"alpha", "bravo", "charlie"};
    for (std::size_t index = 0; index < 3; ++index) {
        WifiScanRecord record;
        std::memcpy(record.bssid.data(), kBssids[index], record.bssid.size());
        record.channel = kChannels[index];
        record.rssiDbm = kRssi[index];
        record.ssid = kSsids[index];
        record.ssidLength = std::strlen(kSsids[index]);
        Observation observation;
        if (!leshy1::drivers::wifi::normalizePassiveRecord(
                record, 2000 + static_cast<std::uint64_t>(index), &observation) ||
            session.append(observation) != SessionStatus::Appended) {
            return false;
        }
    }
    return true;
}

bool publishGoldenObservations(SurveyPipeline& pipeline) {
    static constexpr std::uint8_t kBssids[3][6] = {
        {0x02, 0x00, 0x00, 0x00, 0x00, 0x01},
        {0x02, 0x00, 0x00, 0x00, 0x00, 0x02},
        {0x02, 0x00, 0x00, 0x00, 0x00, 0x03},
    };
    static constexpr std::uint8_t kChannels[3] = {1, 6, 11};
    static constexpr std::int16_t kRssi[3] = {-71, -55, -83};
    static constexpr const char* kSsids[3] = {"alpha", "bravo", "charlie"};
    for (std::size_t index = 0; index < 3; ++index) {
        WifiScanRecord record;
        std::memcpy(record.bssid.data(), kBssids[index], record.bssid.size());
        record.channel = kChannels[index];
        record.rssiDbm = kRssi[index];
        record.ssid = kSsids[index];
        record.ssidLength = std::strlen(kSsids[index]);
        Observation observation;
        if (!leshy1::drivers::wifi::normalizePassiveRecord(
                record, surveySession.startedUs() + 1000U +
                            static_cast<std::uint64_t>(index),
                &observation) ||
            pipeline.enqueue(observation) != SurveyPipelineStatus::Queued) {
            return false;
        }
    }
    return pipeline.drain(
               leshy1::services::survey::ObservationQueue::kCapacity) ==
           SurveyPipelineStatus::Drained;
}

bool prepareSurveyDemo() {
    return surveyPipeline.resetToSetup() == SurveyPipelineStatus::Ready;
}

bool prepareLibraryDemo() {
    librarySession.reset();
    if (librarySession.start("golden-wifi-lib", 1000) != SessionStatus::Started ||
        !appendGoldenObservations(librarySession) ||
        librarySession.stop(3000) != SessionStatus::Stopped) {
        return false;
    }
    ramSessionStore.reset();
    const leshy1::storage::SessionStoreCommitResult committed =
        leshy1::storage::commitNextSession(ramSessionStore, sessionStoreWorkspace,
                                           librarySession);
    if (!committed.complete()) return false;
    libraryController.clear();
    const leshy1::apps::library::SessionCatalogResult cataloged =
        sessionCatalog.recoverLatest(ramSessionStore, sessionStoreWorkspace,
                                     librarySession, libraryController, false,
                                     true);
    return cataloged.admitted() && cataloged.generation == 1 &&
           cataloged.observations == 3;
}

bool exactCidFingerprint(const char* value) {
    if (value == nullptr || std::strlen(value) != 32) return false;
    for (std::size_t index = 0; index < 32; ++index) {
        const char current = value[index];
        if (!((current >= '0' && current <= '9') ||
              (current >= 'A' && current <= 'F'))) {
            return false;
        }
    }
    return true;
}

void formatCidFingerprint(const leshy1::storage::SdIdentity& identity,
                          char* output, std::size_t capacity) {
    if (output == nullptr || capacity < 33) return;
    output[0] = '\0';
    for (std::size_t index = 0; index < identity.cid.size(); ++index) {
        std::snprintf(output + index * 2, capacity - index * 2, "%02X",
                      static_cast<unsigned>(identity.cid[index]));
    }
}

bool loadProductFingerprint(char* output, std::size_t capacity) {
    if (output == nullptr || capacity < 33) return false;
    output[0] = '\0';
    Preferences preferences;
    if (!preferences.begin(kProductEnrollmentNamespace, true)) return false;
    const std::size_t stored = preferences.getBytesLength(kProductEnrollmentKey);
    const std::size_t read = stored == 33
        ? preferences.getBytes(kProductEnrollmentKey, output, 33) : 0;
    preferences.end();
    if (read != 33 || output[32] != '\0' || !exactCidFingerprint(output)) {
        output[0] = '\0';
        return false;
    }
    return true;
}

bool saveProductFingerprint(const char* fingerprint) {
    if (!exactCidFingerprint(fingerprint)) return false;
    Preferences preferences;
    if (!preferences.begin(kProductEnrollmentNamespace, false)) return false;
    const std::size_t written = preferences.putBytes(
        kProductEnrollmentKey, fingerprint, 33);
    preferences.end();
    char verified[33] = {};
    return written == 33 && loadProductFingerprint(verified, sizeof(verified)) &&
           std::strcmp(verified, fingerprint) == 0;
}

bool clearProductFingerprint() {
    char existing[33] = {};
    if (!loadProductFingerprint(existing, sizeof(existing))) return true;
    Preferences preferences;
    if (!preferences.begin(kProductEnrollmentNamespace, false)) return false;
    const bool removed = preferences.remove(kProductEnrollmentKey);
    preferences.end();
    char verified[33] = {};
    return removed && !loadProductFingerprint(verified, sizeof(verified));
}

UiLanguage loadUiLanguage() {
    Preferences preferences;
    if (!preferences.begin(kUiPreferencesNamespace, true)) {
        return UiLanguage::English;
    }
    const std::uint8_t stored = preferences.getUChar(kUiLanguageKey, 0);
    preferences.end();
    return stored == static_cast<std::uint8_t>(UiLanguage::Russian)
               ? UiLanguage::Russian
               : UiLanguage::English;
}

bool saveUiLanguage(UiLanguage language) {
    Preferences preferences;
    if (!preferences.begin(kUiPreferencesNamespace, false)) return false;
    const std::size_t written = preferences.putUChar(
        kUiLanguageKey, static_cast<std::uint8_t>(language));
    preferences.end();
    return written == sizeof(std::uint8_t);
}

bool closeProductSurveyBackend() {
    productSurveyRuntime.storeBytesWritten = productSurveyStore.bytesWritten();
    productSurveyStore.end();
    const bool filesystemWasMounted = productSurveyFilesystem.mounted();
    if (filesystemWasMounted) productSurveyFilesystem.end();
    surveyStoreRouter.bind(ramSessionStore);
    productSurveyRuntime.backendOpen = false;
    const bool filesystemCleanup =
        !productSurveyRuntime.filesystemAttempted ||
        productSurveyFilesystem.cleanupComplete();
    productSurveyRuntime.cleanupComplete =
        productSurveyRuntime.identityCleanupComplete &&
        productSurveyRuntime.scannerCleanupComplete && filesystemCleanup &&
        !productSurveyFilesystem.mounted() &&
        surveyStoreRouter.boundTo(ramSessionStore);
    return productSurveyRuntime.cleanupComplete;
}

ProductSurveyWorkerControl productSurveyControl() {
    portENTER_CRITICAL(&productSurveyWorkerMux);
    const ProductSurveyWorkerControl control = productSurveyWorkerControl;
    portEXIT_CRITICAL(&productSurveyWorkerMux);
    return control;
}

void setProductSurveyControl(ProductSurveyWorkerControl control) {
    portENTER_CRITICAL(&productSurveyWorkerMux);
    productSurveyWorkerControl = control;
    portEXIT_CRITICAL(&productSurveyWorkerMux);
}

bool transitionProductSurveyControl(ProductSurveyWorkerControl expected,
                                    ProductSurveyWorkerControl next) {
    bool changed = false;
    portENTER_CRITICAL(&productSurveyWorkerMux);
    if (productSurveyWorkerControl == expected) {
        productSurveyWorkerControl = next;
        changed = true;
    }
    portEXIT_CRITICAL(&productSurveyWorkerMux);
    return changed;
}

bool productSurveyStopRequested() {
    const ProductSurveyWorkerControl control = productSurveyControl();
    return control == ProductSurveyWorkerControl::PauseRequested ||
           control == ProductSurveyWorkerControl::StopRequested ||
           control == ProductSurveyWorkerControl::CancelRequested;
}

bool productSurveyCancelRequested() {
    return productSurveyControl() ==
           ProductSurveyWorkerControl::CancelRequested;
}

bool productSurveyScanActive() {
    portENTER_CRITICAL(&productSurveyWorkerMux);
    const bool active = productSurveyWorkerScanActive;
    portEXIT_CRITICAL(&productSurveyWorkerMux);
    return active;
}

bool productSurveySourceUnavailableInjectionArmed() {
    portENTER_CRITICAL(&productSurveyWorkerMux);
    const bool armed = productSurveySourceUnavailableOnce;
    portEXIT_CRITICAL(&productSurveyWorkerMux);
    return armed;
}

void setProductSurveySourceUnavailableInjection(bool armed) {
    portENTER_CRITICAL(&productSurveyWorkerMux);
    productSurveySourceUnavailableOnce = armed;
    portEXIT_CRITICAL(&productSurveyWorkerMux);
}

bool consumeProductSurveySourceUnavailableInjection() {
    portENTER_CRITICAL(&productSurveyWorkerMux);
    const bool injected = productSurveySourceUnavailableOnce;
    productSurveySourceUnavailableOnce = false;
    portEXIT_CRITICAL(&productSurveyWorkerMux);
    return injected;
}

std::uint8_t productSurveyRuntimeUnavailableInjectionMask() {
    portENTER_CRITICAL(&productSurveyWorkerMux);
    const std::uint8_t mask = productSurveyRuntimeUnavailableOnceMask;
    portEXIT_CRITICAL(&productSurveyWorkerMux);
    return mask;
}

void setProductSurveyRuntimeUnavailableInjection(std::uint8_t mask) {
    portENTER_CRITICAL(&productSurveyWorkerMux);
    productSurveyRuntimeUnavailableOnceMask = static_cast<std::uint8_t>(
        mask & leshy1::services::survey::kSupportedSourceMask);
    portEXIT_CRITICAL(&productSurveyWorkerMux);
}

bool consumeProductSurveyRuntimeUnavailableInjection(RadioKind source) {
    const std::uint8_t mask = leshy1::services::survey::sourceMask(source);
    bool injected = false;
    portENTER_CRITICAL(&productSurveyWorkerMux);
    if ((productSurveyRuntimeUnavailableOnceMask & mask) != 0) {
        productSurveyRuntimeUnavailableOnceMask = static_cast<std::uint8_t>(
            productSurveyRuntimeUnavailableOnceMask &
            static_cast<std::uint8_t>(~mask));
        injected = true;
    }
    portEXIT_CRITICAL(&productSurveyWorkerMux);
    return injected;
}

bool productSurveySourceUnavailableVisible() {
    return productSurveyRuntime.selected &&
        productSurveyRuntime.cleanupComplete &&
        productSurveyRuntime.admissionStatus ==
            leshy1::apps::survey::ProductSurveyAdmissionStatus::SourceUnavailable &&
        std::strcmp(productSurveyRuntime.status, "source_unavailable") == 0;
}

void setProductSurveyScanActive(bool active) {
    portENTER_CRITICAL(&productSurveyWorkerMux);
    productSurveyWorkerScanActive = active;
    portEXIT_CRITICAL(&productSurveyWorkerMux);
}

void applyProductSurveyWorkerReport(
    const ProductSurveyWorkerReport& report) {
    productSurveyRuntime.backendOpen = report.backendOpen;
    productSurveyRuntime.identityCleanupComplete =
        report.identityCleanupComplete;
    productSurveyRuntime.filesystemAttempted = report.filesystemAttempted;
    productSurveyRuntime.scannerCleanupComplete =
        report.scannerCleanupComplete;
    productSurveyRuntime.cleanupComplete = report.cleanupComplete;
    productSurveyRuntime.sourceActive = report.sourceActive;
    productSurveyRuntime.sourceStartAttempted = report.sourceStartAttempted;
    productSurveyRuntime.sourceFailureInjected = report.sourceFailureInjected;
    productSurveyRuntime.runtimeSourceFailureInjected =
        report.runtimeSourceFailureInjected;
    productSurveyRuntime.runtimeSourceFailureInjectedMask =
        report.runtimeSourceFailureInjectedMask;
    productSurveyRuntime.storeOpenAttempted = report.storeOpenAttempted;
    productSurveyRuntime.storeBytesWritten = report.storeBytesWritten;
    productSurveyRuntime.identityAttempts = report.identityAttempts;
    productSurveyRuntime.identityTransientRetries =
        report.identityTransientRetries;
    productSurveyRuntime.identityStatus = report.identityStatus;
    std::memcpy(productSurveyRuntime.expectedFingerprint,
                report.expectedFingerprint,
                sizeof(productSurveyRuntime.expectedFingerprint));
    std::memcpy(productSurveyRuntime.observedFingerprint,
                report.observedFingerprint,
                sizeof(productSurveyRuntime.observedFingerprint));
    productSurveyRuntime.cardCapacityBytes = report.cardCapacityBytes;
    productSurveyRuntime.cachedFreeBytes = report.cachedFreeBytes;
    productSurveyRuntime.storeStatus = report.storeStatus;
    productSurveyRuntime.admissionStatus = report.admissionStatus;
    productSurveyRuntime.activeSourceMask = report.activeSourceMask;
    productSurveyRuntime.unavailableSourceMask = report.unavailableSourceMask;
}

void accumulateProductSurveyScan(BoardWifiPassiveScanResult* total,
                                 const BoardWifiPassiveScanResult& scan) {
    if (total == nullptr) return;
    total->status = scan.status;
    total->driverError = scan.driverError;
    total->durationUs += scan.durationUs;
    total->recordsReported = static_cast<std::uint16_t>(
        total->recordsReported + scan.recordsReported);
    total->recordsRead = static_cast<std::uint16_t>(
        total->recordsRead + scan.recordsRead);
    total->accepted = static_cast<std::uint16_t>(
        total->accepted + scan.accepted);
    total->rejected = static_cast<std::uint16_t>(
        total->rejected + scan.rejected);
    total->dropped = static_cast<std::uint16_t>(
        total->dropped + scan.dropped);
}

void accumulateProductSurveyBleScan(BoardBlePassiveScanResult* total,
                                    const BoardBlePassiveScanResult& scan) {
    if (total == nullptr) return;
    total->status = scan.status;
    total->durationUs += scan.durationUs;
    total->recordsReported = static_cast<std::uint16_t>(
        total->recordsReported + scan.recordsReported);
    total->recordsRead = static_cast<std::uint16_t>(
        total->recordsRead + scan.recordsRead);
    total->accepted = static_cast<std::uint16_t>(
        total->accepted + scan.accepted);
    total->rejected = static_cast<std::uint16_t>(
        total->rejected + scan.rejected);
    total->dropped = static_cast<std::uint16_t>(
        total->dropped + scan.dropped);
}

SourceFailureClass productSurveyFailureClass(
    RadioKind source, const BoardWifiPassiveScanResult& wifiScan,
    const BoardBlePassiveScanResult& bleScan) {
    if (source == RadioKind::Wifi) {
        return wifiScan.status ==
                       leshy1::platform::arduino::BoardWifiScanStatus::NotStarted
                   ? SourceFailureClass::Unavailable
                   : SourceFailureClass::Fault;
    }
    switch (bleScan.status) {
        case leshy1::platform::arduino::BoardBleScanStatus::NotStarted:
        case leshy1::platform::arduino::BoardBleScanStatus::StackInitFailed:
        case leshy1::platform::arduino::BoardBleScanStatus::ScannerUnavailable:
            return SourceFailureClass::Unavailable;
        case leshy1::platform::arduino::BoardBleScanStatus::Valid:
        case leshy1::platform::arduino::BoardBleScanStatus::InvalidPlan:
        case leshy1::platform::arduino::BoardBleScanStatus::ScanTimedOut:
            return SourceFailureClass::Fault;
    }
    return SourceFailureClass::Fault;
}

WifiRecordDisposition enqueueProductSurveyWorkerRecord(
    const WifiScanRecord& record, std::uint64_t monotonicUs, void*) {
    Observation observation;
    if (!leshy1::drivers::wifi::normalizePassiveRecord(
            record, monotonicUs, &observation)) {
        return WifiRecordDisposition::Rejected;
    }
    if (productSurveyObservations == nullptr ||
        xQueueSend(productSurveyObservations, &observation, 0) != pdTRUE) {
        return WifiRecordDisposition::Dropped;
    }
    return WifiRecordDisposition::Accepted;
}

BleRecordDisposition enqueueProductSurveyWorkerBleRecord(
    const BleAdvertisementRecord& record, std::uint64_t monotonicUs, void*) {
    Observation observation;
    if (!leshy1::drivers::ble::normalizePassiveRecord(
            record, monotonicUs, &observation)) {
        return BleRecordDisposition::Rejected;
    }
    if (productSurveyObservations == nullptr ||
        xQueueSend(productSurveyObservations, &observation, 0) != pdTRUE) {
        return BleRecordDisposition::Dropped;
    }
    return BleRecordDisposition::Accepted;
}

void sendProductSurveyWorkerEvent(
    ProductSurveyWorkerEventKind kind,
    const ProductSurveyWorkerReport& report,
    RadioKind source = RadioKind::Wifi,
    const BoardWifiPassiveScanResult& scan = {},
    const BoardBlePassiveScanResult& bleScan = {},
    std::uint32_t scanCycles = 0, std::uint32_t sourceScanCycles = 0,
    std::uint64_t eventUs = 0,
    std::uint64_t scanStartedUs = 0, std::uint64_t scanEndedUs = 0,
    std::uint16_t scanDropped = 0,
    SourceWindowState failureState = SourceWindowState::Fault,
    SourceWindowReason failureReason = SourceWindowReason::DriverFault) {
    if (productSurveyWorkerEvents == nullptr) return;
    if (eventUs == 0) {
        eventUs = static_cast<std::uint64_t>(esp_timer_get_time());
        if (eventUs == 0) eventUs = 1;
    }
    const ProductSurveyWorkerEvent event{
        kind, report, source, scan, bleScan, scanCycles, sourceScanCycles,
        eventUs, scanStartedUs, scanEndedUs, scanDropped,
        failureState, failureReason};
    xQueueSend(productSurveyWorkerEvents, &event, portMAX_DELAY);
}

void cleanupProductSurveyWorkerHardware(
    ProductSurveyWorkerReport* report) {
    if (report == nullptr) return;
    report->storeBytesWritten = productSurveyStore.bytesWritten();
    productSurveyStore.end();
    if (productSurveyFilesystem.mounted()) productSurveyFilesystem.end();
    surveyStoreRouter.bind(ramSessionStore);
    report->backendOpen = false;
    const bool filesystemCleanup =
        !report->filesystemAttempted || productSurveyFilesystem.cleanupComplete();
    report->cleanupComplete = report->identityCleanupComplete &&
        report->scannerCleanupComplete && filesystemCleanup &&
        !productSurveyFilesystem.mounted() &&
        surveyStoreRouter.boundTo(ramSessionStore);
}

ProductSurveyWorkerReport prepareProductSurveyWorker(
    BoardWifiPassiveScanner* wifiScanner,
    BoardBlePassiveScanner* bleScanner) {
    ProductSurveyWorkerReport report;
    report.status = "preparing";
    report.cleanupComplete = false;
    if (wifiScanner == nullptr || bleScanner == nullptr) {
        report.status = "worker_missing";
        return report;
    }

    portENTER_CRITICAL(&productSurveyWorkerMux);
    const std::uint32_t ownedResources = productSurveyWorkerOwnedResources;
    const std::uint8_t selectedSourceMask =
        productSurveyRuntime.selectedSourceMask;
    portEXIT_CRITICAL(&productSurveyWorkerMux);
    report.selectedSourceMask = selectedSourceMask;
    const auto required =
        leshy1::kernel::runtime::resourceMask(Resource::UiForeground) |
        leshy1::kernel::runtime::resourceMask(Resource::EspRf) |
        leshy1::kernel::runtime::resourceMask(Resource::Storage) |
        leshy1::kernel::runtime::resourceMask(Resource::RadioSpi);
    if ((ownedResources & required) != required) {
        report.status = "resources_missing";
        return report;
    }
    if (!loadProductFingerprint(report.expectedFingerprint,
                                sizeof(report.expectedFingerprint))) {
        report.status = "enrollment_missing";
        return report;
    }

    leshy1::storage::SdTransportRunResult identity;
    for (std::uint8_t attempt = 1;
         attempt <= leshy1::storage::kProductStartMaximumIdentityAttempts;
         ++attempt) {
        if (productSurveyCancelRequested()) {
            report.status = "cancelled";
            return report;
        }
        BoardSdSpiTransport identityTransport;
        const bool identityBegun = identityTransport.begin();
        identity = {};
        if (identityBegun) {
            leshy1::storage::SdTransportRunPolicy policy;
            policy.allowPhysical = true;
            policy.explicitlySelected = true;
            policy.identificationOnly = true;
            policy.ownedResources = ownedResources;
            identity = leshy1::storage::runSdIdentificationStateMachine(
                leshy1::storage::defaultSdIdentificationPlan(),
                identityTransport, policy);
            identityTransport.end();
        }
        report.identityAttempts = attempt;
        report.identityTransientRetries =
            static_cast<std::uint8_t>(attempt - 1U);
        report.identityStatus = identity.status;
        report.identityCleanupComplete = identityTransport.cleanupComplete();
        formatCidFingerprint(identity.identity,
                             report.observedFingerprint,
                             sizeof(report.observedFingerprint));
        if (report.identityCleanupComplete &&
            identity.status == leshy1::storage::SdTransportRunStatus::Valid) {
            break;
        }
        const leshy1::storage::ProductStartIdentityRetryEvidence retryEvidence{
            true,
            true,
            exactCidFingerprint(report.expectedFingerprint),
            (ownedResources & required) == required,
            identityTransport.physicalSpiStarted(),
            identity.status,
            std::strcmp(report.observedFingerprint,
                        "00000000000000000000000000000000") == 0,
            report.identityCleanupComplete,
            report.filesystemAttempted,
        };
        if (!leshy1::storage::shouldRetryProductStartIdentity(
                retryEvidence, attempt)) {
            break;
        }
        ulTaskNotifyTake(
            pdTRUE,
            pdMS_TO_TICKS(
                leshy1::storage::productStartIdentityRetryDelayMs(attempt)));
    }
    if (productSurveyCancelRequested()) {
        report.status = "cancelled";
        return report;
    }
    if (!report.identityCleanupComplete ||
        identity.status != leshy1::storage::SdTransportRunStatus::Valid) {
        report.status = "identity_failed";
        return report;
    }
    if (std::strcmp(report.expectedFingerprint,
                    report.observedFingerprint) != 0) {
        report.status = "fingerprint_mismatch";
        return report;
    }

    report.filesystemAttempted = true;
    if (!productSurveyFilesystem.begin()) {
        report.status = "mount_failed";
        return report;
    }
    if (productSurveyCancelRequested()) {
        report.status = "cancelled";
        return report;
    }
    report.cardCapacityBytes = productSurveyFilesystem.cardCapacityBytes();
    report.cachedFreeBytes = productSurveyFilesystem.cachedFreeBytes();
    const bool capacityMatched =
        report.cardCapacityBytes != 0 &&
        report.cardCapacityBytes == identity.identity.capacityBytes;
    const bool rootExists = productSurveyFilesystem.exists(
        leshy1::storage::kProductSessionStoreRoot);

    leshy1::storage::MediaIdentity media;
    media.present = capacityMatched;
    media.kind = leshy1::storage::MediaKind::Sd;
    media.fingerprint = report.observedFingerprint;
    media.capacityBytes = report.cardCapacityBytes;
    media.freeBytes = report.cachedFreeBytes;
    leshy1::storage::ProductStoreRequest storeRequest;
    storeRequest.operation =
        leshy1::storage::ProductStoreOperation::CommitSession;
    storeRequest.explicitlySelected = true;
    storeRequest.expectedFingerprint = report.expectedFingerprint;
    storeRequest.rootPath = leshy1::storage::kProductSessionStoreRoot;
    storeRequest.rootExists = rootExists;
    storeRequest.driverWriteEnabled = true;
    storeRequest.requiredBytes = kProductSurveyCommitBytes;
    storeRequest.reserveBytes = kProductSurveyReserveBytes;
    storeRequest.ownedResources = ownedResources;
    const leshy1::storage::ProductStorePermit storePermit =
        leshy1::storage::authorizeProductStore(media, storeRequest);
    report.storeStatus = storePermit.status;
    if (!storePermit.allowed()) {
        report.status =
            leshy1::storage::productStoreAccessStatusName(storePermit.status);
        return report;
    }

    report.sourceFailureInjected =
        consumeProductSurveySourceUnavailableInjection();
    if (report.sourceFailureInjected) {
        report.sourceStartAttempted = false;
        report.activeSourceMask = 0;
        report.unavailableSourceMask = selectedSourceMask;
        leshy1::apps::survey::ProductSurveyRequest unavailableRequest;
        unavailableRequest.explicitStart = true;
        unavailableRequest.sourceAvailable = false;
        unavailableRequest.selectedSourceMask = selectedSourceMask;
        unavailableRequest.availableSourceMask = 0;
        unavailableRequest.scanPlan =
            leshy1::drivers::wifi::defaultPassivePlan();
        unavailableRequest.bleScanPlan =
            leshy1::drivers::ble::defaultPassivePlan();
        unavailableRequest.storePermit = storePermit;
        unavailableRequest.ownedResources = ownedResources;
        const auto unavailablePermit =
            leshy1::apps::survey::authorizeProductSurvey(unavailableRequest);
        report.admissionStatus = unavailablePermit.status;
        report.scannerCleanupComplete = true;
        report.status =
            leshy1::apps::survey::productSurveyAdmissionStatusName(
                unavailablePermit.status);
        return report;
    }

    // Validate the writable store before starting Wi-Fi/BLE, then release the
    // FAT/SDSPI stack completely.  The radio stacks and SDSPI both depend on
    // scarce DMA-capable internal heap on this no-PSRAM board and must not have
    // overlapping lifetimes.  The exact CID is checked again and the store is
    // reopened only after both scanners have stopped, immediately before the
    // atomic terminal commit.
    report.storeOpenAttempted = true;
    if (!productSurveyStore.selectDrive(productSurveyFilesystem.driveNumber()) ||
        !productSurveyStore.openExistingWritable(storePermit)) {
        report.status = "store_open_failed";
        return report;
    }
    productSurveyStore.end();
    productSurveyFilesystem.end();
    surveyStoreRouter.bind(ramSessionStore);
    report.backendOpen = false;
    if (!productSurveyFilesystem.cleanupComplete() ||
        productSurveyFilesystem.mounted() ||
        !surveyStoreRouter.boundTo(ramSessionStore)) {
        report.status = "storage_release_failed";
        return report;
    }
    if (productSurveyCancelRequested()) {
        report.status = "cancelled";
        return report;
    }

    report.sourceStartAttempted = selectedSourceMask != 0;
    const std::uint8_t wifiMask =
        leshy1::services::survey::sourceMask(RadioKind::Wifi);
    const std::uint8_t bleMask =
        leshy1::services::survey::sourceMask(RadioKind::Ble);
    const bool wifiSelected = (selectedSourceMask & wifiMask) != 0;
    const bool bleSelected = (selectedSourceMask & bleMask) != 0;
    const bool wifiBegun = wifiSelected ? wifiScanner->begin() : false;
    const bool bleBegun = bleSelected ? bleScanner->begin() : false;
    report.activeSourceMask = static_cast<std::uint8_t>(
        (wifiBegun ? wifiMask : 0U) | (bleBegun ? bleMask : 0U));
    report.unavailableSourceMask = static_cast<std::uint8_t>(
        selectedSourceMask & ~report.activeSourceMask);
    leshy1::apps::survey::ProductSurveyRequest surveyRequest;
    surveyRequest.explicitStart = true;
    surveyRequest.sourceAvailable = report.activeSourceMask != 0;
    surveyRequest.selectedSourceMask = selectedSourceMask;
    surveyRequest.availableSourceMask = report.activeSourceMask;
    surveyRequest.scanPlan = leshy1::drivers::wifi::defaultPassivePlan();
    surveyRequest.bleScanPlan = leshy1::drivers::ble::defaultPassivePlan();
    surveyRequest.storePermit = storePermit;
    surveyRequest.ownedResources = ownedResources;
    const leshy1::apps::survey::ProductSurveyPermit surveyPermit =
        leshy1::apps::survey::authorizeProductSurvey(surveyRequest);
    report.admissionStatus = surveyPermit.status;
    report.scannerCleanupComplete = !wifiBegun && !bleBegun;
    if (!surveyPermit.allowed()) {
        report.status =
            leshy1::apps::survey::productSurveyAdmissionStatusName(
                surveyPermit.status);
        return report;
    }
    if (productSurveyCancelRequested()) {
        report.status = "cancelled";
        return report;
    }
    report.sourceActive = true;
    report.status = "prepared";
    return report;
}

void runProductSurveyWorker(void*) {
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        if (productSurveyControl() != ProductSurveyWorkerControl::Starting) {
            continue;
        }
        if (productSurveyObservations != nullptr) {
            xQueueReset(productSurveyObservations);
        }
        setProductSurveyScanActive(false);
        BoardWifiPassiveScanner wifiScanner;
        BoardBlePassiveScanner bleScanner;
        ProductSurveyWorkerReport report =
            prepareProductSurveyWorker(&wifiScanner, &bleScanner);
        if (std::strcmp(report.status, "prepared") != 0) {
            const bool wifiCleanup = wifiScanner.end();
            const bool bleCleanup = bleScanner.end();
            report.scannerCleanupComplete = wifiCleanup && bleCleanup;
            report.sourceActive = false;
            cleanupProductSurveyWorkerHardware(&report);
            const bool cancelled = productSurveyCancelRequested() ||
                std::strcmp(report.status, "cancelled") == 0;
            sendProductSurveyWorkerEvent(
                cancelled ? ProductSurveyWorkerEventKind::Cancelled
                          : ProductSurveyWorkerEventKind::Failed,
                report);
            continue;
        }

        if (!transitionProductSurveyControl(
                ProductSurveyWorkerControl::Starting,
                ProductSurveyWorkerControl::Running)) {
            report.status = "cancelled";
            const bool wifiCleanup = wifiScanner.end();
            const bool bleCleanup = bleScanner.end();
            report.scannerCleanupComplete = wifiCleanup && bleCleanup;
            report.sourceActive = false;
            cleanupProductSurveyWorkerHardware(&report);
            sendProductSurveyWorkerEvent(
                ProductSurveyWorkerEventKind::Cancelled, report);
            continue;
        }
        sendProductSurveyWorkerEvent(
            ProductSurveyWorkerEventKind::Prepared, report);
        BoardWifiPassiveScanResult wifiAggregate;
        BoardBlePassiveScanResult bleAggregate;
        std::uint32_t scanCycles = 0;
        std::uint32_t wifiScanCycles = 0;
        std::uint32_t bleScanCycles = 0;
        bool scanFailed = false;
        bool pendingScanWindow = false;
        RadioKind pendingScanSource = RadioKind::Wifi;
        std::uint64_t pendingScanStartedUs = 0;
        std::uint64_t pendingScanEndedUs = 0;
        std::uint16_t pendingScanDropped = 0;
        while (!productSurveyStopRequested()) {
            const std::array<RadioKind, 2> schedule{
                RadioKind::Wifi, RadioKind::Ble};
            for (const RadioKind source : schedule) {
                const std::uint8_t mask =
                    leshy1::services::survey::sourceMask(source);
                if ((report.activeSourceMask & mask) == 0) continue;
                if (productSurveyStopRequested()) break;
                std::uint64_t scanStartedUs =
                    static_cast<std::uint64_t>(esp_timer_get_time());
                if (scanStartedUs == 0) scanStartedUs = 1;
                const std::uint32_t sourceCycles =
                    source == RadioKind::Wifi ? wifiScanCycles : bleScanCycles;
                // Event and observation queues cannot establish ordering with
                // each other. Clear any stale acknowledgement, publish the
                // window transition, and wait until the UI task has made this
                // source Active before its driver can emit observations.
                xSemaphoreTake(productSurveyScanStartGate, 0);
                sendProductSurveyWorkerEvent(
                    ProductSurveyWorkerEventKind::ScanStarted, report, source,
                    wifiAggregate, bleAggregate, scanCycles, sourceCycles,
                    scanStartedUs, scanStartedUs);
                xSemaphoreTake(productSurveyScanStartGate, portMAX_DELAY);
                if (productSurveyStopRequested()) break;
                setProductSurveyScanActive(true);
                BoardWifiPassiveScanResult wifiScan;
                BoardBlePassiveScanResult bleScan;
                const bool runtimeUnavailableInjected =
                    consumeProductSurveyRuntimeUnavailableInjection(source);
                if (runtimeUnavailableInjected) {
                    report.runtimeSourceFailureInjected = true;
                    report.runtimeSourceFailureInjectedMask =
                        static_cast<std::uint8_t>(
                            report.runtimeSourceFailureInjectedMask | mask);
                } else if (source == RadioKind::Wifi) {
                    wifiScan = wifiScanner.scan(
                        leshy1::drivers::wifi::defaultPassivePlan(),
                        enqueueProductSurveyWorkerRecord, nullptr);
                } else {
                    bleScan = bleScanner.scan(
                        leshy1::drivers::ble::defaultPassivePlan(),
                        enqueueProductSurveyWorkerBleRecord, nullptr);
                }
                setProductSurveyScanActive(false);
                std::uint64_t scanEndedUs =
                    static_cast<std::uint64_t>(esp_timer_get_time());
                if (scanEndedUs < scanStartedUs) scanEndedUs = scanStartedUs;
                pendingScanWindow = true;
                pendingScanSource = source;
                pendingScanStartedUs = scanStartedUs;
                pendingScanEndedUs = scanEndedUs;
                pendingScanDropped = source == RadioKind::Wifi
                    ? wifiScan.dropped : bleScan.dropped;
                if (productSurveyStopRequested()) break;
                const bool valid = source == RadioKind::Wifi
                    ? wifiScan.valid() : bleScan.valid();
                if (!valid) {
                    if (source == RadioKind::Wifi) {
                        accumulateProductSurveyScan(&wifiAggregate, wifiScan);
                    } else {
                        accumulateProductSurveyBleScan(&bleAggregate, bleScan);
                    }
                    const auto degradation =
                        leshy1::services::survey::decideSourceDegradation(
                            report.activeSourceMask,
                            report.unavailableSourceMask, source,
                            productSurveyFailureClass(
                                source, wifiScan, bleScan));
                    if (!degradation.valid) {
                        report.status = "invalid_source_failure";
                        scanFailed = true;
                        break;
                    }
                    report.activeSourceMask = degradation.activeSourceMask;
                    report.unavailableSourceMask =
                        degradation.unavailableSourceMask;
                    report.status = degradation.status;
                    sendProductSurveyWorkerEvent(
                        ProductSurveyWorkerEventKind::SourceUnavailable,
                        report, source, wifiAggregate, bleAggregate,
                        scanCycles, sourceCycles, scanEndedUs,
                        scanStartedUs, scanEndedUs, pendingScanDropped,
                        degradation.windowState,
                        degradation.windowReason);
                    pendingScanWindow = false;
                    if (!degradation.continueSession) {
                        scanFailed = true;
                        break;
                    }
                    continue;
                }
                if (source == RadioKind::Wifi) {
                    ++wifiScanCycles;
                    accumulateProductSurveyScan(&wifiAggregate, wifiScan);
                } else {
                    ++bleScanCycles;
                    accumulateProductSurveyBleScan(&bleAggregate, bleScan);
                }
                const bool wifiActive =
                    (report.activeSourceMask &
                     leshy1::services::survey::sourceMask(RadioKind::Wifi)) != 0;
                const bool bleActive =
                    (report.activeSourceMask &
                     leshy1::services::survey::sourceMask(RadioKind::Ble)) != 0;
                scanCycles = wifiActive && bleActive
                    ? (wifiScanCycles < bleScanCycles
                           ? wifiScanCycles : bleScanCycles)
                    : (wifiActive ? wifiScanCycles : bleScanCycles);
                sendProductSurveyWorkerEvent(
                    ProductSurveyWorkerEventKind::Scan, report, source,
                    wifiAggregate, bleAggregate, scanCycles,
                    source == RadioKind::Wifi ? wifiScanCycles : bleScanCycles,
                    scanEndedUs, scanStartedUs, scanEndedUs,
                    pendingScanDropped);
                pendingScanWindow = false;
            }
            if (productSurveyStopRequested() || scanFailed) break;
            ulTaskNotifyTake(
                pdTRUE, pdMS_TO_TICKS(kProductSurveyScanIntervalMs));
        }

        const ProductSurveyWorkerControl terminalControl =
            productSurveyControl();
        setProductSurveyScanActive(false);
        const bool wifiCleanup = wifiScanner.end();
        const bool bleCleanup = bleScanner.end();
        report.scannerCleanupComplete = wifiCleanup && bleCleanup;
        report.sourceActive = false;
        std::uint64_t terminalUs =
            static_cast<std::uint64_t>(esp_timer_get_time());
        if (terminalUs == 0) terminalUs = 1;
        if (scanFailed ||
            terminalControl == ProductSurveyWorkerControl::CancelRequested) {
            cleanupProductSurveyWorkerHardware(&report);
        }
        if (scanFailed) {
            sendProductSurveyWorkerEvent(
                ProductSurveyWorkerEventKind::Failed,
                report, pendingScanSource, wifiAggregate, bleAggregate,
                scanCycles,
                pendingScanSource == RadioKind::Wifi
                    ? wifiScanCycles : bleScanCycles,
                terminalUs,
                pendingScanWindow ? pendingScanStartedUs : 0,
                pendingScanWindow ? pendingScanEndedUs : 0,
                pendingScanWindow ? pendingScanDropped : 0);
        } else if (terminalControl ==
                   ProductSurveyWorkerControl::PauseRequested) {
            report.status = "paused";
            sendProductSurveyWorkerEvent(
                ProductSurveyWorkerEventKind::Paused,
                report, pendingScanSource, wifiAggregate, bleAggregate,
                scanCycles,
                pendingScanSource == RadioKind::Wifi
                    ? wifiScanCycles : bleScanCycles,
                terminalUs,
                pendingScanWindow ? pendingScanStartedUs : 0,
                pendingScanWindow ? pendingScanEndedUs : 0,
                pendingScanWindow ? pendingScanDropped : 0);
        } else if (terminalControl ==
                   ProductSurveyWorkerControl::StopRequested) {
            report.status = "stopped";
            sendProductSurveyWorkerEvent(
                ProductSurveyWorkerEventKind::Stopped,
                report, pendingScanSource, wifiAggregate, bleAggregate,
                scanCycles,
                pendingScanSource == RadioKind::Wifi
                    ? wifiScanCycles : bleScanCycles,
                terminalUs,
                pendingScanWindow ? pendingScanStartedUs : 0,
                pendingScanWindow ? pendingScanEndedUs : 0,
                pendingScanWindow ? pendingScanDropped : 0);
        } else {
            report.status = "cancelled";
            sendProductSurveyWorkerEvent(
                ProductSurveyWorkerEventKind::Cancelled,
                report, pendingScanSource, wifiAggregate, bleAggregate,
                scanCycles,
                pendingScanSource == RadioKind::Wifi
                    ? wifiScanCycles : bleScanCycles,
                terminalUs,
                pendingScanWindow ? pendingScanStartedUs : 0,
                pendingScanWindow ? pendingScanEndedUs : 0,
                pendingScanWindow ? pendingScanDropped : 0);
        }
    }
}

bool initializeProductSurveyWorker() {
    productSurveyScanStartGate = xSemaphoreCreateBinaryStatic(
        &productSurveyScanStartGateStorage);
    productSurveyWorkerEvents = xQueueCreate(
        kProductSurveyWorkerEventCapacity,
        sizeof(ProductSurveyWorkerEvent));
    productSurveyObservations = xQueueCreate(
        kProductSurveyObservationCapacity, sizeof(Observation));
    if (productSurveyScanStartGate == nullptr ||
        productSurveyWorkerEvents == nullptr ||
        productSurveyObservations == nullptr) {
        if (productSurveyWorkerEvents != nullptr) {
            vQueueDelete(productSurveyWorkerEvents);
            productSurveyWorkerEvents = nullptr;
        }
        if (productSurveyObservations != nullptr) {
            vQueueDelete(productSurveyObservations);
            productSurveyObservations = nullptr;
        }
        return false;
    }
    const bool started = xTaskCreatePinnedToCore(
        runProductSurveyWorker, "leshy-survey", 8192, nullptr, 1,
        &productSurveyWorkerTaskHandle, 0) == pdPASS;
    if (!started) {
        vQueueDelete(productSurveyWorkerEvents);
        vQueueDelete(productSurveyObservations);
        productSurveyWorkerEvents = nullptr;
        productSurveyObservations = nullptr;
        productSurveyScanStartGate = nullptr;
    }
    return started;
}

bool failProductSurveyStart(const char* status) {
    if (surveyWorkflow.state() == SurveyWorkflowState::Running) {
        surveyPipeline.cancel();
    }
    closeProductSurveyBackend();
    productSurveyRuntime.status = productSurveyRuntime.cleanupComplete
                                      ? status
                                      : "cleanup_failed";
    lastRuntimeEvent = productSurveyRuntime.status;
    return false;
}

bool startProductSurvey() {
    const std::uint64_t actionStartedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    if (!productSurveyWorkerReady ||
        productSurveyControl() != ProductSurveyWorkerControl::Idle ||
        productSurveyWorkerTaskHandle == nullptr) {
        productSurveyRuntime.status = "worker_unavailable";
        lastRuntimeEvent = productSurveyRuntime.status;
        return false;
    }
    productSurveyRuntime = {};
    productSurveyTimeline.reset();
    productSurveyRuntime.status = "preparing";
    productSurveyRuntime.selected = true;
    productSurveyRuntime.selectedSourceMask =
        surveySourceController.selectedMask();
    productSurveyRuntime.timelineStatus = "preparing";
    if (productSurveyRuntime.selectedSourceMask == 0) {
        productSurveyRuntime.status = "source_plan_empty";
        productSurveyRuntime.timelineStatus = "invalid_mask";
        lastRuntimeEvent = productSurveyRuntime.status;
        return false;
    }
    productSurveyRuntime.cleanupComplete = false;
    productSurveyRuntime.workerReady = true;
    portENTER_CRITICAL(&productSurveyWorkerMux);
    productSurveyWorkerOwnedResources = appRuntime.activeResources();
    productSurveyWorkerScanActive = false;
    productSurveyWorkerControl = ProductSurveyWorkerControl::Starting;
    portEXIT_CRITICAL(&productSurveyWorkerMux);
    xTaskNotifyGive(productSurveyWorkerTaskHandle);
    productSurveyRuntime.startActionUs =
        static_cast<std::uint64_t>(esp_timer_get_time()) - actionStartedUs;
    lastRuntimeEvent = "product_survey_preparing";
    return true;
}

bool reopenProductSurveyBackendForCommit() {
    const auto required =
        leshy1::kernel::runtime::resourceMask(Resource::UiForeground) |
        leshy1::kernel::runtime::resourceMask(Resource::EspRf) |
        leshy1::kernel::runtime::resourceMask(Resource::Storage) |
        leshy1::kernel::runtime::resourceMask(Resource::RadioSpi);
    const auto ownedResources = appRuntime.activeResources();
    char enrolledFingerprint[33] = {};
    if ((ownedResources & required) != required ||
        !exactCidFingerprint(productSurveyRuntime.expectedFingerprint) ||
        !loadProductFingerprint(enrolledFingerprint,
                                sizeof(enrolledFingerprint)) ||
        std::strcmp(enrolledFingerprint,
                    productSurveyRuntime.expectedFingerprint) != 0) {
        return false;
    }

    leshy1::storage::SdTransportRunResult identity;
    for (std::uint8_t attempt = 1;
         attempt <= leshy1::storage::kProductStartMaximumIdentityAttempts;
         ++attempt) {
        BoardSdSpiTransport identityTransport;
        const bool identityBegun = identityTransport.begin();
        identity = {};
        if (identityBegun) {
            leshy1::storage::SdTransportRunPolicy policy;
            policy.allowPhysical = true;
            policy.explicitlySelected = true;
            policy.identificationOnly = true;
            policy.ownedResources = ownedResources;
            identity = leshy1::storage::runSdIdentificationStateMachine(
                leshy1::storage::defaultSdIdentificationPlan(),
                identityTransport, policy);
            identityTransport.end();
        }
        productSurveyRuntime.identityAttempts = attempt;
        productSurveyRuntime.identityTransientRetries =
            static_cast<std::uint8_t>(attempt - 1U);
        productSurveyRuntime.identityStatus = identity.status;
        productSurveyRuntime.identityCleanupComplete =
            identityTransport.cleanupComplete();
        formatCidFingerprint(identity.identity,
                             productSurveyRuntime.observedFingerprint,
                             sizeof(productSurveyRuntime.observedFingerprint));
        if (productSurveyRuntime.identityCleanupComplete &&
            identity.status ==
                leshy1::storage::SdTransportRunStatus::Valid) {
            break;
        }
        const leshy1::storage::ProductStartIdentityRetryEvidence retryEvidence{
            true,
            true,
            true,
            (ownedResources & required) == required,
            identityTransport.physicalSpiStarted(),
            identity.status,
            std::strcmp(productSurveyRuntime.observedFingerprint,
                        "00000000000000000000000000000000") == 0,
            productSurveyRuntime.identityCleanupComplete,
            false,
        };
        if (!leshy1::storage::shouldRetryProductStartIdentity(
                retryEvidence, attempt)) {
            break;
        }
        vTaskDelay(pdMS_TO_TICKS(
            leshy1::storage::productStartIdentityRetryDelayMs(attempt)));
    }
    if (!productSurveyRuntime.identityCleanupComplete ||
        identity.status != leshy1::storage::SdTransportRunStatus::Valid ||
        std::strcmp(productSurveyRuntime.expectedFingerprint,
                    productSurveyRuntime.observedFingerprint) != 0) {
        return false;
    }

    productSurveyRuntime.filesystemAttempted = true;
    if (!productSurveyFilesystem.begin()) return false;
    productSurveyRuntime.cardCapacityBytes =
        productSurveyFilesystem.cardCapacityBytes();
    productSurveyRuntime.cachedFreeBytes =
        productSurveyFilesystem.cachedFreeBytes();
    const bool capacityMatched =
        productSurveyRuntime.cardCapacityBytes != 0 &&
        productSurveyRuntime.cardCapacityBytes == identity.identity.capacityBytes;
    const bool rootExists = productSurveyFilesystem.exists(
        leshy1::storage::kProductSessionStoreRoot);

    leshy1::storage::MediaIdentity media;
    media.present = capacityMatched;
    media.kind = leshy1::storage::MediaKind::Sd;
    media.fingerprint = productSurveyRuntime.observedFingerprint;
    media.capacityBytes = productSurveyRuntime.cardCapacityBytes;
    media.freeBytes = productSurveyRuntime.cachedFreeBytes;
    leshy1::storage::ProductStoreRequest storeRequest;
    storeRequest.operation =
        leshy1::storage::ProductStoreOperation::CommitSession;
    storeRequest.explicitlySelected = true;
    storeRequest.expectedFingerprint =
        productSurveyRuntime.expectedFingerprint;
    storeRequest.rootPath = leshy1::storage::kProductSessionStoreRoot;
    storeRequest.rootExists = rootExists;
    storeRequest.driverWriteEnabled = true;
    storeRequest.requiredBytes = kProductSurveyCommitBytes;
    storeRequest.reserveBytes = kProductSurveyReserveBytes;
    storeRequest.ownedResources = ownedResources;
    const leshy1::storage::ProductStorePermit storePermit =
        leshy1::storage::authorizeProductStore(media, storeRequest);
    productSurveyRuntime.storeStatus = storePermit.status;
    if (!storePermit.allowed() ||
        !productSurveyStore.selectDrive(productSurveyFilesystem.driveNumber()) ||
        !productSurveyStore.openExistingWritable(storePermit)) {
        return false;
    }
    surveyStoreRouter.bind(productSurveyStore);
    productSurveyRuntime.backendOpen = true;
    productSurveyRuntime.cleanupComplete = false;
    return true;
}

SurveyPipelineStatus stopProductSurvey() {
    if (!reopenProductSurveyBackendForCommit()) {
        const bool cleanup = closeProductSurveyBackend();
        productSurveyRuntime.status = cleanup
            ? "commit_backend_failed" : "cleanup_failed";
        lastRuntimeEvent = productSurveyRuntime.status;
        return SurveyPipelineStatus::WorkflowRejected;
    }
    const SurveyPipelineStatus status = surveyPipeline.stopAndCommit(
        static_cast<std::uint64_t>(esp_timer_get_time()));
    const bool cleanup = closeProductSurveyBackend();
    productSurveyRuntime.status =
        status == SurveyPipelineStatus::Committed
            ? (cleanup ? "committed" : "cleanup_failed")
            : (cleanup ? "commit_failed" : "cleanup_failed");
    lastRuntimeEvent = productSurveyRuntime.status;
    return status;
}

void releaseProductSurveyAfterTerminal(const char* status, bool returnHome);

bool requestProductSurveyWorkerStop(bool cancel) {
    const std::uint64_t actionStartedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    const ProductSurveyWorkerControl control = productSurveyControl();
    if (control != ProductSurveyWorkerControl::Starting &&
        control != ProductSurveyWorkerControl::Running) {
        return false;
    }
    const bool scanWasActive = productSurveyScanActive();
    setProductSurveyControl(
        cancel ? ProductSurveyWorkerControl::CancelRequested
               : ProductSurveyWorkerControl::StopRequested);
    if (cancel) {
        productSurveyRuntime.cancelRequestedDuringScan = scanWasActive;
    }
    productSurveyRuntime.status = cancel ? "cancelling" : "stopping";
    productSurveyRuntime.stopActionUs =
        static_cast<std::uint64_t>(esp_timer_get_time()) - actionStartedUs;
    lastRuntimeEvent = cancel ? "product_survey_cancelling"
                              : "product_survey_stopping";
    BoardWifiPassiveScanner::cancelActiveScan();
    BoardBlePassiveScanner::cancelActiveScan();
    if (productSurveyWorkerTaskHandle != nullptr) {
        xTaskNotifyGive(productSurveyWorkerTaskHandle);
    }
    return true;
}

bool requestProductSurveyWorkerPause() {
    const std::uint64_t actionStartedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    if (productSurveyControl() != ProductSurveyWorkerControl::Running) {
        return false;
    }
    setProductSurveyControl(ProductSurveyWorkerControl::PauseRequested);
    productSurveyRuntime.status = "pausing";
    productSurveyRuntime.stopActionUs =
        static_cast<std::uint64_t>(esp_timer_get_time()) - actionStartedUs;
    lastRuntimeEvent = "product_survey_pausing";
    BoardWifiPassiveScanner::cancelActiveScan();
    BoardBlePassiveScanner::cancelActiveScan();
    if (productSurveyWorkerTaskHandle != nullptr) {
        xTaskNotifyGive(productSurveyWorkerTaskHandle);
    }
    return true;
}

bool commitPausedProductSurvey() {
    if (productSurveyControl() != ProductSurveyWorkerControl::Paused) {
        return false;
    }
    const SurveyPipelineStatus committed = stopProductSurvey();
    if (committed == SurveyPipelineStatus::Committed) {
        constexpr ProductSurveyWorkerControl terminalControl =
            ProductSurveyWorkerControl::Idle;
        setProductSurveyControl(terminalControl);
        return true;
    }
    releaseProductSurveyAfterTerminal("commit_failed", true);
    return false;
}

bool applyProductSurveyTimelineStatus(
    SourceTimelineStatus status, SourceTimelineStatus expected,
    const char* stage = "unspecified", std::uint64_t eventUs = 0) {
    productSurveyRuntime.timelineStatus =
        leshy1::services::survey::sourceTimelineStatusName(status);
    if (status != expected) {
        if (std::strcmp(productSurveyRuntime.timelineFailureStatus, "none") == 0) {
            productSurveyRuntime.timelineFailureStatus =
                productSurveyRuntime.timelineStatus;
            productSurveyRuntime.timelineFailureStage = stage;
            productSurveyRuntime.timelineFailureEventUs = eventUs;
            productSurveyRuntime.timelineFailureLatestUs =
                productSurveyTimeline.latestUs();
        }
        productSurveyRuntime.timelineHealthy = false;
    }
    return status == expected;
}

bool drainProductSurveyTimelineWindows() {
    leshy1::services::survey::SourceWindow window;
    while (true) {
        const SourceTimelineStatus dequeued = productSurveyTimeline.pop(&window);
        if (dequeued == SourceTimelineStatus::Empty) return true;
        if (dequeued != SourceTimelineStatus::WindowDequeued) {
            productSurveyRuntime.timelineArchiveStatus =
                leshy1::services::survey::sourceTimelineStatusName(dequeued);
            if (std::strcmp(productSurveyRuntime.timelineFailureStatus,
                            "none") == 0) {
                productSurveyRuntime.timelineFailureStatus =
                    productSurveyRuntime.timelineArchiveStatus;
                productSurveyRuntime.timelineFailureStage = "archive_pop";
                productSurveyRuntime.timelineFailureLatestUs =
                    productSurveyTimeline.latestUs();
            }
            productSurveyRuntime.timelineHealthy = false;
            return false;
        }
        const auto archived = surveySession.appendTimelineWindow(window);
        productSurveyRuntime.timelineArchiveStatus =
            leshy1::services::survey::sessionTimelineStatusName(archived);
        if (archived !=
            leshy1::services::survey::SessionTimelineStatus::Appended) {
            if (std::strcmp(productSurveyRuntime.timelineFailureStatus,
                            "none") == 0) {
                productSurveyRuntime.timelineFailureStatus =
                    productSurveyRuntime.timelineArchiveStatus;
                productSurveyRuntime.timelineFailureStage = "archive_append";
                productSurveyRuntime.timelineFailureEventUs = window.endedUs;
                productSurveyRuntime.timelineFailureLatestUs =
                    productSurveyTimeline.latestUs();
            }
            productSurveyRuntime.timelineHealthy = false;
            return false;
        }
        ++productSurveyRuntime.timelineArchivedWindows;
        window = {};
    }
}

bool recordProductSurveyTimelineDrops(RadioKind source, std::uint16_t count,
                                      std::uint64_t monotonicUs) {
    for (std::uint16_t index = 0; index < count; ++index) {
        const SourceTimelineStatus status =
            productSurveyTimeline.recordObservation(
                source, false, monotonicUs);
        if (!applyProductSurveyTimelineStatus(
                status, SourceTimelineStatus::ObservationRecorded,
                "driver_drop", monotonicUs)) {
            return false;
        }
    }
    return true;
}

bool drainProductSurveyWorkerObservations() {
    if (productSurveyObservations == nullptr ||
        surveyWorkflow.state() != SurveyWorkflowState::Running) {
        return false;
    }
    bool changed = false;
    Observation observation;
    while (xQueueReceive(productSurveyObservations, &observation, 0) == pdTRUE) {
        const Observation* selectedWifi = wifiNetworkAt(wifiNetworkSelection);
        const Observation wifiSelectionAnchor = selectedWifi == nullptr
            ? Observation{} : *selectedWifi;
        const bool wifiSelectionAnchored = selectedWifi != nullptr;
        const bool wifiCatalogChanged =
            (wifiProductView == WifiProductView::Networks ||
             wifiProductView == WifiProductView::NetworkDetail) &&
            wifiNetworkCatalog.upsert(
                observation, !wifiNetworkNavigationOrder.locked());
        if (wifiCatalogChanged && wifiSelectionAnchored &&
            !wifiNetworkNavigationOrder.locked()) {
            const std::size_t anchored =
                wifiNetworkCatalog.indexOfIdentity(wifiSelectionAnchor);
            wifiNetworkSelection = anchored < wifiNetworkCatalog.size()
                ? anchored : wifiNetworkCatalog.size() - 1U;
        }
        const Observation* selectedBle =
            bleDeviceCatalog.at(bleDeviceSelection);
        const Observation bleSelectionAnchor = selectedBle == nullptr
            ? Observation{} : *selectedBle;
        const bool bleSelectionAnchored = selectedBle != nullptr;
        const bool bleCatalogChanged =
            (bleProductView == BleProductView::Devices ||
             bleProductView == BleProductView::DeviceDetail) &&
            bleDeviceCatalog.upsert(observation);
        if (bleCatalogChanged && bleSelectionAnchored) {
            const std::size_t anchored =
                bleDeviceCatalog.indexOfIdentity(bleSelectionAnchor);
            bleDeviceSelection = anchored < bleDeviceCatalog.size()
                ? anchored : bleDeviceCatalog.size() - 1U;
        }
        const SurveyPipelineStatus queued = surveyPipeline.enqueue(observation);
        const bool accepted = queued == SurveyPipelineStatus::Queued;
        const SourceTimelineStatus timelineStatus =
            productSurveyTimeline.recordObservation(
                observation.radio, accepted, observation.monotonicUs);
        if (!applyProductSurveyTimelineStatus(
                timelineStatus, SourceTimelineStatus::ObservationRecorded,
                "observation", observation.monotonicUs)) {
            productSurveyRuntime.status = "timeline_record_failed";
            lastRuntimeEvent = productSurveyRuntime.status;
        }
        changed = queued == SurveyPipelineStatus::Queued ||
                  wifiCatalogChanged || bleCatalogChanged || changed;
        observation = {};
    }
    if (changed) {
        changed = surveyPipeline.drain(
            leshy1::services::survey::ObservationQueue::kCapacity) ==
            SurveyPipelineStatus::Drained;
    }
    return changed;
}

bool closeProductSurveyScanWindow(
    const ProductSurveyWorkerEvent& event,
    SourceWindowState nextState = SourceWindowState::Scheduled,
    SourceWindowReason nextReason = SourceWindowReason::DutyCycle) {
    if (event.scanStartedUs == 0 || event.scanEndedUs < event.scanStartedUs) {
        return true;
    }
    drainProductSurveyWorkerObservations();
    if (!productSurveyRuntime.timelineHealthy) return false;
    if (!recordProductSurveyTimelineDrops(event.source, event.scanDropped,
                                          event.scanEndedUs)) {
        return false;
    }
    const SourceTimelineStatus status = productSurveyTimeline.transition(
        event.source, nextState, nextReason, event.scanEndedUs);
    return applyProductSurveyTimelineStatus(
               status, SourceTimelineStatus::Transitioned,
               nextState == SourceWindowState::Fault
                   ? "scan_fault_close"
                   : nextState == SourceWindowState::Unavailable
                         ? "scan_unavailable_close" : "scan_close",
               event.scanEndedUs) &&
           drainProductSurveyTimelineWindows();
}

int hexNibble(char value) {
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'a' && value <= 'f') return value - 'a' + 10;
    if (value >= 'A' && value <= 'F') return value - 'A' + 10;
    return -1;
}

CaptureMetadata productCaptureMetadata(std::uint8_t selectedSourceMask) {
    CaptureMetadata metadata;
    metadata.present = true;
    metadata.passive = true;
    metadata.selectedSourceMask = selectedSourceMask;
    const auto wifiPlan = leshy1::drivers::wifi::defaultPassivePlan();
    if ((selectedSourceMask & leshy1::services::survey::sourceMask(
            RadioKind::Wifi)) != 0) {
        metadata.wifiShowHidden = wifiPlan.showHidden;
        metadata.wifiMaxMsPerChannel = wifiPlan.maxMsPerChannel;
        metadata.wifiChannel = wifiPlan.channel;
    }
    const auto blePlan = leshy1::drivers::ble::defaultPassivePlan();
    if ((selectedSourceMask & leshy1::services::survey::sourceMask(
            RadioKind::Ble)) != 0) {
        metadata.bleDurationMs = blePlan.durationMs;
        metadata.bleIntervalMs = blePlan.intervalMs;
        metadata.bleWindowMs = blePlan.windowMs;
        metadata.bleMaximumRecords = blePlan.maximumRecords;
    }
    if (std::strlen(runningAppElfSha256) ==
        metadata.appIdentity.size() * 2U) {
        bool valid = true;
        for (std::size_t index = 0; index < metadata.appIdentity.size(); ++index) {
            const int high = hexNibble(runningAppElfSha256[index * 2U]);
            const int low = hexNibble(runningAppElfSha256[index * 2U + 1U]);
            if (high < 0 || low < 0) {
                valid = false;
                break;
            }
            metadata.appIdentity[index] = static_cast<std::uint8_t>(
                (static_cast<unsigned>(high) << 4U) |
                static_cast<unsigned>(low));
        }
        if (valid) {
            metadata.appIdentityLength = metadata.appIdentity.size();
        }
    }
    return metadata;
}

CaptureMetadata productWifiFrameCaptureMetadata() {
    CaptureMetadata metadata = productCaptureMetadata(
        leshy1::services::survey::sourceMask(RadioKind::Wifi));
    const auto& plan = wifiFrameCapture.capture().plan();
    const auto& stats = wifiFrameCapture.stats();
    metadata.wifiShowHidden = false;
    metadata.wifiMaxMsPerChannel = plan.channelDwellMs;
    metadata.wifiChannel = plan.channel;
    metadata.framePayloadCaptured = true;
    metadata.framePayloadBytes = stats.payloadBytes;
    metadata.framePayloadRecords = static_cast<std::uint16_t>(
        wifiFrameCapture.capture().size());
    metadata.framePayloadSnapLength = plan.snapLength;
    metadata.framePayloadFormat = FramePayloadFormat::Ieee80211;
    return metadata;
}

CaptureMetadata productSubGhzRawCaptureMetadata() {
    CaptureMetadata metadata = productCaptureMetadata(0);
    const auto& plan = subGhzRawCapture.plan();
    const auto& stats = subGhzRawCapture.stats();
    metadata.selectedSourceMask = 0;
    metadata.subGhzRawCaptured = true;
    metadata.subGhzFrequencyKHz = plan.frequencyKHz;
    metadata.subGhzThresholdDbm = plan.thresholdDbm;
    metadata.subGhzModulation = plan.modulation;
    metadata.subGhzStartLevel = stats.startLevel;
    metadata.subGhzTruncated = stats.truncated;
    metadata.subGhzPulseRecords = static_cast<std::uint16_t>(
        subGhzRawCapture.pulseCount());
    metadata.subGhzPulseBytes = static_cast<std::uint32_t>(
        subGhzRawCapture.pulseCount() * 2U);
    return metadata;
}

CaptureMetadata productInfraredRawCaptureMetadata() {
    CaptureMetadata metadata = productCaptureMetadata(0);
    const auto& stats = infraredCapture.stats();
    metadata.selectedSourceMask = 0;
    metadata.infraredRawCaptured = true;
    metadata.infraredStartLevel = stats.startLevel;
    metadata.infraredTruncated = stats.truncated;
    metadata.infraredPulseRecords = static_cast<std::uint16_t>(
        infraredCapture.pulseCount());
    metadata.infraredPulseBytes = static_cast<std::uint32_t>(
        infraredCapture.pulseCount() * 2U);
    metadata.infraredDecode = infraredCapture.decode();
    return metadata;
}

void runCaptureStoreWorker(void*) {
    CaptureStoreEvent event;
    event.status = "store_failed";
    bool identityCleanupComplete = true;
    bool filesystemAttempted = false;
    leshy1::storage::SdTransportRunResult identity;
    char expectedFingerprint[33] = {};
    char observedFingerprint[33] = {};
    do {
        const auto required =
            leshy1::kernel::runtime::resourceMask(Resource::UiForeground) |
            leshy1::kernel::runtime::resourceMask(Resource::Storage) |
            leshy1::kernel::runtime::resourceMask(Resource::RadioSpi);
        const auto owned = resourceBroker.ownedBy(AppRuntime::kForegroundOwner);
        if ((owned & required) != required) {
            event.status = "resources_missing";
            break;
        }
        if (!loadProductFingerprint(expectedFingerprint,
                                    sizeof(expectedFingerprint))) {
            event.status = "enrollment_missing";
            break;
        }
        for (std::uint8_t attempt = 1;
             attempt <= leshy1::storage::kProductStartMaximumIdentityAttempts;
             ++attempt) {
            BoardSdSpiTransport transport;
            const bool begun = transport.begin();
            identity = {};
            if (begun) {
                leshy1::storage::SdTransportRunPolicy policy;
                policy.allowPhysical = true;
                policy.explicitlySelected = true;
                policy.identificationOnly = true;
                policy.ownedResources = owned;
                identity = leshy1::storage::runSdIdentificationStateMachine(
                    leshy1::storage::defaultSdIdentificationPlan(), transport,
                    policy);
                transport.end();
            }
            identityCleanupComplete = transport.cleanupComplete();
            formatCidFingerprint(identity.identity, observedFingerprint,
                                 sizeof(observedFingerprint));
            if (identityCleanupComplete &&
                identity.status ==
                    leshy1::storage::SdTransportRunStatus::Valid) {
                break;
            }
            const leshy1::storage::ProductStartIdentityRetryEvidence evidence{
                true, true, exactCidFingerprint(expectedFingerprint),
                (owned & required) == required,
                transport.physicalSpiStarted(), identity.status,
                std::strcmp(observedFingerprint,
                            "00000000000000000000000000000000") == 0,
                identityCleanupComplete, filesystemAttempted,
            };
            if (!leshy1::storage::shouldRetryProductStartIdentity(
                    evidence, attempt)) {
                break;
            }
            vTaskDelay(pdMS_TO_TICKS(
                leshy1::storage::productStartIdentityRetryDelayMs(attempt)));
        }
        if (!identityCleanupComplete ||
            identity.status != leshy1::storage::SdTransportRunStatus::Valid) {
            event.status = "identity_failed";
            break;
        }
        if (std::strcmp(expectedFingerprint, observedFingerprint) != 0) {
            event.status = "fingerprint_mismatch";
            break;
        }
        filesystemAttempted = true;
        if (!productSurveyFilesystem.begin()) {
            event.status = "mount_failed";
            break;
        }
        const std::uint64_t cardCapacity =
            productSurveyFilesystem.cardCapacityBytes();
        const std::uint64_t cachedFree =
            productSurveyFilesystem.cachedFreeBytes();
        const bool rootExists = productSurveyFilesystem.exists(
            leshy1::storage::kProductSessionStoreRoot);
        leshy1::storage::MediaIdentity media;
        media.present = cardCapacity != 0 &&
            cardCapacity == identity.identity.capacityBytes;
        media.kind = leshy1::storage::MediaKind::Sd;
        media.fingerprint = observedFingerprint;
        media.capacityBytes = cardCapacity;
        media.freeBytes = cachedFree;
        leshy1::storage::ProductStoreRequest request;
        request.operation =
            leshy1::storage::ProductStoreOperation::CommitSession;
        request.explicitlySelected = true;
        request.expectedFingerprint = expectedFingerprint;
        request.rootPath = leshy1::storage::kProductSessionStoreRoot;
        request.rootExists = rootExists;
        request.driverWriteEnabled = true;
        request.requiredBytes = kProductSurveyCommitBytes;
        request.reserveBytes = kProductSurveyReserveBytes;
        request.ownedResources = owned;
        const leshy1::storage::ProductStorePermit permit =
            leshy1::storage::authorizeProductStore(media, request);
        if (!permit.allowed()) {
            event.status =
                leshy1::storage::productStoreAccessStatusName(permit.status);
            break;
        }
        if (!productSurveyStore.selectDrive(
                productSurveyFilesystem.driveNumber()) ||
            !productSurveyStore.openExistingWritable(permit)) {
            event.status = "store_open_failed";
            break;
        }

        const auto& stats = wifiFrameCapture.stats();
        char sessionId[SurveySession::kSessionIdCapacity + 1] = {};
        std::snprintf(sessionId, sizeof(sessionId), "wifi-cap-%08llx",
                      static_cast<unsigned long long>(
                          stats.startedUs & 0xFFFFFFFFULL));
        surveySession.reset();
        if (stats.state != WifiFrameCaptureState::Complete ||
            wifiFrameCapture.capture().size() == 0 ||
            surveySession.start(sessionId, stats.startedUs) !=
                SessionStatus::Started ||
            surveySession.configureCaptureMetadata(
                productWifiFrameCaptureMetadata()) !=
                CaptureMetadataStatus::Configured ||
            surveySession.stop(stats.endedUs) != SessionStatus::Stopped) {
            event.status = "artifact_invalid";
            break;
        }
        const leshy1::storage::SessionStoreCommitResult commit =
            leshy1::storage::commitNextWifiFrameCapture(
                productSurveyStore, sessionStoreWorkspace, surveySession,
                wifiFrameCapture.capture());
        event.storeStatus = commit.status;
        if (!commit.complete()) {
            event.status = leshy1::storage::sessionStoreStatusName(commit.status);
            break;
        }
        const leshy1::storage::SessionStoreRecoveryResult recovered =
            leshy1::storage::recoverSession(
                productSurveyStore, sessionStoreWorkspace,
                &sessionStoreWorkspace.validationSession);
        if (!recovered.valid() || recovered.generation != commit.generation) {
            event.status = "reopen_failed";
            event.storeStatus = recovered.status;
            break;
        }
        event.valid = true;
        event.generation = recovered.generation;
        event.status = "saved";
    } while (false);

    productSurveyStore.end();
    if (productSurveyFilesystem.mounted()) productSurveyFilesystem.end();
    const bool filesystemCleanup = !filesystemAttempted ||
        productSurveyFilesystem.cleanupComplete();
    event.cleanupComplete = identityCleanupComplete && filesystemCleanup &&
        !productSurveyFilesystem.mounted();
    if (!event.cleanupComplete) {
        event.valid = false;
        event.status = "cleanup_failed";
    }
    if (captureStoreEvents != nullptr) {
        xQueueSend(captureStoreEvents, &event, portMAX_DELAY);
    }
    vTaskDelete(nullptr);
}

bool requestWifiFrameCapturePersist() {
    if (capturePersistState != CapturePersistState::Confirm ||
        wifiFrameCapture.stats().state != WifiFrameCaptureState::Complete ||
        wifiFrameCapture.capture().size() == 0) {
        return false;
    }
    if (captureStoreEvents == nullptr || captureStoreTaskHandle != nullptr) {
        capturePersistState = CapturePersistState::Failed;
        capturePersistStatus = "worker_unavailable";
        lastRuntimeEvent = "capture_store_worker_unavailable";
        return true;
    }
    const auto storageResources =
        leshy1::kernel::runtime::resourceMask(Resource::Storage) |
        leshy1::kernel::runtime::resourceMask(Resource::RadioSpi);
    if (!resourceBroker.acquire(AppRuntime::kForegroundOwner,
                                storageResources)) {
        capturePersistState = CapturePersistState::Failed;
        capturePersistStatus = "resources_busy";
        lastRuntimeEvent = "capture_store_resources_busy";
        return true;
    }
    capturePersistState = CapturePersistState::Saving;
    capturePersistStatus = "saving";
    const bool started = xTaskCreatePinnedToCore(
        runCaptureStoreWorker, "leshy-cap-store", 8192, nullptr, 1,
        &captureStoreTaskHandle, 0) == pdPASS;
    if (!started) {
        resourceBroker.release(AppRuntime::kForegroundOwner, storageResources);
        captureStoreTaskHandle = nullptr;
        capturePersistState = CapturePersistState::Failed;
        capturePersistStatus = "worker_unavailable";
        lastRuntimeEvent = "capture_store_worker_unavailable";
    } else {
        lastRuntimeEvent = "capture_store_saving";
    }
    return true;
}

void serviceWifiFrameCapturePersist() {
    if (captureStoreEvents == nullptr) return;
    CaptureStoreEvent event;
    if (xQueueReceive(captureStoreEvents, &event, 0) != pdTRUE) return;
    captureStoreTaskHandle = nullptr;
    const auto storageResources =
        leshy1::kernel::runtime::resourceMask(Resource::Storage) |
        leshy1::kernel::runtime::resourceMask(Resource::RadioSpi);
    if (!(uiController.page() == 2 &&
          wifiProductView == WifiProductView::Capture)) {
        resourceBroker.release(AppRuntime::kForegroundOwner,
                               storageResources);
    }
    const bool admitted = event.valid && event.cleanupComplete &&
        libraryController.replaceWithOwnedCopy(
            sessionStoreWorkspace.validationSession, librarySession,
            event.generation, SessionIntegrity::Valid, true, false);
    capturePersistState = admitted ? CapturePersistState::Saved
                                   : CapturePersistState::Failed;
    capturePersistStatus = admitted ? "saved" : event.status;
    capturePersistGeneration = admitted ? event.generation : 0;
    lastRuntimeEvent = admitted ? "capture_store_saved"
                                : "capture_store_failed";
    if (uiController.page() == 4 ||
        (uiController.page() == 2 &&
         wifiProductView == WifiProductView::Capture)) {
        renderInteractiveScreen();
    }
}

void runPulseCaptureStoreWorker(bool infrared, QueueHandle_t events) {
    CaptureStoreEvent event;
    event.status = "store_failed";
    bool identityCleanupComplete = true;
    bool filesystemAttempted = false;
    leshy1::storage::SdTransportRunResult identity;
    char expectedFingerprint[33] = {};
    char observedFingerprint[33] = {};
    do {
        const auto required =
            leshy1::kernel::runtime::resourceMask(Resource::UiForeground) |
            leshy1::kernel::runtime::resourceMask(Resource::Storage) |
            leshy1::kernel::runtime::resourceMask(Resource::RadioSpi);
        const auto owned = resourceBroker.ownedBy(
            AppRuntime::kForegroundOwner);
        if ((owned & required) != required) {
            event.status = "resources_missing";
            break;
        }
        if (!loadProductFingerprint(expectedFingerprint,
                                    sizeof(expectedFingerprint))) {
            event.status = "enrollment_missing";
            break;
        }
        for (std::uint8_t attempt = 1;
             attempt <= leshy1::storage::kProductStartMaximumIdentityAttempts;
             ++attempt) {
            BoardSdSpiTransport transport;
            const bool begun = transport.begin();
            identity = {};
            if (begun) {
                leshy1::storage::SdTransportRunPolicy policy;
                policy.allowPhysical = true;
                policy.explicitlySelected = true;
                policy.identificationOnly = true;
                policy.ownedResources = owned;
                identity = leshy1::storage::runSdIdentificationStateMachine(
                    leshy1::storage::defaultSdIdentificationPlan(), transport,
                    policy);
                transport.end();
            }
            identityCleanupComplete = transport.cleanupComplete();
            formatCidFingerprint(identity.identity, observedFingerprint,
                                 sizeof(observedFingerprint));
            if (identityCleanupComplete &&
                identity.status ==
                    leshy1::storage::SdTransportRunStatus::Valid) {
                break;
            }
            const leshy1::storage::ProductStartIdentityRetryEvidence evidence{
                true, true, exactCidFingerprint(expectedFingerprint),
                (owned & required) == required,
                transport.physicalSpiStarted(), identity.status,
                std::strcmp(observedFingerprint,
                            "00000000000000000000000000000000") == 0,
                identityCleanupComplete, filesystemAttempted,
            };
            if (!leshy1::storage::shouldRetryProductStartIdentity(
                    evidence, attempt)) {
                break;
            }
            vTaskDelay(pdMS_TO_TICKS(
                leshy1::storage::productStartIdentityRetryDelayMs(attempt)));
        }
        if (!identityCleanupComplete ||
            identity.status !=
                leshy1::storage::SdTransportRunStatus::Valid) {
            event.status = "identity_failed";
            break;
        }
        if (std::strcmp(expectedFingerprint, observedFingerprint) != 0) {
            event.status = "fingerprint_mismatch";
            break;
        }
        filesystemAttempted = true;
        if (!productSurveyFilesystem.begin()) {
            event.status = "mount_failed";
            break;
        }
        const std::uint64_t cardCapacity =
            productSurveyFilesystem.cardCapacityBytes();
        const std::uint64_t cachedFree =
            productSurveyFilesystem.cachedFreeBytes();
        const bool rootExists = productSurveyFilesystem.exists(
            leshy1::storage::kProductSessionStoreRoot);
        leshy1::storage::MediaIdentity media;
        media.present = cardCapacity != 0 &&
            cardCapacity == identity.identity.capacityBytes;
        media.kind = leshy1::storage::MediaKind::Sd;
        media.fingerprint = observedFingerprint;
        media.capacityBytes = cardCapacity;
        media.freeBytes = cachedFree;
        leshy1::storage::ProductStoreRequest request;
        request.operation =
            leshy1::storage::ProductStoreOperation::CommitSession;
        request.explicitlySelected = true;
        request.expectedFingerprint = expectedFingerprint;
        request.rootPath = leshy1::storage::kProductSessionStoreRoot;
        request.rootExists = rootExists;
        request.driverWriteEnabled = true;
        request.requiredBytes = kProductSurveyCommitBytes;
        request.reserveBytes = kProductSurveyReserveBytes;
        request.ownedResources = owned;
        const leshy1::storage::ProductStorePermit permit =
            leshy1::storage::authorizeProductStore(media, request);
        if (!permit.allowed()) {
            event.status =
                leshy1::storage::productStoreAccessStatusName(permit.status);
            break;
        }
        if (!productSurveyStore.selectDrive(
                productSurveyFilesystem.driveNumber()) ||
            !productSurveyStore.openExistingWritable(permit)) {
            event.status = "store_open_failed";
            break;
        }

        char sessionId[SurveySession::kSessionIdCapacity + 1] = {};
        surveySession.reset();
        leshy1::storage::SessionStoreCommitResult commit;
        std::size_t expectedPulses = 0;
        if (infrared) {
            const auto& stats = infraredCapture.stats();
            std::snprintf(sessionId, sizeof(sessionId), "ir-raw-%08llx",
                          static_cast<unsigned long long>(
                              stats.signalStartedUs & 0xFFFFFFFFULL));
            expectedPulses = infraredCapture.pulseCount();
            if (stats.state != InfraredCaptureState::Complete ||
                expectedPulses == 0 ||
                surveySession.start(sessionId, stats.startedUs) !=
                    SessionStatus::Started ||
                surveySession.configureCaptureMetadata(
                    productInfraredRawCaptureMetadata()) !=
                    CaptureMetadataStatus::Configured ||
                surveySession.stop(stats.endedUs) != SessionStatus::Stopped) {
                event.status = "artifact_invalid";
                break;
            }
            commit = leshy1::storage::commitNextInfraredRawCapture(
                productSurveyStore, sessionStoreWorkspace, surveySession,
                infraredCapture);
        } else {
            const auto& stats = subGhzRawCapture.stats();
            std::snprintf(sessionId, sizeof(sessionId), "sub-raw-%08llx",
                          static_cast<unsigned long long>(
                              stats.signalStartedUs & 0xFFFFFFFFULL));
            expectedPulses = subGhzRawCapture.pulseCount();
            if (stats.state != SubGhzRawCaptureState::Complete ||
                expectedPulses == 0 ||
                surveySession.start(sessionId, stats.startedUs) !=
                    SessionStatus::Started ||
                surveySession.configureCaptureMetadata(
                    productSubGhzRawCaptureMetadata()) !=
                    CaptureMetadataStatus::Configured ||
                surveySession.stop(stats.endedUs) != SessionStatus::Stopped) {
                event.status = "artifact_invalid";
                break;
            }
            commit = leshy1::storage::commitNextSubGhzRawCapture(
                productSurveyStore, sessionStoreWorkspace, surveySession,
                subGhzRawCapture);
        }
        event.storeStatus = commit.status;
        if (!commit.complete()) {
            event.status =
                leshy1::storage::sessionStoreStatusName(commit.status);
            break;
        }
        const leshy1::storage::SessionStoreRecoveryResult recovered =
            leshy1::storage::recoverSession(
                productSurveyStore, sessionStoreWorkspace,
                &sessionStoreWorkspace.validationSession);
        if (!recovered.valid() || recovered.generation != commit.generation) {
            event.status = "reopen_failed";
            event.storeStatus = recovered.status;
            break;
        }
        bool pulseReopened = false;
        if (infrared) {
            leshy1::storage::PersistedInfraredRawCaptureView reopened;
            pulseReopened = leshy1::storage::openPersistedInfraredRawCapture(
                sessionStoreWorkspace.validationSession,
                sessionStoreWorkspace.segment.data(),
                sessionStoreWorkspace.segmentSize, &reopened) ==
                    leshy1::storage::SessionCodecStatus::Valid &&
                reopened.pulseCount() == expectedPulses;
        } else {
            leshy1::storage::PersistedSubGhzRawCaptureView reopened;
            pulseReopened = leshy1::storage::openPersistedSubGhzRawCapture(
                sessionStoreWorkspace.validationSession,
                sessionStoreWorkspace.segment.data(),
                sessionStoreWorkspace.segmentSize, &reopened) ==
                    leshy1::storage::SessionCodecStatus::Valid &&
                reopened.pulseCount() == expectedPulses;
        }
        if (!pulseReopened) {
            event.status = "pulse_reopen_failed";
            break;
        }
        event.valid = true;
        event.generation = recovered.generation;
        event.status = "saved";
    } while (false);

    productSurveyStore.end();
    if (productSurveyFilesystem.mounted()) productSurveyFilesystem.end();
    const bool filesystemCleanup = !filesystemAttempted ||
        productSurveyFilesystem.cleanupComplete();
    event.cleanupComplete = identityCleanupComplete && filesystemCleanup &&
        !productSurveyFilesystem.mounted();
    if (!event.cleanupComplete) {
        event.valid = false;
        event.status = "cleanup_failed";
    }
    if (events != nullptr) {
        xQueueSend(events, &event, portMAX_DELAY);
    }
    vTaskDelete(nullptr);
}

void runSubGhzCaptureStoreWorker(void*) {
    runPulseCaptureStoreWorker(false, subGhzCaptureStoreEvents);
}

void runInfraredCaptureStoreWorker(void*) {
    runPulseCaptureStoreWorker(true, infraredCaptureStoreEvents);
}

bool requestSubGhzRawCapturePersist() {
    if (subGhzCapturePersistState != CapturePersistState::Result ||
        subGhzRawCapture.stats().state !=
            SubGhzRawCaptureState::Complete ||
        subGhzRawCapture.pulseCount() == 0) {
        return false;
    }
    if (subGhzCaptureStoreEvents == nullptr ||
        subGhzCaptureStoreTaskHandle != nullptr) {
        subGhzCapturePersistState = CapturePersistState::Failed;
        subGhzCapturePersistStatus = "worker_unavailable";
        lastRuntimeEvent = "subghz_raw_store_worker_unavailable";
        return true;
    }
    const auto storageResources =
        leshy1::kernel::runtime::resourceMask(Resource::Storage);
    if (!resourceBroker.acquire(AppRuntime::kForegroundOwner,
                                storageResources)) {
        subGhzCapturePersistState = CapturePersistState::Failed;
        subGhzCapturePersistStatus = "resources_busy";
        lastRuntimeEvent = "subghz_raw_store_resources_busy";
        return true;
    }
    subGhzCapturePersistState = CapturePersistState::Saving;
    subGhzCapturePersistStatus = "saving";
    const bool started = xTaskCreatePinnedToCore(
        runSubGhzCaptureStoreWorker, "leshy-sub-store", 8192, nullptr, 1,
        &subGhzCaptureStoreTaskHandle, 0) == pdPASS;
    if (!started) {
        resourceBroker.release(AppRuntime::kForegroundOwner,
                               storageResources);
        subGhzCaptureStoreTaskHandle = nullptr;
        subGhzCapturePersistState = CapturePersistState::Failed;
        subGhzCapturePersistStatus = "worker_unavailable";
        lastRuntimeEvent = "subghz_raw_store_worker_unavailable";
    } else {
        lastRuntimeEvent = "subghz_raw_saving";
    }
    return true;
}

void serviceSubGhzRawCapturePersist() {
    if (subGhzCaptureStoreEvents == nullptr) return;
    CaptureStoreEvent event;
    if (xQueueReceive(subGhzCaptureStoreEvents, &event, 0) != pdTRUE) return;
    subGhzCaptureStoreTaskHandle = nullptr;
    resourceBroker.release(
        AppRuntime::kForegroundOwner,
        leshy1::kernel::runtime::resourceMask(Resource::Storage));
    const bool admitted = event.valid && event.cleanupComplete &&
        libraryController.replaceWithOwnedCopy(
            sessionStoreWorkspace.validationSession, librarySession,
            event.generation, SessionIntegrity::Valid, true, false);
    subGhzCapturePersistState = admitted ? CapturePersistState::Saved
                                        : CapturePersistState::Failed;
    subGhzCapturePersistStatus = admitted ? "saved" : event.status;
    subGhzCapturePersistGeneration = admitted ? event.generation : 0;
    lastRuntimeEvent = admitted ? "subghz_raw_saved"
                                : "subghz_raw_store_failed";
    if (rfSpectrumView == RfSpectrumView::SubGhzCaptureLive) {
        renderInteractiveScreen();
    }
}

bool requestInfraredRawCapturePersist() {
    if (infraredCapturePersistState != CapturePersistState::Result ||
        infraredCapture.stats().state != InfraredCaptureState::Complete ||
        infraredCapture.pulseCount() == 0) {
        return false;
    }
    if (infraredCaptureStoreEvents == nullptr ||
        infraredCaptureStoreTaskHandle != nullptr) {
        infraredCapturePersistState = CapturePersistState::Failed;
        infraredCapturePersistStatus = "worker_unavailable";
        lastRuntimeEvent = "infrared_raw_store_worker_unavailable";
        return true;
    }
    const auto storageResources =
        leshy1::kernel::runtime::resourceMask(Resource::Storage);
    if (!resourceBroker.acquire(AppRuntime::kForegroundOwner,
                                storageResources)) {
        infraredCapturePersistState = CapturePersistState::Failed;
        infraredCapturePersistStatus = "resources_busy";
        lastRuntimeEvent = "infrared_raw_store_resources_busy";
        return true;
    }
    infraredCapturePersistState = CapturePersistState::Saving;
    infraredCapturePersistStatus = "saving";
    const bool started = xTaskCreatePinnedToCore(
        runInfraredCaptureStoreWorker, "leshy-ir-store", 8192, nullptr, 1,
        &infraredCaptureStoreTaskHandle, 0) == pdPASS;
    if (!started) {
        resourceBroker.release(AppRuntime::kForegroundOwner,
                               storageResources);
        infraredCaptureStoreTaskHandle = nullptr;
        infraredCapturePersistState = CapturePersistState::Failed;
        infraredCapturePersistStatus = "worker_unavailable";
        lastRuntimeEvent = "infrared_raw_store_worker_unavailable";
    } else {
        lastRuntimeEvent = "infrared_raw_saving";
    }
    return true;
}

void serviceInfraredRawCapturePersist() {
    if (infraredCaptureStoreEvents == nullptr) return;
    CaptureStoreEvent event;
    if (xQueueReceive(infraredCaptureStoreEvents, &event, 0) != pdTRUE) return;
    infraredCaptureStoreTaskHandle = nullptr;
    resourceBroker.release(
        AppRuntime::kForegroundOwner,
        leshy1::kernel::runtime::resourceMask(Resource::Storage));
    const bool admitted = event.valid && event.cleanupComplete &&
        libraryController.replaceWithOwnedCopy(
            sessionStoreWorkspace.validationSession, librarySession,
            event.generation, SessionIntegrity::Valid, true, false);
    infraredCapturePersistState = admitted ? CapturePersistState::Saved
                                          : CapturePersistState::Failed;
    infraredCapturePersistStatus = admitted ? "saved" : event.status;
    infraredCapturePersistGeneration = admitted ? event.generation : 0;
    lastRuntimeEvent = admitted ? "infrared_raw_saved"
                                : "infrared_raw_store_failed";
    if (uiController.page() == 4 && captureView == CaptureView::Infrared) {
        renderInteractiveScreen();
    }
}

void releaseProductSurveyAfterTerminal(const char* status, bool returnHome) {
    if (surveyWorkflow.state() == SurveyWorkflowState::Running ||
        surveyWorkflow.state() == SurveyWorkflowState::Setup) {
        surveyPipeline.cancel();
    }
    closeProductSurveyBackend();
    productSurveyRuntime.status = productSurveyRuntime.cleanupComplete
                                      ? status
                                      : "cleanup_failed";
    lastRuntimeEvent = productSurveyRuntime.status;
    const bool returnToWifiMenu = returnHome && !uiController.isRoot() &&
        uiController.page() == 2 &&
        wifiProductView == WifiProductView::Networks &&
        std::strcmp(appRuntime.activeApp(), "wifi") == 0;
    const bool returnFromBle = returnHome && !uiController.isRoot() &&
        uiController.page() == 2 &&
        bleProductView != BleProductView::None &&
        std::strcmp(appRuntime.activeApp(), "ble") == 0;
    if (returnToWifiMenu) {
        surveyPipeline.resetToSetup();
        wifiProductView = WifiProductView::Menu;
        wifiProductSelection = 0;
        lastRuntimeEvent = "wifi_menu";
    } else if (returnHome && !uiController.isRoot() &&
               uiController.page() == 2) {
        if (returnFromBle) bleProductView = BleProductView::None;
        uiController.apply(UiAction::Back,
                           static_cast<std::uint8_t>(appCatalog.size()), false);
    }
    if (!returnToWifiMenu && appRuntime.running()) appRuntime.stop();
    setProductSurveyControl(ProductSurveyWorkerControl::Idle);
    renderInteractiveScreen();
}

void serviceProductSurveyWorker() {
    if (productSurveyWorkerEvents == nullptr) return;
    bool render = false;
    ProductSurveyWorkerEvent event;
    while (xQueueReceive(productSurveyWorkerEvents, &event, 0) == pdTRUE) {
        applyProductSurveyWorkerReport(event.report);
        if (event.kind != ProductSurveyWorkerEventKind::ScanStarted) {
            productSurveyRuntime.scan = event.scan;
            productSurveyRuntime.bleScan = event.bleScan;
            productSurveyRuntime.scanCycles = event.scanCycles;
            if (event.source == RadioKind::Wifi) {
                productSurveyRuntime.wifiScanCycles = event.sourceScanCycles;
            } else {
                productSurveyRuntime.bleScanCycles = event.sourceScanCycles;
            }
        }
        if (event.kind == ProductSurveyWorkerEventKind::Prepared) {
            std::uint64_t startedUs = event.eventUs;
            if (startedUs == 0) startedUs = 1;
            const SurveyPipelineStatus pipelineStarted = surveyPipeline.start(
                "product-passive-live", startedUs);
            const CaptureMetadataStatus captureConfigured =
                pipelineStarted == SurveyPipelineStatus::Started
                    ? surveySession.configureCaptureMetadata(
                          productCaptureMetadata(
                              productSurveyRuntime.selectedSourceMask))
                    : CaptureMetadataStatus::InvalidState;
            const SourceTimelineStatus timelineStarted =
                pipelineStarted == SurveyPipelineStatus::Started &&
                        captureConfigured == CaptureMetadataStatus::Configured
                    ? productSurveyTimeline.start(
                          productSurveyRuntime.selectedSourceMask, startedUs)
                    : SourceTimelineStatus::InvalidState;
            const auto archiveStarted =
                pipelineStarted == SurveyPipelineStatus::Started &&
                        timelineStarted == SourceTimelineStatus::Started
                    ? surveySession.startTimeline(
                          productSurveyRuntime.selectedSourceMask, startedUs)
                    : leshy1::services::survey::SessionTimelineStatus::NotRunning;
            productSurveyRuntime.timelineArchiveStatus =
                leshy1::services::survey::sessionTimelineStatusName(
                    archiveStarted);
            bool degradationRecorded = true;
            if (pipelineStarted == SurveyPipelineStatus::Started &&
                timelineStarted == SourceTimelineStatus::Started &&
                archiveStarted ==
                    leshy1::services::survey::SessionTimelineStatus::Started) {
                for (const RadioKind source :
                     std::array<RadioKind, 2>{RadioKind::Wifi, RadioKind::Ble}) {
                    if ((event.report.unavailableSourceMask &
                         leshy1::services::survey::sourceMask(source)) == 0) {
                        continue;
                    }
                    const SourceTimelineStatus unavailable =
                        productSurveyTimeline.transition(
                            source, SourceWindowState::Unavailable,
                            SourceWindowReason::DriverUnavailable, startedUs);
                    if (!applyProductSurveyTimelineStatus(
                            unavailable, SourceTimelineStatus::Transitioned,
                            "initial_unavailable", startedUs) ||
                        !drainProductSurveyTimelineWindows()) {
                        degradationRecorded = false;
                        break;
                    }
                }
            }
            if (pipelineStarted != SurveyPipelineStatus::Started ||
                captureConfigured != CaptureMetadataStatus::Configured ||
                !applyProductSurveyTimelineStatus(
                    timelineStarted, SourceTimelineStatus::Started,
                    "timeline_start", startedUs) ||
                archiveStarted !=
                    leshy1::services::survey::SessionTimelineStatus::Started ||
                !degradationRecorded) {
                productSurveyTimeline.reset();
                requestProductSurveyWorkerStop(true);
                productSurveyRuntime.status = "workflow_start_failed";
            } else {
                productSurveyRuntime.status = "running";
                productSurveyRuntime.backendOpen = true;
                productSurveyRuntime.sourceActive = true;
                lastRuntimeEvent = "product_survey_running";
            }
            render = true;
        } else if (event.kind ==
                   ProductSurveyWorkerEventKind::ScanStarted) {
            const SourceTimelineStatus status =
                productSurveyTimeline.transition(
                    event.source, SourceWindowState::Active,
                    SourceWindowReason::None, event.scanStartedUs);
            const bool scanStartReady = applyProductSurveyTimelineStatus(
                    status, SourceTimelineStatus::Transitioned,
                    "scan_start", event.scanStartedUs) &&
                drainProductSurveyTimelineWindows();
            if (!scanStartReady) {
                productSurveyRuntime.status = "timeline_start_failed";
                lastRuntimeEvent = productSurveyRuntime.status;
                requestProductSurveyWorkerStop(true);
            }
            xSemaphoreGive(productSurveyScanStartGate);
        } else if (event.kind == ProductSurveyWorkerEventKind::Scan) {
            if (closeProductSurveyScanWindow(event)) {
                productSurveyRuntime.status =
                    event.report.unavailableSourceMask == 0
                        ? "running" : "running_degraded";
                productSurveyRuntime.sourceActive = true;
                lastRuntimeEvent =
                    event.report.unavailableSourceMask == 0
                        ? "product_survey_scan"
                        : "product_survey_scan_degraded";
            } else {
                productSurveyRuntime.status = "timeline_close_failed";
                lastRuntimeEvent = productSurveyRuntime.status;
                requestProductSurveyWorkerStop(true);
            }
            render = true;
        } else if (event.kind ==
                   ProductSurveyWorkerEventKind::SourceUnavailable) {
            if (closeProductSurveyScanWindow(
                    event, event.failureState, event.failureReason)) {
                productSurveyRuntime.status = "running_degraded";
                productSurveyRuntime.sourceActive =
                    event.report.activeSourceMask != 0;
                lastRuntimeEvent = "product_survey_source_degraded";
            } else {
                productSurveyRuntime.status = "timeline_degrade_failed";
                lastRuntimeEvent = productSurveyRuntime.status;
                requestProductSurveyWorkerStop(true);
            }
            render = true;
        } else if (event.kind == ProductSurveyWorkerEventKind::Paused) {
            const bool windowClosed = closeProductSurveyScanWindow(event);
            productSurveyRuntime.sourceActive = false;
            const SourceTimelineStatus timelineStopped = windowClosed
                ? productSurveyTimeline.stop(event.eventUs)
                : SourceTimelineStatus::InvalidState;
            const bool sourceStopped = windowClosed &&
                applyProductSurveyTimelineStatus(
                    timelineStopped, SourceTimelineStatus::Stopped,
                    "timeline_pause", event.eventUs) &&
                drainProductSurveyTimelineWindows();
            const auto* wifi = productSurveyTimeline.source(RadioKind::Wifi);
            const auto* ble = productSurveyTimeline.source(RadioKind::Ble);
            const auto archiveFinalized =
                sourceStopped && wifi != nullptr && ble != nullptr
                    ? surveySession.finalizeTimeline(
                          event.eventUs, *wifi, *ble,
                          productSurveyTimeline.overflowEvents())
                    : leshy1::services::survey::SessionTimelineStatus::InvalidSummary;
            productSurveyRuntime.timelineArchiveStatus =
                leshy1::services::survey::sessionTimelineStatusName(
                    archiveFinalized);
            if (sourceStopped &&
                archiveFinalized ==
                    leshy1::services::survey::SessionTimelineStatus::Finalized) {
                productSurveyRuntime.status = "paused";
                lastRuntimeEvent = "product_survey_paused";
                setProductSurveyControl(ProductSurveyWorkerControl::Paused);
                render = true;
            } else {
                releaseProductSurveyAfterTerminal("pause_failed", true);
                render = false;
            }
        } else if (event.kind == ProductSurveyWorkerEventKind::Stopped) {
            const bool windowClosed = closeProductSurveyScanWindow(event);
            productSurveyRuntime.sourceActive = false;
            const SourceTimelineStatus timelineStopped = windowClosed
                ? productSurveyTimeline.stop(event.eventUs)
                : SourceTimelineStatus::InvalidState;
            const bool sourceStopped = windowClosed &&
                applyProductSurveyTimelineStatus(
                    timelineStopped, SourceTimelineStatus::Stopped,
                    "timeline_stop", event.eventUs) &&
                drainProductSurveyTimelineWindows();
            const auto* wifi = productSurveyTimeline.source(RadioKind::Wifi);
            const auto* ble = productSurveyTimeline.source(RadioKind::Ble);
            const auto archiveFinalized =
                sourceStopped && wifi != nullptr && ble != nullptr
                    ? surveySession.finalizeTimeline(
                          event.eventUs, *wifi, *ble,
                          productSurveyTimeline.overflowEvents())
                    : leshy1::services::survey::SessionTimelineStatus::InvalidSummary;
            productSurveyRuntime.timelineArchiveStatus =
                leshy1::services::survey::sessionTimelineStatusName(
                    archiveFinalized);
            const bool timelineComplete = sourceStopped &&
                archiveFinalized ==
                    leshy1::services::survey::SessionTimelineStatus::Finalized;
            const SurveyPipelineStatus stopped = timelineComplete
                ? stopProductSurvey() : SurveyPipelineStatus::WorkflowRejected;
            if (!timelineComplete ||
                stopped != SurveyPipelineStatus::Committed) {
                releaseProductSurveyAfterTerminal("commit_failed", true);
                render = false;
            } else {
                setProductSurveyControl(ProductSurveyWorkerControl::Idle);
                render = true;
            }
        } else if (event.kind == ProductSurveyWorkerEventKind::Cancelled) {
            const bool windowClosed = closeProductSurveyScanWindow(event);
            const SourceTimelineStatus cancelled =
                productSurveyTimeline.state() == SourceTimelineState::Running
                    ? productSurveyTimeline.cancel(event.eventUs)
                    : SourceTimelineStatus::Cancelled;
            const bool timelineCancelled = windowClosed &&
                (cancelled == SourceTimelineStatus::Cancelled);
            applyProductSurveyTimelineStatus(
                cancelled, SourceTimelineStatus::Cancelled,
                "timeline_cancel", event.eventUs);
            releaseProductSurveyAfterTerminal(
                timelineCancelled ? "cancelled" : "timeline_cancel_failed",
                true);
            render = false;
        } else {
            const bool windowClosed = closeProductSurveyScanWindow(
                event, SourceWindowState::Fault,
                SourceWindowReason::DriverFault);
            if (!windowClosed) event.report.status = "timeline_fault_failed";
            if (productSurveyTimeline.state() == SourceTimelineState::Running) {
                const SourceTimelineStatus cancelled =
                    productSurveyTimeline.cancel(event.eventUs);
                applyProductSurveyTimelineStatus(
                    cancelled, SourceTimelineStatus::Cancelled,
                    "timeline_failure_cancel", event.eventUs);
            }
            const bool keepVisible = event.report.admissionStatus ==
                leshy1::apps::survey::ProductSurveyAdmissionStatus::SourceUnavailable;
            releaseProductSurveyAfterTerminal(event.report.status, !keepVisible);
            render = false;
        }
    }
    if (drainProductSurveyWorkerObservations()) render = true;
    // Keep a detail page visually stable while the worker continues updating
    // the backing catalog. Returning to the list reveals the latest values.
    if (render && wifiProductView != WifiProductView::NetworkDetail &&
        bleProductView != BleProductView::DeviceDetail) {
        productSurveyIncrementalRefreshPending = true;
        renderInteractiveScreen(false);
        productSurveyIncrementalRefreshPending = false;
    }
}

void recoverProductCatalogForFingerprint(const char* expectedFingerprint,
                                         bool enrollmentPresent) {
    productBootRecovery = {};
    productBootRecovery.status = "invalid_enrollment";
    productBootRecovery.cleanupComplete = true;
    productBootRecovery.enrolled = enrollmentPresent;
    if (!exactCidFingerprint(expectedFingerprint)) return;
    std::snprintf(productBootRecovery.expectedFingerprint,
                  sizeof(productBootRecovery.expectedFingerprint), "%s",
                  expectedFingerprint);

    const bool resourcesAcquired = resourceBroker.acquire(
        kBootCatalogOwner, leshy1::storage::kSdIdentificationResources);
    productBootRecovery.ownedDuring = resourceBroker.ownedBy(kBootCatalogOwner);
    if (!resourcesAcquired) {
        productBootRecovery.status = "resources_unavailable";
        productBootRecovery.cleanupComplete = true;
        return;
    }

    BoardSdSpiTransport identityTransport;
    const bool identityBegun = identityTransport.begin();
    leshy1::storage::SdTransportRunResult identity;
    if (identityBegun) {
        leshy1::storage::SdTransportRunPolicy policy;
        policy.allowPhysical = true;
        policy.explicitlySelected = true;
        policy.identificationOnly = true;
        policy.ownedResources = productBootRecovery.ownedDuring;
        identity = leshy1::storage::runSdIdentificationStateMachine(
            leshy1::storage::defaultSdIdentificationPlan(), identityTransport,
            policy);
        identityTransport.end();
    }
    const bool identityCleanup = identityTransport.cleanupComplete();
    formatCidFingerprint(identity.identity,
                         productBootRecovery.observedFingerprint,
                         sizeof(productBootRecovery.observedFingerprint));
    productBootRecovery.fingerprintMatched =
        identity.status == leshy1::storage::SdTransportRunStatus::Valid &&
        std::strcmp(productBootRecovery.observedFingerprint,
                    productBootRecovery.expectedFingerprint) == 0;

    BoardSdFilesystem filesystem;
    const bool mounted = productBootRecovery.fingerprintMatched &&
                         filesystem.beginReadOnly();
    productBootRecovery.mountedReadOnly = mounted;
    productBootRecovery.readOnlyGuaranteed =
        mounted && filesystem.readOnlyGuaranteed();
    const std::uint64_t cardCapacity =
        mounted ? filesystem.cardCapacityBytes() : 0;
    const bool capacityMatched = mounted &&
        cardCapacity != 0 && cardCapacity == identity.identity.capacityBytes;
    productBootRecovery.rootExists = mounted && filesystem.exists(
        leshy1::storage::kProductSessionStoreRoot);

    leshy1::storage::MediaIdentity media;
    media.present = capacityMatched;
    media.kind = leshy1::storage::MediaKind::Sd;
    media.fingerprint = productBootRecovery.observedFingerprint;
    media.capacityBytes = cardCapacity;
    // Recovery never writes, so it does not need an O(media-size) free-space
    // scan. Zero is valid geometry and keeps cold boot bounded.
    media.freeBytes = 0;
    leshy1::storage::ProductStoreRequest request;
    request.operation = leshy1::storage::ProductStoreOperation::RecoverCatalog;
    request.expectedFingerprint = productBootRecovery.expectedFingerprint;
    request.rootPath = leshy1::storage::kProductSessionStoreRoot;
    request.rootExists = productBootRecovery.rootExists;
    request.driverReadOnlyGuaranteed =
        productBootRecovery.readOnlyGuaranteed;
    request.ownedResources = productBootRecovery.ownedDuring;
    const leshy1::storage::ProductStorePermit permit =
        leshy1::storage::authorizeProductStore(media, request);
    productBootRecovery.permitStatus = permit.status;

    if (permit.allowed()) {
        ArduinoFsSessionStoreIo io(filesystem.driveNumber(),
                                   sdSessionStoreIoWorkspace);
        productBootRecovery.opened = io.openExistingReadOnly(permit);
        if (productBootRecovery.opened) {
            productBootRecovery.catalog = sessionCatalog.recoverLatest(
                io, sessionStoreWorkspace, librarySession, libraryController,
                true, false);
            productBootRecovery.catalogAdmitted =
                productBootRecovery.catalog.admitted();
        }
        io.end();
    }
    productBootRecovery.blockedWriteAttempts =
        filesystem.blockedWriteAttempts();
    if (productBootRecovery.fingerprintMatched) filesystem.end();
    const bool filesystemCleanup =
        !productBootRecovery.fingerprintMatched || filesystem.cleanupComplete();
    resourceBroker.releaseAll(kBootCatalogOwner);
    productBootRecovery.ownedAfter = resourceBroker.ownedBy(kBootCatalogOwner);
    productBootRecovery.cleanupComplete = identityCleanup && filesystemCleanup &&
        productBootRecovery.ownedAfter == 0 &&
        productBootRecovery.blockedWriteAttempts == 0;

    if (!identityBegun || identity.status !=
                              leshy1::storage::SdTransportRunStatus::Valid) {
        productBootRecovery.status = "identity_failed";
    } else if (!productBootRecovery.fingerprintMatched) {
        productBootRecovery.status = "fingerprint_mismatch";
    } else if (!mounted || !productBootRecovery.readOnlyGuaranteed) {
        productBootRecovery.status = "readonly_mount_failed";
    } else if (!permit.allowed()) {
        productBootRecovery.status =
            leshy1::storage::productStoreAccessStatusName(permit.status);
    } else if (!productBootRecovery.opened) {
        productBootRecovery.status = "open_failed";
    } else if (productBootRecovery.catalogAdmitted) {
        productBootRecovery.status = "admitted";
        libraryDemoReady = true;
    } else {
        productBootRecovery.status =
            leshy1::apps::library::sessionCatalogStatusName(
                productBootRecovery.catalog.status);
    }
    if (!productBootRecovery.cleanupComplete) {
        productBootRecovery.status = "cleanup_failed";
    }
}

bool IRAM_ATTR recordProductBootRecoveryTimeout() {
    if (__atomic_exchange_n(&productBootRecoveryWatchdogArmed, 0,
                            __ATOMIC_ACQ_REL) == 0) {
        return false;
    }
    if (productBootRetryRtcMagic == kProductBootRetryRtcMagic &&
        productBootRetryRestarts <
            leshy1::storage::kProductBootMaximumAttempts) {
        ++productBootRetryRestarts;
        ++productBootRetryTimeouts;
    }
    return true;
}

static_assert(BoardProfile::kBuzzerPin == 2 &&
                  BoardProfile::kNrfCePins[0] == 15 &&
                  BoardProfile::kNrfCePins[1] == 47 &&
                  BoardProfile::kNrfCePins[2] == 14,
              "Task-WDT emergency GPIO masks must match the board profile");

void IRAM_ATTR quiesceEmergencyGpioFromIsr() {
    // GPIO2 is the active-high buzzer. GPIO14/15/47 are every declared nRF CE
    // path. Write-one-to-clear is peripheral-local, allocation-free, and does
    // not depend on a healthy scheduler or flash-resident Arduino code.
    GPIO.out_w1tc = (1U << 2U) | (1U << 14U) | (1U << 15U);
    GPIO.out1_w1tc.val = (1U << (47U - 32U));
}

bool IRAM_ATTR recordRuntimeSafetyWatchdogTrip() {
    if (__atomic_exchange_n(&runtimeSafetyWatchdogArmed, 0,
                            __ATOMIC_ACQ_REL) == 0) {
        return false;
    }
    quiesceEmergencyGpioFromIsr();
    const std::uint32_t appIdentity = runtimeSafetyAppIdentity;
    const std::uint32_t reason =
        static_cast<std::uint32_t>(SafetyReason::RuntimeWatchdog);
    const std::uint32_t tripCount = runtimeSafetyNextTripCount;
    const std::uint32_t quiesceCount = runtimeSafetyNextQuiesceCount;
    // Invalidate first and publish magic last. Complements reject a reset in
    // the middle of this bounded RTC write sequence.
    safetyRetainedRtc.magic = 0;
    safetyRetainedRtc.schema = leshy1::kernel::safety::kSafetyRetainedSchema;
    safetyRetainedRtc.appIdentity = appIdentity;
    safetyRetainedRtc.appIdentityInverse = ~appIdentity;
    safetyRetainedRtc.reason = reason;
    safetyRetainedRtc.reasonInverse = ~reason;
    safetyRetainedRtc.tripCount = tripCount;
    safetyRetainedRtc.tripCountInverse = ~tripCount;
    safetyRetainedRtc.quiesceCount = quiesceCount;
    safetyRetainedRtc.quiesceCountInverse = ~quiesceCount;
    safetyRetainedRtc.latchConfirmed = 0;
    safetyRetainedRtc.latchConfirmedInverse = ~1U;
    __atomic_thread_fence(__ATOMIC_RELEASE);
    safetyRetainedRtc.magic = leshy1::kernel::safety::kSafetyRetainedMagic;
    return true;
}

extern "C" void IRAM_ATTR esp_task_wdt_isr_user_handler() {
    // The Task WDT ISR is the last-resort path when the scheduler-based
    // watchdog cannot run. Only claim the already armed recovery attempt and
    // retain its reason; the configured panic path performs the reset.
    if (!recordProductBootRecoveryTimeout()) {
        recordRuntimeSafetyWatchdogTrip();
    }
}

void watchProductBootRecovery(void*) {
    delay(leshy1::storage::kProductBootRecoveryWatchdogMs);
    if (recordProductBootRecoveryTimeout()) {
        // Recovery may hold filesystem or console locks. Do not log, flush,
        // or run shutdown handlers here; retain the reason in RTC and force a
        // digital restart from this independent task.
        esp_restart_noos();
    }
    vTaskDelete(nullptr);
}

bool armProductBootRecoveryWatchdog() {
    productBootRecoveryTaskWatchdogAdded = false;
    const esp_err_t taskWatchdogStatus = esp_task_wdt_status(nullptr);
    if (taskWatchdogStatus == ESP_ERR_NOT_FOUND) {
        if (esp_task_wdt_add(nullptr) != ESP_OK) return false;
        productBootRecoveryTaskWatchdogAdded = true;
    } else if (taskWatchdogStatus != ESP_OK) {
        return false;
    }
    if (esp_task_wdt_reset() != ESP_OK) {
        if (productBootRecoveryTaskWatchdogAdded) {
            esp_task_wdt_delete(nullptr);
            productBootRecoveryTaskWatchdogAdded = false;
        }
        return false;
    }
    __atomic_store_n(&productBootRecoveryWatchdogArmed, 1,
                     __ATOMIC_RELEASE);
    productBootRecoveryWatchdogTask = nullptr;
    if (xTaskCreatePinnedToCore(
            watchProductBootRecovery, "leshy-sd-boot-watch", 2048, nullptr, 3,
            &productBootRecoveryWatchdogTask, 0) != pdPASS) {
        __atomic_store_n(&productBootRecoveryWatchdogArmed, 0,
                         __ATOMIC_RELEASE);
        productBootRecoveryWatchdogTask = nullptr;
        if (productBootRecoveryTaskWatchdogAdded) {
            esp_task_wdt_delete(nullptr);
            productBootRecoveryTaskWatchdogAdded = false;
        }
        return false;
    }
    return true;
}

bool disarmProductBootRecoveryWatchdog() {
    __atomic_store_n(&productBootRecoveryWatchdogArmed, 0,
                     __ATOMIC_RELEASE);
    TaskHandle_t task = productBootRecoveryWatchdogTask;
    productBootRecoveryWatchdogTask = nullptr;
    if (task != nullptr) vTaskDelete(task);
    if (!productBootRecoveryTaskWatchdogAdded) return true;
    productBootRecoveryTaskWatchdogAdded = false;
    return esp_task_wdt_delete(nullptr) == ESP_OK;
}

bool safetyWatchdogResetReason(std::uint32_t reason) {
    return reason == static_cast<std::uint32_t>(ESP_RST_PANIC) ||
           reason == static_cast<std::uint32_t>(ESP_RST_INT_WDT) ||
           reason == static_cast<std::uint32_t>(ESP_RST_TASK_WDT) ||
           reason == static_cast<std::uint32_t>(ESP_RST_WDT);
}

SafetyRetainedRecord snapshotSafetyRetainedRecord() {
    SafetyRetainedRecord record{};
    record.magic = safetyRetainedRtc.magic;
    record.schema = safetyRetainedRtc.schema;
    record.appIdentity = safetyRetainedRtc.appIdentity;
    record.appIdentityInverse = safetyRetainedRtc.appIdentityInverse;
    record.reason = safetyRetainedRtc.reason;
    record.reasonInverse = safetyRetainedRtc.reasonInverse;
    record.tripCount = safetyRetainedRtc.tripCount;
    record.tripCountInverse = safetyRetainedRtc.tripCountInverse;
    record.quiesceCount = safetyRetainedRtc.quiesceCount;
    record.quiesceCountInverse = safetyRetainedRtc.quiesceCountInverse;
    record.latchConfirmed = safetyRetainedRtc.latchConfirmed;
    record.latchConfirmedInverse = safetyRetainedRtc.latchConfirmedInverse;
    return record;
}

void clearSafetyRetainedRecord() {
    safetyRetainedRtc.magic = 0;
    safetyRetainedRtc.schema = 0;
    safetyRetainedRtc.appIdentity = 0;
    safetyRetainedRtc.appIdentityInverse = 0;
    safetyRetainedRtc.reason = 0;
    safetyRetainedRtc.reasonInverse = 0;
    safetyRetainedRtc.tripCount = 0;
    safetyRetainedRtc.tripCountInverse = 0;
    safetyRetainedRtc.quiesceCount = 0;
    safetyRetainedRtc.quiesceCountInverse = 0;
    safetyRetainedRtc.latchConfirmed = 0;
    safetyRetainedRtc.latchConfirmedInverse = 0;
}

void persistSafetyStop(SafetyReason reason, std::uint32_t tripCount,
                       std::uint32_t quiesceCount) {
    const SafetyRetainedRecord record =
        leshy1::kernel::safety::makeSafetyRetainedRecord(
            runningAppIdentity, reason, tripCount, quiesceCount);
    safetyRetainedRtc.magic = 0;
    safetyRetainedRtc.schema = record.schema;
    safetyRetainedRtc.appIdentity = record.appIdentity;
    safetyRetainedRtc.appIdentityInverse = record.appIdentityInverse;
    safetyRetainedRtc.reason = record.reason;
    safetyRetainedRtc.reasonInverse = record.reasonInverse;
    safetyRetainedRtc.tripCount = record.tripCount;
    safetyRetainedRtc.tripCountInverse = record.tripCountInverse;
    safetyRetainedRtc.quiesceCount = record.quiesceCount;
    safetyRetainedRtc.quiesceCountInverse = record.quiesceCountInverse;
    safetyRetainedRtc.latchConfirmed = record.latchConfirmed;
    safetyRetainedRtc.latchConfirmedInverse = record.latchConfirmedInverse;
    safetyRetainedRtc.magic = record.magic;
}

void confirmRetainedSafetyLatch(const SafetyRetainedRecord& record) {
    if (record.latchConfirmed == 1U) return;
    // The ISR already published the target inverse (~1). One aligned store
    // confirms the latch without creating a reset window in which the otherwise
    // valid watchdog record would be rejected.
    safetyRetainedRtc.latchConfirmed = 1U;
    __atomic_thread_fence(__ATOMIC_RELEASE);
}

void latchSafetyStopInTask(SafetyReason reason) {
    BoardSafeOutputs::emergencyQuiesce();
    BoardSdSpiTransport::holdRadioTransmitPathsInactive();
    const std::uint32_t tripCount = safetySupervisor.tripCount() + 1U;
    const std::uint32_t quiesceCount = safetySupervisor.quiesceCount() + 1U;
    persistSafetyStop(reason, tripCount, quiesceCount);
    safetySupervisor.latch(reason, tripCount, quiesceCount);
    runtimeSafetyWatchdogReady = false;
    __atomic_store_n(&runtimeSafetyWatchdogArmed, 0, __ATOMIC_RELEASE);
}

bool armRuntimeSafetyWatchdog() {
    const esp_err_t status = esp_task_wdt_status(nullptr);
    if (status == ESP_ERR_NOT_FOUND) {
        if (esp_task_wdt_add(nullptr) != ESP_OK) return false;
    } else if (status != ESP_OK) {
        return false;
    }
    if (esp_task_wdt_reset() != ESP_OK) return false;
    runtimeSafetyAppIdentity = runningAppIdentity;
    runtimeSafetyNextTripCount = safetySupervisor.tripCount() + 1U;
    runtimeSafetyNextQuiesceCount = safetySupervisor.quiesceCount() + 1U;
    __atomic_store_n(&runtimeSafetyWatchdogArmed, 1, __ATOMIC_RELEASE);
    if (safetySupervisor.state() == SafetyState::Startup) {
        safetySupervisor.arm();
    }
    runtimeSafetyWatchdogReady = true;
    return true;
}

void feedRuntimeSafetyWatchdog() {
    if (!runtimeSafetyWatchdogReady) return;
    if (esp_task_wdt_reset() != ESP_OK) {
        latchSafetyStopInTask(SafetyReason::SupervisorUnavailable);
        renderInteractiveScreen(true);
    }
}

[[noreturn]] void clearSafetyStopAndRestart() {
    BoardSafeOutputs::emergencyQuiesce();
    BoardSdSpiTransport::holdRadioTransmitPathsInactive();
    __atomic_store_n(&runtimeSafetyWatchdogArmed, 0, __ATOMIC_RELEASE);
    clearSafetyRetainedRecord();
    safetySupervisor.confirmClear(true);
    broadcast(
        "{\"schema\":\"leshy.safety.v1\",\"kind\":\"cleared\","
        "\"restart_required\":true,\"outputs_inactive\":true}");
    Serial.flush();
    Serial0.flush();
    delay(20);
    esp_restart();
    for (;;) {}
}

void recoverProductCatalogAtBoot() {
    const bool softwareReset =
        bootMetrics.resetReason == static_cast<std::uint32_t>(ESP_RST_SW);
    const bool watchdogReset =
        bootMetrics.resetReason == static_cast<std::uint32_t>(ESP_RST_PANIC) ||
        bootMetrics.resetReason == static_cast<std::uint32_t>(ESP_RST_INT_WDT) ||
        bootMetrics.resetReason == static_cast<std::uint32_t>(ESP_RST_TASK_WDT) ||
        bootMetrics.resetReason == static_cast<std::uint32_t>(ESP_RST_WDT);
    const bool retryReset = leshy1::storage::isProductBootRetryReset(
        softwareReset, watchdogReset, productBootRetryTimeouts > 0);
    std::uint32_t currentAppIdentity = 0;
    const esp_app_desc_t* appDescription = esp_app_get_description();
    if (appDescription != nullptr &&
        appDescription->magic_word == ESP_APP_DESC_MAGIC_WORD) {
        std::memcpy(&currentAppIdentity, appDescription->app_elf_sha256,
                    sizeof(currentAppIdentity));
    }
    if (leshy1::storage::shouldResetProductBootRetryState(
            retryReset,
            productBootRetryRtcMagic == kProductBootRetryRtcMagic,
            currentAppIdentity != 0,
            productBootRetryAppIdentity == currentAppIdentity)) {
        productBootRetryRtcMagic = kProductBootRetryRtcMagic;
        productBootRetryRestarts = 0;
        productBootRetryAppIdentity = currentAppIdentity;
        productBootRetryTimeouts = 0;
        productBootWatchdogTestRtcState = 0;
    }
    char expectedFingerprint[33] = {};
    if (!loadProductFingerprint(expectedFingerprint,
                                sizeof(expectedFingerprint))) {
        productBootRecovery = {};
        productBootRecovery.status = "unenrolled";
        productBootRecovery.cleanupComplete = true;
        productBootRetryRestarts = 0;
        productBootRetryTimeouts = 0;
        return;
    }
    if (productBootRetryRestarts >=
        leshy1::storage::kProductBootMaximumAttempts) {
        productBootRecovery = {};
        productBootRecovery.status = "recovery_timeout_exhausted";
        productBootRecovery.enrolled = true;
        std::snprintf(productBootRecovery.expectedFingerprint,
                      sizeof(productBootRecovery.expectedFingerprint), "%s",
                      expectedFingerprint);
        productBootRecovery.attempts =
            leshy1::storage::kProductBootMaximumAttempts;
        productBootRecovery.transientRetries = static_cast<std::uint8_t>(
            leshy1::storage::kProductBootMaximumAttempts - 1U);
        productBootRecovery.timeoutRestarts = static_cast<std::uint8_t>(
            productBootRetryTimeouts);
        productBootRecovery.cleanupComplete = false;
        productBootRetryRestarts = 0;
        productBootRetryTimeouts = 0;
        return;
    }
    if (!armProductBootRecoveryWatchdog()) {
        productBootRecovery = {};
        productBootRecovery.status = "recovery_watchdog_unavailable";
        productBootRecovery.enrolled = true;
        std::snprintf(productBootRecovery.expectedFingerprint,
                      sizeof(productBootRecovery.expectedFingerprint), "%s",
                      expectedFingerprint);
        productBootRecovery.attempts = static_cast<std::uint8_t>(
            productBootRetryRestarts + 1U);
        productBootRecovery.transientRetries = static_cast<std::uint8_t>(
            productBootRetryRestarts);
        productBootRecovery.timeoutRestarts = static_cast<std::uint8_t>(
            productBootRetryTimeouts);
        productBootRecovery.cleanupComplete = true;
        productBootRetryRestarts = 0;
        productBootRetryTimeouts = 0;
        return;
    }
    if (productBootWatchdogTestRtcState ==
        kProductBootWatchdogTestRtcMagic) {
        productBootWatchdogTestRtcState = 0;
        TaskHandle_t softwareWatchdog = productBootRecoveryWatchdogTask;
        productBootRecoveryWatchdogTask = nullptr;
        if (softwareWatchdog != nullptr) vTaskDelete(softwareWatchdog);
        for (;;) delay(1000);
    }
    recoverProductCatalogForFingerprint(expectedFingerprint, true);
    if (!disarmProductBootRecoveryWatchdog()) {
        productBootRecovery.status = "recovery_watchdog_cleanup_failed";
        productBootRecovery.cleanupComplete = false;
    }
    const std::uint8_t completedAttempts = static_cast<std::uint8_t>(
        productBootRetryRestarts + 1U);
    productBootRecovery.attempts = completedAttempts;
    productBootRecovery.transientRetries = static_cast<std::uint8_t>(
        productBootRetryRestarts);
    productBootRecovery.timeoutRestarts = static_cast<std::uint8_t>(
        productBootRetryTimeouts);
    const leshy1::storage::ProductBootRetryEvidence retryEvidence{
        std::strcmp(productBootRecovery.status, "identity_failed") == 0,
        productBootRecovery.enrolled,
        exactCidFingerprint(productBootRecovery.expectedFingerprint),
        std::strcmp(
            productBootRecovery.observedFingerprint,
            "00000000000000000000000000000000") == 0,
        productBootRecovery.fingerprintMatched,
        productBootRecovery.mountedReadOnly,
        productBootRecovery.rootExists,
        productBootRecovery.opened,
        productBootRecovery.catalogAdmitted,
        productBootRecovery.permitStatus ==
            leshy1::storage::ProductStoreAccessStatus::MissingMedia,
        productBootRecovery.cleanupComplete,
        productBootRecovery.blockedWriteAttempts,
        productBootRecovery.ownedAfter,
    };
    if (leshy1::storage::shouldRetryProductBootRecovery(
            retryEvidence, completedAttempts)) {
        ++productBootRetryRestarts;
        char line[320] = {};
        std::snprintf(
            line, sizeof(line),
            "{\"schema\":\"leshy.storage.product_boot_retry.v1\","
            "\"kind\":\"restart\",\"reason\":\"transient_missing_media\","
            "\"completed_attempts\":%u,\"next_attempt\":%u,"
            "\"delay_ms\":%lu,\"blocked_write_attempts\":0,"
            "\"owned_after\":0,\"cleanup_complete\":true}",
            static_cast<unsigned>(completedAttempts),
            static_cast<unsigned>(completedAttempts + 1U),
            static_cast<unsigned long>(
                leshy1::storage::productBootRetryDelayMs(completedAttempts)));
        broadcast(line);
        Serial.flush();
        Serial0.flush();
        delay(leshy1::storage::productBootRetryDelayMs(completedAttempts));
        esp_restart();
        return;
    }
    productBootRetryRestarts = 0;
    productBootRetryTimeouts = 0;
}

void emitProductBootRecovery(Stream& reply) {
    char line[1024] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.storage.product_boot_recovery.v1\","
        "\"kind\":\"state\",\"status\":\"%s\",\"enrolled\":%s,"
        "\"expected_fingerprint\":\"%s\",\"observed_fingerprint\":\"%s\","
        "\"fingerprint_matched\":%s,\"mounted_read_only\":%s,"
        "\"read_only_guaranteed\":%s,\"write_enabled\":false,"
        "\"blocked_write_attempts\":%lu,\"product_root\":\"%s\","
        "\"root_exists\":%s,\"permit_status\":\"%s\",\"opened\":%s,"
        "\"catalog_status\":\"%s\",\"catalog_admitted\":%s,"
        "\"generation\":%lu,\"observations\":%u,"
        "\"integrity\":\"%s\",\"attempts\":%u,\"transient_retries\":%u,"
        "\"timeout_restarts\":%u,"
        "\"owned_during\":%lu,\"owned_after\":%lu,"
        "\"cleanup_complete\":%s,\"physical_write_calls\":0}",
        productBootRecovery.status,
        productBootRecovery.enrolled ? "true" : "false",
        productBootRecovery.expectedFingerprint,
        productBootRecovery.observedFingerprint,
        productBootRecovery.fingerprintMatched ? "true" : "false",
        productBootRecovery.mountedReadOnly ? "true" : "false",
        productBootRecovery.readOnlyGuaranteed ? "true" : "false",
        static_cast<unsigned long>(productBootRecovery.blockedWriteAttempts),
        leshy1::storage::kProductSessionStoreRoot,
        productBootRecovery.rootExists ? "true" : "false",
        leshy1::storage::productStoreAccessStatusName(
            productBootRecovery.permitStatus),
        productBootRecovery.opened ? "true" : "false",
        leshy1::apps::library::sessionCatalogStatusName(
            productBootRecovery.catalog.status),
        productBootRecovery.catalogAdmitted ? "true" : "false",
        static_cast<unsigned long>(productBootRecovery.catalog.generation),
        static_cast<unsigned>(productBootRecovery.catalog.observations),
        leshy1::apps::library::sessionIntegrityName(
            productBootRecovery.catalog.integrity),
        static_cast<unsigned>(productBootRecovery.attempts),
        static_cast<unsigned>(productBootRecovery.transientRetries),
        static_cast<unsigned>(productBootRecovery.timeoutRestarts),
        static_cast<unsigned long>(productBootRecovery.ownedDuring),
        static_cast<unsigned long>(productBootRecovery.ownedAfter),
        productBootRecovery.cleanupComplete ? "true" : "false");
    reply.println(line);
}

void triggerProductBootWatchdogTest(Stream& reply) {
    if (!productBootRecovery.catalogAdmitted ||
        appRuntime.activeResources() != 0 ||
        productBootRecovery.ownedAfter != 0) {
        reply.println(
            "{\"schema\":\"leshy.storage.product_boot_watchdog_test.v1\","
            "\"kind\":\"result\",\"status\":\"not_ready\"}");
        return;
    }
    productBootWatchdogTestRtcState = kProductBootWatchdogTestRtcMagic;
    reply.println(
        "{\"schema\":\"leshy.storage.product_boot_watchdog_test.v1\","
        "\"kind\":\"armed\",\"status\":\"ready\","
        "\"filesystem_write_attempted\":false,"
        "\"physical_write_calls\":0}");
    reply.flush();
    delay(50);
    esp_restart();
}

void admitPersistentLibraryCapability(const char* evidence) {
    if (inventory.find("library.persistent_session") == nullptr) {
        inventory.add({"library.persistent_session", CapabilityState::Available,
                       evidence, "validated_session_open"});
    }
    appCatalog.rebuild(inventory);
    renderInteractiveScreen();
}

void emitProductEnrollment(Stream& reply, const char* expectedFingerprint) {
    recoverProductCatalogForFingerprint(expectedFingerprint, false);
    const bool recoveryValid =
        std::strcmp(productBootRecovery.status, "admitted") == 0 &&
        productBootRecovery.catalogAdmitted &&
        productBootRecovery.readOnlyGuaranteed &&
        productBootRecovery.blockedWriteAttempts == 0 &&
        productBootRecovery.cleanupComplete;
    const bool enrollmentSaved = recoveryValid &&
        saveProductFingerprint(expectedFingerprint);
    productBootRecovery.enrolled = enrollmentSaved;
    if (enrollmentSaved) {
        admitPersistentLibraryCapability("explicit_readonly_enrollment");
    }

    char line[1024] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.storage.product_enrollment.v1\","
        "\"kind\":\"result\",\"mode\":\"enroll\",\"status\":\"%s\","
        "\"expected_fingerprint\":\"%s\","
        "\"observed_fingerprint\":\"%s\",\"fingerprint_matched\":%s,"
        "\"mounted_read_only\":%s,\"read_only_guaranteed\":%s,"
        "\"write_enabled\":false,\"blocked_write_attempts\":%lu,"
        "\"catalog_status\":\"%s\",\"catalog_admitted\":%s,"
        "\"generation\":%lu,\"observations\":%u,"
        "\"enrollment_saved\":%s,\"owned_after\":%lu,"
        "\"cleanup_complete\":%s,\"physical_write_calls\":0}",
        enrollmentSaved ? "valid" : "failed", expectedFingerprint,
        productBootRecovery.observedFingerprint,
        productBootRecovery.fingerprintMatched ? "true" : "false",
        productBootRecovery.mountedReadOnly ? "true" : "false",
        productBootRecovery.readOnlyGuaranteed ? "true" : "false",
        static_cast<unsigned long>(productBootRecovery.blockedWriteAttempts),
        leshy1::apps::library::sessionCatalogStatusName(
            productBootRecovery.catalog.status),
        productBootRecovery.catalogAdmitted ? "true" : "false",
        static_cast<unsigned long>(productBootRecovery.catalog.generation),
        static_cast<unsigned>(productBootRecovery.catalog.observations),
        enrollmentSaved ? "true" : "false",
        static_cast<unsigned long>(productBootRecovery.ownedAfter),
        productBootRecovery.cleanupComplete ? "true" : "false");
    reply.println(line);
}

void emitProductUnenrollment(Stream& reply) {
    char enrolledFingerprint[33] = {};
    const bool wasEnrolled = loadProductFingerprint(
        enrolledFingerprint, sizeof(enrolledFingerprint));
    const bool cleared = clearProductFingerprint();
    char line[512] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.storage.product_enrollment.v1\","
        "\"kind\":\"result\",\"mode\":\"unenroll\",\"status\":\"%s\","
        "\"was_enrolled\":%s,\"cleared_fingerprint\":\"%s\","
        "\"nvs_key_removed\":%s,\"sd_accessed\":false,"
        "\"sd_data_untouched\":true,\"active_catalog_unchanged\":true,"
        "\"reboot_required\":true,\"physical_write_calls\":0}",
        cleared ? "valid" : "failed", wasEnrolled ? "true" : "false",
        wasEnrolled ? enrolledFingerprint : "", cleared ? "true" : "false");
    reply.println(line);
}

bool prepareBatchThroughputSession(std::size_t* encodedBytes) {
    if (encodedBytes == nullptr) return false;
    *encodedBytes = 0;
    librarySession.reset();
    if (librarySession.start("batch-wifi-64", 1000) != SessionStatus::Started) {
        return false;
    }
    for (std::size_t index = 0;
         index < SurveySession::kObservationCapacity; ++index) {
        WifiScanRecord record;
        record.bssid = {
            0x02, 0xBA, 0x7C, 0x48,
            static_cast<std::uint8_t>(index >> 8U),
            static_cast<std::uint8_t>(index + 1U),
        };
        record.channel = static_cast<std::uint8_t>(1U + index % 13U);
        record.rssiDbm = static_cast<std::int16_t>(-35 - index % 55U);
        char label[Observation::kLabelCapacity + 1] = {};
        std::snprintf(label, sizeof(label),
                      "batch-ap-%02u-0123456789abcdefghij",
                      static_cast<unsigned>(index));
        record.ssid = label;
        record.ssidLength = std::strlen(label);
        Observation observation;
        if (!leshy1::drivers::wifi::normalizePassiveRecord(
                record, 2000U + static_cast<std::uint64_t>(index),
                &observation) ||
            librarySession.append(observation) != SessionStatus::Appended) {
            return false;
        }
    }
    if (librarySession.stop(3000) != SessionStatus::Stopped) return false;
    return leshy1::storage::encodeObservationSegment(
               librarySession, sessionStoreWorkspace.segment.data(),
               sessionStoreWorkspace.segment.size(), encodedBytes) ==
               leshy1::storage::SessionCodecStatus::Valid &&
           *encodedBytes >=
               leshy1::services::survey::SessionBatchPolicy{}.targetEncodedBytes;
}

bool parseLittleFsParityCommand(const char* command, char* fingerprint,
                                std::size_t fingerprintCapacity, char* runId,
                                std::size_t runIdCapacity) {
    if (command == nullptr || fingerprint == nullptr || runId == nullptr ||
        fingerprintCapacity < 65 || runIdCapacity < 33 ||
        std::strncmp(command, kLittleFsParityPrefix,
                     std::strlen(kLittleFsParityPrefix)) != 0) {
        return false;
    }
    char extra = '\0';
    const int parsed = std::sscanf(
        command + std::strlen(kLittleFsParityPrefix),
        "%64[0-9a-fA-F] %32[A-Za-z0-9_-] %c", fingerprint, runId, &extra);
    return parsed == 2 && std::strlen(fingerprint) == 64 && runId[0] != '\0';
}

bool parseLittleFsResetCommand(const char* command, const char* prefix,
                               char* fingerprint,
                               std::size_t fingerprintCapacity, char* runId,
                               std::size_t runIdCapacity,
                               unsigned* boundaryNumber) {
    if (command == nullptr || prefix == nullptr || fingerprint == nullptr ||
        runId == nullptr || boundaryNumber == nullptr ||
        fingerprintCapacity < 65 || runIdCapacity < 33 ||
        std::strncmp(command, prefix, std::strlen(prefix)) != 0) {
        return false;
    }
    char extra = '\0';
    unsigned parsedBoundary = 0;
    const int parsed = std::sscanf(
        command + std::strlen(prefix),
        "%64[0-9a-fA-F] %32[A-Za-z0-9_-] %u %c", fingerprint, runId,
        &parsedBoundary, &extra);
    if (parsed != 3 || std::strlen(fingerprint) != 64 || runId[0] == '\0' ||
        !leshy1::storage::isSessionStoreBoundary(
            resetBoundaryStage(parsedBoundary))) {
        return false;
    }
    *boundaryNumber = parsedBoundary;
    return true;
}

void emitLittleFsParity(Stream& reply, const char* expectedFingerprint,
                        const char* runId) {
    auto& line = sdPhysicalEvidence.line;
    auto& commitUs = sdPhysicalEvidence.commitUs;
    commitUs.fill(0);
    char observedFingerprint[65] = {};
    const bool idleUi = uiController.isRoot() && !appRuntime.running() &&
        productSurveyControl() == ProductSurveyWorkerControl::Idle;
    DisposableOtaLittleFs filesystem;
    const bool inspected = filesystem.inspect();
    const bool targetSafe = inspected && filesystem.safeInactiveTarget();
    const bool resourcesAcquired = idleUi && targetSafe &&
        resourceBroker.acquire(
            kLittleFsHilOwner,
            leshy1::kernel::runtime::resourceMask(Resource::Storage));
    const std::uint32_t ownedDuring =
        resourceBroker.ownedBy(kLittleFsHilOwner);
    const bool targetHashed = resourcesAcquired &&
        filesystem.hashTarget(observedFingerprint, sizeof(observedFingerprint));
    const bool fingerprintMatched = targetHashed &&
        std::strcmp(expectedFingerprint, observedFingerprint) == 0;
    const std::uint32_t heapFreeBefore = ESP.getFreeHeap();
    const std::uint64_t mountStartedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    const bool mounted = fingerprintMatched &&
        filesystem.formatAndMountWritable();
    const std::uint64_t mountUs = mounted
        ? static_cast<std::uint64_t>(esp_timer_get_time()) - mountStartedUs : 0;
    const std::uint64_t capacityBytes = mounted ? filesystem.totalBytes() : 0;
    const std::uint64_t freeBefore = mounted ? filesystem.freeBytes() : 0;
    const bool scratchPreexisting = mounted && filesystem.exists(
        leshy1::storage::kScratchRoot);

    leshy1::storage::MediaIdentity media;
    media.present = mounted && capacityBytes != 0 && freeBefore <= capacityBytes;
    media.kind = leshy1::storage::MediaKind::LittleFs;
    media.fingerprint = observedFingerprint;
    media.capacityBytes = capacityBytes;
    media.freeBytes = freeBefore;
    leshy1::storage::WriteRequest request;
    request.explicitlyDisposable = true;
    request.expectedFingerprint = expectedFingerprint;
    request.runId = runId;
    request.scratchExists = scratchPreexisting;
    request.requiredBytes = 1024U * 1024U;
    request.reserveBytes = 512U * 1024U;
    const leshy1::storage::WritePermit permit =
        leshy1::storage::authorizeScratchWrite(media, request);

    const char* status = "target_not_inspected";
    if (!idleUi) {
        status = "ui_not_idle";
    } else if (!inspected) {
        status = "target_not_found";
    } else if (!targetSafe) {
        status = "target_not_inactive_ota1";
    } else if (!resourcesAcquired) {
        status = "resources_unavailable";
    } else if (!targetHashed) {
        status = "target_hash_failed";
    } else if (!fingerprintMatched) {
        status = "target_fingerprint_mismatch";
    } else if (!mounted) {
        status = "format_or_mount_failed";
    } else if (!permit.allowed()) {
        status = "permit_rejected";
    } else {
        status = "ready";
    }

    std::size_t fixtureSegmentBytes = 0;
    const bool fixtureReady = std::strcmp(status, "ready") == 0 &&
        prepareBatchThroughputSession(&fixtureSegmentBytes);
    if (std::strcmp(status, "ready") == 0 && !fixtureReady) {
        status = "fixture_prepare_failed";
    }

    std::size_t commitsCompleted = 0;
    std::uint64_t bytesWritten = 0;
    std::uint32_t fileSyncs = 0;
    std::uint32_t directorySyncs = 0;
    const char* ioFailure = "not_started";
    int ioErrno = 0;
    bool prepared = false;
    leshy1::storage::SessionStoreRecoveryResult recoveryBeforeRemount;
    leshy1::storage::SessionStoreRecoveryResult recoveryAfterRemount;
    std::uint64_t freeAfter = freeBefore;
    if (fixtureReady) {
        ArduinoLittleFsSessionStoreIo io(filesystem);
        prepared = io.prepare(permit);
        if (!prepared || !filesystem.exists(permit.scratchPath)) {
            status = "scratch_prepare_failed";
        } else {
            for (std::size_t sample = 0; sample < kSdThroughputSamples;
                 ++sample) {
                const std::uint64_t started =
                    static_cast<std::uint64_t>(esp_timer_get_time());
                const leshy1::storage::SessionStoreCommitResult committed =
                    leshy1::storage::commitNextSession(
                        io, sessionStoreWorkspace, librarySession);
                commitUs[sample] =
                    static_cast<std::uint64_t>(esp_timer_get_time()) - started;
                if (!committed.complete() ||
                    committed.generation != sample + 1U) {
                    status = "commit_failed";
                    break;
                }
                ++commitsCompleted;
            }
            if (commitsCompleted == kSdThroughputSamples) {
                recoveryBeforeRemount = leshy1::storage::recoverSession(
                    io, sessionStoreWorkspace,
                    &sessionStoreWorkspace.validationSession);
                status = recoveryBeforeRemount.valid() &&
                                 recoveryBeforeRemount.generation ==
                                     kSdThroughputSamples &&
                                 recoveryBeforeRemount.observations ==
                                     SurveySession::kObservationCapacity
                    ? "awaiting_remount" : "pre_remount_recovery_failed";
            }
        }
        bytesWritten = io.bytesWritten();
        fileSyncs = io.fileSyncs();
        directorySyncs = io.directorySyncs();
        ioFailure = io.lastFailure();
        ioErrno = io.lastErrno();
        freeAfter = filesystem.freeBytes();
        io.end();
    }

    filesystem.end();
    const bool writableCleanup = filesystem.cleanupComplete();
    bool remountedReadOnly = false;
    bool reopenedReadOnly = false;
    if (std::strcmp(status, "awaiting_remount") == 0) {
        remountedReadOnly = filesystem.mountReadOnly();
        if (remountedReadOnly && filesystem.exists(permit.scratchPath)) {
            ArduinoLittleFsSessionStoreIo readOnlyIo(filesystem);
            reopenedReadOnly = readOnlyIo.openExistingReadOnly(permit);
            if (reopenedReadOnly) {
                recoveryAfterRemount = leshy1::storage::recoverSession(
                    readOnlyIo, sessionStoreWorkspace,
                    &sessionStoreWorkspace.validationSession);
            }
            readOnlyIo.end();
        }
        status = recoveryAfterRemount.valid() &&
                         recoveryAfterRemount.generation ==
                             kSdThroughputSamples &&
                         recoveryAfterRemount.observations ==
                             SurveySession::kObservationCapacity
            ? "valid" : "post_remount_recovery_failed";
    }
    filesystem.end();
    const bool cleanupComplete = writableCleanup && filesystem.cleanupComplete();
    resourceBroker.releaseAll(kLittleFsHilOwner);
    const std::uint32_t ownedAfter = resourceBroker.ownedBy(kLittleFsHilOwner);

    const leshy1::storage::StorageTimingSummary timings =
        leshy1::storage::summarizeStorageTimings(
            commitUs.data(), commitsCompleted);
    const std::uint64_t encodedPayloadBytesPerSecond =
        timings.valid && timings.totalUs != 0
            ? (static_cast<std::uint64_t>(fixtureSegmentBytes) *
               commitsCompleted * 1000000ULL) / timings.totalUs
            : 0;
    const bool storageRateTargetMet =
        encodedPayloadBytesPerSecond >=
            kStorageRequiredEncodedBytesPerSecond;
    const bool valid = std::strcmp(status, "valid") == 0 && targetSafe &&
        fingerprintMatched && mounted && filesystem.formatted() &&
        permit.allowed() && prepared &&
        commitsCompleted == kSdThroughputSamples && timings.valid &&
        bytesWritten != 0 && fileSyncs == kSdThroughputSamples * 3U &&
        directorySyncs == fileSyncs && remountedReadOnly && reopenedReadOnly &&
        storageRateTargetMet && cleanupComplete && ownedAfter == 0;
    if (!valid && std::strcmp(status, "valid") == 0) {
        status = "postcondition_failed";
    }
    const std::uint32_t heapFreeAfter = ESP.getFreeHeap();

    std::snprintf(
        line, sizeof(sdPhysicalEvidence.line),
        "{\"schema\":\"leshy.storage.littlefs.parity.v1\","
        "\"kind\":\"result\",\"status\":\"%s\","
        "\"explicitly_disposable\":true,\"target\":\"ota1\","
        "\"expected_fingerprint\":\"%s\","
        "\"observed_fingerprint\":\"%s\","
        "\"fingerprint_matched\":%s,\"run_id\":\"%s\","
        "\"target_address\":%lu,\"target_size\":%lu,"
        "\"running_address\":%lu,\"boot_address\":%lu,"
        "\"target_inactive\":%s,"
        "\"host_backup_fingerprint_confirmed\":%s,"
        "\"ota1_restore_required\":true,\"ota1_restored\":false,"
        "\"partition_table_modified\":false,"
        "\"product_partition_touched\":false,\"nvs_touched\":false,"
        "\"sd_accessed\":false,\"radio_touched\":false,"
        "\"format_allowed\":true,\"format_performed\":%s,"
        "\"mounted_writable\":%s,\"remounted_read_only\":%s,"
        "\"reopened_read_only\":%s,\"mount_us\":%llu,"
        "\"permit_status\":\"%s\",\"scratch_path\":\"%s\","
        "\"scratch_preexisting_after_format\":%s,"
        "\"byte_limit\":%llu,\"filesystem_capacity_bytes\":%llu,"
        "\"free_before\":%llu,\"free_after\":%llu,"
        "\"bytes_written\":%llu,\"file_syncs\":%lu,"
        "\"directory_syncs\":%lu,"
        "\"file_sync_covers_directory\":true,"
        "\"commit_samples_requested\":%u,"
        "\"commit_samples_completed\":%u,\"commit_total_us\":%llu,"
        "\"commit_min_us\":%llu,\"commit_p50_us\":%llu,"
        "\"commit_p95_us\":%llu,\"commit_p99_us\":%llu,"
        "\"commit_max_us\":%llu,\"fixture_observations\":%u,"
        "\"fixture_segment_bytes\":%u,"
        "\"encoded_payload_bytes_per_second\":%llu,"
        "\"required_encoded_bytes_per_second\":%llu,"
        "\"storage_rate_target_met\":%s,"
        "\"pre_remount_status\":\"%s\","
        "\"pre_remount_generation\":%lu,"
        "\"post_remount_status\":\"%s\","
        "\"post_remount_generation\":%lu,"
        "\"post_remount_observations\":%u,"
        "\"io_failure\":\"%s\",\"io_errno\":%d,"
        "\"owned_during\":%lu,\"owned_after\":%lu,"
        "\"cleanup_complete\":%s,\"heap_free_before\":%lu,"
        "\"heap_free_after\":%lu,\"heap_min_free\":%lu,"
        "\"reset_injection\":false,\"physical_power_cut\":false}",
        status, expectedFingerprint, observedFingerprint,
        fingerprintMatched ? "true" : "false", runId,
        static_cast<unsigned long>(filesystem.targetAddress()),
        static_cast<unsigned long>(filesystem.targetSize()),
        static_cast<unsigned long>(filesystem.runningAddress()),
        static_cast<unsigned long>(filesystem.bootAddress()),
        targetSafe ? "true" : "false",
        fingerprintMatched ? "true" : "false",
        filesystem.formatted() ? "true" : "false",
        mounted ? "true" : "false",
        remountedReadOnly ? "true" : "false",
        reopenedReadOnly ? "true" : "false",
        static_cast<unsigned long long>(mountUs),
        leshy1::storage::permitStatusName(permit.status),
        permit.allowed() ? permit.scratchPath : "",
        scratchPreexisting ? "true" : "false",
        static_cast<unsigned long long>(permit.byteLimit),
        static_cast<unsigned long long>(capacityBytes),
        static_cast<unsigned long long>(freeBefore),
        static_cast<unsigned long long>(freeAfter),
        static_cast<unsigned long long>(bytesWritten),
        static_cast<unsigned long>(fileSyncs),
        static_cast<unsigned long>(directorySyncs),
        static_cast<unsigned>(kSdThroughputSamples),
        static_cast<unsigned>(commitsCompleted),
        static_cast<unsigned long long>(timings.totalUs),
        static_cast<unsigned long long>(timings.minimumUs),
        static_cast<unsigned long long>(timings.p50Us),
        static_cast<unsigned long long>(timings.p95Us),
        static_cast<unsigned long long>(timings.p99Us),
        static_cast<unsigned long long>(timings.maximumUs),
        static_cast<unsigned>(SurveySession::kObservationCapacity),
        static_cast<unsigned>(fixtureSegmentBytes),
        static_cast<unsigned long long>(encodedPayloadBytesPerSecond),
        static_cast<unsigned long long>(
            kStorageRequiredEncodedBytesPerSecond),
        storageRateTargetMet ? "true" : "false",
        leshy1::storage::sessionStoreStatusName(recoveryBeforeRemount.status),
        static_cast<unsigned long>(recoveryBeforeRemount.generation),
        leshy1::storage::sessionStoreStatusName(recoveryAfterRemount.status),
        static_cast<unsigned long>(recoveryAfterRemount.generation),
        static_cast<unsigned>(recoveryAfterRemount.observations),
        ioFailure, ioErrno, static_cast<unsigned long>(ownedDuring),
        static_cast<unsigned long>(ownedAfter),
        cleanupComplete ? "true" : "false",
        static_cast<unsigned long>(heapFreeBefore),
        static_cast<unsigned long>(heapFreeAfter),
        static_cast<unsigned long>(ESP.getMinFreeHeap()));
    reply.println(line);
}

void emitLittleFsResetArm(Stream& reply, const char* expectedFingerprint,
                          const char* runId, unsigned boundaryNumber) {
    auto& line = sdPhysicalEvidence.line;
    littleFsResetRtcState.magic = 0;
    char observedFingerprint[65] = {};
    char scratchPath[leshy1::storage::kScratchPathMax] = {};
    std::snprintf(scratchPath, sizeof(scratchPath), "%s%s",
                  leshy1::storage::kScratchRoot, runId);
    const leshy1::storage::CommitStage boundary =
        resetBoundaryStage(boundaryNumber);
    const bool idleUi = uiController.isRoot() && !appRuntime.running() &&
        productSurveyControl() == ProductSurveyWorkerControl::Idle;
    DisposableOtaLittleFs filesystem;
    const bool inspected = filesystem.inspect();
    const bool targetSafe = inspected && filesystem.safeInactiveTarget();
    const bool resourcesAcquired = idleUi && targetSafe &&
        resourceBroker.acquire(
            kLittleFsHilOwner,
            leshy1::kernel::runtime::resourceMask(Resource::Storage));
    const std::uint32_t ownedDuring =
        resourceBroker.ownedBy(kLittleFsHilOwner);
    const bool targetHashed = resourcesAcquired &&
        filesystem.hashTarget(observedFingerprint, sizeof(observedFingerprint));
    const bool fingerprintMatched = targetHashed &&
        std::strcmp(expectedFingerprint, observedFingerprint) == 0;
    const bool mounted = fingerprintMatched &&
        filesystem.formatAndMountWritable();
    const std::uint64_t capacityBytes = mounted ? filesystem.totalBytes() : 0;
    const std::uint64_t freeBefore = mounted ? filesystem.freeBytes() : 0;
    const bool scratchPreexisting = mounted && filesystem.exists(scratchPath);

    leshy1::storage::MediaIdentity media;
    media.present = mounted && capacityBytes != 0 && freeBefore <= capacityBytes;
    media.kind = leshy1::storage::MediaKind::LittleFs;
    media.fingerprint = observedFingerprint;
    media.capacityBytes = capacityBytes;
    media.freeBytes = freeBefore;
    leshy1::storage::WriteRequest request;
    request.explicitlyDisposable = true;
    request.expectedFingerprint = expectedFingerprint;
    request.runId = runId;
    request.scratchExists = scratchPreexisting;
    request.requiredBytes = 1024U * 1024U;
    request.reserveBytes = 512U * 1024U;
    const leshy1::storage::WritePermit permit =
        leshy1::storage::authorizeScratchWrite(media, request);

    const char* status = "target_not_inspected";
    if (!leshy1::storage::isSessionStoreBoundary(boundary)) {
        status = "invalid_boundary";
    } else if (!idleUi) {
        status = "ui_not_idle";
    } else if (!inspected) {
        status = "target_not_found";
    } else if (!targetSafe) {
        status = "target_not_inactive_ota1";
    } else if (!resourcesAcquired) {
        status = "resources_unavailable";
    } else if (!targetHashed) {
        status = "target_hash_failed";
    } else if (!fingerprintMatched) {
        status = "target_fingerprint_mismatch";
    } else if (!mounted) {
        status = "format_or_mount_failed";
    } else if (!permit.allowed()) {
        status = "permit_rejected";
    } else {
        status = "ready";
    }

    leshy1::storage::SessionStoreCommitResult initialCommit;
    leshy1::storage::SessionStoreRecoveryResult initialRecovery;
    StoredGenerationEvidence priorEvidence;
    bool fixtureReady = false;
    bool prepared = false;
    bool scratchCreated = false;
    bool priorUnchanged = false;
    bool continuityArmed = false;
    std::uint64_t bytesWritten = 0;
    std::uint32_t fileSyncs = 0;
    std::uint32_t directorySyncs = 0;
    const char* ioFailure = "not_started";
    int ioErrno = 0;
    if (std::strcmp(status, "ready") == 0) {
        fixtureReady = prepareLittleFsResetFixture();
        if (!fixtureReady) status = "fixture_prepare_failed";
    }
    if (fixtureReady) {
        ArduinoLittleFsSessionStoreIo io(filesystem);
        prepared = io.prepare(permit);
        scratchCreated = prepared && filesystem.exists(permit.scratchPath);
        if (!prepared || !scratchCreated) {
            status = "scratch_prepare_failed";
        } else {
            initialCommit = leshy1::storage::commitNextSession(
                io, sessionStoreWorkspace, littleFsResetSession);
            initialRecovery = leshy1::storage::recoverSession(
                io, sessionStoreWorkspace,
                &sessionStoreWorkspace.validationSession);
            priorUnchanged = initialCommit.complete() &&
                initialCommit.generation == 1 && initialRecovery.valid() &&
                initialRecovery.generation == 1 &&
                initialRecovery.observations == 3 &&
                inspectStoredGeneration(
                    io, sessionStoreWorkspace, littleFsResetSession, 1,
                    &priorEvidence);
            if (!priorUnchanged) {
                status = "initial_generation_failed";
            } else {
                continuityArmed = armLittleFsResetContinuity(
                    expectedFingerprint, runId, boundaryNumber);
                if (!continuityArmed) {
                    status = "continuity_arm_failed";
                } else {
                    std::snprintf(
                        line, sizeof(sdPhysicalEvidence.line),
                        "{\"schema\":\"leshy.storage.littlefs.reset.v1\","
                        "\"kind\":\"armed\",\"status\":\"ready\","
                        "\"run_id\":\"%s\",\"boundary\":%u,"
                        "\"boundary_name\":\"%s\","
                        "\"expected_recovery\":\"%s\","
                        "\"expected_fingerprint\":\"%s\","
                        "\"observed_fingerprint\":\"%s\","
                        "\"fingerprint_matched\":true,"
                        "\"target\":\"ota1\",\"target_address\":%lu,"
                        "\"target_size\":%lu,\"target_inactive\":true,"
                        "\"scratch_path\":\"%s\","
                        "\"initial_generation\":1,"
                        "\"initial_observations\":3,"
                        "\"prior_segment_crc32c\":%lu,"
                        "\"prior_manifest_crc32c\":%lu,"
                        "\"continuity_armed\":true,"
                        "\"format_performed\":true,"
                        "\"writes_bounded_to_scratch\":true,"
                        "\"ota1_restore_required\":true,"
                        "\"product_partition_touched\":false,"
                        "\"sd_accessed\":false,\"nvs_touched\":false,"
                        "\"radio_touched\":false,"
                        "\"reset_injection\":true,"
                        "\"physical_power_cut\":false}",
                        runId, boundaryNumber,
                        leshy1::storage::sessionStoreBoundaryName(boundary),
                        resetExpectedRecovery(boundaryNumber),
                        expectedFingerprint, observedFingerprint,
                        static_cast<unsigned long>(filesystem.targetAddress()),
                        static_cast<unsigned long>(filesystem.targetSize()),
                        permit.scratchPath,
                        static_cast<unsigned long>(
                            priorEvidence.observedSegmentCrc),
                        static_cast<unsigned long>(
                            priorEvidence.observedManifestCrc));
                    reply.println(line);
                    reply.flush();
                    ResetBoundaryHookContext hookContext{
                        &reply, runId, boundaryNumber};
                    leshy1::storage::SessionStoreBoundaryIo injecting(
                        io, boundary, restartAtLittleFsSessionStoreBoundary,
                        &hookContext);
                    static_cast<void>(leshy1::storage::commitNextSession(
                        injecting, sessionStoreWorkspace,
                        littleFsResetSession));
                    status = "reset_not_triggered";
                }
            }
        }
        bytesWritten = io.bytesWritten();
        fileSyncs = io.fileSyncs();
        directorySyncs = io.directorySyncs();
        ioFailure = io.lastFailure();
        ioErrno = io.lastErrno();
        io.end();
    }

    filesystem.end();
    resourceBroker.releaseAll(kLittleFsHilOwner);
    const std::uint32_t ownedAfter = resourceBroker.ownedBy(kLittleFsHilOwner);
    const bool cleanupComplete = filesystem.cleanupComplete() && ownedAfter == 0;
    if (std::strcmp(status, "reset_not_triggered") == 0) {
        littleFsResetRtcState.magic = 0;
    }
    std::snprintf(
        line, sizeof(sdPhysicalEvidence.line),
        "{\"schema\":\"leshy.storage.littlefs.reset.v1\","
        "\"kind\":\"result\",\"mode\":\"arm\",\"status\":\"%s\","
        "\"run_id\":\"%s\",\"boundary\":%u,\"boundary_name\":\"%s\","
        "\"expected_fingerprint\":\"%s\","
        "\"observed_fingerprint\":\"%s\","
        "\"fingerprint_matched\":%s,\"target_inactive\":%s,"
        "\"format_performed\":%s,\"permit_status\":\"%s\","
        "\"scratch_preexisting\":%s,\"scratch_created\":%s,"
        "\"fixture_ready\":%s,\"prior_unchanged\":%s,"
        "\"continuity_armed\":%s,\"bytes_written\":%llu,"
        "\"file_syncs\":%lu,\"directory_syncs\":%lu,"
        "\"io_failure\":\"%s\",\"io_errno\":%d,"
        "\"owned_during\":%lu,\"owned_after\":%lu,"
        "\"cleanup_complete\":%s,\"ota1_restore_required\":true,"
        "\"product_partition_touched\":false,\"sd_accessed\":false,"
        "\"nvs_touched\":false,\"radio_touched\":false,"
        "\"reset_injection\":true,\"physical_power_cut\":false}",
        status, runId, boundaryNumber,
        leshy1::storage::sessionStoreBoundaryName(boundary),
        expectedFingerprint, observedFingerprint,
        fingerprintMatched ? "true" : "false",
        targetSafe ? "true" : "false",
        filesystem.formatted() ? "true" : "false",
        leshy1::storage::permitStatusName(permit.status),
        scratchPreexisting ? "true" : "false",
        scratchCreated ? "true" : "false",
        fixtureReady ? "true" : "false",
        priorUnchanged ? "true" : "false",
        continuityArmed ? "true" : "false",
        static_cast<unsigned long long>(bytesWritten),
        static_cast<unsigned long>(fileSyncs),
        static_cast<unsigned long>(directorySyncs), ioFailure, ioErrno,
        static_cast<unsigned long>(ownedDuring),
        static_cast<unsigned long>(ownedAfter),
        cleanupComplete ? "true" : "false");
    reply.println(line);
}

void emitLittleFsResetRecovery(Stream& reply,
                               const char* expectedFingerprint,
                               const char* runId,
                               unsigned boundaryNumber) {
    auto& line = sdPhysicalEvidence.line;
    const leshy1::storage::CommitStage boundary =
        resetBoundaryStage(boundaryNumber);
    const esp_reset_reason_t resetReason = esp_reset_reason();
    const bool softwareReset = resetReason == ESP_RST_SW;
    const bool continuityValid = littleFsResetContinuityValid(
        expectedFingerprint, runId, boundaryNumber);
    const bool idleUi = uiController.isRoot() && !appRuntime.running() &&
        productSurveyControl() == ProductSurveyWorkerControl::Idle;
    DisposableOtaLittleFs filesystem;
    const bool inspected = filesystem.inspect();
    const bool targetSafe = inspected && filesystem.safeInactiveTarget();
    const bool resourcesAcquired = idleUi && targetSafe && softwareReset &&
        continuityValid && resourceBroker.acquire(
            kLittleFsHilOwner,
            leshy1::kernel::runtime::resourceMask(Resource::Storage));
    const std::uint32_t ownedDuring =
        resourceBroker.ownedBy(kLittleFsHilOwner);
    const bool mounted = resourcesAcquired && filesystem.mountReadOnly();
    const std::uint64_t capacityBytes = mounted ? filesystem.totalBytes() : 0;
    const std::uint64_t freeBytes = mounted ? filesystem.freeBytes() : 0;
    char scratchPath[leshy1::storage::kScratchPathMax] = {};
    std::snprintf(scratchPath, sizeof(scratchPath), "%s%s",
                  leshy1::storage::kScratchRoot, runId);
    const bool scratchExists = mounted && filesystem.exists(scratchPath);

    leshy1::storage::MediaIdentity media;
    media.present = mounted && capacityBytes != 0 && freeBytes <= capacityBytes;
    media.kind = leshy1::storage::MediaKind::LittleFs;
    media.fingerprint = expectedFingerprint;
    media.capacityBytes = capacityBytes;
    media.freeBytes = freeBytes;
    leshy1::storage::ExistingScratchReadRequest request;
    request.explicitlySelected = true;
    request.expectedFingerprint = expectedFingerprint;
    request.runId = runId;
    request.scratchExists = scratchExists;
    const leshy1::storage::ReadPermit permit =
        leshy1::storage::authorizeExistingScratchRead(media, request);

    const bool fixtureReady = prepareLittleFsResetFixture();
    leshy1::storage::SessionStoreRecoveryResult recovery;
    StoredGenerationEvidence priorEvidence;
    bool openedReadOnly = false;
    bool priorUnchanged = false;
    std::uint64_t bytesWritten = 0;
    std::uint32_t fileSyncs = 0;
    std::uint32_t directorySyncs = 0;
    const char* ioFailure = "not_started";
    int ioErrno = 0;
    if (permit.allowed() && fixtureReady) {
        ArduinoLittleFsSessionStoreIo io(filesystem);
        openedReadOnly = io.openExistingReadOnly(permit);
        if (openedReadOnly) {
            priorUnchanged = inspectStoredGeneration(
                io, sessionStoreWorkspace, littleFsResetSession, 1,
                &priorEvidence);
            recovery = leshy1::storage::recoverSession(
                io, sessionStoreWorkspace,
                &sessionStoreWorkspace.validationSession);
        }
        bytesWritten = io.bytesWritten();
        fileSyncs = io.fileSyncs();
        directorySyncs = io.directorySyncs();
        ioFailure = io.lastFailure();
        ioErrno = io.lastErrno();
        io.end();
    }

    filesystem.end();
    resourceBroker.releaseAll(kLittleFsHilOwner);
    const std::uint32_t ownedAfter = resourceBroker.ownedBy(kLittleFsHilOwner);
    const bool cleanupComplete = filesystem.cleanupComplete() && ownedAfter == 0;
    const bool generationAllowed = recovery.valid() &&
        resetRecoveredGenerationAllowed(boundaryNumber, recovery.generation);
    const bool valid = leshy1::storage::isSessionStoreBoundary(boundary) &&
        softwareReset && continuityValid && idleUi && targetSafe && mounted &&
        permit.allowed() && fixtureReady && openedReadOnly &&
        generationAllowed && recovery.observations == 3 && priorUnchanged &&
        bytesWritten == 0 && fileSyncs == 0 && directorySyncs == 0 &&
        cleanupComplete;

    std::snprintf(
        line, sizeof(sdPhysicalEvidence.line),
        "{\"schema\":\"leshy.storage.littlefs.reset.v1\","
        "\"kind\":\"result\",\"mode\":\"recovery\","
        "\"status\":\"%s\",\"run_id\":\"%s\",\"boundary\":%u,"
        "\"boundary_name\":\"%s\",\"expected_recovery\":\"%s\","
        "\"reset_reason_code\":%u,\"software_reset\":%s,"
        "\"continuity_valid\":%s,\"target\":\"ota1\","
        "\"target_address\":%lu,\"target_size\":%lu,"
        "\"target_inactive\":%s,\"read_permit_status\":\"%s\","
        "\"scratch_path\":\"%s\",\"scratch_exists\":%s,"
        "\"mounted_read_only\":%s,\"opened_read_only\":%s,"
        "\"session_store_io_writable\":false,"
        "\"recovery_status\":\"%s\",\"recovered_generation\":%lu,"
        "\"generation_allowed\":%s,\"reopened_observations\":%u,"
        "\"a_status\":%u,\"b_status\":%u,\"prior_unchanged\":%s,"
        "\"prior_segment_crc32c\":%lu,"
        "\"prior_manifest_crc32c\":%lu,"
        "\"bytes_written\":%llu,\"file_syncs\":%lu,"
        "\"directory_syncs\":%lu,\"io_failure\":\"%s\","
        "\"io_errno\":%d,\"owned_during\":%lu,\"owned_after\":%lu,"
        "\"cleanup_complete\":%s,\"mount_on_boot\":false,"
        "\"format_allowed\":false,\"existing_paths_deleted\":false,"
        "\"ota1_restore_required\":true,"
        "\"product_partition_touched\":false,\"sd_accessed\":false,"
        "\"nvs_touched\":false,\"radio_touched\":false,"
        "\"reset_injection\":true,\"physical_power_cut\":false}",
        valid ? "valid" : "failed", runId, boundaryNumber,
        leshy1::storage::sessionStoreBoundaryName(boundary),
        resetExpectedRecovery(boundaryNumber),
        static_cast<unsigned>(resetReason), softwareReset ? "true" : "false",
        continuityValid ? "true" : "false",
        static_cast<unsigned long>(filesystem.targetAddress()),
        static_cast<unsigned long>(filesystem.targetSize()),
        targetSafe ? "true" : "false",
        leshy1::storage::readPermitStatusName(permit.status),
        permit.allowed() ? permit.scratchPath : scratchPath,
        scratchExists ? "true" : "false", mounted ? "true" : "false",
        openedReadOnly ? "true" : "false",
        leshy1::storage::sessionStoreStatusName(recovery.status),
        static_cast<unsigned long>(recovery.generation),
        generationAllowed ? "true" : "false",
        static_cast<unsigned>(recovery.observations),
        static_cast<unsigned>(recovery.aStatus),
        static_cast<unsigned>(recovery.bStatus),
        priorUnchanged ? "true" : "false",
        static_cast<unsigned long>(priorEvidence.observedSegmentCrc),
        static_cast<unsigned long>(priorEvidence.observedManifestCrc),
        static_cast<unsigned long long>(bytesWritten),
        static_cast<unsigned long>(fileSyncs),
        static_cast<unsigned long>(directorySyncs), ioFailure, ioErrno,
        static_cast<unsigned long>(ownedDuring),
        static_cast<unsigned long>(ownedAfter),
        cleanupComplete ? "true" : "false");
    reply.println(line);
}

void broadcast(const char* line) {
    Serial.println(line);
    Serial0.println(line);
}

void emitMetrics() {
    char line[768] = {};
    bootMetrics.heapFree = ESP.getFreeHeap();
    bootMetrics.heapMinimum = ESP.getMinFreeHeap();
    if (leshy1::services::diagnostics::formatBootMetrics(bootMetrics, line, sizeof(line))) {
        broadcast(line);
    }
}

void emitInventory() {
    char line[384] = {};
    for (std::size_t i = 0; i < inventory.size(); ++i) {
        const CapabilityRecord* record = inventory.get(i);
        if (record != nullptr &&
            leshy1::services::diagnostics::formatCapability(*record, line, sizeof(line))) {
            broadcast(line);
        }
    }
}

void emitSafeOutputs(Stream& reply) {
    const bool buzzerInactive = BoardSafeOutputs::buzzerHeldInactive();
    const bool radioCeInactive =
        BoardSafeOutputs::radioTransmitPathsHeldInactive();
    char line[512] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.hardware.safe-outputs.v1\",\"kind\":\"state\","
        "\"buzzer_pin\":%d,\"buzzer_active_level\":\"high\","
        "\"buzzer_mode\":\"output\",\"buzzer_level\":\"%s\","
        "\"buzzer_inactive\":%s,\"nrf_ce_inactive\":%s,"
        "\"software_quiesce_complete\":%s,"
        "\"physical_rail_kill_available\":false,"
        "\"cc1101_hard_kill_available\":false}",
        BoardProfile::kBuzzerPin, buzzerInactive ? "low" : "high",
        buzzerInactive ? "true" : "false",
        radioCeInactive ? "true" : "false",
        buzzerInactive && radioCeInactive ? "true" : "false");
    reply.println(line);
}

void emitSafetyState(Stream& reply) {
    const bool watchdogArmed = runtimeSafetyWatchdogReady &&
        __atomic_load_n(&runtimeSafetyWatchdogArmed, __ATOMIC_ACQUIRE) != 0;
    char line[1024] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.safety.v1\",\"kind\":\"state\","
        "\"state\":\"%s\",\"reason\":\"%s\",\"armed\":%s,"
        "\"latched\":%s,\"clear_pending\":%s,"
        "\"watchdog_timeout_ms\":%lu,\"trip_count\":%lu,"
        "\"emergency_quiesce_count\":%lu,\"reset_reason_code\":%lu,"
        "\"buzzer_inactive\":%s,\"nrf_ce_inactive\":%s,"
        "\"runtime_owner\":\"%s\",\"lease_mask\":%lu,"
        "\"software_only\":true,\"physical_rail_kill_available\":false,"
        "\"thermal_sensor_available\":false,"
        "\"cc1101_hard_kill_available\":false,"
        "\"automatic_clear\":false}",
        leshy1::kernel::safety::safetyStateName(safetySupervisor.state()),
        leshy1::kernel::safety::safetyReasonName(safetySupervisor.reason()),
        watchdogArmed ? "true" : "false",
        safetySupervisor.latched() ? "true" : "false",
        safetySupervisor.clearPending() ? "true" : "false",
        static_cast<unsigned long>(
            leshy1::storage::kProductBootRecoveryHardwareWatchdogMs),
        static_cast<unsigned long>(safetySupervisor.tripCount()),
        static_cast<unsigned long>(safetySupervisor.quiesceCount()),
        static_cast<unsigned long>(bootMetrics.resetReason),
        BoardSafeOutputs::buzzerHeldInactive() ? "true" : "false",
        BoardSafeOutputs::radioTransmitPathsHeldInactive() ? "true" : "false",
        appRuntime.activeApp(),
        static_cast<unsigned long>(appRuntime.activeResources()));
    reply.println(line);
}

void triggerRuntimeSafetyWatchdogTest(Stream& reply) {
    const bool outputsInactive = BoardSafeOutputs::buzzerHeldInactive() &&
        BoardSafeOutputs::radioTransmitPathsHeldInactive();
    const bool eligible = safetySupervisor.state() == SafetyState::Armed &&
        runtimeSafetyWatchdogReady && outputsInactive &&
        !appRuntime.running() && appRuntime.activeResources() == 0;
    if (!eligible) {
        reply.println(
            "{\"schema\":\"leshy.safety.watchdog_test.v1\","
            "\"kind\":\"error\",\"reason\":\"unsafe_precondition\"}");
        return;
    }
    reply.println(
        "{\"schema\":\"leshy.safety.watchdog_test.v1\","
        "\"kind\":\"armed\",\"status\":\"ready\","
        "\"watchdog_timeout_ms\":5000,\"outputs_inactive\":true,"
        "\"filesystem_write_attempted\":false,"
        "\"physical_write_calls\":0}");
    reply.flush();
    // Deliberately stop feeding the loop task. The independent panic Task WDT
    // must take the ISR quiesce path, retain the reason, and reset the MCU.
    for (;;) delay(1000);
}

void restartLatchedSafetyStopForTest(Stream& reply) {
    const bool eligible = safetySupervisor.latched() &&
        !safetySupervisor.clearPending() && !appRuntime.running() &&
        appRuntime.activeResources() == 0;
    if (!eligible) {
        reply.println(
            "{\"schema\":\"leshy.safety.restart_test.v1\","
            "\"kind\":\"error\",\"reason\":\"unsafe_precondition\"}");
        return;
    }
    BoardSafeOutputs::emergencyQuiesce();
    BoardSdSpiTransport::holdRadioTransmitPathsInactive();
    __atomic_store_n(&runtimeSafetyWatchdogArmed, 0, __ATOMIC_RELEASE);
    reply.println(
        "{\"schema\":\"leshy.safety.restart_test.v1\","
        "\"kind\":\"restart\",\"latch_preserved\":true,"
        "\"outputs_inactive\":true,\"filesystem_write_attempted\":false,"
        "\"physical_write_calls\":0}");
    reply.flush();
    Serial.flush();
    Serial0.flush();
    delay(20);
    esp_restart();
    for (;;) {}
}

void clearSafetyStopFromConsole(Stream& reply) {
    if (!safetySupervisor.latched()) {
        reply.println(
            "{\"schema\":\"leshy.safety.v1\",\"kind\":\"error\","
            "\"reason\":\"not_latched\"}");
        return;
    }
    if (!safetySupervisor.clearPending()) safetySupervisor.requestClear();
    reply.println(
        "{\"schema\":\"leshy.safety.v1\",\"kind\":\"clear_confirmed\","
        "\"restart_required\":true}");
    reply.flush();
    clearSafetyStopAndRestart();
}

bool readInputRaw(std::uint8_t* value) {
    if (value == nullptr) return false;
    const std::uint8_t received = Wire.requestFrom(BoardProfile::kPcf8574Address,
                                                   static_cast<std::uint8_t>(1), true);
    if (received != 1 || Wire.available() == 0) return false;
    *value = static_cast<std::uint8_t>(Wire.read());
    return true;
}

bool probeInputAtBoot(std::uint8_t* value, std::uint8_t* attempts) {
    if (value == nullptr || attempts == nullptr) return false;
    *attempts = 0;
    for (std::uint8_t attempt = 1; attempt <= kInputProbeMaxAttempts; ++attempt) {
        *attempts = attempt;
        if (readInputRaw(value)) return true;
        if (attempt < kInputProbeMaxAttempts) delay(kInputProbeRetryDelayMs);
    }
    return false;
}

void pollPhysicalInput(void*) {
    TickType_t lastWake = xTaskGetTickCount();
    for (;;) {
        std::uint8_t current = 0xFF;
        const bool valid = readInputRaw(&current);
        const std::uint32_t now = millis();
        PhysicalInputEvent event;
        portENTER_CRITICAL(&physicalInputMux);
        event.action = physicalButtonInput.sample(valid, current, now);
        event.raw = physicalButtonInput.stableRaw();
        event.atMs = now;
        event.atUs = static_cast<std::uint64_t>(esp_timer_get_time());
        portEXIT_CRITICAL(&physicalInputMux);
        if (event.action != UiAction::Unknown) {
            if (xQueueSend(physicalInputEvents, &event, 0) != pdTRUE) {
                portENTER_CRITICAL(&physicalInputMux);
                ++physicalInputQueueDrops;
                portEXIT_CRITICAL(&physicalInputMux);
            } else {
                const std::uint32_t depth = static_cast<std::uint32_t>(
                    uxQueueMessagesWaiting(physicalInputEvents));
                portENTER_CRITICAL(&physicalInputMux);
                if (depth > physicalInputQueueHighWater) {
                    physicalInputQueueHighWater = depth;
                }
                portEXIT_CRITICAL(&physicalInputMux);
            }
        }
        vTaskDelayUntil(&lastWake,
                        pdMS_TO_TICKS(Pcf8574ButtonInput::kPollPeriodMs));
    }
}

const char* tr(UiTextId id) {
    return leshy1::ui::uiText(languageController.active(), id);
}

enum class ActiveDisplayFont : std::uint8_t {
    None,
    Body,
    Meta,
};

ActiveDisplayFont activeDisplayFont = ActiveDisplayFont::None;

void selectUiFont(UiTextRole role) {
    const ActiveDisplayFont requested = role == UiTextRole::Body
        ? ActiveDisplayFont::Body : ActiveDisplayFont::Meta;
    if (activeDisplayFont == requested) return;
    if (role == UiTextRole::Body) {
        display.setFreeFont(&RobotoCondensedBody);
    } else {
        display.setFreeFont(&RobotoCondensedMeta);
    }
    activeDisplayFont = requested;
}

std::int16_t uiFontAscent(UiTextRole role) {
    return role == UiTextRole::Body ? kRobotoCondensedBodyAscent
                                    : kRobotoCondensedMetaAscent;
}

void setUiCursor(UiTextRole role, std::int16_t x, std::int16_t top) {
    selectUiFont(role);
    display.setCursor(x, top + uiFontAscent(role));
}

enum class NavigationKey : std::uint8_t {
    None,
    Left,
    UpDown,
    RightAndSelect,
};

struct NavigationCell final {
    NavigationKey key = NavigationKey::None;
    UiTextId label = UiTextId::Count;
};

struct NavigationFooter final {
    NavigationCell left{};
    NavigationCell middle{};
    NavigationCell right{};
};

NavigationFooter navigationFooterForCurrentState() {
    const NavigationCell back = {NavigationKey::Left, UiTextId::NavBack};
    const NavigationCell choose = {NavigationKey::UpDown, UiTextId::NavSelect};
    const NavigationCell enter = {NavigationKey::RightAndSelect,
                                  UiTextId::NavEnter};
    if (safetySupervisor.latched()) {
        return safetySupervisor.clearPending()
            ? NavigationFooter{
                  {NavigationKey::Left, UiTextId::NavCancel}, {},
                  {NavigationKey::RightAndSelect, UiTextId::NavConfirm}}
            : NavigationFooter{
                  {}, {},
                  {NavigationKey::RightAndSelect, UiTextId::NavUnlock}};
    }
    if (uiController.isRoot()) return {{}, choose, enter};
    if (uiController.page() == 1) return {back, {}, {}};

    if (uiController.page() == 2) {
        if (bleProductView == BleProductView::DeviceDetail) {
            return {{NavigationKey::Left, UiTextId::NavList}, {}, {}};
        }
        if (bleProductView == BleProductView::Devices) {
            return {back, choose, enter};
        }
        if (wifiProductView == WifiProductView::Menu) {
            return {back, choose, enter};
        }
        if (wifiProductView == WifiProductView::NetworkDetail) {
            return {{NavigationKey::Left, UiTextId::NavList}, {}, {}};
        }
        if (wifiProductView == WifiProductView::DeviceDetail) {
            return {{NavigationKey::Left, UiTextId::NavList}, {},
                    {NavigationKey::RightAndSelect, UiTextId::NavTrack}};
        }
        if (wifiProductView == WifiProductView::DeviceRadar) {
            return {{NavigationKey::Left, UiTextId::NavInfo}, {}, {}};
        }
        if (wifiProductView == WifiProductView::Devices) {
            return {back, choose, enter};
        }
        if (wifiProductView == WifiProductView::Channels) {
            return {back, {}, {}};
        }
        if (wifiProductView == WifiProductView::Capture) {
            const auto state = wifiFrameCapture.stats().state;
            if (state == WifiFrameCaptureState::Idle) {
                return {back, {},
                        {NavigationKey::RightAndSelect, UiTextId::NavStart}};
            }
            if (state == WifiFrameCaptureState::Running) {
                return {{NavigationKey::Left, UiTextId::NavCancel}, {},
                        {NavigationKey::RightAndSelect, UiTextId::NavStop}};
            }
            if (state == WifiFrameCaptureState::Complete &&
                capturePersistState == CapturePersistState::Result) {
                return {back, {},
                        {NavigationKey::RightAndSelect, UiTextId::NavSave}};
            }
            if (state == WifiFrameCaptureState::Complete &&
                capturePersistState == CapturePersistState::Confirm) {
                return {{NavigationKey::Left, UiTextId::NavBack}, {},
                        {NavigationKey::RightAndSelect, UiTextId::NavSave}};
            }
            if (capturePersistState == CapturePersistState::Saving) {
                return {};
            }
            return {back, {}, {}};
        }
        if (rfSpectrumView == RfSpectrumView::SourceMenu) {
            return {back, choose, enter};
        }
        if (rfSpectrumView == RfSpectrumView::SubGhzMenu ||
            rfSpectrumView == RfSpectrumView::SubGhzCaptureBandMenu) {
            return {back, choose, enter};
        }
        if (rfSpectrumView == RfSpectrumView::SubGhzCaptureLive) {
            const auto state = subGhzRawCapture.stats().state;
            if (state == SubGhzRawCaptureState::Waiting ||
                state == SubGhzRawCaptureState::Capturing) {
                return {{NavigationKey::Left, UiTextId::NavCancel}, {}, {}};
            }
            if (state == SubGhzRawCaptureState::Complete) {
                return subGhzCapturePersistState ==
                               CapturePersistState::Result
                    ? NavigationFooter{
                          back, {}, {NavigationKey::RightAndSelect,
                                     UiTextId::NavSave}}
                    : subGhzCapturePersistState ==
                              CapturePersistState::Saving
                          ? NavigationFooter{}
                          : NavigationFooter{
                                back, {},
                                {NavigationKey::RightAndSelect,
                                 UiTextId::NavStart}};
            }
            return {back, {},
                    {NavigationKey::RightAndSelect, UiTextId::NavStart}};
        }
        if (rfSpectrumView == RfSpectrumView::CcBandMenu) {
            return {back, choose, enter};
        }
        if (rfSpectrumView == RfSpectrumView::Live) {
            const bool cc = rfSpectrumKind == RfSpectrumKind::Cc1101;
            const bool fault = cc
                ? cc1101SpectrumController.state() ==
                      Cc1101SpectrumViewState::Fault
                : nrf24SpectrumController.state() ==
                      Nrf24SpectrumViewState::Fault;
            const bool paused = cc
                ? cc1101SpectrumController.state() ==
                      Cc1101SpectrumViewState::Paused
                : nrf24SpectrumController.state() ==
                      Nrf24SpectrumViewState::Paused;
            if (fault) {
                return {back, {}, {}};
            }
            return {back,
                    {NavigationKey::UpDown, UiTextId::NavView},
                    {NavigationKey::RightAndSelect,
                     cc ? (paused ? UiTextId::NavResume
                                  : UiTextId::NavPause)
                        : UiTextId::NavMode}};
        }
        if (productSurveySourceUnavailableVisible()) {
            return {{NavigationKey::Left, UiTextId::NavHome}, {}, {}};
        }
        if (surveyWorkflow.state() == SurveyWorkflowState::Setup) {
            if (surveySourceController.view() == SurveySetupView::Sources) {
                return {back, choose,
                        {NavigationKey::RightAndSelect,
                         UiTextId::NavToggle}};
            }
            if (surveySourceController.scope() != SurveySourceScope::All) {
                return {back, {},
                        {NavigationKey::RightAndSelect,
                         UiTextId::NavStart}};
            }
            return {back, choose,
                    {NavigationKey::RightAndSelect,
                     surveySourceController.selection() < 2
                         ? UiTextId::NavEnter : UiTextId::NavStart}};
        }
        if (surveyWorkflow.state() == SurveyWorkflowState::Running &&
            surveyController.view() == SurveyView::Filter) {
            return {{NavigationKey::Left, UiTextId::NavList}, choose,
                    {NavigationKey::RightAndSelect, UiTextId::NavApply}};
        }
        if (surveyWorkflow.state() == SurveyWorkflowState::Running &&
            surveyController.view() == SurveyView::Detail) {
            return {{NavigationKey::Left, UiTextId::NavList}, {},
                    {NavigationKey::RightAndSelect,
                     surveyWorkflow.simulated() ? UiTextId::NavStop
                                                : UiTextId::NavSave}};
        }
        if (surveyWorkflow.state() == SurveyWorkflowState::Running) {
            return {{NavigationKey::Left, UiTextId::NavCancel}, choose,
                    {NavigationKey::RightAndSelect,
                     surveyController.filterFocused()
                         ? UiTextId::NavFilter : UiTextId::NavDetails}};
        }
        return {{NavigationKey::Left, UiTextId::NavHome}, {}, {}};
    }

    if (uiController.page() == 3) {
        if (libraryController.view() == LibraryView::ExportReady) {
            return {{NavigationKey::Left, UiTextId::NavDetails}, {}, {}};
        }
        if (libraryController.view() == LibraryView::SessionDetail) {
            return {{NavigationKey::Left, UiTextId::NavList}, {},
                    {NavigationKey::RightAndSelect, UiTextId::NavExport}};
        }
        return {back, choose,
                {NavigationKey::RightAndSelect, UiTextId::NavDetails}};
    }

    if (uiController.page() == 4) {
        if (captureView == CaptureView::SourceMenu) {
            return {back, choose, enter};
        }
        if (captureView == CaptureView::Infrared) {
            const auto state = infraredCapture.stats().state;
            if (state == InfraredCaptureState::Idle) {
                return {back, {},
                        {NavigationKey::RightAndSelect, UiTextId::NavStart}};
            }
            if (state == InfraredCaptureState::Waiting ||
                state == InfraredCaptureState::Capturing) {
                return {{NavigationKey::Left, UiTextId::NavCancel}, {}, {}};
            }
            if (state == InfraredCaptureState::Complete &&
                infraredCapturePersistState == CapturePersistState::Result) {
                return {back, {},
                        {NavigationKey::RightAndSelect, UiTextId::NavSave}};
            }
            if (infraredCapturePersistState == CapturePersistState::Saving) {
                return {{}, {}, {}};
            }
            if (state == InfraredCaptureState::Complete) {
                return {back, {},
                        {NavigationKey::RightAndSelect, UiTextId::NavStart}};
            }
            return {back, {},
                    {NavigationKey::RightAndSelect, UiTextId::NavStart}};
        }
        const auto state = wifiFrameCapture.stats().state;
        if (state == WifiFrameCaptureState::Idle) {
            return {back, {},
                    {NavigationKey::RightAndSelect, UiTextId::NavStart}};
        }
        if (state == WifiFrameCaptureState::Running) {
            return {{NavigationKey::Left, UiTextId::NavCancel}, {},
                    {NavigationKey::RightAndSelect, UiTextId::NavStop}};
        }
        if (state == WifiFrameCaptureState::Complete &&
            capturePersistState == CapturePersistState::Result) {
            return {back, {},
                    {NavigationKey::RightAndSelect, UiTextId::NavSave}};
        }
        if (state == WifiFrameCaptureState::Complete &&
            capturePersistState == CapturePersistState::Confirm) {
            return {{NavigationKey::Left, UiTextId::NavBack}, {},
                    {NavigationKey::RightAndSelect, UiTextId::NavSave}};
        }
        return {back, {}, {}};
    }

    if (uiController.page() == 5) {
        return {back, choose,
                {NavigationKey::RightAndSelect, UiTextId::NavApply}};
    }

    if (uiController.page() == 6) {
        if (selfTestController.view() == SelfTestView::ModeMenu) {
            return {back, choose, enter};
        }
        if (selfTestController.view() == SelfTestView::Preflight) {
            return {{NavigationKey::Left, UiTextId::NavModes}, {},
                    {NavigationKey::RightAndSelect, UiTextId::NavStart}};
        }
        if (selfTestController.view() == SelfTestView::VisualCheck) {
            return {{NavigationKey::Left, UiTextId::NavCancel}, {},
                    {NavigationKey::RightAndSelect, UiTextId::NavNext}};
        }
        if (selfTestController.view() == SelfTestView::ActiveChecks) {
            return {{NavigationKey::Left, UiTextId::NavCancel}, {}, {}};
        }
        return {{NavigationKey::Left, UiTextId::NavModes}, {}, {}};
    }
    if (uiController.page() == kDevicePage) return {back, choose, enter};
    return {back, {}, {}};
}

constexpr std::int16_t kNavigationInset = 6;
constexpr std::int16_t kNavigationGap = 4;
constexpr std::int16_t kNavigationArrowWidth = 9;
constexpr std::int16_t kNavigationUpDownWidth = 23;

std::int16_t navigationKeyWidth(NavigationKey key) {
    if (key == NavigationKey::Left) return kNavigationArrowWidth;
    if (key == NavigationKey::UpDown) return kNavigationUpDownWidth;
    if (key == NavigationKey::RightAndSelect) {
        selectUiFont(UiTextRole::Meta);
        return display.textWidth(tr(UiTextId::NavOk)) + 3 +
               kNavigationArrowWidth;
    }
    return 0;
}

void renderNavigationKey(NavigationKey key, std::int16_t x,
                         std::int16_t centerY, std::int16_t textTop) {
    if (key == NavigationKey::Left) {
        display.fillTriangle(x, centerY, x + 8, centerY - 5,
                             x + 8, centerY + 5, Palette::TextSecondary);
    } else if (key == NavigationKey::UpDown) {
        display.fillTriangle(x, centerY + 2, x + 5, centerY - 4,
                             x + 10, centerY + 2,
                             Palette::TextSecondary);
        display.fillTriangle(x + 12, centerY - 2, x + 17, centerY + 4,
                             x + 22, centerY - 2,
                             Palette::TextSecondary);
    } else if (key == NavigationKey::RightAndSelect) {
        display.setTextColor(Palette::TextSecondary, Palette::Canvas);
        selectUiFont(UiTextRole::Meta);
        const char* ok = tr(UiTextId::NavOk);
        const std::int16_t okWidth = display.textWidth(ok);
        setUiCursor(UiTextRole::Meta, x, textTop);
        display.print(ok);
        const std::int16_t arrowX = x + okWidth + 3;
        display.fillTriangle(arrowX, centerY - 5, arrowX, centerY + 5,
                             arrowX + 8, centerY,
                             Palette::TextSecondary);
    }
}

void renderNavigationCell(std::uint8_t index, NavigationCell cell) {
    if (cell.key == NavigationKey::None || cell.label == UiTextId::Count) return;
    const Rect bounds = Components::navigationCell(index);
    const char* label = tr(cell.label);
    selectUiFont(UiTextRole::Meta);
    const std::int16_t labelWidth = display.textWidth(label);
    const std::int16_t keyWidth = navigationKeyWidth(cell.key);
    const std::int16_t totalWidth = keyWidth + kNavigationGap + labelWidth;
    const std::int16_t textHeight = kRobotoCondensedMetaAscent +
                                    kRobotoCondensedMetaDescent;
    const std::int16_t textTop = bounds.y + (bounds.height - textHeight) / 2;
    const std::int16_t centerY = bounds.y + bounds.height / 2;
    std::int16_t x = bounds.x + (bounds.width - totalWidth) / 2;
    if (index == 0) x = bounds.x + kNavigationInset;
    if (index == 2) {
        x = bounds.x + bounds.width - kNavigationInset - totalWidth;
    }
    display.setTextColor(Palette::TextSecondary, Palette::Canvas);
    if (cell.key == NavigationKey::RightAndSelect) {
        setUiCursor(UiTextRole::Meta, x, textTop);
        display.print(label);
        renderNavigationKey(cell.key, x + labelWidth + kNavigationGap,
                            centerY, textTop);
    } else {
        renderNavigationKey(cell.key, x, centerY, textTop);
        setUiCursor(UiTextRole::Meta, x + keyWidth + kNavigationGap,
                    textTop);
        display.print(label);
    }
}

void renderNavigationFooter() {
    const Rect hint = Components::footerHint();
    display.fillRect(hint.x, hint.y, hint.width, hint.height, Palette::Canvas);
    const NavigationFooter footer = navigationFooterForCurrentState();
    renderNavigationCell(0, footer.left);
    renderNavigationCell(1, footer.middle);
    renderNavigationCell(2, footer.right);
}

std::uint16_t toneColor(Tone tone) {
    switch (tone) {
        case Tone::Focus:
            return Palette::Focus;
        case Tone::Positive:
            return Palette::Positive;
        case Tone::Warning:
            return Palette::Warning;
        case Tone::Danger:
            return Palette::Danger;
        case Tone::Muted:
            return Palette::TextMuted;
        case Tone::Neutral:
        default:
            return Palette::TextSecondary;
    }
}

const char* headerReceiverStatus() {
    if (nrf24SpectrumController.state() ==
        Nrf24SpectrumViewState::Running) {
        static char nrfReceivers[12] = {};
        std::size_t at = 0;
        at += static_cast<std::size_t>(std::snprintf(
            nrfReceivers, sizeof(nrfReceivers), "RX N"));
        bool first = true;
        for (std::uint8_t slot = 0; slot < 3 && at + 2 < sizeof(nrfReceivers);
             ++slot) {
            if ((nrf24SpectrumReport.activeSlotMask & (1U << slot)) == 0) {
                continue;
            }
            at += static_cast<std::size_t>(std::snprintf(
                nrfReceivers + at, sizeof(nrfReceivers) - at,
                first ? "%u" : "+%u", static_cast<unsigned>(slot + 1U)));
            first = false;
        }
        return nrfReceivers;
    }
    if (cc1101SpectrumController.state() ==
        Cc1101SpectrumViewState::Running) {
        return "RX CC";
    }
    if (wifiFrameCapture.stats().state == WifiFrameCaptureState::Running ||
        wifiFrameCapture.deviceMonitorStats().active ||
        wifiFrameCapture.channelMonitorStats().active) {
        return "RX WIFI";
    }
    if (infraredCapture.stats().state == InfraredCaptureState::Waiting ||
        infraredCapture.stats().state == InfraredCaptureState::Capturing) {
        return "RX IR";
    }
    if (productSurveyRuntime.sourceActive) {
        const std::uint8_t wifiMask = leshy1::services::survey::sourceMask(
            RadioKind::Wifi);
        const std::uint8_t bleMask = leshy1::services::survey::sourceMask(
            RadioKind::Ble);
        const bool wifi =
            (productSurveyRuntime.activeSourceMask & wifiMask) != 0;
        const bool ble =
            (productSurveyRuntime.activeSourceMask & bleMask) != 0;
        if (wifi && ble) return "RX W+B";
        if (wifi) return "RX WIFI";
        if (ble) return "RX BLE";
    }
    return "RX --";
}

void renderHeaderStatus() {
    if (safetySupervisor.latched()) {
        constexpr const char* stopped = "STOP";
        selectUiFont(UiTextRole::Meta);
        const std::int16_t x = Layout::ScreenWidth - 6 -
                               display.textWidth(stopped);
        display.setTextColor(Palette::Danger, Palette::Header);
        setUiCursor(UiTextRole::Meta, x, 5);
        display.print(stopped);
        return;
    }
    const char* receiver = headerReceiverStatus();
    constexpr const char* transmitter = "TX --";
    const bool receiving = receiver[3] != '-';

    selectUiFont(UiTextRole::Meta);
    const std::int16_t transmitterWidth = display.textWidth(transmitter);
    const std::int16_t receiverWidth = display.textWidth(receiver);
    const std::int16_t transmitterX =
        Layout::ScreenWidth - 6 - transmitterWidth;
    const std::int16_t receiverX = transmitterX - 6 - receiverWidth;
    display.setTextColor(receiving ? Palette::Positive : Palette::TextMuted,
                         Palette::Header);
    setUiCursor(UiTextRole::Meta, receiverX, 5);
    display.print(receiver);
    display.setTextColor(Palette::TextMuted, Palette::Header);
    setUiCursor(UiTextRole::Meta, transmitterX, 5);
    display.print(transmitter);
}

void formatHomeVersion(char* output, std::size_t capacity) {
    if (output == nullptr || capacity == 0) return;
    std::size_t written = 0;
    if (capacity > 1) output[written++] = 'v';
    const char* source = LESHY1_VERSION;
    while (*source != '\0' && *source != '-' && written + 1 < capacity) {
        output[written++] = *source++;
    }
    output[written] = '\0';
}

void renderHeader(const char* title, bool clearContent) {
    const Rect header = Components::header();
    display.fillRect(header.x, header.y, header.width, header.height,
                     Palette::Header);
    if (clearContent) {
        display.fillRect(0, header.y + header.height, Layout::ScreenWidth,
                         Layout::ScreenHeight - header.height,
                         Palette::Canvas);
    }
    display.setTextColor(Palette::TextPrimary, Palette::Header);
    const bool home = uiController.isRoot() && !safetySupervisor.latched();
    if (home) {
        const char* brand = tr(UiTextId::Brand);
        selectUiFont(UiTextRole::Body);
        const std::int16_t brandWidth = display.textWidth(brand);
        setUiCursor(UiTextRole::Body, 10, 2);
        display.print(brand);
        char version[24] = {};
        formatHomeVersion(version, sizeof(version));
        display.setTextColor(Palette::TextMuted, Palette::Header);
        const std::int16_t versionTop = 2 + kRobotoCondensedBodyAscent -
                                        kRobotoCondensedMetaAscent;
        setUiCursor(UiTextRole::Meta, 10 + brandWidth + 5, versionTop);
        display.print(version);
    } else {
        const Rect titleBounds = Components::title();
        setUiCursor(UiTextRole::Meta, titleBounds.x, titleBounds.y);
        display.print(title);
    }
    renderHeaderStatus();
}

void renderFocusCue(Rect bounds, bool selected) {
    if (!selected) return;
    display.drawRoundRect(bounds.x, bounds.y, bounds.width, bounds.height,
                          Layout::Radius, Palette::Focus);
    const Rect marker = Components::focusMarker(bounds);
    display.fillTriangle(marker.x, marker.y,
                         marker.x, marker.y + marker.height,
                         marker.x + marker.width,
                         marker.y + marker.height / 2,
                         Palette::Focus);
}

constexpr std::int16_t kInteractiveRowTextInset = 12;

std::int16_t menuRowTextTop(Rect bounds) {
    constexpr std::int16_t kLineGap = 1;
    constexpr std::int16_t kTextBlockHeight =
        kRobotoCondensedBodyAscent + kRobotoCondensedBodyDescent +
        kLineGap + kRobotoCondensedMetaAscent + kRobotoCondensedMetaDescent;
    return static_cast<std::int16_t>(
        bounds.y + (bounds.height - kTextBlockHeight) / 2);
}

void renderMenuRow(Rect bounds, const char* label, const char* note,
                   bool selected, bool enabled, Tone noteTone) {
    const std::uint16_t background = selected
        ? (enabled ? Palette::SurfaceFocus : Palette::SurfaceFocusDisabled)
        : Palette::Surface;
    display.fillRoundRect(bounds.x, bounds.y, bounds.width, bounds.height,
                          Layout::Radius, background);
    renderFocusCue(bounds, selected);
    display.setTextColor(selected ? Palette::Focus : Palette::TextSecondary,
                         background);
    const std::int16_t labelTop = menuRowTextTop(bounds);
    setUiCursor(UiTextRole::Body,
                bounds.x + kInteractiveRowTextInset, labelTop);
    display.print(label);
    display.setTextColor(enabled ? toneColor(noteTone) : Palette::TextMuted,
                         background);
    setUiCursor(
        UiTextRole::Meta, bounds.x + kInteractiveRowTextInset,
        labelTop + kRobotoCondensedBodyAscent +
            kRobotoCondensedBodyDescent + 1);
    display.print(note);
}

void renderMetric(std::uint8_t index, const char* text,
                  Tone tone = Tone::Neutral) {
    const Rect bounds = Components::metricRow(index);
    display.setTextColor(toneColor(tone), Palette::Canvas);
    setUiCursor(UiTextRole::Body, bounds.x + 2, bounds.y - 2);
    display.print(text);
}

void renderStateCard(const char* state, const char* detail, Tone tone,
                     std::uint8_t step) {
    const Rect bounds = Components::stateCard();
    display.fillRoundRect(bounds.x, bounds.y, bounds.width, bounds.height,
                          Layout::Radius, Palette::Surface);
    display.drawRoundRect(bounds.x, bounds.y, bounds.width, bounds.height,
                          Layout::Radius, toneColor(tone));
    display.drawRect(bounds.x + 12, bounds.y + 15, 18, 18, toneColor(tone));
    display.setTextColor(toneColor(tone), Palette::Surface);
    setUiCursor(UiTextRole::Body, bounds.x + 40, bounds.y + 10);
    display.print(state);
    display.setTextColor(Palette::TextSecondary, Palette::Surface);
    setUiCursor(UiTextRole::Meta, bounds.x + 16, bounds.y + 50);
    display.print(detail);
    char line[40] = {};
    std::snprintf(line, sizeof(line), tr(UiTextId::VisualStepFormat),
                  static_cast<unsigned>(step + 1U));
    display.setTextColor(Palette::TextMuted, Palette::Surface);
    setUiCursor(UiTextRole::Meta, bounds.x + 16, bounds.y + 78);
    display.print(line);
}

UiTextId homeLabel(const AppMenuItem& item) {
    if (std::strcmp(item.id, "wifi") == 0) return UiTextId::AppWifi;
    if (std::strcmp(item.id, "ble") == 0) return UiTextId::AppBle;
    if (std::strcmp(item.id, "spectrum24") == 0) {
        return UiTextId::AppSpectrum24;
    }
    if (std::strcmp(item.id, "subghz") == 0) return UiTextId::AppSubGhz;
    if (std::strcmp(item.id, "survey") == 0) return UiTextId::AppSurvey;
    if (std::strcmp(item.id, "library") == 0) return UiTextId::AppLibrary;
    if (std::strcmp(item.id, "capture") == 0) return UiTextId::AppCapture;
    if (std::strcmp(item.id, "targets") == 0) return UiTextId::AppTargets;
    if (std::strcmp(item.id, "lab") == 0) return UiTextId::AppLab;
    return UiTextId::AppDevice;
}

UiTextId homeNote(const AppMenuItem& item) {
    if (std::strcmp(item.id, "wifi") == 0) {
        return item.enabled ? UiTextId::NoteWifiReady
                            : UiTextId::NoteSurveyUnavailable;
    }
    if (std::strcmp(item.id, "ble") == 0) {
        return item.enabled ? UiTextId::NoteBleReady
                            : UiTextId::NoteSurveyUnavailable;
    }
    if (std::strcmp(item.id, "spectrum24") == 0) {
        return UiTextId::NoteSpectrum24;
    }
    if (std::strcmp(item.id, "subghz") == 0) {
        return UiTextId::NoteSubGhz;
    }
    if (std::strcmp(item.id, "survey") == 0) {
        if (item.simulated) return UiTextId::NoteSurveySimulated;
        if (!item.enabled) return UiTextId::NoteSurveyUnavailable;
        if (std::strcmp(item.reason, "passive / persistent") == 0) {
            return UiTextId::NoteSurveyPersistent;
        }
    }
    if (std::strcmp(item.id, "library") == 0) {
        if (item.simulated) return UiTextId::NoteLibrarySimulated;
        if (!item.enabled) return UiTextId::NoteLibraryUnavailable;
        return UiTextId::NoteLibraryReady;
    }
    if (std::strcmp(item.id, "capture") == 0) {
        return item.enabled ? UiTextId::NoteCaptureReady
                            : UiTextId::NoteCaptureUnavailable;
    }
    if (std::strcmp(item.id, "targets") == 0) return UiTextId::NoteTargetsPlanned;
    if (std::strcmp(item.id, "lab") == 0) return UiTextId::NoteLabPlanned;
    if (std::strcmp(item.id, "device") == 0) return UiTextId::NoteDevice;
    return UiTextId::Ready;
}

constexpr std::uint8_t kVisibleHomeRows = 4;

std::uint8_t homeFirstVisible(std::uint8_t selection) {
    return selection < kVisibleHomeRows
               ? 0U
               : static_cast<std::uint8_t>(selection -
                                           (kVisibleHomeRows - 1U));
}

void renderHomeRow(std::uint8_t index, std::uint8_t firstVisible) {
    const AppMenuItem* item = appCatalog.get(index);
    if (item == nullptr) return;
    if (index < firstVisible || index >= firstVisible + kVisibleHomeRows) return;
    const Rect bounds = Components::homeRow(
        static_cast<std::uint8_t>(index - firstVisible));
    const bool selected = uiController.selection() == index;
    renderMenuRow(bounds, tr(homeLabel(*item)), tr(homeNote(*item)), selected,
                  item->enabled,
                  item->enabled ? Tone::Positive : Tone::Muted);
}

void renderHome(bool clearContent) {
    renderHeader(tr(UiTextId::HomeTitle), clearContent);
    const std::uint8_t first = homeFirstVisible(uiController.selection());
    const std::size_t end = appCatalog.size() < first + kVisibleHomeRows
                                ? appCatalog.size()
                                : first + kVisibleHomeRows;
    for (std::uint8_t i = first; i < end; ++i) {
        renderHomeRow(i, first);
    }
}

std::uint8_t deviceFirstVisible(std::uint8_t selection) {
    return selection < kVisibleHomeRows
               ? 0U
               : static_cast<std::uint8_t>(selection -
                                           (kVisibleHomeRows - 1U));
}

UiTextId deviceLabel(std::uint8_t index) {
    switch (index) {
        case 0: return UiTextId::DeviceSettings;
        case 1: return UiTextId::AppSelfTest;
        case 2: return UiTextId::AppDiagnostics;
        default: return UiTextId::DeviceAbout;
    }
}

UiTextId deviceNote(std::uint8_t index) {
    switch (index) {
        case 0: return UiTextId::DeviceSettingsNote;
        case 1: return UiTextId::NoteSelfTest;
        case 2: return UiTextId::DeviceDiagnosticsNote;
        default: return UiTextId::DeviceAboutNote;
    }
}

void renderDeviceRow(std::uint8_t index, std::uint8_t firstVisible) {
    if (index < firstVisible ||
        index >= firstVisible + kVisibleHomeRows ||
        index >= kDeviceItemCount) return;
    const Rect bounds = Components::homeRow(
        static_cast<std::uint8_t>(index - firstVisible));
    renderMenuRow(bounds, tr(deviceLabel(index)), tr(deviceNote(index)),
                  deviceSelection == index, true, Tone::Positive);
}

void renderDevicePage(bool clearContent) {
    renderHeader(tr(UiTextId::DeviceTitle), clearContent);
    const std::uint8_t first = deviceFirstVisible(deviceSelection);
    const std::uint8_t end = static_cast<std::uint8_t>(
        kDeviceItemCount < first + kVisibleHomeRows
            ? kDeviceItemCount : first + kVisibleHomeRows);
    for (std::uint8_t index = first; index < end; ++index) {
        renderDeviceRow(index, first);
    }
}

void renderAboutPage(bool clearContent) {
    renderHeader(tr(UiTextId::AboutTitle), clearContent);
    char line[96] = {};
    display.setTextColor(Palette::TextSecondary, Palette::Canvas);
    std::snprintf(line, sizeof(line), tr(UiTextId::AboutVersionFormat),
                  LESHY1_VERSION);
    setUiCursor(UiTextRole::Body, 14, 82);
    display.print(line);
    std::snprintf(line, sizeof(line), tr(UiTextId::AboutProfileFormat),
                  BoardProfile::kId);
    setUiCursor(UiTextRole::Body, 14, 116);
    display.print(line);
    display.setTextColor(Palette::Positive, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 168);
    display.print(tr(UiTextId::AboutOpenSource));
}

void runShieldReceiverSelfTestProbe() {
    shieldReceiverProbeReport = {};
    shieldReceiverProbeReport.profileDeclared = BoardProfile::kRfShieldDeclared;
    shieldReceiverProbeReport.gpsExcludedByProfile = !BoardProfile::kGpsDeclared;
    shieldReceiverProbeReport.pn532ExcludedByProfile = !BoardProfile::kPn532Declared;
    const auto radioSpi = leshy1::kernel::runtime::resourceMask(Resource::RadioSpi);
    if (!resourceBroker.acquire(AppRuntime::kForegroundOwner, radioSpi)) {
        leshy1::drivers::radio::finalizeShieldReceiverProbe(
            &shieldReceiverProbeReport);
        return;
    }
    BoardShieldReceiverProbe probe;
    probe.run(resourceBroker.ownerOf(Resource::RadioSpi) ==
                  AppRuntime::kForegroundOwner,
              &shieldReceiverProbeReport);
    resourceBroker.release(AppRuntime::kForegroundOwner, radioSpi);
    shieldReceiverProbeReport.resourceReleased =
        resourceBroker.ownerOf(Resource::RadioSpi) ==
        leshy1::kernel::runtime::kNoOwner;
}

SelfTestFacts snapshotSelfTestFacts() {
    std::uint32_t inputQueueDrops = 0;
    portENTER_CRITICAL(&physicalInputMux);
    inputQueueDrops = physicalInputQueueDrops;
    portEXIT_CRITICAL(&physicalInputMux);

    const CapabilityRecord* profile = inventory.find("board.profile");
    const CapabilityRecord* persistentSurvey =
        inventory.find("survey.persistent_passive");
    const CapabilityRecord* passiveBle = inventory.find("radio.ble");
    const CapabilityRecord* passiveWifiCapture =
        inventory.find("capture.wifi_passive");
    const CapabilityRecord* persistentLibrary =
        inventory.find("library.persistent_session");
    const CapabilityRecord* persistentWifiCapture =
        inventory.find("capture.wifi_persistent");
    const auto uiOnly = leshy1::kernel::runtime::resourceMask(
        Resource::UiForeground);
    SelfTestFacts facts;
    facts.buildIdentityPresent = std::strlen(runningAppElfSha256) == 64;
    facts.profileMatched = profile != nullptr &&
                           profile->state == CapabilityState::Available;
    facts.displayReady = bootMetrics.displayReadyUs != 0;
    facts.touchFrontendReady = boardTouchInput.ready();
    facts.inputFrontendReady = physicalInputTaskStarted &&
                               bootMetrics.inputDetected;
    facts.inputQueueHealthy = physicalInputEvents != nullptr &&
                              inputQueueDrops == 0;
    facts.buzzerInactive = BoardSafeOutputs::buzzerHeldInactive();
    facts.heapFree = ESP.getFreeHeap();
    facts.heapMinimum = ESP.getMinFreeHeap();
    facts.inputQueueDrops = inputQueueDrops;
    facts.activeResources = appRuntime.activeResources();
    facts.resourceScopeClean = facts.activeResources == uiOnly;
    facts.persistentSurveyReady = persistentSurvey != nullptr &&
        persistentSurvey->state == CapabilityState::Available;
    facts.passiveBleReady = passiveBle != nullptr &&
        passiveBle->state == CapabilityState::Available;
    facts.passiveWifiCaptureReady = passiveWifiCapture != nullptr &&
        passiveWifiCapture->state == CapabilityState::Available;
    facts.enrolledStorageReady = productBootRecovery.enrolled &&
        productBootRecovery.fingerprintMatched &&
        productBootRecovery.catalogAdmitted &&
        productBootRecovery.readOnlyGuaranteed &&
        productBootRecovery.cleanupComplete &&
        productBootRecovery.ownedAfter == 0;
    facts.persistentLibraryReady = persistentLibrary != nullptr &&
        persistentLibrary->state == CapabilityState::Available;
    facts.persistentWifiCaptureReady = persistentWifiCapture != nullptr &&
        persistentWifiCapture->state == CapabilityState::Available;
    facts.gpsDeclared = BoardProfile::kGpsDeclared;
    facts.pn532Declared = BoardProfile::kPn532Declared;
    facts.irDeclared = BoardProfile::kIrDeclared;
    facts.shieldReceiversApplicable = BoardProfile::kRfShieldDeclared;
    facts.shieldReceiverProbeComplete =
        shieldReceiverProbeReport.status == ShieldReceiverProbeStatus::Pass ||
        shieldReceiverProbeReport.status == ShieldReceiverProbeStatus::Partial ||
        shieldReceiverProbeReport.status == ShieldReceiverProbeStatus::Failed;
    facts.shieldReceiverProbePassed =
        shieldReceiverProbeReport.status == ShieldReceiverProbeStatus::Pass &&
        shieldReceiverProbeReport.resourceReleased &&
        shieldReceiverProbeReport.cleanupComplete;
    facts.nrf24SpectrumExerciseComplete = fullGuidedRfState.nrf24Complete;
    facts.nrf24SpectrumExercisePassed = fullGuidedRfState.nrf24Passed;
    facts.cc1101SpectrumExerciseComplete = fullGuidedRfState.cc1101Complete;
    facts.cc1101SpectrumExercisePassed = fullGuidedRfState.cc1101Passed;
    facts.persistentRecoveryAuditComplete =
        fullGuidedArtifactState.recoveryComplete;
    facts.persistentRecoveryAuditPassed =
        fullGuidedArtifactState.recoveryPassed;
    facts.libraryExportAuditComplete = fullGuidedArtifactState.libraryComplete;
    facts.libraryExportAuditPassed = fullGuidedArtifactState.libraryPassed;
    facts.capturePcapAuditComplete = fullGuidedArtifactState.captureComplete;
    facts.capturePcapAuditApplicable =
        fullGuidedArtifactState.captureApplicable;
    facts.capturePcapAuditPassed = fullGuidedArtifactState.capturePassed;
    facts.disposableCommitComplete =
        fullGuidedArtifactState.disposableCommitComplete;
    facts.disposableCommitPassed =
        fullGuidedArtifactState.disposableCommitPassed;
    facts.disposableRemountComplete =
        fullGuidedArtifactState.disposableRemountComplete;
    facts.disposableRemountPassed =
        fullGuidedArtifactState.disposableRemountPassed;
    facts.disposableExportComplete =
        fullGuidedArtifactState.disposableExportComplete;
    facts.disposableExportPassed =
        fullGuidedArtifactState.disposableExportPassed;
    facts.disposableCleanupComplete =
        fullGuidedArtifactState.disposableCleanupComplete;
    facts.disposableCleanupPassed =
        fullGuidedArtifactState.disposableCleanupPassed &&
        fullGuidedArtifactState.productVerifyComplete &&
        fullGuidedArtifactState.productVerifyPassed;
    facts.disposableStorageWriteCalls =
        fullGuidedArtifactState.disposableStorageWriteCalls;
    facts.disposableStorageWriteBytes =
        fullGuidedArtifactState.disposableStorageWriteBytes;
    return facts;
}

void renderLanguageRow(std::uint8_t index) {
    const UiTextId labels[2] = {UiTextId::LanguageEnglish,
                                UiTextId::LanguageRussian};
    const UiTextId notes[2] = {UiTextId::LanguageEnglishNote,
                               UiTextId::LanguageRussianNote};
    if (index >= 2) return;
    renderMenuRow(Components::choiceRow(index), tr(labels[index]),
                  tr(notes[index]), languageController.selection() == index,
                  true,
                  languageController.active() ==
                          (index == 0 ? UiLanguage::English
                                      : UiLanguage::Russian)
                      ? Tone::Positive
                      : Tone::Neutral);
}

void renderLanguagePage(bool clearContent) {
    renderHeader(tr(UiTextId::LanguageTitle), clearContent);
    for (std::uint8_t index = 0; index < 2; ++index) {
        renderLanguageRow(index);
    }
    display.setTextColor(Palette::TextMuted, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 207);
    display.print(tr(UiTextId::LanguagePersisted));
}

void renderWifiCapturePage(bool clearContent) {
    const auto stats = wifiFrameCapture.stats();
    const bool productRoute = uiController.page() == 2 &&
        wifiProductView == WifiProductView::Capture;
    const auto renderPageHeader = [&](UiTextId stateTitle) {
        renderHeader(tr(productRoute ? UiTextId::WifiCaptureTitle : stateTitle),
                     clearContent);
    };
    char line[64] = {};
    if (stats.state == WifiFrameCaptureState::Idle) {
        renderPageHeader(UiTextId::CaptureSetup);
        renderMetric(0, tr(UiTextId::CaptureWifiPurpose), Tone::Positive);
        renderMetric(1, tr(UiTextId::CaptureDurationUser));
        renderMetric(2, tr(UiTextId::CaptureAutoChannelsUser));
        return;
    }

    if (stats.state == WifiFrameCaptureState::Running) {
        renderPageHeader(UiTextId::CaptureRunning);
    } else if (stats.state == WifiFrameCaptureState::Complete) {
        const UiTextId title =
            capturePersistState == CapturePersistState::Confirm
                ? UiTextId::CaptureSaveConfirm
                : capturePersistState == CapturePersistState::Saving
                      ? UiTextId::CaptureSaving
                      : capturePersistState == CapturePersistState::Saved
                            ? UiTextId::CaptureSaved
                            : capturePersistState == CapturePersistState::Failed
                                  ? UiTextId::CaptureSaveFailed
                                  : UiTextId::CaptureResult;
        renderPageHeader(title);
    } else {
        renderPageHeader(UiTextId::CaptureError);
    }
    if (stats.state == WifiFrameCaptureState::Failed) {
        renderMetric(0, tr(UiTextId::CaptureRecordFailedUser), Tone::Danger);
        renderMetric(1, tr(UiTextId::CaptureTryAgainUser));
        return;
    }

    if (stats.framesAccepted == 0U &&
        stats.state == WifiFrameCaptureState::Complete) {
        renderMetric(0, tr(UiTextId::CaptureNoPackets), Tone::Warning);
    } else {
        std::snprintf(line, sizeof(line), tr(UiTextId::CapturePacketsFormat),
                      static_cast<unsigned long>(stats.framesAccepted));
        renderMetric(0, line, Tone::Positive);
    }
    if (stats.state == WifiFrameCaptureState::Running) {
        std::snprintf(line, sizeof(line), tr(UiTextId::CaptureChannelFormat),
                      static_cast<unsigned>(
                          wifiFrameCapture.currentChannel()));
        renderMetric(1, line);
        renderMetric(2, tr(UiTextId::CaptureRecordingUser), Tone::Positive);
    } else {
        renderMetric(1, tr(UiTextId::CapturePcapReadyUser), Tone::Positive);
        const UiTextId storageMessage =
            capturePersistState == CapturePersistState::Confirm
                ? UiTextId::CaptureIdentifiersWarning
                : capturePersistState == CapturePersistState::Saving
                      ? UiTextId::CaptureSavingUser
                      : capturePersistState == CapturePersistState::Saved
                            ? UiTextId::CaptureSavedUser
                            : capturePersistState == CapturePersistState::Failed
                                  ? UiTextId::CaptureSaveFailedUser
                                  : UiTextId::CaptureReadyToSave;
        renderMetric(2, tr(storageMessage),
                     capturePersistState == CapturePersistState::Failed
                         ? Tone::Danger
                         : capturePersistState == CapturePersistState::Confirm
                               ? Tone::Warning
                               : Tone::Positive);
    }
    const std::uint32_t dropped = stats.framesDroppedCapacity +
                                  stats.framesDroppedInvalid;
    if (dropped != 0U) {
        std::snprintf(line, sizeof(line),
                      tr(UiTextId::CaptureLossWarningFormat),
                      static_cast<unsigned long>(dropped));
        renderMetric(3, line, Tone::Warning);
    }
    if (stats.state == WifiFrameCaptureState::Running) {
        wifiCaptureRenderedFrames = stats.framesAccepted;
        wifiCaptureRenderedChannel = wifiFrameCapture.currentChannel();
        wifiCaptureRenderedDrops = dropped;
    }
}

void renderWifiCaptureLiveData() {
    const auto stats = wifiFrameCapture.stats();
    if (stats.state != WifiFrameCaptureState::Running) return;
    char line[64] = {};
    if (wifiCaptureRenderedFrames != stats.framesAccepted) {
        const Rect bounds = Components::metricRow(0);
        display.fillRect(bounds.x, bounds.y, bounds.width, bounds.height,
                         Palette::Canvas);
        std::snprintf(line, sizeof(line), tr(UiTextId::CapturePacketsFormat),
                      static_cast<unsigned long>(stats.framesAccepted));
        renderMetric(0, line, Tone::Positive);
        wifiCaptureRenderedFrames = stats.framesAccepted;
    }
    const std::uint8_t channel = wifiFrameCapture.currentChannel();
    if (wifiCaptureRenderedChannel != channel) {
        const Rect bounds = Components::metricRow(1);
        display.fillRect(bounds.x, bounds.y, bounds.width, bounds.height,
                         Palette::Canvas);
        std::snprintf(line, sizeof(line), tr(UiTextId::CaptureChannelFormat),
                      static_cast<unsigned>(channel));
        renderMetric(1, line);
        wifiCaptureRenderedChannel = channel;
    }
    const std::uint32_t dropped = stats.framesDroppedCapacity +
                                  stats.framesDroppedInvalid;
    if (wifiCaptureRenderedDrops != dropped) {
        const Rect bounds = Components::metricRow(3);
        display.fillRect(bounds.x, bounds.y, bounds.width, bounds.height,
                         Palette::Canvas);
        if (dropped != 0U) {
            std::snprintf(line, sizeof(line),
                          tr(UiTextId::CaptureLossWarningFormat),
                          static_cast<unsigned long>(dropped));
            renderMetric(3, line, Tone::Warning);
        }
        wifiCaptureRenderedDrops = dropped;
    }
}

void renderCaptureSourceMenu(bool clearContent) {
    renderHeader(tr(UiTextId::CaptureSources), clearContent);
    renderMenuRow(Components::choiceRow(0), tr(UiTextId::CaptureWifiSource),
                  tr(UiTextId::CaptureWifiSourceNote),
                  captureSourceSelection == 0, true, Tone::Positive);
    renderMenuRow(Components::choiceRow(1), tr(UiTextId::CaptureIrSource),
                  tr(UiTextId::CaptureIrSourceNote),
                  captureSourceSelection == 1, BoardProfile::kIrDeclared,
                  BoardProfile::kIrDeclared ? Tone::Positive : Tone::Muted);
}

void renderInfraredCapturePage(bool clearContent) {
    const auto& stats = infraredCapture.stats();
    char line[64] = {};
    if (stats.state == InfraredCaptureState::Idle) {
        renderHeader(tr(UiTextId::CaptureIrSource), clearContent);
        renderMetric(0, tr(UiTextId::IrAimDevice), Tone::Positive);
        renderMetric(1, tr(UiTextId::IrPressButton));
        renderMetric(2, tr(UiTextId::IrWaitUser));
        return;
    }

    UiTextId title = UiTextId::IrError;
    if (stats.state == InfraredCaptureState::Waiting) {
        title = UiTextId::IrWaiting;
    } else if (stats.state == InfraredCaptureState::Capturing) {
        title = UiTextId::IrCapturing;
    } else if (stats.state == InfraredCaptureState::Complete) {
        title = UiTextId::IrResult;
    } else if (stats.state == InfraredCaptureState::TimedOut) {
        title = UiTextId::IrNoSignal;
    } else if (stats.state == InfraredCaptureState::Unreliable) {
        title = UiTextId::IrUnreliable;
    }
    renderHeader(tr(title), clearContent);
    if (stats.state == InfraredCaptureState::Waiting) {
        renderMetric(0, tr(UiTextId::IrAimDevice), Tone::Positive);
        renderMetric(1, tr(UiTextId::IrPressButton));
        renderMetric(2, tr(UiTextId::IrWaitUser));
    } else if (stats.state == InfraredCaptureState::Capturing) {
        renderMetric(0, tr(UiTextId::IrSignalDetected), Tone::Positive);
        renderMetric(1, tr(UiTextId::IrKeepPressed));
    } else if (stats.state == InfraredCaptureState::Complete) {
        renderMetric(0, tr(UiTextId::IrSignalDetected), Tone::Positive);
        if (infraredCapture.decode().integrityValid) {
            std::snprintf(line, sizeof(line), tr(UiTextId::IrProtocolFormat),
                          leshy1::domain::captures::infraredProtocolName(
                              infraredCapture.decode().protocol));
            renderMetric(1, line, Tone::Positive);
            std::snprintf(line, sizeof(line), tr(UiTextId::IrCodeFormat),
                          static_cast<unsigned long>(
                              infraredCapture.decode().rawCode));
            renderMetric(2, line);
        } else {
            renderMetric(1, tr(UiTextId::IrUnknownFormat), Tone::Warning);
        }
        const UiTextId storageMessage =
            infraredCapturePersistState == CapturePersistState::Saving
                ? UiTextId::CaptureSavingUser
                : infraredCapturePersistState == CapturePersistState::Saved
                      ? UiTextId::CaptureSavedUser
                      : infraredCapturePersistState == CapturePersistState::Failed
                            ? UiTextId::CaptureSaveFailedUser
                            : UiTextId::CaptureReadyToSave;
        renderMetric(3, tr(storageMessage),
                     infraredCapturePersistState == CapturePersistState::Failed
                         ? Tone::Danger : Tone::Positive);
    } else if (stats.state == InfraredCaptureState::TimedOut) {
        renderMetric(0, tr(UiTextId::IrNoSignalDetected), Tone::Warning);
        renderMetric(1, tr(UiTextId::IrTryCloser));
        renderMetric(2, tr(UiTextId::CaptureTryAgainUser));
    } else if (stats.state == InfraredCaptureState::Unreliable) {
        renderMetric(0, tr(UiTextId::IrSignalDetected), Tone::Warning);
        renderMetric(1, tr(UiTextId::IrReadUnreliable), Tone::Danger);
        renderMetric(2, tr(UiTextId::CaptureTryAgainUser));
    } else {
        renderMetric(0, tr(UiTextId::CaptureRecordFailedUser), Tone::Danger);
        renderMetric(1, tr(UiTextId::CaptureTryAgainUser));
    }
}

void renderCapturePage(bool clearContent) {
    if (captureView == CaptureView::SourceMenu) {
        renderCaptureSourceMenu(clearContent);
    } else if (captureView == CaptureView::Infrared) {
        renderInfraredCapturePage(clearContent);
    } else {
        renderWifiCapturePage(clearContent);
    }
}

void renderSelfTestModeRow(std::uint8_t index) {
    const UiTextId labels[2] = {UiTextId::Quick, UiTextId::FullGuided};
    const UiTextId notes[2] = {UiTextId::QuickNote, UiTextId::FullNote};
    if (index >= 2) return;
    const bool selected = selfTestController.selection() == index;
    renderMenuRow(Components::choiceRow(index), tr(labels[index]),
                  tr(notes[index]), selected, true,
                  index == 0 ? Tone::Positive : Tone::Warning);
}

void renderSelfTestPage(bool clearContent) {
    char line[96] = {};
    if (selfTestController.view() == SelfTestView::ModeMenu) {
        renderHeader(tr(UiTextId::SelfTestTitle), clearContent);
        for (std::uint8_t index = 0; index < 2; ++index) {
            renderSelfTestModeRow(index);
        }
        display.setTextColor(Palette::TextMuted, Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 207);
        display.print(tr(UiTextId::SelfTestNoBoot));
        return;
    }

    if (selfTestController.view() == SelfTestView::Preflight) {
        renderHeader(tr(UiTextId::FullPreflight), clearContent);
        renderMetric(0, tr(UiTextId::QuickChecks9));
        renderMetric(1, tr(UiTextId::CapabilityPlanStaged));
        renderMetric(2, tr(UiTextId::SideEffectsNone));
        renderMetric(3, tr(UiTextId::ResultBlocked), Tone::Warning);
        display.setTextColor(Palette::TextMuted, Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 203);
        display.print(tr(UiTextId::GuidedLater));
        return;
    }

    if (selfTestController.view() == SelfTestView::VisualCheck) {
        renderHeader(tr(UiTextId::VisualCheckTitle), clearContent);
        constexpr UiTextId states[SelfTestController::kVisualStateCount] = {
            UiTextId::VisualDialog,
            UiTextId::VisualUnavailable,
            UiTextId::VisualDegraded,
            UiTextId::VisualError,
            UiTextId::VisualRunning,
        };
        constexpr UiTextId details[SelfTestController::kVisualStateCount] = {
            UiTextId::VisualDialogDetail,
            UiTextId::VisualUnavailableDetail,
            UiTextId::VisualDegradedDetail,
            UiTextId::VisualErrorDetail,
            UiTextId::VisualRunningDetail,
        };
        constexpr Tone tones[SelfTestController::kVisualStateCount] = {
            Tone::Focus, Tone::Muted, Tone::Warning, Tone::Danger, Tone::Positive,
        };
        const std::uint8_t state = selfTestController.visualState();
        renderStateCard(tr(states[state]), tr(details[state]), tones[state], state);
        return;
    }

    if (selfTestController.view() == SelfTestView::ActiveChecks) {
        const bool artifactPhase =
            fullGuidedRfState.step == FullGuidedRfStep::Complete;
        renderHeader(tr(artifactPhase ? UiTextId::FullActiveDataTitle
                                     : UiTextId::FullActiveTitle),
                     clearContent);
        if (artifactPhase) {
            const bool disposablePhase =
                fullGuidedArtifactState.step ==
                    FullGuidedArtifactStep::DisposableCommit ||
                fullGuidedArtifactState.step ==
                    FullGuidedArtifactStep::DisposableRemountExport ||
                fullGuidedArtifactState.step ==
                    FullGuidedArtifactStep::DisposableCleanup ||
                fullGuidedArtifactState.step ==
                    FullGuidedArtifactStep::ProductVerify;
            if (disposablePhase) {
                renderMetric(
                    0,
                    fullGuidedArtifactState.disposableCommitPassed
                        ? tr(UiTextId::FullActiveScratchPass)
                        : tr(UiTextId::FullActiveScratchRun),
                    fullGuidedArtifactState.disposableCommitPassed
                        ? Tone::Positive : Tone::Warning);
                renderMetric(
                    1,
                    fullGuidedArtifactState.disposableExportPassed
                        ? tr(UiTextId::FullActiveRemountPass)
                        : tr(UiTextId::FullActiveRemountRun),
                    fullGuidedArtifactState.disposableExportPassed
                        ? Tone::Positive : Tone::Warning);
                renderMetric(
                    2,
                    fullGuidedArtifactState.disposableCleanupPassed &&
                            fullGuidedArtifactState.productVerifyPassed
                        ? tr(UiTextId::FullActiveCleanupPass)
                        : tr(UiTextId::FullActiveCleanupRun),
                    fullGuidedArtifactState.disposableCleanupPassed &&
                            fullGuidedArtifactState.productVerifyPassed
                        ? Tone::Positive : Tone::Warning);
                display.setTextColor(Palette::TextMuted, Palette::Canvas);
                setUiCursor(UiTextRole::Meta, 14, 207);
                display.print(tr(UiTextId::FullActiveDataSafety));
                return;
            }
            renderMetric(
                0,
                fullGuidedArtifactState.recoveryPassed
                    ? tr(UiTextId::FullActiveStoragePass)
                    : tr(UiTextId::FullActiveStorageRun),
                fullGuidedArtifactState.recoveryPassed ? Tone::Positive
                                                       : Tone::Warning);
            renderMetric(
                1,
                fullGuidedArtifactState.libraryPassed
                    ? tr(UiTextId::FullActiveLibraryPass)
                    : tr(UiTextId::FullActiveLibraryRun),
                fullGuidedArtifactState.libraryPassed ? Tone::Positive
                                                      : Tone::Warning);
            renderMetric(2, tr(UiTextId::FullActiveCaptureRun), Tone::Warning);
            display.setTextColor(Palette::TextMuted, Palette::Canvas);
            setUiCursor(UiTextRole::Meta, 14, 207);
            display.print(tr(UiTextId::FullActiveDataSafety));
            return;
        }
        if (fullGuidedRfState.step == FullGuidedRfStep::Idle) {
            renderMetric(0, tr(UiTextId::FullActivePreparing), Tone::Warning);
        } else {
            renderMetric(
                0,
                fullGuidedRfState.nrf24Passed
                    ? tr(UiTextId::FullActiveNrfPass)
                    : tr(UiTextId::FullActiveNrfRunning),
                fullGuidedRfState.nrf24Passed ? Tone::Positive
                                               : Tone::Warning);
        }
        std::snprintf(line, sizeof(line), tr(UiTextId::FullActiveCcFormat),
                      static_cast<unsigned>(fullGuidedRfState.cc1101Bins));
        renderMetric(1, line,
                     fullGuidedRfState.cc1101Passed ? Tone::Positive
                                                    : Tone::Warning);
        display.setTextColor(Palette::TextMuted, Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 207);
        display.print(tr(UiTextId::FullActiveSafety));
        return;
    }

    const SelfTestReport& report = selfTestController.report();
    renderHeader(report.status == SelfTestResultStatus::Pass
                     ? tr(UiTextId::SelfTestPass)
                     : (report.status == SelfTestResultStatus::Fail
                            ? tr(UiTextId::SelfTestFail)
                            : tr(UiTextId::SelfTestBlocked)),
                 clearContent);
    renderMetric(0,
                 report.mode == SelfTestMode::Quick ? tr(UiTextId::ModeQuick)
                                                    : tr(UiTextId::ModeFull),
                 report.status == SelfTestResultStatus::Pass
                     ? Tone::Positive
                     : (report.status == SelfTestResultStatus::Fail
                            ? Tone::Danger
                            : Tone::Warning));
    std::snprintf(line, sizeof(line), tr(UiTextId::ChecksFormat),
                  static_cast<unsigned>(report.passed),
                  static_cast<unsigned>(report.checkCount));
    renderMetric(1, line);
    std::snprintf(line, sizeof(line), tr(UiTextId::FailBlockedFormat),
                  static_cast<unsigned>(report.failed),
                  static_cast<unsigned>(report.blocked),
                  static_cast<unsigned>(report.notApplicable));
    renderMetric(2, line);
    std::snprintf(line, sizeof(line), tr(UiTextId::HeapMinFormat),
                  static_cast<unsigned long>(report.facts.heapMinimum / 1024U));
    renderMetric(3, line);
    std::snprintf(line, sizeof(line), tr(UiTextId::InputDropsFormat),
                  static_cast<unsigned long>(report.facts.inputQueueDrops));
    renderMetric(4, line);
    display.setTextColor(Palette::Positive, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 218);
    display.print(tr(report.readOnly ? UiTextId::SelfTestReportUsb
                                    : UiTextId::SelfTestReportActiveUsb));
}

void renderOverview(bool clearContent) {
    char line[80] = {};
    renderHeader(tr(UiTextId::DiagnosticsTitle), clearContent);
    display.setTextColor(Palette::Positive, Palette::Canvas);
    setUiCursor(UiTextRole::Body, 14, 82);
    display.print(tr(UiTextId::ProfileN16));

    display.setTextColor(Palette::TextSecondary, Palette::Canvas);
    std::snprintf(line, sizeof(line), tr(UiTextId::FlashFormat),
                  static_cast<unsigned long>(bootMetrics.flashBytes / 1024U));
    setUiCursor(UiTextRole::Body, 14, 120);
    display.print(line);
    std::snprintf(line, sizeof(line), tr(UiTextId::HeapFreeFormat),
                  static_cast<unsigned long>(ESP.getFreeHeap() / 1024U));
    setUiCursor(UiTextRole::Body, 14, 144);
    display.print(line);
    std::snprintf(line, sizeof(line), tr(UiTextId::UiReadyFormat),
                  static_cast<unsigned long long>(bootMetrics.interactiveReadyUs));
    setUiCursor(UiTextRole::Body, 14, 168);
    display.print(line);

}

UiTextId safetyReasonTextId() {
    switch (safetySupervisor.reason()) {
        case SafetyReason::RuntimeWatchdog:
            return UiTextId::SafetyWatchdogReason;
        case SafetyReason::SupervisorUnavailable:
            return UiTextId::SafetySupervisorReason;
        case SafetyReason::OutputInvariant:
        default:
            return UiTextId::SafetyOutputReason;
    }
}

void renderSafetyStop(bool clearContent) {
    renderHeader(tr(UiTextId::SafetyStopTitle), clearContent);
    display.setTextColor(Palette::Danger, Palette::Canvas);
    setUiCursor(UiTextRole::Body, 14, 52);
    display.print(tr(safetyReasonTextId()));

    display.fillRoundRect(Layout::Edge, 88, Layout::ContentWidth, 82,
                          Layout::Radius, Palette::Surface);
    display.setTextColor(Palette::Positive, Palette::Surface);
    setUiCursor(UiTextRole::Body, 20, 101);
    display.print(tr(UiTextId::SafetyOutputsStopped));
    display.setTextColor(Palette::Warning, Palette::Surface);
    setUiCursor(UiTextRole::Meta, 20, 137);
    display.print(tr(UiTextId::SafetyPowerWarning));

    display.setTextColor(Palette::TextPrimary, Palette::Canvas);
    setUiCursor(UiTextRole::Body, 14, 202);
    display.print(tr(safetySupervisor.clearPending()
                         ? UiTextId::SafetyClearConfirm
                         : UiTextId::SafetyClearPrompt));
    if (safetySupervisor.clearPending()) {
        display.setTextColor(Palette::TextSecondary, Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 240);
        display.print(tr(UiTextId::SafetyClearCancel));
    }
}

constexpr std::size_t kVisibleSurveyRows = 2;
constexpr std::int16_t kSurveyFilterY = 101;
constexpr std::int16_t kSurveyRowsY = 132;
constexpr std::size_t kVisibleWifiNetworkRows = 4;

std::size_t surveyFirstVisible(std::size_t selection) {
    return selection < kVisibleSurveyRows
        ? 0
        : selection - kVisibleSurveyRows + 1;
}

void renderSurveyListRow(std::size_t index, std::size_t firstVisible) {
    const Observation* observation = surveyController.visibleAt(index);
    if (observation == nullptr) return;
    const std::int32_t y =
        kSurveyRowsY + static_cast<std::int32_t>(index - firstVisible) * 40;
    const bool selected = !surveyController.filterFocused() &&
                          surveyController.selection() == index;
    const std::uint16_t background = selected ? Palette::SurfaceFocus
                                               : Palette::Surface;
    display.fillRoundRect(Layout::Edge, y, Layout::ContentWidth, 36,
                          Layout::Radius, background);
    renderFocusCue({Layout::Edge, static_cast<std::int16_t>(y),
                    Layout::ContentWidth, 36}, selected);
    display.setTextColor(selected ? Palette::Focus : Palette::TextSecondary,
                         background);
    setUiCursor(UiTextRole::Body,
                Layout::Edge + kInteractiveRowTextInset, y - 2);
    char visibleLabel[24] = {};
    const std::size_t visibleLength = observation->labelLength < 15U
        ? observation->labelLength : 15U;
    if (visibleLength == 0) {
        std::strcpy(visibleLabel, tr(UiTextId::Hidden));
    } else {
        std::memcpy(visibleLabel, observation->label.data(), visibleLength);
        if (observation->labelLength > visibleLength) {
            visibleLabel[visibleLength - 1U] = '~';
        }
    }
    display.print(visibleLabel);
    char line[96] = {};
    display.setTextColor(Palette::Positive, background);
    if (observation->radio == RadioKind::Ble) {
        std::snprintf(line, sizeof(line), tr(UiTextId::BleRssiFormat),
                      static_cast<int>(observation->rssiDbm));
    } else {
        std::snprintf(line, sizeof(line), tr(UiTextId::ChannelRssiFormat),
                      static_cast<unsigned>(observation->channel),
                      static_cast<int>(observation->rssiDbm));
    }
    setUiCursor(UiTextRole::Meta, 146, y + 13);
    display.print(line);
}

std::size_t wifiNetworkFirstVisible(std::size_t selection) {
    return selection < kVisibleWifiNetworkRows
        ? 0
        : selection - kVisibleWifiNetworkRows + 1U;
}

std::uint8_t wifiSignalLevel(std::int16_t rssiDbm) {
    if (rssiDbm >= -55) return 4;
    if (rssiDbm >= -67) return 3;
    if (rssiDbm >= -78) return 2;
    return 1;
}

void renderWifiSignalBars(Rect bounds, std::int16_t rssiDbm,
                          std::uint16_t background) {
    constexpr std::int16_t kBarWidth = 4;
    constexpr std::int16_t kBarGap = 2;
    constexpr std::int16_t kBarCount = 4;
    const std::int16_t x = bounds.x + bounds.width - 30;
    const std::int16_t baseline = bounds.y + bounds.height - 12;
    const std::uint8_t level = wifiSignalLevel(rssiDbm);
    for (std::int16_t index = 0; index < kBarCount; ++index) {
        const std::int16_t height = 4 + index * 3;
        display.fillRect(x + index * (kBarWidth + kBarGap), baseline - height,
                         kBarWidth, height,
                         index < level ? Palette::Positive
                                       : Palette::TextMuted);
        display.drawFastHLine(
            x + index * (kBarWidth + kBarGap), baseline, kBarWidth,
            background);
    }
}

UiTextId radioSignalQualityText(std::int16_t rssiDbm) {
    switch (wifiSignalLevel(rssiDbm)) {
        case 4: return UiTextId::RadioSignalExcellent;
        case 3: return UiTextId::RadioSignalGood;
        case 2: return UiTextId::RadioSignalWeak;
        default: return UiTextId::RadioSignalVeryWeak;
    }
}

void renderRadioSignalCard(std::int16_t rssiDbm) {
    constexpr Rect bounds{Layout::Edge, 128, Layout::ContentWidth, 104};
    constexpr std::int16_t kTrackInset = 10;
    constexpr std::int16_t kTrackY = bounds.y + 59;
    constexpr std::int16_t kTrackWidth = bounds.width - 2 * kTrackInset;
    constexpr std::int16_t kTrackHeight = 14;
    const std::uint8_t level = wifiSignalLevel(rssiDbm);
    const std::uint16_t tone = level >= 3U
        ? Palette::Positive : (level == 2U ? Palette::Warning
                                           : Palette::Danger);
    display.fillRoundRect(bounds.x, bounds.y, bounds.width, bounds.height,
                          Layout::Radius, Palette::Surface);
    display.setTextColor(Palette::TextSecondary, Palette::Surface);
    setUiCursor(UiTextRole::Meta, bounds.x + 10, bounds.y + 9);
    display.print(tr(UiTextId::RadioSignalLabel));
    display.setTextColor(tone, Palette::Surface);
    setUiCursor(UiTextRole::Body, bounds.x + 10, bounds.y + 29);
    display.print(tr(radioSignalQualityText(rssiDbm)));
    char value[24] = {};
    std::snprintf(value, sizeof(value), tr(UiTextId::RadioSignalDbmFormat),
                  static_cast<int>(rssiDbm));
    setUiCursor(UiTextRole::Body, bounds.x + 10, bounds.y + 29);
    const std::int16_t valueX = bounds.x + bounds.width - 10 -
                                display.textWidth(value);
    setUiCursor(UiTextRole::Body, valueX, bounds.y + 29);
    display.print(value);
    display.fillRect(bounds.x + kTrackInset, kTrackY, kTrackWidth,
                     kTrackHeight, Palette::Canvas);
    display.drawRect(bounds.x + kTrackInset, kTrackY, kTrackWidth,
                     kTrackHeight, Palette::Divider);
    const std::int16_t clamped = rssiDbm < -100
        ? -100 : (rssiDbm > -40 ? -40 : rssiDbm);
    const std::int16_t fillWidth = static_cast<std::int16_t>(
        (static_cast<std::int32_t>(clamped + 100) * (kTrackWidth - 2)) / 60);
    if (fillWidth > 0) {
        display.fillRect(bounds.x + kTrackInset + 1, kTrackY + 1,
                         fillWidth, kTrackHeight - 2, tone);
    }
    display.setTextColor(Palette::TextMuted, Palette::Surface);
    setUiCursor(UiTextRole::Meta, bounds.x + kTrackInset, bounds.y + 79);
    display.print(tr(UiTextId::RadioSignalScaleWeak));
    const char* strong = tr(UiTextId::RadioSignalScaleStrong);
    const std::int16_t strongX = bounds.x + bounds.width - kTrackInset -
                                 display.textWidth(strong);
    setUiCursor(UiTextRole::Meta, strongX, bounds.y + 79);
    display.print(strong);
}

void renderWifiNetworkRow(std::size_t index, std::size_t firstVisible) {
    const Observation* observation = wifiNetworkAt(index);
    if (observation == nullptr || index < firstVisible ||
        index >= firstVisible + kVisibleWifiNetworkRows) {
        return;
    }
    const Rect bounds = Components::homeRow(
        static_cast<std::uint8_t>(index - firstVisible));
    const bool selected = wifiNetworkSelection == index;
    const std::uint16_t background = selected ? Palette::SurfaceFocus
                                               : Palette::Surface;
    display.fillRoundRect(bounds.x, bounds.y, bounds.width, bounds.height,
                          Layout::Radius, background);
    renderFocusCue(bounds, selected);
    char label[24] = {};
    const std::size_t visibleLength = observation->labelLength < 18U
        ? observation->labelLength : 18U;
    if (visibleLength == 0) {
        std::snprintf(label, sizeof(label), "%s", tr(UiTextId::Hidden));
    } else {
        std::memcpy(label, observation->label.data(), visibleLength);
        if (observation->labelLength > visibleLength) {
            label[visibleLength - 1U] = '~';
        }
    }
    const std::int16_t labelTop = menuRowTextTop(bounds);
    display.setTextColor(selected ? Palette::Focus : Palette::TextSecondary,
                         background);
    setUiCursor(UiTextRole::Body,
                bounds.x + kInteractiveRowTextInset, labelTop);
    display.print(label);
    char note[48] = {};
    std::snprintf(note, sizeof(note), tr(UiTextId::ChannelRssiFormat),
                  static_cast<unsigned>(observation->channel),
                  static_cast<int>(observation->rssiDbm));
    display.setTextColor(Palette::Positive, background);
    setUiCursor(UiTextRole::Meta,
                bounds.x + kInteractiveRowTextInset,
                labelTop + kRobotoCondensedBodyAscent +
                    kRobotoCondensedBodyDescent + 1);
    display.print(note);
    renderWifiSignalBars(bounds, observation->rssiDbm, background);
}

void renderWifiNetworksData() {
    const std::size_t visibleSize = wifiNetworkVisibleSize();
    if (visibleSize == 0) {
        display.setTextColor(Palette::Positive, Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 70);
        display.print(tr(UiTextId::WifiNetworksSearching));
        return;
    }
    const std::size_t first = wifiNetworkFirstVisible(wifiNetworkSelection);
    const std::size_t end = visibleSize <
            first + kVisibleWifiNetworkRows
        ? visibleSize : first + kVisibleWifiNetworkRows;
    for (std::size_t index = first; index < end; ++index) {
        renderWifiNetworkRow(index, first);
    }
}

void renderWifiNetworks(bool clearContent) {
    renderHeader(tr(UiTextId::WifiMenuNetworks), clearContent);
    renderWifiNetworksData();
}

void renderWifiNetworkDetail(bool clearContent) {
    renderHeader(tr(UiTextId::WifiNetworkDetailTitle), clearContent);
    const char* label = wifiNetworkDetail.labelLength == 0
        ? tr(UiTextId::Hidden) : wifiNetworkDetail.label.data();
    display.setTextColor(Palette::Focus, Palette::Canvas);
    setUiCursor(UiTextRole::Body, 14, 42);
    display.print(label);
    char line[96] = {};
    std::snprintf(
        line, sizeof(line), tr(UiTextId::WifiNetworkBssidFormat),
        static_cast<unsigned>(wifiNetworkDetail.identity[0]),
        static_cast<unsigned>(wifiNetworkDetail.identity[1]),
        static_cast<unsigned>(wifiNetworkDetail.identity[2]),
        static_cast<unsigned>(wifiNetworkDetail.identity[3]),
        static_cast<unsigned>(wifiNetworkDetail.identity[4]),
        static_cast<unsigned>(wifiNetworkDetail.identity[5]));
    display.setTextColor(Palette::TextSecondary, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 72);
    display.print(line);
    std::snprintf(line, sizeof(line), tr(UiTextId::RadioChannelFormat),
                  static_cast<unsigned>(wifiNetworkDetail.channel));
    display.setTextColor(Palette::Positive, Palette::Canvas);
    setUiCursor(UiTextRole::Body, 14, 98);
    display.print(line);
    renderRadioSignalCard(wifiNetworkDetail.rssiDbm);
}

std::size_t bleDeviceFirstVisible(std::size_t selection) {
    return selection < kVisibleWifiNetworkRows
        ? 0 : selection - kVisibleWifiNetworkRows + 1U;
}

void formatBleAddress(const Observation& device, char* output,
                      std::size_t capacity) {
    if (output == nullptr || capacity == 0U) return;
    std::snprintf(output, capacity, tr(UiTextId::BleAddressFormat),
                  static_cast<unsigned>(device.identity[0]),
                  static_cast<unsigned>(device.identity[1]),
                  static_cast<unsigned>(device.identity[2]),
                  static_cast<unsigned>(device.identity[3]),
                  static_cast<unsigned>(device.identity[4]),
                  static_cast<unsigned>(device.identity[5]));
}

void renderBleDeviceRow(std::size_t index, std::size_t firstVisible) {
    const Observation* device = bleDeviceCatalog.at(index);
    if (device == nullptr || index < firstVisible ||
        index >= firstVisible + kVisibleWifiNetworkRows) {
        return;
    }
    const Rect bounds = Components::homeRow(
        static_cast<std::uint8_t>(index - firstVisible));
    const bool selected = bleDeviceSelection == index;
    const std::uint16_t background = selected ? Palette::SurfaceFocus
                                               : Palette::Surface;
    display.fillRoundRect(bounds.x, bounds.y, bounds.width, bounds.height,
                          Layout::Radius, background);
    renderFocusCue(bounds, selected);
    char label[24] = {};
    const std::size_t visibleLength = device->labelLength < 18U
        ? device->labelLength : 18U;
    if (visibleLength == 0U) {
        std::snprintf(label, sizeof(label), "%s",
                      tr(UiTextId::BleDeviceUnnamed));
    } else {
        std::memcpy(label, device->label.data(), visibleLength);
        if (device->labelLength > visibleLength) {
            label[visibleLength - 1U] = '~';
        }
    }
    const std::int16_t labelTop = menuRowTextTop(bounds);
    display.setTextColor(selected ? Palette::Focus : Palette::TextSecondary,
                         background);
    setUiCursor(UiTextRole::Body,
                bounds.x + kInteractiveRowTextInset, labelTop);
    display.print(label);
    char note[64] = {};
    std::snprintf(note, sizeof(note), tr(UiTextId::BleDeviceRowFormat),
                  static_cast<int>(device->rssiDbm),
                  static_cast<unsigned>(device->identity[3]),
                  static_cast<unsigned>(device->identity[4]),
                  static_cast<unsigned>(device->identity[5]));
    display.setTextColor(Palette::Positive, background);
    setUiCursor(UiTextRole::Meta,
                bounds.x + kInteractiveRowTextInset,
                labelTop + kRobotoCondensedBodyAscent +
                    kRobotoCondensedBodyDescent + 1);
    display.print(note);
    renderWifiSignalBars(bounds, device->rssiDbm, background);
}

void renderBleDevicesData() {
    if (bleDeviceCatalog.size() == 0U) {
        const bool unavailable = productSurveySourceUnavailableVisible();
        display.setTextColor(unavailable ? Palette::Danger : Palette::Positive,
                             Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 70);
        display.print(tr(unavailable ? UiTextId::BleReceiverUnavailable
                                     : UiTextId::BleDevicesSearching));
        return;
    }
    const std::size_t first = bleDeviceFirstVisible(bleDeviceSelection);
    const std::size_t end = bleDeviceCatalog.size() <
            first + kVisibleWifiNetworkRows
        ? bleDeviceCatalog.size() : first + kVisibleWifiNetworkRows;
    for (std::size_t index = first; index < end; ++index) {
        renderBleDeviceRow(index, first);
    }
}

void renderBleDevices(bool clearContent) {
    renderHeader(tr(UiTextId::BleDevicesTitle), clearContent);
    renderBleDevicesData();
}

void renderBleDeviceDetail(bool clearContent) {
    renderHeader(tr(UiTextId::BleDeviceDetailTitle), clearContent);
    const char* label = bleDeviceDetail.labelLength == 0U
        ? tr(UiTextId::BleDeviceUnnamed) : bleDeviceDetail.label.data();
    display.setTextColor(Palette::Focus, Palette::Canvas);
    setUiCursor(UiTextRole::Body, 14, 42);
    display.print(label);
    char line[96] = {};
    formatBleAddress(bleDeviceDetail, line, sizeof(line));
    display.setTextColor(Palette::TextSecondary, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 72);
    display.print(line);
    display.setTextColor(Palette::Positive, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 101);
    display.print(tr(UiTextId::BlePassiveOnly));
    renderRadioSignalCard(bleDeviceDetail.rssiDbm);
}

std::size_t wifiDeviceFirstVisible(std::size_t selection) {
    return selection < kVisibleWifiNetworkRows
        ? 0 : selection - kVisibleWifiNetworkRows + 1U;
}

UiTextId wifiDeviceGenerationText(WifiDeviceGeneration generation) {
    switch (generation) {
        case WifiDeviceGeneration::Legacy:
            return UiTextId::WifiDeviceWifiLegacy;
        case WifiDeviceGeneration::Wifi4:
            return UiTextId::WifiDeviceWifi4;
        case WifiDeviceGeneration::Wifi5:
            return UiTextId::WifiDeviceWifi5;
        case WifiDeviceGeneration::Wifi6:
            return UiTextId::WifiDeviceWifi6;
        case WifiDeviceGeneration::Unknown:
        default:
            return UiTextId::WifiDeviceUnknown;
    }
}

const char* wifiDeviceMaker(const WifiDeviceRecord& device) {
    if (device.wpsManufacturerLength != 0U) {
        return device.wpsManufacturer.data();
    }
    return device.ouiVendorLength != 0U ? device.ouiVendor.data() : nullptr;
}

const char* wifiDevicePrimaryLabel(const WifiDeviceRecord& device) {
    if (device.wpsDeviceNameLength != 0U) {
        return device.wpsDeviceName.data();
    }
    if (device.wpsModelLength != 0U) return device.wpsModel.data();
    const char* maker = wifiDeviceMaker(device);
    return maker == nullptr ? "" : maker;
}

void formatWifiAddress(const std::array<std::uint8_t, 6>& address,
                       char* output, std::size_t capacity);

void compactWifiDeviceLabel(const WifiDeviceRecord& device, char* output,
                            std::size_t capacity) {
    if (output == nullptr || capacity == 0U) return;
    const char* source = wifiDevicePrimaryLabel(device);
    if (source[0] == '\0') {
        formatWifiAddress(device.address, output, capacity);
        return;
    }
    const std::size_t sourceLength = std::strlen(source);
    const std::size_t visible = sourceLength < capacity
        ? sourceLength : capacity - 1U;
    std::memcpy(output, source, visible);
    output[visible] = '\0';
    if (visible < sourceLength && visible > 1U) output[visible - 1U] = '~';
}

UiTextId wifiDeviceStateText(WifiDeviceState state) {
    switch (state) {
        case WifiDeviceState::Searching: return UiTextId::WifiDeviceSearching;
        case WifiDeviceState::Connecting: return UiTextId::WifiDeviceConnecting;
        case WifiDeviceState::Connected: return UiTextId::WifiDeviceConnected;
    }
    return UiTextId::WifiDeviceSearching;
}

void formatWifiAddress(const std::array<std::uint8_t, 6>& address,
                       char* output, std::size_t capacity) {
    if (output == nullptr || capacity == 0U) return;
    std::snprintf(output, capacity, tr(UiTextId::WifiDeviceAddressFormat),
                  static_cast<unsigned>(address[0]),
                  static_cast<unsigned>(address[1]),
                  static_cast<unsigned>(address[2]),
                  static_cast<unsigned>(address[3]),
                  static_cast<unsigned>(address[4]),
                  static_cast<unsigned>(address[5]));
}

void renderWifiDeviceRow(std::size_t index, std::size_t firstVisible) {
    const WifiDeviceRecord* device = wifiDeviceAt(index);
    if (device == nullptr || index < firstVisible ||
        index >= firstVisible + kVisibleWifiNetworkRows) {
        return;
    }
    const Rect bounds = Components::homeRow(
        static_cast<std::uint8_t>(index - firstVisible));
    const bool selected = wifiDeviceSelection == index;
    const std::uint16_t background = selected ? Palette::SurfaceFocus
                                               : Palette::Surface;
    display.fillRoundRect(bounds.x, bounds.y, bounds.width, bounds.height,
                          Layout::Radius, background);
    renderFocusCue(bounds, selected);
    char primary[23] = {};
    compactWifiDeviceLabel(*device, primary, sizeof(primary));
    const std::int16_t labelTop = menuRowTextTop(bounds);
    display.setTextColor(selected ? Palette::Focus : Palette::TextSecondary,
                         background);
    setUiCursor(UiTextRole::Body,
                bounds.x + kInteractiveRowTextInset, labelTop);
    display.print(primary);
    char note[64] = {};
    std::snprintf(note, sizeof(note), tr(UiTextId::WifiDeviceRowFormat),
                  tr(wifiDeviceStateText(device->state)),
                  static_cast<unsigned>(device->channel),
                  static_cast<int>(device->rssiDbm));
    display.setTextColor(Palette::Positive, background);
    setUiCursor(UiTextRole::Meta,
                bounds.x + kInteractiveRowTextInset,
                labelTop + kRobotoCondensedBodyAscent +
                    kRobotoCondensedBodyDescent + 1);
    display.print(note);
}

void renderWifiDevicesData() {
    if (wifiDeviceCatalog.size() == 0U) {
        const auto stats = wifiFrameCapture.deviceMonitorStats();
        display.setTextColor(stats.active ? Palette::Positive : Palette::Danger,
                             Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 70);
        display.print(tr(stats.active ? UiTextId::WifiDevicesListening
                                      : UiTextId::WifiDevicesFailed));
        return;
    }
    const std::size_t first = wifiDeviceFirstVisible(wifiDeviceSelection);
    const std::size_t end = wifiDeviceVisibleSize() <
            first + kVisibleWifiNetworkRows
        ? wifiDeviceVisibleSize() : first + kVisibleWifiNetworkRows;
    for (std::size_t index = first; index < end; ++index) {
        renderWifiDeviceRow(index, first);
    }
}

void renderWifiDevices(bool clearContent) {
    renderHeader(tr(UiTextId::WifiMenuDevices), clearContent);
    renderWifiDevicesData();
}

void renderWifiDeviceDetail(bool clearContent) {
    renderHeader(tr(UiTextId::WifiDeviceDetailTitle), clearContent);
    char line[96] = {};
    char primary[23] = {};
    compactWifiDeviceLabel(wifiDeviceDetail, primary, sizeof(primary));
    display.setTextColor(Palette::Focus, Palette::Canvas);
    setUiCursor(UiTextRole::Body, 14, 42);
    display.print(primary);
    display.setTextColor(Palette::TextSecondary, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 69);
    formatWifiAddress(wifiDeviceDetail.address, line, sizeof(line));
    display.print(line);
    display.setTextColor(Palette::TextMuted, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 92);
    display.print(tr(wifiDeviceDetail.locallyAdministered
                         ? UiTextId::WifiDevicePrivateAddress
                         : UiTextId::WifiDeviceFactoryAddress));
    const char* maker = wifiDeviceMaker(wifiDeviceDetail);
    std::snprintf(line, sizeof(line), tr(UiTextId::WifiDeviceMakerFormat),
                  maker == nullptr ? tr(UiTextId::WifiDeviceUnknown) : maker);
    display.setTextColor(maker == nullptr ? Palette::TextMuted
                                         : Palette::TextSecondary,
                         Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 115);
    display.print(line);
    if (wifiDeviceDetail.wpsModelLength != 0U) {
        std::snprintf(line, sizeof(line), tr(UiTextId::WifiDeviceModelFormat),
                      wifiDeviceDetail.wpsModel.data());
        setUiCursor(UiTextRole::Meta, 14, 138);
        display.print(line);
    }
    std::snprintf(
        line, sizeof(line), tr(UiTextId::WifiDeviceRadioFormat),
        tr(wifiDeviceGenerationText(wifiDeviceDetail.generation)),
        static_cast<unsigned>(wifiDeviceDetail.channel));
    display.setTextColor(Palette::Positive, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 161);
    display.print(line);
    if (wifiDeviceDetail.ssidLength != 0U) {
        std::snprintf(line, sizeof(line),
                      tr(UiTextId::WifiDeviceNetworkFormat),
                      wifiDeviceDetail.ssid.data());
        display.setTextColor(Palette::TextSecondary, Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 184);
        display.print(line);
    }
    if (wifiDeviceDetail.bssidKnown) {
        std::snprintf(
            line, sizeof(line), tr(UiTextId::WifiNetworkBssidFormat),
            static_cast<unsigned>(wifiDeviceDetail.bssid[0]),
            static_cast<unsigned>(wifiDeviceDetail.bssid[1]),
            static_cast<unsigned>(wifiDeviceDetail.bssid[2]),
            static_cast<unsigned>(wifiDeviceDetail.bssid[3]),
            static_cast<unsigned>(wifiDeviceDetail.bssid[4]),
            static_cast<unsigned>(wifiDeviceDetail.bssid[5]));
        display.setTextColor(Palette::TextSecondary, Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 207);
        display.print(line);
    }
    const std::uint64_t observedUs = wifiDeviceDetail.monotonicUs >=
            wifiDeviceDetail.firstSeenUs
        ? wifiDeviceDetail.monotonicUs - wifiDeviceDetail.firstSeenUs : 0U;
    std::snprintf(line, sizeof(line), tr(UiTextId::WifiDeviceSeenFormat),
                  static_cast<unsigned long>(observedUs / 1000000ULL),
                  tr(wifiDeviceStateText(wifiDeviceDetail.state)));
    display.setTextColor(Palette::TextMuted, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 230);
    display.print(line);
    setUiCursor(UiTextRole::Meta, 14, 257);
    display.print(tr(UiTextId::WifiDevicePassiveOnly));
}

UiTextId wifiDeviceTrendText(std::int16_t trendDb) {
    if (trendDb >= 4) return UiTextId::WifiDeviceTrendCloser;
    if (trendDb <= -4) return UiTextId::WifiDeviceTrendFarther;
    return UiTextId::WifiDeviceTrendStable;
}

void renderWifiDeviceRadarData() {
    display.fillRect(Layout::Edge, Layout::ContentTop, Layout::ContentWidth,
                     Layout::FooterDividerY - Layout::ContentTop,
                     Palette::Canvas);
    char line[96] = {};
    char primary[23] = {};
    compactWifiDeviceLabel(wifiDeviceDetail, primary, sizeof(primary));
    display.setTextColor(Palette::Focus, Palette::Canvas);
    setUiCursor(UiTextRole::Body, 14, 42);
    display.print(primary);
    std::snprintf(line, sizeof(line), tr(UiTextId::WifiDeviceRadioFormat),
                  tr(wifiDeviceStateText(wifiDeviceDetail.state)),
                  static_cast<unsigned>(wifiDeviceDetail.channel));
    display.setTextColor(Palette::TextSecondary, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 70);
    display.print(line);
    display.setTextColor(Palette::Positive, Palette::Canvas);
    setUiCursor(UiTextRole::Body, 14, 98);
    display.print(tr(wifiDeviceTrendText(wifiDeviceDetail.rssiTrendDb)));
    renderRadioSignalCard(wifiDeviceDetail.rssiDbm);
    std::snprintf(line, sizeof(line), tr(UiTextId::WifiDeviceRssiRangeFormat),
                  static_cast<int>(wifiDeviceDetail.minimumRssiDbm),
                  static_cast<int>(wifiDeviceDetail.maximumRssiDbm));
    display.setTextColor(Palette::TextMuted, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 247);
    display.print(line);
}

void renderWifiDeviceRadar(bool clearContent) {
    renderHeader(tr(UiTextId::WifiDeviceRadarTitle), clearContent);
    renderWifiDeviceRadarData();
}

constexpr std::int16_t kWifiChannelInfoY = Layout::ContentTop;
constexpr std::int16_t kWifiChannelInfoHeight = 26;
constexpr std::int16_t kWifiChannelGraphY =
    kWifiChannelInfoY + kWifiChannelInfoHeight;
constexpr std::int16_t kWifiChannelGraphHeight = 194;
constexpr std::int16_t kWifiChannelGraphBottom =
    kWifiChannelGraphY + kWifiChannelGraphHeight;
constexpr std::int16_t kWifiChannelAxisY = kWifiChannelGraphBottom + 5;
constexpr std::int16_t kWifiChannelBarX = 4;
constexpr std::int16_t kWifiChannelBarWidth = 13;
constexpr std::int16_t kWifiChannelBarStep = 18;
constexpr std::uint16_t kWifiChannelDisplayFullScalePermille = 80;
constexpr std::uint16_t kWifiChannelGraphBackground =
    leshy1::ui::visual::rgb565(0, 0, 0);
static_assert(kWifiChannelAxisY + 18 <= Layout::FooterDividerY,
              "Wi-Fi channel axis must stay above the footer");

std::uint16_t wifiChannelBarTone(std::uint16_t busyPermille,
                                 std::uint8_t channel) {
    if (busyPermille >= 80U) return Palette::Danger;
    if (busyPermille >= 40U) return Palette::Warning;
    return channel == 1U || channel == 6U || channel == 11U
        ? Palette::Positive : Palette::TextSecondary;
}

std::int16_t wifiChannelBarHeight(std::uint16_t busyPermille) {
    const std::uint32_t scaled =
        static_cast<std::uint32_t>(busyPermille) *
        kWifiChannelGraphHeight / kWifiChannelDisplayFullScalePermille;
    return static_cast<std::int16_t>(
        scaled > static_cast<std::uint32_t>(kWifiChannelGraphHeight)
            ? kWifiChannelGraphHeight : scaled);
}

void renderWifiChannelInfo(const WifiChannelLoadSnapshot& snapshot,
                           bool force) {
    const std::uint8_t best = wifiFrameCapture.bestPrimaryChannel();
    if (force) {
        display.setTextColor(Palette::TextMuted, Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 4, kWifiChannelInfoY + 5);
        display.print(tr(UiTextId::WifiChannelsScale));
    }
    if (!force && best == wifiChannelRenderedBest) return;
    constexpr std::int16_t rightX = 116;
    display.fillRect(rightX, kWifiChannelInfoY,
                     Layout::ScreenWidth - rightX,
                     kWifiChannelInfoHeight, Palette::Canvas);
    char line[40] = {};
    if (best == 0U) {
        std::snprintf(line, sizeof(line), "%s",
                      tr(UiTextId::WifiChannelsMeasuring));
    } else {
        std::snprintf(line, sizeof(line),
                      tr(UiTextId::WifiChannelsBestFormat),
                      static_cast<unsigned>(best));
    }
    selectUiFont(UiTextRole::Meta);
    const std::int16_t x = Layout::ScreenWidth - 4 - display.textWidth(line);
    display.setTextColor(best == 0U ? Palette::TextMuted : Palette::Focus,
                         Palette::Canvas);
    setUiCursor(UiTextRole::Meta, x < rightX ? rightX : x,
                kWifiChannelInfoY + 5);
    display.print(line);
    wifiChannelRenderedBest = best;
    (void)snapshot;
}

void renderWifiChannelBar(std::uint8_t channel,
                          const WifiChannelLoadSnapshot& snapshot,
                          bool force) {
    if (channel < 1U || channel > 13U) return;
    const std::size_t at = static_cast<std::size_t>(channel - 1U);
    const auto& bin = snapshot.channels[at];
    const std::uint16_t next = bin.measured ? bin.busyPermille : 0U;
    const std::uint16_t previous = wifiChannelRenderedLoads[at];
    if (!force && previous == next) return;
    const std::int16_t x = kWifiChannelBarX +
        static_cast<std::int16_t>(at) * kWifiChannelBarStep;
    const std::int16_t nextHeight = wifiChannelBarHeight(next);
    const std::int16_t previousHeight = previous == 0xffffU
        ? 0 : wifiChannelBarHeight(previous);
    if (force || nextHeight < previousHeight) {
        const std::int16_t clearTop = force
            ? kWifiChannelGraphY
            : kWifiChannelGraphBottom - previousHeight;
        const std::int16_t clearHeight = force
            ? kWifiChannelGraphHeight
            : previousHeight - nextHeight;
        if (clearHeight > 0) {
            display.fillRect(x, clearTop, kWifiChannelBarWidth, clearHeight,
                             kWifiChannelGraphBackground);
        }
    }
    if (nextHeight > 0) {
        display.fillRect(x, kWifiChannelGraphBottom - nextHeight,
                         kWifiChannelBarWidth, nextHeight,
                         wifiChannelBarTone(next, channel));
    }
    wifiChannelRenderedLoads[at] = next;
}

void renderWifiChannelsData(bool full) {
    const auto stats = wifiFrameCapture.channelMonitorStats();
    const WifiChannelLoadSnapshot snapshot =
        wifiFrameCapture.channelLoadSnapshot();
    if (full) {
        display.fillRect(0, kWifiChannelGraphY, Layout::ScreenWidth,
                         kWifiChannelGraphHeight,
                         kWifiChannelGraphBackground);
        const std::uint16_t grid =
            leshy1::ui::visual::rgb565(22, 36, 32);
        for (std::uint8_t division = 1U; division < 4U; ++division) {
            const std::int16_t y = kWifiChannelGraphY +
                kWifiChannelGraphHeight * division / 4;
            display.drawFastHLine(0, y, Layout::ScreenWidth, grid);
        }
        for (std::uint8_t channel = 1U; channel <= 13U; ++channel) {
            char label[4] = {};
            std::snprintf(label, sizeof(label), "%u",
                          static_cast<unsigned>(channel));
            selectUiFont(UiTextRole::Meta);
            const std::int16_t center = kWifiChannelBarX +
                static_cast<std::int16_t>(channel - 1U) *
                    kWifiChannelBarStep + kWifiChannelBarWidth / 2;
            const bool primary = channel == 1U || channel == 6U ||
                                 channel == 11U;
            display.setTextColor(primary ? Palette::Focus
                                         : Palette::TextMuted,
                                 Palette::Canvas);
            setUiCursor(UiTextRole::Meta,
                        center - display.textWidth(label) / 2,
                        kWifiChannelAxisY);
            display.print(label);
        }
    }
    renderWifiChannelInfo(snapshot, full);
    for (std::uint8_t channel = 1U; channel <= 13U; ++channel) {
        renderWifiChannelBar(channel, snapshot, full);
    }
    if (full && !stats.active) {
        display.fillRect(4, kWifiChannelGraphY + 70,
                         Layout::ScreenWidth - 8, 24,
                         kWifiChannelGraphBackground);
        display.setTextColor(Palette::Danger,
                             kWifiChannelGraphBackground);
        setUiCursor(UiTextRole::Meta, 14, kWifiChannelGraphY + 75);
        display.print(tr(UiTextId::WifiChannelsFailed));
    }
}

void renderWifiChannels(bool clearContent) {
    renderHeader(tr(UiTextId::WifiChannelsTitle), clearContent);
    renderWifiChannelsData(true);
}

UiTextId surveyFilterLabel(SurveyFilter filter) {
    switch (filter) {
        case SurveyFilter::Wifi: return UiTextId::FilterWifi;
        case SurveyFilter::Ble: return UiTextId::FilterBle;
        case SurveyFilter::All:
        default: return UiTextId::FilterAll;
    }
}

UiTextId surveyFilterBarFormat(SurveyFilter filter) {
    switch (filter) {
        case SurveyFilter::Wifi: return UiTextId::FilterBarWifiFormat;
        case SurveyFilter::Ble: return UiTextId::FilterBarBleFormat;
        case SurveyFilter::All:
        default: return UiTextId::FilterBarAllFormat;
    }
}

void renderSurveyFilterBar() {
    const bool selected = surveyController.filterFocused();
    const std::uint16_t background = selected ? Palette::SurfaceFocus
                                               : Palette::Surface;
    display.fillRoundRect(Layout::Edge, kSurveyFilterY, Layout::ContentWidth, 26,
                          Layout::Radius, background);
    renderFocusCue({Layout::Edge, kSurveyFilterY, Layout::ContentWidth, 26},
                   selected);
    display.setTextColor(selected ? Palette::Focus : Palette::TextSecondary,
                         background);
    char line[64] = {};
    std::snprintf(line, sizeof(line), tr(surveyFilterBarFormat(
                      surveyController.filter())),
                  static_cast<unsigned>(surveyController.visibleSize()));
    setUiCursor(UiTextRole::Body,
                Layout::Edge + kInteractiveRowTextInset,
                kSurveyFilterY + 3);
    display.print(line);
}

void renderSurveyFilterOption(std::uint8_t index) {
    if (index > static_cast<std::uint8_t>(SurveyFilter::Ble)) return;
    const SurveyFilter filter = static_cast<SurveyFilter>(index);
    char note[48] = {};
    std::snprintf(note, sizeof(note), tr(UiTextId::FilterCountFormat),
                  static_cast<unsigned>(surveyController.filterCount(filter)));
    renderMenuRow(Components::choiceRow(index), tr(surveyFilterLabel(filter)),
                  note, surveyController.draftFilter() == filter, true,
                  filter == surveyController.filter() ? Tone::Positive
                                                       : Tone::Neutral);
}

void renderRssiHistory(const ObservationHistory& history) {
    if (!history.valid || history.retainedSamples == 0) return;
    char line[64] = {};
    std::snprintf(line, sizeof(line), tr(UiTextId::SignalRangeFormat),
                  static_cast<int>(history.minimumRssiDbm),
                  static_cast<int>(history.maximumRssiDbm));
    display.setTextColor(Palette::Positive, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 199);
    display.print(line);

    constexpr std::int16_t x = 136;
    constexpr std::int16_t y = 187;
    constexpr std::int16_t width = 90;
    constexpr std::int16_t height = 35;
    display.drawRoundRect(x, y, width, height, Layout::Radius, Palette::Divider);
    const auto pointY = [&](std::int16_t rssi) {
        const std::int16_t bounded = rssi < -100 ? -100 : (rssi > -20 ? -20 : rssi);
        return static_cast<std::int16_t>(
            y + height - 3 - ((bounded + 100) * (height - 6)) / 80);
    };
    if (history.retainedSamples == 1) {
        display.fillCircle(x + width / 2, pointY(history.samples[0]), 2,
                           Palette::Focus);
        return;
    }
    for (std::uint8_t index = 1; index < history.retainedSamples; ++index) {
        const std::int16_t previousX = static_cast<std::int16_t>(
            x + 3 + ((index - 1U) * (width - 6)) /
                        (history.retainedSamples - 1U));
        const std::int16_t currentX = static_cast<std::int16_t>(
            x + 3 + (index * (width - 6)) /
                        (history.retainedSamples - 1U));
        display.drawLine(previousX, pointY(history.samples[index - 1U]),
                         currentX, pointY(history.samples[index]),
                         Palette::Focus);
    }
}

UiTextId surveySourceLabel(const SurveySourceOption& source) {
    return source.kind == SurveySourceKind::Wifi
        ? UiTextId::SourceWifiRow : UiTextId::SourceBleRow;
}

UiTextId surveySourceNote(const SurveySourceOption& source) {
    if (source.state == SurveySourceState::Available) {
        return source.selected ? UiTextId::SourceOnReady
                               : UiTextId::SourceOffReady;
    }
    if (source.state == SurveySourceState::Conflicted) {
        return UiTextId::SourceConflicted;
    }
    if (source.state == SurveySourceState::Fault) {
        return UiTextId::SourceFault;
    }
    return UiTextId::SourceDriverPending;
}

Rect surveyPlanRowBounds(std::uint8_t index) {
    return Components::choiceRow(index);
}

void renderSurveyPlanRow(std::uint8_t index) {
    if (index >= surveySourceController.planItemCount()) return;
    char note[48] = {};
    const bool selected = surveySourceController.selection() == index;
    if (surveySourceController.scope() != SurveySourceScope::All) {
        const bool wifi = surveySourceController.scope() ==
                          SurveySourceScope::WifiOnly;
        const bool ready = surveySourceController.canStart();
        renderMenuRow(surveyPlanRowBounds(index),
                      tr(wifi ? UiTextId::WifiScanStart
                              : UiTextId::BleScanStart),
                      tr(ready ? UiTextId::StartReady
                               : UiTextId::StartNeedsSource),
                      selected, ready,
                      ready ? Tone::Positive : Tone::Warning);
        return;
    }
    if (index == 0) {
        if (surveySourceController.simulatedPreview() &&
            surveySourceController.selectedCount() == 0) {
            std::snprintf(note, sizeof(note), "%s", tr(UiTextId::SourcesPreview));
        } else {
            std::snprintf(note, sizeof(note), tr(UiTextId::SourcesCountFormat),
                          static_cast<unsigned>(
                              surveySourceController.selectedCount()),
                          static_cast<unsigned>(
                              SurveySourceController::kSourceCount));
        }
        renderMenuRow(surveyPlanRowBounds(index), tr(UiTextId::PlanSources),
                      note, selected, true, Tone::Positive);
        return;
    }
    if (index == 1) {
        const bool available = BoardProfile::kRfShieldDeclared &&
            !BoardProfile::kGpsDeclared && !BoardProfile::kPn532Declared;
        renderMenuRow(surveyPlanRowBounds(index), tr(UiTextId::PlanSpectrum),
                      tr(available ? UiTextId::SpectrumReady
                                   : UiTextId::SpectrumUnavailable),
                      selected, available,
                      available ? Tone::Positive : Tone::Warning);
        return;
    }
    const bool preparing =
        std::strcmp(productSurveyRuntime.status, "preparing") == 0;
    const bool cancelling =
        std::strcmp(productSurveyRuntime.status, "cancelling") == 0;
    const bool ready = surveySourceController.canStart() &&
                       !preparing && !cancelling;
    const UiTextId startNote = preparing
        ? UiTextId::StartPreparing
        : (cancelling
               ? UiTextId::StartCancelling
               : (!ready
                      ? UiTextId::StartNeedsSource
                      : (surveySourceController.simulatedPreview()
                             ? UiTextId::StartPreview
                             : UiTextId::StartReady)));
    renderMenuRow(surveyPlanRowBounds(index), tr(UiTextId::PlanStart),
                  tr(startNote), selected, ready,
                  ready ? Tone::Positive : Tone::Warning);
}

void renderSurveySourceRow(std::uint8_t index) {
    const SurveySourceOption* source = surveySourceController.get(index);
    if (source == nullptr) return;
    const bool selected = surveySourceController.selection() == index;
    renderMenuRow(Components::choiceRow(index), tr(surveySourceLabel(*source)),
                  tr(surveySourceNote(*source)), selected,
                  source->available(),
                  source->selected ? Tone::Positive : Tone::Muted);
}

constexpr std::uint8_t kWifiProductTaskCount = 4;

UiTextId wifiProductLabel(std::uint8_t index) {
    constexpr UiTextId labels[kWifiProductTaskCount] = {
        UiTextId::WifiMenuNetworks,
        UiTextId::WifiMenuDevices,
        UiTextId::WifiMenuChannels,
        UiTextId::WifiMenuCapture,
    };
    return labels[index < kWifiProductTaskCount ? index : 0];
}

UiTextId wifiProductNote(std::uint8_t index) {
    constexpr UiTextId notes[kWifiProductTaskCount] = {
        UiTextId::WifiMenuNetworksNote,
        UiTextId::WifiMenuDevicesNote,
        UiTextId::WifiMenuChannelsNote,
        UiTextId::WifiMenuCaptureNote,
    };
    return notes[index < kWifiProductTaskCount ? index : 0];
}

bool wifiProductTaskReady(std::uint8_t index) {
    // Functions are admitted one at a time. The menu stays truthful while the
    // remaining radio workflows are being implemented and measured.
    return index <= 3U;
}

void renderWifiProductRow(std::uint8_t index) {
    if (index >= kWifiProductTaskCount) return;
    const bool ready = wifiProductTaskReady(index);
    renderMenuRow(Components::homeRow(index), tr(wifiProductLabel(index)),
                  tr(ready ? wifiProductNote(index) : UiTextId::WifiMenuNext),
                  wifiProductSelection == index, ready,
                  ready ? Tone::Positive : Tone::Muted);
}

void renderWifiProductMenu(bool clearContent) {
    renderHeader(tr(UiTextId::WifiMenuTitle), clearContent);
    for (std::uint8_t index = 0; index < kWifiProductTaskCount; ++index) {
        renderWifiProductRow(index);
    }
}

void renderRfSpectrumSourceRow(std::uint8_t index) {
    if (index >= 2) return;
    const bool selected = rfSpectrumSelection == index;
    const bool available = BoardProfile::kRfShieldDeclared &&
        !BoardProfile::kGpsDeclared && !BoardProfile::kPn532Declared;
    renderMenuRow(Components::choiceRow(index),
                  tr(index == 0 ? UiTextId::SpectrumNrf24
                                : UiTextId::SpectrumCc1101),
                  tr(available ? UiTextId::SpectrumRxReady
                               : UiTextId::SpectrumUnavailable),
                  selected, available,
                  available ? Tone::Positive : Tone::Muted);
}

void renderRfSpectrumSourceMenu(bool clearContent) {
    renderHeader(tr(UiTextId::SpectrumSources), clearContent);
    renderRfSpectrumSourceRow(0);
    renderRfSpectrumSourceRow(1);
}

void renderSubGhzModeMenu(bool clearContent) {
    renderHeader(tr(UiTextId::SubGhzModes), clearContent);
    renderMenuRow(Components::choiceRow(0), tr(UiTextId::SubGhzSpectrum),
                  tr(UiTextId::SubGhzSpectrumNote),
                  subGhzModeSelection == 0, true, Tone::Positive);
    renderMenuRow(Components::choiceRow(1), tr(UiTextId::SubGhzRaw),
                  tr(UiTextId::SubGhzRawNote),
                  subGhzModeSelection == 1, true, Tone::Positive);
}

leshy1::drivers::radio::Cc1101SpectrumBand ccBandFromIndex(
    std::uint8_t index) {
    const std::uint8_t count = static_cast<std::uint8_t>(
        leshy1::drivers::radio::Cc1101SpectrumBand::Count);
    return static_cast<leshy1::drivers::radio::Cc1101SpectrumBand>(
        index < count ? index : 0);
}

std::uint8_t ccBandSelectionIndex() {
    return static_cast<std::uint8_t>(rfCcBandSelection);
}

void renderRfCcBandRow(std::uint8_t index) {
    if (index >= static_cast<std::uint8_t>(
            leshy1::drivers::radio::Cc1101SpectrumBand::Count)) return;
    const auto band = ccBandFromIndex(index);
    const auto plan = leshy1::drivers::radio::cc1101PassiveSpectrumPlan(band);
    char label[40] = {};
    char note[48] = {};
    std::snprintf(label, sizeof(label),
                  tr(UiTextId::CcSpectrumBandChoiceFormat),
                  leshy1::drivers::radio::cc1101SpectrumBandName(band));
    std::snprintf(note, sizeof(note),
                  tr(UiTextId::CcSpectrumBandRangeFormat),
                  static_cast<unsigned long>(plan.firstKHz / 1000U),
                  static_cast<unsigned long>(plan.firstKHz % 1000U),
                  static_cast<unsigned long>(plan.lastKHz / 1000U),
                  static_cast<unsigned long>(plan.lastKHz % 1000U));
    renderMenuRow(Components::homeRow(index), label, note,
                  rfCcBandSelection == band, true, Tone::Positive);
}

void renderRfCcBandMenu(bool clearContent) {
    renderHeader(tr(UiTextId::CcSpectrumBands), clearContent);
    for (std::uint8_t index = 0; index < 4; ++index) {
        renderRfCcBandRow(index);
    }
}

std::uint32_t subGhzCaptureFrequencyKHz(
    leshy1::drivers::radio::Cc1101SpectrumBand band) {
    switch (band) {
        case leshy1::drivers::radio::Cc1101SpectrumBand::Band315:
            return 315000;
        case leshy1::drivers::radio::Cc1101SpectrumBand::Band433:
            return 433920;
        case leshy1::drivers::radio::Cc1101SpectrumBand::Band868:
            return 868350;
        case leshy1::drivers::radio::Cc1101SpectrumBand::Band915:
            return 915000;
        case leshy1::drivers::radio::Cc1101SpectrumBand::Count:
            break;
    }
    return 433920;
}

void renderSubGhzCaptureBandMenu(bool clearContent) {
    renderHeader(tr(UiTextId::SubGhzRawBands), clearContent);
    for (std::uint8_t index = 0; index < 4; ++index) {
        renderRfCcBandRow(index);
    }
}

void renderSubGhzRawCapturePage(bool clearContent) {
    const auto& stats = subGhzRawCapture.stats();
    const UiTextId title = stats.state == SubGhzRawCaptureState::Waiting
        ? UiTextId::SubGhzRawWaiting
        : stats.state == SubGhzRawCaptureState::Capturing
              ? UiTextId::SubGhzRawCapturing
              : stats.state == SubGhzRawCaptureState::Complete
                    ? UiTextId::SubGhzRawComplete
                    : stats.state == SubGhzRawCaptureState::TimedOut
                          ? UiTextId::SubGhzRawTimedOut
                          : stats.state ==
                                    SubGhzRawCaptureState::SignalTooLong
                                ? UiTextId::SubGhzRawTooLong
                          : UiTextId::SubGhzRawFailed;
    renderHeader(tr(title), clearContent);
    char line[96] = {};
    const auto& plan = subGhzRawCapture.plan();
    std::snprintf(line, sizeof(line), tr(UiTextId::SubGhzRawFrequencyFormat),
                  static_cast<unsigned long>(plan.frequencyKHz / 1000U),
                  static_cast<unsigned long>(plan.frequencyKHz % 1000U));
    if (stats.state == SubGhzRawCaptureState::Waiting) {
        renderMetric(0, line, Tone::Positive);
        renderMetric(1, tr(UiTextId::SubGhzPressButton));
        renderMetric(2, tr(UiTextId::SubGhzWaitUser));
        return;
    }
    if (stats.state == SubGhzRawCaptureState::Capturing) {
        renderMetric(0, tr(UiTextId::SubGhzSignalDetected), Tone::Positive);
        renderMetric(1, tr(UiTextId::SubGhzKeepPressed));
        renderMetric(2, line);
        return;
    }
    if (stats.state == SubGhzRawCaptureState::Complete) {
        renderMetric(0, tr(UiTextId::SubGhzSignalRecorded), Tone::Positive);
        renderMetric(1, line);
        const UiTextId storageMessage =
            subGhzCapturePersistState == CapturePersistState::Saving
                ? UiTextId::CaptureSavingUser
                : subGhzCapturePersistState == CapturePersistState::Saved
                      ? UiTextId::CaptureSavedUser
                      : subGhzCapturePersistState == CapturePersistState::Failed
                            ? UiTextId::CaptureSaveFailedUser
                            : UiTextId::CaptureReadyToSave;
        renderMetric(2, tr(storageMessage),
                     subGhzCapturePersistState == CapturePersistState::Failed
                         ? Tone::Danger : Tone::Positive);
        return;
    }
    if (stats.state == SubGhzRawCaptureState::TimedOut) {
        renderMetric(0, line);
        renderMetric(1, tr(UiTextId::SubGhzTryCloser), Tone::Warning);
        renderMetric(2, tr(UiTextId::CaptureTryAgainUser));
        return;
    }
    if (stats.state == SubGhzRawCaptureState::SignalTooLong) {
        renderMetric(0, tr(UiTextId::SubGhzSignalDetected), Tone::Warning);
        renderMetric(1, tr(UiTextId::SubGhzReleaseButton), Tone::Danger);
        return;
    }
    renderMetric(0, tr(UiTextId::SubGhzReceiverFailed), Tone::Danger);
    renderMetric(1, tr(UiTextId::CaptureTryAgainUser));
}

constexpr std::int16_t kSpectrumOverlayY = Layout::HeaderHeight;
constexpr std::int16_t kSpectrumOverlayHeight = 28;
constexpr std::int16_t kSpectrumAxisHeight = 15;
constexpr std::int16_t kSpectrumAxisY =
    Layout::FooterDividerY - kSpectrumAxisHeight;
constexpr std::int16_t kSpectrumGraphY =
    kSpectrumOverlayY + kSpectrumOverlayHeight;
constexpr std::int16_t kSpectrumGraphHeight =
    kSpectrumAxisY - kSpectrumGraphY;
static_assert(kSpectrumGraphHeight == SpectrumViewport::kHistoryRows,
              "each waterfall sample must occupy exactly one TFT row");
static_assert(Layout::ScreenWidth == SpectrumViewport::kDisplayColumns,
              "the expanded spectrum scanline must span the TFT width");
constexpr std::uint16_t kSpectrumNoSignal =
    leshy1::ui::visual::rgb565(0, 0, 0);
constexpr std::uint16_t kWifiChannelDivider =
    leshy1::ui::visual::rgb565(24, 44, 40);
constexpr std::uint16_t kWifiPrimaryChannelDivider =
    leshy1::ui::visual::rgb565(104, 84, 16);
constexpr std::uint8_t kSpectrumQuietThreshold = 8;

std::int16_t wifiChannelCenterX(std::uint8_t channel) {
    const std::uint16_t frequencyMhz = static_cast<std::uint16_t>(
        2412U + static_cast<std::uint16_t>(channel - 1U) * 5U);
    return static_cast<std::int16_t>(
        (static_cast<std::uint32_t>(frequencyMhz - 2402U) *
             (Layout::ScreenWidth - 1) + 41U) /
        82U);
}

std::uint16_t spectrumTone(std::uint8_t intensity) {
    if (intensity < kSpectrumQuietThreshold) return kSpectrumNoSignal;
    if (intensity < 64U) {
        return leshy1::ui::visual::rgb565(
            0, static_cast<std::uint8_t>(intensity * 2U), 196);
    }
    if (intensity < 128U) {
        return leshy1::ui::visual::rgb565(
            0, static_cast<std::uint8_t>(128U + intensity),
            static_cast<std::uint8_t>(255U - (intensity - 64U) * 3U));
    }
    if (intensity < 192U) {
        return leshy1::ui::visual::rgb565(
            static_cast<std::uint8_t>((intensity - 128U) * 4U), 255, 0);
    }
    return leshy1::ui::visual::rgb565(
        255, static_cast<std::uint8_t>(255U - (intensity - 192U) * 4U), 0);
}

std::uint16_t wifiChannelGridTone(std::int16_t x,
                                  std::uint8_t intensity) {
    const std::uint16_t signal = spectrumTone(intensity);
    if (intensity >= kSpectrumQuietThreshold) return signal;
    for (std::uint8_t channel = 1; channel <= 13; ++channel) {
        if (x != wifiChannelCenterX(channel)) continue;
        return channel == 1 || channel == 6 || channel == 11
            ? kWifiPrimaryChannelDivider : kWifiChannelDivider;
    }
    return signal;
}

const char* spectrumDisplayModeText() {
    return tr(spectrumViewport.mode() == SpectrumDisplayMode::Spectrum
                  ? UiTextId::SpectrumDisplaySpectrum
                  : UiTextId::SpectrumDisplayWaterfall);
}

std::size_t activeSpectrumBins() {
    return rfSpectrumKind == RfSpectrumKind::Cc1101
        ? Cc1101SpectrumController::kBinCount
        : Nrf24SpectrumController::kChannelCount;
}

std::uint8_t activeSpectrumIntensity(std::size_t bin) {
    return rfSpectrumKind == RfSpectrumKind::Cc1101
        ? cc1101SpectrumController.intensity(bin)
        : nrf24SpectrumController.displayIntensity(bin);
}

bool pushActiveSpectrumHistory() {
    const std::size_t bins = activeSpectrumBins();
    for (std::size_t bin = 0; bin < bins; ++bin) {
        spectrumIntensity[bin] = activeSpectrumIntensity(bin);
    }
    return spectrumViewport.push(spectrumIntensity.data(), bins);
}

void prepareWaterfallScanline(std::size_t row) {
    for (std::int16_t x = 0; x < Layout::ScreenWidth; ++x) {
        const std::uint8_t intensity = spectrumViewport.intensity(
            row, static_cast<std::size_t>(x));
        spectrumScanline[static_cast<std::size_t>(x)] =
            rfSpectrumKind == RfSpectrumKind::Nrf24
                ? wifiChannelGridTone(x, intensity)
                : spectrumTone(intensity);
    }
}

void renderWaterfallSlot(std::size_t row) {
    if (!spectrumViewport.rowValid(row)) return;
    prepareWaterfallScanline(row);
    const std::int16_t firstY = kSpectrumGraphY +
        static_cast<std::int32_t>(row) * kSpectrumGraphHeight /
            SpectrumViewport::kHistoryRows;
    const std::int16_t nextY = kSpectrumGraphY +
        static_cast<std::int32_t>(row + 1U) * kSpectrumGraphHeight /
            SpectrumViewport::kHistoryRows;
    for (std::int16_t y = firstY; y < nextY; ++y) {
        display.pushImage(0, y, Layout::ScreenWidth, 1,
                          spectrumScanline.data());
    }
}

void renderWaterfallCursor() {
    const std::int16_t y = kSpectrumGraphY +
        static_cast<std::int32_t>(spectrumViewport.nextRow()) *
            kSpectrumGraphHeight / SpectrumViewport::kHistoryRows;
    display.drawFastHLine(0, y < kSpectrumAxisY ? y : kSpectrumGraphY,
                          Layout::ScreenWidth, Palette::Divider);
}

void renderSpectrumWaterfall() {
    display.fillRect(0, kSpectrumGraphY, Layout::ScreenWidth,
                     kSpectrumGraphHeight, kSpectrumNoSignal);
    for (std::size_t row = 0; row < SpectrumViewport::kHistoryRows; ++row) {
        renderWaterfallSlot(row);
    }
    renderWaterfallCursor();
}

void renderLatestWaterfallRow() {
    renderWaterfallSlot(spectrumViewport.latestRow());
    renderWaterfallCursor();
}

void renderSpectrumBars() {
    display.fillRect(0, kSpectrumGraphY, Layout::ScreenWidth,
                     kSpectrumGraphHeight, Palette::Surface);
    const std::size_t bins = activeSpectrumBins();
    for (std::size_t bin = 0; bin < bins; ++bin) {
        spectrumIntensity[bin] = activeSpectrumIntensity(bin);
    }
    for (std::int16_t x = 0; x < Layout::ScreenWidth; ++x) {
        const std::uint8_t intensity = SpectrumViewport::resample(
            spectrumIntensity.data(), bins, static_cast<std::size_t>(x));
        const std::int16_t height = intensity == 0
            ? 1
            : static_cast<std::int16_t>(1 +
                  static_cast<std::uint32_t>(intensity) *
                      (kSpectrumGraphHeight - 1) / 255U);
        display.drawFastVLine(x, kSpectrumAxisY - height, height,
                              spectrumTone(intensity));
    }
}

void renderActiveSpectrumData() {
    if (spectrumViewport.mode() == SpectrumDisplayMode::Waterfall) {
        renderSpectrumWaterfall();
    } else {
        renderSpectrumBars();
    }
}

void renderSpectrumModeAtRight() {
    const char* mode = spectrumDisplayModeText();
    selectUiFont(UiTextRole::Meta);
    const std::int16_t width = display.textWidth(mode);
    display.setTextColor(Palette::Focus, Palette::Surface);
    setUiCursor(UiTextRole::Meta, Layout::ScreenWidth - 4 - width,
                kSpectrumOverlayY);
    display.print(mode);
}

void renderSpectrumLegend(UiTextId receiverState, Tone tone,
                          UiTextId quietId = UiTextId::SpectrumLegendQuiet,
                          UiTextId strongId = UiTextId::SpectrumLegendStrong,
                          UiTextId metricId = UiTextId::Count) {
    display.fillRect(0, kSpectrumOverlayY, Layout::ScreenWidth,
                     kSpectrumOverlayHeight, Palette::Surface);
    display.setTextColor(tone == Tone::Danger ? Palette::Danger
                                              : Palette::Positive,
                         Palette::Surface);
    setUiCursor(UiTextRole::Meta, 4, kSpectrumOverlayY);
    display.print(tr(receiverState));
    if (metricId != UiTextId::Count) {
        display.print(tr(UiTextId::SpectrumModeSeparator));
        display.print(tr(metricId));
    }
    renderSpectrumModeAtRight();

    constexpr std::int16_t kLegendGap = 5;
    constexpr std::int16_t kLegendTop = kSpectrumOverlayY + 14;
    constexpr std::int16_t kLegendBarTop = kLegendTop + 3;
    constexpr std::int16_t kLegendBarHeight = 7;
    const char* quiet = tr(quietId);
    const char* strong = tr(strongId);
    selectUiFont(UiTextRole::Meta);
    const std::int16_t quietWidth = display.textWidth(quiet);
    const std::int16_t strongWidth = display.textWidth(strong);
    const std::int16_t strongX = Layout::ScreenWidth - 4 - strongWidth;
    const std::int16_t barX = 4 + quietWidth + kLegendGap;
    const std::int16_t barWidth = strongX - kLegendGap - barX;
    display.setTextColor(Palette::TextSecondary, Palette::Surface);
    setUiCursor(UiTextRole::Meta, 4, kLegendTop);
    display.print(quiet);
    setUiCursor(UiTextRole::Meta, strongX, kLegendTop);
    display.print(strong);
    for (std::int16_t x = 0; x < barWidth; ++x) {
        const std::uint8_t intensity = static_cast<std::uint8_t>(
            static_cast<std::uint32_t>(x) * 255U /
            static_cast<std::uint32_t>(barWidth - 1));
        display.drawFastVLine(barX + x, kLegendBarTop, kLegendBarHeight,
                              spectrumTone(intensity));
    }
}

void renderNrf24SpectrumLegend() {
    const Nrf24SpectrumViewState state = nrf24SpectrumController.state();
    const bool traffic = nrf24SpectrumController.metric() ==
        Nrf24SpectrumMetric::Traffic;
    renderSpectrumLegend(
        state == Nrf24SpectrumViewState::Running
            ? UiTextId::SpectrumOverlayRunning
            : (state == Nrf24SpectrumViewState::Paused
                   ? UiTextId::SpectrumOverlayPaused : UiTextId::SpectrumFault),
        state == Nrf24SpectrumViewState::Fault ? Tone::Danger : Tone::Positive,
        traffic ? UiTextId::SpectrumLegendBaseline
                : UiTextId::SpectrumLegendQuiet,
        traffic ? UiTextId::SpectrumLegendBurst
                : UiTextId::SpectrumLegendStrong,
        traffic ? UiTextId::SpectrumMetricTraffic
                : UiTextId::SpectrumMetricSignal);
}

void renderNrf24SpectrumAxis() {
    display.fillRect(0, kSpectrumAxisY, Layout::ScreenWidth,
                     kSpectrumAxisHeight, Palette::Canvas);
    selectUiFont(UiTextRole::Meta);
    for (std::uint8_t channel = 1; channel <= 13; ++channel) {
        const std::int16_t centerX = wifiChannelCenterX(channel);
        const bool primary = channel == 1 || channel == 6 || channel == 11;
        display.drawFastVLine(centerX, kSpectrumAxisY, 2,
            primary ? kWifiPrimaryChannelDivider : kWifiChannelDivider);
        char label[3] = {};
        std::snprintf(label, sizeof(label), "%u",
                      static_cast<unsigned>(channel));
        const std::int16_t width = display.textWidth(label);
        display.setTextColor(primary ? Palette::Warning : Palette::TextMuted,
                             Palette::Canvas);
        setUiCursor(UiTextRole::Meta, centerX - width / 2,
                    kSpectrumAxisY + 2);
        display.print(label);
    }
}

void renderNrf24SpectrumPage(bool clearContent) {
    renderHeader(tr(UiTextId::SpectrumTitle), clearContent);
    renderActiveSpectrumData();
    renderNrf24SpectrumLegend();
    renderNrf24SpectrumAxis();
}

void formatCcFrequency(std::uint32_t frequencyKHz, char* output,
                       std::size_t capacity) {
    if (output == nullptr || capacity == 0) return;
    std::snprintf(output, capacity, "%lu.%03lu",
                  static_cast<unsigned long>(frequencyKHz / 1000U),
                  static_cast<unsigned long>(frequencyKHz % 1000U));
}

void renderCc1101SpectrumAxis() {
    display.fillRect(0, kSpectrumAxisY, Layout::ScreenWidth,
                     kSpectrumAxisHeight, Palette::Canvas);
    const Cc1101PassiveSpectrumPlan plan = cc1101SpectrumController.plan();
    char first[16] = {};
    char middle[16] = {};
    char last[16] = {};
    formatCcFrequency(plan.firstKHz, first, sizeof(first));
    formatCcFrequency(plan.firstKHz + (plan.lastKHz - plan.firstKHz) / 2U,
                      middle, sizeof(middle));
    formatCcFrequency(plan.lastKHz, last, sizeof(last));
    display.setTextColor(Palette::TextMuted, Palette::Canvas);
    selectUiFont(UiTextRole::Meta);
    setUiCursor(UiTextRole::Meta, 2, kSpectrumAxisY);
    display.print(first);
    setUiCursor(UiTextRole::Meta,
                (Layout::ScreenWidth - display.textWidth(middle)) / 2,
                kSpectrumAxisY);
    display.print(middle);
    setUiCursor(UiTextRole::Meta,
                Layout::ScreenWidth - 2 - display.textWidth(last),
                kSpectrumAxisY);
    display.print(last);
}

void renderCc1101SpectrumLegend() {
    const Cc1101SpectrumViewState state = cc1101SpectrumController.state();
    renderSpectrumLegend(
        state == Cc1101SpectrumViewState::Running
            ? UiTextId::CcSpectrumOverlayRunning
            : (state == Cc1101SpectrumViewState::Paused
                   ? UiTextId::CcSpectrumOverlayPaused : UiTextId::SpectrumFault),
        state == Cc1101SpectrumViewState::Fault ? Tone::Danger : Tone::Positive);
}

void renderCc1101SpectrumPage(bool clearContent) {
    renderHeader(tr(UiTextId::CcSpectrumTitle), clearContent);
    renderActiveSpectrumData();
    renderCc1101SpectrumLegend();
    renderCc1101SpectrumAxis();
}

void renderInventoryPage(bool clearContent) {
    char line[96] = {};
    if (bleProductView == BleProductView::DeviceDetail) {
        renderBleDeviceDetail(clearContent);
        return;
    }
    if (bleProductView == BleProductView::Devices) {
        renderBleDevices(clearContent);
        return;
    }
    if (wifiProductView == WifiProductView::Menu) {
        renderWifiProductMenu(clearContent);
        return;
    }
    if (wifiProductView == WifiProductView::NetworkDetail) {
        renderWifiNetworkDetail(clearContent);
        return;
    }
    if (wifiProductView == WifiProductView::DeviceDetail) {
        renderWifiDeviceDetail(clearContent);
        return;
    }
    if (wifiProductView == WifiProductView::DeviceRadar) {
        renderWifiDeviceRadar(clearContent);
        return;
    }
    if (wifiProductView == WifiProductView::Channels) {
        renderWifiChannels(clearContent);
        return;
    }
    if (wifiProductView == WifiProductView::Capture) {
        renderWifiCapturePage(clearContent);
        return;
    }
    if (wifiProductView == WifiProductView::Devices) {
        renderWifiDevices(clearContent);
        return;
    }
    if (rfSpectrumView == RfSpectrumView::SourceMenu) {
        renderRfSpectrumSourceMenu(clearContent);
        return;
    }
    if (rfSpectrumView == RfSpectrumView::SubGhzMenu) {
        renderSubGhzModeMenu(clearContent);
        return;
    }
    if (rfSpectrumView == RfSpectrumView::CcBandMenu) {
        renderRfCcBandMenu(clearContent);
        return;
    }
    if (rfSpectrumView == RfSpectrumView::SubGhzCaptureBandMenu) {
        renderSubGhzCaptureBandMenu(clearContent);
        return;
    }
    if (rfSpectrumView == RfSpectrumView::SubGhzCaptureLive) {
        renderSubGhzRawCapturePage(clearContent);
        return;
    }
    if (rfSpectrumView == RfSpectrumView::Live) {
        if (rfSpectrumKind == RfSpectrumKind::Cc1101) {
            renderCc1101SpectrumPage(clearContent);
        } else {
            renderNrf24SpectrumPage(clearContent);
        }
        return;
    }
    if (wifiProductView == WifiProductView::Networks &&
        surveyWorkflow.state() == SurveyWorkflowState::Setup &&
        std::strcmp(productSurveyRuntime.status, "preparing") == 0) {
        renderHeader(tr(UiTextId::WifiMenuNetworks), clearContent);
        renderMetric(0, tr(UiTextId::SurveySearchWifi), Tone::Positive);
        return;
    }
    if (wifiProductView == WifiProductView::Networks &&
        surveyWorkflow.state() == SurveyWorkflowState::Running) {
        renderWifiNetworks(clearContent);
        return;
    }
    if (productSurveySourceUnavailableVisible()) {
        renderHeader(tr(UiTextId::SurveyUnavailable), clearContent);
        display.setTextColor(Palette::Danger, Palette::Canvas);
        setUiCursor(UiTextRole::Body, 14, 82);
        display.print(tr(UiTextId::SourceUnavailableReason));
        display.setTextColor(Palette::TextSecondary, Palette::Canvas);
        setUiCursor(UiTextRole::Body, 14, 116);
        display.print(tr(UiTextId::NoSessionCreated));
        setUiCursor(UiTextRole::Body, 14, 150);
        display.print(tr(UiTextId::PriorLibraryPreserved));
        display.setTextColor(Palette::Positive, Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 207);
        display.print(tr(UiTextId::BackNoRetry));
        return;
    }
    if (surveyWorkflow.state() == SurveyWorkflowState::Setup) {
        if (surveySourceController.view() == SurveySetupView::Sources) {
            renderHeader(tr(UiTextId::SurveySources), clearContent);
            for (std::uint8_t index = 0;
                 index < SurveySourceController::kSourceCount; ++index) {
                renderSurveySourceRow(index);
            }
        } else {
            const UiTextId title = surveySourceController.scope() ==
                    SurveySourceScope::WifiOnly
                ? UiTextId::WifiScanSetup
                : (surveySourceController.scope() ==
                           SurveySourceScope::BleOnly
                       ? UiTextId::BleScanSetup
                       : UiTextId::SurveySetup);
            renderHeader(tr(title), clearContent);
            for (std::uint8_t index = 0;
                 index < surveySourceController.planItemCount(); ++index) {
                renderSurveyPlanRow(index);
            }
        }
        if (surveySourceController.view() == SurveySetupView::Sources) {
            display.setTextColor(Palette::Positive, Palette::Canvas);
            setUiCursor(UiTextRole::Meta, 14, 207);
            display.print(tr(UiTextId::SurveyChooseSources));
        }
        return;
    }
    if (surveyWorkflow.state() == SurveyWorkflowState::Result) {
        renderHeader(tr(UiTextId::SurveyCommitted), clearContent);
        std::snprintf(line, sizeof(line), tr(UiTextId::SurveyFoundFormat),
                      static_cast<unsigned>(surveySession.size()));
        renderMetric(0, line, Tone::Positive);
        renderMetric(1, tr(surveyWorkflow.persistent()
                               ? UiTextId::SurveyResultsSaved
                               : UiTextId::SurveyResultsTemporary),
                     surveyWorkflow.persistent() ? Tone::Positive
                                                 : Tone::Warning);
        return;
    }
    if (surveyWorkflow.state() == SurveyWorkflowState::Error) {
        renderHeader(tr(UiTextId::SurveyError), clearContent);
        renderMetric(0, tr(UiTextId::SurveyCouldNotStart), Tone::Danger);
        renderMetric(1, tr(UiTextId::SurveyPreviousSafe));
        renderMetric(2, tr(UiTextId::CaptureTryAgainUser));
        return;
    }
    if (surveyController.view() == SurveyView::Filter) {
        renderHeader(tr(UiTextId::SurveyFilter), clearContent);
        for (std::uint8_t index = 0;
             index <= static_cast<std::uint8_t>(SurveyFilter::Ble); ++index) {
            renderSurveyFilterOption(index);
        }
        return;
    }
    if (surveyController.view() == SurveyView::Detail) {
        renderHeader(tr(UiTextId::SurveyDetail), clearContent);
        const Observation* observation = surveyController.selected();
        if (observation == nullptr) return;
        display.setTextFont(4);
        activeDisplayFont = ActiveDisplayFont::None;
        display.setTextColor(Palette::Focus, Palette::Canvas);
        display.setCursor(14, 88);
        display.print(observation->label.data());
        display.setTextColor(Palette::TextSecondary, Palette::Canvas);
        if (observation->radio == RadioKind::Ble) {
            setUiCursor(UiTextRole::Body, 14, 122);
            display.print(tr(UiTextId::BluetoothDevice));
            std::snprintf(
                line, sizeof(line), tr(UiTextId::BleAddressFormat),
                static_cast<unsigned>(observation->identity[0]),
                static_cast<unsigned>(observation->identity[1]),
                static_cast<unsigned>(observation->identity[2]),
                static_cast<unsigned>(observation->identity[3]),
                static_cast<unsigned>(observation->identity[4]),
                static_cast<unsigned>(observation->identity[5]));
            setUiCursor(UiTextRole::Meta, 14, 151);
            display.print(line);
        } else {
            std::snprintf(line, sizeof(line), tr(UiTextId::ChannelFormat),
                          static_cast<unsigned>(observation->channel));
            setUiCursor(UiTextRole::Body, 14, 122);
            display.print(line);
        }
        std::snprintf(line, sizeof(line), tr(UiTextId::RssiFormat),
                      static_cast<int>(observation->rssiDbm));
        setUiCursor(UiTextRole::Body, 14,
                    observation->radio == RadioKind::Ble ? 174 : 148);
        display.print(line);
        const ObservationHistory history = surveyController.selectedHistory();
        if (history.valid) {
            renderRssiHistory(history);
        } else {
            display.setTextColor(Palette::Positive, Palette::Canvas);
            setUiCursor(UiTextRole::Meta, 14, 203);
            display.print(tr(UiTextId::NoSignalHistory));
        }
        return;
    }

    renderHeader(tr(UiTextId::SurveyRunning), clearContent);
    display.setTextColor(Palette::Positive, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 70);
    if (std::strcmp(productSurveyRuntime.status, "paused") == 0) {
        display.print(tr(UiTextId::SurveyPaused));
    } else if (std::strcmp(productSurveyRuntime.status, "pausing") == 0) {
        display.print(tr(UiTextId::SurveyPausing));
    } else if (std::strcmp(productSurveyRuntime.status, "stopping") == 0) {
        display.print(tr(UiTextId::SurveyStopping));
    } else if (std::strcmp(productSurveyRuntime.status, "cancelling") == 0) {
        display.print(tr(UiTextId::SurveyCancelling));
    } else {
        const std::uint8_t selectedMask = productSurveyTimeline.selectedMask();
        display.print(tr(selectedMask == 1U
                             ? UiTextId::SurveySearchWifi
                             : selectedMask == 2U
                                   ? UiTextId::SurveySearchBle
                                   : UiTextId::SurveySearchBoth));
    }
    if (productSurveyTimeline.state() == SourceTimelineState::Running) {
        const auto* wifi = productSurveyTimeline.source(RadioKind::Wifi);
        const auto* ble = productSurveyTimeline.source(RadioKind::Ble);
        const bool wifiUnavailable =
            wifi != nullptr && wifi->selected &&
            (wifi->state == SourceWindowState::Unavailable ||
             wifi->state == SourceWindowState::Fault);
        const bool bleUnavailable =
            ble != nullptr && ble->selected &&
            (ble->state == SourceWindowState::Unavailable ||
             ble->state == SourceWindowState::Fault);
        if (wifiUnavailable || bleUnavailable) {
            display.setTextColor(Palette::Warning, Palette::Canvas);
            setUiCursor(UiTextRole::Meta, 14, 84);
            const char* unavailable = wifiUnavailable
                ? tr(UiTextId::TimelineWifiUnavailable)
                : tr(UiTextId::TimelineBleUnavailable);
            display.print(unavailable);
        }
    }
    renderSurveyFilterBar();
    const std::size_t selection = surveyController.selection();
    const std::size_t firstVisible = surveyFirstVisible(selection);
    const std::size_t endVisible =
        surveyController.visibleSize() < firstVisible + kVisibleSurveyRows
            ? surveyController.visibleSize()
            : firstVisible + kVisibleSurveyRows;
    for (std::size_t index = firstVisible; index < endVisible; ++index) {
        renderSurveyListRow(index, firstVisible);
    }
}

UiTextId libraryEntryTitle(const LibraryEntry& entry) {
    if (entry.session == nullptr) return UiTextId::LibraryRecord;
    const auto& capture = entry.session->captureMetadata();
    if (capture.infraredRawCaptured) return UiTextId::LibraryInfraredCapture;
    if (capture.subGhzRawCaptured) return UiTextId::LibrarySubGhzCapture;
    if (capture.framePayloadCaptured) return UiTextId::LibraryWifiCapture;
    if (capture.selectedSourceMask == 1U) return UiTextId::LibraryWifiScan;
    if (capture.selectedSourceMask == 2U) return UiTextId::LibraryBleScan;
    if (capture.selectedSourceMask == 3U) return UiTextId::LibraryCombinedScan;
    return UiTextId::LibraryRecord;
}

UiTextId libraryEntryState(const LibraryEntry& entry) {
    if (entry.integrity ==
        leshy1::apps::library::SessionIntegrity::RecoveredFallback) {
        return UiTextId::LibraryRecovered;
    }
    return entry.persistent ? UiTextId::LibrarySaved
                            : UiTextId::LibraryTemporary;
}

void libraryObservationCounts(const LibraryEntry& entry,
                              std::size_t* wifiCount,
                              std::size_t* bleCount) {
    if (wifiCount != nullptr) *wifiCount = 0;
    if (bleCount != nullptr) *bleCount = 0;
    if (entry.session == nullptr) return;
    for (std::size_t index = 0; index < entry.session->size(); ++index) {
        const Observation* observation = entry.session->get(index);
        if (observation == nullptr) continue;
        if (observation->radio == RadioKind::Wifi) {
            if (wifiCount != nullptr) ++(*wifiCount);
        } else if (bleCount != nullptr) {
            ++(*bleCount);
        }
    }
}

void renderLibraryListRow(std::size_t index) {
    const LibraryEntry* entry = libraryController.get(index);
    if (entry == nullptr || entry->session == nullptr) return;
    const std::int32_t y = 94 + static_cast<std::int32_t>(index) * 48;
    const bool selected = libraryController.selection() == index;
    const std::uint16_t background = selected ? Palette::SurfaceFocus
                                               : Palette::Surface;
    display.fillRoundRect(Layout::Edge, y, Layout::ContentWidth,
                          Layout::RowHeight, Layout::Radius, background);
    renderFocusCue({Layout::Edge, static_cast<std::int16_t>(y),
                    Layout::ContentWidth, Layout::RowHeight}, selected);
    display.setTextColor(selected ? Palette::Focus : Palette::TextSecondary,
                         background);
    setUiCursor(UiTextRole::Body,
                Layout::Edge + kInteractiveRowTextInset, y - 1);
    display.print(tr(libraryEntryTitle(*entry)));
    display.setTextColor(
        entry->integrity ==
                leshy1::apps::library::SessionIntegrity::RecoveredFallback ||
                !entry->persistent
            ? Palette::Warning
            : Palette::Positive,
        background);
    setUiCursor(UiTextRole::Meta,
                Layout::Edge + kInteractiveRowTextInset, y + 23);
    display.print(tr(libraryEntryState(*entry)));
}

void renderLibraryPage(bool clearContent) {
    char line[96] = {};
    const LibraryEntry* selected = libraryController.selected();
    const bool persistent = selected != nullptr && selected->persistent;
    if (libraryController.view() == LibraryView::ExportReady) {
        renderHeader(tr(UiTextId::ExportReady), clearContent);
        if (selected == nullptr || selected->session == nullptr) return;
        renderMetric(0, tr(libraryEntryTitle(*selected)), Tone::Positive);
        renderMetric(1, tr(UiTextId::FormatSummaryReady));
        const auto& capture = selected->session->captureMetadata();
        const bool rawFrames = capture.framePayloadCaptured;
        if (capture.subGhzRawCaptured || capture.infraredRawCaptured) {
            renderMetric(2, tr(UiTextId::FormatPulseCsvReady));
        } else if (rawFrames) {
            renderMetric(2, tr(UiTextId::FormatPcapReady));
        } else {
            renderMetric(2, tr(UiTextId::FormatCsvReady));
        }
        renderMetric(3, tr(UiTextId::ExportUsbRequired), Tone::Positive);
        return;
    }
    if (libraryController.view() == LibraryView::SessionDetail) {
        renderHeader(tr(UiTextId::SessionDetail), clearContent);
        if (selected == nullptr || selected->session == nullptr) return;
        renderMetric(0, tr(libraryEntryTitle(*selected)), Tone::Positive);
        const auto& capture = selected->session->captureMetadata();
        if (capture.infraredRawCaptured) {
            if (capture.infraredDecode.integrityValid) {
                std::snprintf(
                    line, sizeof(line), tr(UiTextId::IrProtocolFormat),
                    leshy1::domain::captures::infraredProtocolName(
                        capture.infraredDecode.protocol));
                renderMetric(1, line, Tone::Positive);
                std::snprintf(
                    line, sizeof(line), tr(UiTextId::IrCodeFormat),
                    static_cast<unsigned long>(capture.infraredDecode.rawCode));
                renderMetric(2, line);
            } else {
                renderMetric(1, tr(UiTextId::IrUnknownFormat), Tone::Warning);
            }
        } else if (capture.subGhzRawCaptured) {
            std::snprintf(
                line, sizeof(line), tr(UiTextId::SubGhzRawFrequencyFormat),
                static_cast<unsigned long>(capture.subGhzFrequencyKHz / 1000U),
                static_cast<unsigned long>(capture.subGhzFrequencyKHz % 1000U));
            renderMetric(1, line);
            renderMetric(2, tr(UiTextId::SubGhzSignalRecorded), Tone::Positive);
        } else if (capture.framePayloadCaptured) {
            std::snprintf(line, sizeof(line),
                          tr(UiTextId::CapturePacketsFormat),
                          static_cast<unsigned long>(
                              capture.framePayloadRecords));
            renderMetric(1, line);
            renderMetric(2, tr(UiTextId::CapturePcapReadyUser), Tone::Positive);
        } else {
            std::size_t wifiCount = 0;
            std::size_t bleCount = 0;
            libraryObservationCounts(*selected, &wifiCount, &bleCount);
            std::snprintf(line, sizeof(line),
                          tr(UiTextId::LibraryWifiBleCountFormat),
                          static_cast<unsigned>(wifiCount),
                          static_cast<unsigned>(bleCount));
            renderMetric(1, line);
        }
        renderMetric(3,
                     tr(selected->integrity ==
                                leshy1::apps::library::SessionIntegrity::
                                    RecoveredFallback
                            ? UiTextId::LibraryRecoveredWarning
                            : persistent ? UiTextId::LibraryStoredOnSd
                                         : UiTextId::LibraryNotStored),
                     selected->integrity ==
                             leshy1::apps::library::SessionIntegrity::
                                 RecoveredFallback
                         ? Tone::Warning
                         : persistent ? Tone::Positive : Tone::Warning);
        return;
    }

    renderHeader(tr(UiTextId::AppLibrary), clearContent);
    display.setTextColor(Palette::Positive, Palette::Canvas);
    std::snprintf(line, sizeof(line), tr(UiTextId::LibraryCountFormat),
                  static_cast<unsigned>(libraryController.size()));
    setUiCursor(UiTextRole::Meta, 14, 70);
    display.print(line);
    for (std::size_t index = 0; index < libraryController.size(); ++index) {
        renderLibraryListRow(index);
    }
}

struct UiRenderSnapshot final {
    bool valid = false;
    std::uint8_t page = 0;
    std::uint8_t rootSelection = 0;
    std::uint8_t deviceSelection = 0;
    std::uint8_t languageSelection = 0;
    std::uint8_t selfTestView = 0;
    std::uint8_t selfTestSelection = 0;
    std::uint8_t wifiProductView = 0;
    std::uint8_t wifiProductSelection = 0;
    std::size_t wifiNetworkSelection = 0;
    std::size_t wifiNetworkSize = 0;
    std::uint32_t wifiNetworkRevision = 0;
    std::size_t wifiDeviceSelection = 0;
    std::size_t wifiDeviceSize = 0;
    std::uint32_t wifiDeviceRevision = 0;
    bool wifiDeviceActive = false;
    std::uint8_t bleProductView = 0;
    std::size_t bleDeviceSelection = 0;
    std::size_t bleDeviceSize = 0;
    std::uint32_t bleDeviceRevision = 0;
    std::uint32_t wifiChannelRevision = 0;
    bool wifiChannelActive = false;
    std::uint8_t rfSpectrumView = 0;
    std::uint8_t rfSpectrumSelection = 0;
    std::uint8_t subGhzModeSelection = 0;
    std::uint8_t rfCcBandSelection = 0;
    std::uint8_t rfSpectrumDisplayMode = 0;
    std::uint8_t surveyState = 0;
    std::uint8_t surveySetupView = 0;
    std::uint8_t surveySetupSelection = 0;
    std::uint8_t surveySourceMask = 0;
    std::uint8_t surveyView = 0;
    std::uint8_t surveyFilter = 0;
    std::uint8_t surveyDraftFilter = 0;
    bool surveyFilterFocused = false;
    std::size_t surveySelection = 0;
    std::size_t surveySize = 0;
    std::size_t surveyVisibleSize = 0;
    std::uint8_t libraryView = 0;
    std::size_t librarySelection = 0;
    std::size_t librarySize = 0;
};

UiRenderSnapshot renderedUi{};

UiRenderSnapshot captureUiRenderSnapshot() {
    return {
        true,
        uiController.page(),
        uiController.selection(),
        deviceSelection,
        languageController.selection(),
        static_cast<std::uint8_t>(selfTestController.view()),
        selfTestController.selection(),
        static_cast<std::uint8_t>(wifiProductView),
        wifiProductSelection,
        wifiNetworkSelection,
        wifiNetworkVisibleSize(),
        wifiNetworkCatalog.revision(),
        wifiDeviceSelection,
        wifiDeviceVisibleSize(),
        wifiDeviceCatalog.revision(),
        wifiFrameCapture.deviceMonitorStats().active,
        static_cast<std::uint8_t>(bleProductView),
        bleDeviceSelection,
        bleDeviceCatalog.size(),
        bleDeviceCatalog.revision(),
        wifiFrameCapture.channelLoadSnapshot().revision,
        wifiFrameCapture.channelMonitorStats().active,
        static_cast<std::uint8_t>(rfSpectrumView),
        rfSpectrumSelection,
        subGhzModeSelection,
        ccBandSelectionIndex(),
        static_cast<std::uint8_t>(spectrumViewport.mode()),
        static_cast<std::uint8_t>(surveyWorkflow.state()),
        static_cast<std::uint8_t>(surveySourceController.view()),
        surveySourceController.selection(),
        surveySourceController.selectedMask(),
        static_cast<std::uint8_t>(surveyController.view()),
        static_cast<std::uint8_t>(surveyController.filter()),
        static_cast<std::uint8_t>(surveyController.draftFilter()),
        surveyController.filterFocused(),
        surveyController.selection(),
        surveySession.size(),
        surveyController.visibleSize(),
        static_cast<std::uint8_t>(libraryController.view()),
        libraryController.selection(),
        libraryController.size(),
    };
}

bool renderSelectionDelta() {
    if (!renderedUi.valid || renderedUi.page != uiController.page()) return false;

    if (uiController.isRoot()) {
        const std::uint8_t current = uiController.selection();
        if (renderedUi.rootSelection == current) return false;
        const std::uint8_t oldFirst =
            homeFirstVisible(renderedUi.rootSelection);
        const std::uint8_t currentFirst = homeFirstVisible(current);
        if (oldFirst != currentFirst) {
            renderHome(false);
            return true;
        }
        renderHomeRow(renderedUi.rootSelection, currentFirst);
        renderHomeRow(current, currentFirst);
        return true;
    }

    if (uiController.page() == kDevicePage) {
        if (renderedUi.deviceSelection == deviceSelection) return false;
        const std::uint8_t oldFirst =
            deviceFirstVisible(renderedUi.deviceSelection);
        const std::uint8_t currentFirst = deviceFirstVisible(deviceSelection);
        if (oldFirst != currentFirst) {
            renderDevicePage(false);
            return true;
        }
        renderDeviceRow(renderedUi.deviceSelection, currentFirst);
        renderDeviceRow(deviceSelection, currentFirst);
        return true;
    }

    if (uiController.page() == 2 &&
        bleProductView == BleProductView::Devices &&
        renderedUi.bleProductView ==
            static_cast<std::uint8_t>(BleProductView::Devices)) {
        const std::size_t current = bleDeviceSelection;
        const std::size_t oldFirst =
            bleDeviceFirstVisible(renderedUi.bleDeviceSelection);
        const std::size_t currentFirst = bleDeviceFirstVisible(current);
        const bool dataChanged =
            renderedUi.bleDeviceSize != bleDeviceCatalog.size() ||
            renderedUi.bleDeviceRevision != bleDeviceCatalog.revision();
        const bool stateChanged = renderedUi.surveyState !=
            static_cast<std::uint8_t>(surveyWorkflow.state());
        if (dataChanged || oldFirst != currentFirst) {
            const bool clearRows = oldFirst != currentFirst ||
                renderedUi.bleDeviceSize == 0U ||
                bleDeviceCatalog.size() == 0U;
            if (clearRows) {
                display.fillRect(
                    Layout::Edge, Layout::ContentTop, Layout::ContentWidth,
                    Layout::FooterDividerY - Layout::ContentTop,
                    Palette::Canvas);
                renderBleDevicesData();
            } else {
                const std::size_t end = bleDeviceCatalog.size() <
                        currentFirst + kVisibleWifiNetworkRows
                    ? bleDeviceCatalog.size()
                    : currentFirst + kVisibleWifiNetworkRows;
                for (std::size_t index = currentFirst; index < end; ++index) {
                    renderBleDeviceRow(index, currentFirst);
                }
            }
        }
        if (stateChanged) {
            display.fillRect(128, 0, Layout::ScreenWidth - 128,
                             Layout::HeaderHeight, Palette::Header);
            renderHeaderStatus();
            renderNavigationFooter();
        }
        if (dataChanged || stateChanged || oldFirst != currentFirst) {
            return true;
        }
        if (renderedUi.bleDeviceSelection == current) {
            // The shared survey worker can report a duplicate advertisement.
            // Nothing visible changed, so acknowledge the refresh without a
            // fallback full-screen repaint.
            return true;
        }
        renderBleDeviceRow(renderedUi.bleDeviceSelection, currentFirst);
        renderBleDeviceRow(current, currentFirst);
        return true;
    }

    if (uiController.page() == 2 &&
        wifiProductView == WifiProductView::Menu &&
        renderedUi.wifiProductView ==
            static_cast<std::uint8_t>(WifiProductView::Menu)) {
        if (renderedUi.wifiProductSelection == wifiProductSelection) {
            return false;
        }
        renderWifiProductRow(renderedUi.wifiProductSelection);
        renderWifiProductRow(wifiProductSelection);
        renderNavigationFooter();
        return true;
    }

    if (uiController.page() == 2 &&
        wifiProductView == WifiProductView::Networks &&
        surveyWorkflow.state() == SurveyWorkflowState::Running &&
        renderedUi.wifiProductView ==
            static_cast<std::uint8_t>(WifiProductView::Networks)) {
        const std::size_t current = wifiNetworkSelection;
        const std::size_t oldFirst =
            wifiNetworkFirstVisible(renderedUi.wifiNetworkSelection);
        const std::size_t currentFirst = wifiNetworkFirstVisible(current);
        const bool dataChanged = productSurveyIncrementalRefreshPending ||
            renderedUi.wifiNetworkSize != wifiNetworkVisibleSize() ||
            renderedUi.wifiNetworkRevision != wifiNetworkCatalog.revision();
        if (dataChanged || oldFirst != currentFirst) {
            const bool clearRows = oldFirst != currentFirst ||
                renderedUi.wifiNetworkSize == 0 ||
                wifiNetworkVisibleSize() == 0;
            if (clearRows) {
                display.fillRect(
                    Layout::Edge, Layout::ContentTop, Layout::ContentWidth,
                    Layout::FooterDividerY - Layout::ContentTop,
                    Palette::Canvas);
                renderWifiNetworksData();
            } else {
                const std::size_t end = wifiNetworkVisibleSize() <
                        currentFirst + kVisibleWifiNetworkRows
                    ? wifiNetworkVisibleSize()
                    : currentFirst + kVisibleWifiNetworkRows;
                for (std::size_t index = currentFirst; index < end; ++index) {
                    renderWifiNetworkRow(index, currentFirst);
                }
            }
            if (renderedUi.surveyState !=
                static_cast<std::uint8_t>(SurveyWorkflowState::Running)) {
                display.fillRect(128, 0, Layout::ScreenWidth - 128,
                                 Layout::HeaderHeight, Palette::Header);
                renderHeaderStatus();
                renderNavigationFooter();
            }
            return true;
        }
        if (renderedUi.wifiNetworkSelection == current) return false;
        renderWifiNetworkRow(renderedUi.wifiNetworkSelection, currentFirst);
        renderWifiNetworkRow(current, currentFirst);
        return true;
    }

    if (uiController.page() == 2 &&
        wifiProductView == WifiProductView::DeviceRadar &&
        renderedUi.wifiProductView ==
            static_cast<std::uint8_t>(WifiProductView::DeviceRadar)) {
        if (renderedUi.wifiDeviceRevision == wifiDeviceCatalog.revision()) {
            return false;
        }
        renderWifiDeviceRadarData();
        return true;
    }

    if (uiController.page() == 2 &&
        wifiProductView == WifiProductView::Devices &&
        renderedUi.wifiProductView ==
            static_cast<std::uint8_t>(WifiProductView::Devices)) {
        const std::size_t current = wifiDeviceSelection;
        const std::size_t oldFirst =
            wifiDeviceFirstVisible(renderedUi.wifiDeviceSelection);
        const std::size_t currentFirst = wifiDeviceFirstVisible(current);
        const bool dataChanged =
            renderedUi.wifiDeviceSize != wifiDeviceVisibleSize() ||
            renderedUi.wifiDeviceRevision != wifiDeviceCatalog.revision() ||
            renderedUi.wifiDeviceActive !=
                wifiFrameCapture.deviceMonitorStats().active;
        if (dataChanged || oldFirst != currentFirst) {
            const bool clearRows = oldFirst != currentFirst ||
                renderedUi.wifiDeviceSize == 0U ||
                wifiDeviceVisibleSize() == 0U;
            if (clearRows) {
                display.fillRect(
                    Layout::Edge, Layout::ContentTop, Layout::ContentWidth,
                    Layout::FooterDividerY - Layout::ContentTop,
                    Palette::Canvas);
                renderWifiDevicesData();
            } else {
                const std::size_t end = wifiDeviceVisibleSize() <
                        currentFirst + kVisibleWifiNetworkRows
                    ? wifiDeviceVisibleSize()
                    : currentFirst + kVisibleWifiNetworkRows;
                for (std::size_t index = currentFirst; index < end; ++index) {
                    renderWifiDeviceRow(index, currentFirst);
                }
            }
            return true;
        }
        if (renderedUi.wifiDeviceSelection == current) return false;
        renderWifiDeviceRow(renderedUi.wifiDeviceSelection, currentFirst);
        renderWifiDeviceRow(current, currentFirst);
        return true;
    }

    if (uiController.page() == 2 &&
        wifiProductView == WifiProductView::Channels &&
        renderedUi.wifiProductView ==
            static_cast<std::uint8_t>(WifiProductView::Channels)) {
        const auto stats = wifiFrameCapture.channelMonitorStats();
        if (renderedUi.wifiChannelActive != stats.active) return false;
        const auto snapshot = wifiFrameCapture.channelLoadSnapshot();
        if (renderedUi.wifiChannelRevision == snapshot.revision) return false;
        renderWifiChannelsData(false);
        return true;
    }

    if (uiController.page() == 2 &&
        rfSpectrumView == RfSpectrumView::SourceMenu &&
        renderedUi.rfSpectrumView ==
            static_cast<std::uint8_t>(RfSpectrumView::SourceMenu)) {
        const std::uint8_t current = rfSpectrumSelection;
        if (renderedUi.rfSpectrumSelection == current) return false;
        renderRfSpectrumSourceRow(renderedUi.rfSpectrumSelection);
        renderRfSpectrumSourceRow(current);
        renderNavigationFooter();
        return true;
    }

    if (uiController.page() == 2 &&
        rfSpectrumView == RfSpectrumView::SubGhzMenu &&
        renderedUi.rfSpectrumView ==
            static_cast<std::uint8_t>(RfSpectrumView::SubGhzMenu)) {
        const std::uint8_t current = subGhzModeSelection;
        if (renderedUi.subGhzModeSelection == current) return false;
        const auto renderMode = [](std::uint8_t index, bool selected) {
            renderMenuRow(
                Components::choiceRow(index),
                tr(index == 0 ? UiTextId::SubGhzSpectrum
                              : UiTextId::SubGhzRaw),
                tr(index == 0 ? UiTextId::SubGhzSpectrumNote
                              : UiTextId::SubGhzRawNote),
                selected, true, Tone::Positive);
        };
        renderMode(renderedUi.subGhzModeSelection, false);
        renderMode(current, true);
        renderNavigationFooter();
        return true;
    }

    if (uiController.page() == 2 &&
        (rfSpectrumView == RfSpectrumView::CcBandMenu ||
         rfSpectrumView == RfSpectrumView::SubGhzCaptureBandMenu) &&
        renderedUi.rfSpectrumView ==
            static_cast<std::uint8_t>(rfSpectrumView)) {
        const std::uint8_t current = ccBandSelectionIndex();
        if (renderedUi.rfCcBandSelection == current) return false;
        renderRfCcBandRow(renderedUi.rfCcBandSelection);
        renderRfCcBandRow(current);
        renderNavigationFooter();
        return true;
    }

    if (uiController.page() == 2 &&
        surveyWorkflow.state() == SurveyWorkflowState::Setup &&
        renderedUi.surveyState ==
            static_cast<std::uint8_t>(SurveyWorkflowState::Setup) &&
        renderedUi.surveySetupView ==
            static_cast<std::uint8_t>(surveySourceController.view()) &&
        renderedUi.surveySourceMask == surveySourceController.selectedMask()) {
        const std::uint8_t current = surveySourceController.selection();
        if (renderedUi.surveySetupSelection == current) return false;
        if (surveySourceController.view() == SurveySetupView::Sources) {
            renderSurveySourceRow(renderedUi.surveySetupSelection);
            renderSurveySourceRow(current);
        } else {
            renderSurveyPlanRow(renderedUi.surveySetupSelection);
            renderSurveyPlanRow(current);
        }
        renderNavigationFooter();
        return true;
    }

    if (uiController.page() == 2 &&
        surveyWorkflow.state() == SurveyWorkflowState::Running &&
        surveyController.view() == SurveyView::Filter &&
        renderedUi.surveyState ==
            static_cast<std::uint8_t>(SurveyWorkflowState::Running) &&
        renderedUi.surveyView == static_cast<std::uint8_t>(SurveyView::Filter) &&
        renderedUi.surveySize == surveySession.size()) {
        const std::uint8_t current =
            static_cast<std::uint8_t>(surveyController.draftFilter());
        if (renderedUi.surveyDraftFilter == current) return false;
        renderSurveyFilterOption(renderedUi.surveyDraftFilter);
        renderSurveyFilterOption(current);
        renderNavigationFooter();
        return true;
    }

    if (uiController.page() == 2 &&
        surveyWorkflow.state() == SurveyWorkflowState::Running &&
        surveyController.view() == SurveyView::List &&
        renderedUi.surveyState ==
            static_cast<std::uint8_t>(SurveyWorkflowState::Running) &&
        renderedUi.surveyView == static_cast<std::uint8_t>(SurveyView::List) &&
        renderedUi.surveyFilter ==
            static_cast<std::uint8_t>(surveyController.filter())) {
        const std::size_t current = surveyController.selection();
        const bool currentFilterFocused = surveyController.filterFocused();
        if (productSurveyIncrementalRefreshPending) {
            renderSurveyFilterBar();
            display.fillRect(Layout::Edge, kSurveyRowsY, Layout::ContentWidth,
                             92, Palette::Canvas);
            const std::size_t first = surveyFirstVisible(current);
            const std::size_t end =
                surveyController.visibleSize() < first + kVisibleSurveyRows
                    ? surveyController.visibleSize()
                    : first + kVisibleSurveyRows;
            for (std::size_t index = first; index < end; ++index) {
                renderSurveyListRow(index, first);
            }
            return true;
        }
        if (renderedUi.surveySelection == current &&
            renderedUi.surveyFilterFocused == currentFilterFocused) return false;
        if (renderedUi.surveyFilterFocused != currentFilterFocused) {
            renderSurveyFilterBar();
            if (!renderedUi.surveyFilterFocused) {
                renderSurveyListRow(renderedUi.surveySelection,
                                    surveyFirstVisible(renderedUi.surveySelection));
            }
            if (!currentFilterFocused) {
                renderSurveyListRow(current, surveyFirstVisible(current));
            }
            renderNavigationFooter();
            return true;
        }
        const std::size_t oldFirst =
            surveyFirstVisible(renderedUi.surveySelection);
        const std::size_t currentFirst = surveyFirstVisible(current);
        if (oldFirst == currentFirst) {
            renderSurveyListRow(renderedUi.surveySelection, currentFirst);
            renderSurveyListRow(current, currentFirst);
        } else {
            display.fillRect(Layout::Edge, kSurveyRowsY, Layout::ContentWidth, 92,
                             Palette::Canvas);
            const std::size_t end =
                surveyController.visibleSize() < currentFirst + kVisibleSurveyRows
                    ? surveyController.visibleSize()
                    : currentFirst + kVisibleSurveyRows;
            for (std::size_t index = currentFirst; index < end; ++index) {
                renderSurveyListRow(index, currentFirst);
            }
        }
        return true;
    }

    if (uiController.page() == 3 &&
        libraryController.view() == LibraryView::SessionList &&
        renderedUi.libraryView ==
            static_cast<std::uint8_t>(LibraryView::SessionList) &&
        renderedUi.librarySize == libraryController.size()) {
        const std::size_t current = libraryController.selection();
        if (renderedUi.librarySelection == current) return false;
        renderLibraryListRow(renderedUi.librarySelection);
        renderLibraryListRow(current);
        return true;
    }

    if (uiController.page() == 5) {
        const std::uint8_t current = languageController.selection();
        if (renderedUi.languageSelection == current) return false;
        renderLanguageRow(renderedUi.languageSelection);
        renderLanguageRow(current);
        return true;
    }

    if (uiController.page() == 6 &&
        selfTestController.view() == SelfTestView::ModeMenu &&
        renderedUi.selfTestView ==
            static_cast<std::uint8_t>(SelfTestView::ModeMenu)) {
        const std::uint8_t current = selfTestController.selection();
        if (renderedUi.selfTestSelection == current) return false;
        renderSelfTestModeRow(renderedUi.selfTestSelection);
        renderSelfTestModeRow(current);
        return true;
    }
    return false;
}

void renderInteractiveScreen(bool clearContent) {
    std::uint64_t startedUs = static_cast<std::uint64_t>(esp_timer_get_time());
    if (startedUs == 0) startedUs = 1;
    display.startWrite();
    const bool incremental = !safetySupervisor.latched() && !clearContent &&
                             renderSelectionDelta();
    if (!incremental) {
        clearContent = true;
        if (safetySupervisor.latched()) {
            renderSafetyStop(clearContent);
        } else if (uiController.isRoot()) {
            renderHome(clearContent);
        } else if (uiController.page() == 1) {
            renderOverview(clearContent);
        } else if (uiController.page() == 2) {
            renderInventoryPage(clearContent);
        } else if (uiController.page() == 3) {
            renderLibraryPage(clearContent);
        } else if (uiController.page() == 4) {
            renderCapturePage(clearContent);
        } else if (uiController.page() == 5) {
            renderLanguagePage(clearContent);
        } else if (uiController.page() == 6) {
            renderSelfTestPage(clearContent);
        } else if (uiController.page() == kDevicePage) {
            renderDevicePage(clearContent);
        } else {
            renderAboutPage(clearContent);
        }
        const Rect divider = Components::footerDivider();
        display.drawFastHLine(divider.x, divider.y, divider.width,
                              Palette::Divider);
        renderNavigationFooter();
        // As in 0.x MenuScreen::repaint, focus movement leaves chrome untouched.
    }
    display.endWrite();
    renderedUi = captureUiRenderSnapshot();
    const std::uint64_t finishedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    lastUiRenderWasIncremental = incremental;
    lastUiRenderUs = finishedUs >= startedUs ? finishedUs - startedUs : 0;
}

bool startNrf24Spectrum() {
    nrf24SpectrumController.reset();
    spectrumViewport.reset(Nrf24SpectrumController::kChannelCount);
    nrf24SpectrumReport = {};
    std::uint64_t startedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    if (startedUs == 0) startedUs = 1;
    const bool owned = resourceBroker.ownerOf(Resource::RadioSpi) ==
        AppRuntime::kForegroundOwner;
    const Nrf24PassiveSpectrumPlan plan =
        leshy1::drivers::radio::defaultNrf24PassiveSpectrumPlan();
    const bool hardwareReady = boardNrf24Spectrum.begin(
        owned, plan, &nrf24SpectrumReport);
    const bool started = hardwareReady && nrf24SpectrumController.start(
        nrf24SpectrumReport.detectedModules, startedUs);
    if (!started) {
        boardNrf24Spectrum.end();
        nrf24SpectrumController.fail();
    }
    rfSpectrumKind = RfSpectrumKind::Nrf24;
    rfSpectrumView = RfSpectrumView::Live;
    nextSpectrumUiRefreshUs = startedUs;
    resetSpectrumWaterfallTiming();
    armSpectrumWaterfallForCurrentReceiver();
    nrf24SpectrumChunkMaxUs = 0;
    lastRuntimeEvent = started ? "nrf24_spectrum_running"
                               : "nrf24_spectrum_start_failed";
    return true;
}

bool stopNrf24Spectrum(bool returnToSourceMenu) {
    const bool cleanup = boardNrf24Spectrum.end();
    if (nrf24SpectrumController.state() != Nrf24SpectrumViewState::Idle) {
        nrf24SpectrumController.stop();
    }
    rfSpectrumView = returnToSourceMenu ? RfSpectrumView::SourceMenu
                                        : RfSpectrumView::None;
    nextSpectrumUiRefreshUs = 0;
    lastRuntimeEvent = cleanup ? "nrf24_spectrum_stopped"
                               : "nrf24_spectrum_cleanup_failed";
    return true;
}

void serviceNrf24Spectrum() {
    if (rfSpectrumView != RfSpectrumView::Live ||
        rfSpectrumKind != RfSpectrumKind::Nrf24 ||
        nrf24SpectrumController.state() !=
            Nrf24SpectrumViewState::Running) {
        return;
    }
    Nrf24PassiveSweep sweep;
    const bool valid = boardNrf24Spectrum.sampleChunk(&sweep) &&
                       nrf24SpectrumController.ingest(sweep);
    if (!valid) {
        boardNrf24Spectrum.end();
        nrf24SpectrumController.fail();
        lastRuntimeEvent = "nrf24_spectrum_runtime_fault";
        renderInteractiveScreen(true);
        return;
    }
    const std::uint64_t chunkUs = sweep.endedUs - sweep.startedUs;
    if (chunkUs > nrf24SpectrumChunkMaxUs) {
        nrf24SpectrumChunkMaxUs = chunkUs;
    }
    const std::uint64_t refreshUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    if (!uiController.isRoot() && uiController.page() == 2 &&
        spectrumViewport.mode() == SpectrumDisplayMode::Spectrum &&
        refreshUs >= nextSpectrumUiRefreshUs) {
        display.startWrite();
        renderSpectrumBars();
        display.endWrite();
        nextSpectrumUiRefreshUs = refreshUs + 100000ULL;
    }
}

bool startCc1101Spectrum(
    leshy1::drivers::radio::Cc1101SpectrumBand band) {
    cc1101SpectrumController.reset();
    spectrumViewport.reset(Cc1101SpectrumController::kBinCount);
    cc1101SpectrumReport = {};
    std::uint64_t startedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    if (startedUs == 0) startedUs = 1;
    const bool owned = resourceBroker.ownerOf(Resource::RadioSpi) ==
        AppRuntime::kForegroundOwner;
    const bool hardwareReady = boardCc1101Spectrum.begin(
        owned, &cc1101SpectrumReport);
    const bool started = hardwareReady &&
        cc1101SpectrumController.start(band, startedUs);
    if (!started) {
        boardCc1101Spectrum.end();
        cc1101SpectrumController.fail();
    }
    rfSpectrumKind = RfSpectrumKind::Cc1101;
    rfSpectrumView = RfSpectrumView::Live;
    nextSpectrumUiRefreshUs = startedUs;
    resetSpectrumWaterfallTiming();
    armSpectrumWaterfallForCurrentReceiver();
    lastRuntimeEvent = started ? "cc1101_spectrum_running"
                               : "cc1101_spectrum_start_failed";
    return true;
}

bool stopCc1101Spectrum(bool returnToSourceMenu) {
    const bool cleanup = boardCc1101Spectrum.end();
    if (cc1101SpectrumController.state() !=
        Cc1101SpectrumViewState::Idle) {
        cc1101SpectrumController.stop();
    }
    rfSpectrumView = returnToSourceMenu ? RfSpectrumView::CcBandMenu
                                        : RfSpectrumView::None;
    nextSpectrumUiRefreshUs = 0;
    lastRuntimeEvent = cleanup ? "cc1101_spectrum_stopped"
                               : "cc1101_spectrum_cleanup_failed";
    return true;
}

bool stopCurrentSpectrum(bool returnToSourceMenu) {
    return rfSpectrumKind == RfSpectrumKind::Cc1101
        ? stopCc1101Spectrum(returnToSourceMenu)
        : stopNrf24Spectrum(returnToSourceMenu);
}

void serviceCc1101Spectrum() {
    if (rfSpectrumView != RfSpectrumView::Live ||
        rfSpectrumKind != RfSpectrumKind::Cc1101 ||
        cc1101SpectrumController.state() !=
            Cc1101SpectrumViewState::Running) {
        return;
    }
    Cc1101PassiveSample sample;
    const bool valid = boardCc1101Spectrum.sample(
        cc1101SpectrumController.plan(),
        cc1101SpectrumController.nextBin(), &sample) &&
        cc1101SpectrumController.ingest(sample);
    if (!valid) {
        boardCc1101Spectrum.end();
        cc1101SpectrumController.fail();
        lastRuntimeEvent = "cc1101_spectrum_runtime_fault";
        renderInteractiveScreen(true);
        return;
    }
    const std::uint64_t refreshUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    if (cc1101SpectrumController.nextBin() == 0 &&
        !uiController.isRoot() && uiController.page() == 2 &&
        spectrumViewport.mode() == SpectrumDisplayMode::Spectrum &&
        refreshUs >= nextSpectrumUiRefreshUs) {
        display.startWrite();
        renderSpectrumBars();
        display.endWrite();
        nextSpectrumUiRefreshUs = refreshUs + 100000ULL;
    }
}

bool startSubGhzRawCapture(
    leshy1::drivers::radio::Cc1101SpectrumBand band) {
    subGhzRawCapture.reset();
    subGhzCapturePersistState = CapturePersistState::Result;
    subGhzCapturePersistStatus = "volatile";
    subGhzCapturePersistGeneration = 0;
    cc1101SpectrumReport = {};
    SubGhzRawCapturePlan plan;
    plan.frequencyKHz = subGhzCaptureFrequencyKHz(band);
    std::uint64_t startedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    if (startedUs == 0U) startedUs = 1U;
    const bool owned = resourceBroker.ownerOf(Resource::RadioSpi) ==
        AppRuntime::kForegroundOwner;
    const bool hardwareReady = boardCc1101Spectrum.begin(
        owned, &cc1101SpectrumReport) &&
        boardCc1101Spectrum.lockReceive(plan.frequencyKHz);
    const bool started = hardwareReady &&
        subGhzRawCapture.begin(plan, startedUs);
    if (!started) {
        boardCc1101Spectrum.end();
        if (subGhzRawCapture.stats().state ==
            SubGhzRawCaptureState::Waiting) {
            subGhzRawCapture.fail(-1, startedUs);
        }
    }
    rfCcBandSelection = band;
    rfSpectrumKind = RfSpectrumKind::Cc1101;
    rfSpectrumView = RfSpectrumView::SubGhzCaptureLive;
    nextSubGhzCaptureUiRefreshUs = startedUs;
    lastRuntimeEvent = started ? "subghz_raw_waiting"
                               : "subghz_raw_start_failed";
    return true;
}

bool stopSubGhzRawCapture(bool returnToModes) {
    const std::uint64_t nowUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    const auto state = subGhzRawCapture.stats().state;
    if (state == SubGhzRawCaptureState::Waiting ||
        state == SubGhzRawCaptureState::Capturing) {
        subGhzRawCapture.cancel(nowUs == 0U ? 1U : nowUs);
    }
    const bool cleanup = boardCc1101Spectrum.end();
    nextSubGhzCaptureUiRefreshUs = 0;
    rfSpectrumView = returnToModes ? RfSpectrumView::SubGhzMenu
                                   : RfSpectrumView::None;
    lastRuntimeEvent = cleanup ? "subghz_raw_stopped"
                               : "subghz_raw_cleanup_failed";
    return true;
}

void serviceSubGhzRawCapture() {
    if (rfSpectrumView != RfSpectrumView::SubGhzCaptureLive) return;
    const auto state = subGhzRawCapture.stats().state;
    if (state != SubGhzRawCaptureState::Waiting &&
        state != SubGhzRawCaptureState::Capturing) {
        return;
    }
    std::int16_t rssiDbm = 0;
    std::uint64_t sampleUs = 0;
    if (!boardCc1101Spectrum.sampleRssi(&rssiDbm, &sampleUs)) {
        const std::uint64_t nowUs =
            static_cast<std::uint64_t>(esp_timer_get_time());
        subGhzRawCapture.fail(-2, nowUs == 0U ? 1U : nowUs);
        boardCc1101Spectrum.end();
        lastRuntimeEvent = "subghz_raw_runtime_fault";
        renderInteractiveScreen(true);
        return;
    }
    subGhzRawCapture.ingest({sampleUs, rssiDbm});
    subGhzRawCapture.service(sampleUs);
    const auto after = subGhzRawCapture.stats().state;
    const bool terminal = after != SubGhzRawCaptureState::Waiting &&
        after != SubGhzRawCaptureState::Capturing;
    if (terminal) {
        const bool cleanup = boardCc1101Spectrum.end();
        lastRuntimeEvent = !cleanup
            ? "subghz_raw_cleanup_failed"
            : after == SubGhzRawCaptureState::Complete
                  ? "subghz_raw_complete"
                  : after == SubGhzRawCaptureState::TimedOut
                        ? "subghz_raw_no_signal"
                        : after == SubGhzRawCaptureState::SignalTooLong
                              ? "subghz_raw_signal_too_long"
                              : "subghz_raw_terminal";
    }
    // Display transfers are deliberately suspended once the first edge starts
    // the capture.  A full TFT refresh is long enough to create false pulse
    // widths; measurement integrity takes precedence until the terminal gap.
    if (terminal ||
        (after == SubGhzRawCaptureState::Waiting &&
         sampleUs >= nextSubGhzCaptureUiRefreshUs)) {
        nextSubGhzCaptureUiRefreshUs = sampleUs + 200000ULL;
        renderInteractiveScreen(true);
    }
}

bool activeSpectrumRunning() {
    if (rfSpectrumView != RfSpectrumView::Live) return false;
    return rfSpectrumKind == RfSpectrumKind::Cc1101
        ? cc1101SpectrumController.state() ==
              Cc1101SpectrumViewState::Running
        : nrf24SpectrumController.state() ==
              Nrf24SpectrumViewState::Running;
}

bool activeReceiveSampling() {
    const auto rawState = subGhzRawCapture.stats().state;
    const auto irState = infraredCapture.stats().state;
    return activeSpectrumRunning() ||
        (rfSpectrumView == RfSpectrumView::SubGhzCaptureLive &&
         (rawState == SubGhzRawCaptureState::Waiting ||
          rawState == SubGhzRawCaptureState::Capturing)) ||
        (uiController.page() == 4 && captureView == CaptureView::Infrared &&
         (irState == InfraredCaptureState::Waiting ||
          irState == InfraredCaptureState::Capturing));
}

std::uint32_t activeSpectrumSweeps() {
    return rfSpectrumKind == RfSpectrumKind::Cc1101
        ? cc1101SpectrumController.sweeps()
        : nrf24SpectrumController.sweeps();
}

void armSpectrumWaterfallForCurrentReceiver() {
    const std::uint32_t sweeps = activeSpectrumSweeps();
    spectrumWaterfallSourceSweepBaseline = sweeps;
    spectrumWaterfallLastSourceSweep = sweeps;
}

void serviceSpectrumWaterfallCadence() {
    if (!activeSpectrumRunning()) return;
    const std::uint32_t sourceSweeps = activeSpectrumSweeps();
    if (sourceSweeps == spectrumWaterfallLastSourceSweep) return;
    if (sourceSweeps < spectrumWaterfallLastSourceSweep) {
        armSpectrumWaterfallForCurrentReceiver();
        return;
    }
    const std::uint32_t newlyCompleted =
        sourceSweeps - spectrumWaterfallLastSourceSweep;
    if (newlyCompleted > 1U) {
        spectrumWaterfallMeasurementsSkipped += newlyCompleted - 1U;
    }
    spectrumWaterfallLastSourceSweep = sourceSweeps;

    // One complete receiver sweep becomes exactly one physical TFT row.  No
    // fixed display timer can replay a partial or stale receiver snapshot.
    const bool renderRows = !uiController.isRoot() &&
        uiController.page() == 2 &&
        spectrumViewport.mode() == SpectrumDisplayMode::Waterfall;
    if (renderRows) display.startWrite();
    const std::uint64_t rowStartedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    if (spectrumWaterfallPreviousRowUs != 0) {
        const std::uint64_t intervalUs =
            rowStartedUs - spectrumWaterfallPreviousRowUs;
        spectrumWaterfallRowIntervalTotalUs += intervalUs;
        if (intervalUs > spectrumWaterfallRowIntervalMaxUs) {
            spectrumWaterfallRowIntervalMaxUs = intervalUs;
        }
    }
    spectrumWaterfallPreviousRowUs = rowStartedUs;
    if (!pushActiveSpectrumHistory()) {
        if (rfSpectrumKind == RfSpectrumKind::Cc1101) {
            boardCc1101Spectrum.end();
            cc1101SpectrumController.fail();
        } else {
            boardNrf24Spectrum.end();
            nrf24SpectrumController.fail();
        }
        lastRuntimeEvent = "spectrum_history_fault";
        if (renderRows) display.endWrite();
        renderInteractiveScreen(true);
        return;
    }
    const std::uint64_t pushedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    const std::uint64_t pushUs = pushedUs - rowStartedUs;
    spectrumWaterfallPushTotalUs += pushUs;
    if (pushUs > spectrumWaterfallPushMaxUs) {
        spectrumWaterfallPushMaxUs = pushUs;
    }
    if (spectrumWaterfallStartedUs == 0) {
        spectrumWaterfallStartedUs = rowStartedUs;
    }
    ++spectrumWaterfallRowsEmitted;
    ++spectrumWaterfallMeasurementsConsumed;
    if (spectrumWaterfallCompletedUs == 0 &&
        spectrumViewport.rowsStored() == SpectrumViewport::kHistoryRows) {
        spectrumWaterfallCompletedUs = rowStartedUs;
    }
    if (renderRows) {
        renderLatestWaterfallRow();
    }
    const std::uint64_t renderedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    const std::uint64_t renderUs = renderedUs - pushedUs;
    spectrumWaterfallRenderTotalUs += renderUs;
    if (renderUs > spectrumWaterfallRenderMaxUs) {
        spectrumWaterfallRenderMaxUs = renderUs;
    }
    const std::uint64_t serviceUs = renderedUs - rowStartedUs;
    if (serviceUs > spectrumWaterfallServiceMaxUs) {
        spectrumWaterfallServiceMaxUs = serviceUs;
    }
    if (renderRows) display.endWrite();
}

void releaseFullGuidedRfResource() {
    if (fullGuidedRfState.resourceAcquired) {
        resourceBroker.release(
            AppRuntime::kForegroundOwner,
            leshy1::kernel::runtime::resourceMask(Resource::RadioSpi));
    }
    fullGuidedRfState.resourceReleased =
        resourceBroker.ownerOf(Resource::RadioSpi) ==
        leshy1::kernel::runtime::kNoOwner;
}

void restoreFullGuidedLibraryView() {
    if (libraryController.view() == LibraryView::ExportReady) {
        libraryController.back();
    }
    if (libraryController.view() == LibraryView::SessionDetail) {
        libraryController.back();
    }
}

void finishFullGuidedActiveChecks(bool success);

void releaseFullGuidedDisposableResources() {
    resourceBroker.release(
        AppRuntime::kForegroundOwner,
        leshy1::storage::kSdIdentificationResources);
    fullGuidedArtifactState.disposableResourceReleased =
        resourceBroker.ownerOf(Resource::Storage) ==
            leshy1::kernel::runtime::kNoOwner &&
        resourceBroker.ownerOf(Resource::RadioSpi) ==
            leshy1::kernel::runtime::kNoOwner;
}

bool acquireFullGuidedDisposableResources() {
    fullGuidedArtifactState.disposableResourceReleased = false;
    fullGuidedArtifactState.disposableResourceAcquired =
        resourceBroker.acquire(
            AppRuntime::kForegroundOwner,
            leshy1::storage::kSdIdentificationResources);
    return fullGuidedArtifactState.disposableResourceAcquired;
}

bool identifyFullGuidedDisposableMedia(std::uint64_t* capacityBytes) {
    if (capacityBytes == nullptr) return false;
    *capacityBytes = 0;
    BoardSdSpiTransport transport;
    if (!transport.begin()) return false;
    leshy1::storage::SdTransportRunPolicy policy;
    policy.allowPhysical = true;
    policy.explicitlySelected = true;
    policy.identificationOnly = true;
    policy.ownedResources = resourceBroker.ownedBy(
        AppRuntime::kForegroundOwner);
    const leshy1::storage::SdTransportRunResult identity =
        leshy1::storage::runSdIdentificationStateMachine(
            leshy1::storage::defaultSdIdentificationPlan(), transport,
            policy);
    transport.end();
    fullGuidedArtifactState.disposableObservedFingerprint[0] = '\0';
    if (identity.status == leshy1::storage::SdTransportRunStatus::Valid) {
        formatCidFingerprint(
            identity.identity,
            fullGuidedArtifactState.disposableObservedFingerprint,
            sizeof(fullGuidedArtifactState.disposableObservedFingerprint));
        *capacityBytes = identity.identity.capacityBytes;
    }
    fullGuidedArtifactState.disposableIdentityPassed =
        identity.status == leshy1::storage::SdTransportRunStatus::Valid &&
        transport.cleanupComplete() &&
        std::strcmp(
            fullGuidedArtifactState.disposableObservedFingerprint,
            fullGuidedArtifactState.expectedFingerprint) == 0;
    return fullGuidedArtifactState.disposableIdentityPassed;
}

leshy1::storage::MediaIdentity fullGuidedDisposableMedia(
    const BoardSdFilesystem& filesystem, std::uint64_t identifiedCapacity) {
    leshy1::storage::MediaIdentity media;
    media.present = filesystem.mounted() && identifiedCapacity != 0 &&
        filesystem.cardCapacityBytes() == identifiedCapacity &&
        filesystem.filesystemCapacityBytes() != 0 &&
        filesystem.filesystemCapacityBytes() <= identifiedCapacity;
    media.kind = leshy1::storage::MediaKind::Sd;
    media.fingerprint =
        fullGuidedArtifactState.disposableObservedFingerprint;
    media.capacityBytes = filesystem.cardCapacityBytes();
    media.freeBytes = filesystem.freeBytes();
    return media;
}

bool removeFullGuidedDisposableScratch(BoardSdFilesystem& filesystem,
                                       const leshy1::storage::MediaIdentity& media) {
    const bool exists = filesystem.exists(
        fullGuidedArtifactState.disposableScratchPath);
    if (!exists) {
        fullGuidedArtifactState.scratchRemoved = true;
        return true;
    }
    leshy1::storage::ScratchCleanupRequest request;
    request.explicitlyDisposable = true;
    request.expectedFingerprint =
        fullGuidedArtifactState.expectedFingerprint;
    request.runId = kFullGuidedDisposableRunId;
    request.scratchExists = true;
    const leshy1::storage::ScratchCleanupPermit permit =
        leshy1::storage::authorizeScratchCleanup(media, request);
    ArduinoFsSessionStoreIo io(filesystem.driveNumber(),
                               sdSessionStoreIoWorkspace);
    const bool removed = permit.allowed() && io.removeScratch(permit);
    fullGuidedArtifactState.disposableFilesRemoved += io.filesRemoved();
    fullGuidedArtifactState.scratchRemoved = removed &&
        !filesystem.exists(fullGuidedArtifactState.disposableScratchPath);
    return fullGuidedArtifactState.scratchRemoved;
}

void runFullGuidedDisposableCommit() {
    bool filesystemAttempted = false;
    bool filesystemCleanup = true;
    bool passed = false;
    if (acquireFullGuidedDisposableResources()) {
        std::uint64_t identifiedCapacity = 0;
        if (identifyFullGuidedDisposableMedia(&identifiedCapacity)) {
            BoardSdFilesystem filesystem;
            filesystemAttempted = true;
            if (filesystem.begin()) {
                const leshy1::storage::MediaIdentity media =
                    fullGuidedDisposableMedia(filesystem, identifiedCapacity);
                fullGuidedArtifactState.scratchPreexisting =
                    filesystem.exists(
                        fullGuidedArtifactState.disposableScratchPath);
                const bool staleReady =
                    !fullGuidedArtifactState.scratchPreexisting ||
                    removeFullGuidedDisposableScratch(filesystem, media);
                leshy1::storage::WriteRequest request;
                request.explicitlyDisposable = true;
                request.expectedFingerprint =
                    fullGuidedArtifactState.expectedFingerprint;
                request.runId = kFullGuidedDisposableRunId;
                request.scratchExists = filesystem.exists(
                    fullGuidedArtifactState.disposableScratchPath);
                request.requiredBytes = kFullGuidedDisposableBytes;
                request.reserveBytes = kFullGuidedDisposableReserve;
                const leshy1::storage::WritePermit permit =
                    leshy1::storage::authorizeScratchWrite(media, request);

                littleFsResetSession.reset();
                const std::uint8_t selectedSourceMask =
                    leshy1::services::survey::sourceMask(RadioKind::Wifi);
                const CaptureMetadata metadata =
                    productCaptureMetadata(selectedSourceMask);
                const SourceWindow wifiWindow{
                    RadioKind::Wifi, SourceWindowState::Active,
                    SourceWindowReason::None, 1000, 3000, 3, 0};
                leshy1::services::survey::SourceRuntimeSummary wifiSummary;
                wifiSummary.selected = true;
                wifiSummary.state = SourceWindowState::Stopped;
                wifiSummary.activeUs = 2000;
                wifiSummary.accepted = 3;
                wifiSummary.windows = 1;
                leshy1::services::survey::SourceRuntimeSummary bleSummary;
                const bool fixtureReady = staleReady && permit.allowed() &&
                    littleFsResetSession.start(
                        kFullGuidedDisposableRunId, 1000) ==
                        SessionStatus::Started &&
                    littleFsResetSession.configureCaptureMetadata(metadata) ==
                        leshy1::services::survey::
                            CaptureMetadataStatus::Configured &&
                    littleFsResetSession.startTimeline(
                        selectedSourceMask, 1000) ==
                        leshy1::services::survey::
                            SessionTimelineStatus::Started &&
                    appendGoldenObservations(littleFsResetSession) &&
                    littleFsResetSession.appendTimelineWindow(wifiWindow) ==
                        leshy1::services::survey::
                            SessionTimelineStatus::Appended &&
                    littleFsResetSession.finalizeTimeline(
                        3000, wifiSummary, bleSummary, 0) ==
                        leshy1::services::survey::
                            SessionTimelineStatus::Finalized &&
                    littleFsResetSession.stop(3000) == SessionStatus::Stopped;
                if (fixtureReady) {
                    ArduinoFsSessionStoreIo io(
                        filesystem.driveNumber(), sdSessionStoreIoWorkspace);
                    const bool prepared = io.prepare(permit);
                    fullGuidedArtifactState.scratchCreated = prepared &&
                        filesystem.exists(permit.scratchPath);
                    fullGuidedArtifactState.scratchRemoved = false;
                    leshy1::storage::SessionStoreCommitResult commit;
                    leshy1::storage::SessionStoreRecoveryResult recovery;
                    if (fullGuidedArtifactState.scratchCreated) {
                        commit = leshy1::storage::commitNextSession(
                            io, sessionStoreWorkspace,
                            littleFsResetSession);
                        if (commit.complete()) {
                            recovery = leshy1::storage::recoverSession(
                                io, sessionStoreWorkspace,
                                &sessionStoreWorkspace.validationSession);
                        }
                    }
                    fullGuidedArtifactState.disposableStorageWriteBytes +=
                        io.bytesWritten();
                    fullGuidedArtifactState.disposableStorageWriteCalls +=
                        io.writeCalls();
                    fullGuidedArtifactState.disposableFileSyncs +=
                        io.fileSyncs();
                    fullGuidedArtifactState.disposableDirectorySyncs +=
                        io.directorySyncs();
                    fullGuidedArtifactState.disposableGeneration =
                        recovery.generation;
                    fullGuidedArtifactState.disposableObservations =
                        recovery.observations;
                    passed = commit.complete() && commit.generation == 1 &&
                        recovery.valid() && recovery.generation == 1 &&
                        recovery.observations == 3 &&
                        io.bytesWritten() != 0 && io.writeCalls() == 3 &&
                        io.fileSyncs() == 3 && io.directorySyncs() == 3;
                    io.end();
                }
            }
            filesystem.end();
            filesystemCleanup = filesystem.cleanupComplete();
        }
    }
    releaseFullGuidedDisposableResources();
    fullGuidedArtifactState.disposableCommitComplete = true;
    fullGuidedArtifactState.disposableCommitPassed = passed &&
        (!filesystemAttempted || filesystemCleanup) &&
        fullGuidedArtifactState.disposableResourceReleased;
    fullGuidedArtifactState.workflowPassed =
        fullGuidedArtifactState.workflowPassed &&
        fullGuidedArtifactState.disposableCommitPassed;
    fullGuidedArtifactState.step =
        fullGuidedArtifactState.disposableCommitPassed
            ? FullGuidedArtifactStep::DisposableRemountExport
            : FullGuidedArtifactStep::DisposableCleanup;
    lastRuntimeEvent = fullGuidedArtifactState.disposableCommitPassed
        ? "self_test_disposable_remount"
        : "self_test_disposable_commit_failed";
    renderInteractiveScreen(true);
}

void runFullGuidedDisposableRemountExport() {
    bool filesystemAttempted = false;
    bool filesystemCleanup = true;
    bool remountPassed = false;
    bool exportPassed = false;
    if (acquireFullGuidedDisposableResources()) {
        std::uint64_t identifiedCapacity = 0;
        if (identifyFullGuidedDisposableMedia(&identifiedCapacity)) {
            BoardSdFilesystem filesystem;
            filesystemAttempted = true;
            if (filesystem.beginReadOnly()) {
                const leshy1::storage::MediaIdentity media =
                    fullGuidedDisposableMedia(filesystem, identifiedCapacity);
                leshy1::storage::ExistingScratchReadRequest request;
                request.explicitlySelected = true;
                request.expectedFingerprint =
                    fullGuidedArtifactState.expectedFingerprint;
                request.runId = kFullGuidedDisposableRunId;
                request.scratchExists = filesystem.exists(
                    fullGuidedArtifactState.disposableScratchPath);
                const leshy1::storage::ReadPermit permit =
                    leshy1::storage::authorizeExistingScratchRead(
                        media, request);
                ArduinoFsSessionStoreIo io(
                    filesystem.driveNumber(), sdSessionStoreIoWorkspace);
                const bool opened = permit.allowed() &&
                    io.openExistingReadOnly(permit);
                leshy1::storage::SessionStoreRecoveryResult recovery;
                if (opened) {
                    recovery = leshy1::storage::recoverSession(
                        io, sessionStoreWorkspace,
                        &sessionStoreWorkspace.validationSession);
                }
                remountPassed = opened && recovery.valid() &&
                    recovery.generation == 1 && recovery.observations == 3 &&
                    io.bytesWritten() == 0 && io.writeCalls() == 0 &&
                    io.fileSyncs() == 0 && io.directorySyncs() == 0;
                if (remountPassed) {
                    LibraryController disposableLibrary;
                    exportPassed = disposableLibrary.add(
                        sessionStoreWorkspace.validationSession,
                        recovery.generation, SessionIntegrity::Valid, true,
                        false) && disposableLibrary.openSelected() &&
                        disposableLibrary.requestExport();
                    if (exportPassed) {
                        const auto json =
                            disposableLibrary.formatSelectedJsonExport(
                                diagnosticJson, sizeof(diagnosticJson));
                        fullGuidedArtifactState.disposableJsonBytes =
                            json.bytes;
                        const auto metadata = disposableLibrary.
                            formatSelectedCaptureMetadata(
                                diagnosticJson, sizeof(diagnosticJson));
                        fullGuidedArtifactState.disposableMetadataBytes =
                            metadata.bytes;
                        char row[256] = {};
                        const auto header =
                            disposableLibrary.formatSelectedCsvHeader(
                                row, sizeof(row));
                        fullGuidedArtifactState.disposableCsvBytes =
                            header.bytes;
                        exportPassed = json.valid() && json.bytes != 0 &&
                            metadata.valid() && metadata.bytes != 0 &&
                            header.valid() && header.bytes != 0;
                        for (std::size_t index = 0;
                             exportPassed && index < recovery.observations;
                             ++index) {
                            const auto record =
                                disposableLibrary.formatSelectedCsvRow(
                                    index, row, sizeof(row));
                            exportPassed = record.valid() &&
                                record.bytes != 0;
                            if (exportPassed) {
                                fullGuidedArtifactState.disposableCsvBytes +=
                                    record.bytes;
                                ++fullGuidedArtifactState.
                                    disposableCsvRecords;
                            }
                        }
                        exportPassed = exportPassed &&
                            fullGuidedArtifactState.disposableCsvRecords == 3;
                    }
                }
                io.end();
            }
            filesystem.end();
            filesystemCleanup = filesystem.cleanupComplete() &&
                filesystem.blockedWriteAttempts() == 0;
        }
    }
    releaseFullGuidedDisposableResources();
    fullGuidedArtifactState.disposableRemountComplete = true;
    fullGuidedArtifactState.disposableRemountPassed = remountPassed &&
        (!filesystemAttempted || filesystemCleanup) &&
        fullGuidedArtifactState.disposableResourceReleased;
    fullGuidedArtifactState.disposableExportComplete = true;
    fullGuidedArtifactState.disposableExportPassed = exportPassed &&
        fullGuidedArtifactState.disposableRemountPassed;
    fullGuidedArtifactState.workflowPassed =
        fullGuidedArtifactState.workflowPassed &&
        fullGuidedArtifactState.disposableRemountPassed &&
        fullGuidedArtifactState.disposableExportPassed;
    fullGuidedArtifactState.step = FullGuidedArtifactStep::DisposableCleanup;
    lastRuntimeEvent = fullGuidedArtifactState.disposableExportPassed
        ? "self_test_disposable_cleanup"
        : "self_test_disposable_remount_failed";
    renderInteractiveScreen(true);
}

bool runFullGuidedDisposableCleanup() {
    bool filesystemAttempted = false;
    bool filesystemCleanup = true;
    bool passed = !fullGuidedArtifactState.scratchCreated;
    if (acquireFullGuidedDisposableResources()) {
        std::uint64_t identifiedCapacity = 0;
        if (identifyFullGuidedDisposableMedia(&identifiedCapacity)) {
            BoardSdFilesystem filesystem;
            filesystemAttempted = true;
            if (filesystem.begin()) {
                const leshy1::storage::MediaIdentity media =
                    fullGuidedDisposableMedia(filesystem, identifiedCapacity);
                passed = removeFullGuidedDisposableScratch(filesystem, media);
            }
            filesystem.end();
            filesystemCleanup = filesystem.cleanupComplete();
        }
    }
    releaseFullGuidedDisposableResources();
    fullGuidedArtifactState.disposableCleanupComplete = true;
    fullGuidedArtifactState.disposableCleanupPassed = passed &&
        (!filesystemAttempted || filesystemCleanup) &&
        fullGuidedArtifactState.disposableResourceReleased;
    fullGuidedArtifactState.workflowPassed =
        fullGuidedArtifactState.workflowPassed &&
        fullGuidedArtifactState.disposableCleanupPassed;
    fullGuidedArtifactState.step = FullGuidedArtifactStep::ProductVerify;
    lastRuntimeEvent = fullGuidedArtifactState.disposableCleanupPassed
        ? "self_test_product_verify"
        : "self_test_disposable_cleanup_failed";
    renderInteractiveScreen(true);
    return fullGuidedArtifactState.disposableCleanupPassed;
}

void runFullGuidedProductVerify() {
    char expectedFingerprint[33] = {};
    std::snprintf(expectedFingerprint, sizeof(expectedFingerprint), "%s",
                  fullGuidedArtifactState.expectedFingerprint);
    recoverProductCatalogForFingerprint(expectedFingerprint, true);
    fullGuidedArtifactState.productVerifyComplete = true;
    fullGuidedArtifactState.productGenerationFinal =
        productBootRecovery.catalog.generation;
    fullGuidedArtifactState.productObservationsFinal =
        productBootRecovery.catalog.observations;
    const LibraryEntry* entry = libraryController.selected();
    fullGuidedArtifactState.productVerifyPassed =
        std::strcmp(productBootRecovery.status, "admitted") == 0 &&
        productBootRecovery.catalogAdmitted &&
        productBootRecovery.readOnlyGuaranteed &&
        productBootRecovery.cleanupComplete &&
        productBootRecovery.ownedAfter == 0 &&
        productBootRecovery.blockedWriteAttempts == 0 &&
        fullGuidedArtifactState.productGenerationFinal ==
            fullGuidedArtifactState.generationBefore &&
        fullGuidedArtifactState.productObservationsFinal ==
            fullGuidedArtifactState.observationsBefore &&
        entry != nullptr && entry->session != nullptr && entry->persistent &&
        entry->generation == fullGuidedArtifactState.generationBefore;
    fullGuidedArtifactState.workflowPassed =
        fullGuidedArtifactState.workflowPassed &&
        fullGuidedArtifactState.productVerifyPassed;
    finishFullGuidedActiveChecks(fullGuidedArtifactState.workflowPassed);
}

void finishFullGuidedActiveChecks(bool success) {
    const bool nrfCleanup = boardNrf24Spectrum.end();
    const bool ccCleanup = boardCc1101Spectrum.end();
    releaseFullGuidedRfResource();
    fullGuidedRfState.cleanupComplete = nrfCleanup && ccCleanup &&
        fullGuidedRfState.resourceReleased;
    restoreFullGuidedLibraryView();
    const bool storageReleased =
        resourceBroker.ownerOf(Resource::Storage) ==
            leshy1::kernel::runtime::kNoOwner &&
        resourceBroker.ownerOf(Resource::RadioSpi) ==
            leshy1::kernel::runtime::kNoOwner;
    fullGuidedArtifactState.cleanupComplete =
        productBootRecovery.cleanupComplete && storageReleased &&
        libraryController.view() == LibraryView::SessionList &&
        fullGuidedArtifactState.blockedWriteAttempts == 0 &&
        fullGuidedArtifactState.disposableCleanupPassed &&
        fullGuidedArtifactState.productVerifyPassed;
    const bool passed = success && fullGuidedRfState.cleanupComplete &&
        fullGuidedArtifactState.cleanupComplete;
    fullGuidedArtifactState.step = passed
        ? FullGuidedArtifactStep::Complete : FullGuidedArtifactStep::Failed;
    const std::uint64_t finishedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    selfTestController.completeActiveChecks(snapshotSelfTestFacts(), finishedUs);
    lastRuntimeEvent = passed ? "self_test_active_artifact_complete"
                              : "self_test_active_checks_failed";
    renderInteractiveScreen(true);
}

void startFullGuidedArtifactChecks() {
    fullGuidedArtifactState = {};
    fullGuidedArtifactState.cleanupComplete = false;
    fullGuidedArtifactState.generationBefore =
        productBootRecovery.catalog.generation;
    fullGuidedArtifactState.observationsBefore =
        productBootRecovery.catalog.observations;
    std::snprintf(fullGuidedArtifactState.expectedFingerprint,
                  sizeof(fullGuidedArtifactState.expectedFingerprint), "%s",
                  productBootRecovery.expectedFingerprint);
    std::snprintf(fullGuidedArtifactState.disposableScratchPath,
                  sizeof(fullGuidedArtifactState.disposableScratchPath),
                  "%s%s", leshy1::storage::kScratchRoot,
                  kFullGuidedDisposableRunId);
    if (!productBootRecovery.enrolled ||
        !exactCidFingerprint(fullGuidedArtifactState.expectedFingerprint)) {
        fullGuidedArtifactState.recoveryComplete = true;
        finishFullGuidedActiveChecks(false);
        return;
    }
    fullGuidedArtifactState.step = FullGuidedArtifactStep::Recover;
    fullGuidedArtifactStartAfterUs =
        static_cast<std::uint64_t>(esp_timer_get_time()) + 500000ULL;
    lastRuntimeEvent = "self_test_active_storage_recover";
    renderInteractiveScreen(true);
}

void finishFullGuidedRfChecks(bool success) {
    const bool nrfCleanup = boardNrf24Spectrum.end();
    const bool ccCleanup = boardCc1101Spectrum.end();
    releaseFullGuidedRfResource();
    fullGuidedRfState.cleanupComplete = nrfCleanup && ccCleanup &&
        fullGuidedRfState.resourceReleased;
    fullGuidedRfState.step = success && fullGuidedRfState.cleanupComplete
        ? FullGuidedRfStep::Complete : FullGuidedRfStep::Failed;
    if (!success || !fullGuidedRfState.cleanupComplete) {
        finishFullGuidedActiveChecks(false);
        return;
    }
    startFullGuidedArtifactChecks();
}

void startFullGuidedRfChecks() {
    fullGuidedRfState = {};
    fullGuidedRfState.resourceReleased = false;
    fullGuidedRfState.cleanupComplete = false;
    fullGuidedNrf24Report = {};
    fullGuidedCc1101Report = {};
    const auto radioSpi =
        leshy1::kernel::runtime::resourceMask(Resource::RadioSpi);
    fullGuidedRfState.resourceAcquired =
        resourceBroker.acquire(AppRuntime::kForegroundOwner, radioSpi);
    if (!fullGuidedRfState.resourceAcquired) {
        fullGuidedRfState.nrf24Complete = true;
        finishFullGuidedRfChecks(false);
        return;
    }
    const bool owned = resourceBroker.ownerOf(Resource::RadioSpi) ==
        AppRuntime::kForegroundOwner;
    if (!boardNrf24Spectrum.begin(
            owned,
            leshy1::drivers::radio::defaultNrf24PassiveSpectrumPlan(),
            &fullGuidedNrf24Report)) {
        fullGuidedRfState.nrf24Complete = true;
        finishFullGuidedRfChecks(false);
        return;
    }
    fullGuidedRfState.step = FullGuidedRfStep::Nrf24Sweep;
    lastRuntimeEvent = "self_test_active_nrf24";
}

bool cancelFullGuidedRfChecks() {
    const bool nrfCleanup = boardNrf24Spectrum.end();
    const bool ccCleanup = boardCc1101Spectrum.end();
    releaseFullGuidedRfResource();
    fullGuidedRfState.cleanupComplete = nrfCleanup && ccCleanup &&
        fullGuidedRfState.resourceReleased;
    bool disposableCleanup = true;
    if (fullGuidedArtifactState.scratchCreated &&
        !fullGuidedArtifactState.scratchRemoved) {
        disposableCleanup = runFullGuidedDisposableCleanup();
    }
    if (fullGuidedArtifactState.recoveryComplete) {
        char expectedFingerprint[33] = {};
        std::snprintf(expectedFingerprint, sizeof(expectedFingerprint), "%s",
                      fullGuidedArtifactState.expectedFingerprint);
        recoverProductCatalogForFingerprint(expectedFingerprint, true);
    }
    fullGuidedRfState.step = FullGuidedRfStep::Cancelled;
    fullGuidedArtifactState.step = FullGuidedArtifactStep::Cancelled;
    restoreFullGuidedLibraryView();
    fullGuidedArtifactState.cleanupComplete =
        productBootRecovery.cleanupComplete &&
        resourceBroker.ownerOf(Resource::Storage) ==
            leshy1::kernel::runtime::kNoOwner &&
        fullGuidedRfState.resourceReleased &&
        libraryController.view() == LibraryView::SessionList &&
        disposableCleanup;
    fullGuidedRfStartAfterUs = 0;
    fullGuidedArtifactStartAfterUs = 0;
    lastRuntimeEvent = fullGuidedRfState.cleanupComplete &&
                               fullGuidedArtifactState.cleanupComplete
        ? "self_test_active_cancelled"
        : "self_test_active_cancel_failed";
    return fullGuidedRfState.cleanupComplete &&
        fullGuidedArtifactState.cleanupComplete;
}

void serviceFullGuidedArtifactChecks() {
    if (fullGuidedRfState.step != FullGuidedRfStep::Complete) return;
    if (fullGuidedArtifactState.step == FullGuidedArtifactStep::Recover) {
        const std::uint64_t nowUs =
            static_cast<std::uint64_t>(esp_timer_get_time());
        if (nowUs < fullGuidedArtifactStartAfterUs) return;
        fullGuidedArtifactStartAfterUs = 0;
        char expectedFingerprint[33] = {};
        std::snprintf(expectedFingerprint, sizeof(expectedFingerprint), "%s",
                      fullGuidedArtifactState.expectedFingerprint);
        recoverProductCatalogForFingerprint(expectedFingerprint, true);
        fullGuidedArtifactState.recoveryComplete = true;
        fullGuidedArtifactState.generationAfter =
            productBootRecovery.catalog.generation;
        fullGuidedArtifactState.observationsAfter =
            productBootRecovery.catalog.observations;
        fullGuidedArtifactState.blockedWriteAttempts =
            productBootRecovery.blockedWriteAttempts;
        fullGuidedArtifactState.recoveryPassed =
            std::strcmp(productBootRecovery.status, "admitted") == 0 &&
            productBootRecovery.catalogAdmitted &&
            productBootRecovery.readOnlyGuaranteed &&
            productBootRecovery.cleanupComplete &&
            productBootRecovery.ownedAfter == 0 &&
            productBootRecovery.blockedWriteAttempts == 0 &&
            fullGuidedArtifactState.generationAfter ==
                fullGuidedArtifactState.generationBefore &&
            fullGuidedArtifactState.observationsAfter ==
                fullGuidedArtifactState.observationsBefore;
        if (!fullGuidedArtifactState.recoveryPassed) {
            finishFullGuidedActiveChecks(false);
            return;
        }
        const LibraryEntry* entry = libraryController.selected();
        if (entry == nullptr || entry->session == nullptr ||
            !entry->persistent ||
            entry->generation != fullGuidedArtifactState.generationAfter ||
            !libraryController.openSelected() ||
            !libraryController.requestExport()) {
            fullGuidedArtifactState.libraryComplete = true;
            finishFullGuidedActiveChecks(false);
            return;
        }
        fullGuidedArtifactState.step = FullGuidedArtifactStep::LibraryJson;
        lastRuntimeEvent = "self_test_active_library_json";
        renderInteractiveScreen(true);
        return;
    }
    if (fullGuidedArtifactState.step == FullGuidedArtifactStep::LibraryJson) {
        const auto json = libraryController.formatSelectedJsonExport(
            diagnosticJson, sizeof(diagnosticJson));
        const bool jsonValid = json.valid() && json.bytes != 0 &&
            std::strstr(diagnosticJson, "\"status\":\"valid\"") != nullptr;
        fullGuidedArtifactState.jsonBytes = json.bytes;
        const auto metadata = libraryController.formatSelectedCaptureMetadata(
            diagnosticJson, sizeof(diagnosticJson));
        const bool metadataValid = metadata.valid() && metadata.bytes != 0 &&
            std::strstr(diagnosticJson, "\"immutable\":true") != nullptr;
        fullGuidedArtifactState.metadataBytes = metadata.bytes;
        if (!jsonValid || !metadataValid) {
            fullGuidedArtifactState.libraryComplete = true;
            finishFullGuidedActiveChecks(false);
            return;
        }
        fullGuidedArtifactState.step = FullGuidedArtifactStep::LibraryCsv;
        lastRuntimeEvent = "self_test_active_library_csv";
        renderInteractiveScreen(true);
        return;
    }
    if (fullGuidedArtifactState.step == FullGuidedArtifactStep::LibraryCsv) {
        char row[256] = {};
        if (fullGuidedArtifactState.csvBytes == 0) {
            const auto header = libraryController.formatSelectedCsvHeader(
                row, sizeof(row));
            if (!header.valid() || header.bytes == 0) {
                fullGuidedArtifactState.libraryComplete = true;
                finishFullGuidedActiveChecks(false);
                return;
            }
            fullGuidedArtifactState.csvBytes = header.bytes;
        }
        const LibraryEntry* entry = libraryController.selected();
        if (entry == nullptr || entry->session == nullptr) {
            fullGuidedArtifactState.libraryComplete = true;
            finishFullGuidedActiveChecks(false);
            return;
        }
        if (fullGuidedArtifactState.csvIndex < entry->session->size()) {
            const auto record = libraryController.formatSelectedCsvRow(
                fullGuidedArtifactState.csvIndex, row, sizeof(row));
            if (!record.valid() || record.bytes == 0) {
                fullGuidedArtifactState.libraryComplete = true;
                finishFullGuidedActiveChecks(false);
                return;
            }
            fullGuidedArtifactState.csvBytes += record.bytes;
            ++fullGuidedArtifactState.csvRecords;
            ++fullGuidedArtifactState.csvIndex;
            return;
        }
        fullGuidedArtifactState.libraryComplete = true;
        fullGuidedArtifactState.libraryPassed =
            fullGuidedArtifactState.csvRecords == entry->session->size();
        if (!fullGuidedArtifactState.libraryPassed) {
            finishFullGuidedActiveChecks(false);
            return;
        }
        fullGuidedArtifactState.step = FullGuidedArtifactStep::CapturePcap;
        lastRuntimeEvent = "self_test_active_capture_pcap";
        renderInteractiveScreen(true);
        return;
    }
    if (fullGuidedArtifactState.step == FullGuidedArtifactStep::CapturePcap) {
        fullGuidedArtifactState.captureComplete = true;
        const LibraryEntry* entry = libraryController.selected();
        if (entry == nullptr || entry->session == nullptr) {
            finishFullGuidedActiveChecks(false);
            return;
        }
        const auto& capture = entry->session->captureMetadata();
        fullGuidedArtifactState.captureApplicable =
            capture.present && capture.framePayloadCaptured;
        if (!fullGuidedArtifactState.captureApplicable) {
            fullGuidedArtifactState.workflowPassed = true;
            fullGuidedArtifactState.step =
                FullGuidedArtifactStep::DisposableCommit;
            lastRuntimeEvent = "self_test_disposable_commit";
            renderInteractiveScreen(true);
            return;
        }
        leshy1::storage::PersistedWifiFrameCaptureView persisted;
        const auto opened = leshy1::storage::openPersistedWifiFrameCapture(
            *entry->session, sessionStoreWorkspace.segment.data(),
            sessionStoreWorkspace.segmentSize, &persisted);
        const auto& source = static_cast<
            const leshy1::domain::captures::WifiFrameSource&>(persisted);
        const std::size_t expectedBytes = opened ==
                leshy1::storage::SessionCodecStatus::Valid
            ? leshy1::apps::capture::radiotapPcapSize(source) : 0;
        FullGuidedPcapSink sink;
        const PcapExportResult pcap = opened ==
                leshy1::storage::SessionCodecStatus::Valid
            ? leshy1::apps::capture::writeRadiotapPcap(
                  source, writeFullGuidedPcapBytes, &sink)
            : PcapExportResult{};
        fullGuidedArtifactState.pcapBytes = sink.bytes;
        fullGuidedArtifactState.pcapFrames = pcap.framesWritten;
        fullGuidedArtifactState.pcapFnv1a = sink.fnv1a;
        fullGuidedArtifactState.capturePassed = pcap.valid &&
            persisted.frameCount() != 0 &&
            pcap.framesWritten == persisted.frameCount() &&
            pcap.framesWritten == capture.framePayloadRecords &&
            pcap.bytesWritten == expectedBytes && sink.bytes == expectedBytes;
        fullGuidedArtifactState.workflowPassed =
            fullGuidedArtifactState.capturePassed;
        fullGuidedArtifactState.step =
            fullGuidedArtifactState.capturePassed
                ? FullGuidedArtifactStep::DisposableCommit
                : FullGuidedArtifactStep::DisposableCleanup;
        lastRuntimeEvent = fullGuidedArtifactState.capturePassed
            ? "self_test_disposable_commit"
            : "self_test_capture_pcap_failed";
        renderInteractiveScreen(true);
        return;
    }
    if (fullGuidedArtifactState.step ==
        FullGuidedArtifactStep::DisposableCommit) {
        runFullGuidedDisposableCommit();
        return;
    }
    if (fullGuidedArtifactState.step ==
        FullGuidedArtifactStep::DisposableRemountExport) {
        runFullGuidedDisposableRemountExport();
        return;
    }
    if (fullGuidedArtifactState.step ==
        FullGuidedArtifactStep::DisposableCleanup) {
        runFullGuidedDisposableCleanup();
        return;
    }
    if (fullGuidedArtifactState.step ==
        FullGuidedArtifactStep::ProductVerify) {
        runFullGuidedProductVerify();
        return;
    }
}

void serviceFullGuidedRfChecks() {
    if (selfTestController.view() != SelfTestView::ActiveChecks) return;
    if (fullGuidedRfState.step == FullGuidedRfStep::Complete) {
        serviceFullGuidedArtifactChecks();
        return;
    }
    if (fullGuidedRfState.step == FullGuidedRfStep::Idle) {
        const std::uint64_t nowUs =
            static_cast<std::uint64_t>(esp_timer_get_time());
        if (nowUs < fullGuidedRfStartAfterUs) return;
        startFullGuidedRfChecks();
        return;
    }
    if (fullGuidedRfState.step == FullGuidedRfStep::Nrf24Sweep) {
        Nrf24PassiveSweep sweep;
        const bool swept = boardNrf24Spectrum.sweep(&sweep);
        const bool cleanup = boardNrf24Spectrum.end();
        fullGuidedRfState.nrf24Complete = true;
        fullGuidedRfState.nrf24Passed = swept && sweep.valid && cleanup &&
            fullGuidedNrf24Report.sweeps == 1 &&
            fullGuidedNrf24Report.cleanupComplete;
        if (!fullGuidedRfState.nrf24Passed) {
            finishFullGuidedRfChecks(false);
            return;
        }
        const bool owned = resourceBroker.ownerOf(Resource::RadioSpi) ==
            AppRuntime::kForegroundOwner;
        if (!boardCc1101Spectrum.begin(owned, &fullGuidedCc1101Report)) {
            fullGuidedRfState.cc1101Complete = true;
            finishFullGuidedRfChecks(false);
            return;
        }
        fullGuidedRfState.step = FullGuidedRfStep::Cc1101Sweep;
        lastRuntimeEvent = "self_test_active_cc1101";
        renderInteractiveScreen(true);
        return;
    }
    if (fullGuidedRfState.step == FullGuidedRfStep::Cc1101Sweep) {
        const Cc1101PassiveSpectrumPlan plan =
            leshy1::drivers::radio::cc1101PassiveSpectrumPlan(
                leshy1::drivers::radio::Cc1101SpectrumBand::Band433);
        Cc1101PassiveSample sample;
        const bool sampled = boardCc1101Spectrum.sample(
            plan, fullGuidedRfState.cc1101Bins, &sample);
        if (!sampled || !sample.valid) {
            fullGuidedRfState.cc1101Complete = true;
            finishFullGuidedRfChecks(false);
            return;
        }
        ++fullGuidedRfState.cc1101Bins;
        if (fullGuidedRfState.cc1101Bins <
            Cc1101PassiveSpectrumPlan::kBinCount) {
            return;
        }
        const bool cleanup = boardCc1101Spectrum.end();
        fullGuidedRfState.cc1101Complete = true;
        fullGuidedRfState.cc1101Passed = cleanup &&
            fullGuidedCc1101Report.samples ==
                Cc1101PassiveSpectrumPlan::kBinCount &&
            fullGuidedCc1101Report.cleanupComplete;
        finishFullGuidedRfChecks(fullGuidedRfState.cc1101Passed);
    }
}

void releaseWifiFrameCaptureRfLease() {
    // The Wi-Fi product owns ESP RF for its whole menu lifetime. The separate
    // Capture app releases RF immediately after a bounded recording.
    if (wifiProductView == WifiProductView::Capture) return;
    resourceBroker.release(
        AppRuntime::kForegroundOwner,
        leshy1::kernel::runtime::resourceMask(Resource::EspRf));
}

bool startWifiFrameCapture() {
    wifiFrameCapture.reset();
    capturePersistState = CapturePersistState::Result;
    capturePersistStatus = "volatile";
    capturePersistGeneration = 0;
    wifiCaptureRenderedFrames = UINT32_MAX;
    wifiCaptureRenderedDrops = UINT32_MAX;
    wifiCaptureRenderedChannel = 0xffU;
    std::uint64_t startedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    if (startedUs == 0U) startedUs = 1U;
    const bool started =
        wifiFrameCapture.begin(kProductWifiFrameCapturePlan, startedUs);
    nextCaptureUiRefreshUs = startedUs + 500000ULL;
    lastRuntimeEvent = started ? "capture_running" : "capture_start_failed";
    if (!started) releaseWifiFrameCaptureRfLease();
    return true;
}

bool stopWifiFrameCapture() {
    std::uint64_t endedUs = static_cast<std::uint64_t>(esp_timer_get_time());
    if (endedUs == 0U) endedUs = 1U;
    const bool cleanup = wifiFrameCapture.stop(endedUs);
    releaseWifiFrameCaptureRfLease();
    const auto state = wifiFrameCapture.stats().state;
    lastRuntimeEvent =
        state == WifiFrameCaptureState::Complete && cleanup
            ? "capture_complete"
            : "capture_failed";
    return true;
}

void serviceWifiFrameCapture() {
    const auto before = wifiFrameCapture.stats();
    if (before.state != WifiFrameCaptureState::Running) return;
    std::uint64_t nowUs = static_cast<std::uint64_t>(esp_timer_get_time());
    if (nowUs == 0U) nowUs = 1U;
    wifiFrameCapture.service(nowUs);
    const auto after = wifiFrameCapture.stats();
    const bool terminal = after.state != WifiFrameCaptureState::Running;
    if (terminal) {
        releaseWifiFrameCaptureRfLease();
        lastRuntimeEvent = after.state == WifiFrameCaptureState::Complete &&
                                   wifiFrameCapture.cleanupComplete()
                               ? "capture_complete"
                               : "capture_failed";
    }
    const bool productRoute = uiController.page() == 2 &&
        wifiProductView == WifiProductView::Capture;
    const bool captureRoute = uiController.page() == 4 &&
        captureView == CaptureView::Wifi;
    if ((productRoute || captureRoute) && terminal) {
        nextCaptureUiRefreshUs = 0;
        renderInteractiveScreen(true);
    } else if ((productRoute || captureRoute) &&
               nowUs >= nextCaptureUiRefreshUs) {
        nextCaptureUiRefreshUs = nowUs + 500000ULL;
        display.startWrite();
        renderWifiCaptureLiveData();
        display.endWrite();
    }
}

bool startInfraredCapture() {
    infraredCapture.reset();
    infraredCapturePersistState = CapturePersistState::Result;
    infraredCapturePersistStatus = "volatile";
    infraredCapturePersistGeneration = 0;
    infraredReceiverReport = {};
    bool initialLevel = true;
    std::uint64_t startedUs = 0;
    const bool owned = resourceBroker.ownerOf(Resource::RadioSpi) ==
        AppRuntime::kForegroundOwner;
    const bool hardwareReady = boardInfraredReceiver.begin(
        owned, &infraredReceiverReport, &initialLevel, &startedUs);
    const bool started = hardwareReady && infraredCapture.begin(
        kProductInfraredCapturePlan, startedUs, initialLevel);
    if (!started) {
        boardInfraredReceiver.end();
        if (infraredCapture.stats().state == InfraredCaptureState::Waiting) {
            infraredCapture.fail(-1, startedUs == 0U ? 1U : startedUs);
        }
    }
    nextCaptureUiRefreshUs = startedUs + 200000ULL;
    lastRuntimeEvent = started ? "infrared_raw_waiting"
                               : "infrared_raw_start_failed";
    return true;
}

bool stopInfraredCapture() {
    std::uint64_t endedUs = static_cast<std::uint64_t>(esp_timer_get_time());
    if (endedUs == 0U) endedUs = 1U;
    const auto state = infraredCapture.stats().state;
    if (state == InfraredCaptureState::Waiting ||
        state == InfraredCaptureState::Capturing) {
        infraredCapture.cancel(endedUs);
    }
    const bool cleanup = boardInfraredReceiver.end();
    nextCaptureUiRefreshUs = 0;
    lastRuntimeEvent = cleanup ? "infrared_raw_stopped"
                               : "infrared_raw_cleanup_failed";
    return true;
}

void serviceInfraredCapture() {
    if (uiController.page() != 4 || captureView != CaptureView::Infrared) {
        return;
    }
    const auto before = infraredCapture.stats().state;
    if (before != InfraredCaptureState::Waiting &&
        before != InfraredCaptureState::Capturing) {
        return;
    }
    bool level = true;
    std::uint64_t sampleUs = 0;
    if (!boardInfraredReceiver.sample(&level, &sampleUs)) {
        const std::uint64_t nowUs =
            static_cast<std::uint64_t>(esp_timer_get_time());
        infraredCapture.fail(-2, nowUs == 0U ? 1U : nowUs);
        boardInfraredReceiver.end();
        lastRuntimeEvent = "infrared_raw_runtime_fault";
        renderInteractiveScreen(true);
        return;
    }
    infraredCapture.ingest({sampleUs, level});
    const auto after = infraredCapture.stats().state;
    const bool terminal = after != InfraredCaptureState::Waiting &&
        after != InfraredCaptureState::Capturing;
    if (terminal) {
        const bool cleanup = boardInfraredReceiver.end();
        lastRuntimeEvent = !cleanup
            ? "infrared_raw_cleanup_failed"
            : after == InfraredCaptureState::Complete
                  ? "infrared_raw_complete"
                  : after == InfraredCaptureState::TimedOut
                        ? "infrared_raw_no_signal"
                        : after == InfraredCaptureState::Unreliable
                              ? "infrared_raw_unreliable"
                              : "infrared_raw_terminal";
    }
    // The TFT and touch controller share long transactions with GPIO timing.
    // Once the first IR edge is observed, keep the hot path measurement-only.
    if (terminal) {
        nextCaptureUiRefreshUs = 0;
        renderInteractiveScreen(true);
    }
}

void emitUiState(Stream& reply, UiAction action, bool changed) {
    auto& line = diagnosticJson;
    line[0] = '\0';
    const AppMenuItem* selected = appCatalog.get(uiController.selection());
    const LibraryEntry* selectedLibrary = libraryController.selected();
    std::snprintf(line, sizeof(line),
                  "{\"schema\":\"leshy.ui.v1\",\"kind\":\"state\","
                  "\"action\":\"%s\",\"changed\":%s,\"page\":\"%s\","
                  "\"parent_page\":\"%s\",\"device_selection\":%u,"
                  "\"selection\":%u,\"selected_id\":\"%s\","
                  "\"selected_enabled\":%s,\"reason\":\"%s\","
                  "\"language\":\"%s\",\"language_selection\":%u,"
                  "\"revision\":%lu,\"safety_state\":\"%s\","
                  "\"safety_reason\":\"%s\",\"safety_latched\":%s,"
                  "\"safety_clear_pending\":%s,\"render_mode\":\"%s\","
                  "\"render_us\":%llu}",
                  leshy1::ui::uiActionName(action), changed ? "true" : "false",
                  safetySupervisor.latched()
                      ? "safe_mode"
                      : leshy1::ui::probePageName(uiController.page()),
                  leshy1::ui::probePageName(uiController.parentPage()),
                  static_cast<unsigned>(deviceSelection),
                  static_cast<unsigned>(uiController.selection()),
                  selected == nullptr ? "none" : selected->id,
                  selected != nullptr && selected->enabled ? "true" : "false",
                  selected == nullptr ? "missing selection" : selected->reason,
                  leshy1::ui::uiLanguageName(languageController.active()),
                  static_cast<unsigned>(languageController.selection()),
                  static_cast<unsigned long>(uiController.revision()),
                  leshy1::kernel::safety::safetyStateName(
                      safetySupervisor.state()),
                  leshy1::kernel::safety::safetyReasonName(
                      safetySupervisor.reason()),
                  safetySupervisor.latched() ? "true" : "false",
                  safetySupervisor.clearPending() ? "true" : "false",
                  lastUiRenderWasIncremental ? "incremental" : "full",
                  static_cast<unsigned long long>(lastUiRenderUs));
    const std::size_t length = std::strlen(line);
    if (length > 0 && length < sizeof(line)) {
        const SurveyPipelineProgress pipelineProgress = surveyPipeline.progress();
        const auto* wifiTimeline =
            productSurveyTimeline.source(RadioKind::Wifi);
        const auto* bleTimeline =
            productSurveyTimeline.source(RadioKind::Ble);
        const auto* storedTimeline =
            selectedLibrary != nullptr && selectedLibrary->session != nullptr
                ? &selectedLibrary->session->timeline() : nullptr;
        std::uint64_t timelineAsOfUs =
            productSurveyTimeline.state() == SourceTimelineState::Running
                ? static_cast<std::uint64_t>(esp_timer_get_time())
                : productSurveyTimeline.endedUs();
        if (timelineAsOfUs == 0) timelineAsOfUs = 1;
        const SelfTestReport& selfTestReport = selfTestController.report();
        const SelfTestMode visibleSelfTestMode =
            selfTestController.view() == SelfTestView::Result
                ? selfTestReport.mode
                : selfTestController.selectedMode();
        const auto wifiDeviceStats = wifiFrameCapture.deviceMonitorStats();
        const auto wifiChannelStats = wifiFrameCapture.channelMonitorStats();
        const auto wifiChannelSnapshot = wifiFrameCapture.channelLoadSnapshot();
        line[length - 1] = '\0';
        const std::size_t detailCapacity = sizeof(line) - length + 1;
        const int detailLength = std::snprintf(
                      line + length - 1, detailCapacity,
                      ",\"runtime_event\":\"%s\",\"runtime_owner\":\"%s\","
                      "\"lease_mask\":%lu,\"survey_simulated\":%s,"
                      "\"survey_view\":\"%s\",\"survey_workflow_state\":\"%s\","
                      "\"survey_workflow_status\":\"%s\",\"survey_running\":%s,"
                      "\"survey_observations\":%u,\"survey_selection\":%u,"
                      "\"survey_generation\":%lu,\"survey_persistent\":%s,"
                      "\"survey_pipeline_status\":\"%s\","
                      "\"survey_received\":%llu,\"survey_forwarded\":%llu,"
                      "\"survey_dropped\":%llu,\"survey_queue_depth\":%u,"
                      "\"survey_queue_high_water\":%u,"
                      "\"survey_batch_trigger\":\"%s\","
                      "\"survey_setup_view\":\"%s\","
                      "\"survey_setup_selection\":%u,"
                      "\"survey_source_selected_mask\":%u,"
                      "\"survey_source_selected_count\":%u,"
                      "\"survey_source_can_start\":%s,"
                      "\"survey_source_wifi_state\":\"%s\","
                      "\"survey_source_ble_state\":\"%s\","
                      "\"survey_timeline_state\":\"%s\","
                      "\"survey_timeline_status\":\"%s\","
                      "\"survey_timeline_archive_status\":\"%s\","
                      "\"survey_timeline_healthy\":%s,"
                      "\"survey_timeline_failure_status\":\"%s\","
                      "\"survey_timeline_failure_stage\":\"%s\","
                      "\"survey_timeline_failure_event_us\":%llu,"
                      "\"survey_timeline_failure_latest_us\":%llu,"
                      "\"survey_timeline_archived_windows\":%lu,"
                      "\"survey_timeline_persisted\":%s,"
                      "\"survey_timeline_persisted_windows\":%lu,"
                      "\"survey_timeline_retained_windows\":%u,"
                      "\"survey_timeline_evicted_windows\":%lu,"
                      "\"survey_timeline_selected_mask\":%u,"
                      "\"survey_timeline_queue_depth\":%u,"
                      "\"survey_timeline_queue_high_water\":%u,"
                      "\"survey_timeline_overflow\":%llu,"
                      "\"survey_timeline_wifi_state\":\"%s\","
                      "\"survey_timeline_wifi_duty_permille\":%u,"
                      "\"survey_timeline_wifi_accepted\":%llu,"
                      "\"survey_timeline_wifi_dropped\":%llu,"
                      "\"survey_timeline_ble_state\":\"%s\","
                      "\"survey_timeline_ble_duty_permille\":%u,"
                      "\"survey_timeline_ble_accepted\":%llu,"
                      "\"survey_timeline_ble_dropped\":%llu,"
                      "\"survey_product_selected_source_mask\":%u,"
                      "\"survey_product_active_source_mask\":%u,"
                      "\"survey_product_unavailable_source_mask\":%u,"
                      "\"survey_product_selected\":%s,"
                      "\"survey_product_status\":\"%s\","
                      "\"survey_product_backend_open\":%s,"
                      "\"survey_product_storage_mounted\":%s,"
                      "\"survey_product_store_status\":\"%s\","
                      "\"survey_product_admission_status\":\"%s\","
                      "\"survey_product_expected_cid\":\"%s\","
                      "\"survey_product_observed_cid\":\"%s\","
                      "\"survey_product_identity_status\":\"%s\","
                      "\"survey_product_identity_attempts\":%u,"
                      "\"survey_product_identity_transient_retries\":%u,"
                      "\"survey_product_capacity_bytes\":%llu,"
                      "\"survey_product_cached_free_bytes\":%llu,"
                      "\"survey_scan_status\":\"%s\","
                      "\"survey_scan_reported\":%u,"
                      "\"survey_scan_read\":%u,"
                      "\"survey_scan_accepted\":%u,"
                      "\"survey_scan_rejected\":%u,"
                      "\"survey_scan_dropped\":%u,"
                      "\"survey_ble_scan_status\":\"%s\","
                      "\"survey_ble_scan_reported\":%u,"
                      "\"survey_ble_scan_read\":%u,"
                      "\"survey_ble_scan_accepted\":%u,"
                      "\"survey_ble_scan_rejected\":%u,"
                      "\"survey_ble_scan_dropped\":%u,"
                      "\"survey_product_cleanup_complete\":%s,"
                      "\"survey_product_worker_ready\":%s,"
                      "\"survey_product_source_active\":%s,"
                      "\"survey_product_source_start_attempted\":%s,"
                      "\"survey_product_source_failure_injected\":%s,"
                      "\"survey_product_source_injection_armed\":%s,"
                      "\"survey_product_runtime_source_failure_injected\":%s,"
                      "\"survey_product_runtime_source_failure_injected_mask\":%u,"
                      "\"survey_product_runtime_source_injection_armed_mask\":%u,"
                      "\"survey_product_store_open_attempted\":%s,"
                      "\"survey_product_store_bytes_written\":%llu,"
                      "\"survey_product_scan_active\":%s,"
                      "\"survey_product_cancel_requested_during_scan\":%s,"
                      "\"survey_product_scan_cycles\":%lu,"
                      "\"survey_product_wifi_scan_cycles\":%lu,"
                      "\"survey_product_ble_scan_cycles\":%lu,"
                      "\"survey_product_start_action_us\":%llu,"
                      "\"survey_product_stop_action_us\":%llu,"
                      "\"wifi_product_view\":\"%s\","
                      "\"wifi_product_selection\":%u,"
                      "\"ble_product_view\":\"%s\","
                      "\"ble_device_selection\":%u,"
                      "\"ble_devices_unique\":%u,"
                      "\"ble_devices_strongest_first\":%s,"
                      "\"ble_device_catalog_revision\":%lu,"
                      "\"wifi_network_selection\":%u,"
                      "\"wifi_network_visible_size\":%u,"
                      "\"wifi_network_navigation_locked\":%s,"
                      "\"wifi_network_order_hash\":%lu,"
                      "\"wifi_network_selected_identity_hash\":%lu,"
                      "\"wifi_networks_unique\":%u,"
                      "\"wifi_networks_strongest_first\":%s,"
                      "\"wifi_network_catalog_revision\":%lu,"
                      "\"wifi_device_selection\":%u,"
                      "\"wifi_device_visible_size\":%u,"
                      "\"wifi_device_navigation_locked\":%s,"
                      "\"wifi_device_order_hash\":%lu,"
                      "\"wifi_devices_unique\":%u,"
                      "\"wifi_devices_strongest_first\":%s,"
                      "\"wifi_device_catalog_revision\":%lu,"
                      "\"wifi_device_oui_database_available\":%s,"
                      "\"wifi_device_oui_records\":%u,"
                      "\"wifi_device_detail_private_mac\":%s,"
                      "\"wifi_device_detail_ssid_known\":%s,"
                      "\"wifi_device_detail_wps_identity_known\":%s,"
                      "\"wifi_device_detail_generation\":\"%s\","
                      "\"wifi_device_detail_last_seen_us\":%llu,"
                      "\"wifi_device_detail_rssi_dbm\":%d,"
                      "\"wifi_device_monitor_active\":%s,"
                      "\"wifi_device_channel_locked\":%s,"
                      "\"wifi_device_monitor_cleanup_complete\":%s,"
                      "\"wifi_device_nvs_disabled\":%s,"
                      "\"wifi_device_volatile_storage_only\":%s,"
                      "\"wifi_device_frames_reported\":%lu,"
                      "\"wifi_device_clients_accepted\":%lu,"
                      "\"wifi_device_clients_dropped\":%lu,"
                      "\"wifi_device_channel_hops\":%lu,"
                      "\"wifi_device_current_channel\":%u,"
                      "\"wifi_channel_monitor_active\":%s,"
                      "\"wifi_channel_monitor_cleanup_complete\":%s,"
                      "\"wifi_channel_frames_reported\":%lu,"
                      "\"wifi_channel_invalid_frames\":%lu,"
                      "\"wifi_channel_hops\":%lu,"
                      "\"wifi_channel_current\":%u,"
                      "\"wifi_channel_revision\":%lu,"
                      "\"wifi_channel_completed_dwells\":%lu,"
                      "\"wifi_channel_completed_sweeps\":%lu,"
                      "\"wifi_channel_measured_mask\":%u,"
                      "\"wifi_channel_best_primary\":%u,"
                      "\"library_simulated\":%s,\"library_view\":\"%s\","
                      "\"library_entries\":%u,\"library_generation\":%lu,"
                      "\"library_persistent\":%s,"
                      "\"self_test_view\":\"%s\","
                      "\"self_test_visual_state\":\"%s\","
                      "\"self_test_mode\":\"%s\","
                      "\"self_test_status\":\"%s\","
                      "\"self_test_checks\":%u,\"self_test_passed\":%u,"
                      "\"self_test_failed\":%u,\"self_test_blocked\":%u,"
                      "\"self_test_not_applicable\":%u,"
                      "\"self_test_read_only\":%s,"
                      "\"self_test_active_step\":\"%s\","
                      "\"self_test_active_cc_bins\":%u,"
                      "\"self_test_artifact_step\":\"%s\","
                      "\"self_test_artifact_recovery_complete\":%s,"
                      "\"self_test_artifact_library_complete\":%s,"
                      "\"self_test_artifact_capture_complete\":%s,"
                      "\"self_test_artifact_pcap_frames\":%u}",
                      lastRuntimeEvent, appRuntime.activeApp(),
                      static_cast<unsigned long>(appRuntime.activeResources()),
                      surveyWorkflow.simulated() ? "true" : "false",
                      leshy1::apps::survey::surveyViewName(
                          surveyController.view()),
                      leshy1::apps::survey::surveyWorkflowStateName(
                          surveyWorkflow.state()),
                      leshy1::apps::survey::surveyWorkflowStatusName(
                          surveyWorkflow.lastStatus()),
                      surveySession.state() == SessionState::Running ? "true" : "false",
                      static_cast<unsigned>(surveySession.size()),
                      static_cast<unsigned>(surveyController.selection()),
                      static_cast<unsigned long>(surveyWorkflow.generation()),
                      surveyWorkflow.persistent() ? "true" : "false",
                      leshy1::apps::survey::surveyPipelineStatusName(
                          surveyPipeline.lastStatus()),
                      static_cast<unsigned long long>(pipelineProgress.received),
                      static_cast<unsigned long long>(pipelineProgress.forwarded),
                      static_cast<unsigned long long>(pipelineProgress.dropped),
                      static_cast<unsigned>(pipelineProgress.queueDepth),
                      static_cast<unsigned>(pipelineProgress.queueHighWater),
                      leshy1::services::survey::sessionBatchTriggerName(
                          pipelineProgress.trigger),
                      leshy1::apps::survey::surveySetupViewName(
                          surveySourceController.view()),
                      static_cast<unsigned>(
                          surveySourceController.selection()),
                      static_cast<unsigned>(
                          surveySourceController.selectedMask()),
                      static_cast<unsigned>(
                          surveySourceController.selectedCount()),
                      surveySourceController.canStart() ? "true" : "false",
                      leshy1::apps::survey::surveySourceStateName(
                          surveySourceController.find(SurveySourceKind::Wifi) ==
                                  nullptr
                              ? SurveySourceState::Unavailable
                              : surveySourceController.find(
                                    SurveySourceKind::Wifi)->state),
                      leshy1::apps::survey::surveySourceStateName(
                          surveySourceController.find(SurveySourceKind::Ble) ==
                                  nullptr
                              ? SurveySourceState::Unavailable
                              : surveySourceController.find(
                                    SurveySourceKind::Ble)->state),
                      leshy1::services::survey::sourceTimelineStateName(
                          productSurveyTimeline.state()),
                      productSurveyRuntime.timelineStatus,
                      productSurveyRuntime.timelineArchiveStatus,
                      productSurveyRuntime.timelineHealthy ? "true" : "false",
                      productSurveyRuntime.timelineFailureStatus,
                      productSurveyRuntime.timelineFailureStage,
                      static_cast<unsigned long long>(
                          productSurveyRuntime.timelineFailureEventUs),
                      static_cast<unsigned long long>(
                          productSurveyRuntime.timelineFailureLatestUs),
                      static_cast<unsigned long>(
                          productSurveyRuntime.timelineArchivedWindows),
                      storedTimeline != nullptr && storedTimeline->present &&
                              storedTimeline->finalized
                          ? "true" : "false",
                      static_cast<unsigned long>(
                          storedTimeline == nullptr
                              ? 0 : storedTimeline->totalWindows),
                      static_cast<unsigned>(
                          selectedLibrary == nullptr ||
                                  selectedLibrary->session == nullptr
                              ? 0
                              : selectedLibrary->session->timelineWindowCount()),
                      static_cast<unsigned long>(
                          storedTimeline == nullptr
                              ? 0 : storedTimeline->evictedWindows),
                      static_cast<unsigned>(
                          productSurveyTimeline.selectedMask()),
                      static_cast<unsigned>(
                          productSurveyTimeline.queuedWindows()),
                      static_cast<unsigned>(
                          productSurveyTimeline.windowHighWater()),
                      static_cast<unsigned long long>(
                          productSurveyTimeline.overflowEvents()),
                      leshy1::services::survey::sourceWindowStateName(
                          wifiTimeline == nullptr
                              ? SourceWindowState::Unselected
                              : wifiTimeline->state),
                      static_cast<unsigned>(
                          productSurveyTimeline.dutyPermille(
                              RadioKind::Wifi, timelineAsOfUs)),
                      static_cast<unsigned long long>(
                          wifiTimeline == nullptr ? 0 : wifiTimeline->accepted),
                      static_cast<unsigned long long>(
                          wifiTimeline == nullptr ? 0 : wifiTimeline->dropped),
                      leshy1::services::survey::sourceWindowStateName(
                          bleTimeline == nullptr
                              ? SourceWindowState::Unselected
                              : bleTimeline->state),
                      static_cast<unsigned>(
                          productSurveyTimeline.dutyPermille(
                              RadioKind::Ble, timelineAsOfUs)),
                      static_cast<unsigned long long>(
                          bleTimeline == nullptr ? 0 : bleTimeline->accepted),
                      static_cast<unsigned long long>(
                          bleTimeline == nullptr ? 0 : bleTimeline->dropped),
                      static_cast<unsigned>(
                          productSurveyRuntime.selectedSourceMask),
                      static_cast<unsigned>(
                          productSurveyRuntime.activeSourceMask),
                      static_cast<unsigned>(
                          productSurveyRuntime.unavailableSourceMask),
                      productSurveyRuntime.selected ? "true" : "false",
                      productSurveyRuntime.status,
                      productSurveyRuntime.backendOpen ? "true" : "false",
                      productSurveyFilesystem.mounted() ? "true" : "false",
                      leshy1::storage::productStoreAccessStatusName(
                          productSurveyRuntime.storeStatus),
                      leshy1::apps::survey::productSurveyAdmissionStatusName(
                          productSurveyRuntime.admissionStatus),
                      productSurveyRuntime.expectedFingerprint,
                      productSurveyRuntime.observedFingerprint,
                      leshy1::storage::sdTransportRunStatusName(
                          productSurveyRuntime.identityStatus),
                      static_cast<unsigned>(
                          productSurveyRuntime.identityAttempts),
                      static_cast<unsigned>(
                          productSurveyRuntime.identityTransientRetries),
                      static_cast<unsigned long long>(
                          productSurveyRuntime.cardCapacityBytes),
                      static_cast<unsigned long long>(
                          productSurveyRuntime.cachedFreeBytes),
                      leshy1::platform::arduino::boardWifiScanStatusName(
                          productSurveyRuntime.scan.status),
                      static_cast<unsigned>(
                          productSurveyRuntime.scan.recordsReported),
                      static_cast<unsigned>(
                          productSurveyRuntime.scan.recordsRead),
                      static_cast<unsigned>(productSurveyRuntime.scan.accepted),
                      static_cast<unsigned>(productSurveyRuntime.scan.rejected),
                      static_cast<unsigned>(productSurveyRuntime.scan.dropped),
                      leshy1::platform::arduino::boardBleScanStatusName(
                          productSurveyRuntime.bleScan.status),
                      static_cast<unsigned>(
                          productSurveyRuntime.bleScan.recordsReported),
                      static_cast<unsigned>(
                          productSurveyRuntime.bleScan.recordsRead),
                      static_cast<unsigned>(
                          productSurveyRuntime.bleScan.accepted),
                      static_cast<unsigned>(
                          productSurveyRuntime.bleScan.rejected),
                      static_cast<unsigned>(
                          productSurveyRuntime.bleScan.dropped),
                      productSurveyRuntime.cleanupComplete ? "true" : "false",
                      productSurveyRuntime.workerReady ? "true" : "false",
                      productSurveyRuntime.sourceActive ? "true" : "false",
                      productSurveyRuntime.sourceStartAttempted ? "true" : "false",
                      productSurveyRuntime.sourceFailureInjected ? "true" : "false",
                      productSurveySourceUnavailableInjectionArmed()
                          ? "true" : "false",
                      productSurveyRuntime.runtimeSourceFailureInjected
                          ? "true" : "false",
                      static_cast<unsigned>(
                          productSurveyRuntime.runtimeSourceFailureInjectedMask),
                      static_cast<unsigned>(
                          productSurveyRuntimeUnavailableInjectionMask()),
                      productSurveyRuntime.storeOpenAttempted ? "true" : "false",
                      static_cast<unsigned long long>(
                          productSurveyRuntime.storeBytesWritten),
                      productSurveyScanActive() ? "true" : "false",
                      productSurveyRuntime.cancelRequestedDuringScan
                          ? "true" : "false",
                      static_cast<unsigned long>(
                          productSurveyRuntime.scanCycles),
                      static_cast<unsigned long>(
                          productSurveyRuntime.wifiScanCycles),
                      static_cast<unsigned long>(
                          productSurveyRuntime.bleScanCycles),
                      static_cast<unsigned long long>(
                          productSurveyRuntime.startActionUs),
                      static_cast<unsigned long long>(
                          productSurveyRuntime.stopActionUs),
                      wifiProductViewName(wifiProductView),
                      static_cast<unsigned>(wifiProductSelection),
                      bleProductViewName(bleProductView),
                      static_cast<unsigned>(bleDeviceSelection),
                      static_cast<unsigned>(bleDeviceCatalog.size()),
                      bleDeviceCatalog.strongestFirst() ? "true" : "false",
                      static_cast<unsigned long>(bleDeviceCatalog.revision()),
                      static_cast<unsigned>(wifiNetworkSelection),
                      static_cast<unsigned>(wifiNetworkVisibleSize()),
                      wifiNetworkNavigationOrder.locked() ? "true" : "false",
                      static_cast<unsigned long>(
                          wifiNetworkNavigationOrder.orderHash(
                              wifiNetworkCatalog)),
                      static_cast<unsigned long>(
                          wifiNetworkNavigationOrder.identityHash(
                              wifiNetworkCatalog, wifiNetworkSelection)),
                      static_cast<unsigned>(wifiNetworkCatalog.size()),
                      wifiNetworkCatalog.strongestFirst() ? "true" : "false",
                      static_cast<unsigned long>(
                          wifiNetworkCatalog.revision()),
                      static_cast<unsigned>(wifiDeviceSelection),
                      static_cast<unsigned>(wifiDeviceVisibleSize()),
                      wifiDeviceNavigationOrder.locked() ? "true" : "false",
                      static_cast<unsigned long>(
                          wifiDeviceNavigationOrder.orderHash(
                              wifiDeviceCatalog)),
                      static_cast<unsigned>(wifiDeviceCatalog.size()),
                      wifiDeviceCatalog.strongestFirst() ? "true" : "false",
                      static_cast<unsigned long>(wifiDeviceCatalog.revision()),
                      wifiOuiDatabase.available() ? "true" : "false",
                      static_cast<unsigned>(wifiOuiDatabase.records()),
                      wifiDeviceDetail.locallyAdministered ? "true" : "false",
                      wifiDeviceDetail.ssidLength != 0U ? "true" : "false",
                      (wifiDeviceDetail.wpsDeviceNameLength != 0U ||
                       wifiDeviceDetail.wpsManufacturerLength != 0U ||
                       wifiDeviceDetail.wpsModelLength != 0U)
                          ? "true" : "false",
                      leshy1::apps::wifi::wifiDeviceGenerationName(
                          wifiDeviceDetail.generation),
                      static_cast<unsigned long long>(
                          wifiDeviceDetail.monotonicUs),
                      static_cast<int>(wifiDeviceDetail.rssiDbm),
                      wifiDeviceStats.active ? "true" : "false",
                      wifiFrameCapture.deviceChannelLocked() ? "true" : "false",
                      wifiDeviceStats.cleanupComplete ? "true" : "false",
                      wifiFrameCapture.nvsDisabled() ? "true" : "false",
                      wifiFrameCapture.volatileStorageOnly() ? "true" : "false",
                      static_cast<unsigned long>(wifiDeviceStats.framesReported),
                      static_cast<unsigned long>(wifiDeviceStats.clientsAccepted),
                      static_cast<unsigned long>(wifiDeviceStats.clientsDropped),
                      static_cast<unsigned long>(wifiDeviceStats.channelHops),
                      static_cast<unsigned>(wifiFrameCapture.currentChannel()),
                      wifiChannelStats.active ? "true" : "false",
                      wifiChannelStats.cleanupComplete ? "true" : "false",
                      static_cast<unsigned long>(
                          wifiChannelStats.framesReported),
                      static_cast<unsigned long>(
                          wifiChannelStats.invalidFrames),
                      static_cast<unsigned long>(wifiChannelStats.channelHops),
                      static_cast<unsigned>(wifiFrameCapture.currentChannel()),
                      static_cast<unsigned long>(wifiChannelSnapshot.revision),
                      static_cast<unsigned long>(
                          wifiChannelSnapshot.completedDwells),
                      static_cast<unsigned long>(
                          wifiChannelSnapshot.completedSweeps),
                      static_cast<unsigned>(wifiChannelSnapshot.measuredMask),
                      static_cast<unsigned>(
                          wifiFrameCapture.bestPrimaryChannel()),
                      selectedLibrary != nullptr && selectedLibrary->simulated
                          ? "true" : "false",
                      libraryController.view() == LibraryView::ExportReady
                          ? "export_ready"
                          : (libraryController.view() == LibraryView::SessionDetail
                                 ? "detail"
                                 : "list"),
                      static_cast<unsigned>(libraryController.size()),
                      static_cast<unsigned long>(selectedLibrary == nullptr
                                                     ? 0
                                                     : selectedLibrary->generation),
                      selectedLibrary != nullptr && selectedLibrary->persistent
                          ? "true" : "false",
                      leshy1::apps::self_test::selfTestViewName(
                          selfTestController.view()),
                      selfTestController.view() == SelfTestView::VisualCheck
                          ? leshy1::apps::self_test::selfTestVisualStateName(
                                selfTestController.visualState())
                          : "none",
                      leshy1::apps::self_test::selfTestModeName(
                          visibleSelfTestMode),
                      leshy1::apps::self_test::selfTestResultStatusName(
                          selfTestReport.status),
                      static_cast<unsigned>(selfTestReport.checkCount),
                      static_cast<unsigned>(selfTestReport.passed),
                      static_cast<unsigned>(selfTestReport.failed),
                      static_cast<unsigned>(selfTestReport.blocked),
                      static_cast<unsigned>(selfTestReport.notApplicable),
                      selfTestReport.readOnly ? "true" : "false",
                      fullGuidedRfStepName(fullGuidedRfState.step),
                      static_cast<unsigned>(fullGuidedRfState.cc1101Bins),
                      fullGuidedArtifactStepName(
                          fullGuidedArtifactState.step),
                      fullGuidedArtifactState.recoveryComplete
                          ? "true" : "false",
                      fullGuidedArtifactState.libraryComplete
                          ? "true" : "false",
                      fullGuidedArtifactState.captureComplete
                          ? "true" : "false",
                      static_cast<unsigned>(
                          fullGuidedArtifactState.pcapFrames));
        if (detailLength < 0 ||
            static_cast<std::size_t>(detailLength) >= detailCapacity) {
            std::snprintf(
                line, sizeof(line),
                "{\"schema\":\"leshy.ui.v1\",\"kind\":\"error\","
                "\"error\":\"state_overflow\"}");
        }
    }
    reply.println(line);
}

void emitWifiFrameCaptureState(Stream& reply) {
    const auto stats = wifiFrameCapture.stats();
    const auto& plan = wifiFrameCapture.capture().plan();
    const std::size_t pcapBytes =
        leshy1::apps::capture::radiotapPcapSize(wifiFrameCapture.capture());
    char line[1024] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.capture.wifi_frame.v1\",\"kind\":\"state\","
        "\"state\":\"%s\",\"passive_only\":true,\"rx_only\":true,"
        "\"application_connect_calls\":0,\"application_raw_tx_calls\":0,"
        "\"physical_no_tx_verified\":false,\"storage_written\":%s,"
        "\"volatile_ram\":true,\"immutable_after_stop\":true,"
        "\"persist_state\":\"%s\",\"persist_status\":\"%s\","
        "\"persist_generation\":%lu,"
        "\"channel_plan\":%u,\"current_channel\":%u,"
        "\"duration_ms\":%lu,\"channel_dwell_ms\":%u,"
        "\"snap_length\":%u,\"maximum_frames\":%u,"
        "\"started_us\":%llu,\"ended_us\":%llu,"
        "\"frames_reported\":%lu,\"frames_accepted\":%lu,"
        "\"frames_dropped_capacity\":%lu,"
        "\"frames_dropped_invalid\":%lu,\"payload_bytes\":%lu,"
        "\"driver_error\":%ld,\"pcap_available\":%s,"
        "\"pcap_bytes\":%u,\"pcap_linktype\":127,"
        "\"pcap_timebase\":\"monotonic_us\","
        "\"cleanup_complete\":%s,\"lease_mask\":%lu}",
        leshy1::apps::capture::wifiFrameCaptureStateName(stats.state),
        capturePersistState == CapturePersistState::Saved ? "true" : "false",
        capturePersistStateName(capturePersistState), capturePersistStatus,
        static_cast<unsigned long>(capturePersistGeneration),
        static_cast<unsigned>(plan.channel),
        static_cast<unsigned>(wifiFrameCapture.currentChannel()),
        static_cast<unsigned long>(plan.durationMs),
        static_cast<unsigned>(plan.channelDwellMs),
        static_cast<unsigned>(plan.snapLength),
        static_cast<unsigned>(plan.maximumFrames),
        static_cast<unsigned long long>(stats.startedUs),
        static_cast<unsigned long long>(stats.endedUs),
        static_cast<unsigned long>(stats.framesReported),
        static_cast<unsigned long>(stats.framesAccepted),
        static_cast<unsigned long>(stats.framesDroppedCapacity),
        static_cast<unsigned long>(stats.framesDroppedInvalid),
        static_cast<unsigned long>(stats.payloadBytes),
        static_cast<long>(stats.driverError),
        pcapBytes == 0U ? "false" : "true",
        static_cast<unsigned>(pcapBytes),
        wifiFrameCapture.cleanupComplete() ? "true" : "false",
        static_cast<unsigned long>(appRuntime.activeResources()));
    reply.println(line);
}

struct StreamPcapSink final {
    Stream* stream = nullptr;
};

bool writePcapBytes(const std::uint8_t* data, std::size_t size,
                    void* context) {
    auto* sink = static_cast<StreamPcapSink*>(context);
    return sink != nullptr && sink->stream != nullptr &&
           sink->stream->write(data, size) == size;
}

void emitWifiFrameCapturePcap(Stream& reply) {
    const auto stats = wifiFrameCapture.stats();
    const std::size_t expected =
        leshy1::apps::capture::radiotapPcapSize(wifiFrameCapture.capture());
    if (stats.state != WifiFrameCaptureState::Complete || expected == 0U) {
        reply.println(
            "{\"schema\":\"leshy.capture.pcap.v1\",\"kind\":\"error\","
            "\"reason\":\"capture_not_complete\"}");
        return;
    }
    char line[320] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.capture.pcap.v1\",\"kind\":\"pcap_begin\","
        "\"bytes\":%u,\"frames\":%u,\"linktype\":127,"
        "\"timebase\":\"monotonic_us\",\"streaming\":true,"
        "\"payload_retained_by_firmware\":true,"
        "\"storage_written\":false}",
        static_cast<unsigned>(expected),
        static_cast<unsigned>(wifiFrameCapture.capture().size()));
    reply.println(line);
    reply.flush();
    StreamPcapSink sink{&reply};
    const PcapExportResult result =
        leshy1::apps::capture::writeRadiotapPcap(
            wifiFrameCapture.capture(), writePcapBytes, &sink);
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.capture.pcap.v1\",\"kind\":\"pcap_end\","
        "\"status\":\"%s\",\"bytes\":%u,\"frames\":%u,"
        "\"storage_written\":false}",
        result.valid ? "valid" : "stream_failed",
        static_cast<unsigned>(result.bytesWritten),
        static_cast<unsigned>(result.framesWritten));
    reply.println(line);
    reply.flush();
}

void emitSubGhzRawCaptureState(Stream& reply) {
    const auto& stats = subGhzRawCapture.stats();
    const auto& plan = subGhzRawCapture.plan();
    const bool noTransmit = cc1101SpectrumReport.txStrobes == 0U &&
        cc1101SpectrumReport.paTableWrites == 0U &&
        cc1101SpectrumReport.fifoWrites == 0U;
    char line[1024] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.capture.subghz_raw.v1\",\"kind\":\"state\","
        "\"state\":\"%s\",\"passive_only\":true,\"rx_only\":true,"
        "\"modulation\":\"ook_envelope\",\"frequency_khz\":%lu,"
        "\"threshold_dbm\":%d,\"wait_timeout_ms\":%lu,"
        "\"maximum_capture_ms\":%lu,"
        "\"debounce_us\":%u,\"end_gap_us\":%u,"
        "\"maximum_pulses\":%u,\"started_us\":%llu,"
        "\"signal_started_us\":%llu,\"ended_us\":%llu,"
        "\"samples\":%lu,\"invalid_samples\":%lu,"
        "\"short_transitions_rejected\":%lu,\"pulses\":%u,"
        "\"start_level\":%s,\"truncated\":%s,"
        "\"driver_error\":%ld,\"csv_available\":%s,"
        "\"application_tx_calls\":0,\"tx_strobes\":%lu,"
        "\"pa_table_writes\":%lu,\"fifo_writes\":%lu,"
        "\"physical_no_tx_verified\":%s,\"cleanup_complete\":%s,"
        "\"storage_written\":%s,\"persist_state\":\"%s\","
        "\"persist_status\":\"%s\",\"persist_generation\":%lu,"
        "\"lease_mask\":%lu}",
        leshy1::apps::capture::subGhzRawCaptureStateName(stats.state),
        static_cast<unsigned long>(plan.frequencyKHz),
        static_cast<int>(plan.thresholdDbm),
        static_cast<unsigned long>(plan.waitTimeoutMs),
        static_cast<unsigned long>(plan.maximumCaptureMs),
        static_cast<unsigned>(plan.debounceUs),
        static_cast<unsigned>(plan.endGapUs),
        static_cast<unsigned>(plan.maximumPulses),
        static_cast<unsigned long long>(stats.startedUs),
        static_cast<unsigned long long>(stats.signalStartedUs),
        static_cast<unsigned long long>(stats.endedUs),
        static_cast<unsigned long>(stats.samples),
        static_cast<unsigned long>(stats.invalidSamples),
        static_cast<unsigned long>(stats.shortTransitionsRejected),
        static_cast<unsigned>(subGhzRawCapture.pulseCount()),
        stats.startLevel ? "true" : "false",
        stats.truncated ? "true" : "false",
        static_cast<long>(stats.driverError),
        stats.state == SubGhzRawCaptureState::Complete ? "true" : "false",
        static_cast<unsigned long>(cc1101SpectrumReport.txStrobes),
        static_cast<unsigned long>(cc1101SpectrumReport.paTableWrites),
        static_cast<unsigned long>(cc1101SpectrumReport.fifoWrites),
        noTransmit && cc1101SpectrumReport.cleanupComplete
            ? "true" : "false",
        cc1101SpectrumReport.cleanupComplete ? "true" : "false",
        subGhzCapturePersistState == CapturePersistState::Saved
            ? "true" : "false",
        capturePersistStateName(subGhzCapturePersistState),
        subGhzCapturePersistStatus,
        static_cast<unsigned long>(subGhzCapturePersistGeneration),
        static_cast<unsigned long>(appRuntime.activeResources()));
    reply.println(line);
}

void emitSubGhzRawCaptureCsv(Stream& reply) {
    const auto& stats = subGhzRawCapture.stats();
    if (stats.state != SubGhzRawCaptureState::Complete ||
        subGhzRawCapture.pulseCount() == 0U) {
        reply.println(
            "{\"schema\":\"leshy.capture.subghz_raw.csv.v1\","
            "\"kind\":\"error\",\"reason\":\"capture_not_complete\"}");
        return;
    }
    char line[160] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.capture.subghz_raw.csv.v1\","
        "\"kind\":\"csv_begin\",\"pulses\":%u,"
        "\"frequency_khz\":%lu,\"modulation\":\"ook_envelope\","
        "\"streaming\":true}",
        static_cast<unsigned>(subGhzRawCapture.pulseCount()),
        static_cast<unsigned long>(subGhzRawCapture.plan().frequencyKHz));
    reply.println(line);
    reply.flush();

    std::size_t bytes = 0;
    const auto header = leshy1::apps::capture::formatSubGhzRawCsvHeader(
        line, sizeof(line));
    bool valid = header.valid &&
        reply.write(reinterpret_cast<const std::uint8_t*>(line),
                    header.bytes) == header.bytes;
    bytes += valid ? header.bytes : 0U;
    for (std::size_t index = 0;
         valid && index < subGhzRawCapture.pulseCount(); ++index) {
        const auto row = leshy1::apps::capture::formatSubGhzRawCsvRow(
            subGhzRawCapture, index, stats.startLevel, line, sizeof(line));
        valid = row.valid &&
            reply.write(reinterpret_cast<const std::uint8_t*>(line),
                        row.bytes) == row.bytes;
        bytes += valid ? row.bytes : 0U;
    }
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.capture.subghz_raw.csv.v1\","
        "\"kind\":\"csv_end\",\"status\":\"%s\",\"bytes\":%u,"
        "\"pulses\":%u}",
        valid ? "valid" : "stream_failed", static_cast<unsigned>(bytes),
        static_cast<unsigned>(subGhzRawCapture.pulseCount()));
    reply.println(line);
    reply.flush();
}

void emitInfraredRawCaptureState(Stream& reply) {
    const auto& stats = infraredCapture.stats();
    const auto& plan = infraredCapture.plan();
    const auto& decode = infraredCapture.decode();
    char line[1024] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.capture.infrared_raw.v1\",\"kind\":\"state\","
        "\"state\":\"%s\",\"passive_only\":true,\"rx_only\":true,"
        "\"gpio_rx\":%d,\"gpio_tx\":%d,\"tx_level\":\"low\","
        "\"application_tx_calls\":0,\"wait_timeout_ms\":%lu,"
        "\"maximum_capture_ms\":%lu,\"minimum_pulse_us\":%u,"
        "\"end_gap_us\":%u,\"maximum_sample_gap_us\":%u,"
        "\"maximum_pulses\":%u,\"started_us\":%llu,"
        "\"signal_started_us\":%llu,\"ended_us\":%llu,"
        "\"samples\":%lu,\"transitions\":%lu,"
        "\"invalid_samples\":%lu,\"short_pulses_rejected\":%lu,"
        "\"maximum_observed_sample_gap_us\":%lu,\"pulses\":%u,"
        "\"start_level\":%s,\"truncated\":%s,\"driver_error\":%ld,"
        "\"protocol\":\"%s\",\"raw_code\":%lu,\"address\":%u,"
        "\"command\":%u,\"decode_integrity_valid\":%s,"
        "\"csv_available\":%s,\"cleanup_complete\":%s,"
        "\"storage_written\":%s,\"persist_state\":\"%s\","
        "\"persist_status\":\"%s\",\"persist_generation\":%lu,"
        "\"lease_mask\":%lu}",
        leshy1::apps::capture::infraredCaptureStateName(stats.state),
        BoardProfile::kIrRxPin, BoardProfile::kIrTxPin,
        static_cast<unsigned long>(plan.waitTimeoutMs),
        static_cast<unsigned long>(plan.maximumCaptureMs),
        static_cast<unsigned>(plan.minimumPulseUs),
        static_cast<unsigned>(plan.endGapUs),
        static_cast<unsigned>(plan.maximumSampleGapUs),
        static_cast<unsigned>(plan.maximumPulses),
        static_cast<unsigned long long>(stats.startedUs),
        static_cast<unsigned long long>(stats.signalStartedUs),
        static_cast<unsigned long long>(stats.endedUs),
        static_cast<unsigned long>(stats.samples),
        static_cast<unsigned long>(infraredReceiverReport.transitions),
        static_cast<unsigned long>(stats.invalidSamples),
        static_cast<unsigned long>(stats.shortPulsesRejected),
        static_cast<unsigned long>(stats.maximumObservedSampleGapUs),
        static_cast<unsigned>(infraredCapture.pulseCount()),
        stats.startLevel ? "true" : "false",
        stats.truncated ? "true" : "false",
        static_cast<long>(stats.driverError),
        leshy1::domain::captures::infraredProtocolName(decode.protocol),
        static_cast<unsigned long>(decode.rawCode),
        static_cast<unsigned>(decode.address),
        static_cast<unsigned>(decode.command),
        decode.integrityValid ? "true" : "false",
        stats.state == InfraredCaptureState::Complete ? "true" : "false",
        infraredReceiverReport.cleanupComplete ? "true" : "false",
        infraredCapturePersistState == CapturePersistState::Saved
            ? "true" : "false",
        capturePersistStateName(infraredCapturePersistState),
        infraredCapturePersistStatus,
        static_cast<unsigned long>(infraredCapturePersistGeneration),
        static_cast<unsigned long>(appRuntime.activeResources()));
    reply.println(line);
}

void emitInfraredRawCaptureCsv(Stream& reply) {
    const auto& stats = infraredCapture.stats();
    if (stats.state != InfraredCaptureState::Complete ||
        infraredCapture.pulseCount() == 0U) {
        reply.println(
            "{\"schema\":\"leshy.capture.infrared_raw.csv.v1\","
            "\"kind\":\"error\",\"reason\":\"capture_not_complete\"}");
        return;
    }
    char line[192] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.capture.infrared_raw.csv.v1\","
        "\"kind\":\"csv_begin\",\"pulses\":%u,"
        "\"protocol\":\"%s\",\"streaming\":true}",
        static_cast<unsigned>(infraredCapture.pulseCount()),
        leshy1::domain::captures::infraredProtocolName(
            infraredCapture.decode().protocol));
    reply.println(line);
    reply.flush();

    std::size_t bytes = 0;
    const auto header = leshy1::apps::capture::formatInfraredCsvHeader(
        line, sizeof(line));
    bool valid = header.valid &&
        reply.write(reinterpret_cast<const std::uint8_t*>(line),
                    header.bytes) == header.bytes;
    bytes += valid ? header.bytes : 0U;
    for (std::size_t index = 0;
         valid && index < infraredCapture.pulseCount(); ++index) {
        const auto row = leshy1::apps::capture::formatInfraredCsvRow(
            infraredCapture, index, stats.startLevel, line, sizeof(line));
        valid = row.valid &&
            reply.write(reinterpret_cast<const std::uint8_t*>(line),
                        row.bytes) == row.bytes;
        bytes += valid ? row.bytes : 0U;
    }
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.capture.infrared_raw.csv.v1\","
        "\"kind\":\"csv_end\",\"status\":\"%s\",\"bytes\":%u,"
        "\"pulses\":%u}",
        valid ? "valid" : "stream_failed", static_cast<unsigned>(bytes),
        static_cast<unsigned>(infraredCapture.pulseCount()));
    reply.println(line);
    reply.flush();
}

void emitSurveyBrowser(Stream& reply) {
    const Observation* selected = surveyController.selected();
    const ObservationHistory history = surveyController.selectedHistory();
    char line[768] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.survey.browser.v1\",\"kind\":\"state\","
        "\"view\":\"%s\",\"filter\":\"%s\",\"draft_filter\":\"%s\","
        "\"filter_focused\":%s,\"total\":%u,\"visible\":%u,"
        "\"selection\":%u,\"selected\":%s,\"selected_radio\":\"%s\","
        "\"history_valid\":%s,\"history_samples\":%u,"
        "\"history_retained\":%u,\"history_min_rssi_dbm\":%d,"
        "\"history_max_rssi_dbm\":%d,\"history_latest_rssi_dbm\":%d,"
        "\"read_only_query\":true,\"radio_touched\":false,"
        "\"storage_touched\":false}",
        leshy1::apps::survey::surveyViewName(surveyController.view()),
        leshy1::apps::survey::surveyFilterName(surveyController.filter()),
        leshy1::apps::survey::surveyFilterName(surveyController.draftFilter()),
        surveyController.filterFocused() ? "true" : "false",
        static_cast<unsigned>(surveySession.size()),
        static_cast<unsigned>(surveyController.visibleSize()),
        static_cast<unsigned>(surveyController.selection()),
        selected == nullptr ? "false" : "true",
        selected == nullptr ? "none"
                            : (selected->radio == RadioKind::Ble ? "ble" : "wifi"),
        history.valid ? "true" : "false",
        static_cast<unsigned>(history.sampleCount),
        static_cast<unsigned>(history.retainedSamples),
        static_cast<int>(history.minimumRssiDbm),
        static_cast<int>(history.maximumRssiDbm),
        static_cast<int>(history.latestRssiDbm));
    reply.println(line);
}

bool startWifiNetworksProduct() {
    if (surveyWorkflow.state() != SurveyWorkflowState::Setup) {
        surveyPipeline.resetToSetup();
    }
    closeProductSurveyBackend();
    wifiNetworkCatalog.reset();
    wifiNetworkNavigationOrder.reset();
    wifiNetworkSelection = 0;
    wifiNetworkDetail = {};
    productSurveyRuntime = {};
    productSurveyRuntime.selected = true;
    productSurveyRuntime.workerReady = productSurveyWorkerReady;
    surveySourceController.rebuild(inventory, false,
                                   SurveySourceScope::WifiOnly);
    const SurveyWorkflowStatus configured =
        surveyWorkflow.configure(true, false);
    if (configured != SurveyWorkflowStatus::Ready) {
        productSurveyRuntime.status = "workflow_config_failed";
        lastRuntimeEvent = productSurveyRuntime.status;
        return false;
    }
    wifiProductView = WifiProductView::Networks;
    if (!startProductSurvey()) {
        wifiProductView = WifiProductView::Menu;
        return false;
    }
    lastRuntimeEvent = "wifi_networks_preparing";
    return true;
}

bool startBleDevicesProduct() {
    if (surveyWorkflow.state() != SurveyWorkflowState::Setup) {
        surveyPipeline.resetToSetup();
    }
    closeProductSurveyBackend();
    bleDeviceCatalog.reset();
    bleDeviceSelection = 0;
    bleDeviceDetail = {};
    productSurveyRuntime = {};
    productSurveyRuntime.selected = true;
    productSurveyRuntime.workerReady = productSurveyWorkerReady;
    surveySourceController.rebuild(inventory, false,
                                   SurveySourceScope::BleOnly);
    const SurveyWorkflowStatus configured =
        surveyWorkflow.configure(true, false);
    bleProductView = BleProductView::Devices;
    if (configured != SurveyWorkflowStatus::Ready) {
        productSurveyRuntime.status = "workflow_config_failed";
        lastRuntimeEvent = productSurveyRuntime.status;
        return true;
    }
    if (!startProductSurvey()) return true;
    lastRuntimeEvent = "ble_devices_preparing";
    return true;
}

bool startWifiDevicesProduct() {
    wifiFrameCapture.reset();
    wifiDeviceCatalog.reset();
    wifiDeviceNavigationOrder.reset();
    wifiDeviceSelection = 0;
    wifiDeviceDetail = {};
    std::uint64_t startedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    if (startedUs == 0U) startedUs = 1U;
    const bool started = wifiFrameCapture.beginDeviceMonitor(startedUs);
    wifiProductView = WifiProductView::Devices;
    nextWifiDeviceUiRefreshUs = startedUs + 250000ULL;
    lastRuntimeEvent = started ? "wifi_devices_listening"
                               : "wifi_devices_start_failed";
    return true;
}

bool stopWifiDevicesProduct() {
    std::uint64_t endedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    if (endedUs == 0U) endedUs = 1U;
    const bool cleanup = wifiFrameCapture.stop(endedUs);
    wifiProductView = WifiProductView::Menu;
    wifiProductSelection = 1;
    nextWifiDeviceUiRefreshUs = 0;
    lastRuntimeEvent = cleanup ? "wifi_menu" : "wifi_devices_cleanup_failed";
    return true;
}

void serviceWifiDevicesProduct() {
    const auto before = wifiFrameCapture.deviceMonitorStats();
    if (!before.active) return;
    std::uint64_t nowUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    if (nowUs == 0U) nowUs = 1U;
    wifiFrameCapture.service(nowUs);
    bool changed = false;
    const WifiDeviceRecord* selected = wifiDeviceAt(wifiDeviceSelection);
    const std::array<std::uint8_t, 6> selectionAnchor = selected == nullptr
        ? std::array<std::uint8_t, 6>{} : selected->address;
    const bool selectionAnchored = selected != nullptr;
    WifiDeviceObservation observation{};
    while (wifiFrameCapture.pollDevice(&observation)) {
        const std::size_t existingIndex =
            wifiDeviceCatalog.indexOfAddress(observation.address);
        if (wifiDeviceNavigationOrder.locked() &&
            existingIndex >= wifiDeviceCatalog.size()) {
            observation = {};
            continue;
        }
        if (!observation.locallyAdministered &&
            observation.wpsManufacturerLength == 0U) {
            const WifiDeviceRecord* existing =
                wifiDeviceCatalog.at(existingIndex);
            const bool needsVendor = existing == nullptr ||
                (existing->wpsManufacturerLength == 0U &&
                 existing->ouiVendorLength == 0U);
            if (needsVendor) {
                char vendor[WifiDeviceObservation::kWpsTextCapacity] = {};
                if (wifiOuiDatabase.lookup(observation.address.data(), vendor,
                                           sizeof(vendor))) {
                    std::snprintf(observation.ouiVendor.data(),
                                  observation.ouiVendor.size(), "%s", vendor);
                    observation.ouiVendorLength = static_cast<std::uint8_t>(
                        std::strlen(observation.ouiVendor.data()));
                }
            }
        }
        changed = wifiDeviceCatalog.upsert(observation) || changed;
        observation = {};
    }
    if (changed && selectionAnchored &&
        !wifiDeviceNavigationOrder.locked()) {
        const std::size_t anchored =
            wifiDeviceCatalog.indexOfAddress(selectionAnchor);
        wifiDeviceSelection = anchored < wifiDeviceCatalog.size()
            ? anchored : wifiDeviceCatalog.size() - 1U;
    }
    if (changed &&
        (wifiProductView == WifiProductView::DeviceDetail ||
         wifiProductView == WifiProductView::DeviceRadar)) {
        const std::size_t detailIndex =
            wifiDeviceCatalog.indexOfAddress(wifiDeviceDetail.address);
        const WifiDeviceRecord* current = wifiDeviceCatalog.at(detailIndex);
        if (current != nullptr) wifiDeviceDetail = *current;
    }
    const auto after = wifiFrameCapture.deviceMonitorStats();
    const bool terminal = before.active && !after.active;
    if (terminal) lastRuntimeEvent = "wifi_devices_failed";
    // At most four data-only refreshes per second. The facts page remains
    // stable; the explicit Radar page updates live without repainting chrome.
    if ((changed || terminal) && uiController.page() == 2 &&
        (wifiProductView == WifiProductView::Devices ||
         wifiProductView == WifiProductView::DeviceRadar) &&
        (terminal || nowUs >= nextWifiDeviceUiRefreshUs)) {
        nextWifiDeviceUiRefreshUs = nowUs + 250000ULL;
        renderInteractiveScreen(false);
    }
}

bool startWifiChannelsProduct() {
    wifiFrameCapture.reset();
    wifiChannelRenderedLoads.fill(0xffffU);
    wifiChannelRenderedBest = 0xffU;
    std::uint64_t startedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    if (startedUs == 0U) startedUs = 1U;
    const bool started = wifiFrameCapture.beginChannelMonitor(startedUs);
    wifiProductView = WifiProductView::Channels;
    lastRuntimeEvent = started ? "wifi_channels_measuring"
                               : "wifi_channels_start_failed";
    return true;
}

bool stopWifiChannelsProduct() {
    std::uint64_t endedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    if (endedUs == 0U) endedUs = 1U;
    const bool cleanup = wifiFrameCapture.stop(endedUs);
    wifiProductView = WifiProductView::Menu;
    wifiProductSelection = 2;
    lastRuntimeEvent = cleanup ? "wifi_menu" : "wifi_channels_cleanup_failed";
    return true;
}

void serviceWifiChannelsProduct() {
    const auto beforeStats = wifiFrameCapture.channelMonitorStats();
    if (!beforeStats.active) return;
    const auto before = wifiFrameCapture.channelLoadSnapshot();
    std::uint64_t nowUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    if (nowUs == 0U) nowUs = 1U;
    wifiFrameCapture.service(nowUs);
    const auto afterStats = wifiFrameCapture.channelMonitorStats();
    const auto after = wifiFrameCapture.channelLoadSnapshot();
    const bool terminal = beforeStats.active && !afterStats.active;
    if (terminal) lastRuntimeEvent = "wifi_channels_failed";
    if ((terminal || after.revision != before.revision) &&
        uiController.page() == 2 &&
        wifiProductView == WifiProductView::Channels) {
        renderInteractiveScreen(false);
    }
}

bool openWifiCaptureProduct() {
    wifiFrameCapture.reset();
    capturePersistState = CapturePersistState::Result;
    capturePersistStatus = "volatile";
    capturePersistGeneration = 0;
    wifiCaptureRenderedFrames = UINT32_MAX;
    wifiCaptureRenderedDrops = UINT32_MAX;
    wifiCaptureRenderedChannel = 0xffU;
    nextCaptureUiRefreshUs = 0;
    wifiProductView = WifiProductView::Capture;
    lastRuntimeEvent = "wifi_capture_setup";
    return true;
}

bool closeWifiCaptureProduct() {
    const auto state = wifiFrameCapture.stats().state;
    bool cleanup = true;
    if (state == WifiFrameCaptureState::Running) {
        cleanup = stopWifiFrameCapture();
    }
    wifiFrameCapture.reset();
    capturePersistState = CapturePersistState::Result;
    capturePersistStatus = "volatile";
    capturePersistGeneration = 0;
    wifiCaptureRenderedFrames = UINT32_MAX;
    wifiCaptureRenderedDrops = UINT32_MAX;
    wifiCaptureRenderedChannel = 0xffU;
    nextCaptureUiRefreshUs = 0;
    wifiProductView = WifiProductView::Menu;
    wifiProductSelection = 3;
    lastRuntimeEvent = cleanup ? "wifi_menu" : "wifi_capture_cleanup_failed";
    return true;
}

bool selectionCanRepaintInPlace(UiAction action) {
    if (action != UiAction::Up && action != UiAction::Down) return false;
    if (uiController.isRoot()) return true;
    if (uiController.page() == 2) {
        if (bleProductView == BleProductView::Devices) return true;
        if (wifiProductView == WifiProductView::Menu) return true;
        if (wifiProductView == WifiProductView::Networks &&
            surveyWorkflow.state() == SurveyWorkflowState::Running) {
            return true;
        }
        if (wifiProductView == WifiProductView::Devices) return true;
        if (rfSpectrumView == RfSpectrumView::Live) return false;
        if (rfSpectrumView == RfSpectrumView::SourceMenu ||
            rfSpectrumView == RfSpectrumView::SubGhzMenu ||
            rfSpectrumView == RfSpectrumView::CcBandMenu ||
            rfSpectrumView == RfSpectrumView::SubGhzCaptureBandMenu) return true;
        return surveyWorkflow.state() == SurveyWorkflowState::Setup ||
               (surveyWorkflow.state() == SurveyWorkflowState::Running &&
                (surveyController.view() == SurveyView::List ||
                 surveyController.view() == SurveyView::Filter));
    }
    if (uiController.page() == 3) {
        return libraryController.view() == LibraryView::SessionList;
    }
    if (uiController.page() == 4) {
        return captureView == CaptureView::SourceMenu;
    }
    if (uiController.page() == 5) return true;
    if (uiController.page() == kDevicePage) return true;
    return uiController.page() == 6 &&
           selfTestController.view() == SelfTestView::ModeMenu;
}

bool applyUiAction(UiAction action, bool render = true) {
    const bool incrementalCandidate = selectionCanRepaintInPlace(action);
    lastUiActionUsedIncrementalRender = false;
    const auto finish = [&](bool changed) {
        lastUiActionUsedIncrementalRender = changed && incrementalCandidate;
        if (changed && render) {
            renderInteractiveScreen(!lastUiActionUsedIncrementalRender);
        }
        return changed;
    };
    if (safetySupervisor.latched()) {
        bool changed = false;
        if (action == UiAction::Select || action == UiAction::Right) {
            if (safetySupervisor.clearPending()) {
                clearSafetyStopAndRestart();
            }
            changed = safetySupervisor.requestClear();
        } else if ((action == UiAction::Back || action == UiAction::Left) &&
                   safetySupervisor.clearPending()) {
            changed = safetySupervisor.cancelClear();
        }
        if (action != UiAction::Unknown) {
            uiController.recordHandledAction(action);
        }
        return finish(changed);
    }
    const AppMenuItem* selected = appCatalog.get(uiController.selection());
    const bool wasRoot = uiController.isRoot();
    if (!wasRoot && uiController.page() == 2) {
        bool handled = false;
        bool changed = false;
        if (bleProductView == BleProductView::DeviceDetail) {
            handled = true;
            if (action == UiAction::Back || action == UiAction::Left) {
                bleProductView = BleProductView::Devices;
                lastRuntimeEvent = "ble_devices";
                changed = true;
            }
        } else if (bleProductView == BleProductView::Devices) {
            handled = true;
            if (action == UiAction::Up && bleDeviceSelection > 0U) {
                --bleDeviceSelection;
                changed = true;
            } else if (action == UiAction::Down &&
                       bleDeviceSelection + 1U < bleDeviceCatalog.size()) {
                ++bleDeviceSelection;
                changed = true;
            } else if (action == UiAction::Select ||
                       action == UiAction::Right) {
                const Observation* device =
                    bleDeviceCatalog.at(bleDeviceSelection);
                if (device != nullptr) {
                    bleDeviceDetail = *device;
                    bleProductView = BleProductView::DeviceDetail;
                    lastRuntimeEvent = "ble_device_detail";
                    changed = true;
                }
            } else if (action == UiAction::Back ||
                       action == UiAction::Left) {
                const auto control = productSurveyControl();
                if (control == ProductSurveyWorkerControl::Starting ||
                    control == ProductSurveyWorkerControl::Running) {
                    changed = requestProductSurveyWorkerStop(true);
                } else {
                    bleProductView = BleProductView::None;
                    surveyPipeline.resetToSetup();
                    changed = uiController.apply(
                        action,
                        static_cast<std::uint8_t>(appCatalog.size()),
                        true, 2);
                    if (changed) appRuntime.stop();
                    lastRuntimeEvent = "ble_home";
                }
            }
        } else if (wifiProductView == WifiProductView::Menu) {
            if (action == UiAction::Up && wifiProductSelection > 0) {
                handled = true;
                --wifiProductSelection;
                changed = true;
            } else if (action == UiAction::Down &&
                       wifiProductSelection + 1U < kWifiProductTaskCount) {
                handled = true;
                ++wifiProductSelection;
                changed = true;
            } else if ((action == UiAction::Select ||
                        action == UiAction::Right) &&
                       wifiProductTaskReady(wifiProductSelection)) {
                handled = true;
                if (wifiProductSelection == 0) {
                    changed = startWifiNetworksProduct();
                } else if (wifiProductSelection == 1) {
                    changed = startWifiDevicesProduct();
                } else if (wifiProductSelection == 2) {
                    changed = startWifiChannelsProduct();
                } else if (wifiProductSelection == 3) {
                    changed = openWifiCaptureProduct();
                }
            } else if (action == UiAction::Select ||
                       action == UiAction::Right) {
                handled = true;
                lastRuntimeEvent = "wifi_task_not_ready";
            } else if (action == UiAction::Back || action == UiAction::Left) {
                handled = true;
                wifiProductView = WifiProductView::None;
                changed = uiController.apply(
                    action, static_cast<std::uint8_t>(appCatalog.size()),
                    true, 2);
                if (changed) appRuntime.stop();
                lastRuntimeEvent = "wifi_home";
            }
        } else if (rfSpectrumView == RfSpectrumView::SourceMenu) {
            handled = true;
            if (action == UiAction::Up && rfSpectrumSelection != 0) {
                rfSpectrumSelection = 0;
                changed = true;
            } else if (action == UiAction::Down && rfSpectrumSelection != 1) {
                rfSpectrumSelection = 1;
                changed = true;
            } else if ((action == UiAction::Select ||
                        action == UiAction::Right) &&
                       rfSpectrumSelection == 0) {
                changed = startNrf24Spectrum();
            } else if ((action == UiAction::Select ||
                        action == UiAction::Right) &&
                       rfSpectrumSelection == 1) {
                rfCcBandSelection =
                    leshy1::drivers::radio::Cc1101SpectrumBand::Band433;
                rfSpectrumView = RfSpectrumView::CcBandMenu;
                lastRuntimeEvent = "cc1101_spectrum_band_menu";
                changed = true;
            } else if (action == UiAction::Back || action == UiAction::Left) {
                rfSpectrumView = RfSpectrumView::None;
                lastRuntimeEvent = "survey_spectrum_plan";
                changed = true;
            }
        } else if (rfSpectrumView == RfSpectrumView::SubGhzMenu) {
            handled = true;
            if (action == UiAction::Up && subGhzModeSelection != 0) {
                subGhzModeSelection = 0;
                changed = true;
            } else if (action == UiAction::Down &&
                       subGhzModeSelection != 1) {
                subGhzModeSelection = 1;
                changed = true;
            } else if (action == UiAction::Select ||
                       action == UiAction::Right) {
                rfCcBandSelection =
                    leshy1::drivers::radio::Cc1101SpectrumBand::Band433;
                rfSpectrumView = subGhzModeSelection == 0
                    ? RfSpectrumView::CcBandMenu
                    : RfSpectrumView::SubGhzCaptureBandMenu;
                lastRuntimeEvent = subGhzModeSelection == 0
                    ? "cc1101_spectrum_band_menu"
                    : "subghz_raw_band_menu";
                changed = true;
            } else if (action == UiAction::Back ||
                       action == UiAction::Left) {
                rfSpectrumView = RfSpectrumView::None;
                changed = uiController.apply(
                    action, static_cast<std::uint8_t>(appCatalog.size()),
                    true, 2);
                if (changed) appRuntime.stop();
                lastRuntimeEvent = "subghz_home";
            }
        } else if (rfSpectrumView ==
                   RfSpectrumView::SubGhzCaptureBandMenu) {
            handled = true;
            std::uint8_t selection = ccBandSelectionIndex();
            if (action == UiAction::Up && selection != 0) {
                --selection;
                rfCcBandSelection = ccBandFromIndex(selection);
                changed = true;
            } else if (action == UiAction::Down && selection != 3) {
                ++selection;
                rfCcBandSelection = ccBandFromIndex(selection);
                changed = true;
            } else if (action == UiAction::Select ||
                       action == UiAction::Right) {
                changed = startSubGhzRawCapture(rfCcBandSelection);
            } else if (action == UiAction::Back ||
                       action == UiAction::Left) {
                rfSpectrumView = RfSpectrumView::SubGhzMenu;
                lastRuntimeEvent = "subghz_modes";
                changed = true;
            }
        } else if (rfSpectrumView == RfSpectrumView::SubGhzCaptureLive) {
            handled = true;
            if (subGhzRawCapture.stats().state ==
                    SubGhzRawCaptureState::Complete &&
                subGhzCapturePersistState == CapturePersistState::Result &&
                (action == UiAction::Select || action == UiAction::Right)) {
                changed = requestSubGhzRawCapturePersist();
            } else if (subGhzCapturePersistState ==
                           CapturePersistState::Saving) {
                changed = false;
            } else if (subGhzRawCapture.stats().state !=
                           SubGhzRawCaptureState::Waiting &&
                       subGhzRawCapture.stats().state !=
                           SubGhzRawCaptureState::Capturing &&
                       (action == UiAction::Select ||
                        action == UiAction::Right)) {
                changed = startSubGhzRawCapture(rfCcBandSelection);
            } else if (action == UiAction::Back || action == UiAction::Left) {
                changed = stopSubGhzRawCapture(true);
                subGhzRawCapture.reset();
                subGhzCapturePersistState = CapturePersistState::Result;
                subGhzCapturePersistStatus = "volatile";
                subGhzCapturePersistGeneration = 0;
            }
        } else if (rfSpectrumView == RfSpectrumView::CcBandMenu) {
            handled = true;
            std::uint8_t selection = ccBandSelectionIndex();
            if (action == UiAction::Up && selection != 0) {
                --selection;
                rfCcBandSelection = ccBandFromIndex(selection);
                changed = true;
            } else if (action == UiAction::Down && selection != 3) {
                ++selection;
                rfCcBandSelection = ccBandFromIndex(selection);
                changed = true;
            } else if (action == UiAction::Select ||
                       action == UiAction::Right) {
                changed = startCc1101Spectrum(rfCcBandSelection);
            } else if (action == UiAction::Back || action == UiAction::Left) {
                const bool direct = std::strcmp(appRuntime.activeApp(),
                                                "subghz") == 0;
                if (direct) {
                    rfSpectrumView = RfSpectrumView::SubGhzMenu;
                    lastRuntimeEvent = "subghz_modes";
                    changed = true;
                } else {
                    rfSpectrumView = RfSpectrumView::SourceMenu;
                    lastRuntimeEvent = "spectrum_source_menu";
                    changed = true;
                }
            }
        } else if (rfSpectrumView == RfSpectrumView::Live) {
            handled = true;
            if (action == UiAction::Back || action == UiAction::Left) {
                const bool directNrf =
                    rfSpectrumKind == RfSpectrumKind::Nrf24 &&
                    std::strcmp(appRuntime.activeApp(), "spectrum24") == 0;
                changed = stopCurrentSpectrum(!directNrf);
                if (changed && directNrf) {
                    changed = uiController.apply(
                        action, static_cast<std::uint8_t>(appCatalog.size()),
                        true, 2);
                    if (changed) appRuntime.stop();
                }
            } else if (action == UiAction::Up || action == UiAction::Down) {
                const bool fault = rfSpectrumKind == RfSpectrumKind::Cc1101
                    ? cc1101SpectrumController.state() ==
                          Cc1101SpectrumViewState::Fault
                    : nrf24SpectrumController.state() ==
                          Nrf24SpectrumViewState::Fault;
                changed = !fault &&
                    (action == UiAction::Up
                         ? spectrumViewport.previousMode()
                         : spectrumViewport.nextMode());
                if (changed) {
                    if (spectrumViewport.mode() ==
                        SpectrumDisplayMode::Waterfall) {
                        const std::size_t bins = activeSpectrumBins();
                        spectrumViewport.reset(bins);
                        spectrumViewport.setMode(
                            SpectrumDisplayMode::Waterfall);
                        resetSpectrumWaterfallTiming();
                        armSpectrumWaterfallForCurrentReceiver();
                    }
                    nextSpectrumUiRefreshUs = 0;
                    lastRuntimeEvent = spectrumViewport.mode() ==
                        SpectrumDisplayMode::Waterfall
                            ? "spectrum_waterfall_view"
                            : "spectrum_bar_view";
                }
            } else if (rfSpectrumKind == RfSpectrumKind::Cc1101) {
                if ((action == UiAction::Select ||
                     action == UiAction::Right) &&
                    cc1101SpectrumController.togglePause()) {
                    changed = true;
                    if (cc1101SpectrumController.state() ==
                        Cc1101SpectrumViewState::Paused) {
                        if (!boardCc1101Spectrum.idle()) {
                            boardCc1101Spectrum.end();
                            cc1101SpectrumController.fail();
                            lastRuntimeEvent =
                                "cc1101_spectrum_pause_failed";
                        } else {
                            lastRuntimeEvent = "cc1101_spectrum_paused";
                        }
                    } else {
                        lastRuntimeEvent = "cc1101_spectrum_running";
                    }
                }
            } else if ((action == UiAction::Select ||
                        action == UiAction::Right) &&
                       nrf24SpectrumController.toggleMetric()) {
                const SpectrumDisplayMode displayMode =
                    spectrumViewport.mode();
                changed = spectrumViewport.reset(
                    Nrf24SpectrumController::kChannelCount);
                if (changed && displayMode ==
                        SpectrumDisplayMode::Waterfall) {
                    changed = spectrumViewport.nextMode();
                }
                resetSpectrumWaterfallTiming();
                armSpectrumWaterfallForCurrentReceiver();
                nextSpectrumUiRefreshUs = 0;
                lastRuntimeEvent = nrf24SpectrumController.metric() ==
                    Nrf24SpectrumMetric::Traffic
                        ? "nrf24_spectrum_traffic"
                        : "nrf24_spectrum_signal";
            }
        } else if (wifiProductView == WifiProductView::Networks &&
                   surveyWorkflow.state() != SurveyWorkflowState::Running &&
                   productSurveyControl() == ProductSurveyWorkerControl::Idle &&
                   (action == UiAction::Back || action == UiAction::Left)) {
            handled = true;
            closeProductSurveyBackend();
            surveyPipeline.resetToSetup();
            wifiProductView = WifiProductView::Menu;
            wifiProductSelection = 0;
            lastRuntimeEvent = "wifi_menu";
            changed = true;
        } else if (wifiProductView == WifiProductView::NetworkDetail) {
            handled = true;
            if (action == UiAction::Back || action == UiAction::Left) {
                wifiProductView = WifiProductView::Networks;
                lastRuntimeEvent = "wifi_networks";
                changed = true;
            }
        } else if (wifiProductView == WifiProductView::DeviceDetail) {
            handled = true;
            if (action == UiAction::Back || action == UiAction::Left) {
                wifiProductView = WifiProductView::Devices;
                lastRuntimeEvent = "wifi_devices";
                changed = true;
            } else if (action == UiAction::Select ||
                       action == UiAction::Right) {
                std::uint64_t nowUs =
                    static_cast<std::uint64_t>(esp_timer_get_time());
                if (nowUs == 0U) nowUs = 1U;
                if (wifiFrameCapture.lockDeviceChannel(
                        wifiDeviceDetail.channel, nowUs)) {
                    wifiProductView = WifiProductView::DeviceRadar;
                    nextWifiDeviceUiRefreshUs = nowUs;
                    lastRuntimeEvent = "wifi_device_radar";
                    changed = true;
                } else {
                    lastRuntimeEvent = "wifi_device_radar_unavailable";
                }
            }
        } else if (wifiProductView == WifiProductView::DeviceRadar) {
            handled = true;
            if (action == UiAction::Back || action == UiAction::Left) {
                std::uint64_t nowUs =
                    static_cast<std::uint64_t>(esp_timer_get_time());
                if (nowUs == 0U) nowUs = 1U;
                wifiFrameCapture.unlockDeviceChannel(nowUs);
                wifiProductView = WifiProductView::DeviceDetail;
                lastRuntimeEvent = "wifi_device_detail";
                changed = true;
            }
        } else if (wifiProductView == WifiProductView::Devices) {
            handled = true;
            if (action == UiAction::Up || action == UiAction::Down ||
                action == UiAction::Select || action == UiAction::Right) {
                wifiDeviceNavigationOrder.lock(wifiDeviceCatalog);
            }
            if (action == UiAction::Up && wifiDeviceSelection > 0U) {
                --wifiDeviceSelection;
                changed = true;
            } else if (action == UiAction::Down &&
                       wifiDeviceSelection + 1U < wifiDeviceVisibleSize()) {
                ++wifiDeviceSelection;
                changed = true;
            } else if (action == UiAction::Select ||
                       action == UiAction::Right) {
                const WifiDeviceRecord* device =
                    wifiDeviceAt(wifiDeviceSelection);
                if (device != nullptr) {
                    wifiDeviceDetail = *device;
                    wifiProductView = WifiProductView::DeviceDetail;
                    lastRuntimeEvent = "wifi_device_detail";
                    changed = true;
                }
            } else if (action == UiAction::Back ||
                       action == UiAction::Left) {
                changed = stopWifiDevicesProduct();
            }
        } else if (wifiProductView == WifiProductView::Channels) {
            handled = true;
            if (action == UiAction::Back || action == UiAction::Left) {
                changed = stopWifiChannelsProduct();
            }
        } else if (wifiProductView == WifiProductView::Capture) {
            handled = true;
            const auto state = wifiFrameCapture.stats().state;
            if (state == WifiFrameCaptureState::Idle &&
                (action == UiAction::Select || action == UiAction::Right)) {
                changed = startWifiFrameCapture();
            } else if (state == WifiFrameCaptureState::Running &&
                       (action == UiAction::Select ||
                        action == UiAction::Right)) {
                changed = stopWifiFrameCapture();
            } else if (state == WifiFrameCaptureState::Complete &&
                       capturePersistState == CapturePersistState::Result &&
                       (action == UiAction::Select ||
                        action == UiAction::Right)) {
                capturePersistState = CapturePersistState::Confirm;
                capturePersistStatus = "awaiting_confirmation";
                lastRuntimeEvent = "capture_store_confirm";
                changed = true;
            } else if (state == WifiFrameCaptureState::Complete &&
                       capturePersistState == CapturePersistState::Confirm &&
                       (action == UiAction::Select ||
                        action == UiAction::Right)) {
                changed = requestWifiFrameCapturePersist();
            } else if (state == WifiFrameCaptureState::Complete &&
                       capturePersistState == CapturePersistState::Confirm &&
                       (action == UiAction::Back ||
                        action == UiAction::Left)) {
                capturePersistState = CapturePersistState::Result;
                capturePersistStatus = "volatile";
                lastRuntimeEvent = "capture_store_cancelled";
                changed = true;
            } else if (capturePersistState == CapturePersistState::Saving) {
                changed = false;
            } else if (action == UiAction::Back ||
                       action == UiAction::Left) {
                changed = closeWifiCaptureProduct();
            }
        } else if (wifiProductView == WifiProductView::Networks &&
                   surveyWorkflow.state() == SurveyWorkflowState::Running) {
            handled = true;
            if (action == UiAction::Up || action == UiAction::Down ||
                action == UiAction::Select || action == UiAction::Right) {
                wifiNetworkNavigationOrder.lock(wifiNetworkCatalog);
            }
            if (action == UiAction::Up && wifiNetworkSelection > 0) {
                --wifiNetworkSelection;
                changed = true;
            } else if (action == UiAction::Down &&
                       wifiNetworkSelection + 1U <
                           wifiNetworkVisibleSize()) {
                ++wifiNetworkSelection;
                changed = true;
            } else if (action == UiAction::Select ||
                       action == UiAction::Right) {
                const Observation* observation = wifiNetworkAt(
                    wifiNetworkSelection);
                if (observation != nullptr) {
                    wifiNetworkDetail = *observation;
                    wifiProductView = WifiProductView::NetworkDetail;
                    lastRuntimeEvent = "wifi_network_detail";
                    changed = true;
                }
            } else if (action == UiAction::Back ||
                       action == UiAction::Left) {
                changed = requestProductSurveyWorkerStop(true);
            }
        } else if (surveyWorkflow.state() == SurveyWorkflowState::Setup &&
            productSurveySourceUnavailableVisible() &&
            (action == UiAction::Select || action == UiAction::Right ||
             action == UiAction::Up || action == UiAction::Down)) {
            handled = true;
            lastRuntimeEvent = "source_unavailable_waiting_back";
        } else if (surveyWorkflow.state() == SurveyWorkflowState::Setup &&
                   surveySourceController.view() ==
                       SurveySetupView::Sources) {
            if (action == UiAction::Up) {
                handled = true;
                changed = surveySourceController.previous();
            } else if (action == UiAction::Down) {
                handled = true;
                changed = surveySourceController.next();
            } else if (action == UiAction::Select ||
                       action == UiAction::Right) {
                handled = true;
                const SurveySetupActivation activation =
                    surveySourceController.activate();
                changed = activation ==
                    SurveySetupActivation::SourceChanged;
                lastRuntimeEvent = leshy1::apps::survey::
                    surveySetupActivationName(activation);
            } else if (action == UiAction::Back ||
                       action == UiAction::Left) {
                handled = true;
                changed = surveySourceController.back();
                if (changed) lastRuntimeEvent = "survey_source_plan";
            }
        } else if (surveyWorkflow.state() == SurveyWorkflowState::Setup &&
                   (action == UiAction::Up || action == UiAction::Down)) {
            handled = true;
            changed = action == UiAction::Up
                ? surveySourceController.previous()
                : surveySourceController.next();
        } else if (surveyWorkflow.state() == SurveyWorkflowState::Setup &&
                   (action == UiAction::Select ||
                    action == UiAction::Right)) {
            handled = true;
            const SurveySetupActivation activation =
                surveySourceController.activate();
            lastRuntimeEvent = leshy1::apps::survey::
                surveySetupActivationName(activation);
            if (activation == SurveySetupActivation::OpenedSources) {
                changed = true;
            } else if (activation ==
                       SurveySetupActivation::OpenedSpectrum) {
                const bool available = BoardProfile::kRfShieldDeclared &&
                    !BoardProfile::kGpsDeclared &&
                    !BoardProfile::kPn532Declared;
                if (available) {
                    rfSpectrumView = RfSpectrumView::SourceMenu;
                    rfSpectrumSelection = 0;
                    changed = true;
                }
            } else if (activation ==
                       SurveySetupActivation::StartRequested) {
                if (productSurveyRuntime.selected) {
                    if (productSurveyControl() ==
                        ProductSurveyWorkerControl::Idle) {
                        changed = startProductSurvey();
                    }
                } else {
                    std::uint64_t startedUs =
                        static_cast<std::uint64_t>(esp_timer_get_time());
                    if (startedUs == 0) startedUs = 1;
                    const SurveyPipelineStatus started = surveyPipeline.start(
                        "product-wifi-preview", startedUs);
                    changed = started == SurveyPipelineStatus::Started &&
                              publishGoldenObservations(surveyPipeline);
                    lastRuntimeEvent =
                        leshy1::apps::survey::surveyPipelineStatusName(
                            changed ? surveyPipeline.lastStatus() : started);
                }
            }
        } else if (surveyWorkflow.state() == SurveyWorkflowState::Setup &&
                   (action == UiAction::Back || action == UiAction::Left)) {
            if (productSurveyRuntime.selected &&
                productSurveyControl() != ProductSurveyWorkerControl::Idle) {
                handled = true;
                changed = requestProductSurveyWorkerStop(true);
            } else {
                surveyPipeline.cancel();
                if (productSurveyRuntime.selected) {
                    const bool cleanup = closeProductSurveyBackend();
                    productSurveyRuntime.status = cleanup ? "cancelled"
                                                           : "cleanup_failed";
                }
                lastRuntimeEvent =
                    leshy1::apps::survey::surveyPipelineStatusName(
                        surveyPipeline.lastStatus());
            }
        } else if (surveyWorkflow.state() == SurveyWorkflowState::Running &&
                   surveyController.view() == SurveyView::Filter) {
            handled = true;
            if (action == UiAction::Up) {
                changed = surveyController.previous();
            } else if (action == UiAction::Down) {
                changed = surveyController.next();
            } else if (action == UiAction::Select ||
                       action == UiAction::Right) {
                changed = surveyController.activateFilter();
                if (changed) lastRuntimeEvent = "survey_filter_applied";
            } else if (action == UiAction::Back ||
                       action == UiAction::Left) {
                changed = surveyController.back();
                if (changed) lastRuntimeEvent = "survey_filter_cancelled";
            } else {
                handled = false;
            }
        } else if (surveyWorkflow.state() == SurveyWorkflowState::Running &&
                   surveyController.view() == SurveyView::Detail) {
            if (action == UiAction::Back || action == UiAction::Left) {
                handled = true;
                changed = surveyController.back();
            } else if (action == UiAction::Select ||
                       action == UiAction::Right) {
                handled = true;
                if (productSurveyRuntime.selected) {
                    changed =
                        productSurveyControl() ==
                                ProductSurveyWorkerControl::Paused
                            ? commitPausedProductSurvey()
                            : requestProductSurveyWorkerStop(false);
                } else {
                    const SurveyPipelineStatus status =
                        surveyPipeline.stopAndCommit(
                            static_cast<std::uint64_t>(esp_timer_get_time()));
                    changed = status == SurveyPipelineStatus::Committed;
                    lastRuntimeEvent =
                        leshy1::apps::survey::surveyPipelineStatusName(status);
                }
            }
        } else if (surveyWorkflow.state() == SurveyWorkflowState::Running &&
                   surveyController.view() == SurveyView::List) {
            if (action == UiAction::Up) {
                handled = true;
                changed = surveyController.previous();
                if (changed && surveyController.filterFocused() &&
                    productSurveyRuntime.selected &&
                    productSurveyControl() ==
                        ProductSurveyWorkerControl::Running) {
                    changed = requestProductSurveyWorkerPause() || changed;
                }
            } else if (action == UiAction::Down) {
                handled = true;
                changed = surveyController.next();
            } else if (action == UiAction::Select ||
                       action == UiAction::Right) {
                handled = true;
                changed = surveyController.openSelected();
            } else if ((action == UiAction::Back || action == UiAction::Left) &&
                       surveyWorkflow.state() == SurveyWorkflowState::Running) {
                if (productSurveyRuntime.selected) {
                    handled = true;
                    if (productSurveyControl() ==
                        ProductSurveyWorkerControl::Paused) {
                        releaseProductSurveyAfterTerminal("cancelled", true);
                        changed = true;
                    } else {
                        changed = requestProductSurveyWorkerStop(true);
                    }
                } else {
                    surveyPipeline.cancel();
                    lastRuntimeEvent = "survey_cancelled";
                }
            }
        }
        if (handled) {
            uiController.recordHandledAction(action);
            return finish(changed);
        }
    }
    if (!wasRoot && uiController.page() == 3) {
        bool handled = false;
        bool changed = false;
        if (libraryController.view() == LibraryView::ExportReady &&
            (action == UiAction::Back || action == UiAction::Left)) {
            handled = true;
            changed = libraryController.back();
        } else if (libraryController.view() == LibraryView::SessionDetail &&
            (action == UiAction::Back || action == UiAction::Left)) {
            handled = true;
            changed = libraryController.back();
        } else if (libraryController.view() == LibraryView::SessionDetail &&
                   (action == UiAction::Select ||
                    action == UiAction::Right)) {
            handled = true;
            changed = libraryController.requestExport();
        } else if (libraryController.view() == LibraryView::SessionList) {
            if (action == UiAction::Up) {
                handled = true;
                changed = libraryController.previous();
            } else if (action == UiAction::Down) {
                handled = true;
                changed = libraryController.next();
            } else if (action == UiAction::Select || action == UiAction::Right) {
                handled = true;
                changed = libraryController.openSelected();
            }
        }
        if (handled) {
            uiController.recordHandledAction(action);
            return finish(changed);
        }
    }
    if (!wasRoot && uiController.page() == 4) {
        if (captureView == CaptureView::SourceMenu) {
            bool handled = false;
            bool changed = false;
            if (action == UiAction::Up && captureSourceSelection != 0) {
                captureSourceSelection = 0;
                handled = changed = true;
            } else if (action == UiAction::Down &&
                       captureSourceSelection != 1) {
                captureSourceSelection = 1;
                handled = changed = true;
            } else if ((action == UiAction::Select ||
                        action == UiAction::Right) &&
                       (captureSourceSelection == 0 ||
                        BoardProfile::kIrDeclared)) {
                captureView = captureSourceSelection == 0
                    ? CaptureView::Wifi : CaptureView::Infrared;
                lastRuntimeEvent = captureSourceSelection == 0
                    ? "capture_wifi_setup" : "capture_infrared_setup";
                handled = changed = true;
            }
            if (handled) {
                uiController.recordHandledAction(action);
                return finish(changed);
            }
        } else if (captureView == CaptureView::Infrared) {
            const auto state = infraredCapture.stats().state;
            if (state == InfraredCaptureState::Idle &&
                (action == UiAction::Select || action == UiAction::Right)) {
                uiController.recordHandledAction(action);
                return finish(startInfraredCapture());
            }
            if (state == InfraredCaptureState::Complete &&
                infraredCapturePersistState == CapturePersistState::Result &&
                (action == UiAction::Select || action == UiAction::Right)) {
                uiController.recordHandledAction(action);
                return finish(requestInfraredRawCapturePersist());
            }
            if (infraredCapturePersistState == CapturePersistState::Saving) {
                uiController.recordHandledAction(action);
                return finish(false);
            }
            if (state == InfraredCaptureState::Complete &&
                infraredCapturePersistState != CapturePersistState::Result &&
                (action == UiAction::Select || action == UiAction::Right)) {
                uiController.recordHandledAction(action);
                return finish(startInfraredCapture());
            }
            if (state != InfraredCaptureState::Waiting &&
                state != InfraredCaptureState::Capturing &&
                state != InfraredCaptureState::Complete &&
                (action == UiAction::Select || action == UiAction::Right)) {
                uiController.recordHandledAction(action);
                return finish(startInfraredCapture());
            }
            if (action == UiAction::Back || action == UiAction::Left) {
                if (state == InfraredCaptureState::Waiting ||
                    state == InfraredCaptureState::Capturing) {
                    stopInfraredCapture();
                }
                infraredCapture.reset();
                infraredCapturePersistState = CapturePersistState::Result;
                infraredCapturePersistStatus = "volatile";
                infraredCapturePersistGeneration = 0;
                captureView = CaptureView::SourceMenu;
                lastRuntimeEvent = "capture_source_menu";
                uiController.recordHandledAction(action);
                return finish(true);
            }
        } else {
        const auto state = wifiFrameCapture.stats().state;
        if (state == WifiFrameCaptureState::Idle &&
            (action == UiAction::Select || action == UiAction::Right)) {
            uiController.recordHandledAction(action);
            return finish(startWifiFrameCapture());
        }
        if (state == WifiFrameCaptureState::Running &&
            (action == UiAction::Select || action == UiAction::Right)) {
            uiController.recordHandledAction(action);
            return finish(stopWifiFrameCapture());
        }
        if (state == WifiFrameCaptureState::Complete &&
            capturePersistState == CapturePersistState::Result &&
            (action == UiAction::Select || action == UiAction::Right)) {
            capturePersistState = CapturePersistState::Confirm;
            capturePersistStatus = "awaiting_confirmation";
            lastRuntimeEvent = "capture_store_confirm";
            uiController.recordHandledAction(action);
            return finish(true);
        }
        if (state == WifiFrameCaptureState::Complete &&
            capturePersistState == CapturePersistState::Confirm &&
            (action == UiAction::Select || action == UiAction::Right)) {
            uiController.recordHandledAction(action);
            return finish(requestWifiFrameCapturePersist());
        }
        if (state == WifiFrameCaptureState::Complete &&
            capturePersistState == CapturePersistState::Confirm &&
            (action == UiAction::Back || action == UiAction::Left)) {
            capturePersistState = CapturePersistState::Result;
            capturePersistStatus = "volatile";
            lastRuntimeEvent = "capture_store_cancelled";
            uiController.recordHandledAction(action);
            return finish(true);
        }
        if (state == WifiFrameCaptureState::Complete &&
            capturePersistState == CapturePersistState::Saving) {
            uiController.recordHandledAction(action);
            return finish(false);
        }
        if (action == UiAction::Back || action == UiAction::Left) {
            if (state == WifiFrameCaptureState::Running) {
                stopWifiFrameCapture();
            }
            wifiFrameCapture.reset();
            capturePersistState = CapturePersistState::Result;
            capturePersistStatus = "volatile";
            capturePersistGeneration = 0;
            nextCaptureUiRefreshUs = 0;
            captureView = CaptureView::SourceMenu;
            lastRuntimeEvent = "capture_source_menu";
            uiController.recordHandledAction(action);
            return finish(true);
        }
        }
    }
    if (!wasRoot && uiController.page() == kDevicePage) {
        bool handled = false;
        bool changed = false;
        if (action == UiAction::Up && deviceSelection > 0) {
            handled = true;
            --deviceSelection;
            changed = true;
        } else if (action == UiAction::Down &&
                   deviceSelection + 1U < kDeviceItemCount) {
            handled = true;
            ++deviceSelection;
            changed = true;
        } else if (action == UiAction::Select || action == UiAction::Right) {
            handled = true;
            constexpr std::uint8_t pages[kDeviceItemCount] = {
                5, 6, 1, kAboutPage,
            };
            changed = uiController.openChild(pages[deviceSelection]);
            if (changed && deviceSelection == 0) languageController.enter();
            lastRuntimeEvent = changed ? "device_item_opened"
                                       : "device_item_rejected";
        }
        if (handled) {
            if (action == UiAction::Up || action == UiAction::Down) {
                uiController.recordHandledAction(action);
            }
            return finish(changed);
        }
    }
    if (!wasRoot && uiController.page() == 5) {
        bool handled = false;
        bool changed = false;
        if (action == UiAction::Up) {
            handled = true;
            changed = languageController.previous();
        } else if (action == UiAction::Down) {
            handled = true;
            changed = languageController.next();
        } else if (action == UiAction::Select || action == UiAction::Right) {
            handled = true;
            const UiLanguage requested = languageController.selected();
            const bool persisted = saveUiLanguage(requested);
            changed = persisted && languageController.apply();
            lastRuntimeEvent = persisted ? "language_persisted"
                                         : "language_persist_failed";
        }
        if (handled) {
            uiController.recordHandledAction(action);
            return finish(changed);
        }
    }
    if (!wasRoot && uiController.page() == 6) {
        bool handled = false;
        bool changed = false;
        if (selfTestController.view() == SelfTestView::ModeMenu &&
            action == UiAction::Up) {
            handled = true;
            changed = selfTestController.previousMode();
        } else if (selfTestController.view() == SelfTestView::ModeMenu &&
                   action == UiAction::Down) {
            handled = true;
            changed = selfTestController.nextMode();
        } else if (action == UiAction::Select || action == UiAction::Right) {
            handled = true;
            const std::uint64_t startedUs =
                static_cast<std::uint64_t>(esp_timer_get_time());
            const bool completesFullPlan =
                selfTestController.view() == SelfTestView::VisualCheck &&
                selfTestController.visualState() + 1U >=
                    SelfTestController::kVisualStateCount;
            if (completesFullPlan) runShieldReceiverSelfTestProbe();
            changed = selfTestController.activate(snapshotSelfTestFacts(),
                                                   startedUs);
            if (changed &&
                selfTestController.view() == SelfTestView::ActiveChecks) {
                fullGuidedRfState = {};
                fullGuidedArtifactState = {};
                fullGuidedNrf24Report = {};
                fullGuidedCc1101Report = {};
                fullGuidedRfStartAfterUs = startedUs + 500000ULL;
                lastRuntimeEvent = "self_test_active_rf_pending";
            }
            if (selfTestController.runAwaitingFinish() &&
                selfTestController.view() == SelfTestView::Result) {
                selfTestController.finishRun(
                    static_cast<std::uint64_t>(esp_timer_get_time()));
                lastRuntimeEvent = leshy1::apps::self_test::
                    selfTestResultStatusName(selfTestController.report().status);
            } else if (selfTestController.view() == SelfTestView::VisualCheck) {
                lastRuntimeEvent = "self_test_visual_check";
            } else if (selfTestController.view() ==
                       SelfTestView::ActiveChecks) {
                lastRuntimeEvent = "self_test_active_rf_pending";
            } else if (changed) {
                lastRuntimeEvent = "self_test_preflight";
            }
        } else if (action == UiAction::Back || action == UiAction::Left) {
            bool cleanupReady = true;
            if (selfTestController.view() == SelfTestView::ActiveChecks) {
                cleanupReady = cancelFullGuidedRfChecks();
            }
            changed = cleanupReady && selfTestController.back();
            handled = changed;
            if (changed) {
                lastRuntimeEvent = "self_test_modes";
            } else if (!cleanupReady) {
                handled = true;
                lastRuntimeEvent = "self_test_cancel_cleanup_failed";
            }
        }
        if (handled) {
            uiController.recordHandledAction(action);
            return finish(changed);
        }
    }
    const bool wantsLaunch = wasRoot && (action == UiAction::Select || action == UiAction::Right);
    bool openable = selected != nullptr && selected->enabled;
    LaunchStatus launchStatus = LaunchStatus::InvalidDescriptor;
    if (wantsLaunch) {
        launchStatus = selected == nullptr
                           ? LaunchStatus::InvalidDescriptor
                           : appRuntime.launch(selected->id, selected->enabled, selected->resources);
        lastRuntimeEvent = leshy1::kernel::runtime::launchStatusName(launchStatus);
        openable = launchStatus == LaunchStatus::Started;
        if (openable && selected != nullptr &&
            std::strcmp(selected->id, "language") == 0) {
            languageController.enter();
        }
        if (openable && selected != nullptr &&
            std::strcmp(selected->id, "device") == 0) {
            deviceSelection = 0;
        }
        if (openable && selected != nullptr &&
            std::strcmp(selected->id, "capture") == 0) {
            captureView = CaptureView::SourceMenu;
            captureSourceSelection = 0;
            wifiFrameCapture.reset();
            capturePersistState = CapturePersistState::Result;
            capturePersistStatus = "volatile";
            capturePersistGeneration = 0;
            infraredCapture.reset();
            infraredReceiverReport = {};
            infraredCapturePersistState = CapturePersistState::Result;
            infraredCapturePersistStatus = "volatile";
            infraredCapturePersistGeneration = 0;
            nextCaptureUiRefreshUs = 0;
        }
        const bool surveyApp = selected != nullptr &&
            (std::strcmp(selected->id, "wifi") == 0 ||
             std::strcmp(selected->id, "ble") == 0);
        const bool spectrumApp = selected != nullptr &&
            (std::strcmp(selected->id, "spectrum24") == 0 ||
             std::strcmp(selected->id, "subghz") == 0);
        if (openable && selected != nullptr && (surveyApp || spectrumApp)) {
            if (rfSpectrumView != RfSpectrumView::None ||
                boardNrf24Spectrum.active() ||
                boardCc1101Spectrum.active()) {
                stopCurrentSpectrum(false);
            } else {
                nrf24SpectrumController.reset();
                nrf24SpectrumReport = {};
                cc1101SpectrumController.reset();
                cc1101SpectrumReport = {};
            }
            rfSpectrumKind = RfSpectrumKind::Nrf24;
            rfSpectrumSelection = 0;
            subGhzModeSelection = 0;
            rfCcBandSelection =
                leshy1::drivers::radio::Cc1101SpectrumBand::Band433;
            nextSpectrumUiRefreshUs = 0;
            if (surveyApp) {
                const bool wifiApp = std::strcmp(selected->id, "wifi") == 0;
                if (wifiApp) {
                    wifiFrameCapture.reset();
                    wifiDeviceCatalog.reset();
                    wifiDeviceNavigationOrder.reset();
                    wifiDeviceSelection = 0;
                    wifiDeviceDetail = {};
                    nextWifiDeviceUiRefreshUs = 0;
                }
                wifiProductView = wifiApp ? WifiProductView::Menu
                                          : WifiProductView::None;
                wifiProductSelection = 0;
                if (!wifiApp) {
                    bleProductView = BleProductView::None;
                    startBleDevicesProduct();
                } else {
                    bleProductView = BleProductView::None;
                }
            } else if (std::strcmp(selected->id, "spectrum24") == 0) {
                wifiProductView = WifiProductView::None;
                startNrf24Spectrum();
            } else {
                wifiProductView = WifiProductView::None;
                rfSpectrumKind = RfSpectrumKind::Cc1101;
                rfSpectrumView = RfSpectrumView::SubGhzMenu;
                subGhzRawCapture.reset();
                subGhzCapturePersistState = CapturePersistState::Result;
                subGhzCapturePersistStatus = "volatile";
                subGhzCapturePersistGeneration = 0;
                lastRuntimeEvent = "subghz_modes";
            }
        }
    }
    const bool changed = uiController.apply(
        action, static_cast<std::uint8_t>(appCatalog.size()), openable,
        selected == nullptr ? UiController::kRootPage : selected->page);
    if (wantsLaunch && launchStatus == LaunchStatus::Started && !changed) {
        appRuntime.stop();
        lastRuntimeEvent = "launch_rolled_back";
    } else if (!wasRoot && uiController.isRoot() && changed) {
        appRuntime.stop();
        lastRuntimeEvent = "stopped";
    }
    return finish(changed);
}

struct TouchDispatchTarget final {
    TouchTarget target{};
    std::uint8_t current = 0;
};

TouchDispatchTarget touchDispatchTarget(TouchPoint point) {
    if (uiController.isRoot()) {
        const std::uint8_t first = homeFirstVisible(uiController.selection());
        return {
            leshy1::ui::hitTouchTarget(
                TouchTargetLayout::HomeRows, point, first,
                static_cast<std::uint8_t>(appCatalog.size())),
            uiController.selection(),
        };
    }
    if (uiController.page() == 2) {
        if (bleProductView == BleProductView::Devices) {
            const std::size_t first =
                bleDeviceFirstVisible(bleDeviceSelection);
            return {leshy1::ui::hitTouchTarget(
                        TouchTargetLayout::HomeRows, point,
                        static_cast<std::uint8_t>(first),
                        static_cast<std::uint8_t>(bleDeviceCatalog.size())),
                    static_cast<std::uint8_t>(bleDeviceSelection)};
        }
        if (wifiProductView == WifiProductView::Menu) {
            return {leshy1::ui::hitTouchTarget(
                        TouchTargetLayout::HomeRows, point, 0,
                        kWifiProductTaskCount),
                    wifiProductSelection};
        }
        if (wifiProductView == WifiProductView::Networks &&
            surveyWorkflow.state() == SurveyWorkflowState::Running) {
            const std::size_t first =
                wifiNetworkFirstVisible(wifiNetworkSelection);
            return {leshy1::ui::hitTouchTarget(
                        TouchTargetLayout::HomeRows, point,
                        static_cast<std::uint8_t>(first),
                        static_cast<std::uint8_t>(wifiNetworkVisibleSize())),
                    static_cast<std::uint8_t>(wifiNetworkSelection)};
        }
        if (wifiProductView == WifiProductView::Devices) {
            const std::size_t first =
                wifiDeviceFirstVisible(wifiDeviceSelection);
            return {leshy1::ui::hitTouchTarget(
                        TouchTargetLayout::HomeRows, point,
                        static_cast<std::uint8_t>(first),
                        static_cast<std::uint8_t>(wifiDeviceVisibleSize())),
                    static_cast<std::uint8_t>(wifiDeviceSelection)};
        }
        if (rfSpectrumView == RfSpectrumView::SourceMenu) {
            return {leshy1::ui::hitTouchTarget(
                        TouchTargetLayout::TwoChoices, point),
                    rfSpectrumSelection};
        }
        if (rfSpectrumView == RfSpectrumView::SubGhzMenu) {
            return {leshy1::ui::hitTouchTarget(
                        TouchTargetLayout::TwoChoices, point),
                    subGhzModeSelection};
        }
        if (rfSpectrumView == RfSpectrumView::CcBandMenu ||
            rfSpectrumView == RfSpectrumView::SubGhzCaptureBandMenu) {
            return {leshy1::ui::hitTouchTarget(
                        TouchTargetLayout::HomeRows, point, 0, 4),
                    ccBandSelectionIndex()};
        }
        if (rfSpectrumView == RfSpectrumView::None &&
            surveyWorkflow.state() == SurveyWorkflowState::Setup &&
            !productSurveySourceUnavailableVisible()) {
            const bool sources = surveySourceController.view() ==
                                 SurveySetupView::Sources;
            return {leshy1::ui::hitTouchTarget(
                        sources ? TouchTargetLayout::TwoChoices
                                : TouchTargetLayout::ThreeChoices,
                        point, 0,
                        sources
                            ? static_cast<std::uint8_t>(
                                  SurveySourceController::kSourceCount)
                            : surveySourceController.planItemCount()),
                    surveySourceController.selection()};
        }
        if (rfSpectrumView == RfSpectrumView::None &&
            surveyWorkflow.state() == SurveyWorkflowState::Running &&
            surveyController.view() == SurveyView::Filter) {
            return {leshy1::ui::hitTouchTarget(
                        TouchTargetLayout::ThreeChoices, point),
                    static_cast<std::uint8_t>(surveyController.draftFilter())};
        }
    }
    if (uiController.page() == 4 &&
        captureView == CaptureView::SourceMenu) {
        return {leshy1::ui::hitTouchTarget(
                    TouchTargetLayout::TwoChoices, point),
                captureSourceSelection};
    }
    if (uiController.page() == 5) {
        return {leshy1::ui::hitTouchTarget(
                    TouchTargetLayout::TwoChoices, point),
                languageController.selection()};
    }
    if (uiController.page() == kDevicePage) {
        const std::uint8_t first = deviceFirstVisible(deviceSelection);
        return {
            leshy1::ui::hitTouchTarget(
                TouchTargetLayout::HomeRows, point, first, kDeviceItemCount),
            deviceSelection,
        };
    }
    if (uiController.page() == 6 &&
        selfTestController.view() == SelfTestView::ModeMenu) {
        return {leshy1::ui::hitTouchTarget(
                    TouchTargetLayout::TwoChoices, point),
                selfTestController.selection()};
    }
    return {};
}

bool dispatchTouchPoint(TouchPoint point, bool synthetic = false) {
    lastTouchPoint = point;
    lastTouchChanged = false;
    if (synthetic) ++syntheticTouchPresses;
    const TouchDispatchTarget dispatch = touchDispatchTarget(point);
    if (!dispatch.target.hit) {
        ++touchMissedPresses;
        return false;
    }

    ++touchHandledPresses;
    std::uint8_t current = dispatch.current;
    bool changed = false;
    while (current > dispatch.target.index) {
        if (!applyUiAction(UiAction::Up, false)) break;
        --current;
        changed = true;
    }
    while (current < dispatch.target.index) {
        if (!applyUiAction(UiAction::Down, false)) break;
        ++current;
        changed = true;
    }
    if (current == dispatch.target.index) {
        changed = applyUiAction(UiAction::Select, false) || changed;
    }
    lastTouchChanged = changed;
    if (changed) renderInteractiveScreen(true);
    return changed;
}

void emitTouchState(Stream& reply) {
    const auto& metrics = boardTouchInput.metrics();
    const std::uint16_t rawPressure = boardTouchInput.rawPressure();
    const std::uint16_t* calibration = boardTouchInput.calibration();
    char line[640] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.touch.frontend.v1\",\"kind\":\"state\","
        "\"status\":\"%s\",\"calibration_source\":\"%s\","
        "\"calibration_required_at_boot\":%s,"
        "\"calibration_succeeded_at_boot\":%s,"
        "\"pressure_threshold\":%u,\"raw_pressure\":%u,"
        "\"calibration\":[%u,%u,%u,%u,%u],"
        "\"release_debounce_ms\":%lu,"
        "\"samples\":%lu,\"touched_samples\":%lu,"
        "\"press_events\":%lu,\"release_events\":%lu,"
        "\"rejected_coordinates\":%lu,\"pressed\":%s,"
        "\"last_x\":%u,\"last_y\":%u,"
        "\"handled_presses\":%lu,\"missed_presses\":%lu,"
        "\"synthetic_presses\":%lu,\"last_changed\":%s,"
        "\"footer_interactive\":false,\"touch_back_enabled\":false}",
        boardTouchInput.ready() ? "ready" : "calibration_required",
        leshy1::platform::arduino::touchCalibrationSourceName(
            boardTouchInput.calibrationSource()),
        touchCalibrationRequiredAtBoot ? "true" : "false",
        touchCalibrationSucceededAtBoot ? "true" : "false",
        static_cast<unsigned>(BoardTouchInput::pressureThreshold()),
        static_cast<unsigned>(rawPressure),
        static_cast<unsigned>(calibration[0]),
        static_cast<unsigned>(calibration[1]),
        static_cast<unsigned>(calibration[2]),
        static_cast<unsigned>(calibration[3]),
        static_cast<unsigned>(calibration[4]),
        static_cast<unsigned long>(leshy1::ui::TouchInput::kReleaseDebounceMs),
        static_cast<unsigned long>(metrics.samples),
        static_cast<unsigned long>(metrics.touchedSamples),
        static_cast<unsigned long>(metrics.pressEvents),
        static_cast<unsigned long>(metrics.releaseEvents),
        static_cast<unsigned long>(metrics.rejectedCoordinates),
        boardTouchInput.pressed() ? "true" : "false",
        static_cast<unsigned>(metrics.lastX),
        static_cast<unsigned>(metrics.lastY),
        static_cast<unsigned long>(touchHandledPresses),
        static_cast<unsigned long>(touchMissedPresses),
        static_cast<unsigned long>(syntheticTouchPresses),
        lastTouchChanged ? "true" : "false");
    reply.println(line);
}

void handleSyntheticTouch(Stream& reply, const char* command) {
    unsigned x = 0;
    unsigned y = 0;
    char trailing = '\0';
    if (std::sscanf(command + std::strlen("ui.touch "), "%u %u %c", &x, &y,
                    &trailing) != 2 ||
        x >= static_cast<unsigned>(Layout::ScreenWidth) ||
        y >= static_cast<unsigned>(Layout::ScreenHeight)) {
        reply.println("{\"schema\":\"leshy.touch.frontend.v1\","
                      "\"kind\":\"error\","
                      "\"reason\":\"invalid_screen_coordinate\"}");
        return;
    }
    dispatchTouchPoint(
        {static_cast<std::uint16_t>(x), static_cast<std::uint16_t>(y)}, true);
    emitTouchState(reply);
}

void calibrateTouch(Stream& reply) {
    reply.println("{\"schema\":\"leshy.touch.calibration.v1\","
                  "\"kind\":\"started\",\"points\":4}");
    reply.flush();
    const bool saved = boardTouchInput.calibrateAndSave(millis());
    renderInteractiveScreen(true);
    reply.println(saved
        ? "{\"schema\":\"leshy.touch.calibration.v1\","
          "\"kind\":\"result\",\"status\":\"pass\","
          "\"stored\":true}"
        : "{\"schema\":\"leshy.touch.calibration.v1\","
          "\"kind\":\"result\",\"status\":\"fail\","
          "\"stored\":false}");
}

void captureDisplay(Stream& reply) {
    static std::uint16_t pixels[kScreenWidth * kCaptureRows] = {};
    char line[256] = {};
    const std::uint32_t byteCount =
        static_cast<std::uint32_t>(kScreenWidth * kScreenHeight * 2);
    std::snprintf(line, sizeof(line),
                  "{\"schema\":\"leshy.ui.capture.v1\",\"kind\":\"frame_begin\","
                  "\"width\":%ld,\"height\":%ld,\"format\":\"rgb565be\","
                  "\"bytes\":%lu,\"revision\":%lu}",
                  static_cast<long>(kScreenWidth), static_cast<long>(kScreenHeight),
                  static_cast<unsigned long>(byteCount),
                  static_cast<unsigned long>(uiController.revision()));
    reply.println(line);
    reply.flush();
    for (std::int32_t y = 0; y < kScreenHeight; y += kCaptureRows) {
        display.readRect(0, y, kScreenWidth, kCaptureRows, pixels);
        reply.write(reinterpret_cast<const std::uint8_t*>(pixels), sizeof(pixels));
        delay(0);
    }
    reply.print('\n');
    std::snprintf(line, sizeof(line),
                  "{\"schema\":\"leshy.ui.capture.v1\",\"kind\":\"frame_end\","
                  "\"bytes\":%lu,\"revision\":%lu}",
                  static_cast<unsigned long>(byteCount),
                  static_cast<unsigned long>(uiController.revision()));
    reply.println(line);
    reply.flush();
}

void emitStorageContract(Stream& reply) {
    char line[256] = {};
    std::snprintf(line, sizeof(line),
                  "{\"schema\":\"leshy.storage.contract.v1\",\"kind\":\"contract\","
                  "\"head_bytes\":%u,\"head_schema\":%u,\"commit_boundaries\":6,"
                  "\"write_enabled\":false}",
                  static_cast<unsigned>(leshy1::storage::kHeadWireSize),
                  static_cast<unsigned>(leshy1::storage::kHeadSchemaVersion));
    reply.println(line);
}

void emitStorageGuard(Stream& reply) {
    char line[320] = {};
    std::snprintf(line, sizeof(line),
                  "{\"schema\":\"leshy.storage.guard.v1\",\"kind\":\"policy\","
                  "\"scratch_root\":\"%s\",\"explicit_disposable\":true,"
                  "\"exact_fingerprint\":true,\"refuse_existing_scratch\":true,"
                  "\"mount_on_boot\":false,\"format_allowed\":false,"
                  "\"write_enabled\":false}",
                  leshy1::storage::kScratchRoot);
    reply.println(line);
}

void emitStorageDiscovery(Stream& reply) {
    static char line[768] = {};
    if (storageDiscoveryReady && leshy1::storage::formatMediaDiscoveryJson(
                                     storageDiscovery, line, sizeof(line))) {
        reply.println(line);
        return;
    }
    reply.println(
        "{\"schema\":\"leshy.storage.discovery.v1\",\"kind\":\"report\","
        "\"validation\":\"failed\",\"status\":\"fault\","
        "\"mount_attempted\":false,\"write_enabled\":false,"
        "\"guard_required\":true,\"reason\":\"invalid_discovery_record\"}");
}

void emitStorageMountPolicy(Stream& reply) {
    leshy1::storage::ReadOnlyMountRequest actual;
    actual.explicitlySelected = false;
    actual.driverReadOnlyGuaranteed = BoardStorageAdapter::kDriverReadOnlyGuaranteed;
    actual.formatRequested = false;
    actual.ownedResources = 0;
    actual.conflictingOwner = false;
    const leshy1::storage::ReadOnlyMountPermit actualPermit =
        leshy1::storage::authorizeReadOnlyMountAttempt(storageDiscovery, actual);
    leshy1::storage::ReadOnlyMountRequest ifSelected = actual;
    ifSelected.explicitlySelected = true;
    const leshy1::storage::ReadOnlyMountPermit selectedPermit =
        leshy1::storage::authorizeReadOnlyMountAttempt(storageDiscovery, ifSelected);
    char line[640] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.storage.mount.policy.v1\",\"kind\":\"report\","
        "\"driver\":\"arduino_sdfs\",\"driver_read_only_guaranteed\":%s,"
        "\"explicitly_selected\":false,\"actual_status\":\"%s\","
        "\"if_selected_status\":\"%s\",\"format_requested\":false,"
        "\"required_resources\":%lu,\"owned_resources\":0,"
        "\"mount_attempted\":%s,\"execution_enabled\":false,"
        "\"write_enabled\":false,\"guard_required\":true}",
        BoardStorageAdapter::kDriverReadOnlyGuaranteed ? "true" : "false",
        leshy1::storage::readOnlyMountStatusName(actualPermit.status),
        leshy1::storage::readOnlyMountStatusName(selectedPermit.status),
        static_cast<unsigned long>(actualPermit.requiredResources),
        storageDiscovery.mountAttempted ? "true" : "false");
    reply.println(line);
}

void emitProductSurveyAdmission(Stream& reply) {
    leshy1::storage::MediaIdentity media;
    leshy1::storage::ProductStoreRequest storeRequest;
    storeRequest.operation =
        leshy1::storage::ProductStoreOperation::RecoverCatalog;
    storeRequest.rootPath = leshy1::storage::kProductSessionStoreRoot;
    storeRequest.driverReadOnlyGuaranteed =
        BoardStorageAdapter::kDriverReadOnlyGuaranteed;
    const leshy1::storage::ProductStorePermit storePermit =
        leshy1::storage::authorizeProductStore(media, storeRequest);

    leshy1::apps::survey::ProductSurveyRequest surveyRequest;
    surveyRequest.explicitStart = false;
    surveyRequest.sourceAvailable = false;
    surveyRequest.scanPlan = leshy1::drivers::wifi::defaultPassivePlan();
    surveyRequest.storePermit = storePermit;
    const leshy1::apps::survey::ProductSurveyPermit surveyPermit =
        leshy1::apps::survey::authorizeProductSurvey(surveyRequest);

    char line[1024] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.survey.product_admission.v1\","
        "\"kind\":\"policy_state\",\"status\":\"%s\","
        "\"store_status\":\"%s\",\"store_operation\":\"%s\","
        "\"store_root\":\"%s\",\"required_resources\":%lu,"
        "\"explicit_start\":false,\"passive_only\":true,"
        "\"persistent_required\":true,\"simulated_fallback\":false,"
        "\"hardware_touched\":false,\"radio_started\":false,"
        "\"storage_mounted\":false,\"storage_written\":false,"
        "\"format_allowed\":false,"
        "\"application_connect_calls\":0,"
        "\"application_raw_tx_calls\":0,"
        "\"physical_no_tx_instrumented\":false}",
        leshy1::apps::survey::productSurveyAdmissionStatusName(
            surveyPermit.status),
        leshy1::storage::productStoreAccessStatusName(storePermit.status),
        leshy1::storage::productStoreOperationName(storePermit.operation),
        leshy1::storage::kProductSessionStoreRoot,
        static_cast<unsigned long>(surveyPermit.requiredResources));
    reply.println(line);
}

void emitProductSurveySourceUnavailableTest(Stream& reply,
                                            const char* command) {
    const bool arm = std::strcmp(
        command, "survey.product.test-source-unavailable once") == 0;
    const bool clear = std::strcmp(
        command, "survey.product.test-source-unavailable clear") == 0;
    const bool safeState = productSurveyControl() ==
            ProductSurveyWorkerControl::Idle &&
        uiController.isRoot() && !appRuntime.running();
    const char* status = "invalid_request";
    if (clear && productSurveyControl() == ProductSurveyWorkerControl::Idle) {
        setProductSurveySourceUnavailableInjection(false);
        status = "cleared";
    } else if (arm && safeState) {
        setProductSurveySourceUnavailableInjection(true);
        status = "armed";
    } else if (arm) {
        status = "unsafe_state";
    }
    char line[384] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.survey.source_unavailable_test.v1\","
        "\"kind\":\"state\",\"status\":\"%s\",\"one_shot\":true,"
        "\"armed\":%s,\"worker_idle\":%s,\"ui_home\":%s,"
        "\"runtime_owner\":\"%s\",\"lease_mask\":%lu,"
        "\"hardware_touched\":false,\"source_started\":false,"
        "\"storage_mounted\":false,\"storage_written\":false}",
        status,
        productSurveySourceUnavailableInjectionArmed() ? "true" : "false",
        productSurveyControl() == ProductSurveyWorkerControl::Idle
            ? "true" : "false",
        uiController.isRoot() ? "true" : "false",
        appRuntime.activeApp(),
        static_cast<unsigned long>(appRuntime.activeResources()));
    reply.println(line);
}

void emitProductSurveyRuntimeUnavailableTest(Stream& reply,
                                             const char* command) {
    const bool wifi = std::strcmp(
        command, "survey.product.test-runtime-unavailable wifi") == 0;
    const bool ble = std::strcmp(
        command, "survey.product.test-runtime-unavailable ble") == 0;
    const bool clear = std::strcmp(
        command, "survey.product.test-runtime-unavailable clear") == 0;
    const bool safeState = productSurveyControl() ==
            ProductSurveyWorkerControl::Idle &&
        uiController.isRoot() && !appRuntime.running();
    const char* status = "invalid_request";
    if (clear && productSurveyControl() == ProductSurveyWorkerControl::Idle) {
        setProductSurveyRuntimeUnavailableInjection(0);
        status = "cleared";
    } else if ((wifi || ble) && safeState) {
        setProductSurveyRuntimeUnavailableInjection(
            leshy1::services::survey::sourceMask(
                wifi ? RadioKind::Wifi : RadioKind::Ble));
        status = "armed";
    } else if (wifi || ble) {
        status = "unsafe_state";
    }
    char line[384] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.survey.runtime_unavailable_test.v1\","
        "\"kind\":\"state\",\"status\":\"%s\",\"one_shot\":true,"
        "\"armed_mask\":%u,\"worker_idle\":%s,\"ui_home\":%s,"
        "\"runtime_owner\":\"%s\",\"lease_mask\":%lu,"
        "\"hardware_touched\":false,\"storage_mounted\":false,"
        "\"storage_written\":false}",
        status,
        static_cast<unsigned>(productSurveyRuntimeUnavailableInjectionMask()),
        productSurveyControl() == ProductSurveyWorkerControl::Idle
            ? "true" : "false",
        uiController.isRoot() ? "true" : "false",
        appRuntime.activeApp(),
        static_cast<unsigned long>(appRuntime.activeResources()));
    reply.println(line);
}

void emitSdReadOnlyProtocol(Stream& reply) {
    static char line[512] = {};
    const leshy1::storage::SdReadOnlyPlan plan =
        leshy1::storage::defaultSdIdentificationPlan();
    if (leshy1::storage::formatSdReadOnlyProtocolJson(plan, line, sizeof(line))) {
        reply.println(line);
        return;
    }
    reply.println(
        "{\"schema\":\"leshy.storage.sd.protocol.v1\",\"kind\":\"report\","
        "\"status\":\"invalid_plan\",\"write_commands\":false,"
        "\"execution_enabled\":false}");
}

void emitSdIdentificationFixture(Stream& reply) {
    static char line[640] = {};
    const leshy1::storage::SdReadOnlyPlan plan =
        leshy1::storage::defaultSdIdentificationPlan();
    const leshy1::storage::SdIdentificationTranscript transcript =
        leshy1::storage::goldenSdIdentificationTranscript();
    leshy1::storage::SdIdentity identity;
    const leshy1::storage::SdIdentificationStatus status =
        leshy1::storage::parseSdIdentification(plan, transcript, &identity);
    if (status == leshy1::storage::SdIdentificationStatus::Valid &&
        leshy1::storage::formatSdIdentificationJson(identity, line, sizeof(line))) {
        reply.println(line);
        return;
    }
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.storage.sd.identification.v1\",\"kind\":\"result\","
        "\"status\":\"%s\",\"transport\":\"golden_fake\","
        "\"physical_spi_executed\":false,\"commands_executed\":0,"
        "\"write_commands\":false,\"radio_touched\":false}",
        leshy1::storage::sdIdentificationStatusName(status));
    reply.println(line);
}

void emitSdTransportFixture(Stream& reply) {
    static char line[512] = {};
    const leshy1::storage::SdReadOnlyPlan plan =
        leshy1::storage::defaultSdIdentificationPlan();
    leshy1::storage::GoldenFakeSdTransport transport;
    const leshy1::storage::SdTransportRunResult result =
        leshy1::storage::runSdIdentificationStateMachine(plan, transport);
    if (leshy1::storage::formatSdTransportRunJson(result, line, sizeof(line))) {
        reply.println(line);
        return;
    }
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.storage.sd.transport.v1\",\"kind\":\"result\","
        "\"status\":\"%s\",\"transport\":\"golden_fake\","
        "\"physical_spi_executed\":false,\"commands_attempted\":%u,"
        "\"commands_completed\":%u,\"write_commands\":false,"
        "\"radio_touched\":false}",
        leshy1::storage::sdTransportRunStatusName(result.status),
        static_cast<unsigned>(result.commandsAttempted),
        static_cast<unsigned>(result.commandsCompleted));
    reply.println(line);
}

void emitSdWireContract(Stream& reply) {
    static char line[512] = {};
    if (leshy1::storage::formatSdWireContractJson(line, sizeof(line))) {
        reply.println(line);
        return;
    }
    reply.println(
        "{\"schema\":\"leshy.storage.sd.wire.v1\",\"kind\":\"report\","
        "\"status\":\"invalid_contract\",\"execution_enabled\":false,"
        "\"physical_spi_executed\":false,\"commands_executed\":0,"
        "\"write_commands\":false,\"radio_touched\":false}");
}

void emitPhysicalSdIdentification(Stream& reply) {
    static char line[1400] = {};
    static char cidHex[33] = {};
    static char csdHex[33] = {};
    cidHex[0] = '\0';
    csdHex[0] = '\0';

    const bool idleUi = uiController.isRoot() && !appRuntime.running();
    const bool resourcesAcquired = idleUi && resourceBroker.acquire(
        kSdIdentificationOwner, leshy1::storage::kSdIdentificationResources);
    const std::uint32_t ownedDuring =
        resourceBroker.ownedBy(kSdIdentificationOwner);
    BoardSdSpiTransport transport;
    const bool adapterBegun = resourcesAcquired && transport.begin();
    leshy1::storage::SdTransportRunResult result;
    if (!idleUi) {
        result.status = leshy1::storage::SdTransportRunStatus::ResourceConflict;
    } else if (!resourcesAcquired) {
        result.status = leshy1::storage::SdTransportRunStatus::ResourcesMissing;
    } else if (!adapterBegun) {
        result.status = leshy1::storage::SdTransportRunStatus::ExchangeFailed;
        result.physicalTransport = transport.physicalSpiStarted();
    } else {
        leshy1::storage::SdTransportRunPolicy policy;
        policy.allowPhysical = true;
        policy.explicitlySelected = true;
        policy.identificationOnly = true;
        policy.ownedResources = ownedDuring;
        result = leshy1::storage::runSdIdentificationStateMachine(
            leshy1::storage::defaultSdIdentificationPlan(), transport, policy);
        transport.end();
    }
    resourceBroker.releaseAll(kSdIdentificationOwner);
    const std::uint32_t ownedAfter =
        resourceBroker.ownedBy(kSdIdentificationOwner);

    for (std::size_t index = 0; index < result.identity.cid.size(); ++index) {
        std::snprintf(cidHex + index * 2, sizeof(cidHex) - index * 2, "%02X",
                      static_cast<unsigned>(result.identity.cid[index]));
        std::snprintf(csdHex + index * 2, sizeof(csdHex) - index * 2, "%02X",
                      static_cast<unsigned>(result.identity.csd[index]));
    }
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.storage.sd.physical.v1\",\"kind\":\"result\","
        "\"status\":\"%s\",\"parse_status\":\"%s\","
        "\"wire_status\":\"%s\",\"explicitly_selected\":true,"
        "\"identification_only\":true,\"resource_required\":%lu,"
        "\"resource_acquired\":%s,\"owned_during\":%lu,\"owned_after\":%lu,"
        "\"spi_hz\":%lu,\"detect_level\":%d,"
        "\"detect_authoritative\":false,\"physical_spi_started\":%s,"
        "\"bytes_clocked\":%lu,\"transport_exchanges\":%u,"
        "\"commands_attempted\":%u,\"commands_completed\":%u,"
        "\"init_attempts\":%u,\"ocr\":%lu,\"capacity_bytes\":%llu,"
        "\"cid_hex\":\"%s\",\"csd_hex\":\"%s\","
        "\"gpio21_stable_high\":%s,\"cleanup_complete\":%s,"
        "\"mount_attempted\":false,\"filesystem_touched\":false,"
        "\"write_commands\":false,\"format_allowed\":false,"
        "\"nrf_ce_high_events\":0,\"radio_tx_commands\":0}",
        leshy1::storage::sdTransportRunStatusName(result.status),
        leshy1::storage::sdIdentificationStatusName(result.parseStatus),
        leshy1::storage::sdWireStatusName(transport.lastWireStatus()),
        static_cast<unsigned long>(leshy1::storage::kSdIdentificationResources),
        resourcesAcquired ? "true" : "false",
        static_cast<unsigned long>(ownedDuring),
        static_cast<unsigned long>(ownedAfter),
        static_cast<unsigned long>(BoardProfile::kSdIdentificationSpiHz),
        static_cast<int>(storageDiscovery.detectLevel),
        transport.physicalSpiStarted() ? "true" : "false",
        static_cast<unsigned long>(transport.bytesClocked()),
        static_cast<unsigned>(transport.exchanges()),
        static_cast<unsigned>(result.commandsAttempted),
        static_cast<unsigned>(result.commandsCompleted),
        static_cast<unsigned>(result.identity.initAttempts),
        static_cast<unsigned long>(result.identity.ocr),
        static_cast<unsigned long long>(result.identity.capacityBytes),
        cidHex, csdHex,
        transport.gpio21StableHigh() ? "true" : "false",
        transport.cleanupComplete() ? "true" : "false");
    reply.println(line);
}

void emitPhysicalSdSector0(Stream& reply) {
    auto& line = sdPhysicalEvidence.line;
    auto& summary = sdPhysicalEvidence.summaryA;
    auto& cidHex = sdPhysicalEvidence.cidHex;
    auto& sector = sdPhysicalEvidence.sectorA;
    cidHex[0] = '\0';
    std::strcpy(summary, "{}");
    sector.fill(0);

    const bool idleUi = uiController.isRoot() && !appRuntime.running();
    const bool resourcesAcquired = idleUi && resourceBroker.acquire(
        kSdIdentificationOwner, leshy1::storage::kSdIdentificationResources);
    const std::uint32_t ownedDuring =
        resourceBroker.ownedBy(kSdIdentificationOwner);
    BoardSdSpiTransport transport;
    const bool adapterBegun = resourcesAcquired && transport.begin();
    leshy1::storage::SdTransportRunResult identity;
    leshy1::storage::SdSectorReadStatus permitStatus =
        leshy1::storage::SdSectorReadStatus::ExplicitTargetRequired;
    bool blockRead = false;
    std::uint16_t receivedCrc16 = 0;
    const char* status = "resource_unavailable";

    if (adapterBegun) {
        leshy1::storage::SdTransportRunPolicy identityPolicy;
        identityPolicy.allowPhysical = true;
        identityPolicy.explicitlySelected = true;
        identityPolicy.identificationOnly = true;
        identityPolicy.ownedResources = ownedDuring;
        identity = leshy1::storage::runSdIdentificationStateMachine(
            leshy1::storage::defaultSdIdentificationPlan(), transport,
            identityPolicy);
        if (identity.status == leshy1::storage::SdTransportRunStatus::Valid) {
            leshy1::storage::SdSectorReadRequest request;
            request.explicitlySelected = true;
            request.readOnly = true;
            request.highCapacity = identity.identity.highCapacity;
            request.capacityBytes = identity.identity.capacityBytes;
            request.lba = 0;
            request.blockCount = 1;
            request.ownedResources = ownedDuring;
            permitStatus = leshy1::storage::authorizeSdSector0Read(request);
            if (permitStatus == leshy1::storage::SdSectorReadStatus::Permitted) {
                blockRead = transport.readSingleBlock(0, &sector, &receivedCrc16);
                status = blockRead ? "valid" : "read_failed";
            } else {
                status = "permit_rejected";
            }
        } else {
            status = "identity_failed";
        }
        transport.end();
    } else if (!idleUi) {
        status = "ui_not_idle";
    } else if (resourcesAcquired) {
        status = "adapter_begin_failed";
    }
    resourceBroker.releaseAll(kSdIdentificationOwner);
    const std::uint32_t ownedAfter =
        resourceBroker.ownedBy(kSdIdentificationOwner);

    leshy1::storage::SdSector0Inspection inspection;
    if (blockRead) {
        inspection = leshy1::storage::inspectSdSector0(
            sector, identity.identity.capacityBytes);
        if (!leshy1::storage::formatSdSector0Json(
                inspection, summary, sizeof(summary))) {
            std::strcpy(summary, "{}");
            status = "format_failed";
        }
    }
    for (std::size_t index = 0; index < identity.identity.cid.size(); ++index) {
        std::snprintf(cidHex + index * 2, sizeof(cidHex) - index * 2, "%02X",
                      static_cast<unsigned>(identity.identity.cid[index]));
    }
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.storage.sd.sector0.v1\",\"kind\":\"result\","
        "\"status\":\"%s\",\"identity_status\":\"%s\","
        "\"permit_status\":\"%s\",\"wire_status\":\"%s\","
        "\"explicitly_selected\":true,\"read_only\":true,"
        "\"lba\":0,\"block_count_requested\":1,\"blocks_read\":%u,"
        "\"resource_acquired\":%s,\"owned_during\":%lu,\"owned_after\":%lu,"
        "\"spi_hz\":%lu,\"bytes_clocked\":%lu,"
        "\"identity_commands_completed\":%u,\"cid_hex\":\"%s\","
        "\"capacity_bytes\":%llu,\"wire_crc16\":%u,"
        "\"gpio21_stable_high\":%s,\"cleanup_complete\":%s,"
        "\"mount_attempted\":false,\"filesystem_touched\":false,"
        "\"raw_sector_retained\":false,\"write_commands\":false,"
        "\"format_allowed\":false,\"nrf_ce_high_events\":0,"
        "\"radio_tx_commands\":0,\"inspection\":%s}",
        status, leshy1::storage::sdTransportRunStatusName(identity.status),
        leshy1::storage::sdSectorReadStatusName(permitStatus),
        leshy1::storage::sdWireStatusName(transport.lastWireStatus()),
        static_cast<unsigned>(transport.dataBlockReads()),
        resourcesAcquired ? "true" : "false",
        static_cast<unsigned long>(ownedDuring),
        static_cast<unsigned long>(ownedAfter),
        static_cast<unsigned long>(BoardProfile::kSdIdentificationSpiHz),
        static_cast<unsigned long>(transport.bytesClocked()),
        static_cast<unsigned>(identity.commandsCompleted), cidHex,
        static_cast<unsigned long long>(identity.identity.capacityBytes),
        static_cast<unsigned>(receivedCrc16),
        transport.gpio21StableHigh() ? "true" : "false",
        transport.cleanupComplete() ? "true" : "false", summary);
    reply.println(line);
}

void emitPhysicalSdBoot(Stream& reply) {
    auto& line = sdPhysicalEvidence.line;
    auto& sector0Summary = sdPhysicalEvidence.summaryA;
    auto& bootSummary = sdPhysicalEvidence.summaryB;
    auto& cidHex = sdPhysicalEvidence.cidHex;
    auto& sector0 = sdPhysicalEvidence.sectorA;
    auto& bootSector = sdPhysicalEvidence.sectorB;
    cidHex[0] = '\0';
    std::strcpy(sector0Summary, "{}");
    std::strcpy(bootSummary, "{}");
    sector0.fill(0);
    bootSector.fill(0);

    const bool idleUi = uiController.isRoot() && !appRuntime.running();
    const bool resourcesAcquired = idleUi && resourceBroker.acquire(
        kSdIdentificationOwner, leshy1::storage::kSdIdentificationResources);
    const std::uint32_t ownedDuring =
        resourceBroker.ownedBy(kSdIdentificationOwner);
    BoardSdSpiTransport transport;
    const bool adapterBegun = resourcesAcquired && transport.begin();
    leshy1::storage::SdTransportRunResult identity;
    leshy1::storage::SdSectorReadStatus sector0Permit =
        leshy1::storage::SdSectorReadStatus::ExplicitTargetRequired;
    leshy1::storage::SdSectorReadStatus bootPermit =
        leshy1::storage::SdSectorReadStatus::ExplicitTargetRequired;
    leshy1::storage::SdSector0Inspection sector0Inspection;
    leshy1::storage::SdFilesystemBootInspection bootInspection;
    bool sector0Read = false;
    bool bootRead = false;
    std::uint16_t sector0WireCrc16 = 0;
    std::uint16_t bootWireCrc16 = 0;
    const char* status = "resource_unavailable";

    if (adapterBegun) {
        leshy1::storage::SdTransportRunPolicy identityPolicy;
        identityPolicy.allowPhysical = true;
        identityPolicy.explicitlySelected = true;
        identityPolicy.identificationOnly = true;
        identityPolicy.ownedResources = ownedDuring;
        identity = leshy1::storage::runSdIdentificationStateMachine(
            leshy1::storage::defaultSdIdentificationPlan(), transport,
            identityPolicy);
        if (identity.status == leshy1::storage::SdTransportRunStatus::Valid) {
            leshy1::storage::SdSectorReadRequest request;
            request.explicitlySelected = true;
            request.readOnly = true;
            request.highCapacity = identity.identity.highCapacity;
            request.capacityBytes = identity.identity.capacityBytes;
            request.lba = 0;
            request.blockCount = 1;
            request.ownedResources = ownedDuring;
            sector0Permit = leshy1::storage::authorizeSdSector0Read(request);
            if (sector0Permit == leshy1::storage::SdSectorReadStatus::Permitted) {
                sector0Read = transport.readSingleBlock(
                    0, &sector0, &sector0WireCrc16);
            }
            if (sector0Read) {
                sector0Inspection = leshy1::storage::inspectSdSector0(
                    sector0, identity.identity.capacityBytes);
                request.lba = sector0Inspection.firstPartitionLba;
                bootPermit = leshy1::storage::authorizeSdPartitionBootRead(
                    sector0Inspection, request);
                if (bootPermit == leshy1::storage::SdSectorReadStatus::Permitted) {
                    bootRead = transport.readSingleBlock(
                        request.lba, &bootSector, &bootWireCrc16);
                }
                if (bootRead) {
                    bootInspection = leshy1::storage::inspectSdFilesystemBoot(
                        bootSector, sector0Inspection.firstPartitionSectors);
                    status = bootInspection.geometryValid ? "valid" : "boot_invalid";
                } else {
                    status = "boot_read_failed";
                }
            } else {
                status = "sector0_read_failed";
            }
        } else {
            status = "identity_failed";
        }
        transport.end();
    } else if (!idleUi) {
        status = "ui_not_idle";
    } else if (resourcesAcquired) {
        status = "adapter_begin_failed";
    }
    resourceBroker.releaseAll(kSdIdentificationOwner);
    const std::uint32_t ownedAfter =
        resourceBroker.ownedBy(kSdIdentificationOwner);

    if (sector0Read && !leshy1::storage::formatSdSector0Json(
                           sector0Inspection, sector0Summary,
                           sizeof(sector0Summary))) {
        std::strcpy(sector0Summary, "{}");
        status = "format_failed";
    }
    if (bootRead && !leshy1::storage::formatSdFilesystemBootJson(
                        bootInspection, bootSummary, sizeof(bootSummary))) {
        std::strcpy(bootSummary, "{}");
        status = "format_failed";
    }
    for (std::size_t index = 0; index < identity.identity.cid.size(); ++index) {
        std::snprintf(cidHex + index * 2, sizeof(cidHex) - index * 2, "%02X",
                      static_cast<unsigned>(identity.identity.cid[index]));
    }
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.storage.sd.boot.v1\",\"kind\":\"result\","
        "\"status\":\"%s\",\"identity_status\":\"%s\","
        "\"sector0_permit\":\"%s\",\"boot_permit\":\"%s\","
        "\"wire_status\":\"%s\",\"explicitly_selected\":true,"
        "\"read_only\":true,\"blocks_requested\":2,\"blocks_read\":%u,"
        "\"sector0_lba\":0,\"boot_lba\":%lu,"
        "\"resource_acquired\":%s,\"owned_during\":%lu,\"owned_after\":%lu,"
        "\"spi_hz\":%lu,\"bytes_clocked\":%lu,"
        "\"identity_commands_completed\":%u,\"cid_hex\":\"%s\","
        "\"capacity_bytes\":%llu,\"sector0_wire_crc16\":%u,"
        "\"boot_wire_crc16\":%u,\"gpio21_stable_high\":%s,"
        "\"cleanup_complete\":%s,\"mount_attempted\":false,"
        "\"filesystem_touched\":false,\"raw_sectors_retained\":false,"
        "\"write_commands\":false,\"format_allowed\":false,"
        "\"nrf_ce_high_events\":0,\"radio_tx_commands\":0,"
        "\"sector0\":%s,\"boot\":%s}",
        status, leshy1::storage::sdTransportRunStatusName(identity.status),
        leshy1::storage::sdSectorReadStatusName(sector0Permit),
        leshy1::storage::sdSectorReadStatusName(bootPermit),
        leshy1::storage::sdWireStatusName(transport.lastWireStatus()),
        static_cast<unsigned>(transport.dataBlockReads()),
        static_cast<unsigned long>(sector0Inspection.firstPartitionLba),
        resourcesAcquired ? "true" : "false",
        static_cast<unsigned long>(ownedDuring),
        static_cast<unsigned long>(ownedAfter),
        static_cast<unsigned long>(BoardProfile::kSdIdentificationSpiHz),
        static_cast<unsigned long>(transport.bytesClocked()),
        static_cast<unsigned>(identity.commandsCompleted), cidHex,
        static_cast<unsigned long long>(identity.identity.capacityBytes),
        static_cast<unsigned>(sector0WireCrc16),
        static_cast<unsigned>(bootWireCrc16),
        transport.gpio21StableHigh() ? "true" : "false",
        transport.cleanupComplete() ? "true" : "false",
        sector0Summary, bootSummary);
    reply.println(line);
}

void emitPhysicalSdFsInfo(Stream& reply) {
    auto& line = sdPhysicalEvidence.line;
    auto& sector0Summary = sdPhysicalEvidence.summaryA;
    auto& bootSummary = sdPhysicalEvidence.summaryB;
    auto& fsInfoSummary = sdPhysicalEvidence.summaryC;
    auto& cidHex = sdPhysicalEvidence.cidHex;
    auto& sector0 = sdPhysicalEvidence.sectorA;
    auto& bootSector = sdPhysicalEvidence.sectorB;
    auto& fsInfoSector = sdPhysicalEvidence.sectorC;
    cidHex[0] = '\0';
    std::strcpy(sector0Summary, "{}");
    std::strcpy(bootSummary, "{}");
    std::strcpy(fsInfoSummary, "{}");
    sector0.fill(0);
    bootSector.fill(0);
    fsInfoSector.fill(0);

    const bool idleUi = uiController.isRoot() && !appRuntime.running();
    const bool resourcesAcquired = idleUi && resourceBroker.acquire(
        kSdIdentificationOwner, leshy1::storage::kSdIdentificationResources);
    const std::uint32_t ownedDuring =
        resourceBroker.ownedBy(kSdIdentificationOwner);
    BoardSdSpiTransport transport;
    const bool adapterBegun = resourcesAcquired && transport.begin();
    leshy1::storage::SdTransportRunResult identity;
    leshy1::storage::SdSectorReadStatus sector0Permit =
        leshy1::storage::SdSectorReadStatus::ExplicitTargetRequired;
    leshy1::storage::SdSectorReadStatus bootPermit =
        leshy1::storage::SdSectorReadStatus::ExplicitTargetRequired;
    leshy1::storage::SdSectorReadStatus fsInfoPermit =
        leshy1::storage::SdSectorReadStatus::ExplicitTargetRequired;
    leshy1::storage::SdSector0Inspection sector0Inspection;
    leshy1::storage::SdFilesystemBootInspection bootInspection;
    leshy1::storage::SdFat32FsInfoInspection fsInfoInspection;
    bool sector0Read = false;
    bool bootRead = false;
    bool fsInfoRead = false;
    bool fsInfoBufferZeroed = false;
    std::uint32_t fsInfoLba = 0;
    std::uint16_t sector0WireCrc16 = 0;
    std::uint16_t bootWireCrc16 = 0;
    std::uint16_t fsInfoWireCrc16 = 0;
    const char* status = "resource_unavailable";

    if (adapterBegun) {
        leshy1::storage::SdTransportRunPolicy identityPolicy;
        identityPolicy.allowPhysical = true;
        identityPolicy.explicitlySelected = true;
        identityPolicy.identificationOnly = true;
        identityPolicy.ownedResources = ownedDuring;
        identity = leshy1::storage::runSdIdentificationStateMachine(
            leshy1::storage::defaultSdIdentificationPlan(), transport,
            identityPolicy);
        if (identity.status == leshy1::storage::SdTransportRunStatus::Valid) {
            leshy1::storage::SdSectorReadRequest request;
            request.explicitlySelected = true;
            request.readOnly = true;
            request.highCapacity = identity.identity.highCapacity;
            request.capacityBytes = identity.identity.capacityBytes;
            request.lba = 0;
            request.blockCount = 1;
            request.ownedResources = ownedDuring;
            sector0Permit = leshy1::storage::authorizeSdSector0Read(request);
            if (sector0Permit == leshy1::storage::SdSectorReadStatus::Permitted) {
                sector0Read = transport.readSingleBlock(
                    0, &sector0, &sector0WireCrc16);
            }
            if (sector0Read) {
                sector0Inspection = leshy1::storage::inspectSdSector0(
                    sector0, identity.identity.capacityBytes);
                request.lba = sector0Inspection.firstPartitionLba;
                bootPermit = leshy1::storage::authorizeSdPartitionBootRead(
                    sector0Inspection, request);
                if (bootPermit == leshy1::storage::SdSectorReadStatus::Permitted) {
                    bootRead = transport.readSingleBlock(
                        request.lba, &bootSector, &bootWireCrc16);
                }
                if (bootRead) {
                    bootInspection = leshy1::storage::inspectSdFilesystemBoot(
                        bootSector, sector0Inspection.firstPartitionSectors);
                    if (leshy1::storage::calculateSdFat32FsInfoLba(
                            sector0Inspection, bootInspection, &fsInfoLba)) {
                        request.lba = fsInfoLba;
                        fsInfoPermit = leshy1::storage::authorizeSdFat32FsInfoRead(
                            sector0Inspection, bootInspection, request);
                        if (fsInfoPermit ==
                            leshy1::storage::SdSectorReadStatus::Permitted) {
                            fsInfoRead = transport.readSingleBlock(
                                request.lba, &fsInfoSector, &fsInfoWireCrc16);
                        }
                        if (fsInfoRead) {
                            fsInfoInspection =
                                leshy1::storage::inspectSdFat32FsInfo(
                                    fsInfoSector, bootInspection);
                            fsInfoSector.fill(0);
                            fsInfoBufferZeroed = true;
                            status = fsInfoInspection.hintsValid
                                ? "valid" : "fsinfo_invalid";
                        } else {
                            status = "fsinfo_read_failed";
                        }
                    } else {
                        status = "fsinfo_lba_invalid";
                    }
                } else {
                    status = "boot_read_failed";
                }
            } else {
                status = "sector0_read_failed";
            }
        } else {
            status = "identity_failed";
        }
        transport.end();
    } else if (!idleUi) {
        status = "ui_not_idle";
    } else if (resourcesAcquired) {
        status = "adapter_begin_failed";
    }
    fsInfoSector.fill(0);
    if (fsInfoRead) fsInfoBufferZeroed = true;
    resourceBroker.releaseAll(kSdIdentificationOwner);
    const std::uint32_t ownedAfter =
        resourceBroker.ownedBy(kSdIdentificationOwner);

    if (sector0Read && !leshy1::storage::formatSdSector0Json(
                           sector0Inspection, sector0Summary,
                           sizeof(sector0Summary))) {
        std::strcpy(sector0Summary, "{}");
        status = "format_failed";
    }
    if (bootRead && !leshy1::storage::formatSdFilesystemBootJson(
                        bootInspection, bootSummary, sizeof(bootSummary))) {
        std::strcpy(bootSummary, "{}");
        status = "format_failed";
    }
    if (fsInfoRead && !leshy1::storage::formatSdFat32FsInfoJson(
                          fsInfoInspection, fsInfoSummary,
                          sizeof(fsInfoSummary))) {
        std::strcpy(fsInfoSummary, "{}");
        status = "format_failed";
    }
    for (std::size_t index = 0; index < identity.identity.cid.size(); ++index) {
        std::snprintf(cidHex + index * 2, sizeof(cidHex) - index * 2, "%02X",
                      static_cast<unsigned>(identity.identity.cid[index]));
    }
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.storage.sd.fsinfo.v1\",\"kind\":\"result\","
        "\"status\":\"%s\",\"identity_status\":\"%s\","
        "\"sector0_permit\":\"%s\",\"boot_permit\":\"%s\","
        "\"fsinfo_permit\":\"%s\",\"wire_status\":\"%s\","
        "\"explicitly_selected\":true,\"read_only\":true,"
        "\"blocks_requested\":3,\"blocks_read\":%u,"
        "\"sector0_lba\":0,\"boot_lba\":%lu,\"fsinfo_lba\":%lu,"
        "\"resource_acquired\":%s,\"owned_during\":%lu,\"owned_after\":%lu,"
        "\"spi_hz\":%lu,\"bytes_clocked\":%lu,"
        "\"identity_commands_completed\":%u,\"cid_hex\":\"%s\","
        "\"capacity_bytes\":%llu,\"sector0_wire_crc16\":%u,"
        "\"boot_wire_crc16\":%u,\"fsinfo_wire_crc16\":%u,"
        "\"gpio21_stable_high\":%s,\"cleanup_complete\":%s,"
        "\"mount_attempted\":false,\"filesystem_api_touched\":false,"
        "\"technical_metadata_only\":true,\"names_read\":false,"
        "\"fsinfo_buffer_zeroed\":%s,\"raw_sectors_retained\":false,"
        "\"file_data_read\":false,\"write_commands\":false,"
        "\"format_allowed\":false,\"nrf_ce_high_events\":0,"
        "\"radio_tx_commands\":0,\"sector0\":%s,\"boot\":%s,"
        "\"fsinfo\":%s}",
        status, leshy1::storage::sdTransportRunStatusName(identity.status),
        leshy1::storage::sdSectorReadStatusName(sector0Permit),
        leshy1::storage::sdSectorReadStatusName(bootPermit),
        leshy1::storage::sdSectorReadStatusName(fsInfoPermit),
        leshy1::storage::sdWireStatusName(transport.lastWireStatus()),
        static_cast<unsigned>(transport.dataBlockReads()),
        static_cast<unsigned long>(sector0Inspection.firstPartitionLba),
        static_cast<unsigned long>(fsInfoLba),
        resourcesAcquired ? "true" : "false",
        static_cast<unsigned long>(ownedDuring),
        static_cast<unsigned long>(ownedAfter),
        static_cast<unsigned long>(BoardProfile::kSdIdentificationSpiHz),
        static_cast<unsigned long>(transport.bytesClocked()),
        static_cast<unsigned>(identity.commandsCompleted), cidHex,
        static_cast<unsigned long long>(identity.identity.capacityBytes),
        static_cast<unsigned>(sector0WireCrc16),
        static_cast<unsigned>(bootWireCrc16),
        static_cast<unsigned>(fsInfoWireCrc16),
        transport.gpio21StableHigh() ? "true" : "false",
        transport.cleanupComplete() ? "true" : "false",
        fsInfoBufferZeroed ? "true" : "false",
        sector0Summary, bootSummary, fsInfoSummary);
    reply.println(line);
}

void emitPhysicalSdFatReserved(Stream& reply) {
    auto& line = sdPhysicalEvidence.line;
    auto& sector0Summary = sdPhysicalEvidence.summaryA;
    auto& bootSummary = sdPhysicalEvidence.summaryB;
    auto& fatSummary = sdPhysicalEvidence.summaryC;
    auto& cidHex = sdPhysicalEvidence.cidHex;
    auto& sector0 = sdPhysicalEvidence.sectorA;
    auto& bootSector = sdPhysicalEvidence.sectorB;
    auto& fatSector = sdPhysicalEvidence.sectorC;
    cidHex[0] = '\0';
    std::strcpy(sector0Summary, "{}");
    std::strcpy(bootSummary, "{}");
    std::strcpy(fatSummary, "{}");
    sector0.fill(0);
    bootSector.fill(0);
    fatSector.fill(0);

    const bool idleUi = uiController.isRoot() && !appRuntime.running();
    const bool resourcesAcquired = idleUi && resourceBroker.acquire(
        kSdIdentificationOwner, leshy1::storage::kSdIdentificationResources);
    const std::uint32_t ownedDuring =
        resourceBroker.ownedBy(kSdIdentificationOwner);
    BoardSdSpiTransport transport;
    const bool adapterBegun = resourcesAcquired && transport.begin();
    leshy1::storage::SdTransportRunResult identity;
    leshy1::storage::SdSectorReadStatus sector0Permit =
        leshy1::storage::SdSectorReadStatus::ExplicitTargetRequired;
    leshy1::storage::SdSectorReadStatus bootPermit =
        leshy1::storage::SdSectorReadStatus::ExplicitTargetRequired;
    leshy1::storage::SdSectorReadStatus fsInfoPermit =
        leshy1::storage::SdSectorReadStatus::ExplicitTargetRequired;
    leshy1::storage::SdSectorReadStatus fatPermit =
        leshy1::storage::SdSectorReadStatus::ExplicitTargetRequired;
    leshy1::storage::SdSector0Inspection sector0Inspection;
    leshy1::storage::SdFilesystemBootInspection bootInspection;
    leshy1::storage::SdFat32FsInfoInspection fsInfoInspection;
    leshy1::storage::SdFat32ReservedInspection fatInspection;
    leshy1::storage::SdFat32FsInfoCrossCheck crossCheck;
    bool sector0Read = false;
    bool bootRead = false;
    bool fsInfoRead = false;
    bool fatRead = false;
    bool fsInfoBufferZeroed = false;
    bool fatBufferZeroed = false;
    std::uint32_t fsInfoLba = 0;
    std::uint32_t firstFatLba = 0;
    std::uint16_t sector0WireCrc16 = 0;
    std::uint16_t bootWireCrc16 = 0;
    std::uint16_t fsInfoWireCrc16 = 0;
    std::uint16_t fatWireCrc16 = 0;
    const char* status = "resource_unavailable";

    if (adapterBegun) {
        leshy1::storage::SdTransportRunPolicy identityPolicy;
        identityPolicy.allowPhysical = true;
        identityPolicy.explicitlySelected = true;
        identityPolicy.identificationOnly = true;
        identityPolicy.ownedResources = ownedDuring;
        identity = leshy1::storage::runSdIdentificationStateMachine(
            leshy1::storage::defaultSdIdentificationPlan(), transport,
            identityPolicy);
        if (identity.status == leshy1::storage::SdTransportRunStatus::Valid) {
            leshy1::storage::SdSectorReadRequest request;
            request.explicitlySelected = true;
            request.readOnly = true;
            request.highCapacity = identity.identity.highCapacity;
            request.capacityBytes = identity.identity.capacityBytes;
            request.lba = 0;
            request.blockCount = 1;
            request.ownedResources = ownedDuring;
            sector0Permit = leshy1::storage::authorizeSdSector0Read(request);
            if (sector0Permit == leshy1::storage::SdSectorReadStatus::Permitted) {
                sector0Read = transport.readSingleBlock(
                    0, &sector0, &sector0WireCrc16);
            }
            if (sector0Read) {
                sector0Inspection = leshy1::storage::inspectSdSector0(
                    sector0, identity.identity.capacityBytes);
                request.lba = sector0Inspection.firstPartitionLba;
                bootPermit = leshy1::storage::authorizeSdPartitionBootRead(
                    sector0Inspection, request);
                if (bootPermit == leshy1::storage::SdSectorReadStatus::Permitted) {
                    bootRead = transport.readSingleBlock(
                        request.lba, &bootSector, &bootWireCrc16);
                }
                if (bootRead) {
                    bootInspection = leshy1::storage::inspectSdFilesystemBoot(
                        bootSector, sector0Inspection.firstPartitionSectors);
                    const bool targetsValid =
                        leshy1::storage::calculateSdFat32FsInfoLba(
                            sector0Inspection, bootInspection, &fsInfoLba) &&
                        leshy1::storage::calculateSdFat32FirstFatLba(
                            sector0Inspection, bootInspection, &firstFatLba) &&
                        bootInspection.rootCluster == 2;
                    if (targetsValid) {
                        request.lba = fsInfoLba;
                        fsInfoPermit = leshy1::storage::authorizeSdFat32FsInfoRead(
                            sector0Inspection, bootInspection, request);
                        if (fsInfoPermit ==
                            leshy1::storage::SdSectorReadStatus::Permitted) {
                            fsInfoRead = transport.readSingleBlock(
                                request.lba, &fatSector, &fsInfoWireCrc16);
                        }
                        if (fsInfoRead) {
                            fsInfoInspection =
                                leshy1::storage::inspectSdFat32FsInfo(
                                    fatSector, bootInspection);
                            fatSector.fill(0);
                            fsInfoBufferZeroed = true;
                            request.lba = firstFatLba;
                            fatPermit = leshy1::storage::
                                authorizeSdFat32FirstFatSectorRead(
                                    sector0Inspection, bootInspection, request);
                            if (fatPermit ==
                                leshy1::storage::SdSectorReadStatus::Permitted) {
                                fatRead = transport.readSingleBlock(
                                    request.lba, &fatSector, &fatWireCrc16);
                            }
                            if (fatRead) {
                                fatInspection = leshy1::storage::
                                    inspectSdFat32ReservedAndRootEntries(
                                        fatSector, bootInspection);
                                crossCheck = leshy1::storage::
                                    crossCheckSdFat32FsInfoWithReservedEntries(
                                        fsInfoInspection, fatInspection,
                                        bootInspection);
                                fatSector.fill(0);
                                fatBufferZeroed = true;
                                if (!fatInspection.structureValid) {
                                    status = "fat_structure_invalid";
                                } else if (!crossCheck.compatible) {
                                    status = "fsinfo_cross_check_failed";
                                } else if (!fatInspection.cleanShutdown ||
                                           !fatInspection.noHardError) {
                                    status = "fat_health_warning";
                                } else {
                                    status = "valid";
                                }
                            } else {
                                status = "fat_read_failed";
                            }
                        } else {
                            status = "fsinfo_read_failed";
                        }
                    } else {
                        status = bootInspection.rootCluster == 2
                            ? "technical_lba_invalid" : "root_cluster_not_2";
                    }
                } else {
                    status = "boot_read_failed";
                }
            } else {
                status = "sector0_read_failed";
            }
        } else {
            status = "identity_failed";
        }
        transport.end();
    } else if (!idleUi) {
        status = "ui_not_idle";
    } else if (resourcesAcquired) {
        status = "adapter_begin_failed";
    }
    fatSector.fill(0);
    if (fsInfoRead) fsInfoBufferZeroed = true;
    if (fatRead) fatBufferZeroed = true;
    resourceBroker.releaseAll(kSdIdentificationOwner);
    const std::uint32_t ownedAfter =
        resourceBroker.ownedBy(kSdIdentificationOwner);

    if (sector0Read && !leshy1::storage::formatSdSector0Json(
                           sector0Inspection, sector0Summary,
                           sizeof(sector0Summary))) {
        std::strcpy(sector0Summary, "{}");
        status = "format_failed";
    }
    if (bootRead && !leshy1::storage::formatSdFilesystemBootJson(
                        bootInspection, bootSummary, sizeof(bootSummary))) {
        std::strcpy(bootSummary, "{}");
        status = "format_failed";
    }
    if (fatRead && !leshy1::storage::formatSdFat32ReservedInspectionJson(
                       fatInspection, fatSummary, sizeof(fatSummary))) {
        std::strcpy(fatSummary, "{}");
        status = "format_failed";
    }
    for (std::size_t index = 0; index < identity.identity.cid.size(); ++index) {
        std::snprintf(cidHex + index * 2, sizeof(cidHex) - index * 2, "%02X",
                      static_cast<unsigned>(identity.identity.cid[index]));
    }
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.storage.sd.fat_reserved.v1\",\"kind\":\"result\","
        "\"status\":\"%s\",\"identity_status\":\"%s\","
        "\"sector0_permit\":\"%s\",\"boot_permit\":\"%s\","
        "\"fsinfo_permit\":\"%s\",\"fat_permit\":\"%s\","
        "\"wire_status\":\"%s\",\"explicitly_selected\":true,"
        "\"read_only\":true,\"blocks_requested\":4,\"blocks_read\":%u,"
        "\"sector0_lba\":0,\"boot_lba\":%lu,\"fsinfo_lba\":%lu,"
        "\"first_fat_lba\":%lu,\"fat_entries_inspected\":3,"
        "\"resource_acquired\":%s,\"owned_during\":%lu,\"owned_after\":%lu,"
        "\"spi_hz\":%lu,\"bytes_clocked\":%lu,"
        "\"identity_commands_completed\":%u,\"cid_hex\":\"%s\","
        "\"capacity_bytes\":%llu,\"sector0_wire_crc16\":%u,"
        "\"boot_wire_crc16\":%u,\"fsinfo_wire_crc16\":%u,"
        "\"fat_wire_crc16\":%u,\"fsinfo_signatures_valid\":%s,"
        "\"fsinfo_hints_valid\":%s,\"fsinfo_data_clusters\":%lu,"
        "\"fsinfo_free_count_known\":%s,\"fsinfo_free_clusters\":%lu,"
        "\"fsinfo_next_free_known\":%s,\"fsinfo_next_free_cluster\":%lu,"
        "\"cross_check_available\":%s,\"free_hint_compatible\":%s,"
        "\"next_free_hint_compatible\":%s,\"cross_check_compatible\":%s,"
        "\"gpio21_stable_high\":%s,\"cleanup_complete\":%s,"
        "\"mount_attempted\":false,\"filesystem_api_touched\":false,"
        "\"technical_metadata_only\":true,\"names_read\":false,"
        "\"fsinfo_buffer_zeroed\":%s,\"fat_buffer_zeroed\":%s,"
        "\"raw_sectors_retained\":false,\"fat_chain_followed\":false,"
        "\"file_data_read\":false,\"write_commands\":false,"
        "\"format_allowed\":false,\"nrf_ce_high_events\":0,"
        "\"radio_tx_commands\":0,\"sector0\":%s,\"boot\":%s,\"fat\":%s}",
        status, leshy1::storage::sdTransportRunStatusName(identity.status),
        leshy1::storage::sdSectorReadStatusName(sector0Permit),
        leshy1::storage::sdSectorReadStatusName(bootPermit),
        leshy1::storage::sdSectorReadStatusName(fsInfoPermit),
        leshy1::storage::sdSectorReadStatusName(fatPermit),
        leshy1::storage::sdWireStatusName(transport.lastWireStatus()),
        static_cast<unsigned>(transport.dataBlockReads()),
        static_cast<unsigned long>(sector0Inspection.firstPartitionLba),
        static_cast<unsigned long>(fsInfoLba),
        static_cast<unsigned long>(firstFatLba),
        resourcesAcquired ? "true" : "false",
        static_cast<unsigned long>(ownedDuring),
        static_cast<unsigned long>(ownedAfter),
        static_cast<unsigned long>(BoardProfile::kSdIdentificationSpiHz),
        static_cast<unsigned long>(transport.bytesClocked()),
        static_cast<unsigned>(identity.commandsCompleted), cidHex,
        static_cast<unsigned long long>(identity.identity.capacityBytes),
        static_cast<unsigned>(sector0WireCrc16),
        static_cast<unsigned>(bootWireCrc16),
        static_cast<unsigned>(fsInfoWireCrc16),
        static_cast<unsigned>(fatWireCrc16),
        fsInfoInspection.signaturesValid ? "true" : "false",
        fsInfoInspection.hintsValid ? "true" : "false",
        static_cast<unsigned long>(fsInfoInspection.dataClusters),
        fsInfoInspection.freeCountKnown ? "true" : "false",
        static_cast<unsigned long>(fsInfoInspection.freeClusters),
        fsInfoInspection.nextFreeKnown ? "true" : "false",
        static_cast<unsigned long>(fsInfoInspection.nextFreeCluster),
        crossCheck.available ? "true" : "false",
        crossCheck.freeHintCompatible ? "true" : "false",
        crossCheck.nextFreeHintCompatible ? "true" : "false",
        crossCheck.compatible ? "true" : "false",
        transport.gpio21StableHigh() ? "true" : "false",
        transport.cleanupComplete() ? "true" : "false",
        fsInfoBufferZeroed ? "true" : "false",
        fatBufferZeroed ? "true" : "false",
        sector0Summary, bootSummary, fatSummary);
    reply.println(line);
}

void emitPhysicalSdRootMetadata(Stream& reply) {
    auto& line = sdPhysicalEvidence.line;
    auto& sector0Summary = sdPhysicalEvidence.summaryA;
    auto& bootSummary = sdPhysicalEvidence.summaryB;
    auto& directorySummary = sdPhysicalEvidence.summaryC;
    auto& cidHex = sdPhysicalEvidence.cidHex;
    auto& sector0 = sdPhysicalEvidence.sectorA;
    auto& bootSector = sdPhysicalEvidence.sectorB;
    auto& directorySector = sdPhysicalEvidence.sectorC;
    cidHex[0] = '\0';
    std::strcpy(sector0Summary, "{}");
    std::strcpy(bootSummary, "{}");
    std::strcpy(directorySummary, "{}");
    sector0.fill(0);
    bootSector.fill(0);
    directorySector.fill(0);

    const bool idleUi = uiController.isRoot() && !appRuntime.running();
    const bool resourcesAcquired = idleUi && resourceBroker.acquire(
        kSdIdentificationOwner, leshy1::storage::kSdIdentificationResources);
    const std::uint32_t ownedDuring =
        resourceBroker.ownedBy(kSdIdentificationOwner);
    BoardSdSpiTransport transport;
    const bool adapterBegun = resourcesAcquired && transport.begin();
    leshy1::storage::SdTransportRunResult identity;
    leshy1::storage::SdSectorReadStatus sector0Permit =
        leshy1::storage::SdSectorReadStatus::ExplicitTargetRequired;
    leshy1::storage::SdSectorReadStatus bootPermit =
        leshy1::storage::SdSectorReadStatus::ExplicitTargetRequired;
    leshy1::storage::SdSectorReadStatus directoryPermit =
        leshy1::storage::SdSectorReadStatus::ExplicitTargetRequired;
    leshy1::storage::SdSector0Inspection sector0Inspection;
    leshy1::storage::SdFilesystemBootInspection bootInspection;
    leshy1::storage::SdFat32DirectoryAggregate directoryAggregate;
    bool sector0Read = false;
    bool bootRead = false;
    bool directoryRead = false;
    bool directoryBufferZeroed = false;
    std::uint32_t rootDirectoryLba = 0;
    std::uint16_t sector0WireCrc16 = 0;
    std::uint16_t bootWireCrc16 = 0;
    std::uint16_t directoryWireCrc16 = 0;
    const char* status = "resource_unavailable";

    if (adapterBegun) {
        leshy1::storage::SdTransportRunPolicy identityPolicy;
        identityPolicy.allowPhysical = true;
        identityPolicy.explicitlySelected = true;
        identityPolicy.identificationOnly = true;
        identityPolicy.ownedResources = ownedDuring;
        identity = leshy1::storage::runSdIdentificationStateMachine(
            leshy1::storage::defaultSdIdentificationPlan(), transport,
            identityPolicy);
        if (identity.status == leshy1::storage::SdTransportRunStatus::Valid) {
            leshy1::storage::SdSectorReadRequest request;
            request.explicitlySelected = true;
            request.readOnly = true;
            request.highCapacity = identity.identity.highCapacity;
            request.capacityBytes = identity.identity.capacityBytes;
            request.lba = 0;
            request.blockCount = 1;
            request.ownedResources = ownedDuring;
            sector0Permit = leshy1::storage::authorizeSdSector0Read(request);
            if (sector0Permit == leshy1::storage::SdSectorReadStatus::Permitted) {
                sector0Read = transport.readSingleBlock(
                    0, &sector0, &sector0WireCrc16);
            }
            if (sector0Read) {
                sector0Inspection = leshy1::storage::inspectSdSector0(
                    sector0, identity.identity.capacityBytes);
                request.lba = sector0Inspection.firstPartitionLba;
                bootPermit = leshy1::storage::authorizeSdPartitionBootRead(
                    sector0Inspection, request);
                if (bootPermit == leshy1::storage::SdSectorReadStatus::Permitted) {
                    bootRead = transport.readSingleBlock(
                        request.lba, &bootSector, &bootWireCrc16);
                }
                if (bootRead) {
                    bootInspection = leshy1::storage::inspectSdFilesystemBoot(
                        bootSector, sector0Inspection.firstPartitionSectors);
                    if (leshy1::storage::calculateSdFat32RootDirectoryLba(
                            sector0Inspection, bootInspection,
                            &rootDirectoryLba)) {
                        status = "valid";
                        for (std::uint8_t sectorOffset = 0;
                             sectorOffset < bootInspection.sectorsPerCluster;
                             ++sectorOffset) {
                            request.lba = rootDirectoryLba + sectorOffset;
                            directoryPermit = leshy1::storage::
                                authorizeSdFat32RootDirectorySectorRead(
                                    sector0Inspection, bootInspection,
                                    sectorOffset, request);
                            if (directoryPermit !=
                                leshy1::storage::SdSectorReadStatus::Permitted) {
                                status = "directory_permit_rejected";
                                break;
                            }
                            directoryRead = transport.readSingleBlock(
                                request.lba, &directorySector,
                                &directoryWireCrc16);
                            if (!directoryRead ||
                                !leshy1::storage::appendSdFat32DirectoryMetadata(
                                    directorySector, &directoryAggregate)) {
                                status = "directory_read_failed";
                                directorySector.fill(0);
                                directoryBufferZeroed = true;
                                break;
                            }
                            directorySector.fill(0);
                            directoryBufferZeroed = true;
                            if (directoryAggregate.endMarkerSeen) break;
                        }
                        if (std::strcmp(status, "valid") == 0 &&
                            !directoryAggregate.endMarkerSeen) {
                            status = "cluster_boundary_reached";
                        }
                    } else {
                        status = "root_lba_invalid";
                    }
                } else {
                    status = "boot_read_failed";
                }
            } else {
                status = "sector0_read_failed";
            }
        } else {
            status = "identity_failed";
        }
        transport.end();
    } else if (!idleUi) {
        status = "ui_not_idle";
    } else if (resourcesAcquired) {
        status = "adapter_begin_failed";
    }
    directorySector.fill(0);
    if (directoryRead) directoryBufferZeroed = true;
    resourceBroker.releaseAll(kSdIdentificationOwner);
    const std::uint32_t ownedAfter =
        resourceBroker.ownedBy(kSdIdentificationOwner);

    if (sector0Read && !leshy1::storage::formatSdSector0Json(
                           sector0Inspection, sector0Summary,
                           sizeof(sector0Summary))) {
        std::strcpy(sector0Summary, "{}");
        status = "format_failed";
    }
    if (bootRead && !leshy1::storage::formatSdFilesystemBootJson(
                        bootInspection, bootSummary, sizeof(bootSummary))) {
        std::strcpy(bootSummary, "{}");
        status = "format_failed";
    }
    if (directoryAggregate.sectorsInspected != 0 &&
        !leshy1::storage::formatSdFat32DirectoryAggregateJson(
                             directoryAggregate, directorySummary,
                             sizeof(directorySummary))) {
        std::strcpy(directorySummary, "{}");
        status = "format_failed";
    }
    for (std::size_t index = 0; index < identity.identity.cid.size(); ++index) {
        std::snprintf(cidHex + index * 2, sizeof(cidHex) - index * 2, "%02X",
                      static_cast<unsigned>(identity.identity.cid[index]));
    }
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.storage.sd.root_cluster_metadata.v1\","
        "\"kind\":\"result\","
        "\"status\":\"%s\",\"identity_status\":\"%s\","
        "\"sector0_permit\":\"%s\",\"boot_permit\":\"%s\","
        "\"directory_permit\":\"%s\",\"wire_status\":\"%s\","
        "\"privacy_policy\":\"counts_hash_only\","
        "\"explicitly_selected\":true,\"read_only\":true,"
        "\"blocks_requested_max\":%lu,\"blocks_read\":%u,"
        "\"sector0_lba\":0,\"boot_lba\":%lu,"
        "\"directory_lba\":%lu,\"directory_cluster_sectors\":%lu,"
        "\"directory_sectors_read\":%u,"
        "\"resource_acquired\":%s,\"owned_during\":%lu,\"owned_after\":%lu,"
        "\"spi_hz\":%lu,\"bytes_clocked\":%lu,"
        "\"identity_commands_completed\":%u,\"cid_hex\":\"%s\","
        "\"capacity_bytes\":%llu,\"sector0_wire_crc16\":%u,"
        "\"boot_wire_crc16\":%u,\"last_directory_wire_crc16\":%u,"
        "\"gpio21_stable_high\":%s,\"cleanup_complete\":%s,"
        "\"mount_attempted\":false,\"filesystem_api_touched\":false,"
        "\"filesystem_metadata_read\":true,\"directory_names_retained\":false,"
        "\"directory_buffer_zeroed\":%s,\"raw_sectors_retained\":false,"
        "\"root_end_marker_seen\":%s,\"fat_chain_followed\":false,"
        "\"file_data_read\":false,\"write_commands\":false,"
        "\"format_allowed\":false,\"nrf_ce_high_events\":0,"
        "\"radio_tx_commands\":0,\"sector0\":%s,\"boot\":%s,"
        "\"directory\":%s}",
        status, leshy1::storage::sdTransportRunStatusName(identity.status),
        leshy1::storage::sdSectorReadStatusName(sector0Permit),
        leshy1::storage::sdSectorReadStatusName(bootPermit),
        leshy1::storage::sdSectorReadStatusName(directoryPermit),
        leshy1::storage::sdWireStatusName(transport.lastWireStatus()),
        static_cast<unsigned long>(2U + bootInspection.sectorsPerCluster),
        static_cast<unsigned>(transport.dataBlockReads()),
        static_cast<unsigned long>(sector0Inspection.firstPartitionLba),
        static_cast<unsigned long>(rootDirectoryLba),
        static_cast<unsigned long>(bootInspection.sectorsPerCluster),
        static_cast<unsigned>(directoryAggregate.sectorsInspected),
        resourcesAcquired ? "true" : "false",
        static_cast<unsigned long>(ownedDuring),
        static_cast<unsigned long>(ownedAfter),
        static_cast<unsigned long>(BoardProfile::kSdIdentificationSpiHz),
        static_cast<unsigned long>(transport.bytesClocked()),
        static_cast<unsigned>(identity.commandsCompleted), cidHex,
        static_cast<unsigned long long>(identity.identity.capacityBytes),
        static_cast<unsigned>(sector0WireCrc16),
        static_cast<unsigned>(bootWireCrc16),
        static_cast<unsigned>(directoryWireCrc16),
        transport.gpio21StableHigh() ? "true" : "false",
        transport.cleanupComplete() ? "true" : "false",
        directoryBufferZeroed ? "true" : "false",
        directoryAggregate.endMarkerSeen ? "true" : "false",
        sector0Summary, bootSummary, directorySummary);
    reply.println(line);
}

leshy1::storage::CommitStage resetBoundaryStage(unsigned number) {
    switch (number) {
        case 1: return leshy1::storage::CommitStage::WritePayloads;
        case 2: return leshy1::storage::CommitStage::SyncPayloads;
        case 3: return leshy1::storage::CommitStage::WriteManifest;
        case 4: return leshy1::storage::CommitStage::SyncManifest;
        case 5: return leshy1::storage::CommitStage::WriteHead;
        case 6: return leshy1::storage::CommitStage::SyncHead;
        default: return leshy1::storage::CommitStage::Complete;
    }
}

const char* resetExpectedRecovery(unsigned boundary) {
    if (boundary <= 4) return "prior_generation";
    if (boundary == 5) return "prior_or_new_generation";
    if (boundary == 6) return "new_generation";
    return "invalid";
}

bool resetRecoveredGenerationAllowed(unsigned boundary,
                                     std::uint32_t generation) {
    if (boundary >= 1 && boundary <= 4) return generation == 1;
    if (boundary == 5) return generation == 1 || generation == 2;
    return boundary == 6 && generation == 2;
}

bool prepareLittleFsResetFixture() {
    littleFsResetSession.reset();
    return littleFsResetSession.start("littlefs-reset", 1000) ==
               SessionStatus::Started &&
        appendGoldenObservations(littleFsResetSession) &&
        littleFsResetSession.stop(3000) == SessionStatus::Stopped;
}

bool computeLittleFsResetToken(const char* fingerprint, const char* runId,
                               unsigned boundary,
                               std::uint8_t output[32]) {
    if (fingerprint == nullptr || std::strlen(fingerprint) != 64 ||
        runId == nullptr || runId[0] == '\0' || output == nullptr ||
        boundary < 1 || boundary > 6) {
        return false;
    }
    const std::uint8_t separator = 0;
    const std::uint8_t boundaryByte = static_cast<std::uint8_t>(boundary);
    mbedtls_sha256_context context;
    mbedtls_sha256_init(&context);
    bool valid = mbedtls_sha256_starts(&context, 0) == 0 &&
        mbedtls_sha256_update(
            &context, reinterpret_cast<const std::uint8_t*>(fingerprint),
            std::strlen(fingerprint)) == 0 &&
        mbedtls_sha256_update(&context, &separator, 1) == 0 &&
        mbedtls_sha256_update(
            &context, reinterpret_cast<const std::uint8_t*>(runId),
            std::strlen(runId)) == 0 &&
        mbedtls_sha256_update(&context, &separator, 1) == 0 &&
        mbedtls_sha256_update(&context, &boundaryByte, 1) == 0 &&
        mbedtls_sha256_finish(&context, output) == 0;
    mbedtls_sha256_free(&context);
    return valid;
}

bool armLittleFsResetContinuity(const char* fingerprint, const char* runId,
                                unsigned boundary) {
    littleFsResetRtcState.magic = 0;
    littleFsResetRtcState.boundary = boundary;
    if (!computeLittleFsResetToken(
            fingerprint, runId, boundary, littleFsResetRtcState.token)) {
        std::memset(littleFsResetRtcState.token, 0,
                    sizeof(littleFsResetRtcState.token));
        return false;
    }
    littleFsResetRtcState.magic = kLittleFsResetRtcMagic;
    return true;
}

bool littleFsResetContinuityValid(const char* fingerprint, const char* runId,
                                  unsigned boundary) {
    std::uint8_t expected[32] = {};
    const bool computed = computeLittleFsResetToken(
        fingerprint, runId, boundary, expected);
    const bool valid = computed &&
        littleFsResetRtcState.magic == kLittleFsResetRtcMagic &&
        littleFsResetRtcState.boundary == boundary &&
        std::memcmp(expected, littleFsResetRtcState.token,
                    sizeof(expected)) == 0;
    std::memset(expected, 0, sizeof(expected));
    return valid;
}

bool inspectStoredGeneration(leshy1::storage::SessionStoreIo& io,
                             leshy1::storage::SessionStoreWorkspace& workspace,
                             const SurveySession& expected,
                             std::uint32_t generation,
                             StoredGenerationEvidence* evidence) {
    if (evidence == nullptr) return false;
    *evidence = {};
    if (leshy1::storage::encodeObservationSegment(
            expected, workspace.segment.data(), workspace.segment.size(),
            &evidence->expectedSegmentSize) !=
            leshy1::storage::SessionCodecStatus::Valid ||
        leshy1::storage::encodeSessionManifest(
            expected, workspace.segment.data(), evidence->expectedSegmentSize,
            workspace.manifest.data(), workspace.manifest.size(),
            &evidence->expectedManifestSize) !=
            leshy1::storage::SessionCodecStatus::Valid) {
        return false;
    }
    evidence->expectedSegmentCrc = leshy1::storage::crc32c(
        workspace.segment.data(), evidence->expectedSegmentSize);
    evidence->expectedManifestCrc = leshy1::storage::crc32c(
        workspace.manifest.data(), evidence->expectedManifestSize);

    char segmentPath[leshy1::storage::kSessionStorePathMax] = {};
    char manifestPath[leshy1::storage::kSessionStorePathMax] = {};
    if (!leshy1::storage::formatSessionStorePath(
            leshy1::storage::StoreFileKind::Segment, generation, segmentPath,
            sizeof(segmentPath)) ||
        !leshy1::storage::formatSessionStorePath(
            leshy1::storage::StoreFileKind::Manifest, generation, manifestPath,
            sizeof(manifestPath)) ||
        io.readFile(segmentPath, workspace.segment.data(), workspace.segment.size(),
                    &evidence->observedSegmentSize) !=
            leshy1::storage::SessionStoreIo::ReadStatus::Ok ||
        io.readFile(manifestPath, workspace.manifest.data(), workspace.manifest.size(),
                    &evidence->observedManifestSize) !=
            leshy1::storage::SessionStoreIo::ReadStatus::Ok) {
        return false;
    }
    evidence->observedSegmentCrc = leshy1::storage::crc32c(
        workspace.segment.data(), evidence->observedSegmentSize);
    evidence->observedManifestCrc = leshy1::storage::crc32c(
        workspace.manifest.data(), evidence->observedManifestSize);
    evidence->unchanged =
        evidence->expectedSegmentSize == evidence->observedSegmentSize &&
        evidence->expectedManifestSize == evidence->observedManifestSize &&
        evidence->expectedSegmentCrc == evidence->observedSegmentCrc &&
        evidence->expectedManifestCrc == evidence->observedManifestCrc;
    return evidence->unchanged;
}

void restartAtSessionStoreBoundary(void* rawContext,
                                   leshy1::storage::CommitStage boundary) {
    auto* context = static_cast<ResetBoundaryHookContext*>(rawContext);
    if (context != nullptr && context->reply != nullptr) {
        std::snprintf(
            sdPhysicalEvidence.line, sizeof(sdPhysicalEvidence.line),
            "{\"schema\":\"leshy.storage.sd.session_store_reset.v1\","
            "\"kind\":\"reset_trigger\",\"status\":\"boundary_reached\","
            "\"run_id\":\"%s\",\"boundary\":%u,\"boundary_name\":\"%s\","
            "\"reset_injection\":true,\"physical_power_cut\":false}",
            context->runId != nullptr ? context->runId : "invalid",
            context->boundaryNumber,
            leshy1::storage::sessionStoreBoundaryName(boundary));
        context->reply->println(sdPhysicalEvidence.line);
        context->reply->flush();
    }
    Serial.flush();
    Serial0.flush();
    delay(10);
    esp_restart();
}

[[noreturn]] void waitForPowerCutAtSessionStoreBoundary(
    void* rawContext, leshy1::storage::CommitStage boundary) {
    auto* context = static_cast<ResetBoundaryHookContext*>(rawContext);
    if (context != nullptr && context->reply != nullptr) {
        std::snprintf(
            sdPhysicalEvidence.line, sizeof(sdPhysicalEvidence.line),
            "{\"schema\":\"leshy.storage.sd.session_store_reset.v1\","
            "\"kind\":\"reset_trigger\",\"status\":\"boundary_reached\","
            "\"run_id\":\"%s\",\"boundary\":%u,\"boundary_name\":\"%s\","
            "\"reset_injection\":false,\"physical_power_cut\":true}",
            context->runId != nullptr ? context->runId : "invalid",
            context->boundaryNumber,
            leshy1::storage::sessionStoreBoundaryName(boundary));
        context->reply->println(sdPhysicalEvidence.line);
        context->reply->flush();
    }
    Serial.flush();
    Serial0.flush();
    while (true) {
        if (esp_task_wdt_status(nullptr) == ESP_OK) {
            esp_task_wdt_reset();
        }
        delay(50);
    }
}

void restartAtLittleFsSessionStoreBoundary(
    void* rawContext, leshy1::storage::CommitStage boundary) {
    auto* context = static_cast<ResetBoundaryHookContext*>(rawContext);
    if (context != nullptr && context->reply != nullptr) {
        std::snprintf(
            sdPhysicalEvidence.line, sizeof(sdPhysicalEvidence.line),
            "{\"schema\":\"leshy.storage.littlefs.reset.v1\","
            "\"kind\":\"reset_trigger\",\"status\":\"boundary_reached\","
            "\"run_id\":\"%s\",\"boundary\":%u,\"boundary_name\":\"%s\","
            "\"continuity_armed\":true,\"reset_injection\":true,"
            "\"physical_power_cut\":false}",
            context->runId != nullptr ? context->runId : "invalid",
            context->boundaryNumber,
            leshy1::storage::sessionStoreBoundaryName(boundary));
        context->reply->println(sdPhysicalEvidence.line);
        context->reply->flush();
    }
    Serial.flush();
    Serial0.flush();
    delay(10);
    esp_restart();
}

bool parseSdSessionStoreCommand(const char* command, const char* prefix,
                                char* fingerprint,
                                std::size_t fingerprintCapacity, char* runId,
                                std::size_t runIdCapacity) {
    if (command == nullptr || prefix == nullptr || fingerprint == nullptr ||
        runId == nullptr ||
        fingerprintCapacity < 33 || runIdCapacity < 33 ||
        std::strncmp(command, prefix, std::strlen(prefix)) != 0) {
        return false;
    }
    char extra = '\0';
    const int parsed = std::sscanf(
        command + std::strlen(prefix), "%32[0-9A-F] %32[A-Za-z0-9_-] %c",
        fingerprint, runId, &extra);
    return parsed == 2 && std::strlen(fingerprint) == 32 && runId[0] != '\0';
}

bool parseExactFingerprintCommand(const char* command, const char* prefix,
                                  char* fingerprint,
                                  std::size_t fingerprintCapacity) {
    if (command == nullptr || prefix == nullptr || fingerprint == nullptr ||
        fingerprintCapacity < 33 ||
        std::strncmp(command, prefix, std::strlen(prefix)) != 0) {
        return false;
    }
    char extra = '\0';
    const int parsed = std::sscanf(command + std::strlen(prefix),
                                   "%32[0-9A-F] %c", fingerprint, &extra);
    return parsed == 1 && std::strlen(fingerprint) == 32;
}

void emitPhysicalSdReadOnlyMount(Stream& reply,
                                 const char* expectedFingerprint) {
    auto& line = sdPhysicalEvidence.line;
    auto& cidHex = sdPhysicalEvidence.cidHex;
    cidHex[0] = '\0';
    const bool idleUi = uiController.isRoot() && !appRuntime.running();
    const bool resourcesAcquired = idleUi && resourceBroker.acquire(
        kSdIdentificationOwner, leshy1::storage::kSdIdentificationResources);
    const std::uint32_t ownedDuring =
        resourceBroker.ownedBy(kSdIdentificationOwner);

    BoardSdSpiTransport identityTransport;
    const bool identityAdapterBegun = resourcesAcquired && identityTransport.begin();
    leshy1::storage::SdTransportRunResult identity;
    if (identityAdapterBegun) {
        leshy1::storage::SdTransportRunPolicy policy;
        policy.allowPhysical = true;
        policy.explicitlySelected = true;
        policy.identificationOnly = true;
        policy.ownedResources = ownedDuring;
        identity = leshy1::storage::runSdIdentificationStateMachine(
            leshy1::storage::defaultSdIdentificationPlan(), identityTransport,
            policy);
        identityTransport.end();
    }
    const bool identityCleanup = identityTransport.cleanupComplete();
    for (std::size_t index = 0; index < identity.identity.cid.size(); ++index) {
        std::snprintf(cidHex + index * 2,
                      sizeof(sdPhysicalEvidence.cidHex) - index * 2, "%02X",
                      static_cast<unsigned>(identity.identity.cid[index]));
    }
    const bool fingerprintMatched =
        identity.status == leshy1::storage::SdTransportRunStatus::Valid &&
        std::strcmp(cidHex, expectedFingerprint) == 0;

    BoardSdFilesystem filesystem;
    const bool mountAttempted = fingerprintMatched;
    const bool mounted = fingerprintMatched && filesystem.beginReadOnly();
    const bool readOnlyGuaranteed = mounted && filesystem.readOnlyGuaranteed();
    const std::uint64_t cardCapacity =
        mounted ? filesystem.cardCapacityBytes() : 0;
    const std::uint64_t filesystemCapacity =
        mounted ? filesystem.filesystemCapacityBytes() : 0;
    const std::uint64_t freeBytes = mounted ? filesystem.freeBytes() : 0;
    const bool capacityMatched = mounted &&
        cardCapacity == identity.identity.capacityBytes &&
        filesystemCapacity != 0 && filesystemCapacity <= cardCapacity;
    const bool rootExists =
        mounted && filesystem.exists(leshy1::storage::kProductSessionStoreRoot);

    leshy1::storage::MediaIdentity media;
    media.present = capacityMatched;
    media.kind = leshy1::storage::MediaKind::Sd;
    media.fingerprint = cidHex;
    media.capacityBytes = cardCapacity;
    media.freeBytes = freeBytes;
    leshy1::storage::ProductStoreRequest request;
    request.operation = leshy1::storage::ProductStoreOperation::RecoverCatalog;
    request.expectedFingerprint = expectedFingerprint;
    request.rootPath = leshy1::storage::kProductSessionStoreRoot;
    request.rootExists = rootExists;
    request.driverReadOnlyGuaranteed = readOnlyGuaranteed;
    request.driverWriteEnabled = false;
    request.ownedResources = ownedDuring;
    const leshy1::storage::ProductStorePermit permit =
        leshy1::storage::authorizeProductStore(media, request);
    const std::uint32_t blockedWritesBeforeEnd =
        filesystem.blockedWriteAttempts();
    filesystem.end();
    const bool mountCleanup = filesystem.cleanupComplete();
    const std::uint32_t blockedWrites = filesystem.blockedWriteAttempts();
    resourceBroker.releaseAll(kSdIdentificationOwner);
    const std::uint32_t ownedAfter =
        resourceBroker.ownedBy(kSdIdentificationOwner);
    const bool valid = idleUi && resourcesAcquired && identityAdapterBegun &&
        identity.status == leshy1::storage::SdTransportRunStatus::Valid &&
        identityCleanup && fingerprintMatched && mounted &&
        readOnlyGuaranteed && capacityMatched && blockedWritesBeforeEnd == 0 &&
        blockedWrites == 0 && mountCleanup && ownedAfter == 0;

    std::snprintf(
        line, sizeof(sdPhysicalEvidence.line),
        "{\"schema\":\"leshy.storage.sd.readonly_mount.v1\","
        "\"kind\":\"result\",\"status\":\"%s\","
        "\"expected_fingerprint\":\"%s\",\"cid_hex\":\"%s\","
        "\"fingerprint_matched\":%s,\"mount_attempted\":%s,"
        "\"mounted\":%s,\"read_only_guaranteed\":%s,"
        "\"write_enabled\":false,\"format_allowed\":false,"
        "\"blocked_write_attempts\":%lu,\"card_capacity_bytes\":%llu,"
        "\"filesystem_capacity_bytes\":%llu,\"free_bytes\":%llu,"
        "\"capacity_matched\":%s,\"product_root\":\"%s\","
        "\"root_exists\":%s,\"permit_status\":\"%s\","
        "\"owned_during\":%lu,\"owned_after\":%lu,"
        "\"identity_cleanup\":%s,\"mount_cleanup\":%s,"
        "\"gpio21_stable_high\":%s,\"physical_write_calls\":0}",
        valid ? "valid" : "rejected", expectedFingerprint, cidHex,
        fingerprintMatched ? "true" : "false",
        mountAttempted ? "true" : "false", mounted ? "true" : "false",
        readOnlyGuaranteed ? "true" : "false",
        static_cast<unsigned long>(blockedWrites),
        static_cast<unsigned long long>(cardCapacity),
        static_cast<unsigned long long>(filesystemCapacity),
        static_cast<unsigned long long>(freeBytes),
        capacityMatched ? "true" : "false",
        leshy1::storage::kProductSessionStoreRoot,
        rootExists ? "true" : "false",
        leshy1::storage::productStoreAccessStatusName(permit.status),
        static_cast<unsigned long>(ownedDuring),
        static_cast<unsigned long>(ownedAfter),
        identityCleanup ? "true" : "false",
        mountCleanup ? "true" : "false",
        filesystem.gpio21StableHigh() ? "true" : "false");
    reply.println(line);
}

bool parseWifiPersistCommand(const char* command, char* fingerprint,
                             std::size_t fingerprintCapacity, char* runId,
                             std::size_t runIdCapacity,
                             unsigned* maximumScans) {
    if (command == nullptr || fingerprint == nullptr || runId == nullptr ||
        maximumScans == nullptr || fingerprintCapacity < 33 ||
        runIdCapacity < 33 ||
        std::strncmp(command, kWifiPersistPrefix,
                     std::strlen(kWifiPersistPrefix)) != 0) {
        return false;
    }
    char extra = '\0';
    unsigned parsedMaximumScans = 0;
    const int parsed = std::sscanf(
        command + std::strlen(kWifiPersistPrefix),
        "%32[0-9A-F] %32[A-Za-z0-9_-] %u %c", fingerprint, runId,
        &parsedMaximumScans, &extra);
    if (parsed != 3 || std::strlen(fingerprint) != 32 ||
        runId[0] == '\0' || parsedMaximumScans == 0 ||
        parsedMaximumScans > kWifiPersistMaxScans) {
        return false;
    }
    *maximumScans = parsedMaximumScans;
    return true;
}

bool parseSdSessionResetCommand(const char* command, const char* prefix,
                                char* fingerprint,
                                std::size_t fingerprintCapacity, char* runId,
                                std::size_t runIdCapacity,
                                unsigned* boundaryNumber) {
    if (command == nullptr || prefix == nullptr || fingerprint == nullptr ||
        runId == nullptr || boundaryNumber == nullptr ||
        fingerprintCapacity < 33 || runIdCapacity < 33 ||
        std::strncmp(command, prefix, std::strlen(prefix)) != 0) {
        return false;
    }
    char extra = '\0';
    unsigned parsedBoundary = 0;
    const int parsed = std::sscanf(
        command + std::strlen(prefix),
        "%32[0-9A-F] %32[A-Za-z0-9_-] %u %c", fingerprint, runId,
        &parsedBoundary, &extra);
    if (parsed != 3 || std::strlen(fingerprint) != 32 || runId[0] == '\0' ||
        !leshy1::storage::isSessionStoreBoundary(
            resetBoundaryStage(parsedBoundary))) {
        return false;
    }
    *boundaryNumber = parsedBoundary;
    return true;
}

void emitPhysicalSdSessionResetArm(Stream& reply,
                                   const char* expectedFingerprint,
                                   const char* runId,
                                   unsigned boundaryNumber,
                                   bool physicalPowerCut) {
    auto& line = sdPhysicalEvidence.line;
    auto& cidHex = sdPhysicalEvidence.cidHex;
    cidHex[0] = '\0';
    const leshy1::storage::CommitStage boundary =
        resetBoundaryStage(boundaryNumber);
    const bool idleUi = uiController.isRoot() && !appRuntime.running();
    const bool resourcesAcquired = idleUi && resourceBroker.acquire(
        kSdIdentificationOwner, leshy1::storage::kSdIdentificationResources);
    const std::uint32_t ownedDuring =
        resourceBroker.ownedBy(kSdIdentificationOwner);
    const char* status = "resource_unavailable";
    const bool fixtureReady = idleUi && prepareLittleFsResetFixture();

    BoardSdSpiTransport identityTransport;
    const bool identityAdapterBegun = resourcesAcquired && identityTransport.begin();
    leshy1::storage::SdTransportRunResult identity;
    if (identityAdapterBegun) {
        leshy1::storage::SdTransportRunPolicy policy;
        policy.allowPhysical = true;
        policy.explicitlySelected = true;
        policy.identificationOnly = true;
        policy.ownedResources = ownedDuring;
        identity = leshy1::storage::runSdIdentificationStateMachine(
            leshy1::storage::defaultSdIdentificationPlan(), identityTransport,
            policy);
        identityTransport.end();
    }
    const bool identityCleanup = identityTransport.cleanupComplete();
    for (std::size_t index = 0; index < identity.identity.cid.size(); ++index) {
        std::snprintf(cidHex + index * 2, sizeof(sdPhysicalEvidence.cidHex) - index * 2,
                      "%02X", static_cast<unsigned>(identity.identity.cid[index]));
    }
    const bool fingerprintMatched =
        identity.status == leshy1::storage::SdTransportRunStatus::Valid &&
        std::strcmp(cidHex, expectedFingerprint) == 0;

    char scratchPath[leshy1::storage::kScratchPathMax] = {};
    std::snprintf(scratchPath, sizeof(scratchPath), "%s%s",
                  leshy1::storage::kScratchRoot, runId);
    BoardSdFilesystem filesystem;
    const bool mountAttempted = fingerprintMatched;
    const bool mounted = fingerprintMatched && filesystem.begin();
    const std::uint64_t cardCapacity =
        mounted ? filesystem.cardCapacityBytes() : 0;
    const std::uint64_t filesystemCapacity =
        mounted ? filesystem.filesystemCapacityBytes() : 0;
    const std::uint64_t freeBefore = mounted ? filesystem.freeBytes() : 0;
    const bool capacityMatched = mounted &&
        cardCapacity == identity.identity.capacityBytes &&
        filesystemCapacity != 0 && filesystemCapacity <= cardCapacity;
    const bool scratchPreexisting = mounted && filesystem.exists(scratchPath);

    leshy1::storage::MediaIdentity media;
    media.present = capacityMatched;
    media.kind = leshy1::storage::MediaKind::Sd;
    media.fingerprint = cidHex;
    media.capacityBytes = cardCapacity;
    media.freeBytes = freeBefore;
    leshy1::storage::WriteRequest request;
    request.explicitlyDisposable = true;
    request.expectedFingerprint = expectedFingerprint;
    request.runId = runId;
    request.scratchExists = scratchPreexisting;
    request.requiredBytes = 64U * 1024U;
    request.reserveBytes = 1024U * 1024U;
    const leshy1::storage::WritePermit permit =
        leshy1::storage::authorizeScratchWrite(media, request);

    leshy1::storage::SessionStoreCommitResult initialCommit;
    leshy1::storage::SessionStoreCommitResult interruptedCommit;
    leshy1::storage::SessionStoreRecoveryResult initialRecovery;
    StoredGenerationEvidence priorEvidence;
    bool prepared = false;
    bool scratchCreated = false;
    bool priorUnchanged = false;
    bool resetArmed = false;
    bool boundaryStopped = false;
    bool sequenceValid = false;
    std::size_t boundariesReached = 0;
    std::uint64_t bytesWritten = 0;
    std::uint32_t fileSyncs = 0;
    std::uint32_t directorySyncs = 0;
    const char* ioFailure = "not_started";
    unsigned ioFresult = 0;
    const char* ioFresultName = "not_started";
    std::uint64_t freeAfter = freeBefore;

    if (!leshy1::storage::isSessionStoreBoundary(boundary)) {
        status = "invalid_boundary";
    } else if (!idleUi) {
        status = "ui_not_idle";
    } else if (!fixtureReady) {
        status = "fixture_failed";
    } else if (!resourcesAcquired) {
        status = "resources_unavailable";
    } else if (!identityAdapterBegun) {
        status = "identity_adapter_begin_failed";
    } else if (identity.status != leshy1::storage::SdTransportRunStatus::Valid) {
        status = "identity_failed";
    } else if (!fingerprintMatched) {
        status = "fingerprint_mismatch";
    } else if (!mounted) {
        status = "mount_failed";
    } else if (!capacityMatched) {
        status = "capacity_mismatch";
    } else if (!permit.allowed()) {
        status = "permit_rejected";
    } else {
        ArduinoFsSessionStoreIo io(filesystem.driveNumber(),
                                   sdSessionStoreIoWorkspace);
        prepared = io.prepare(permit);
        scratchCreated = prepared && filesystem.exists(permit.scratchPath);
        if (!prepared || !scratchCreated) {
            status = "scratch_prepare_failed";
        } else {
            initialCommit = leshy1::storage::commitNextSession(
                io, sessionStoreWorkspace, littleFsResetSession);
            initialRecovery = leshy1::storage::recoverSession(
                io, sessionStoreWorkspace,
                &sessionStoreWorkspace.validationSession);
            priorUnchanged = initialCommit.complete() &&
                initialCommit.generation == 1 && initialRecovery.valid() &&
                initialRecovery.generation == 1 &&
                inspectStoredGeneration(io, sessionStoreWorkspace,
                                        littleFsResetSession, 1, &priorEvidence);
            if (!priorUnchanged) {
                status = "initial_generation_failed";
            } else {
                resetArmed = true;
                std::snprintf(
                    line, sizeof(sdPhysicalEvidence.line),
                    "{\"schema\":\"leshy.storage.sd.session_store_reset.v1\","
                    "\"kind\":\"armed\",\"status\":\"ready\","
                    "\"run_id\":\"%s\",\"boundary\":%u,"
                    "\"boundary_name\":\"%s\",\"expected_recovery\":\"%s\","
                    "\"cid_hex\":\"%s\",\"fingerprint_matched\":true,"
                    "\"scratch_path\":\"%s\",\"initial_generation\":1,"
                    "\"initial_observations\":%u,"
                    "\"prior_segment_bytes\":%u,\"prior_segment_crc32c\":%lu,"
                    "\"prior_manifest_bytes\":%u,\"prior_manifest_crc32c\":%lu,"
                    "\"filesystem_driver\":\"esp_idf_sdspi\","
                    "\"filesystem_spi_hz\":%lu,\"format_allowed\":false,"
                    "\"writes_bounded_to_scratch\":true,"
                    "\"reset_injection\":%s,\"physical_power_cut\":%s,"
                    "\"radio_tx_commands\":0}",
                    runId, boundaryNumber,
                    leshy1::storage::sessionStoreBoundaryName(boundary),
                    resetExpectedRecovery(boundaryNumber), cidHex,
                    permit.scratchPath,
                    static_cast<unsigned>(initialRecovery.observations),
                    static_cast<unsigned>(priorEvidence.observedSegmentSize),
                    static_cast<unsigned long>(priorEvidence.observedSegmentCrc),
                    static_cast<unsigned>(priorEvidence.observedManifestSize),
                    static_cast<unsigned long>(priorEvidence.observedManifestCrc),
                    static_cast<unsigned long>(filesystem.realFrequencyHz()),
                    physicalPowerCut ? "false" : "true",
                    physicalPowerCut ? "true" : "false");
                reply.println(line);
                reply.flush();
                ResetBoundaryHookContext hookContext{
                    &reply, runId, boundaryNumber};
                const leshy1::storage::SessionStoreBoundaryHook boundaryHook =
                    physicalPowerCut
                        ? waitForPowerCutAtSessionStoreBoundary
                        : restartAtSessionStoreBoundary;
                leshy1::storage::SessionStoreBoundaryIo injecting(
                    io, boundary, boundaryHook, &hookContext);
                interruptedCommit = leshy1::storage::commitNextSession(
                    injecting, sessionStoreWorkspace, littleFsResetSession);
                boundaryStopped = injecting.stopped();
                sequenceValid = injecting.sequenceValid();
                boundariesReached = injecting.boundariesReached();
                status = physicalPowerCut
                    ? "power_cut_not_triggered" : "reset_not_triggered";
            }
        }
        bytesWritten = io.bytesWritten();
        fileSyncs = io.fileSyncs();
        directorySyncs = io.directorySyncs();
        ioFailure = io.lastFailure();
        ioFresult = io.lastFresult();
        ioFresultName = io.lastFresultName();
        io.end();
        freeAfter = filesystem.freeBytes();
    }

    if (mountAttempted) filesystem.end();
    resourceBroker.releaseAll(kSdIdentificationOwner);
    const std::uint32_t ownedAfter =
        resourceBroker.ownedBy(kSdIdentificationOwner);
    const bool cleanupComplete = identityCleanup &&
        (!mountAttempted || filesystem.cleanupComplete()) && ownedAfter == 0;
    std::snprintf(
        line, sizeof(sdPhysicalEvidence.line),
        "{\"schema\":\"leshy.storage.sd.session_store_reset.v1\","
        "\"kind\":\"result\",\"mode\":\"arm\",\"status\":\"%s\","
        "\"run_id\":\"%s\",\"boundary\":%u,\"boundary_name\":\"%s\","
        "\"expected_recovery\":\"%s\",\"permit_status\":\"%s\","
        "\"cid_hex\":\"%s\",\"fingerprint_matched\":%s,"
        "\"scratch_path\":\"%s\",\"scratch_preexisting\":%s,"
        "\"scratch_created\":%s,\"reset_armed\":%s,"
        "\"boundary_stopped\":%s,\"sequence_valid\":%s,"
        "\"boundaries_reached\":%u,\"initial_commit_status\":\"%s\","
        "\"interrupted_commit_status\":\"%s\","
        "\"interrupted_commit_stage\":\"%s\",\"prior_unchanged\":%s,"
        "\"bytes_written\":%llu,\"file_syncs\":%lu,"
        "\"directory_syncs\":%lu,\"io_failure\":\"%s\","
        "\"io_fresult\":%u,\"io_fresult_name\":\"%s\","
        "\"card_capacity_bytes\":%llu,\"filesystem_capacity_bytes\":%llu,"
        "\"free_before\":%llu,\"free_after\":%llu,"
        "\"mounted\":%s,\"resource_acquired\":%s,"
        "\"owned_during\":%lu,\"owned_after\":%lu,"
        "\"cleanup_complete\":%s,\"format_allowed\":false,"
        "\"existing_paths_deleted\":false,\"reset_injection\":%s,"
        "\"physical_power_cut\":%s,\"radio_tx_commands\":0}",
        status, runId, boundaryNumber,
        leshy1::storage::sessionStoreBoundaryName(boundary),
        resetExpectedRecovery(boundaryNumber),
        leshy1::storage::permitStatusName(permit.status), cidHex,
        fingerprintMatched ? "true" : "false",
        permit.allowed() ? permit.scratchPath : scratchPath,
        scratchPreexisting ? "true" : "false",
        scratchCreated ? "true" : "false", resetArmed ? "true" : "false",
        boundaryStopped ? "true" : "false",
        sequenceValid ? "true" : "false",
        static_cast<unsigned>(boundariesReached),
        leshy1::storage::sessionStoreStatusName(initialCommit.status),
        leshy1::storage::sessionStoreStatusName(interruptedCommit.status),
        leshy1::storage::sessionStoreBoundaryName(interruptedCommit.stage),
        priorUnchanged ? "true" : "false",
        static_cast<unsigned long long>(bytesWritten),
        static_cast<unsigned long>(fileSyncs),
        static_cast<unsigned long>(directorySyncs), ioFailure, ioFresult,
        ioFresultName, static_cast<unsigned long long>(cardCapacity),
        static_cast<unsigned long long>(filesystemCapacity),
        static_cast<unsigned long long>(freeBefore),
        static_cast<unsigned long long>(freeAfter),
        mounted ? "true" : "false", resourcesAcquired ? "true" : "false",
        static_cast<unsigned long>(ownedDuring),
        static_cast<unsigned long>(ownedAfter),
        cleanupComplete ? "true" : "false",
        physicalPowerCut ? "false" : "true",
        physicalPowerCut ? "true" : "false");
    reply.println(line);
}

void emitPhysicalSdSessionResetRecovery(Stream& reply,
                                        const char* expectedFingerprint,
                                        const char* runId,
                                        unsigned boundaryNumber,
                                        bool physicalPowerCut) {
    auto& line = sdPhysicalEvidence.line;
    auto& cidHex = sdPhysicalEvidence.cidHex;
    cidHex[0] = '\0';
    const leshy1::storage::CommitStage boundary =
        resetBoundaryStage(boundaryNumber);
    const esp_reset_reason_t resetReason = esp_reset_reason();
    const bool softwareReset = resetReason == ESP_RST_SW;
    const bool powerOnReset = resetReason == ESP_RST_POWERON;
    const bool expectedReset = physicalPowerCut ? powerOnReset : softwareReset;
    const bool idleUi = uiController.isRoot() && !appRuntime.running();
    const bool fixtureReady = idleUi && prepareLittleFsResetFixture();
    const bool resourcesAcquired = idleUi && resourceBroker.acquire(
        kSdIdentificationOwner, leshy1::storage::kSdIdentificationResources);
    const std::uint32_t ownedDuring =
        resourceBroker.ownedBy(kSdIdentificationOwner);

    BoardSdSpiTransport identityTransport;
    const bool identityAdapterBegun = resourcesAcquired && identityTransport.begin();
    leshy1::storage::SdTransportRunResult identity;
    if (identityAdapterBegun) {
        leshy1::storage::SdTransportRunPolicy policy;
        policy.allowPhysical = true;
        policy.explicitlySelected = true;
        policy.identificationOnly = true;
        policy.ownedResources = ownedDuring;
        identity = leshy1::storage::runSdIdentificationStateMachine(
            leshy1::storage::defaultSdIdentificationPlan(), identityTransport,
            policy);
        identityTransport.end();
    }
    const bool identityCleanup = identityTransport.cleanupComplete();
    for (std::size_t index = 0; index < identity.identity.cid.size(); ++index) {
        std::snprintf(cidHex + index * 2, sizeof(sdPhysicalEvidence.cidHex) - index * 2,
                      "%02X", static_cast<unsigned>(identity.identity.cid[index]));
    }
    const bool fingerprintMatched =
        identity.status == leshy1::storage::SdTransportRunStatus::Valid &&
        std::strcmp(cidHex, expectedFingerprint) == 0;

    char scratchPath[leshy1::storage::kScratchPathMax] = {};
    std::snprintf(scratchPath, sizeof(scratchPath), "%s%s",
                  leshy1::storage::kScratchRoot, runId);
    BoardSdFilesystem filesystem;
    const bool mountAttempted = fingerprintMatched;
    const bool mounted = fingerprintMatched && filesystem.begin();
    const std::uint64_t cardCapacity =
        mounted ? filesystem.cardCapacityBytes() : 0;
    const std::uint64_t filesystemCapacity =
        mounted ? filesystem.filesystemCapacityBytes() : 0;
    const std::uint64_t freeBytes = mounted ? filesystem.freeBytes() : 0;
    const std::uint32_t actualFilesystemSpiHz =
        mounted ? filesystem.realFrequencyHz() : 0;
    const bool capacityMatched = mounted &&
        cardCapacity == identity.identity.capacityBytes &&
        filesystemCapacity != 0 && filesystemCapacity <= cardCapacity;
    const bool scratchExists = mounted && filesystem.exists(scratchPath);

    leshy1::storage::MediaIdentity media;
    media.present = capacityMatched;
    media.kind = leshy1::storage::MediaKind::Sd;
    media.fingerprint = cidHex;
    media.capacityBytes = cardCapacity;
    media.freeBytes = freeBytes;
    leshy1::storage::ExistingScratchReadRequest request;
    request.explicitlySelected = true;
    request.expectedFingerprint = expectedFingerprint;
    request.runId = runId;
    request.scratchExists = scratchExists;
    const leshy1::storage::ReadPermit permit =
        leshy1::storage::authorizeExistingScratchRead(media, request);

    leshy1::storage::SessionStoreRecoveryResult recovery;
    StoredGenerationEvidence priorEvidence;
    bool openedReadOnly = false;
    bool priorUnchanged = false;
    std::uint64_t bytesWritten = 0;
    std::uint32_t fileSyncs = 0;
    std::uint32_t directorySyncs = 0;
    const char* ioFailure = "not_started";
    unsigned ioFresult = 0;
    const char* ioFresultName = "not_started";
    if (permit.allowed()) {
        ArduinoFsSessionStoreIo io(filesystem.driveNumber(),
                                   sdSessionStoreIoWorkspace);
        openedReadOnly = io.openExistingReadOnly(permit);
        if (openedReadOnly) {
            priorUnchanged = inspectStoredGeneration(
                io, sessionStoreWorkspace, littleFsResetSession, 1,
                &priorEvidence);
            recovery = leshy1::storage::recoverSession(
                io, sessionStoreWorkspace,
                &sessionStoreWorkspace.validationSession);
        }
        bytesWritten = io.bytesWritten();
        fileSyncs = io.fileSyncs();
        directorySyncs = io.directorySyncs();
        ioFailure = io.lastFailure();
        ioFresult = io.lastFresult();
        ioFresultName = io.lastFresultName();
        io.end();
    }

    if (mountAttempted) filesystem.end();
    resourceBroker.releaseAll(kSdIdentificationOwner);
    const std::uint32_t ownedAfter =
        resourceBroker.ownedBy(kSdIdentificationOwner);
    const bool cleanupComplete = identityCleanup &&
        (!mountAttempted || filesystem.cleanupComplete()) && ownedAfter == 0;
    const bool generationAllowed = recovery.valid() &&
        resetRecoveredGenerationAllowed(boundaryNumber, recovery.generation);
    const bool valid = leshy1::storage::isSessionStoreBoundary(boundary) &&
        expectedReset && fixtureReady && identityAdapterBegun &&
        fingerprintMatched && mounted &&
        capacityMatched && permit.allowed() && openedReadOnly &&
        generationAllowed && recovery.observations == 3 && priorUnchanged &&
        bytesWritten == 0 && fileSyncs == 0 && directorySyncs == 0 &&
        cleanupComplete;

    std::snprintf(
        line, sizeof(sdPhysicalEvidence.line),
        "{\"schema\":\"leshy.storage.sd.session_store_reset.v1\","
        "\"kind\":\"result\",\"mode\":\"recovery\","
        "\"status\":\"%s\",\"run_id\":\"%s\",\"boundary\":%u,"
        "\"boundary_name\":\"%s\",\"expected_recovery\":\"%s\","
        "\"reset_reason_code\":%u,\"software_reset\":%s,"
        "\"power_on_reset\":%s,"
        "\"identity_status\":\"%s\",\"cid_hex\":\"%s\","
        "\"fingerprint_matched\":%s,\"read_permit_status\":\"%s\","
        "\"scratch_path\":\"%s\",\"scratch_exists\":%s,"
        "\"opened_read_only\":%s,\"session_store_io_writable\":false,"
        "\"recovery_status\":\"%s\",\"recovered_generation\":%lu,"
        "\"generation_allowed\":%s,\"reopened_observations\":%u,"
        "\"a_status\":%u,\"b_status\":%u,\"prior_unchanged\":%s,"
        "\"prior_segment_bytes\":%u,\"prior_segment_crc32c\":%lu,"
        "\"prior_manifest_bytes\":%u,\"prior_manifest_crc32c\":%lu,"
        "\"bytes_written\":%llu,\"file_syncs\":%lu,"
        "\"directory_syncs\":%lu,\"io_failure\":\"%s\","
        "\"io_fresult\":%u,\"io_fresult_name\":\"%s\","
        "\"filesystem_driver\":\"esp_idf_sdspi\","
        "\"filesystem_spi_hz\":%lu,\"card_capacity_bytes\":%llu,"
        "\"filesystem_capacity_bytes\":%llu,\"mounted\":%s,"
        "\"owned_during\":%lu,\"owned_after\":%lu,"
        "\"cleanup_complete\":%s,\"mount_on_boot\":false,"
        "\"format_allowed\":false,\"existing_paths_deleted\":false,"
        "\"user_file_names_listed\":false,\"user_file_data_read\":false,"
        "\"reset_injection\":%s,\"physical_power_cut\":%s,"
        "\"radio_tx_commands\":0}",
        valid ? "valid" : "failed", runId, boundaryNumber,
        leshy1::storage::sessionStoreBoundaryName(boundary),
        resetExpectedRecovery(boundaryNumber),
        static_cast<unsigned>(resetReason), softwareReset ? "true" : "false",
        powerOnReset ? "true" : "false",
        leshy1::storage::sdTransportRunStatusName(identity.status), cidHex,
        fingerprintMatched ? "true" : "false",
        leshy1::storage::readPermitStatusName(permit.status),
        permit.allowed() ? permit.scratchPath : scratchPath,
        scratchExists ? "true" : "false", openedReadOnly ? "true" : "false",
        leshy1::storage::sessionStoreStatusName(recovery.status),
        static_cast<unsigned long>(recovery.generation),
        generationAllowed ? "true" : "false",
        static_cast<unsigned>(recovery.observations),
        static_cast<unsigned>(recovery.aStatus),
        static_cast<unsigned>(recovery.bStatus),
        priorUnchanged ? "true" : "false",
        static_cast<unsigned>(priorEvidence.observedSegmentSize),
        static_cast<unsigned long>(priorEvidence.observedSegmentCrc),
        static_cast<unsigned>(priorEvidence.observedManifestSize),
        static_cast<unsigned long>(priorEvidence.observedManifestCrc),
        static_cast<unsigned long long>(bytesWritten),
        static_cast<unsigned long>(fileSyncs),
        static_cast<unsigned long>(directorySyncs), ioFailure, ioFresult,
        ioFresultName, static_cast<unsigned long>(actualFilesystemSpiHz),
        static_cast<unsigned long long>(cardCapacity),
        static_cast<unsigned long long>(filesystemCapacity),
        mounted ? "true" : "false", static_cast<unsigned long>(ownedDuring),
        static_cast<unsigned long>(ownedAfter),
        cleanupComplete ? "true" : "false",
        physicalPowerCut ? "false" : "true",
        physicalPowerCut ? "true" : "false");
    reply.println(line);
}

struct WifiQueueSinkContext final {
    leshy1::services::survey::ObservationQueue* queue = nullptr;
    std::uint64_t oldestObservationUs = 0;
};

WifiRecordDisposition collectWifiQueueRecord(
    const WifiScanRecord& record, std::uint64_t monotonicUs,
    void* rawContext) {
    auto* context = static_cast<WifiQueueSinkContext*>(rawContext);
    if (context == nullptr || context->queue == nullptr) {
        return WifiRecordDisposition::Rejected;
    }
    Observation observation;
    if (!leshy1::drivers::wifi::normalizePassiveRecord(
            record, monotonicUs, &observation)) {
        return WifiRecordDisposition::Rejected;
    }
    if (!context->queue->push(observation)) {
        return WifiRecordDisposition::Dropped;
    }
    if (context->oldestObservationUs == 0 ||
        monotonicUs < context->oldestObservationUs) {
        context->oldestObservationUs = monotonicUs;
    }
    return WifiRecordDisposition::Accepted;
}

void emitProductStoreBootstrap(Stream& reply,
                               const char* expectedFingerprint) {
    auto& line = sdPhysicalEvidence.line;
    auto& cidHex = sdPhysicalEvidence.cidHex;
    cidHex[0] = '\0';
    const bool idleUi = uiController.isRoot() && !appRuntime.running();
    const leshy1::kernel::runtime::ResourceMask requestedResources =
        leshy1::storage::kSdIdentificationResources |
        leshy1::kernel::runtime::resourceMask(Resource::EspRf);
    const bool resourcesAcquired = idleUi && resourceBroker.acquire(
        kSdIdentificationOwner, requestedResources);
    const std::uint32_t ownedDuring =
        resourceBroker.ownedBy(kSdIdentificationOwner);

    BoardSdSpiTransport identityTransport;
    const bool identityBegun = resourcesAcquired && identityTransport.begin();
    leshy1::storage::SdTransportRunResult identity;
    if (identityBegun) {
        leshy1::storage::SdTransportRunPolicy policy;
        policy.allowPhysical = true;
        policy.explicitlySelected = true;
        policy.identificationOnly = true;
        policy.ownedResources = ownedDuring;
        identity = leshy1::storage::runSdIdentificationStateMachine(
            leshy1::storage::defaultSdIdentificationPlan(), identityTransport,
            policy);
        identityTransport.end();
    }
    const bool identityCleanup = identityTransport.cleanupComplete();
    formatCidFingerprint(identity.identity, cidHex,
                         sizeof(sdPhysicalEvidence.cidHex));
    const bool fingerprintMatched =
        identity.status == leshy1::storage::SdTransportRunStatus::Valid &&
        std::strcmp(cidHex, expectedFingerprint) == 0;

    BoardSdFilesystem filesystem;
    const bool mounted = fingerprintMatched && filesystem.begin();
    const std::uint64_t cardCapacity =
        mounted ? filesystem.cardCapacityBytes() : 0;
    const std::uint64_t filesystemCapacity =
        mounted ? filesystem.filesystemCapacityBytes() : 0;
    const std::uint64_t freeBefore = mounted ? filesystem.freeBytes() : 0;
    const bool capacityMatched = mounted &&
        cardCapacity == identity.identity.capacityBytes &&
        filesystemCapacity != 0 && filesystemCapacity <= cardCapacity;
    const bool rootExisted = mounted && filesystem.exists(
        leshy1::storage::kProductSessionStoreRoot);

    leshy1::storage::MediaIdentity media;
    media.present = capacityMatched;
    media.kind = leshy1::storage::MediaKind::Sd;
    media.fingerprint = cidHex;
    media.capacityBytes = cardCapacity;
    media.freeBytes = freeBefore;
    leshy1::storage::ProductStoreRequest request;
    request.operation = rootExisted
        ? leshy1::storage::ProductStoreOperation::CommitSession
        : leshy1::storage::ProductStoreOperation::InitializeStore;
    request.explicitlySelected = true;
    request.expectedFingerprint = expectedFingerprint;
    request.rootPath = leshy1::storage::kProductSessionStoreRoot;
    request.rootExists = rootExisted;
    request.driverWriteEnabled = true;
    request.requiredBytes = 64U * 1024U;
    request.reserveBytes = 1024U * 1024U;
    request.ownedResources = ownedDuring;
    const leshy1::storage::ProductStorePermit permit =
        leshy1::storage::authorizeProductStore(media, request);

    ArduinoFsSessionStoreIo io(filesystem.driveNumber(),
                               sdSessionStoreIoWorkspace);
    const bool opened = permit.allowed() &&
        (rootExisted ? io.openExistingWritable(permit) : io.prepare(permit));
    const bool rootCreated = !rootExisted && opened && filesystem.exists(
        leshy1::storage::kProductSessionStoreRoot);

    BoardWifiPassiveScanner scanner;
    const leshy1::drivers::wifi::WifiScanPlan wifiPlan =
        leshy1::drivers::wifi::defaultPassivePlan();
    std::uint64_t startedUs = static_cast<std::uint64_t>(esp_timer_get_time());
    if (startedUs == 0) startedUs = 1;
    surveyIngressQueue.reset();
    surveySession.reset();
    const bool scannerBegun = opened &&
        leshy1::drivers::wifi::validatePassivePlan(wifiPlan) &&
        surveySession.start("product-wifi-boot", startedUs) ==
            SessionStatus::Started && scanner.begin();
    WifiQueueSinkContext sink{&surveyIngressQueue, 0};
    BoardWifiPassiveScanResult scan;
    if (scannerBegun) scan = scanner.scan(wifiPlan, collectWifiQueueRecord, &sink);
    Observation observation;
    std::uint32_t appendDropped = 0;
    while (surveyIngressQueue.pop(&observation)) {
        if (surveySession.append(observation) != SessionStatus::Appended) {
            ++appendDropped;
        }
    }
    std::uint64_t stoppedUs = static_cast<std::uint64_t>(esp_timer_get_time());
    if (stoppedUs < startedUs) stoppedUs = startedUs;
    const bool stopped = scan.valid() && scan.accepted != 0 &&
        scan.dropped == 0 && appendDropped == 0 &&
        surveySession.stop(stoppedUs) == SessionStatus::Stopped;
    const bool scannerCleanup = scanner.end() && scanner.cleanupComplete();
    const std::uint32_t queueHighWater = surveyIngressQueue.highWater();
    const std::uint32_t queueDropped = surveyIngressQueue.dropped();
    surveyIngressQueue.reset();

    leshy1::storage::SessionStoreCommitResult commit;
    leshy1::apps::library::SessionCatalogResult cataloged;
    if (stopped && scannerCleanup && queueDropped == 0) {
        commit = leshy1::storage::commitNextSession(
            io, sessionStoreWorkspace, surveySession);
        if (commit.complete()) {
            cataloged = sessionCatalog.recoverLatest(
                io, sessionStoreWorkspace, librarySession, libraryController,
                true, false);
        }
    }
    const std::uint64_t bytesWritten = io.bytesWritten();
    const std::uint32_t fileSyncs = io.fileSyncs();
    const std::uint32_t directorySyncs = io.directorySyncs();
    const char* ioFailure = io.lastFailure();
    const char* ioResult = io.lastFresultName();
    io.end();
    if (fingerprintMatched) filesystem.end();
    const bool filesystemCleanup =
        !fingerprintMatched || filesystem.cleanupComplete();
    resourceBroker.releaseAll(kSdIdentificationOwner);
    const std::uint32_t ownedAfter =
        resourceBroker.ownedBy(kSdIdentificationOwner);
    const bool enrollmentSaved = cataloged.admitted() &&
        saveProductFingerprint(expectedFingerprint);
    const bool valid = idleUi && resourcesAcquired && identityBegun &&
        identityCleanup && fingerprintMatched && mounted && capacityMatched &&
        permit.allowed() && opened && (rootExisted || rootCreated) &&
        scannerBegun && stopped && scannerCleanup && queueDropped == 0 &&
        appendDropped == 0 && commit.complete() && cataloged.admitted() &&
        bytesWritten != 0 && fileSyncs != 0 && directorySyncs != 0 &&
        filesystemCleanup && ownedAfter == 0 && enrollmentSaved;

    surveyDemoReady = prepareSurveyDemo();
    if (valid) {
        libraryDemoReady = true;
        const CapabilityRecord* persistentCapability =
            inventory.find("library.persistent_session");
        if (persistentCapability == nullptr) {
            inventory.add({"library.persistent_session",
                           CapabilityState::Available,
                           "explicit_product_bootstrap",
                           "validated_session_open"});
        }
        appCatalog.rebuild(inventory);
        renderInteractiveScreen();
    }

    std::snprintf(
        line, sizeof(sdPhysicalEvidence.line),
        "{\"schema\":\"leshy.storage.product_bootstrap.v1\","
        "\"kind\":\"result\",\"status\":\"%s\","
        "\"expected_fingerprint\":\"%s\",\"cid_hex\":\"%s\","
        "\"fingerprint_matched\":%s,\"mounted_writable\":%s,"
        "\"explicitly_selected\":true,\"format_allowed\":false,"
        "\"product_root\":\"%s\",\"root_existed\":%s,"
        "\"root_created\":%s,\"operation\":\"%s\","
        "\"permit_status\":\"%s\",\"opened\":%s,"
        "\"wifi_scan_status\":\"%s\",\"wifi_records\":%u,"
        "\"observations\":%u,\"queue_high_water\":%lu,"
        "\"queue_drops\":%lu,\"append_drops\":%lu,"
        "\"commit_status\":\"%s\",\"generation\":%lu,"
        "\"catalog_status\":\"%s\",\"catalog_admitted\":%s,"
        "\"bytes_written\":%llu,\"file_syncs\":%lu,"
        "\"directory_syncs\":%lu,\"io_failure\":\"%s\","
        "\"io_result\":\"%s\",\"enrollment_saved\":%s,"
        "\"owned_during\":%lu,\"owned_after\":%lu,"
        "\"identity_cleanup\":%s,\"scanner_cleanup\":%s,"
        "\"filesystem_cleanup\":%s,\"radio_connect_calls\":0,"
        "\"application_raw_tx_calls\":0}",
        valid ? "valid" : "failed", expectedFingerprint, cidHex,
        fingerprintMatched ? "true" : "false", mounted ? "true" : "false",
        leshy1::storage::kProductSessionStoreRoot,
        rootExisted ? "true" : "false", rootCreated ? "true" : "false",
        leshy1::storage::productStoreOperationName(request.operation),
        leshy1::storage::productStoreAccessStatusName(permit.status),
        opened ? "true" : "false",
        leshy1::platform::arduino::boardWifiScanStatusName(scan.status),
        static_cast<unsigned>(scan.recordsRead),
        static_cast<unsigned>(cataloged.observations),
        static_cast<unsigned long>(queueHighWater),
        static_cast<unsigned long>(queueDropped),
        static_cast<unsigned long>(appendDropped),
        leshy1::storage::sessionStoreStatusName(commit.status),
        static_cast<unsigned long>(commit.generation),
        leshy1::apps::library::sessionCatalogStatusName(cataloged.status),
        cataloged.admitted() ? "true" : "false",
        static_cast<unsigned long long>(bytesWritten),
        static_cast<unsigned long>(fileSyncs),
        static_cast<unsigned long>(directorySyncs), ioFailure, ioResult,
        enrollmentSaved ? "true" : "false",
        static_cast<unsigned long>(ownedDuring),
        static_cast<unsigned long>(ownedAfter),
        identityCleanup ? "true" : "false",
        scannerCleanup ? "true" : "false",
        filesystemCleanup ? "true" : "false");
    reply.println(line);
}

void emitPhysicalSdSessionStore(Stream& reply, const char* expectedFingerprint,
                                const char* runId, bool throughput,
                                bool batchThroughput, bool realWifiPipeline,
                                unsigned maximumWifiScans) {
    auto& line = sdPhysicalEvidence.line;
    auto& cidHex = sdPhysicalEvidence.cidHex;
    auto& commitUs = sdPhysicalEvidence.commitUs;
    commitUs.fill(0);
    cidHex[0] = '\0';
    std::size_t fixtureSegmentBytes = 0;
    const bool batchFixtureReady =
        !batchThroughput ||
        prepareBatchThroughputSession(&fixtureSegmentBytes);
    std::size_t fixtureObservations = librarySession.size();
    const bool idleUi = uiController.isRoot() && !appRuntime.running();
    const leshy1::kernel::runtime::ResourceMask requestedResources =
        leshy1::storage::kSdIdentificationResources |
        (realWifiPipeline
             ? leshy1::kernel::runtime::resourceMask(Resource::EspRf)
             : 0U);
    const bool resourcesAcquired = batchFixtureReady && idleUi &&
        resourceBroker.acquire(
            kSdIdentificationOwner, requestedResources);
    const std::uint32_t ownedDuring =
        resourceBroker.ownedBy(kSdIdentificationOwner);
    const char* status = "resource_unavailable";

    BoardSdSpiTransport identityTransport;
    const bool identityAdapterBegun = resourcesAcquired && identityTransport.begin();
    leshy1::storage::SdTransportRunResult identity;
    if (identityAdapterBegun) {
        leshy1::storage::SdTransportRunPolicy identityPolicy;
        identityPolicy.allowPhysical = true;
        identityPolicy.explicitlySelected = true;
        identityPolicy.identificationOnly = true;
        identityPolicy.ownedResources = ownedDuring;
        identity = leshy1::storage::runSdIdentificationStateMachine(
            leshy1::storage::defaultSdIdentificationPlan(), identityTransport,
            identityPolicy);
        identityTransport.end();
    }
    const bool identityCleanup = identityTransport.cleanupComplete();
    for (std::size_t index = 0; index < identity.identity.cid.size(); ++index) {
        std::snprintf(cidHex + index * 2, sizeof(cidHex) - index * 2, "%02X",
                      static_cast<unsigned>(identity.identity.cid[index]));
    }
    const bool fingerprintMatched =
        identity.status == leshy1::storage::SdTransportRunStatus::Valid &&
        std::strcmp(cidHex, expectedFingerprint) == 0;

    char scratchPath[leshy1::storage::kScratchPathMax] = {};
    std::snprintf(scratchPath, sizeof(scratchPath), "%s%s",
                  leshy1::storage::kScratchRoot, runId);
    BoardSdFilesystem primaryFilesystem;
    const std::uint64_t mountStartedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    const bool primaryMountAttempted = fingerprintMatched;
    const bool mounted = fingerprintMatched && primaryFilesystem.begin();
    const int filesystemMountError = primaryFilesystem.mountError();
    const std::uint32_t actualFilesystemSpiHz =
        primaryFilesystem.realFrequencyHz();
    const std::uint64_t mountUs = mounted
        ? static_cast<std::uint64_t>(esp_timer_get_time()) - mountStartedUs : 0;
    const std::uint64_t cardCapacity =
        mounted ? primaryFilesystem.cardCapacityBytes() : 0;
    const std::uint64_t filesystemCapacity =
        mounted ? primaryFilesystem.filesystemCapacityBytes() : 0;
    const std::uint64_t freeBefore =
        mounted ? primaryFilesystem.freeBytes() : 0;
    const bool capacityMatched = mounted &&
        cardCapacity == identity.identity.capacityBytes &&
        filesystemCapacity != 0 && filesystemCapacity <= cardCapacity;
    const bool scratchPreexisting =
        mounted && primaryFilesystem.exists(scratchPath);

    leshy1::storage::MediaIdentity media;
    media.present = capacityMatched;
    media.kind = leshy1::storage::MediaKind::Sd;
    media.fingerprint = cidHex;
    media.capacityBytes = cardCapacity;
    media.freeBytes = freeBefore;
    leshy1::storage::WriteRequest request;
    request.explicitlyDisposable = true;
    request.expectedFingerprint = expectedFingerprint;
    request.runId = runId;
    request.scratchExists = scratchPreexisting;
    // Thirty-two immutable generations can consume one FAT allocation cluster
    // per small file. Bound the physical experiment to 4 MiB even though its
    // logical payload is much smaller; the normal two-commit probe stays 64 KiB.
    request.requiredBytes = throughput ? 4U * 1024U * 1024U : 64U * 1024U;
    request.reserveBytes = 1024U * 1024U;
    const leshy1::storage::WritePermit permit =
        leshy1::storage::authorizeScratchWrite(media, request);

    leshy1::storage::SessionStoreCommitResult commitOne;
    leshy1::storage::SessionStoreCommitResult commitTwo;
    leshy1::storage::SessionStoreRecoveryResult recoveryBeforeRemount;
    leshy1::storage::SessionStoreRecoveryResult recoveryAfterRemount;
    std::uint64_t commitOneUs = 0;
    std::uint64_t commitTwoUs = 0;
    std::size_t commitsRequested = throughput ? kSdThroughputSamples : 2U;
    std::size_t commitsCompleted = 0;
    std::uint64_t bytesWritten = 0;
    std::uint32_t fileSyncs = 0;
    std::uint32_t directorySyncs = 0;
    const char* ioFailure = "not_started";
    int ioErrno = 0;
    unsigned ioFresult = 0;
    const char* ioFresultName = "not_started";
    bool prepared = false;
    bool fatFileSyncCoversDirectory = false;
    bool scratchCreated = false;
    bool remounted = false;
    bool reopenedReadOnly = false;
    bool primaryCleanup = false;
    bool remountCleanup = false;
    bool wifiScannerBegun = false;
    bool wifiScannerCleanup = !realWifiPipeline;
    unsigned wifiScansCompleted = 0;
    std::uint64_t wifiRecordsRead = 0;
    std::uint64_t wifiRecordsAccepted = 0;
    std::uint64_t wifiRecordsRejected = 0;
    std::uint64_t wifiRecordsDropped = 0;
    std::size_t queueHighWater = 0;
    std::uint64_t queuePushed = 0;
    std::uint64_t queuePopped = 0;
    std::uint64_t queueDropped = 0;
    std::uint64_t sessionAppendDropped = 0;
    leshy1::services::survey::SessionBatchTrigger pipelineTrigger =
        leshy1::services::survey::SessionBatchTrigger::None;
    const char* pipelineStopReason = realWifiPipeline ? "not_started"
                                                      : "not_applicable";
    std::uint64_t freeAfter = freeBefore;
    const std::uint32_t heapFreeBefore = ESP.getFreeHeap();

    if (!batchFixtureReady) {
        status = "batch_fixture_prepare_failed";
    } else if (!idleUi) {
        status = "ui_not_idle";
    } else if (!resourcesAcquired) {
        status = "resources_unavailable";
    } else if (!identityAdapterBegun) {
        status = "identity_adapter_begin_failed";
    } else if (identity.status != leshy1::storage::SdTransportRunStatus::Valid) {
        status = "identity_failed";
    } else if (!fingerprintMatched) {
        status = "fingerprint_mismatch";
    } else if (!mounted) {
        status = "mount_failed";
    } else if (!capacityMatched) {
        status = "capacity_mismatch";
    } else if (!permit.allowed()) {
        status = "permit_rejected";
    } else {
        ArduinoFsSessionStoreIo io(primaryFilesystem.driveNumber(),
                                   sdSessionStoreIoWorkspace);
        prepared = io.prepare(permit);
        scratchCreated = prepared && primaryFilesystem.exists(permit.scratchPath);
        if (!prepared || !scratchCreated) {
            status = "scratch_prepare_failed";
        } else if (realWifiPipeline) {
            commitsRequested = 1;
            surveyIngressQueue.reset();
            librarySession.reset();
            std::uint64_t sessionStartedUs =
                static_cast<std::uint64_t>(esp_timer_get_time());
            if (sessionStartedUs == 0) sessionStartedUs = 1;
            const leshy1::drivers::wifi::WifiScanPlan wifiPlan =
                leshy1::drivers::wifi::defaultPassivePlan();
            BoardSdSpiTransport::holdRadioTransmitPathsInactive();
            BoardWifiPassiveScanner scanner;
            wifiScannerBegun =
                leshy1::drivers::wifi::validatePassivePlan(wifiPlan) &&
                librarySession.start("wifi-persist-e2e", sessionStartedUs) ==
                    SessionStatus::Started &&
                scanner.begin();
            bool pipelineCommitted = false;
            status = wifiScannerBegun ? "pipeline_running"
                                      : "wifi_scanner_begin_failed";
            WifiQueueSinkContext sink{&surveyIngressQueue, 0};
            const leshy1::services::survey::SessionBatchPolicy batchPolicy;
            for (unsigned sample = 0;
                 wifiScannerBegun && sample < maximumWifiScans; ++sample) {
                const BoardWifiPassiveScanResult scan =
                    scanner.scan(wifiPlan, collectWifiQueueRecord, &sink);
                if (!scan.valid()) {
                    status = "wifi_scan_failed";
                    break;
                }
                ++wifiScansCompleted;
                wifiRecordsRead += scan.recordsRead;
                wifiRecordsAccepted += scan.accepted;
                wifiRecordsRejected += scan.rejected;
                wifiRecordsDropped += scan.dropped;

                Observation observation;
                while (surveyIngressQueue.pop(&observation)) {
                    const SessionStatus appended =
                        librarySession.append(observation);
                    if (appended != SessionStatus::Appended) {
                        ++sessionAppendDropped;
                    }
                    observation = Observation{};
                }

                std::uint64_t nowUs =
                    static_cast<std::uint64_t>(esp_timer_get_time());
                if (nowUs < sessionStartedUs) nowUs = sessionStartedUs;
                surveySession = librarySession;
                if (surveySession.stop(nowUs) != SessionStatus::Stopped) {
                    status = "pipeline_snapshot_stop_failed";
                    break;
                }
                std::size_t segmentBytes = 0;
                if (leshy1::storage::encodeObservationSegment(
                        surveySession, sessionStoreWorkspace.segment.data(),
                        sessionStoreWorkspace.segment.size(), &segmentBytes) !=
                    leshy1::storage::SessionCodecStatus::Valid) {
                    status = "pipeline_snapshot_encode_failed";
                    break;
                }
                const bool scanBudgetReached =
                    wifiScansCompleted >= maximumWifiScans;
                pipelineTrigger =
                    leshy1::services::survey::sessionBatchTrigger(
                        batchPolicy, librarySession.size(), segmentBytes,
                        sink.oldestObservationUs, nowUs, scanBudgetReached,
                        false);
                if (pipelineTrigger ==
                    leshy1::services::survey::SessionBatchTrigger::None) {
                    continue;
                }

                pipelineStopReason =
                    leshy1::services::survey::sessionBatchTriggerName(
                        pipelineTrigger);
                fixtureSegmentBytes = segmentBytes;
                fixtureObservations = surveySession.size();
                librarySession.stop(nowUs);
                const std::uint64_t commitStarted =
                    static_cast<std::uint64_t>(esp_timer_get_time());
                commitOne = leshy1::storage::commitNextSession(
                    io, sessionStoreWorkspace, surveySession);
                commitOneUs =
                    static_cast<std::uint64_t>(esp_timer_get_time()) -
                    commitStarted;
                commitUs[0] = commitOneUs;
                if (!commitOne.complete()) {
                    status = "pipeline_commit_failed";
                    break;
                }
                commitsCompleted = 1;
                pipelineCommitted = true;
                status = "pipeline_committed";
                break;
            }
            const bool scannerEnded = scanner.end();
            wifiScannerCleanup = scannerEnded && scanner.cleanupComplete();
            queueHighWater = surveyIngressQueue.highWater();
            queuePushed = surveyIngressQueue.pushed();
            queuePopped = surveyIngressQueue.popped();
            queueDropped = surveyIngressQueue.dropped();
            surveyIngressQueue.reset();

            if (pipelineCommitted && wifiScannerCleanup &&
                wifiRecordsDropped == 0 && queueDropped == 0 &&
                sessionAppendDropped == 0 && fixtureObservations != 0) {
                recoveryBeforeRemount = leshy1::storage::recoverSession(
                    io, sessionStoreWorkspace,
                    &sessionStoreWorkspace.validationSession);
                status = recoveryBeforeRemount.valid() &&
                                 recoveryBeforeRemount.generation == 1 &&
                                 recoveryBeforeRemount.observations ==
                                     fixtureObservations
                    ? "awaiting_remount"
                    : "pre_remount_recovery_failed";
            } else if (pipelineCommitted && !wifiScannerCleanup) {
                status = "wifi_scanner_cleanup_failed";
            } else if (pipelineCommitted &&
                       (wifiRecordsDropped != 0 || queueDropped != 0 ||
                        sessionAppendDropped != 0)) {
                status = "pipeline_observation_drop";
            } else if (wifiScannerBegun &&
                       std::strcmp(status, "pipeline_running") == 0) {
                status = "pipeline_trigger_missing";
            }
        } else {
            const std::uint64_t commitOneStarted =
                static_cast<std::uint64_t>(esp_timer_get_time());
            commitOne = leshy1::storage::commitNextSession(
                io, sessionStoreWorkspace, librarySession);
            commitOneUs = static_cast<std::uint64_t>(esp_timer_get_time()) -
                          commitOneStarted;
            commitUs[0] = commitOneUs;
            if (!commitOne.complete()) {
                status = "commit_one_failed";
            } else {
                commitsCompleted = 1;
                const std::uint64_t commitTwoStarted =
                    static_cast<std::uint64_t>(esp_timer_get_time());
                commitTwo = leshy1::storage::commitNextSession(
                    io, sessionStoreWorkspace, librarySession);
                commitTwoUs = static_cast<std::uint64_t>(esp_timer_get_time()) -
                              commitTwoStarted;
                commitUs[1] = commitTwoUs;
                if (!commitTwo.complete()) {
                    status = "commit_two_failed";
                } else {
                    commitsCompleted = 2;
                    while (commitsCompleted < commitsRequested) {
                        const std::uint64_t commitStarted =
                            static_cast<std::uint64_t>(esp_timer_get_time());
                        const leshy1::storage::SessionStoreCommitResult next =
                            leshy1::storage::commitNextSession(
                                io, sessionStoreWorkspace, librarySession);
                        commitUs[commitsCompleted] =
                            static_cast<std::uint64_t>(esp_timer_get_time()) -
                            commitStarted;
                        if (!next.complete()) {
                            status = "throughput_commit_failed";
                            break;
                        }
                        ++commitsCompleted;
                    }
                    if (commitsCompleted == commitsRequested) {
                        recoveryBeforeRemount = leshy1::storage::recoverSession(
                            io, sessionStoreWorkspace,
                            &sessionStoreWorkspace.validationSession);
                        status = recoveryBeforeRemount.valid() &&
                                         recoveryBeforeRemount.generation ==
                                             commitsRequested
                            ? "awaiting_remount" : "pre_remount_recovery_failed";
                    }
                }
            }
        }
        bytesWritten = io.bytesWritten();
        fileSyncs = io.fileSyncs();
        directorySyncs = io.directorySyncs();
        fatFileSyncCoversDirectory = io.fatFileSyncCoversDirectory();
        ioFailure = io.lastFailure();
        ioErrno = io.lastErrno();
        ioFresult = io.lastFresult();
        ioFresultName = io.lastFresultName();
        io.end();
        freeAfter = primaryFilesystem.freeBytes();
    }
    if (primaryMountAttempted) {
        primaryFilesystem.end();
        primaryCleanup = primaryFilesystem.cleanupComplete();
    }

    if (std::strcmp(status, "awaiting_remount") == 0) {
        BoardSdFilesystem remountFilesystem;
        remounted = remountFilesystem.begin();
        if (remounted &&
            remountFilesystem.cardCapacityBytes() == cardCapacity &&
            remountFilesystem.exists(permit.scratchPath)) {
            ArduinoFsSessionStoreIo readOnlyIo(remountFilesystem.driveNumber(),
                                               sdSessionStoreIoWorkspace);
            reopenedReadOnly = readOnlyIo.openExistingReadOnly(permit);
            if (reopenedReadOnly) {
                recoveryAfterRemount = leshy1::storage::recoverSession(
                    readOnlyIo, sessionStoreWorkspace,
                    &sessionStoreWorkspace.validationSession);
            }
            readOnlyIo.end();
        }
        remountFilesystem.end();
        remountCleanup = remountFilesystem.cleanupComplete();
        status = recoveryAfterRemount.valid() &&
                         recoveryAfterRemount.generation == commitsRequested &&
                         recoveryAfterRemount.observations ==
                             fixtureObservations
                     ? "valid" : "post_remount_recovery_failed";
    }

    resourceBroker.releaseAll(kSdIdentificationOwner);
    const std::uint32_t ownedAfter =
        resourceBroker.ownedBy(kSdIdentificationOwner);
    const bool cleanupComplete = identityCleanup && primaryCleanup &&
        wifiScannerCleanup &&
        (std::strcmp(status, "valid") != 0 || remountCleanup);
    const leshy1::storage::StorageTimingSummary timings =
        leshy1::storage::summarizeStorageTimings(
            commitUs.data(), commitsCompleted);
    const std::uint64_t logicalBytesPerSecond =
        timings.valid && timings.totalUs != 0
            ? (bytesWritten * 1000000ULL) / timings.totalUs : 0;
    const std::uint64_t encodedPayloadBytesPerSecond =
        timings.valid && timings.totalUs != 0 && fixtureSegmentBytes != 0
            ? (static_cast<std::uint64_t>(fixtureSegmentBytes) *
               (realWifiPipeline ? 1ULL : commitsCompleted) *
               1000000ULL) / timings.totalUs
            : 0;
    const leshy1::services::survey::SessionBatchPolicy batchPolicy;
    bool fixtureRestored = true;
    bool uiStateReady = true;
    bool persistentLibraryAdmitted = false;
    if (realWifiPipeline) {
        surveyDemoReady = prepareSurveyDemo();
        fixtureRestored = false;
        const LibraryEntry* previousLibrary = libraryController.selected();
        const bool previousPersistentLibrary =
            previousLibrary != nullptr && previousLibrary->session != nullptr &&
            previousLibrary->persistent;
        if (std::strcmp(status, "valid") == 0 &&
            recoveryAfterRemount.valid()) {
            librarySession = sessionStoreWorkspace.validationSession;
            libraryController.clear();
            const leshy1::apps::library::SessionCatalogResult cataloged =
                sessionCatalog.admitRecovered(
                    librarySession, recoveryAfterRemount, libraryController,
                    true, false);
            libraryDemoReady = cataloged.admitted();
            const CapabilityRecord* persistentCapability =
                inventory.find("library.persistent_session");
            const bool persistentCapabilityReady =
                (persistentCapability != nullptr &&
                 persistentCapability->state == CapabilityState::Available) ||
                (persistentCapability == nullptr && inventory.add(
                    {"library.persistent_session", CapabilityState::Available,
                     "E-HIL-040_exact_scratch_reopen",
                     "validated_session_open"}));
            persistentLibraryAdmitted =
                libraryDemoReady && persistentCapabilityReady;
            if (persistentLibraryAdmitted) {
                appCatalog.rebuild(inventory);
                renderInteractiveScreen();
            }
        }
        if (!persistentLibraryAdmitted) {
            const LibraryEntry* currentLibrary = libraryController.selected();
            const bool currentPersistentLibrary =
                currentLibrary != nullptr && currentLibrary->session != nullptr &&
                currentLibrary->persistent;
            if (previousPersistentLibrary || currentPersistentLibrary) {
                libraryDemoReady = true;
            } else {
                fixtureRestored = (libraryDemoReady = prepareLibraryDemo());
            }
        }
        uiStateReady = surveyDemoReady && libraryDemoReady;
    } else if (batchThroughput) {
        fixtureRestored = (libraryDemoReady = prepareLibraryDemo());
        uiStateReady = fixtureRestored;
    }
    if (!uiStateReady && std::strcmp(status, "valid") == 0) {
        status = "ui_state_prepare_failed";
    }
    const LibraryEntry* activeLibrary = libraryController.selected();
    const bool persistentLibraryAvailable =
        activeLibrary != nullptr && activeLibrary->session != nullptr &&
        activeLibrary->persistent;
    const bool storageRateTargetMet =
        (batchThroughput || realWifiPipeline) &&
        std::strcmp(status, "valid") == 0 &&
        encodedPayloadBytesPerSecond >=
            kStorageRequiredEncodedBytesPerSecond;
    const std::uint32_t heapFreeAfter = ESP.getFreeHeap();
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"%s\",\"kind\":\"result\","
        "\"mode\":\"%s\",\"status\":\"%s\",\"identity_status\":\"%s\","
        "\"permit_status\":\"%s\",\"explicitly_disposable\":true,"
        "\"expected_fingerprint\":\"%s\",\"cid_hex\":\"%s\","
        "\"fingerprint_matched\":%s,\"run_id\":\"%s\","
        "\"scratch_path\":\"%s\",\"scratch_preexisting\":%s,"
        "\"scratch_created\":%s,\"byte_limit\":%llu,"
        "\"bytes_written\":%llu,\"card_capacity_bytes\":%llu,"
        "\"filesystem_capacity_bytes\":%llu,\"free_before\":%llu,"
        "\"free_after\":%llu,\"mount_us\":%llu,"
        "\"filesystem_driver\":\"esp_idf_sdspi\","
        "\"filesystem_spi_hz\":%lu,\"filesystem_spi_limit_hz\":%lu,"
        "\"filesystem_mount_error\":%d,"
        "\"commit_one_status\":\"%s\",\"commit_one_us\":%llu,"
        "\"commit_one_generation\":%lu,\"commit_one_slot\":\"%s\","
        "\"commit_two_status\":\"%s\",\"commit_two_us\":%llu,"
        "\"commit_two_generation\":%lu,\"commit_two_slot\":\"%s\","
        "\"commit_samples_requested\":%u,\"commit_samples_completed\":%u,"
        "\"commit_total_us\":%llu,\"commit_min_us\":%llu,"
        "\"commit_p50_us\":%llu,\"commit_p95_us\":%llu,"
        "\"commit_p99_us\":%llu,\"commit_max_us\":%llu,"
        "\"logical_write_bytes_per_second\":%llu,"
        "\"fixture_observations\":%u,\"fixture_segment_bytes\":%u,"
        "\"encoded_payload_bytes_per_second\":%llu,"
        "\"required_encoded_bytes_per_second\":%llu,"
        "\"storage_rate_target_met\":%s,"
        "\"batch_target_encoded_bytes\":%u,"
        "\"batch_maximum_latency_us\":%llu,"
        "\"fixture_restored\":%s,\"ui_state_ready\":%s,"
        "\"persistent_library_admitted\":%s,"
        "\"persistent_library_available\":%s,"
        "\"persistent_library_entries\":%u,"
        "\"persistent_library_generation\":%lu,"
        "\"real_wifi_pipeline\":%s,\"passive_only\":%s,"
        "\"wifi_maximum_scans\":%u,\"wifi_scans_completed\":%u,"
        "\"wifi_records_read\":%llu,\"wifi_records_accepted\":%llu,"
        "\"wifi_records_rejected\":%llu,\"wifi_records_dropped\":%llu,"
        "\"queue_capacity\":%u,\"queue_high_water\":%u,"
        "\"queue_pushed\":%llu,\"queue_popped\":%llu,"
        "\"queue_dropped\":%llu,\"session_append_dropped\":%llu,"
        "\"batch_trigger\":\"%s\",\"pipeline_stop_reason\":\"%s\","
        "\"wifi_scanner_begun\":%s,\"wifi_scanner_cleanup\":%s,"
        "\"pre_remount_status\":\"%s\",\"pre_remount_generation\":%lu,"
        "\"pre_remount_choice\":%u,\"pre_remount_a_status\":%u,"
        "\"pre_remount_b_status\":%u,\"post_remount_generation\":%lu,"
        "\"post_remount_observations\":%u,\"file_syncs\":%lu,"
        "\"directory_syncs\":%lu,\"fat_file_sync_covers_directory\":%s,"
        "\"io_failure\":\"%s\",\"io_errno\":%d,"
        "\"io_fresult\":%u,\"io_fresult_name\":\"%s\","
        "\"mounted\":%s,\"remounted\":%s,\"reopened_read_only\":%s,"
        "\"resource_acquired\":%s,\"owned_during\":%lu,\"owned_after\":%lu,"
        "\"cleanup_complete\":%s,\"gpio21_stable_high\":%s,"
        "\"heap_free_before\":%lu,\"heap_free_after\":%lu,"
        "\"heap_min_free\":%lu,"
        "\"synthetic_fixture\":%s,\"filesystem_api_touched\":%s,"
        "\"user_identifiers_emitted\":false,"
        "\"user_identifiers_retained_in_scratch\":%s,"
        "\"wifi_application_connect_calls\":0,"
        "\"wifi_application_raw_tx_calls\":0,"
        "\"physical_wifi_no_tx_instrumented\":false,"
        "\"mount_on_boot\":false,\"format_allowed\":false,"
        "\"partition_table_modified\":false,\"writes_bounded_to_scratch\":%s,"
        "\"existing_paths_deleted\":false,\"user_file_names_listed\":false,"
        "\"user_file_data_read\":false,\"reset_injection\":false,"
        "\"physical_power_cut\":false,\"nrf_ce_high_events\":0,"
        "\"radio_tx_commands\":0}",
        realWifiPipeline
            ? "leshy.survey.wifi_passive_persist.v1"
            : (batchThroughput
            ? "leshy.storage.sd.session_store_batch_throughput.v1"
            : (throughput
                   ? "leshy.storage.sd.session_store_throughput.v1"
                   : "leshy.storage.sd.session_store.v1")),
        realWifiPipeline
            ? "wifi_passive_persist"
            : (batchThroughput
                   ? "batch_throughput"
                   : (throughput ? "throughput" : "commit_remount")),
        status, leshy1::storage::sdTransportRunStatusName(identity.status),
        leshy1::storage::permitStatusName(permit.status),
        expectedFingerprint, cidHex, fingerprintMatched ? "true" : "false",
        runId, permit.allowed() ? permit.scratchPath : scratchPath,
        scratchPreexisting ? "true" : "false",
        scratchCreated ? "true" : "false",
        static_cast<unsigned long long>(permit.byteLimit),
        static_cast<unsigned long long>(bytesWritten),
        static_cast<unsigned long long>(cardCapacity),
        static_cast<unsigned long long>(filesystemCapacity),
        static_cast<unsigned long long>(freeBefore),
        static_cast<unsigned long long>(freeAfter),
        static_cast<unsigned long long>(mountUs),
        static_cast<unsigned long>(actualFilesystemSpiHz),
        static_cast<unsigned long>(BoardSdFilesystem::kSpiHz),
        filesystemMountError,
        leshy1::storage::sessionStoreStatusName(commitOne.status),
        static_cast<unsigned long long>(commitOneUs),
        static_cast<unsigned long>(commitOne.generation),
        commitOne.publishedSlot == leshy1::storage::HeadSlot::A ? "a" : "b",
        leshy1::storage::sessionStoreStatusName(commitTwo.status),
        static_cast<unsigned long long>(commitTwoUs),
        static_cast<unsigned long>(commitTwo.generation),
        commitTwo.publishedSlot == leshy1::storage::HeadSlot::A ? "a" : "b",
        static_cast<unsigned>(commitsRequested),
        static_cast<unsigned>(commitsCompleted),
        static_cast<unsigned long long>(timings.totalUs),
        static_cast<unsigned long long>(timings.minimumUs),
        static_cast<unsigned long long>(timings.p50Us),
        static_cast<unsigned long long>(timings.p95Us),
        static_cast<unsigned long long>(timings.p99Us),
        static_cast<unsigned long long>(timings.maximumUs),
        static_cast<unsigned long long>(logicalBytesPerSecond),
        static_cast<unsigned>(fixtureObservations),
        static_cast<unsigned>(fixtureSegmentBytes),
        static_cast<unsigned long long>(encodedPayloadBytesPerSecond),
        static_cast<unsigned long long>(
            kStorageRequiredEncodedBytesPerSecond),
        storageRateTargetMet ? "true" : "false",
        static_cast<unsigned>(batchPolicy.targetEncodedBytes),
        static_cast<unsigned long long>(batchPolicy.maximumLatencyUs),
        fixtureRestored ? "true" : "false",
        uiStateReady ? "true" : "false",
        persistentLibraryAdmitted ? "true" : "false",
        persistentLibraryAvailable ? "true" : "false",
        static_cast<unsigned>(libraryController.size()),
        static_cast<unsigned long>(activeLibrary == nullptr
                                       ? 0 : activeLibrary->generation),
        realWifiPipeline ? "true" : "false",
        realWifiPipeline ? "true" : "false",
        maximumWifiScans, wifiScansCompleted,
        static_cast<unsigned long long>(wifiRecordsRead),
        static_cast<unsigned long long>(wifiRecordsAccepted),
        static_cast<unsigned long long>(wifiRecordsRejected),
        static_cast<unsigned long long>(wifiRecordsDropped),
        static_cast<unsigned>(
            leshy1::services::survey::ObservationQueue::kCapacity),
        static_cast<unsigned>(queueHighWater),
        static_cast<unsigned long long>(queuePushed),
        static_cast<unsigned long long>(queuePopped),
        static_cast<unsigned long long>(queueDropped),
        static_cast<unsigned long long>(sessionAppendDropped),
        leshy1::services::survey::sessionBatchTriggerName(pipelineTrigger),
        pipelineStopReason,
        wifiScannerBegun ? "true" : "false",
        wifiScannerCleanup ? "true" : "false",
        leshy1::storage::sessionStoreStatusName(recoveryBeforeRemount.status),
        static_cast<unsigned long>(recoveryBeforeRemount.generation),
        static_cast<unsigned>(recoveryBeforeRemount.choice),
        static_cast<unsigned>(recoveryBeforeRemount.aStatus),
        static_cast<unsigned>(recoveryBeforeRemount.bStatus),
        static_cast<unsigned long>(recoveryAfterRemount.generation),
        static_cast<unsigned>(recoveryAfterRemount.observations),
        static_cast<unsigned long>(fileSyncs),
        static_cast<unsigned long>(directorySyncs),
        fatFileSyncCoversDirectory ? "true" : "false",
        ioFailure, ioErrno, ioFresult, ioFresultName,
        mounted ? "true" : "false", remounted ? "true" : "false",
        reopenedReadOnly ? "true" : "false",
        resourcesAcquired ? "true" : "false",
        static_cast<unsigned long>(ownedDuring),
        static_cast<unsigned long>(ownedAfter),
        cleanupComplete ? "true" : "false",
        (identityTransport.gpio21StableHigh() &&
         primaryFilesystem.gpio21StableHigh()) ? "true" : "false",
        static_cast<unsigned long>(heapFreeBefore),
        static_cast<unsigned long>(heapFreeAfter),
        static_cast<unsigned long>(ESP.getMinFreeHeap()),
        realWifiPipeline ? "false" : "true",
        mounted ? "true" : "false",
        realWifiPipeline ? "true" : "false",
        prepared ? "true" : "false");
    reply.println(line);
}

struct WifiIngressSinkContext final {
    SurveySession* session = nullptr;
};

WifiRecordDisposition collectWifiIngressRecord(
    const WifiScanRecord& record, std::uint64_t monotonicUs, void* rawContext) {
    auto* context = static_cast<WifiIngressSinkContext*>(rawContext);
    if (context == nullptr || context->session == nullptr) {
        return WifiRecordDisposition::Rejected;
    }
    Observation observation;
    if (!leshy1::drivers::wifi::normalizePassiveRecord(
            record, monotonicUs, &observation)) {
        return WifiRecordDisposition::Rejected;
    }
    const SessionStatus status = context->session->append(observation);
    if (status == SessionStatus::Appended) {
        return WifiRecordDisposition::Accepted;
    }
    return status == SessionStatus::Full ? WifiRecordDisposition::Dropped
                                         : WifiRecordDisposition::Rejected;
}

bool parseWifiIngressCommand(const char* command, unsigned* samples) {
    if (command == nullptr || samples == nullptr ||
        std::strncmp(command, kWifiIngressPrefix,
                     std::strlen(kWifiIngressPrefix)) != 0) {
        return false;
    }
    unsigned parsedSamples = 0;
    char extra = '\0';
    const int parsed = std::sscanf(
        command + std::strlen(kWifiIngressPrefix), "%u %c",
        &parsedSamples, &extra);
    if (parsed != 1 || parsedSamples == 0 ||
        parsedSamples > kWifiIngressMaxSamples) {
        return false;
    }
    *samples = parsedSamples;
    return true;
}

void emitPhysicalWifiPassiveIngress(Stream& reply, unsigned samplesRequested) {
    auto& line = sdPhysicalEvidence.line;
    auto& rates = sdPhysicalEvidence.commitUs;
    rates.fill(0);
    const leshy1::drivers::wifi::WifiScanPlan plan =
        leshy1::drivers::wifi::defaultPassivePlan();
    const bool planValid = leshy1::drivers::wifi::validatePassivePlan(plan);
    const bool idleUi = uiController.isRoot() && !appRuntime.running();
    const std::uint32_t heapFreeBefore = ESP.getFreeHeap();
    const bool resourcesAcquired = idleUi && planValid && resourceBroker.acquire(
        kWifiIngressOwner,
        leshy1::kernel::runtime::resourceMask(Resource::EspRf));
    const std::uint32_t ownedDuring = resourceBroker.ownedBy(kWifiIngressOwner);
    BoardSdSpiTransport::holdRadioTransmitPathsInactive();

    BoardWifiPassiveScanner scanner;
    const bool scannerBegun = resourcesAcquired && scanner.begin();
    const bool nvsDisabled = scanner.nvsDisabled();
    const bool volatileStorageOnly = scanner.volatileStorageOnly();
    BoardWifiPassiveScanResult lastScan;
    unsigned samplesCompleted = 0;
    std::uint64_t recordsReported = 0;
    std::uint64_t recordsRead = 0;
    std::uint64_t observationsAccepted = 0;
    std::uint64_t observationsRejected = 0;
    std::uint64_t observationsDropped = 0;
    std::uint64_t storageWireBytes = 0;
    std::uint64_t totalScanUs = 0;
    SurveySession& measurementSession =
        sessionStoreWorkspace.validationSession;
    WifiIngressSinkContext sink{&measurementSession};

    if (scannerBegun) {
        for (unsigned sample = 0; sample < samplesRequested; ++sample) {
            measurementSession.reset();
            std::uint64_t sessionStartUs =
                static_cast<std::uint64_t>(esp_timer_get_time());
            if (sessionStartUs == 0) sessionStartUs = 1;
            if (measurementSession.start("wifi-ingress-measure", sessionStartUs) !=
                SessionStatus::Started) {
                break;
            }
            lastScan = scanner.scan(plan, collectWifiIngressRecord, &sink);
            std::uint64_t sessionStopUs =
                static_cast<std::uint64_t>(esp_timer_get_time());
            if (sessionStopUs < sessionStartUs) sessionStopUs = sessionStartUs;
            if (!lastScan.valid() || lastScan.durationUs == 0 ||
                measurementSession.stop(sessionStopUs) != SessionStatus::Stopped) {
                break;
            }
            std::size_t segmentSize = 0;
            if (leshy1::storage::encodeObservationSegment(
                    measurementSession, sessionStoreWorkspace.segment.data(),
                    sessionStoreWorkspace.segment.size(), &segmentSize) !=
                    leshy1::storage::SessionCodecStatus::Valid ||
                segmentSize == 0) {
                break;
            }
            rates[samplesCompleted] =
                (static_cast<std::uint64_t>(segmentSize) * 1000000ULL) /
                lastScan.durationUs;
            if (rates[samplesCompleted] == 0) rates[samplesCompleted] = 1;
            ++samplesCompleted;
            recordsReported += lastScan.recordsReported;
            recordsRead += lastScan.recordsRead;
            observationsAccepted += lastScan.accepted;
            observationsRejected += lastScan.rejected;
            observationsDropped += lastScan.dropped;
            storageWireBytes += segmentSize;
            totalScanUs += lastScan.durationUs;
        }
    }

    const leshy1::services::survey::IngressRateSummary summary =
        leshy1::services::survey::summarizeIngressRates(
            rates.data(), samplesCompleted);
    measurementSession.reset();
    sessionStoreWorkspace.segment.fill(0);
    const bool scannerEnded = scanner.end();
    resourceBroker.releaseAll(kWifiIngressOwner);
    const std::uint32_t ownedAfter = resourceBroker.ownedBy(kWifiIngressOwner);
    const bool cleanupComplete = scannerEnded && scanner.cleanupComplete() &&
        ownedAfter == 0;
    const bool valid = idleUi && resourcesAcquired && scannerBegun &&
        nvsDisabled && volatileStorageOnly && summary.valid &&
        samplesCompleted == samplesRequested && cleanupComplete;
    const std::uint64_t aggregateBytesPerSecond =
        totalScanUs == 0 ? 0 : (storageWireBytes * 1000000ULL) / totalScanUs;
    const std::uint64_t requiredStorageBytesPerSecond =
        summary.valid ? summary.p99BytesPerSecond * 4ULL : 0;
    const std::uint32_t heapFreeAfter = ESP.getFreeHeap();

    std::snprintf(
        line, sizeof(sdPhysicalEvidence.line),
        "{\"schema\":\"leshy.survey.wifi_passive_ingress.v1\","
        "\"kind\":\"result\",\"status\":\"%s\","
        "\"explicit_passive_only\":true,\"plan_valid\":%s,"
        "\"scan_type\":\"passive\",\"channel\":%u,"
        "\"dwell_ms_per_channel\":%lu,\"show_hidden\":%s,"
        "\"ssid_filter\":false,\"bssid_filter\":false,"
        "\"nvs_enabled\":false,\"config_storage\":\"ram\","
        "\"credentials_loaded\":false,\"active_probe_allowed\":false,"
        "\"application_connect_calls\":0,\"application_raw_tx_calls\":0,"
        "\"physical_tx_instrumented\":false,"
        "\"physical_no_tx_verified\":false,"
        "\"samples_requested\":%u,\"samples_completed\":%u,"
        "\"records_reported\":%llu,\"records_read\":%llu,"
        "\"observations_accepted\":%llu,"
        "\"observations_rejected\":%llu,"
        "\"observations_dropped\":%llu,"
        "\"observation_capacity_per_sample\":%u,"
        "\"storage_wire_bytes\":%llu,\"scan_total_us\":%llu,"
        "\"aggregate_bytes_per_second\":%llu,"
        "\"rate_min_bytes_per_second\":%llu,"
        "\"rate_p50_bytes_per_second\":%llu,"
        "\"rate_p95_bytes_per_second\":%llu,"
        "\"rate_p99_bytes_per_second\":%llu,"
        "\"rate_max_bytes_per_second\":%llu,"
        "\"required_storage_bytes_per_second_4x_p99\":%llu,"
        "\"last_scan_status\":\"%s\",\"driver_error\":%d,"
        "\"resource_acquired\":%s,\"owned_during\":%lu,"
        "\"owned_after\":%lu,\"cleanup_complete\":%s,"
        "\"heap_free_before\":%lu,\"heap_free_after\":%lu,"
        "\"heap_min_free\":%lu,\"storage_written\":false,"
        "\"user_identifiers_emitted\":false,"
        "\"user_identifiers_retained\":false,"
        "\"external_radio_tx_paths_held_inactive\":true}",
        valid ? "valid" : "failed", planValid ? "true" : "false",
        static_cast<unsigned>(plan.channel),
        static_cast<unsigned long>(plan.maxMsPerChannel),
        plan.showHidden ? "true" : "false", samplesRequested,
        samplesCompleted, static_cast<unsigned long long>(recordsReported),
        static_cast<unsigned long long>(recordsRead),
        static_cast<unsigned long long>(observationsAccepted),
        static_cast<unsigned long long>(observationsRejected),
        static_cast<unsigned long long>(observationsDropped),
        static_cast<unsigned>(SurveySession::kObservationCapacity),
        static_cast<unsigned long long>(storageWireBytes),
        static_cast<unsigned long long>(totalScanUs),
        static_cast<unsigned long long>(aggregateBytesPerSecond),
        static_cast<unsigned long long>(summary.minimumBytesPerSecond),
        static_cast<unsigned long long>(summary.p50BytesPerSecond),
        static_cast<unsigned long long>(summary.p95BytesPerSecond),
        static_cast<unsigned long long>(summary.p99BytesPerSecond),
        static_cast<unsigned long long>(summary.maximumBytesPerSecond),
        static_cast<unsigned long long>(requiredStorageBytesPerSecond),
        leshy1::platform::arduino::boardWifiScanStatusName(lastScan.status),
        lastScan.driverError != 0 ? lastScan.driverError : scanner.lastError(),
        resourcesAcquired ? "true" : "false",
        static_cast<unsigned long>(ownedDuring),
        static_cast<unsigned long>(ownedAfter),
        cleanupComplete ? "true" : "false",
        static_cast<unsigned long>(heapFreeBefore),
        static_cast<unsigned long>(heapFreeAfter),
        static_cast<unsigned long>(ESP.getMinFreeHeap()));
    reply.println(line);
}

void emitSurveyContract(Stream& reply) {
    const leshy1::drivers::wifi::WifiScanPlan plan =
        leshy1::drivers::wifi::defaultPassivePlan();
    char line[384] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.survey.contract.v1\",\"kind\":\"contract\","
        "\"source\":\"wifi\",\"passive_only\":%s,\"active_probe_allowed\":%s,"
        "\"directed_ssid\":false,\"plan_valid\":%s,\"driver_started\":%s,"
        "\"observation_capacity\":%u,\"radio_touched\":false,"
        "\"golden_demo_ready\":%s,\"golden_observations\":%u}",
        plan.passive ? "true" : "false",
        leshy1::drivers::wifi::kActiveProbeAllowed ? "true" : "false",
        leshy1::drivers::wifi::validatePassivePlan(plan) ? "true" : "false",
        leshy1::drivers::wifi::kDriverStartedInMeasureTarget ? "true" : "false",
        static_cast<unsigned>(leshy1::services::survey::SurveySession::kObservationCapacity),
        surveyDemoReady ? "true" : "false", static_cast<unsigned>(surveySession.size()));
    reply.println(line);
}

void emitSessionFixture(Stream& reply) {
    if (surveySession.state() != SessionState::Stopped) {
        reply.println("{\"schema\":\"leshy.session.fixture.v1\",\"kind\":\"result\","
                      "\"status\":\"not_stopped\",\"storage_written\":false,"
                      "\"radio_touched\":false}");
        return;
    }
    static char summary[768] = {};
    auto& segment = sessionStoreWorkspace.segment;
    auto& manifest = sessionStoreWorkspace.manifest;
    SurveySession& reopened = sessionStoreWorkspace.validationSession;
    std::size_t segmentSize = 0;
    std::size_t manifestSize = 0;
    leshy1::storage::SessionCodecStatus status = leshy1::storage::encodeObservationSegment(
        surveySession, segment.data(), segment.size(), &segmentSize);
    if (status == leshy1::storage::SessionCodecStatus::Valid) {
        status = leshy1::storage::encodeSessionManifest(
            surveySession, segment.data(), segmentSize, manifest.data(), manifest.size(),
            &manifestSize);
    }
    const std::uint32_t manifestCrc =
        leshy1::storage::crc32c(manifest.data(), manifestSize);
    const std::uint32_t segmentCrc = leshy1::storage::crc32c(segment.data(), segmentSize);
    std::uint8_t headWire[leshy1::storage::kHeadWireSize] = {};
    const leshy1::storage::HeadRecord head{
        1, static_cast<std::uint32_t>(manifestSize), manifestCrc};
    bool headSelected = false;
    if (status == leshy1::storage::SessionCodecStatus::Valid &&
        leshy1::storage::encodeHead(head, headWire, sizeof(headWire))) {
        const leshy1::storage::RecoveryResult recovery = leshy1::storage::recoverHead(
            {headWire, sizeof(headWire),
             {true, static_cast<std::uint32_t>(manifestSize), manifestCrc}},
            {});
        headSelected = recovery.choice == leshy1::storage::RecoveryChoice::A;
        if (!headSelected) status = leshy1::storage::SessionCodecStatus::ChecksumMismatch;
    }
    if (status == leshy1::storage::SessionCodecStatus::Valid) {
        status = leshy1::storage::reopenSession(manifest.data(), manifestSize, segment.data(),
                                                segmentSize, &reopened);
    }
    const bool summaryReady = status == leshy1::storage::SessionCodecStatus::Valid &&
                              leshy1::storage::formatSessionJsonSummary(
                                  reopened, summary, sizeof(summary));
    if (!summaryReady && status == leshy1::storage::SessionCodecStatus::Valid) {
        status = leshy1::storage::SessionCodecStatus::BufferTooSmall;
    }

    char line[1280] = {};
    if (status == leshy1::storage::SessionCodecStatus::Valid) {
        std::snprintf(
            line, sizeof(line),
            "{\"schema\":\"leshy.session.fixture.v1\",\"kind\":\"result\","
            "\"status\":\"valid\",\"storage_written\":false,"
            "\"head_selected\":%s,\"manifest_bytes\":%u,\"manifest_crc32c\":%lu,"
            "\"segment_bytes\":%u,\"segment_crc32c\":%lu,"
            "\"reopened_observations\":%u,\"radio_touched\":false,\"summary\":%s}",
            headSelected ? "true" : "false", static_cast<unsigned>(manifestSize),
            static_cast<unsigned long>(manifestCrc), static_cast<unsigned>(segmentSize),
            static_cast<unsigned long>(segmentCrc), static_cast<unsigned>(reopened.size()),
            summary);
    } else {
        std::snprintf(
            line, sizeof(line),
            "{\"schema\":\"leshy.session.fixture.v1\",\"kind\":\"result\","
            "\"status\":\"%s\",\"storage_written\":false,\"radio_touched\":false}",
            leshy1::storage::sessionCodecStatusName(status));
    }
    reply.println(line);
}

void emitSessionStoreFixture(Stream& reply) {
    if (surveySession.state() != SessionState::Stopped) {
        reply.println(
            "{\"schema\":\"leshy.session.store.fixture.v1\",\"kind\":\"result\","
            "\"status\":\"not_stopped\",\"physical_storage_written\":false,"
            "\"radio_touched\":false}");
        return;
    }
    ramSessionStore.reset();
    const leshy1::storage::SessionStoreCommitResult first =
        leshy1::storage::commitNextSession(ramSessionStore, sessionStoreWorkspace,
                                           surveySession);
    const leshy1::storage::SessionStoreCommitResult second =
        leshy1::storage::commitNextSession(ramSessionStore, sessionStoreWorkspace,
                                           surveySession);
    SurveySession& reopened = sessionStoreWorkspace.validationSession;
    const leshy1::storage::SessionStoreRecoveryResult newest =
        leshy1::storage::recoverSession(ramSessionStore, sessionStoreWorkspace, &reopened);
    static char summary[768] = {};
    const bool summaryReady = newest.valid() &&
                              leshy1::storage::formatSessionJsonSummary(
                                  reopened, summary, sizeof(summary));
    const bool corrupted = ramSessionStore.flipSegmentByte(2, 0);
    const leshy1::storage::SessionStoreRecoveryResult fallback =
        leshy1::storage::recoverSession(ramSessionStore, sessionStoreWorkspace, &reopened);
    const bool restored = ramSessionStore.flipSegmentByte(2, 0);
    const bool valid = first.complete() && first.generation == 1 &&
                       first.publishedSlot == leshy1::storage::HeadSlot::A &&
                       second.complete() && second.generation == 2 &&
                       second.publishedSlot == leshy1::storage::HeadSlot::B &&
                       newest.valid() && newest.generation == 2 && newest.observations == 3 &&
                       summaryReady && corrupted && fallback.valid() &&
                       fallback.generation == 1 && fallback.observations == 3 &&
                       fallback.bStatus == leshy1::storage::CandidateStatus::InvalidPayload &&
                       restored;

    char line[1024] = {};
    if (valid) {
        std::snprintf(
            line, sizeof(line),
            "{\"schema\":\"leshy.session.store.fixture.v1\",\"kind\":\"result\","
            "\"status\":\"valid\",\"backend\":\"bounded_ram\","
            "\"persistent\":false,\"physical_storage_written\":false,"
            "\"first_generation\":%lu,\"first_slot\":\"a\","
            "\"second_generation\":%lu,\"second_slot\":\"b\","
            "\"recovered_generation\":%lu,\"reopened_observations\":%u,"
            "\"corrupt_new_status\":\"invalid_payload\","
            "\"fallback_generation\":%lu,\"fallback_observations\":%u,"
            "\"file_syncs\":%u,\"directory_syncs\":%u,"
            "\"radio_touched\":false,\"summary\":%s}",
            static_cast<unsigned long>(first.generation),
            static_cast<unsigned long>(second.generation),
            static_cast<unsigned long>(newest.generation),
            static_cast<unsigned>(newest.observations),
            static_cast<unsigned long>(fallback.generation),
            static_cast<unsigned>(fallback.observations),
            static_cast<unsigned>(ramSessionStore.fileSyncs()),
            static_cast<unsigned>(ramSessionStore.directorySyncs()), summary);
    } else {
        std::snprintf(
            line, sizeof(line),
            "{\"schema\":\"leshy.session.store.fixture.v1\",\"kind\":\"result\","
            "\"status\":\"failed\",\"first\":\"%s\",\"second\":\"%s\","
            "\"newest\":\"%s\",\"fallback\":\"%s\","
            "\"physical_storage_written\":false,\"radio_touched\":false}",
            leshy1::storage::sessionStoreStatusName(first.status),
            leshy1::storage::sessionStoreStatusName(second.status),
            leshy1::storage::sessionStoreStatusName(newest.status),
            leshy1::storage::sessionStoreStatusName(fallback.status));
    }
    reply.println(line);
}

void emitLibraryFixture(Stream& reply) {
    const LibraryEntry* entry = libraryController.selected();
    static char summary[768] = {};
    const bool valid = libraryDemoReady && entry != nullptr && entry->session != nullptr &&
                       leshy1::storage::formatSessionJsonSummary(
                           *entry->session, summary, sizeof(summary));
    char line[1280] = {};
    if (valid) {
        std::snprintf(
            line, sizeof(line),
            "{\"schema\":\"leshy.library.fixture.v1\",\"kind\":\"result\","
            "\"status\":\"valid\",\"entries\":%u,\"generation\":%lu,"
            "\"integrity\":\"%s\",\"simulated\":%s,\"persistent\":%s,"
            "\"storage_backend\":\"%s\",\"storage_lease_required\":%s,"
            "\"radio_touched\":false,\"summary\":%s}",
            static_cast<unsigned>(libraryController.size()),
            static_cast<unsigned long>(entry->generation),
            leshy1::apps::library::sessionIntegrityName(entry->integrity),
            entry->simulated ? "true" : "false",
            entry->persistent ? "true" : "false",
            entry->persistent ? "persistent_media" : "bounded_ram",
            entry->persistent ? "true" : "false", summary);
    } else {
        std::snprintf(
            line, sizeof(line),
            "{\"schema\":\"leshy.library.fixture.v1\",\"kind\":\"result\","
            "\"status\":\"unavailable\",\"simulated\":false,\"persistent\":false,"
            "\"radio_touched\":false}");
    }
    reply.println(line);
}

void emitLibraryExport(Stream& reply) {
    static char artifact[4096] = {};
    if (libraryController.view() != LibraryView::ExportReady) {
        reply.println(
            "{\"schema\":\"leshy.library.export.v1\",\"kind\":\"artifact\","
            "\"status\":\"not_requested\",\"persistent\":false,"
            "\"transport\":\"serial_ndjson\",\"radio_touched\":false}");
        return;
    }
    const leshy1::apps::library::LibraryExportResult result =
        libraryController.formatSelectedJsonExport(artifact, sizeof(artifact));
    if (result.valid()) {
        reply.println(artifact);
        return;
    }
    char line[256] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.library.export.v1\",\"kind\":\"artifact\","
        "\"status\":\"%s\",\"persistent\":false,"
        "\"transport\":\"serial_ndjson\",\"radio_touched\":false}",
        leshy1::apps::library::libraryExportStatusName(result.status));
    reply.println(line);
}

void emitLibraryCaptureMetadata(Stream& reply) {
    if (libraryController.view() != LibraryView::ExportReady) {
        reply.println(
            "{\"schema\":\"leshy.capture.metadata.v1\",\"kind\":\"capture\","
            "\"status\":\"not_requested\",\"radio_touched\":false}");
        return;
    }
    const auto result = libraryController.formatSelectedCaptureMetadata(
        diagnosticJson, sizeof(diagnosticJson));
    if (result.valid()) {
        reply.println(diagnosticJson);
        return;
    }
    std::snprintf(
        diagnosticJson, sizeof(diagnosticJson),
        "{\"schema\":\"leshy.capture.metadata.v1\",\"kind\":\"capture\","
        "\"status\":\"%s\",\"radio_touched\":false}",
        leshy1::apps::library::libraryExportStatusName(result.status));
    reply.println(diagnosticJson);
}

void emitLibraryCsvExport(Stream& reply) {
    const LibraryEntry* entry = libraryController.selected();
    if (libraryController.view() != LibraryView::ExportReady || entry == nullptr ||
        entry->session == nullptr) {
        reply.println(
            "{\"schema\":\"leshy.library.csv.v1\",\"kind\":\"begin\","
            "\"status\":\"not_requested\",\"radio_touched\":false}");
        return;
    }
    const auto& capture = entry->session->captureMetadata();
    if (capture.subGhzRawCaptured) {
        if (entry->generation != sessionStoreWorkspace.generation) {
            reply.println(
                "{\"schema\":\"leshy.library.csv.v1\",\"kind\":\"error\","
                "\"reason\":\"generation_not_loaded\","
                "\"radio_touched\":false}");
            return;
        }
        leshy1::storage::PersistedSubGhzRawCaptureView persisted;
        const auto opened =
            leshy1::storage::openPersistedSubGhzRawCapture(
                *entry->session, sessionStoreWorkspace.segment.data(),
                sessionStoreWorkspace.segmentSize, &persisted);
        if (opened != leshy1::storage::SessionCodecStatus::Valid) {
            std::snprintf(
                diagnosticJson, sizeof(diagnosticJson),
                "{\"schema\":\"leshy.library.csv.v1\",\"kind\":\"error\","
                "\"reason\":\"%s\",\"radio_touched\":false}",
                leshy1::storage::sessionCodecStatusName(opened));
            reply.println(diagnosticJson);
            return;
        }
        std::snprintf(
            diagnosticJson, sizeof(diagnosticJson),
            "{\"schema\":\"leshy.library.csv.v1\",\"kind\":\"begin\","
            "\"status\":\"valid\",\"format\":\"subghz_raw_pulses\","
            "\"generation\":%lu,\"session_id\":\"%s\","
            "\"records\":%u,\"columns\":3,\"line_endings\":\"crlf\","
            "\"radio_touched\":false}",
            static_cast<unsigned long>(entry->generation),
            entry->session->id(),
            static_cast<unsigned>(persisted.pulseCount()));
        reply.println(diagnosticJson);
        reply.flush();
        char row[64] = {};
        const auto header =
            leshy1::apps::capture::formatSubGhzRawCsvHeader(
                row, sizeof(row));
        bool valid = header.valid &&
            reply.write(reinterpret_cast<const std::uint8_t*>(row),
                        header.bytes) == header.bytes;
        std::size_t bytes = valid ? header.bytes : 0U;
        std::size_t records = 0;
        for (std::size_t index = 0;
             valid && index < persisted.pulseCount(); ++index) {
            const auto formatted =
                leshy1::apps::capture::formatSubGhzRawCsvRow(
                    persisted, index, capture.subGhzStartLevel,
                    row, sizeof(row));
            valid = formatted.valid &&
                reply.write(reinterpret_cast<const std::uint8_t*>(row),
                            formatted.bytes) == formatted.bytes;
            if (valid) {
                bytes += formatted.bytes;
                ++records;
            }
        }
        std::snprintf(
            diagnosticJson, sizeof(diagnosticJson),
            "{\"schema\":\"leshy.library.csv.v1\",\"kind\":\"end\","
            "\"status\":\"%s\",\"format\":\"subghz_raw_pulses\","
            "\"records\":%u,\"bytes\":%u,"
            "\"persistent\":true,\"radio_touched\":false}",
            valid ? "complete" : "stream_failed",
            static_cast<unsigned>(records),
            static_cast<unsigned>(bytes));
        reply.println(diagnosticJson);
        reply.flush();
        return;
    }
    if (capture.infraredRawCaptured) {
        if (entry->generation != sessionStoreWorkspace.generation) {
            reply.println(
                "{\"schema\":\"leshy.library.csv.v1\",\"kind\":\"error\","
                "\"reason\":\"generation_not_loaded\","
                "\"radio_touched\":false}");
            return;
        }
        leshy1::storage::PersistedInfraredRawCaptureView persisted;
        const auto opened = leshy1::storage::openPersistedInfraredRawCapture(
            *entry->session, sessionStoreWorkspace.segment.data(),
            sessionStoreWorkspace.segmentSize, &persisted);
        if (opened != leshy1::storage::SessionCodecStatus::Valid) {
            std::snprintf(
                diagnosticJson, sizeof(diagnosticJson),
                "{\"schema\":\"leshy.library.csv.v1\",\"kind\":\"error\","
                "\"reason\":\"%s\",\"radio_touched\":false}",
                leshy1::storage::sessionCodecStatusName(opened));
            reply.println(diagnosticJson);
            return;
        }
        std::snprintf(
            diagnosticJson, sizeof(diagnosticJson),
            "{\"schema\":\"leshy.library.csv.v1\",\"kind\":\"begin\","
            "\"status\":\"valid\",\"format\":\"infrared_raw_pulses\","
            "\"generation\":%lu,\"session_id\":\"%s\","
            "\"records\":%u,\"columns\":3,\"line_endings\":\"crlf\","
            "\"radio_touched\":false}",
            static_cast<unsigned long>(entry->generation),
            entry->session->id(),
            static_cast<unsigned>(persisted.pulseCount()));
        reply.println(diagnosticJson);
        reply.flush();
        char row[64] = {};
        const auto header = leshy1::apps::capture::formatInfraredCsvHeader(
            row, sizeof(row));
        bool valid = header.valid &&
            reply.write(reinterpret_cast<const std::uint8_t*>(row),
                        header.bytes) == header.bytes;
        std::size_t bytes = valid ? header.bytes : 0U;
        std::size_t records = 0;
        for (std::size_t index = 0;
             valid && index < persisted.pulseCount(); ++index) {
            const auto formatted =
                leshy1::apps::capture::formatInfraredCsvRow(
                    persisted, index, capture.infraredStartLevel,
                    row, sizeof(row));
            valid = formatted.valid &&
                reply.write(reinterpret_cast<const std::uint8_t*>(row),
                            formatted.bytes) == formatted.bytes;
            if (valid) {
                bytes += formatted.bytes;
                ++records;
            }
        }
        std::snprintf(
            diagnosticJson, sizeof(diagnosticJson),
            "{\"schema\":\"leshy.library.csv.v1\",\"kind\":\"end\","
            "\"status\":\"%s\",\"format\":\"infrared_raw_pulses\","
            "\"records\":%u,\"bytes\":%u,"
            "\"persistent\":true,\"radio_touched\":false}",
            valid ? "complete" : "stream_failed",
            static_cast<unsigned>(records), static_cast<unsigned>(bytes));
        reply.println(diagnosticJson);
        reply.flush();
        return;
    }
    char row[256] = {};
    const auto header = libraryController.formatSelectedCsvHeader(
        row, sizeof(row));
    if (!header.valid()) {
        std::snprintf(
            diagnosticJson, sizeof(diagnosticJson),
            "{\"schema\":\"leshy.library.csv.v1\",\"kind\":\"begin\","
            "\"status\":\"%s\",\"radio_touched\":false}",
            leshy1::apps::library::libraryExportStatusName(header.status));
        reply.println(diagnosticJson);
        return;
    }
    std::snprintf(
        diagnosticJson, sizeof(diagnosticJson),
        "{\"schema\":\"leshy.library.csv.v1\",\"kind\":\"begin\","
        "\"status\":\"valid\",\"generation\":%lu,\"session_id\":\"%s\","
        "\"records\":%u,\"columns\":9,\"line_endings\":\"crlf\","
        "\"identity_encoding\":\"lower_hex\",\"label_encoding\":\"lower_hex\","
        "\"radio_touched\":false}",
        static_cast<unsigned long>(entry->generation), entry->session->id(),
        static_cast<unsigned>(entry->session->size()));
    reply.println(diagnosticJson);
    reply.print(row);
    std::size_t bytes = header.bytes;
    std::size_t records = 0;
    for (std::size_t index = 0; index < entry->session->size(); ++index) {
        const auto formatted = libraryController.formatSelectedCsvRow(
            index, row, sizeof(row));
        if (!formatted.valid()) {
            std::snprintf(
                diagnosticJson, sizeof(diagnosticJson),
                "{\"schema\":\"leshy.library.csv.v1\",\"kind\":\"end\","
                "\"status\":\"%s\",\"records\":%u,\"bytes\":%u,"
                "\"radio_touched\":false}",
                leshy1::apps::library::libraryExportStatusName(formatted.status),
                static_cast<unsigned>(records), static_cast<unsigned>(bytes));
            reply.println(diagnosticJson);
            return;
        }
        reply.print(row);
        bytes += formatted.bytes;
        ++records;
    }
    std::snprintf(
        diagnosticJson, sizeof(diagnosticJson),
        "{\"schema\":\"leshy.library.csv.v1\",\"kind\":\"end\","
        "\"status\":\"complete\",\"records\":%u,\"bytes\":%u,"
        "\"radio_touched\":false}",
        static_cast<unsigned>(records), static_cast<unsigned>(bytes));
    reply.println(diagnosticJson);
}

void emitLibraryPcapStatus(Stream& reply) {
    if (libraryController.view() != LibraryView::ExportReady) {
        reply.println(
            "{\"schema\":\"leshy.library.pcap.v1\",\"kind\":\"artifact\","
            "\"status\":\"not_requested\",\"radio_touched\":false}");
        return;
    }
    const LibraryEntry* entry = libraryController.selected();
    if (entry == nullptr || entry->session == nullptr ||
        !entry->session->captureMetadata().framePayloadCaptured) {
        const auto result = libraryController.formatSelectedPcapStatus(
            diagnosticJson, sizeof(diagnosticJson));
        if (result.valid()) {
            reply.println(diagnosticJson);
        } else {
            std::snprintf(
                diagnosticJson, sizeof(diagnosticJson),
                "{\"schema\":\"leshy.library.pcap.v1\",\"kind\":\"artifact\","
                "\"status\":\"%s\",\"radio_touched\":false}",
                leshy1::apps::library::libraryExportStatusName(result.status));
            reply.println(diagnosticJson);
        }
        return;
    }
    if (entry->generation != sessionStoreWorkspace.generation) {
        reply.println(
            "{\"schema\":\"leshy.library.pcap.v1\",\"kind\":\"error\","
            "\"reason\":\"generation_not_loaded\",\"radio_touched\":false}");
        return;
    }
    leshy1::storage::PersistedWifiFrameCaptureView persisted;
    const auto opened = leshy1::storage::openPersistedWifiFrameCapture(
        *entry->session, sessionStoreWorkspace.segment.data(),
        sessionStoreWorkspace.segmentSize, &persisted);
    if (opened != leshy1::storage::SessionCodecStatus::Valid) {
        std::snprintf(
            diagnosticJson, sizeof(diagnosticJson),
            "{\"schema\":\"leshy.library.pcap.v1\",\"kind\":\"error\","
            "\"reason\":\"%s\",\"radio_touched\":false}",
            leshy1::storage::sessionCodecStatusName(opened));
        reply.println(diagnosticJson);
        return;
    }
    const auto& source = static_cast<
        const leshy1::domain::captures::WifiFrameSource&>(persisted);
    const std::size_t expected =
        leshy1::apps::capture::radiotapPcapSize(source);
    std::snprintf(
        diagnosticJson, sizeof(diagnosticJson),
        "{\"schema\":\"leshy.library.pcap.v1\",\"kind\":\"pcap_begin\","
        "\"status\":\"valid\",\"generation\":%lu,\"session_id\":\"%s\","
        "\"bytes\":%u,\"frames\":%u,\"linktype\":127,"
        "\"timebase\":\"monotonic_us\",\"streaming\":true,"
        "\"persistent\":true,\"radio_touched\":false}",
        static_cast<unsigned long>(entry->generation), entry->session->id(),
        static_cast<unsigned>(expected),
        static_cast<unsigned>(persisted.frameCount()));
    reply.println(diagnosticJson);
    reply.flush();
    StreamPcapSink sink{&reply};
    const PcapExportResult pcap = leshy1::apps::capture::writeRadiotapPcap(
        source, writePcapBytes, &sink);
    std::snprintf(
        diagnosticJson, sizeof(diagnosticJson),
        "{\"schema\":\"leshy.library.pcap.v1\",\"kind\":\"pcap_end\","
        "\"status\":\"%s\",\"bytes\":%u,\"frames\":%u,"
        "\"persistent\":true,\"radio_touched\":false}",
        pcap.valid ? "valid" : "stream_failed",
        static_cast<unsigned>(pcap.bytesWritten),
        static_cast<unsigned>(pcap.framesWritten));
    reply.println(diagnosticJson);
    reply.flush();
}

void emitHilSessionBegin(Stream& reply, const char* command) {
    constexpr const char* prefix = "hil.begin ";
    const char* arguments = command + std::strlen(prefix);
    const char* separator = std::strchr(arguments, ' ');
    char sessionId[HilSession::kSessionIdLength + 1] = {};
    char candidateIdentity[HilSession::kAppIdentityLength + 1] = {};
    HilSessionStatus status = HilSessionStatus::InvalidSessionId;
    if (separator != nullptr &&
        static_cast<std::size_t>(separator - arguments) ==
            HilSession::kSessionIdLength &&
        std::strlen(separator + 1) == HilSession::kAppIdentityLength) {
        std::memcpy(sessionId, arguments, HilSession::kSessionIdLength);
        std::memcpy(candidateIdentity, separator + 1,
                    HilSession::kAppIdentityLength + 1);
        status = hilSession.begin(sessionId, candidateIdentity,
                                  runningAppElfSha256);
    }
    char line[384] = {};
    if (status == HilSessionStatus::Begun) {
        std::snprintf(
            line, sizeof(line),
            "{\"schema\":\"leshy.hil.session.v1\",\"kind\":\"begun\","
            "\"status\":\"begun\",\"session_id\":\"%s\",\"active\":true,"
            "\"app_elf_sha256\":\"%s\",\"firmware_version\":\"%s\","
            "\"ui_revision\":%lu}",
            hilSession.id(), runningAppElfSha256, LESHY1_VERSION,
            static_cast<unsigned long>(uiController.revision()));
    } else {
        std::snprintf(
            line, sizeof(line),
            "{\"schema\":\"leshy.hil.session.v1\",\"kind\":\"error\","
            "\"operation\":\"begin\",\"status\":\"%s\",\"active\":%s}",
            leshy1::services::diagnostics::hilSessionStatusName(status),
            hilSession.active() ? "true" : "false");
    }
    reply.println(line);
}

void emitHilSessionEnd(Stream& reply, const char* command) {
    constexpr const char* prefix = "hil.end ";
    const char* sessionId = command + std::strlen(prefix);
    const HilSessionStatus status = hilSession.end(sessionId);
    char line[256] = {};
    if (status == HilSessionStatus::Ended) {
        std::snprintf(
            line, sizeof(line),
            "{\"schema\":\"leshy.hil.session.v1\",\"kind\":\"ended\","
            "\"status\":\"ended\",\"session_id\":\"%s\",\"active\":false,"
            "\"app_elf_sha256\":\"%s\",\"ui_revision\":%lu}",
            hilSession.id(), runningAppElfSha256,
            static_cast<unsigned long>(uiController.revision()));
    } else {
        std::snprintf(
            line, sizeof(line),
            "{\"schema\":\"leshy.hil.session.v1\",\"kind\":\"error\","
            "\"operation\":\"end\",\"status\":\"%s\",\"active\":%s}",
            leshy1::services::diagnostics::hilSessionStatusName(status),
            hilSession.active() ? "true" : "false");
    }
    reply.println(line);
}

void emitInputState(Stream& reply) {
    leshy1::ui::Pcf8574ButtonInputMetrics metrics;
    std::uint32_t queueDrops = 0;
    std::uint32_t queueHighWater = 0;
    portENTER_CRITICAL(&physicalInputMux);
    metrics = physicalButtonInput.metrics();
    queueDrops = physicalInputQueueDrops;
    queueHighWater = physicalInputQueueHighWater;
    portEXIT_CRITICAL(&physicalInputMux);
    const unsigned queueDepth = physicalInputEvents == nullptr
                                    ? 0U
                                    : static_cast<unsigned>(
                                          uxQueueMessagesWaiting(physicalInputEvents));
    char line[768] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.input.frontend.v1\",\"kind\":\"state\","
        "\"status\":\"%s\",\"task_started\":%s,"
        "\"poll_period_ms\":%lu,\"debounce_ms\":%lu,"
        "\"button_mask\":%u,\"latest_raw\":%u,\"stable_raw\":%u,"
        "\"valid_samples\":%lu,\"read_errors\":%lu,"
        "\"raw_transitions\":%lu,\"stable_transitions\":%lu,"
        "\"press_events\":%lu,\"release_events\":%lu,"
        "\"ambiguous_presses\":%lu,\"presses\":{"
        "\"select\":%lu,\"up\":%lu,\"down\":%lu,"
        "\"left\":%lu,\"right\":%lu},"
        "\"maximum_sample_gap_ms\":%lu,\"queue_capacity\":%u,"
        "\"queue_depth\":%u,\"queue_high_water\":%lu,"
        "\"queue_drops\":%lu,"
        "\"dispatched_press_events\":%lu,"
        "\"last_dispatched_action\":\"%s\","
        "\"last_dispatched_changed\":%s,"
        "\"last_queue_latency_us\":%llu,"
        "\"maximum_queue_latency_us\":%llu,"
        "\"last_repaint_us\":%llu,"
        "\"last_end_to_end_us\":%llu,"
        "\"maximum_end_to_end_us\":%llu,"
        "\"hot_path_serial_writes\":0}",
        physicalInputTaskStarted && bootMetrics.inputDetected ? "ready" : "unavailable",
        physicalInputTaskStarted ? "true" : "false",
        static_cast<unsigned long>(Pcf8574ButtonInput::kPollPeriodMs),
        static_cast<unsigned long>(Pcf8574ButtonInput::kDebounceMs),
        static_cast<unsigned>(Pcf8574ButtonInput::kButtonMask),
        static_cast<unsigned>(metrics.latestRaw),
        static_cast<unsigned>(metrics.stableRaw),
        static_cast<unsigned long>(metrics.validSamples),
        static_cast<unsigned long>(metrics.readErrors),
        static_cast<unsigned long>(metrics.rawTransitions),
        static_cast<unsigned long>(metrics.stableTransitions),
        static_cast<unsigned long>(metrics.pressEvents),
        static_cast<unsigned long>(metrics.releaseEvents),
        static_cast<unsigned long>(metrics.ambiguousPresses),
        static_cast<unsigned long>(metrics.selectPresses),
        static_cast<unsigned long>(metrics.upPresses),
        static_cast<unsigned long>(metrics.downPresses),
        static_cast<unsigned long>(metrics.leftPresses),
        static_cast<unsigned long>(metrics.rightPresses),
        static_cast<unsigned long>(metrics.maximumSampleGapMs),
        static_cast<unsigned>(kPhysicalInputQueueCapacity), queueDepth,
        static_cast<unsigned long>(queueHighWater),
        static_cast<unsigned long>(queueDrops),
        static_cast<unsigned long>(physicalInputDispatchedPresses),
        leshy1::ui::uiActionName(lastPhysicalInputAction),
        lastPhysicalInputChanged ? "true" : "false",
        static_cast<unsigned long long>(lastPhysicalInputQueueUs),
        static_cast<unsigned long long>(maximumPhysicalInputQueueUs),
        static_cast<unsigned long long>(lastPhysicalInputRenderUs),
        static_cast<unsigned long long>(lastPhysicalInputEndToEndUs),
        static_cast<unsigned long long>(maximumPhysicalInputEndToEndUs));
    reply.println(line);
}

void emitSelfTestReport(Stream& reply) {
    const SelfTestReport& report = selfTestController.report();
    const std::uint32_t radioTxCommands =
        shieldReceiverProbeReport.radioTxCommands +
        fullGuidedNrf24Report.txModeEntries +
        fullGuidedNrf24Report.txPayloadCommands +
        fullGuidedCc1101Report.txStrobes;
    auto& line = diagnosticJson;
    line[0] = '\0';
    const int prefix = std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.self_test.report.v1\",\"kind\":\"report\","
        "\"schema_version\":%u,\"plan_version\":%u,"
        "\"firmware_version\":\"%s\",\"app_elf_sha256\":\"%s\","
        "\"board_profile\":\"%s\",\"mode\":\"%s\",\"status\":\"%s\","
        "\"sequence\":%lu,\"started_us\":%llu,\"duration_us\":%llu,"
        "\"read_only\":%s,\"cancelled\":%s,"
        "\"passed\":%u,\"failed\":%u,\"blocked\":%u,"
        "\"not_applicable\":%u,"
        "\"side_effects\":{\"radio_tx_commands\":%lu,"
        "\"storage_write_commands\":%lu,"
        "\"storage_write_bytes\":%llu,"
        "\"product_storage_write_commands\":0,"
        "\"buzzer_activations\":0},"
        "\"facts\":{\"build_identity_present\":%s,"
        "\"profile_matched\":%s,\"display_ready\":%s,"
        "\"touch_frontend_ready\":%s,"
        "\"input_frontend_ready\":%s,\"input_queue_healthy\":%s,"
        "\"buzzer_inactive\":%s,\"resource_scope_clean\":%s,"
        "\"heap_free\":%lu,\"heap_minimum\":%lu,\"heap_floor\":%lu,"
        "\"input_queue_drops\":%lu,\"run_resource_mask\":%lu,"
        "\"persistent_survey_ready\":%s,\"passive_ble_ready\":%s,"
        "\"passive_wifi_capture_ready\":%s,"
        "\"enrolled_storage_ready\":%s,"
        "\"persistent_library_ready\":%s,"
        "\"persistent_wifi_capture_ready\":%s,"
        "\"gps_declared\":%s,\"pn532_declared\":%s,"
        "\"ir_declared\":%s,"
        "\"shield_receivers_applicable\":%s,"
        "\"shield_receiver_probe_complete\":%s,"
        "\"shield_receiver_probe_passed\":%s,"
        "\"nrf24_spectrum_exercise_complete\":%s,"
        "\"nrf24_spectrum_exercise_passed\":%s,"
        "\"cc1101_spectrum_exercise_complete\":%s,"
        "\"cc1101_spectrum_exercise_passed\":%s,"
        "\"persistent_recovery_audit_complete\":%s,"
        "\"persistent_recovery_audit_passed\":%s,"
        "\"library_export_audit_complete\":%s,"
        "\"library_export_audit_passed\":%s,"
        "\"capture_pcap_audit_complete\":%s,"
        "\"capture_pcap_audit_applicable\":%s,"
        "\"capture_pcap_audit_passed\":%s,"
        "\"disposable_commit_complete\":%s,"
        "\"disposable_commit_passed\":%s,"
        "\"disposable_remount_complete\":%s,"
        "\"disposable_remount_passed\":%s,"
        "\"disposable_export_complete\":%s,"
        "\"disposable_export_passed\":%s,"
        "\"disposable_cleanup_complete\":%s,"
        "\"disposable_cleanup_passed\":%s},"
        "\"checks\":[",
        static_cast<unsigned>(SelfTestReport::kSchemaVersion),
        static_cast<unsigned>(SelfTestReport::kPlanVersion), LESHY1_VERSION,
        runningAppElfSha256, BoardProfile::kId,
        leshy1::apps::self_test::selfTestModeName(report.mode),
        leshy1::apps::self_test::selfTestResultStatusName(report.status),
        static_cast<unsigned long>(report.sequence),
        static_cast<unsigned long long>(report.startedUs),
        static_cast<unsigned long long>(report.durationUs),
        report.readOnly ? "true" : "false",
        report.cancelled ? "true" : "false",
        static_cast<unsigned>(report.passed),
        static_cast<unsigned>(report.failed),
        static_cast<unsigned>(report.blocked),
        static_cast<unsigned>(report.notApplicable),
        static_cast<unsigned long>(radioTxCommands),
        static_cast<unsigned long>(
            report.mode == SelfTestMode::FullGuided
                ? report.facts.disposableStorageWriteCalls : 0),
        static_cast<unsigned long long>(
            report.mode == SelfTestMode::FullGuided
                ? report.facts.disposableStorageWriteBytes : 0),
        report.facts.buildIdentityPresent ? "true" : "false",
        report.facts.profileMatched ? "true" : "false",
        report.facts.displayReady ? "true" : "false",
        report.facts.touchFrontendReady ? "true" : "false",
        report.facts.inputFrontendReady ? "true" : "false",
        report.facts.inputQueueHealthy ? "true" : "false",
        report.facts.buzzerInactive ? "true" : "false",
        report.facts.resourceScopeClean ? "true" : "false",
        static_cast<unsigned long>(report.facts.heapFree),
        static_cast<unsigned long>(report.facts.heapMinimum),
        static_cast<unsigned long>(report.facts.heapFloor),
        static_cast<unsigned long>(report.facts.inputQueueDrops),
        static_cast<unsigned long>(report.facts.activeResources),
        report.facts.persistentSurveyReady ? "true" : "false",
        report.facts.passiveBleReady ? "true" : "false",
        report.facts.passiveWifiCaptureReady ? "true" : "false",
        report.facts.enrolledStorageReady ? "true" : "false",
        report.facts.persistentLibraryReady ? "true" : "false",
        report.facts.persistentWifiCaptureReady ? "true" : "false",
        report.facts.gpsDeclared ? "true" : "false",
        report.facts.pn532Declared ? "true" : "false",
        report.facts.irDeclared ? "true" : "false",
        report.facts.shieldReceiversApplicable ? "true" : "false",
        report.facts.shieldReceiverProbeComplete ? "true" : "false",
        report.facts.shieldReceiverProbePassed ? "true" : "false",
        report.facts.nrf24SpectrumExerciseComplete ? "true" : "false",
        report.facts.nrf24SpectrumExercisePassed ? "true" : "false",
        report.facts.cc1101SpectrumExerciseComplete ? "true" : "false",
        report.facts.cc1101SpectrumExercisePassed ? "true" : "false",
        report.facts.persistentRecoveryAuditComplete ? "true" : "false",
        report.facts.persistentRecoveryAuditPassed ? "true" : "false",
        report.facts.libraryExportAuditComplete ? "true" : "false",
        report.facts.libraryExportAuditPassed ? "true" : "false",
        report.facts.capturePcapAuditComplete ? "true" : "false",
        report.facts.capturePcapAuditApplicable ? "true" : "false",
        report.facts.capturePcapAuditPassed ? "true" : "false",
        report.facts.disposableCommitComplete ? "true" : "false",
        report.facts.disposableCommitPassed ? "true" : "false",
        report.facts.disposableRemountComplete ? "true" : "false",
        report.facts.disposableRemountPassed ? "true" : "false",
        report.facts.disposableExportComplete ? "true" : "false",
        report.facts.disposableExportPassed ? "true" : "false",
        report.facts.disposableCleanupComplete ? "true" : "false",
        report.facts.disposableCleanupPassed ? "true" : "false");
    if (prefix < 0 || static_cast<std::size_t>(prefix) >= sizeof(line)) {
        reply.println("{\"schema\":\"leshy.self_test.report.v1\","
                      "\"kind\":\"error\",\"reason\":\"format_failed\"}");
        return;
    }
    std::size_t used = static_cast<std::size_t>(prefix);
    for (std::size_t index = 0; index < report.checkCount; ++index) {
        const auto& check = report.checks[index];
        const int written = std::snprintf(
            line + used, sizeof(line) - used,
            "%s{\"id\":\"%s\",\"status\":\"%s\"}",
            index == 0 ? "" : ",", check.id == nullptr ? "missing" : check.id,
            leshy1::apps::self_test::selfTestResultStatusName(check.status));
        if (written < 0 || static_cast<std::size_t>(written) >= sizeof(line) - used) {
            reply.println("{\"schema\":\"leshy.self_test.report.v1\","
                          "\"kind\":\"error\",\"reason\":\"format_failed\"}");
            return;
        }
        used += static_cast<std::size_t>(written);
    }
    const int suffix = std::snprintf(
        line + used, sizeof(line) - used,
        "],\"current_owner\":\"%s\",\"current_lease_mask\":%lu}",
        appRuntime.activeApp(),
        static_cast<unsigned long>(appRuntime.activeResources()));
    if (suffix < 0 || static_cast<std::size_t>(suffix) >= sizeof(line) - used) {
        reply.println("{\"schema\":\"leshy.self_test.report.v1\","
                      "\"kind\":\"error\",\"reason\":\"format_failed\"}");
        return;
    }
    reply.println(line);
}

void emitFullGuidedRfReport(Stream& reply) {
    const std::uint32_t radioTxCommands =
        shieldReceiverProbeReport.radioTxCommands +
        fullGuidedNrf24Report.txModeEntries +
        fullGuidedNrf24Report.txPayloadCommands +
        fullGuidedCc1101Report.txStrobes;
    auto& line = diagnosticJson;
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.self_test.active_rf.v1\",\"kind\":\"report\","
        "\"plan_version\":%u,\"step\":\"%s\",\"rx_only\":true,"
        "\"resource_acquired\":%s,\"resource_released\":%s,"
        "\"cleanup_complete\":%s,"
        "\"nrf24\":{\"complete\":%s,\"passed\":%s,\"sweeps\":%lu,"
        "\"channels\":83,\"modules\":%u,\"wire\":{"
        "\"register_reads\":%lu,\"register_writes\":%lu,"
        "\"spi_bytes_clocked\":%lu,\"receive_ce_high_events\":%lu},"
        "\"cleanup_complete\":%s},"
        "\"cc1101\":{\"complete\":%s,\"passed\":%s,"
        "\"band\":\"433\",\"bins\":%u,\"wire\":{"
        "\"register_reads\":%lu,\"register_writes\":%lu,"
        "\"spi_bytes_clocked\":%lu,\"command_strobes\":%lu,"
        "\"reset_strobes\":%lu,\"receive_strobes\":%lu,"
        "\"idle_strobes\":%lu},\"cleanup_complete\":%s},"
        "\"side_effects\":{\"radio_tx_commands\":%lu,"
        "\"nrf_tx_mode_entries\":%lu,\"nrf_tx_payload_commands\":%lu,"
        "\"cc_tx_strobes\":%lu,\"cc_pa_table_writes\":%lu,"
        "\"cc_fifo_writes\":%lu,\"cc_rejected_strobes\":%lu,"
        "\"storage_write_commands\":0},"
        "\"current_owner\":\"%s\",\"current_lease_mask\":%lu}",
        static_cast<unsigned>(SelfTestReport::kPlanVersion),
        fullGuidedRfStepName(fullGuidedRfState.step),
        fullGuidedRfState.resourceAcquired ? "true" : "false",
        fullGuidedRfState.resourceReleased ? "true" : "false",
        fullGuidedRfState.cleanupComplete ? "true" : "false",
        fullGuidedRfState.nrf24Complete ? "true" : "false",
        fullGuidedRfState.nrf24Passed ? "true" : "false",
        static_cast<unsigned long>(fullGuidedNrf24Report.sweeps),
        static_cast<unsigned>(fullGuidedNrf24Report.detectedModules),
        static_cast<unsigned long>(fullGuidedNrf24Report.registerReads),
        static_cast<unsigned long>(fullGuidedNrf24Report.registerWrites),
        static_cast<unsigned long>(fullGuidedNrf24Report.spiBytesClocked),
        static_cast<unsigned long>(fullGuidedNrf24Report.receiveCeHighEvents),
        fullGuidedNrf24Report.cleanupComplete ? "true" : "false",
        fullGuidedRfState.cc1101Complete ? "true" : "false",
        fullGuidedRfState.cc1101Passed ? "true" : "false",
        static_cast<unsigned>(fullGuidedRfState.cc1101Bins),
        static_cast<unsigned long>(fullGuidedCc1101Report.registerReads),
        static_cast<unsigned long>(fullGuidedCc1101Report.registerWrites),
        static_cast<unsigned long>(fullGuidedCc1101Report.spiBytesClocked),
        static_cast<unsigned long>(fullGuidedCc1101Report.commandStrobes),
        static_cast<unsigned long>(fullGuidedCc1101Report.resetStrobes),
        static_cast<unsigned long>(fullGuidedCc1101Report.receiveStrobes),
        static_cast<unsigned long>(fullGuidedCc1101Report.idleStrobes),
        fullGuidedCc1101Report.cleanupComplete ? "true" : "false",
        static_cast<unsigned long>(radioTxCommands),
        static_cast<unsigned long>(fullGuidedNrf24Report.txModeEntries),
        static_cast<unsigned long>(fullGuidedNrf24Report.txPayloadCommands),
        static_cast<unsigned long>(fullGuidedCc1101Report.txStrobes),
        static_cast<unsigned long>(fullGuidedCc1101Report.paTableWrites),
        static_cast<unsigned long>(fullGuidedCc1101Report.fifoWrites),
        static_cast<unsigned long>(fullGuidedCc1101Report.rejectedStrobes),
        appRuntime.activeApp(),
        static_cast<unsigned long>(appRuntime.activeResources()));
    reply.println(line);
}

void emitFullGuidedArtifactReport(Stream& reply) {
    auto& line = diagnosticJson;
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.self_test.active_artifact.v1\","
        "\"kind\":\"report\",\"plan_version\":%u,\"step\":\"%s\","
        "\"read_only\":false,\"expected_cid\":\"%s\","
        "\"recovery\":{\"complete\":%s,\"passed\":%s,"
        "\"status\":\"%s\",\"generation_before\":%lu,"
        "\"generation_after\":%lu,\"observations_before\":%u,"
        "\"observations_after\":%u,\"mounted_read_only\":%s,"
        "\"cleanup_complete\":%s},"
        "\"library\":{\"complete\":%s,\"passed\":%s,"
        "\"json_bytes\":%u,\"metadata_bytes\":%u,"
        "\"csv_records\":%u,\"csv_bytes\":%u},"
        "\"capture\":{\"complete\":%s,\"applicable\":%s,"
        "\"passed\":%s,\"pcap_frames\":%u,\"pcap_bytes\":%u,"
        "\"pcap_fnv1a\":%lu},"
        "\"disposable\":{\"run_id\":\"%s\","
        "\"scratch_path\":\"%s\",\"observed_cid\":\"%s\","
        "\"identity_passed\":%s,\"scratch_preexisting\":%s,"
        "\"scratch_created\":%s,\"commit_complete\":%s,"
        "\"commit_passed\":%s,\"generation\":%lu,"
        "\"observations\":%u,\"write_calls\":%lu,"
        "\"write_bytes\":%llu,\"file_syncs\":%lu,"
        "\"directory_syncs\":%lu,\"remount_complete\":%s,"
        "\"remount_passed\":%s,\"export_complete\":%s,"
        "\"export_passed\":%s,\"json_bytes\":%u,"
        "\"metadata_bytes\":%u,\"csv_records\":%u,"
        "\"csv_bytes\":%u,\"cleanup_complete\":%s,"
        "\"cleanup_passed\":%s,\"files_removed\":%u,"
        "\"scratch_removed\":%s},"
        "\"product_continuity\":{\"complete\":%s,\"passed\":%s,"
        "\"generation_final\":%lu,\"observations_final\":%u},"
        "\"side_effects\":{\"radio_tx_commands\":0,"
        "\"disposable_storage_write_commands\":%lu,"
        "\"disposable_storage_write_bytes\":%llu,"
        "\"product_storage_write_commands\":0,"
        "\"blocked_write_attempts\":%lu},"
        "\"cleanup_complete\":%s,\"current_owner\":\"%s\","
        "\"current_lease_mask\":%lu}",
        static_cast<unsigned>(SelfTestReport::kPlanVersion),
        fullGuidedArtifactStepName(fullGuidedArtifactState.step),
        fullGuidedArtifactState.expectedFingerprint,
        fullGuidedArtifactState.recoveryComplete ? "true" : "false",
        fullGuidedArtifactState.recoveryPassed ? "true" : "false",
        productBootRecovery.status,
        static_cast<unsigned long>(
            fullGuidedArtifactState.generationBefore),
        static_cast<unsigned long>(fullGuidedArtifactState.generationAfter),
        static_cast<unsigned>(fullGuidedArtifactState.observationsBefore),
        static_cast<unsigned>(fullGuidedArtifactState.observationsAfter),
        productBootRecovery.readOnlyGuaranteed ? "true" : "false",
        productBootRecovery.cleanupComplete ? "true" : "false",
        fullGuidedArtifactState.libraryComplete ? "true" : "false",
        fullGuidedArtifactState.libraryPassed ? "true" : "false",
        static_cast<unsigned>(fullGuidedArtifactState.jsonBytes),
        static_cast<unsigned>(fullGuidedArtifactState.metadataBytes),
        static_cast<unsigned>(fullGuidedArtifactState.csvRecords),
        static_cast<unsigned>(fullGuidedArtifactState.csvBytes),
        fullGuidedArtifactState.captureComplete ? "true" : "false",
        fullGuidedArtifactState.captureApplicable ? "true" : "false",
        fullGuidedArtifactState.capturePassed ? "true" : "false",
        static_cast<unsigned>(fullGuidedArtifactState.pcapFrames),
        static_cast<unsigned>(fullGuidedArtifactState.pcapBytes),
        static_cast<unsigned long>(fullGuidedArtifactState.pcapFnv1a),
        kFullGuidedDisposableRunId,
        fullGuidedArtifactState.disposableScratchPath,
        fullGuidedArtifactState.disposableObservedFingerprint,
        fullGuidedArtifactState.disposableIdentityPassed ? "true" : "false",
        fullGuidedArtifactState.scratchPreexisting ? "true" : "false",
        fullGuidedArtifactState.scratchCreated ? "true" : "false",
        fullGuidedArtifactState.disposableCommitComplete ? "true" : "false",
        fullGuidedArtifactState.disposableCommitPassed ? "true" : "false",
        static_cast<unsigned long>(
            fullGuidedArtifactState.disposableGeneration),
        static_cast<unsigned>(
            fullGuidedArtifactState.disposableObservations),
        static_cast<unsigned long>(
            fullGuidedArtifactState.disposableStorageWriteCalls),
        static_cast<unsigned long long>(
            fullGuidedArtifactState.disposableStorageWriteBytes),
        static_cast<unsigned long>(
            fullGuidedArtifactState.disposableFileSyncs),
        static_cast<unsigned long>(
            fullGuidedArtifactState.disposableDirectorySyncs),
        fullGuidedArtifactState.disposableRemountComplete ? "true" : "false",
        fullGuidedArtifactState.disposableRemountPassed ? "true" : "false",
        fullGuidedArtifactState.disposableExportComplete ? "true" : "false",
        fullGuidedArtifactState.disposableExportPassed ? "true" : "false",
        static_cast<unsigned>(
            fullGuidedArtifactState.disposableJsonBytes),
        static_cast<unsigned>(
            fullGuidedArtifactState.disposableMetadataBytes),
        static_cast<unsigned>(
            fullGuidedArtifactState.disposableCsvRecords),
        static_cast<unsigned>(
            fullGuidedArtifactState.disposableCsvBytes),
        fullGuidedArtifactState.disposableCleanupComplete ? "true" : "false",
        fullGuidedArtifactState.disposableCleanupPassed ? "true" : "false",
        static_cast<unsigned>(
            fullGuidedArtifactState.disposableFilesRemoved),
        fullGuidedArtifactState.scratchRemoved ? "true" : "false",
        fullGuidedArtifactState.productVerifyComplete ? "true" : "false",
        fullGuidedArtifactState.productVerifyPassed ? "true" : "false",
        static_cast<unsigned long>(
            fullGuidedArtifactState.productGenerationFinal),
        static_cast<unsigned>(
            fullGuidedArtifactState.productObservationsFinal),
        static_cast<unsigned long>(
            fullGuidedArtifactState.disposableStorageWriteCalls),
        static_cast<unsigned long long>(
            fullGuidedArtifactState.disposableStorageWriteBytes),
        static_cast<unsigned long>(
            fullGuidedArtifactState.blockedWriteAttempts),
        fullGuidedArtifactState.cleanupComplete ? "true" : "false",
        appRuntime.activeApp(),
        static_cast<unsigned long>(appRuntime.activeResources()));
    reply.println(line);
}

void emitShieldReceiverProbeReport(Stream& reply) {
    const auto& report = shieldReceiverProbeReport;
    auto& line = diagnosticJson;
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.shield.receiver_probe.v1\",\"kind\":\"report\","
        "\"schema_version\":%u,\"status\":\"%s\",\"read_only\":%s,"
        "\"profile_declared\":%s,\"gps_excluded_by_profile\":%s,"
        "\"pn532_excluded_by_profile\":%s,\"nrf_slot3_gated\":%s,"
        "\"gpio21_stable_high\":%s,\"resource_acquired\":%s,"
        "\"resource_released\":%s,\"cleanup_complete\":%s,"
        "\"detected_receivers\":%u,"
        "\"nrf\":["
        "{\"slot\":1,\"detected\":%s,\"status\":%u,\"config\":%u,"
        "\"channel\":%u,\"rf_setup\":%u,\"feature\":%u},"
        "{\"slot\":2,\"detected\":%s,\"status\":%u,\"config\":%u,"
        "\"channel\":%u,\"rf_setup\":%u,\"feature\":%u}],"
        "\"cc1101\":{\"detected\":%s,\"ready\":%s,\"status\":%u,"
        "\"partnum\":%u,\"version\":%u},"
        "\"wire\":{\"nrf_register_reads\":%u,\"cc_status_reads\":%u,"
        "\"spi_bytes_clocked\":%u},"
        "\"side_effects\":{\"nrf_ce_high_events\":%u,"
        "\"cc_command_strobes\":%u,\"radio_tx_commands\":%u},"
        "\"current_owner\":\"%s\",\"current_lease_mask\":%lu}",
        static_cast<unsigned>(ShieldReceiverProbeReport::kSchemaVersion),
        leshy1::drivers::radio::shieldReceiverProbeStatusName(report.status),
        report.readOnly ? "true" : "false",
        report.profileDeclared ? "true" : "false",
        report.gpsExcludedByProfile ? "true" : "false",
        report.pn532ExcludedByProfile ? "true" : "false",
        report.nrfSlot3Gated ? "true" : "false",
        report.gpio21StableHigh ? "true" : "false",
        report.resourceAcquired ? "true" : "false",
        report.resourceReleased ? "true" : "false",
        report.cleanupComplete ? "true" : "false",
        static_cast<unsigned>(report.detectedReceivers),
        report.nrf[0].detected ? "true" : "false",
        static_cast<unsigned>(report.nrf[0].status),
        static_cast<unsigned>(report.nrf[0].config),
        static_cast<unsigned>(report.nrf[0].channel),
        static_cast<unsigned>(report.nrf[0].rfSetup),
        static_cast<unsigned>(report.nrf[0].feature),
        report.nrf[1].detected ? "true" : "false",
        static_cast<unsigned>(report.nrf[1].status),
        static_cast<unsigned>(report.nrf[1].config),
        static_cast<unsigned>(report.nrf[1].channel),
        static_cast<unsigned>(report.nrf[1].rfSetup),
        static_cast<unsigned>(report.nrf[1].feature),
        report.cc1101.detected ? "true" : "false",
        report.cc1101.ready ? "true" : "false",
        static_cast<unsigned>(report.cc1101.status),
        static_cast<unsigned>(report.cc1101.partNumber),
        static_cast<unsigned>(report.cc1101.version),
        static_cast<unsigned>(report.nrfRegisterReads),
        static_cast<unsigned>(report.ccStatusReads),
        static_cast<unsigned>(report.spiBytesClocked),
        static_cast<unsigned>(report.nrfCeHighEvents),
        static_cast<unsigned>(report.ccCommandStrobes),
        static_cast<unsigned>(report.radioTxCommands),
        appRuntime.activeApp(),
        static_cast<unsigned long>(appRuntime.activeResources()));
    reply.println(line);
}

void emitNrf24SpectrumReport(Stream& reply) {
    const auto& report = nrf24SpectrumReport;
    auto& line = diagnosticJson;
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.nrf24.spectrum.v1\",\"kind\":\"state\","
        "\"view\":\"%s\",\"display_mode\":\"%s\",\"metric\":\"%s\","
        "\"traffic_semantics\":\"activity_above_baseline\","
        "\"history_rows\":%u,"
        "\"waterfall_cadence\":\"receiver_sweep\","
        "\"waterfall_fill_target_us\":0,"
        "\"waterfall_row_period_us\":0,\"waterfall_full\":%s,"
        "\"waterfall_fill_elapsed_us\":%llu,"
        "\"waterfall_rows_emitted\":%lu,"
        "\"waterfall_measurements_consumed\":%lu,"
        "\"waterfall_measurements_skipped\":%lu,"
        "\"waterfall_source_sweeps\":%lu,"
        "\"timing\":{\"row_interval_total_us\":%llu,"
        "\"row_interval_max_us\":%llu,\"row_push_total_us\":%llu,"
        "\"row_push_max_us\":%llu,\"row_render_total_us\":%llu,"
        "\"row_render_max_us\":%llu,\"row_service_max_us\":%llu,"
        "\"nrf_chunk_max_us\":%llu,\"loop_interval_total_us\":%llu,"
        "\"loop_interval_max_us\":%llu,\"loop_count\":%llu,"
        "\"touch_poll_total_us\":%llu,\"touch_poll_max_us\":%llu,"
        "\"touch_poll_count\":%llu},"
        "\"state\":\"%s\",\"status\":\"%s\","
        "\"range_mhz\":[2402,2484],\"channels\":%u,\"dwell_us\":%u,"
        "\"modules\":%u,\"active_slot_mask\":%u,\"chunks\":%lu,"
        "\"all_available_antennas\":true,"
        "\"slot3_receive_enabled\":%s,"
        "\"sweeps\":%lu,\"total_hits\":%llu,"
        "\"active_bins\":%u,\"peak_channel\":%u,\"peak_mhz\":%u,"
        "\"rx_only\":%s,\"volatile\":true,\"adapter_active\":%s,"
        "\"profile_declared\":%s,\"nrf_slot3_gated\":%s,"
        "\"gpio21_stable_high\":%s,\"cleanup_complete\":%s,"
        "\"wire\":{\"register_reads\":%lu,\"register_writes\":%lu,"
        "\"spi_bytes_clocked\":%lu,\"receive_ce_high_events\":%lu},"
        "\"side_effects\":{\"tx_mode_entries\":%lu,"
        "\"tx_payload_commands\":%lu,\"cc_command_strobes\":%lu,"
        "\"storage_writes\":0},\"read_only_query\":true,"
        "\"current_owner\":\"%s\",\"current_lease_mask\":%lu}",
        rfSpectrumViewName(rfSpectrumView),
        leshy1::apps::spectrum::spectrumDisplayModeName(
            spectrumViewport.mode()),
        leshy1::apps::spectrum::nrf24SpectrumMetricName(
            nrf24SpectrumController.metric()),
        static_cast<unsigned>(spectrumViewport.rowsStored()),
        spectrumWaterfallCompletedUs != 0 ? "true" : "false",
        static_cast<unsigned long long>(spectrumWaterfallFillElapsedUs()),
        static_cast<unsigned long>(spectrumWaterfallRowsEmitted),
        static_cast<unsigned long>(spectrumWaterfallMeasurementsConsumed),
        static_cast<unsigned long>(spectrumWaterfallMeasurementsSkipped),
        static_cast<unsigned long>(
            nrf24SpectrumController.sweeps() >=
                    spectrumWaterfallSourceSweepBaseline
                ? nrf24SpectrumController.sweeps() -
                      spectrumWaterfallSourceSweepBaseline
                : 0U),
        static_cast<unsigned long long>(spectrumWaterfallRowIntervalTotalUs),
        static_cast<unsigned long long>(spectrumWaterfallRowIntervalMaxUs),
        static_cast<unsigned long long>(spectrumWaterfallPushTotalUs),
        static_cast<unsigned long long>(spectrumWaterfallPushMaxUs),
        static_cast<unsigned long long>(spectrumWaterfallRenderTotalUs),
        static_cast<unsigned long long>(spectrumWaterfallRenderMaxUs),
        static_cast<unsigned long long>(spectrumWaterfallServiceMaxUs),
        static_cast<unsigned long long>(nrf24SpectrumChunkMaxUs),
        static_cast<unsigned long long>(spectrumLoopIntervalTotalUs),
        static_cast<unsigned long long>(spectrumLoopIntervalMaxUs),
        static_cast<unsigned long long>(spectrumLoopCount),
        static_cast<unsigned long long>(spectrumTouchPollTotalUs),
        static_cast<unsigned long long>(spectrumTouchPollMaxUs),
        static_cast<unsigned long long>(spectrumTouchPollCount),
        leshy1::apps::spectrum::nrf24SpectrumViewStateName(
            nrf24SpectrumController.state()),
        leshy1::drivers::radio::nrf24PassiveSpectrumStatusName(report.status),
        static_cast<unsigned>(Nrf24SpectrumController::kChannelCount),
        static_cast<unsigned>(
            leshy1::drivers::radio::defaultNrf24PassiveSpectrumPlan().dwellUs),
        static_cast<unsigned>(nrf24SpectrumController.modules()),
        static_cast<unsigned>(report.activeSlotMask),
        static_cast<unsigned long>(report.chunks),
        (report.activeSlotMask & 0x04U) != 0 ? "true" : "false",
        static_cast<unsigned long>(nrf24SpectrumController.sweeps()),
        static_cast<unsigned long long>(nrf24SpectrumController.totalHits()),
        static_cast<unsigned>(nrf24SpectrumController.activeBins()),
        static_cast<unsigned>(nrf24SpectrumController.hottestChannel()),
        static_cast<unsigned>(2400U +
            nrf24SpectrumController.hottestChannel()),
        report.rxOnly ? "true" : "false",
        boardNrf24Spectrum.active() ? "true" : "false",
        report.profileDeclared ? "true" : "false",
        report.nrfSlot3Gated ? "true" : "false",
        report.gpio21StableHigh ? "true" : "false",
        report.cleanupComplete ? "true" : "false",
        static_cast<unsigned long>(report.registerReads),
        static_cast<unsigned long>(report.registerWrites),
        static_cast<unsigned long>(report.spiBytesClocked),
        static_cast<unsigned long>(report.receiveCeHighEvents),
        static_cast<unsigned long>(report.txModeEntries),
        static_cast<unsigned long>(report.txPayloadCommands),
        static_cast<unsigned long>(report.ccCommandStrobes),
        appRuntime.activeApp(),
        static_cast<unsigned long>(appRuntime.activeResources()));
    reply.println(line);
}

void emitCc1101SpectrumReport(Stream& reply) {
    const auto& report = cc1101SpectrumReport;
    const Cc1101PassiveSpectrumPlan plan = cc1101SpectrumController.plan();
    auto& line = diagnosticJson;
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.cc1101.spectrum.v1\",\"kind\":\"state\","
        "\"view\":\"%s\",\"display_mode\":\"%s\",\"history_rows\":%u,"
        "\"waterfall_cadence\":\"receiver_sweep\","
        "\"waterfall_fill_target_us\":0,"
        "\"waterfall_row_period_us\":0,\"waterfall_full\":%s,"
        "\"waterfall_fill_elapsed_us\":%llu,"
        "\"waterfall_rows_emitted\":%lu,"
        "\"waterfall_measurements_consumed\":%lu,"
        "\"waterfall_measurements_skipped\":%lu,"
        "\"waterfall_source_sweeps\":%lu,"
        "\"state\":\"%s\",\"status\":\"%s\","
        "\"band\":\"%s\",\"range_khz\":[%lu,%lu],\"bins\":%u,"
        "\"settle_us\":%u,\"ready_timeout_us\":%u,"
        "\"partnum\":%u,\"version\":%u,\"sweeps\":%lu,"
        "\"samples\":%llu,\"adapter_samples\":%lu,\"next_bin\":%u,"
        "\"latest_rssi_dbm\":%d,\"peak_khz\":%lu,"
        "\"peak_rssi_dbm\":%d,\"rx_only\":%s,\"volatile\":true,"
        "\"adapter_active\":%s,\"profile_declared\":%s,"
        "\"nrf_slot3_gated\":%s,\"gpio21_stable_high\":%s,"
        "\"cleanup_complete\":%s,"
        "\"wire\":{\"register_reads\":%lu,\"register_writes\":%lu,"
        "\"spi_bytes_clocked\":%lu,\"command_strobes\":%lu,"
        "\"reset_strobes\":%lu,\"receive_strobes\":%lu,"
        "\"idle_strobes\":%lu,\"receive_ready_timeouts\":%lu,"
        "\"transient_retries\":%lu,\"select_ready_timeouts\":%lu,"
        "\"recovery_attempts\":%lu,\"recoveries\":%lu},"
        "\"side_effects\":{\"rejected_strobes\":%lu,"
        "\"tx_strobes\":%lu,\"pa_table_writes\":%lu,"
        "\"fifo_writes\":%lu,\"storage_writes\":0},"
        "\"read_only_query\":true,\"current_owner\":\"%s\","
        "\"current_lease_mask\":%lu}",
        rfSpectrumKind == RfSpectrumKind::Cc1101
            ? rfSpectrumViewName(rfSpectrumView) : "none",
        leshy1::apps::spectrum::spectrumDisplayModeName(
            spectrumViewport.mode()),
        static_cast<unsigned>(spectrumViewport.rowsStored()),
        spectrumWaterfallCompletedUs != 0 ? "true" : "false",
        static_cast<unsigned long long>(spectrumWaterfallFillElapsedUs()),
        static_cast<unsigned long>(spectrumWaterfallRowsEmitted),
        static_cast<unsigned long>(spectrumWaterfallMeasurementsConsumed),
        static_cast<unsigned long>(spectrumWaterfallMeasurementsSkipped),
        static_cast<unsigned long>(
            cc1101SpectrumController.sweeps() >=
                    spectrumWaterfallSourceSweepBaseline
                ? cc1101SpectrumController.sweeps() -
                      spectrumWaterfallSourceSweepBaseline
                : 0U),
        leshy1::apps::spectrum::cc1101SpectrumViewStateName(
            cc1101SpectrumController.state()),
        leshy1::drivers::radio::cc1101PassiveSpectrumStatusName(
            report.status),
        leshy1::drivers::radio::cc1101SpectrumBandName(
            cc1101SpectrumController.band()),
        static_cast<unsigned long>(plan.firstKHz),
        static_cast<unsigned long>(plan.lastKHz),
        static_cast<unsigned>(Cc1101SpectrumController::kBinCount),
        static_cast<unsigned>(plan.settleUs),
        static_cast<unsigned>(plan.readyTimeoutUs),
        static_cast<unsigned>(report.partNumber),
        static_cast<unsigned>(report.version),
        static_cast<unsigned long>(cc1101SpectrumController.sweeps()),
        static_cast<unsigned long long>(cc1101SpectrumController.samples()),
        static_cast<unsigned long>(report.samples),
        static_cast<unsigned>(cc1101SpectrumController.nextBin()),
        static_cast<int>(cc1101SpectrumController.latestRssiDbm()),
        static_cast<unsigned long>(cc1101SpectrumController.peakKHz()),
        static_cast<int>(cc1101SpectrumController.peakRssiDbm()),
        report.rxOnly ? "true" : "false",
        boardCc1101Spectrum.active() ? "true" : "false",
        report.profileDeclared ? "true" : "false",
        report.nrfSlot3Gated ? "true" : "false",
        report.gpio21StableHigh ? "true" : "false",
        report.cleanupComplete ? "true" : "false",
        static_cast<unsigned long>(report.registerReads),
        static_cast<unsigned long>(report.registerWrites),
        static_cast<unsigned long>(report.spiBytesClocked),
        static_cast<unsigned long>(report.commandStrobes),
        static_cast<unsigned long>(report.resetStrobes),
        static_cast<unsigned long>(report.receiveStrobes),
        static_cast<unsigned long>(report.idleStrobes),
        static_cast<unsigned long>(report.receiveReadyTimeouts),
        static_cast<unsigned long>(report.transientRetries),
        static_cast<unsigned long>(report.selectReadyTimeouts),
        static_cast<unsigned long>(report.recoveryAttempts),
        static_cast<unsigned long>(report.recoveries),
        static_cast<unsigned long>(report.rejectedStrobes),
        static_cast<unsigned long>(report.txStrobes),
        static_cast<unsigned long>(report.paTableWrites),
        static_cast<unsigned long>(report.fifoWrites),
        appRuntime.activeApp(),
        static_cast<unsigned long>(appRuntime.activeResources()));
    reply.println(line);
}

bool commandAllowedDuringSafetyStop(const char* command) {
    if (command == nullptr) return false;
    return std::strncmp(command, "hil.begin ", 10) == 0 ||
           std::strncmp(command, "hil.end ", 8) == 0 ||
           std::strcmp(command, "metrics") == 0 ||
           std::strcmp(command, "inventory") == 0 ||
           std::strcmp(command, "ping") == 0 ||
           std::strcmp(command, "hardware.safe-outputs") == 0 ||
           std::strcmp(command, "safety.state") == 0 ||
           std::strcmp(command, "safety.restart-test confirm") == 0 ||
           std::strcmp(command, "safety.clear confirm") == 0 ||
           std::strcmp(command, "ui.state") == 0 ||
           std::strncmp(command, "ui.key ", 7) == 0 ||
           std::strcmp(command, "ui.capture") == 0 ||
           std::strcmp(command, "input.state") == 0 ||
           std::strcmp(command, "touch.state") == 0 ||
           std::strcmp(command, "storage.product.boot-recovery") == 0;
}

void handleCommand(Stream& reply, const char* command) {
    if (safetySupervisor.latched() &&
        !commandAllowedDuringSafetyStop(command)) {
        reply.println(
            "{\"schema\":\"leshy.safety.v1\",\"kind\":\"blocked\","
            "\"reason\":\"safety_latched\"}");
        return;
    }
    if (std::strncmp(command, "hil.begin ", 10) == 0) {
        emitHilSessionBegin(reply, command);
    } else if (std::strncmp(command, "hil.end ", 8) == 0) {
        emitHilSessionEnd(reply, command);
    } else if (std::strcmp(command, "metrics") == 0) {
        emitMetrics();
    } else if (std::strcmp(command, "inventory") == 0) {
        emitInventory();
    } else if (std::strcmp(command, "hardware.safe-outputs") == 0) {
        emitSafeOutputs(reply);
    } else if (std::strcmp(command, "safety.state") == 0) {
        emitSafetyState(reply);
    } else if (std::strcmp(command,
                           "safety.watchdog-test confirm") == 0) {
        triggerRuntimeSafetyWatchdogTest(reply);
    } else if (std::strcmp(command,
                           "safety.restart-test confirm") == 0) {
        restartLatchedSafetyStopForTest(reply);
    } else if (std::strcmp(command, "safety.clear confirm") == 0) {
        clearSafetyStopFromConsole(reply);
    } else if (std::strcmp(command, "hardware.shield.receivers") == 0) {
        emitShieldReceiverProbeReport(reply);
    } else if (std::strcmp(command, "hardware.nrf24.spectrum") == 0) {
        emitNrf24SpectrumReport(reply);
    } else if (std::strcmp(command, "hardware.cc1101.spectrum") == 0) {
        emitCc1101SpectrumReport(reply);
    } else if (std::strcmp(command, "ping") == 0) {
        broadcast("{\"schema\":\"leshy.boot.v1\",\"kind\":\"pong\"}");
    } else if (std::strcmp(command, "ui.state") == 0) {
        emitUiState(reply, UiAction::Unknown, false);
    } else if (std::strcmp(command, "survey.browser") == 0) {
        emitSurveyBrowser(reply);
    } else if (std::strcmp(command, "capture.state") == 0) {
        emitWifiFrameCaptureState(reply);
    } else if (std::strcmp(command, "capture.export.pcap") == 0) {
        emitWifiFrameCapturePcap(reply);
    } else if (std::strcmp(command, "capture.subghz.state") == 0) {
        emitSubGhzRawCaptureState(reply);
    } else if (std::strcmp(command,
                           "capture.subghz.export.csv") == 0) {
        emitSubGhzRawCaptureCsv(reply);
    } else if (std::strcmp(command, "capture.ir.state") == 0) {
        emitInfraredRawCaptureState(reply);
    } else if (std::strcmp(command, "capture.ir.export.csv") == 0) {
        emitInfraredRawCaptureCsv(reply);
    } else if (std::strcmp(command, "input.state") == 0) {
        emitInputState(reply);
    } else if (std::strcmp(command, "touch.state") == 0) {
        emitTouchState(reply);
    } else if (std::strcmp(command, "touch.calibrate confirm") == 0) {
        calibrateTouch(reply);
    } else if (std::strncmp(command, "ui.touch ", 9) == 0) {
        handleSyntheticTouch(reply, command);
    } else if (std::strcmp(command, "self-test.report") == 0) {
        emitSelfTestReport(reply);
    } else if (std::strcmp(command, "self-test.active-rf") == 0) {
        emitFullGuidedRfReport(reply);
    } else if (std::strcmp(command, "self-test.active-artifact") == 0) {
        emitFullGuidedArtifactReport(reply);
    } else if (std::strncmp(command, "ui.language ", 12) == 0) {
        UiLanguage requested = UiLanguage::English;
        if (!leshy1::ui::uiLanguageFromName(command + 12, &requested)) {
            reply.println("{\"schema\":\"leshy.ui.language.v1\","
                          "\"kind\":\"error\",\"reason\":\"invalid_language\"}");
        } else if (!saveUiLanguage(requested)) {
            reply.println("{\"schema\":\"leshy.ui.language.v1\","
                          "\"kind\":\"error\",\"reason\":\"persist_failed\"}");
        } else {
            const bool changed = languageController.active() != requested;
            languageController.restore(requested);
            lastRuntimeEvent = "language_persisted";
            renderInteractiveScreen();
            emitUiState(reply, UiAction::Unknown, changed);
        }
    } else if (std::strncmp(command, "ui.key ", 7) == 0) {
        const UiAction action = leshy1::ui::uiActionFromName(command + 7);
        if (action == UiAction::Unknown) {
            reply.println("{\"schema\":\"leshy.ui.v1\",\"kind\":\"error\","
                          "\"reason\":\"unknown_action\"}");
        } else {
            emitUiState(reply, action, applyUiAction(action));
        }
    } else if (std::strcmp(command, "ui.capture") == 0) {
        captureDisplay(reply);
    } else if (std::strcmp(command, "storage.contract") == 0) {
        emitStorageContract(reply);
    } else if (std::strcmp(command, "storage.guard") == 0) {
        emitStorageGuard(reply);
    } else if (std::strcmp(command, "storage.discovery") == 0) {
        emitStorageDiscovery(reply);
    } else if (std::strcmp(command, "storage.mount.policy") == 0) {
        emitStorageMountPolicy(reply);
    } else if (std::strcmp(command, "storage.product.boot-recovery") == 0) {
        emitProductBootRecovery(reply);
    } else if (std::strcmp(
                   command,
                   "storage.product.boot-watchdog-test confirm") == 0) {
        triggerProductBootWatchdogTest(reply);
    } else if (std::strcmp(command, "storage.product.unenroll confirm") == 0) {
        emitProductUnenrollment(reply);
    } else if (std::strcmp(command, "survey.product.admission") == 0) {
        emitProductSurveyAdmission(reply);
    } else if (std::strncmp(
                   command, "survey.product.test-source-unavailable ", 39) == 0) {
        emitProductSurveySourceUnavailableTest(reply, command);
    } else if (std::strncmp(
                   command, "survey.product.test-runtime-unavailable ", 40) == 0) {
        emitProductSurveyRuntimeUnavailableTest(reply, command);
    } else if (std::strncmp(command, kLittleFsParityPrefix,
                            std::strlen(kLittleFsParityPrefix)) == 0) {
        char fingerprint[65] = {};
        char runId[33] = {};
        if (parseLittleFsParityCommand(
                command, fingerprint, sizeof(fingerprint), runId,
                sizeof(runId))) {
            emitLittleFsParity(reply, fingerprint, runId);
        } else {
            reply.println(
                "{\"schema\":\"leshy.storage.littlefs.parity.v1\","
                "\"kind\":\"error\",\"reason\":\"invalid_explicit_scope\"}");
        }
    } else if (std::strncmp(
                   command, kLittleFsResetRecoverPrefix,
                   std::strlen(kLittleFsResetRecoverPrefix)) == 0) {
        char fingerprint[65] = {};
        char runId[33] = {};
        unsigned boundaryNumber = 0;
        if (parseLittleFsResetCommand(
                command, kLittleFsResetRecoverPrefix, fingerprint,
                sizeof(fingerprint), runId, sizeof(runId), &boundaryNumber)) {
            emitLittleFsResetRecovery(
                reply, fingerprint, runId, boundaryNumber);
        } else {
            reply.println(
                "{\"schema\":\"leshy.storage.littlefs.reset.v1\","
                "\"kind\":\"error\",\"mode\":\"recovery\","
                "\"reason\":\"invalid_explicit_scope\"}");
        }
    } else if (std::strncmp(command, kLittleFsResetPrefix,
                            std::strlen(kLittleFsResetPrefix)) == 0) {
        char fingerprint[65] = {};
        char runId[33] = {};
        unsigned boundaryNumber = 0;
        if (parseLittleFsResetCommand(
                command, kLittleFsResetPrefix, fingerprint,
                sizeof(fingerprint), runId, sizeof(runId), &boundaryNumber)) {
            emitLittleFsResetArm(reply, fingerprint, runId, boundaryNumber);
        } else {
            reply.println(
                "{\"schema\":\"leshy.storage.littlefs.reset.v1\","
                "\"kind\":\"error\",\"mode\":\"arm\","
                "\"reason\":\"invalid_explicit_scope\"}");
        }
    } else if (std::strcmp(command, "storage.sd.protocol") == 0) {
        emitSdReadOnlyProtocol(reply);
    } else if (std::strcmp(command, "storage.sd.identification.fixture") == 0) {
        emitSdIdentificationFixture(reply);
    } else if (std::strcmp(command, "storage.sd.transport.fixture") == 0) {
        emitSdTransportFixture(reply);
    } else if (std::strcmp(command, "storage.sd.wire") == 0) {
        emitSdWireContract(reply);
    } else if (std::strcmp(command,
                           "storage.sd.identify disposable-read-only") == 0) {
        emitPhysicalSdIdentification(reply);
    } else if (std::strcmp(command,
                           "storage.sd.inspect-lba0 disposable-read-only") == 0) {
        emitPhysicalSdSector0(reply);
    } else if (std::strcmp(command,
                           "storage.sd.inspect-boot disposable-read-only") == 0) {
        emitPhysicalSdBoot(reply);
    } else if (std::strcmp(command,
                           "storage.sd.inspect-fsinfo disposable-read-only") == 0) {
        emitPhysicalSdFsInfo(reply);
    } else if (std::strcmp(
                   command,
                   "storage.sd.inspect-fat-reserved disposable-read-only") == 0) {
        emitPhysicalSdFatReserved(reply);
    } else if (std::strcmp(
                   command,
                   "storage.sd.inspect-root-cluster disposable-read-only") == 0) {
        emitPhysicalSdRootMetadata(reply);
    } else if (std::strncmp(command, kSdReadOnlyMountPrefix,
                            std::strlen(kSdReadOnlyMountPrefix)) == 0) {
        char fingerprint[33] = {};
        if (parseExactFingerprintCommand(
                command, kSdReadOnlyMountPrefix, fingerprint,
                sizeof(fingerprint))) {
            emitPhysicalSdReadOnlyMount(reply, fingerprint);
        } else {
            reply.println(
                "{\"schema\":\"leshy.storage.sd.readonly_mount.v1\","
                "\"kind\":\"error\",\"reason\":\"invalid_explicit_scope\"}");
        }
    } else if (std::strncmp(command, kProductBootstrapPrefix,
                            std::strlen(kProductBootstrapPrefix)) == 0) {
        char fingerprint[33] = {};
        if (parseExactFingerprintCommand(
                command, kProductBootstrapPrefix, fingerprint,
                sizeof(fingerprint))) {
            emitProductStoreBootstrap(reply, fingerprint);
        } else {
            reply.println(
                "{\"schema\":\"leshy.storage.product_bootstrap.v1\","
                "\"kind\":\"error\",\"reason\":\"invalid_explicit_scope\"}");
        }
    } else if (std::strncmp(command, kProductEnrollPrefix,
                            std::strlen(kProductEnrollPrefix)) == 0) {
        char fingerprint[33] = {};
        if (parseExactFingerprintCommand(
                command, kProductEnrollPrefix, fingerprint,
                sizeof(fingerprint))) {
            emitProductEnrollment(reply, fingerprint);
        } else {
            reply.println(
                "{\"schema\":\"leshy.storage.product_enrollment.v1\","
                "\"kind\":\"error\",\"mode\":\"enroll\","
                "\"reason\":\"invalid_explicit_scope\"}");
        }
    } else if (std::strncmp(command, kSdSessionPowerCutPrefix,
                            std::strlen(kSdSessionPowerCutPrefix)) == 0) {
        char fingerprint[33] = {};
        char runId[33] = {};
        unsigned boundaryNumber = 0;
        if (parseSdSessionResetCommand(
                command, kSdSessionPowerCutPrefix, fingerprint,
                sizeof(fingerprint), runId, sizeof(runId), &boundaryNumber)) {
            emitPhysicalSdSessionResetArm(reply, fingerprint, runId,
                                          boundaryNumber, true);
        } else {
            reply.println(
                "{\"schema\":\"leshy.storage.sd.session_store_reset.v1\","
                "\"kind\":\"error\",\"mode\":\"power_cut_arm\","
                "\"reason\":\"invalid_explicit_scope\"}");
        }
    } else if (std::strncmp(command, kSdSessionPowerCutRecoverPrefix,
                            std::strlen(kSdSessionPowerCutRecoverPrefix)) == 0) {
        char fingerprint[33] = {};
        char runId[33] = {};
        unsigned boundaryNumber = 0;
        if (parseSdSessionResetCommand(
                command, kSdSessionPowerCutRecoverPrefix, fingerprint,
                sizeof(fingerprint), runId, sizeof(runId), &boundaryNumber)) {
            emitPhysicalSdSessionResetRecovery(reply, fingerprint, runId,
                                               boundaryNumber, true);
        } else {
            reply.println(
                "{\"schema\":\"leshy.storage.sd.session_store_reset.v1\","
                "\"kind\":\"error\",\"mode\":\"power_cut_recovery\","
                "\"reason\":\"invalid_explicit_scope\"}");
        }
    } else if (std::strncmp(command, kSdSessionResetPrefix,
                            std::strlen(kSdSessionResetPrefix)) == 0) {
        char fingerprint[33] = {};
        char runId[33] = {};
        unsigned boundaryNumber = 0;
        if (parseSdSessionResetCommand(
                command, kSdSessionResetPrefix, fingerprint,
                sizeof(fingerprint), runId, sizeof(runId), &boundaryNumber)) {
            emitPhysicalSdSessionResetArm(reply, fingerprint, runId,
                                          boundaryNumber, false);
        } else {
            reply.println(
                "{\"schema\":\"leshy.storage.sd.session_store_reset.v1\","
                "\"kind\":\"error\",\"mode\":\"arm\","
                "\"reason\":\"invalid_explicit_scope\"}");
        }
    } else if (std::strncmp(command, kSdSessionRecoverPrefix,
                            std::strlen(kSdSessionRecoverPrefix)) == 0) {
        char fingerprint[33] = {};
        char runId[33] = {};
        unsigned boundaryNumber = 0;
        if (parseSdSessionResetCommand(
                command, kSdSessionRecoverPrefix, fingerprint,
                sizeof(fingerprint), runId, sizeof(runId), &boundaryNumber)) {
            emitPhysicalSdSessionResetRecovery(reply, fingerprint, runId,
                                               boundaryNumber, false);
        } else {
            reply.println(
                "{\"schema\":\"leshy.storage.sd.session_store_reset.v1\","
                "\"kind\":\"error\",\"mode\":\"recovery\","
                "\"reason\":\"invalid_explicit_scope\"}");
        }
    } else if (std::strncmp(command, kSdSessionBatchThroughputPrefix,
                            std::strlen(kSdSessionBatchThroughputPrefix)) == 0) {
        char fingerprint[33] = {};
        char runId[33] = {};
        if (parseSdSessionStoreCommand(
                command, kSdSessionBatchThroughputPrefix, fingerprint,
                sizeof(fingerprint), runId, sizeof(runId))) {
            emitPhysicalSdSessionStore(reply, fingerprint, runId, true, true,
                                       false, 0);
        } else {
            reply.println(
                "{\"schema\":\"leshy.storage.sd.session_store_batch_throughput.v1\","
                "\"kind\":\"error\",\"reason\":\"invalid_explicit_scope\"}");
        }
    } else if (std::strncmp(command, kSdSessionThroughputPrefix,
                            std::strlen(kSdSessionThroughputPrefix)) == 0) {
        char fingerprint[33] = {};
        char runId[33] = {};
        if (parseSdSessionStoreCommand(
                command, kSdSessionThroughputPrefix, fingerprint,
                sizeof(fingerprint), runId, sizeof(runId))) {
            emitPhysicalSdSessionStore(reply, fingerprint, runId, true, false,
                                       false, 0);
        } else {
            reply.println(
                "{\"schema\":\"leshy.storage.sd.session_store_throughput.v1\","
                "\"kind\":\"error\",\"reason\":\"invalid_explicit_scope\"}");
        }
    } else if (std::strncmp(command, kSdSessionStorePrefix,
                            std::strlen(kSdSessionStorePrefix)) == 0) {
        char fingerprint[33] = {};
        char runId[33] = {};
        if (parseSdSessionStoreCommand(
                command, kSdSessionStorePrefix, fingerprint,
                sizeof(fingerprint), runId, sizeof(runId))) {
            emitPhysicalSdSessionStore(reply, fingerprint, runId, false, false,
                                       false, 0);
        } else {
            reply.println(
                "{\"schema\":\"leshy.storage.sd.session_store.v1\","
                "\"kind\":\"error\",\"reason\":\"invalid_explicit_scope\"}");
        }
    } else if (std::strncmp(command, kWifiPersistPrefix,
                            std::strlen(kWifiPersistPrefix)) == 0) {
        char fingerprint[33] = {};
        char runId[33] = {};
        unsigned maximumScans = 0;
        if (parseWifiPersistCommand(
                command, fingerprint, sizeof(fingerprint), runId,
                sizeof(runId), &maximumScans)) {
            emitPhysicalSdSessionStore(reply, fingerprint, runId, false,
                                       false, true, maximumScans);
        } else {
            reply.println(
                "{\"schema\":\"leshy.survey.wifi_passive_persist.v1\","
                "\"kind\":\"error\",\"reason\":\"invalid_explicit_scope\"}");
        }
    } else if (std::strncmp(command, kWifiIngressPrefix,
                            std::strlen(kWifiIngressPrefix)) == 0) {
        unsigned samples = 0;
        if (parseWifiIngressCommand(command, &samples)) {
            emitPhysicalWifiPassiveIngress(reply, samples);
        } else {
            reply.println(
                "{\"schema\":\"leshy.survey.wifi_passive_ingress.v1\","
                "\"kind\":\"error\",\"reason\":\"invalid_explicit_scope\"}");
        }
    } else if (std::strcmp(command, "survey.contract") == 0) {
        emitSurveyContract(reply);
    } else if (std::strcmp(command, "session.fixture") == 0) {
        emitSessionFixture(reply);
    } else if (std::strcmp(command, "session.store.fixture") == 0) {
        emitSessionStoreFixture(reply);
    } else if (std::strcmp(command, "library.fixture") == 0) {
        emitLibraryFixture(reply);
    } else if (std::strcmp(command, "library.export") == 0) {
        emitLibraryExport(reply);
    } else if (std::strcmp(command, "library.capture") == 0) {
        emitLibraryCaptureMetadata(reply);
    } else if (std::strcmp(command, "library.export.csv") == 0) {
        emitLibraryCsvExport(reply);
    } else if (std::strcmp(command, "library.export.pcap") == 0) {
        emitLibraryPcapStatus(reply);
    } else if (command[0] != '\0') {
        reply.println("{\"schema\":\"leshy.boot.v1\",\"kind\":\"error\","
                      "\"reason\":\"unknown_command\"}");
    }
}

void poll(Stream& stream, char* command, std::size_t& length, std::size_t capacity) {
    while (stream.available() > 0) {
        const char value = static_cast<char>(stream.read());
        if (value == '\r') continue;
        if (value == '\n') {
            command[length] = '\0';
            handleCommand(stream, command);
            length = 0;
        } else if (length + 1 < capacity) {
            command[length++] = value;
        } else {
            length = 0;
        }
    }
}

}  // namespace

void setup() {
    bootMetrics.setupEnterUs = static_cast<std::uint64_t>(esp_timer_get_time());
    BoardSafeOutputs::establishBootInvariant();
    Serial.begin(kConsoleBaud);
    Serial0.begin(kConsoleBaud);
    // ESP-IDF lazily allocates the newlib stream and UART VFS locks on the
    // first system log write.  A Wi-Fi scan can otherwise make that first
    // write while the radio heaps are at their low-water mark, where the
    // lock allocator aborts instead of returning an error.  Pre-warm the
    // locks while the boot heap is unconstrained.
    std::fputc('\n', stdout);
    std::fflush(stdout);
    BoardSdSpiTransport::holdRadioTransmitPathsInactive();

    const bool flashMatches = ESP.getFlashChipSize() == BoardProfile::kExpectedFlashBytes;
    const bool psramMatches = psramFound() == BoardProfile::kExpectedPsram;

    bootMetrics.version = LESHY1_VERSION;
    bootMetrics.profile = BoardProfile::kId;
    bootMetrics.profileRevision = BoardProfile::kEnvelopeRevision;
    const esp_app_desc_t* appDescription = esp_app_get_description();
    if (appDescription != nullptr &&
        appDescription->magic_word == ESP_APP_DESC_MAGIC_WORD) {
        constexpr char kHex[] = "0123456789abcdef";
        for (std::size_t i = 0; i < sizeof(appDescription->app_elf_sha256); ++i) {
            const std::uint8_t value = appDescription->app_elf_sha256[i];
            runningAppElfSha256[i * 2] = kHex[value >> 4U];
            runningAppElfSha256[i * 2 + 1] = kHex[value & 0x0FU];
        }
        runningAppElfSha256[64] = '\0';
        std::memcpy(&runningAppIdentity, appDescription->app_elf_sha256,
                    sizeof(runningAppIdentity));
    }
    bootMetrics.appElfSha256 = runningAppElfSha256;
    bootMetrics.resetReason = static_cast<std::uint32_t>(esp_reset_reason());
    const SafetyRetainedRecord retainedSafety = snapshotSafetyRetainedRecord();
    safetySupervisor.restore(
        retainedSafety, runningAppIdentity,
        safetyWatchdogResetReason(bootMetrics.resetReason));
    if (safetySupervisor.latched()) {
        confirmRetainedSafetyLatch(retainedSafety);
    } else {
        clearSafetyRetainedRecord();
    }
    bootMetrics.flashBytes = ESP.getFlashChipSize();
    bootMetrics.psramFound = psramFound();
    bootMetrics.psramBytes = ESP.getPsramSize();
    bootMetrics.heapTotal = ESP.getHeapSize();
    bootMetrics.buzzerSafetyConfigured = true;
    bootMetrics.buzzerInactive = BoardSafeOutputs::buzzerHeldInactive();
    bootMetrics.runtimeReadyUs = static_cast<std::uint64_t>(esp_timer_get_time());

    ledcAttach(BoardProfile::kBacklightPin, 5000, 8);
    ledcWrite(BoardProfile::kBacklightPin, 255);
    display.init();
    display.setRotation(2);
    boardTouchInput.begin(display, millis());
    touchCalibrationRequiredAtBoot =
        boardTouchInput.calibrationSource() ==
        leshy1::platform::arduino::TouchCalibrationSource::DefaultProfile;
    touchCalibrationSucceededAtBoot = !touchCalibrationRequiredAtBoot;
    languageController.restore(loadUiLanguage());
    bootMetrics.displayReadyUs = static_cast<std::uint64_t>(esp_timer_get_time());

    Wire.begin(BoardProfile::kI2cSdaPin, BoardProfile::kI2cSclPin, kI2cHz);
    bootMetrics.inputDetected =
        probeInputAtBoot(&lastInputRaw, &bootMetrics.inputProbeAttempts);
    bootMetrics.inputProbeTransientRetries =
        bootMetrics.inputProbeAttempts == 0
            ? 0
            : static_cast<std::uint8_t>(bootMetrics.inputProbeAttempts - 1U);
    bootMetrics.inputRaw = lastInputRaw;
    physicalButtonInput.reset(lastInputRaw, millis());
    physicalInputEvents = xQueueCreate(kPhysicalInputQueueCapacity,
                                       sizeof(PhysicalInputEvent));
    if (physicalInputEvents != nullptr) {
        physicalInputTaskStarted =
            xTaskCreatePinnedToCore(pollPhysicalInput, "leshy-input", 4096,
                                    nullptr, 2, &physicalInputTaskHandle, 0) == pdPASS;
    }
    bootMetrics.inputDetected =
        bootMetrics.inputDetected && physicalInputTaskStarted;
    bootMetrics.inputReadyUs = static_cast<std::uint64_t>(esp_timer_get_time());
    if (!safetySupervisor.latched()) {
        surveyDemoReady = prepareSurveyDemo();
        libraryDemoReady = prepareLibraryDemo();
        recoverProductCatalogAtBoot();
        storageDiscovery = boardStorageAdapter.discoverReadOnly();
        storageDiscoveryReady =
            leshy1::storage::validateMediaDiscovery(storageDiscovery) ==
            leshy1::storage::MediaDiscoveryValidation::Valid;
        productSurveyWorkerReady = initializeProductSurveyWorker();
        captureStoreEvents = xQueueCreate(1, sizeof(CaptureStoreEvent));
        subGhzCaptureStoreEvents = xQueueCreate(1, sizeof(CaptureStoreEvent));
        infraredCaptureStoreEvents = xQueueCreate(1, sizeof(CaptureStoreEvent));
    } else {
        productBootRecovery.status = "safety_latched";
        productBootRecovery.cleanupComplete = true;
    }

    if (!armRuntimeSafetyWatchdog()) {
        latchSafetyStopInTask(SafetyReason::SupervisorUnavailable);
    }
    if (!BoardSafeOutputs::buzzerHeldInactive() ||
        !BoardSafeOutputs::radioTransmitPathsHeldInactive()) {
        latchSafetyStopInTask(SafetyReason::OutputInvariant);
    }

    inventory.add({"board.profile",
                   flashMatches && psramMatches ? CapabilityState::Available
                                                : CapabilityState::Fault,
                   "runtime_flash_psram",
                   flashMatches && psramMatches ? "profile_match" : "profile_mismatch"});
    inventory.add({"display.tft", CapabilityState::Declared, "render_attempted",
                   "awaiting_visual_observation"});
    inventory.add({"output.buzzer.safe",
                   bootMetrics.buzzerInactive ? CapabilityState::Available
                                              : CapabilityState::Fault,
                   "gpio2_output_low_runtime_check",
                   bootMetrics.buzzerInactive ? "inactive_boot_invariant"
                                              : "unsafe_level_or_mode"});
    inventory.add({
        "safety.supervisor",
        safetySupervisor.latched() || runtimeSafetyWatchdogReady
            ? CapabilityState::Available : CapabilityState::Declared,
        "panic_task_wdt_plus_rtc_latch",
        safetySupervisor.latched() ? "latched_safe_mode"
                                   : "runtime_watchdog_armed"});
    inventory.add({"input.pcf8574",
                   bootMetrics.inputDetected ? CapabilityState::Detected
                                             : CapabilityState::Unknown,
                   "i2c_read_only_0x20",
                   bootMetrics.inputDetected ? "raw_byte_available" : "no_read_response"});
    inventory.add({
        "input.touch",
        boardTouchInput.ready() ? CapabilityState::Available
                                : CapabilityState::Declared,
        leshy1::platform::arduino::touchCalibrationSourceName(
            boardTouchInput.calibrationSource()),
        boardTouchInput.calibrationSource() == TouchCalibrationSource::Leshy1
            ? "v1_calibration_loaded"
            : (boardTouchInput.calibrationSource() ==
                       TouchCalibrationSource::Legacy0x
                   ? "legacy_0x_calibration_loaded"
                   : "calibration_required")});
    inventory.add({"radio.wifi", CapabilityState::Declared, "esp32_s3_builtin",
                   "passive_contract_ready_driver_not_started"});
    inventory.add({
        "capture.wifi_passive",
        flashMatches && psramMatches ? CapabilityState::Available
                                     : CapabilityState::Fault,
        "explicit_promiscuous_rx_only_adapter",
        flashMatches && psramMatches ? "bounded_ram_capture_ready"
                                     : "board_profile_mismatch"});
    inventory.add({
        "capture.wifi_persistent",
        captureStoreEvents != nullptr && productBootRecovery.catalogAdmitted
            ? CapabilityState::Available : CapabilityState::Fault,
        "schema_v4_exact_media_background_commit",
        captureStoreEvents != nullptr && productBootRecovery.catalogAdmitted
            ? "privacy_confirmed_atomic_capture_ready"
            : "capture_worker_or_exact_media_unavailable"});
    inventory.add({
        "radio.ble",
        productSurveyWorkerReady && productBootRecovery.catalogAdmitted
            ? CapabilityState::Available : CapabilityState::Declared,
        "esp32_s3_builtin_receive_only",
        productSurveyWorkerReady && productBootRecovery.catalogAdmitted
            ? "passive_ble_worker_ready" : "product_worker_or_media_unavailable"});
    inventory.add({"survey.simulated",
                   surveyDemoReady ? CapabilityState::Available : CapabilityState::Fault,
                   "E-SURVEY-001_golden_trace",
                   surveyDemoReady ? "golden_data_rf_off" : "golden_data_invalid"});
    inventory.add({"library.simulated",
                   libraryDemoReady ? CapabilityState::Available : CapabilityState::Fault,
                   "E-STORAGE-005_ram_reopen",
                   libraryDemoReady ? "volatile_offline_fixture" : "ram_fixture_invalid"});
    if (productBootRecovery.catalogAdmitted) {
        inventory.add({"library.persistent_session", CapabilityState::Available,
                       "boot_readonly_product_catalog",
                       "validated_session_open"});
        inventory.add({
            "survey.persistent_passive",
            productSurveyWorkerReady ? CapabilityState::Available
                                     : CapabilityState::Fault,
            "boot_catalog_plus_bounded_worker",
            productSurveyWorkerReady
                ? "exact_media_and_cancellable_worker_ready"
                : "worker_initialization_failed"});
    }
    inventory.add({"storage.sd", CapabilityState::Unknown,
                   "E-STORAGE-006_gpio38_non_authoritative",
                   storageDiscoveryReady ? storageDiscovery.reason
                                         : "invalid_discovery_record"});
    inventory.add({"storage.atomicity", CapabilityState::Declared,
                   "E-STORAGE-001+guard_policy", "filesystem_backend_not_started"});
    inventory.add({"assembly.gps", CapabilityState::Unknown, "default_profile",
                   "not_declared_no_autodetect"});
    inventory.add({"assembly.pn532", CapabilityState::Unknown, "default_profile",
                   "not_declared_no_autodetect"});
    inventory.add({
        "shield.ir",
        BoardProfile::kRfShieldDeclared && BoardProfile::kIrDeclared
            ? CapabilityState::Declared : CapabilityState::Unknown,
        "explicit_board_profile_rx_only_gpio21",
        BoardProfile::kRfShieldDeclared && BoardProfile::kIrDeclared
            ? "raw_capture_ready_awaiting_physical_signal"
            : "explicit_profile_required"});
    inventory.add({
        "capture.ir_passive",
        BoardProfile::kRfShieldDeclared && BoardProfile::kIrDeclared &&
                infraredCaptureStoreEvents != nullptr
            ? CapabilityState::Declared : CapabilityState::Unknown,
        "bounded_polling_raw_nec_schema_v6",
        BoardProfile::kRfShieldDeclared && BoardProfile::kIrDeclared &&
                infraredCaptureStoreEvents != nullptr
            ? "rx_only_runtime_ready_awaiting_physical_signal"
            : "profile_or_worker_unavailable"});
    inventory.add({"shield.receivers",
                   BoardProfile::kRfShieldDeclared ? CapabilityState::Declared
                                                   : CapabilityState::Unknown,
                   "board_profile_full_guided_identity_probe",
                   BoardProfile::kRfShieldDeclared
                       ? "nrf1_nrf2_cc1101_read_only_probe_available"
                       : "rf_shield_not_declared"});

    appCatalog.rebuild(inventory);
    renderInteractiveScreen();
    bootMetrics.interactiveReadyUs = static_cast<std::uint64_t>(esp_timer_get_time());

    emitMetrics();
    emitInventory();
    broadcast("{\"schema\":\"leshy.boot.v1\",\"kind\":\"help\",\"commands\":["
              "\"hil.begin <session-id> <app-elf-sha256>\","
              "\"hil.end <session-id>\","
              "\"metrics\",\"inventory\",\"hardware.safe-outputs\",\"ping\","
              "\"safety.state\",\"safety.watchdog-test confirm\","
              "\"safety.clear confirm\","
              "\"hardware.shield.receivers\","
              "\"hardware.nrf24.spectrum\","
              "\"hardware.cc1101.spectrum\","
              "\"ui.state\",\"ui.key <action>\",\"survey.browser\","
              "\"capture.state\",\"capture.export.pcap\","
              "\"capture.subghz.state\","
              "\"capture.subghz.export.csv\","
              "\"capture.ir.state\",\"capture.ir.export.csv\","
              "\"input.state\",\"touch.state\","
              "\"ui.touch <x> <y>\",\"touch.calibrate confirm\","
              "\"self-test.report\",\"self-test.active-rf\","
              "\"self-test.active-artifact\","
              "\"ui.capture\",\"storage.contract\",\"storage.guard\","
              "\"storage.discovery\",\"storage.mount.policy\","
              "\"storage.product.boot-recovery\","
              "\"storage.product.boot-watchdog-test confirm\","
              "\"storage.product.unenroll confirm\","
              "\"survey.product.admission\","
              "\"survey.product.test-source-unavailable once|clear\","
              "\"survey.product.test-runtime-unavailable wifi|ble|clear\","
              "\"storage.littlefs.parity disposable-ota1 <OTA1-SHA256> <run-id>\","
              "\"storage.littlefs.reset disposable-ota1 <OTA1-SHA256> <run-id> <1..6>\","
              "\"storage.littlefs.reset recover read-only <OTA1-SHA256> <run-id> <1..6>\","
              "\"storage.sd.protocol\",\"storage.sd.identification.fixture\","
              "\"storage.sd.transport.fixture\","
              "\"storage.sd.wire\","
              "\"storage.sd.identify disposable-read-only\","
              "\"storage.sd.inspect-lba0 disposable-read-only\","
              "\"storage.sd.inspect-boot disposable-read-only\","
              "\"storage.sd.inspect-fsinfo disposable-read-only\","
              "\"storage.sd.inspect-fat-reserved disposable-read-only\","
              "\"storage.sd.inspect-root-cluster disposable-read-only\","
              "\"storage.sd.readonly-mount disposable-read-only <CID32>\","
              "\"storage.product.enroll disposable-read-only <CID32>\","
              "\"storage.product.bootstrap disposable-write <CID32>\","
              "\"storage.sd.session-store disposable-write <CID32> <run-id>\","
              "\"storage.sd.session-store throughput disposable-write <CID32> <run-id>\","
              "\"storage.sd.session-store batch-throughput disposable-write <CID32> <run-id>\","
              "\"storage.sd.session-store reset disposable-write <CID32> <run-id> <1..6>\","
              "\"storage.sd.session-store recover disposable-read-only <CID32> <run-id> <1..6>\","
              "\"storage.sd.session-store power-cut disposable-write <CID32> <run-id> <1..6>\","
              "\"storage.sd.session-store power-cut-recover disposable-read-only <CID32> <run-id> <1..6>\","
              "\"survey.wifi.passive-persist disposable-write <CID32> <run-id> <1..8>\","
              "\"survey.wifi.passive-ingress measure passive-only <1..32>\","
              "\"survey.contract\",\"session.fixture\",\"session.store.fixture\","
              "\"library.fixture\",\"library.export\",\"library.capture\","
              "\"library.export.csv\",\"library.export.pcap\"]}");
}

void loop() {
    const std::uint64_t loopStartedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    if (activeReceiveSampling()) {
        if (spectrumLoopPreviousUs != 0) {
            const std::uint64_t intervalUs =
                loopStartedUs - spectrumLoopPreviousUs;
            spectrumLoopIntervalTotalUs += intervalUs;
            if (intervalUs > spectrumLoopIntervalMaxUs) {
                spectrumLoopIntervalMaxUs = intervalUs;
            }
        }
        spectrumLoopPreviousUs = loopStartedUs;
        ++spectrumLoopCount;
    }
    if (!safetySupervisor.latched()) {
        serviceProductSurveyWorker();
        serviceWifiDevicesProduct();
        serviceWifiChannelsProduct();
        serviceWifiFrameCapture();
        serviceWifiFrameCapturePersist();
        serviceSubGhzRawCapturePersist();
        serviceInfraredRawCapturePersist();
        serviceFullGuidedRfChecks();
        serviceNrf24Spectrum();
        serviceCc1101Spectrum();
        serviceSubGhzRawCapture();
        serviceInfraredCapture();
        serviceSpectrumWaterfallCadence();
    }
    const auto rawCaptureState = subGhzRawCapture.stats().state;
    const auto infraredState = infraredCapture.stats().state;
    const bool rawPulseTimingCritical =
        rawCaptureState == SubGhzRawCaptureState::Capturing ||
        infraredState == InfraredCaptureState::Capturing;
    const bool rawReceiveActive = rawPulseTimingCritical ||
        rawCaptureState == SubGhzRawCaptureState::Waiting ||
        infraredState == InfraredCaptureState::Waiting;
    // Once a burst starts, even a large diagnostic response would become a
    // fake pulse. Commands remain buffered by USB/UART and are answered after
    // the terminal gap; no evidence path is allowed to perturb the waveform.
    if (!rawPulseTimingCritical) {
        poll(Serial, usbCommand, usbLength, sizeof(usbCommand));
        poll(Serial0, uartCommand, uartLength, sizeof(uartCommand));
    }
    TouchPoint touchPress;
    const std::uint64_t touchStartedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    // The RAW page has no touch action. Avoid sharing the display/touch SPI
    // path while the receiver is waiting for or timing a burst.
    const bool touchPressed = !safetySupervisor.latched() &&
        !rawReceiveActive &&
        boardTouchInput.poll(millis(), &touchPress);
    const std::uint64_t touchElapsedUs =
        static_cast<std::uint64_t>(esp_timer_get_time()) - touchStartedUs;
    feedRuntimeSafetyWatchdog();
    if (activeReceiveSampling()) {
        spectrumTouchPollTotalUs += touchElapsedUs;
        if (touchElapsedUs > spectrumTouchPollMaxUs) {
            spectrumTouchPollMaxUs = touchElapsedUs;
        }
        ++spectrumTouchPollCount;
    }
    if (touchPressed) {
        dispatchTouchPoint(touchPress);
    }
    PhysicalInputEvent inputEvent;
    // Preserve the 0.x one-key/one-repaint order even when presses are queued.
    if (!rawPulseTimingCritical && physicalInputEvents != nullptr &&
        xQueueReceive(physicalInputEvents, &inputEvent, 0) == pdTRUE) {
        const std::uint64_t dequeuedUs =
            static_cast<std::uint64_t>(esp_timer_get_time());
        lastPhysicalInputQueueUs = dequeuedUs >= inputEvent.atUs
            ? dequeuedUs - inputEvent.atUs : 0;
        if (lastPhysicalInputQueueUs > maximumPhysicalInputQueueUs) {
            maximumPhysicalInputQueueUs = lastPhysicalInputQueueUs;
        }
        lastInputRaw = inputEvent.raw;
        bootMetrics.inputRaw = inputEvent.raw;
        const bool changed = applyUiAction(inputEvent.action, false);
        lastPhysicalInputAction = inputEvent.action;
        lastPhysicalInputChanged = changed;
        ++physicalInputDispatchedPresses;
        if (changed) {
            renderInteractiveScreen(!lastUiActionUsedIncrementalRender);
        }
        lastPhysicalInputRenderUs = changed ? lastUiRenderUs : 0;
        const std::uint64_t finishedUs =
            static_cast<std::uint64_t>(esp_timer_get_time());
        lastPhysicalInputEndToEndUs = finishedUs >= inputEvent.atUs
            ? finishedUs - inputEvent.atUs : 0;
        if (lastPhysicalInputEndToEndUs > maximumPhysicalInputEndToEndUs) {
            maximumPhysicalInputEndToEndUs = lastPhysicalInputEndToEndUs;
        }
        portENTER_CRITICAL(&physicalInputMux);
        lastInputRaw = physicalButtonInput.stableRaw();
        portEXIT_CRITICAL(&physicalInputMux);
        bootMetrics.inputRaw = lastInputRaw;
    }
    if (activeReceiveSampling()) {
        // The receiver itself now clocks the waterfall: yield to the RTOS but
        // do not add an artificial per-bin delay to a physical sweep.
        yield();
    } else {
        delay(2);
    }
}
