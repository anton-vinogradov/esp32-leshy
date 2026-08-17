#include <Arduino.h>
#include <Preferences.h>
#include <SPI.h>
#include <TFT_eSPI.h>
#include <Wire.h>

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
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>

#include "apps/library/LibraryController.h"
#include "apps/library/SessionCatalog.h"
#include "apps/self_test/SelfTestController.h"
#include "apps/survey/ProductSurveyAdmission.h"
#include "apps/survey/SurveyController.h"
#include "apps/survey/SurveyPipeline.h"
#include "apps/survey/SurveyWorkflow.h"
#include "boards/esp32_div_v2/BoardProfile.h"
#include "domain/apps/AppCatalog.h"
#include "domain/hardware/HardwareInventory.h"
#include "domain/observations/Observation.h"
#include "drivers/wifi/WifiPassiveContract.h"
#include "kernel/runtime/AppRuntime.h"
#include "kernel/runtime/ResourceBroker.h"
#include "platform/arduino/BoardSafeOutputs.h"
#include "platform/arduino/ArduinoFsSessionStoreIo.h"
#include "platform/arduino/BoardSdFilesystem.h"
#include "platform/arduino/BoardStorageAdapter.h"
#include "platform/arduino/BoardSdSpiTransport.h"
#include "platform/arduino/BoardWifiPassiveScanner.h"
#include "platform/arduino/RamSessionStoreIo.h"
#include "services/diagnostics/BootReport.h"
#include "services/diagnostics/HilSession.h"
#include "services/survey/IngressTiming.h"
#include "services/survey/ObservationQueue.h"
#include "services/survey/SessionBatchPolicy.h"
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
#include "ui/UiComponents.h"
#include "ui/UiController.h"
#include "ui/UiStrings.h"
#include "ui/VisualTheme.h"
#include "ui/fonts/PTSansNarrowGfx.h"

namespace {

using leshy1::boards::esp32_div_v2::BoardProfile;
using leshy1::apps::library::LibraryController;
using leshy1::apps::library::LibraryEntry;
using leshy1::apps::library::LibraryView;
using leshy1::apps::library::SessionCatalog;
using leshy1::apps::library::SessionIntegrity;
using leshy1::apps::self_test::SelfTestController;
using leshy1::apps::self_test::SelfTestFacts;
using leshy1::apps::self_test::SelfTestMode;
using leshy1::apps::self_test::SelfTestReport;
using leshy1::apps::self_test::SelfTestResultStatus;
using leshy1::apps::self_test::SelfTestView;
using leshy1::apps::survey::SurveyController;
using leshy1::apps::survey::SurveyPipeline;
using leshy1::apps::survey::SurveyPipelineProgress;
using leshy1::apps::survey::SurveyPipelineStatus;
using leshy1::apps::survey::SurveyView;
using leshy1::apps::survey::SurveyWorkflow;
using leshy1::apps::survey::SurveyWorkflowState;
using leshy1::apps::survey::SurveyWorkflowStatus;
using leshy1::domain::apps::AppCatalog;
using leshy1::domain::apps::AppMenuItem;
using leshy1::domain::hardware::CapabilityRecord;
using leshy1::domain::hardware::CapabilityState;
using leshy1::domain::hardware::HardwareInventory;
using leshy1::domain::observations::Observation;
using leshy1::drivers::wifi::WifiScanRecord;
using leshy1::kernel::runtime::AppRuntime;
using leshy1::kernel::runtime::LaunchStatus;
using leshy1::kernel::runtime::Resource;
using leshy1::kernel::runtime::ResourceBroker;
using leshy1::platform::arduino::BoardSafeOutputs;
using leshy1::platform::arduino::ArduinoFsSessionStoreIo;
using leshy1::platform::arduino::ArduinoFsSessionStoreWorkspace;
using leshy1::platform::arduino::BoardSdFilesystem;
using leshy1::platform::arduino::BoardStorageAdapter;
using leshy1::platform::arduino::BoardSdSpiTransport;
using leshy1::platform::arduino::BoardWifiPassiveScanner;
using leshy1::platform::arduino::BoardWifiPassiveScanResult;
using leshy1::platform::arduino::WifiRecordDisposition;
using leshy1::platform::arduino::RamSessionStoreIo;
using leshy1::services::diagnostics::BootMetrics;
using leshy1::services::diagnostics::HilSession;
using leshy1::services::diagnostics::HilSessionStatus;
using leshy1::services::survey::SessionState;
using leshy1::services::survey::SessionStatus;
using leshy1::services::survey::SurveySession;
using leshy1::ui::UiAction;
using leshy1::ui::UiController;
using leshy1::ui::UiLanguage;
using leshy1::ui::UiTextId;
using leshy1::ui::UiTextRole;
using leshy1::ui::LanguageController;
using leshy1::ui::Pcf8574ButtonInput;
using leshy1::ui::visual::Layout;
using leshy1::ui::visual::Palette;
using leshy1::ui::visual::Components;
using leshy1::ui::visual::Rect;
using leshy1::ui::visual::Tone;

constexpr std::uint32_t kConsoleBaud = 115200;
constexpr std::uint32_t kI2cHz = 100000;
constexpr leshy1::kernel::runtime::ResourceOwner kSdIdentificationOwner = 2;
constexpr leshy1::kernel::runtime::ResourceOwner kWifiIngressOwner = 3;
constexpr leshy1::kernel::runtime::ResourceOwner kBootCatalogOwner = 4;
constexpr std::size_t kSdThroughputSamples = 32;
constexpr std::size_t kWifiIngressMaxSamples = 32;
constexpr std::uint64_t kWifiIngressP99EncodedBytesPerSecond = 546;
constexpr std::uint32_t kStorageRateSafetyMultiplier = 4;
constexpr std::uint64_t kStorageRequiredEncodedBytesPerSecond =
    kWifiIngressP99EncodedBytesPerSecond * kStorageRateSafetyMultiplier;
constexpr std::uint64_t kProductSurveyCommitBytes = 64U * 1024U;
constexpr std::uint64_t kProductSurveyReserveBytes = 1024U * 1024U;
constexpr unsigned kWifiPersistMaxScans = 8;
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
constexpr const char* kSdReadOnlyMountPrefix =
    "storage.sd.readonly-mount disposable-read-only ";
constexpr const char* kWifiIngressPrefix =
    "survey.wifi.passive-ingress measure passive-only ";
constexpr const char* kProductBootstrapPrefix =
    "storage.product.bootstrap disposable-write ";
constexpr const char* kProductEnrollPrefix =
    "storage.product.enroll disposable-read-only ";
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
SurveySession librarySession;
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
UiController uiController;
LanguageController languageController;
SelfTestController selfTestController;
constexpr std::size_t kConsoleCommandCapacity = 128;
constexpr char kLongestConsoleCommand[] =
    "storage.sd.session-store recover disposable-read-only "
    "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF s1-session-store-20260816-a 6";
static_assert(sizeof(kLongestConsoleCommand) <= kConsoleCommandCapacity,
              "console command buffer cannot hold the longest command");
char usbCommand[kConsoleCommandCapacity] = {};
char uartCommand[kConsoleCommandCapacity] = {};
char diagnosticJson[3072] = {};
std::size_t usbLength = 0;
std::size_t uartLength = 0;
std::uint8_t lastInputRaw = 0xFF;
Pcf8574ButtonInput physicalButtonInput;

struct PhysicalInputEvent final {
    UiAction action = UiAction::Unknown;
    std::uint8_t raw = 0xFF;
    std::uint32_t atMs = 0;
};

constexpr UBaseType_t kPhysicalInputQueueCapacity = 64;
QueueHandle_t physicalInputEvents = nullptr;
TaskHandle_t physicalInputTaskHandle = nullptr;
portMUX_TYPE physicalInputMux = portMUX_INITIALIZER_UNLOCKED;
std::uint32_t physicalInputQueueDrops = 0;
std::uint32_t physicalInputQueueHighWater = 0;
std::uint32_t physicalInputDispatchedPresses = 0;
bool physicalInputTaskStarted = false;

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
};

ProductSurveyRuntimeState productSurveyRuntime;

void renderInteractiveScreen();
void broadcast(const char* line);

struct SdPhysicalEvidenceWorkspace final {
    char line[4608] = {};
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

WifiRecordDisposition enqueueProductSurveyRecord(
    const WifiScanRecord& record, std::uint64_t monotonicUs, void*) {
    Observation observation;
    if (!leshy1::drivers::wifi::normalizePassiveRecord(
            record, monotonicUs, &observation)) {
        return WifiRecordDisposition::Rejected;
    }
    const SurveyPipelineStatus status = surveyPipeline.enqueue(observation);
    if (status == SurveyPipelineStatus::Queued) {
        return WifiRecordDisposition::Accepted;
    }
    return status == SurveyPipelineStatus::Dropped
               ? WifiRecordDisposition::Dropped
               : WifiRecordDisposition::Rejected;
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
    productSurveyRuntime = {};
    productSurveyRuntime.status = "preparing";
    productSurveyRuntime.selected = true;
    productSurveyRuntime.cleanupComplete = false;
    const auto required =
        leshy1::kernel::runtime::resourceMask(Resource::UiForeground) |
        leshy1::kernel::runtime::resourceMask(Resource::EspRf) |
        leshy1::kernel::runtime::resourceMask(Resource::Storage) |
        leshy1::kernel::runtime::resourceMask(Resource::RadioSpi);
    if ((appRuntime.activeResources() & required) != required) {
        return failProductSurveyStart("resources_missing");
    }
    if (!loadProductFingerprint(productSurveyRuntime.expectedFingerprint,
                                sizeof(productSurveyRuntime.expectedFingerprint))) {
        return failProductSurveyStart("enrollment_missing");
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
            policy.ownedResources = appRuntime.activeResources();
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
            identity.status == leshy1::storage::SdTransportRunStatus::Valid) {
            break;
        }
        const leshy1::storage::ProductStartIdentityRetryEvidence retryEvidence{
            true,
            true,
            exactCidFingerprint(productSurveyRuntime.expectedFingerprint),
            (appRuntime.activeResources() & required) == required,
            identityTransport.physicalSpiStarted(),
            identity.status,
            std::strcmp(
                productSurveyRuntime.observedFingerprint,
                "00000000000000000000000000000000") == 0,
            productSurveyRuntime.identityCleanupComplete,
            productSurveyRuntime.filesystemAttempted,
        };
        if (!leshy1::storage::shouldRetryProductStartIdentity(
                retryEvidence, attempt)) {
            break;
        }
        delay(leshy1::storage::productStartIdentityRetryDelayMs(attempt));
    }
    if (!productSurveyRuntime.identityCleanupComplete ||
        identity.status != leshy1::storage::SdTransportRunStatus::Valid) {
        return failProductSurveyStart("identity_failed");
    }
    if (std::strcmp(productSurveyRuntime.expectedFingerprint,
                    productSurveyRuntime.observedFingerprint) != 0) {
        return failProductSurveyStart("fingerprint_mismatch");
    }

    productSurveyRuntime.filesystemAttempted = true;
    if (!productSurveyFilesystem.begin()) {
        return failProductSurveyStart("mount_failed");
    }
    productSurveyRuntime.cardCapacityBytes =
        productSurveyFilesystem.cardCapacityBytes();
    productSurveyRuntime.cachedFreeBytes =
        productSurveyFilesystem.cachedFreeBytes();
    const bool capacityMatched =
        productSurveyRuntime.cardCapacityBytes != 0 &&
        productSurveyRuntime.cardCapacityBytes ==
            identity.identity.capacityBytes;
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
    storeRequest.ownedResources = appRuntime.activeResources();
    const leshy1::storage::ProductStorePermit storePermit =
        leshy1::storage::authorizeProductStore(media, storeRequest);
    productSurveyRuntime.storeStatus = storePermit.status;
    if (!storePermit.allowed()) {
        return failProductSurveyStart(
            leshy1::storage::productStoreAccessStatusName(storePermit.status));
    }

    BoardWifiPassiveScanner scanner;
    const bool scannerBegun = scanner.begin();
    leshy1::apps::survey::ProductSurveyRequest surveyRequest;
    surveyRequest.explicitStart = true;
    surveyRequest.sourceAvailable = scannerBegun;
    surveyRequest.scanPlan = leshy1::drivers::wifi::defaultPassivePlan();
    surveyRequest.storePermit = storePermit;
    surveyRequest.ownedResources = appRuntime.activeResources();
    const leshy1::apps::survey::ProductSurveyPermit surveyPermit =
        leshy1::apps::survey::authorizeProductSurvey(surveyRequest);
    productSurveyRuntime.admissionStatus = surveyPermit.status;
    if (!surveyPermit.allowed()) {
        productSurveyRuntime.scannerCleanupComplete = scanner.end();
        return failProductSurveyStart(
            leshy1::apps::survey::productSurveyAdmissionStatusName(
                surveyPermit.status));
    }
    if (!productSurveyStore.selectDrive(productSurveyFilesystem.driveNumber()) ||
        !productSurveyStore.openExistingWritable(storePermit)) {
        productSurveyRuntime.scannerCleanupComplete = scanner.end();
        return failProductSurveyStart("store_open_failed");
    }
    surveyStoreRouter.bind(productSurveyStore);
    if (surveyWorkflow.configure(true, false) != SurveyWorkflowStatus::Ready) {
        productSurveyRuntime.scannerCleanupComplete = scanner.end();
        return failProductSurveyStart("workflow_config_failed");
    }

    std::uint64_t startedUs = static_cast<std::uint64_t>(esp_timer_get_time());
    if (startedUs == 0) startedUs = 1;
    if (surveyPipeline.start("product-wifi-live", startedUs) !=
        SurveyPipelineStatus::Started) {
        productSurveyRuntime.scannerCleanupComplete = scanner.end();
        return failProductSurveyStart("workflow_start_failed");
    }
    productSurveyRuntime.scan = scanner.scan(
        surveyRequest.scanPlan, enqueueProductSurveyRecord, nullptr);
    productSurveyRuntime.scannerCleanupComplete = scanner.end();
    if (!productSurveyRuntime.scan.valid() ||
        !productSurveyRuntime.scannerCleanupComplete) {
        return failProductSurveyStart("scan_failed");
    }
    if (surveyPipeline.drain(
            leshy1::services::survey::ObservationQueue::kCapacity) !=
        SurveyPipelineStatus::Drained) {
        return failProductSurveyStart("pipeline_drain_failed");
    }
    productSurveyRuntime.backendOpen = true;
    productSurveyRuntime.status = "running";
    lastRuntimeEvent = "product_survey_running";
    return true;
}

SurveyPipelineStatus stopProductSurvey() {
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

extern "C" void IRAM_ATTR esp_task_wdt_isr_user_handler() {
    // The Task WDT ISR is the last-resort path when the scheduler-based
    // watchdog cannot run. Only claim the already armed recovery attempt and
    // retain its reason; the configured panic path performs the reset.
    recordProductBootRecoveryTimeout();
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
    char line[256] = {};
    std::snprintf(
        line, sizeof(line),
        "{\"schema\":\"leshy.hardware.safe-outputs.v1\",\"kind\":\"state\","
        "\"buzzer_pin\":%d,\"buzzer_active_level\":\"high\","
        "\"buzzer_mode\":\"output\",\"buzzer_level\":\"%s\","
        "\"buzzer_inactive\":%s}",
        BoardProfile::kBuzzerPin, buzzerInactive ? "low" : "high",
        buzzerInactive ? "true" : "false");
    reply.println(line);
}

bool readInputRaw(std::uint8_t* value) {
    if (value == nullptr) return false;
    const std::uint8_t received = Wire.requestFrom(BoardProfile::kPcf8574Address,
                                                   static_cast<std::uint8_t>(1), true);
    if (received != 1 || Wire.available() == 0) return false;
    *value = static_cast<std::uint8_t>(Wire.read());
    return true;
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
        display.setFreeFont(&PTSansNarrowBody);
    } else {
        display.setFreeFont(&PTSansNarrowMeta);
    }
    activeDisplayFont = requested;
}

std::int16_t uiFontAscent(UiTextRole role) {
    return role == UiTextRole::Body ? kPTSansNarrowBodyAscent
                                    : kPTSansNarrowMetaAscent;
}

void setUiCursor(UiTextRole role, std::int16_t x, std::int16_t top) {
    selectUiFont(role);
    display.setCursor(x, top + uiFontAscent(role));
}

void renderInput(std::uint8_t value) {
    char line[48] = {};
    std::snprintf(line, sizeof(line), tr(UiTextId::InputRawFormat), value);
    const Rect bounds = Components::inputStatus();
    display.fillRect(bounds.x, bounds.y, bounds.width, bounds.height,
                     Palette::Canvas);
    display.setTextColor(Palette::Focus, Palette::Canvas);
    setUiCursor(UiTextRole::Body, bounds.x + 4, bounds.y + 1);
    display.print(line);
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

void renderHeader(const char* title) {
    display.fillScreen(Palette::Canvas);
    const Rect header = Components::header();
    display.fillRect(header.x, header.y, header.width, header.height,
                     Palette::Header);
    display.setTextColor(Palette::TextPrimary, Palette::Header);
    display.setTextFont(4);
    activeDisplayFont = ActiveDisplayFont::None;
    display.setCursor(10, 9);
    display.print("LESHY 1.x");
    display.setTextColor(Palette::TextSecondary, Palette::Canvas);
    const Rect titleBounds = Components::title();
    setUiCursor(UiTextRole::Body, titleBounds.x + 2, titleBounds.y);
    display.print(title);
}

void renderMenuRow(Rect bounds, const char* label, const char* note,
                   bool selected, bool enabled, Tone noteTone) {
    const std::uint16_t background = selected
        ? (enabled ? Palette::SurfaceFocus : Palette::SurfaceFocusDisabled)
        : Palette::Surface;
    display.fillRoundRect(bounds.x, bounds.y, bounds.width, bounds.height,
                          Layout::Radius, background);
    display.setTextColor(selected ? Palette::Focus : Palette::TextSecondary,
                         background);
    setUiCursor(UiTextRole::Body, bounds.x + 10, bounds.y - 3);
    display.print(label);
    display.setTextColor(enabled ? toneColor(noteTone) : Palette::TextMuted,
                         background);
    setUiCursor(UiTextRole::Meta, bounds.x + 10, bounds.y + 11);
    display.print(note);
}

void renderMetric(std::uint8_t index, const char* text,
                  Tone tone = Tone::Neutral) {
    const Rect bounds = Components::metricRow(index);
    display.setTextColor(toneColor(tone), Palette::Canvas);
    setUiCursor(UiTextRole::Body, bounds.x + 2, bounds.y - 2);
    display.print(text);
}

UiTextId homeLabel(const AppMenuItem& item) {
    if (std::strcmp(item.id, "diagnostics") == 0) return UiTextId::AppDiagnostics;
    if (std::strcmp(item.id, "survey") == 0) return UiTextId::AppSurvey;
    if (std::strcmp(item.id, "library") == 0) return UiTextId::AppLibrary;
    if (std::strcmp(item.id, "language") == 0) return UiTextId::AppLanguage;
    return UiTextId::AppSelfTest;
}

UiTextId homeNote(const AppMenuItem& item) {
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
    }
    if (std::strcmp(item.id, "language") == 0) return UiTextId::NoteLanguage;
    if (std::strcmp(item.id, "self-test") == 0) return UiTextId::NoteSelfTest;
    return UiTextId::Ready;
}

void renderHome() {
    renderHeader(tr(UiTextId::HomeTitle));
    for (std::uint8_t i = 0; i < appCatalog.size(); ++i) {
        const AppMenuItem* item = appCatalog.get(i);
        if (item == nullptr) continue;
        const bool utility = std::strcmp(item->id, "self-test") == 0;
        const Rect bounds = Components::homeRow(i, utility);
        const bool selected = uiController.selection() == i;
        renderMenuRow(bounds, tr(homeLabel(*item)), tr(homeNote(*item)),
                      selected, item->enabled,
                      item->enabled ? Tone::Positive : Tone::Muted);
    }
}

SelfTestFacts snapshotSelfTestFacts() {
    std::uint32_t inputQueueDrops = 0;
    portENTER_CRITICAL(&physicalInputMux);
    inputQueueDrops = physicalInputQueueDrops;
    portEXIT_CRITICAL(&physicalInputMux);

    const CapabilityRecord* profile = inventory.find("board.profile");
    const auto uiOnly = leshy1::kernel::runtime::resourceMask(
        Resource::UiForeground);
    SelfTestFacts facts;
    facts.buildIdentityPresent = std::strlen(runningAppElfSha256) == 64;
    facts.profileMatched = profile != nullptr &&
                           profile->state == CapabilityState::Available;
    facts.displayReady = bootMetrics.displayReadyUs != 0;
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
    return facts;
}

void renderLanguagePage() {
    renderHeader(tr(UiTextId::LanguageTitle));
    const UiTextId labels[2] = {UiTextId::LanguageEnglish,
                                UiTextId::LanguageRussian};
    const UiTextId notes[2] = {UiTextId::LanguageEnglishNote,
                               UiTextId::LanguageRussianNote};
    for (std::uint8_t index = 0; index < 2; ++index) {
        renderMenuRow(Components::choiceRow(index), tr(labels[index]),
                      tr(notes[index]),
                      languageController.selection() == index, true,
                      languageController.active() ==
                              (index == 0 ? UiLanguage::English
                                          : UiLanguage::Russian)
                          ? Tone::Positive
                          : Tone::Neutral);
    }
    display.setTextColor(Palette::TextMuted, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 207);
    display.print(tr(UiTextId::LanguagePersisted));
}

void renderSelfTestPage() {
    char line[96] = {};
    if (selfTestController.view() == SelfTestView::ModeMenu) {
        renderHeader(tr(UiTextId::SelfTestTitle));
        const UiTextId labels[2] = {UiTextId::Quick, UiTextId::FullGuided};
        const UiTextId notes[2] = {UiTextId::QuickNote, UiTextId::FullNote};
        for (std::uint8_t index = 0; index < 2; ++index) {
            const bool selected = selfTestController.selection() == index;
            renderMenuRow(Components::choiceRow(index), tr(labels[index]),
                          tr(notes[index]),
                          selected, true,
                          index == 0 ? Tone::Positive : Tone::Warning);
        }
        display.setTextColor(Palette::TextMuted, Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 207);
        display.print(tr(UiTextId::SelfTestNoBoot));
        return;
    }

    if (selfTestController.view() == SelfTestView::Preflight) {
        renderHeader(tr(UiTextId::FullPreflight));
        renderMetric(0, tr(UiTextId::QuickChecks8));
        renderMetric(1, tr(UiTextId::CapabilityPlanStaged));
        renderMetric(2, tr(UiTextId::SideEffectsNone));
        renderMetric(3, tr(UiTextId::ResultBlocked), Tone::Warning);
        display.setTextColor(Palette::TextMuted, Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 203);
        display.print(tr(UiTextId::GuidedLater));
        return;
    }

    const SelfTestReport& report = selfTestController.report();
    renderHeader(report.status == SelfTestResultStatus::Pass
                     ? tr(UiTextId::SelfTestPass)
                     : (report.status == SelfTestResultStatus::Fail
                            ? tr(UiTextId::SelfTestFail)
                            : tr(UiTextId::SelfTestBlocked)));
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
                  static_cast<unsigned>(report.blocked));
    renderMetric(2, line);
    std::snprintf(line, sizeof(line), tr(UiTextId::HeapMinFormat),
                  static_cast<unsigned long>(report.facts.heapMinimum / 1024U));
    renderMetric(3, line);
    std::snprintf(line, sizeof(line), tr(UiTextId::InputDropsFormat),
                  static_cast<unsigned long>(report.facts.inputQueueDrops));
    renderMetric(4, line);
    display.setTextColor(Palette::Positive, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 218);
    display.print(tr(UiTextId::SelfTestReportUsb));
}

void renderOverview() {
    char line[80] = {};
    renderHeader(tr(UiTextId::DiagnosticsTitle));
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

void renderInventoryPage() {
    char line[96] = {};
    if (surveyWorkflow.state() == SurveyWorkflowState::Setup) {
        renderHeader(tr(UiTextId::SurveySetup));
        display.setTextColor(Palette::TextSecondary, Palette::Canvas);
        setUiCursor(UiTextRole::Body, 14, 82);
        display.print(tr(UiTextId::SourceWifi));
        setUiCursor(UiTextRole::Body, 14, 110);
        display.print(surveyWorkflow.persistent()
                          ? tr(UiTextId::StorageProduct)
                          : tr(UiTextId::StorageRamPreview));
        setUiCursor(UiTextRole::Body, 14, 138);
        display.print(surveyWorkflow.simulated()
                          ? tr(UiTextId::ModeSimulated)
                          : tr(UiTextId::ModeRealPassive));
        display.setTextColor(Palette::Focus, Palette::Canvas);
        setUiCursor(UiTextRole::Body, 14, 181);
        display.print(tr(UiTextId::SelectStart));
        display.setTextColor(Palette::Positive, Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 207);
        display.print(surveyWorkflow.simulated()
                          ? tr(UiTextId::FifoNoRf)
                          : tr(UiTextId::FifoRxOnly));
        return;
    }
    if (surveyWorkflow.state() == SurveyWorkflowState::Result) {
        renderHeader(tr(UiTextId::SurveyCommitted));
        display.setTextColor(Palette::Focus, Palette::Canvas);
        setUiCursor(UiTextRole::Body, 14, 80);
        display.print(surveySession.id());
        display.setTextColor(Palette::TextSecondary, Palette::Canvas);
        std::snprintf(line, sizeof(line), tr(UiTextId::ObservationsFormat),
                      static_cast<unsigned>(surveySession.size()));
        setUiCursor(UiTextRole::Body, 14, 120);
        display.print(line);
        std::snprintf(line, sizeof(line), tr(UiTextId::GenerationFormat),
                      static_cast<unsigned long>(surveyWorkflow.generation()));
        setUiCursor(UiTextRole::Body, 14, 148);
        display.print(line);
        setUiCursor(UiTextRole::Body, 14, 176);
        display.print(surveyWorkflow.persistent()
                          ? tr(UiTextId::StorageProduct)
                          : tr(UiTextId::StorageRamOnly));
        const SurveyPipelineProgress progress = surveyPipeline.progress();
        std::snprintf(line, sizeof(line), tr(UiTextId::PipelineFormat),
                      static_cast<unsigned>(progress.queueHighWater),
                      static_cast<unsigned long long>(progress.dropped));
        setUiCursor(UiTextRole::Meta, 14, 196);
        display.print(line);
        display.setTextColor(Palette::Positive, Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 211);
        display.print(tr(UiTextId::OneCommit));
        return;
    }
    if (surveyWorkflow.state() == SurveyWorkflowState::Error) {
        renderHeader(tr(UiTextId::SurveyError));
        display.setTextColor(Palette::Danger, Palette::Canvas);
        setUiCursor(UiTextRole::Body, 14, 82);
        display.print(leshy1::apps::survey::surveyWorkflowStatusName(
            surveyWorkflow.lastStatus()));
        display.setTextColor(Palette::TextSecondary, Palette::Canvas);
        setUiCursor(UiTextRole::Body, 14, 122);
        display.print(tr(UiTextId::PriorLibraryPreserved));
        display.setTextColor(Palette::Positive, Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 207);
        display.print(tr(UiTextId::BackNoRetry));
        return;
    }
    if (surveyController.view() == SurveyView::Detail) {
        renderHeader(tr(UiTextId::SurveyDetail));
        const Observation* observation = surveyController.selected();
        if (observation == nullptr) return;
        display.setTextFont(4);
        activeDisplayFont = ActiveDisplayFont::None;
        display.setTextColor(Palette::Focus, Palette::Canvas);
        display.setCursor(14, 88);
        display.print(observation->label.data());
        display.setTextColor(Palette::TextSecondary, Palette::Canvas);
        std::snprintf(line, sizeof(line), tr(UiTextId::ChannelFormat),
                      static_cast<unsigned>(observation->channel));
        setUiCursor(UiTextRole::Body, 14, 122);
        display.print(line);
        std::snprintf(line, sizeof(line), tr(UiTextId::FrequencyFormat),
                      static_cast<unsigned long>(observation->frequencyKhz));
        setUiCursor(UiTextRole::Body, 14, 148);
        display.print(line);
        std::snprintf(line, sizeof(line), tr(UiTextId::RssiFormat),
                      static_cast<int>(observation->rssiDbm));
        setUiCursor(UiTextRole::Body, 14, 174);
        display.print(line);
        display.setTextColor(Palette::Positive, Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 203);
        display.print(surveyWorkflow.simulated()
                          ? tr(UiTextId::SimulatedData)
                          : tr(UiTextId::RealPassive));
        return;
    }

    renderHeader(tr(UiTextId::SurveyRunning));
    display.setTextColor(Palette::Positive, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 70);
    display.print(surveyWorkflow.simulated()
                      ? tr(UiTextId::RunningSimulated)
                      : tr(UiTextId::RunningPassive));
    const SurveyPipelineProgress progress = surveyPipeline.progress();
    std::snprintf(line, sizeof(line), tr(UiTextId::FifoFormat),
                  static_cast<unsigned>(progress.queueDepth),
                  static_cast<unsigned>(progress.queueHighWater),
                  static_cast<unsigned long long>(progress.dropped));
    setUiCursor(UiTextRole::Meta, 14, 82);
    display.print(line);
    constexpr std::size_t kVisibleSurveyRows = 3;
    const std::size_t selection = surveyController.selection();
    const std::size_t firstVisible =
        selection < kVisibleSurveyRows ? 0 : selection - kVisibleSurveyRows + 1;
    const std::size_t endVisible =
        surveySession.size() < firstVisible + kVisibleSurveyRows
            ? surveySession.size()
            : firstVisible + kVisibleSurveyRows;
    for (std::size_t index = firstVisible; index < endVisible; ++index) {
        const Observation* observation = surveySession.get(index);
        if (observation == nullptr) continue;
        const std::int32_t y = 100 +
            static_cast<std::int32_t>(index - firstVisible) * 40;
        const bool selected = surveyController.selection() == index;
        const std::uint16_t background = selected ? Palette::SurfaceFocus
                                                   : Palette::Surface;
        display.fillRoundRect(Layout::Edge, y, Layout::ContentWidth, 36,
                              Layout::Radius, background);
        display.setTextColor(selected ? Palette::Focus : Palette::TextSecondary,
                             background);
        setUiCursor(UiTextRole::Body, 20, y - 2);
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
        display.setTextColor(Palette::Positive, background);
        std::snprintf(line, sizeof(line), tr(UiTextId::ChannelRssiFormat),
                      static_cast<unsigned>(observation->channel),
                      static_cast<int>(observation->rssiDbm));
        setUiCursor(UiTextRole::Meta, 146, y + 13);
        display.print(line);
    }
}

void renderLibraryPage() {
    char line[96] = {};
    const LibraryEntry* selected = libraryController.selected();
    const bool persistent = selected != nullptr && selected->persistent;
    if (libraryController.view() == LibraryView::ExportReady) {
        renderHeader(tr(UiTextId::ExportReady));
        if (selected == nullptr || selected->session == nullptr) return;
        display.setTextColor(Palette::Focus, Palette::Canvas);
        setUiCursor(UiTextRole::Body, 14, 80);
        display.print(selected->session->id());
        display.setTextColor(Palette::TextSecondary, Palette::Canvas);
        setUiCursor(UiTextRole::Body, 14, 120);
        display.print(tr(UiTextId::FormatJson));
        setUiCursor(UiTextRole::Body, 14, 146);
        display.print(tr(UiTextId::TransportSerial));
        setUiCursor(UiTextRole::Body, 14, 172);
        display.print(persistent ? tr(UiTextId::PersistedYes)
                                 : tr(UiTextId::PersistedNo));
        display.setTextColor(Palette::Positive, Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 203);
        display.print(persistent ? tr(UiTextId::PersistentMedia)
                                 : tr(UiTextId::BoundedRamSource));
        return;
    }
    if (libraryController.view() == LibraryView::SessionDetail) {
        renderHeader(tr(UiTextId::SessionDetail));
        if (selected == nullptr || selected->session == nullptr) return;
        display.setTextColor(Palette::Focus, Palette::Canvas);
        setUiCursor(UiTextRole::Body, 14, 80);
        display.print(selected->session->id());
        display.setTextColor(Palette::TextSecondary, Palette::Canvas);
        std::snprintf(line, sizeof(line), tr(UiTextId::GenerationFormat),
                      static_cast<unsigned long>(selected->generation));
        setUiCursor(UiTextRole::Body, 14, 116);
        display.print(line);
        std::snprintf(line, sizeof(line), tr(UiTextId::ObservationsFormat),
                      static_cast<unsigned>(selected->session->size()));
        setUiCursor(UiTextRole::Body, 14, 142);
        display.print(line);
        std::snprintf(line, sizeof(line), tr(UiTextId::IntegrityFormat),
                      leshy1::apps::library::sessionIntegrityName(selected->integrity));
        setUiCursor(UiTextRole::Body, 14, 168);
        display.print(line);
        display.setTextColor(Palette::Positive, Palette::Canvas);
        setUiCursor(UiTextRole::Meta, 14, 199);
        display.print(persistent ? tr(UiTextId::PersistentRecovered)
                                 : tr(UiTextId::RamVolatile));
        return;
    }

    renderHeader(tr(UiTextId::LibraryOffline));
    display.setTextColor(Palette::Positive, Palette::Canvas);
    setUiCursor(UiTextRole::Meta, 14, 70);
    display.print(persistent ? tr(UiTextId::PersistentSession)
                             : tr(UiTextId::SimulatedRam));
    for (std::size_t index = 0; index < libraryController.size(); ++index) {
        const LibraryEntry* entry = libraryController.get(index);
        if (entry == nullptr || entry->session == nullptr) continue;
        const std::int32_t y = 94 + static_cast<std::int32_t>(index) * 48;
        const bool isSelected = libraryController.selection() == index;
        const std::uint16_t background = isSelected ? Palette::SurfaceFocus
                                                    : Palette::Surface;
        display.fillRoundRect(Layout::Edge, y, Layout::ContentWidth,
                              Layout::RowHeight, Layout::Radius, background);
        display.setTextColor(isSelected ? Palette::Focus : Palette::TextSecondary,
                             background);
        setUiCursor(UiTextRole::Body, 20, y - 1);
        display.print(entry->session->id());
        display.setTextColor(Palette::Positive, background);
        std::snprintf(line, sizeof(line), tr(UiTextId::LibraryRowFormat),
                      static_cast<unsigned>(entry->session->size()),
                      static_cast<unsigned long>(entry->generation),
                      leshy1::apps::library::sessionIntegrityName(entry->integrity));
        setUiCursor(UiTextRole::Meta, 20, y + 23);
        display.print(line);
    }
}

void renderInteractiveScreen() {
    if (uiController.isRoot()) {
        renderHome();
    } else if (uiController.page() == 1) {
        renderOverview();
    } else if (uiController.page() == 2) {
        renderInventoryPage();
    } else if (uiController.page() == 3) {
        renderLibraryPage();
    } else if (uiController.page() == 4) {
        renderLanguagePage();
    } else {
        renderSelfTestPage();
    }
    const Rect divider = Components::footerDivider();
    display.drawFastHLine(divider.x, divider.y, divider.width,
                          Palette::Divider);
    renderInput(lastInputRaw);
    display.setTextColor(Palette::TextMuted, Palette::Canvas);
    const Rect hint = Components::footerHint();
    setUiCursor(UiTextRole::Meta, hint.x + 8, hint.y);
    if (uiController.isRoot()) {
        display.print(tr(UiTextId::FooterRoot));
    } else if (uiController.page() == 2 &&
               surveyWorkflow.state() == SurveyWorkflowState::Setup) {
        display.print(surveyWorkflow.simulated()
                          ? tr(UiTextId::FooterSurveySetupSim)
                          : tr(UiTextId::FooterSurveySetupReal));
    } else if (uiController.page() == 2 && surveyController.view() == SurveyView::Detail) {
        display.print(surveyWorkflow.simulated()
                          ? tr(UiTextId::FooterSurveyDetailSim)
                          : tr(UiTextId::FooterSurveyDetailReal));
    } else if (uiController.page() == 2 &&
               surveyWorkflow.state() == SurveyWorkflowState::Running) {
        display.print(surveyWorkflow.simulated()
                          ? tr(UiTextId::FooterSurveyRunSim)
                          : tr(UiTextId::FooterSurveyRunReal));
    } else if (uiController.page() == 2) {
        display.print(surveyWorkflow.simulated()
                          ? tr(UiTextId::FooterSurveyDoneSim)
                          : tr(UiTextId::FooterSurveyDoneReal));
    } else if (uiController.page() == 3 &&
               libraryController.view() == LibraryView::ExportReady) {
        display.print(tr(UiTextId::FooterLibraryExport));
    } else if (uiController.page() == 3 &&
               libraryController.view() == LibraryView::SessionDetail) {
        display.print(tr(UiTextId::FooterLibraryDetail));
    } else if (uiController.page() == 3) {
        const LibraryEntry* selected = libraryController.selected();
        display.print(selected != nullptr && selected->persistent
                          ? tr(UiTextId::FooterLibrarySd)
                          : tr(UiTextId::FooterLibraryRam));
    } else if (uiController.page() == 4 &&
               languageController.selection() <= 1) {
        display.print(tr(UiTextId::FooterLanguage));
    } else if (uiController.page() == 5 &&
               selfTestController.view() == SelfTestView::ModeMenu) {
        display.print(tr(UiTextId::FooterSelfModes));
    } else if (uiController.page() == 5 &&
               selfTestController.view() == SelfTestView::Preflight) {
        display.print(tr(UiTextId::FooterSelfPreflight));
    } else if (uiController.page() == 5) {
        display.print(tr(UiTextId::FooterSelfResult));
    } else {
        display.print(tr(UiTextId::FooterGeneric));
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
                  "\"selection\":%u,\"selected_id\":\"%s\","
                  "\"selected_enabled\":%s,\"reason\":\"%s\","
                  "\"language\":\"%s\",\"language_selection\":%u,"
                  "\"revision\":%lu}",
                  leshy1::ui::uiActionName(action), changed ? "true" : "false",
                  leshy1::ui::probePageName(uiController.page()),
                  static_cast<unsigned>(uiController.selection()),
                  selected == nullptr ? "none" : selected->id,
                  selected != nullptr && selected->enabled ? "true" : "false",
                  selected == nullptr ? "missing selection" : selected->reason,
                  leshy1::ui::uiLanguageName(languageController.active()),
                  static_cast<unsigned>(languageController.selection()),
                  static_cast<unsigned long>(uiController.revision()));
    const std::size_t length = std::strlen(line);
    if (length > 0 && length + 2300 < sizeof(line)) {
        const SurveyPipelineProgress pipelineProgress = surveyPipeline.progress();
        const SelfTestReport& selfTestReport = selfTestController.report();
        const SelfTestMode visibleSelfTestMode =
            selfTestController.view() == SelfTestView::Result
                ? selfTestReport.mode
                : selfTestController.selectedMode();
        line[length - 1] = '\0';
        std::snprintf(line + length - 1, sizeof(line) - length + 1,
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
                      "\"survey_product_selected\":%s,"
                      "\"survey_product_status\":\"%s\","
                      "\"survey_product_backend_open\":%s,"
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
                      "\"survey_product_cleanup_complete\":%s,"
                      "\"library_simulated\":%s,\"library_view\":\"%s\","
                      "\"library_entries\":%u,\"library_generation\":%lu,"
                      "\"library_persistent\":%s,"
                      "\"self_test_view\":\"%s\","
                      "\"self_test_mode\":\"%s\","
                      "\"self_test_status\":\"%s\","
                      "\"self_test_checks\":%u,\"self_test_passed\":%u,"
                      "\"self_test_failed\":%u,\"self_test_blocked\":%u,"
                      "\"self_test_read_only\":%s}",
                      lastRuntimeEvent, appRuntime.activeApp(),
                      static_cast<unsigned long>(appRuntime.activeResources()),
                      surveyWorkflow.simulated() ? "true" : "false",
                      surveyController.view() == SurveyView::Detail ? "detail" : "list",
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
                      productSurveyRuntime.selected ? "true" : "false",
                      productSurveyRuntime.status,
                      productSurveyRuntime.backendOpen ? "true" : "false",
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
                      productSurveyRuntime.cleanupComplete ? "true" : "false",
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
                      leshy1::apps::self_test::selfTestModeName(
                          visibleSelfTestMode),
                      leshy1::apps::self_test::selfTestResultStatusName(
                          selfTestReport.status),
                      static_cast<unsigned>(selfTestReport.checkCount),
                      static_cast<unsigned>(selfTestReport.passed),
                      static_cast<unsigned>(selfTestReport.failed),
                      static_cast<unsigned>(selfTestReport.blocked),
                      selfTestReport.readOnly ? "true" : "false");
    }
    reply.println(line);
}

bool applyUiAction(UiAction action, bool render = true) {
    const AppMenuItem* selected = appCatalog.get(uiController.selection());
    const bool wasRoot = uiController.isRoot();
    if (!wasRoot && uiController.page() == 2) {
        bool handled = false;
        bool changed = false;
        if (surveyWorkflow.state() == SurveyWorkflowState::Setup &&
            (action == UiAction::Select || action == UiAction::Right)) {
            handled = true;
            if (productSurveyRuntime.selected) {
                changed = startProductSurvey();
            } else {
                std::uint64_t startedUs =
                    static_cast<std::uint64_t>(esp_timer_get_time());
                if (startedUs == 0) startedUs = 1;
                const SurveyPipelineStatus started =
                    surveyPipeline.start("product-wifi-preview", startedUs);
                changed = started == SurveyPipelineStatus::Started &&
                          publishGoldenObservations(surveyPipeline);
                lastRuntimeEvent =
                    leshy1::apps::survey::surveyPipelineStatusName(
                        changed ? surveyPipeline.lastStatus() : started);
            }
        } else if (surveyWorkflow.state() == SurveyWorkflowState::Setup &&
                   (action == UiAction::Back || action == UiAction::Left)) {
            surveyPipeline.cancel();
            if (productSurveyRuntime.selected) {
                const bool cleanup = closeProductSurveyBackend();
                productSurveyRuntime.status = cleanup ? "cancelled"
                                                       : "cleanup_failed";
            }
            lastRuntimeEvent =
                leshy1::apps::survey::surveyPipelineStatusName(
                    surveyPipeline.lastStatus());
        } else if (surveyWorkflow.state() == SurveyWorkflowState::Running &&
                   surveyController.view() == SurveyView::Detail &&
            (action == UiAction::Back || action == UiAction::Left)) {
            handled = true;
            changed = surveyController.back();
        } else if (surveyWorkflow.state() == SurveyWorkflowState::Running &&
                   surveyController.view() == SurveyView::List) {
            if (action == UiAction::Up) {
                handled = true;
                changed = surveyController.previous();
            } else if (action == UiAction::Down) {
                handled = true;
                changed = surveyController.next();
            } else if (action == UiAction::Select) {
                handled = true;
                changed = surveyController.openSelected();
            } else if (action == UiAction::Right) {
                handled = true;
                const SurveyPipelineStatus status =
                    productSurveyRuntime.selected
                        ? stopProductSurvey()
                        : surveyPipeline.stopAndCommit(
                              static_cast<std::uint64_t>(esp_timer_get_time()));
                changed = status == SurveyPipelineStatus::Committed;
                if (!productSurveyRuntime.selected) {
                    lastRuntimeEvent =
                        leshy1::apps::survey::surveyPipelineStatusName(status);
                }
            } else if ((action == UiAction::Back || action == UiAction::Left) &&
                       surveyWorkflow.state() == SurveyWorkflowState::Running) {
                surveyPipeline.cancel();
                if (productSurveyRuntime.selected) {
                    const bool cleanup = closeProductSurveyBackend();
                    productSurveyRuntime.status = cleanup ? "cancelled"
                                                           : "cleanup_failed";
                }
                lastRuntimeEvent = "survey_cancelled";
            }
        }
        if (handled) {
            uiController.recordHandledAction(action);
            if (changed && render) renderInteractiveScreen();
            return changed;
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
                   action == UiAction::Right) {
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
            if (changed && render) renderInteractiveScreen();
            return changed;
        }
    }
    if (!wasRoot && uiController.page() == 4) {
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
            if (persisted && render) renderInteractiveScreen();
        }
        if (handled) {
            uiController.recordHandledAction(action);
            if (changed && render && action != UiAction::Select &&
                action != UiAction::Right) {
                renderInteractiveScreen();
            }
            return changed;
        }
    }
    if (!wasRoot && uiController.page() == 5) {
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
            changed = selfTestController.activate(snapshotSelfTestFacts(),
                                                   startedUs);
            if (selfTestController.runAwaitingFinish()) {
                selfTestController.finishRun(
                    static_cast<std::uint64_t>(esp_timer_get_time()));
                lastRuntimeEvent = leshy1::apps::self_test::
                    selfTestResultStatusName(selfTestController.report().status);
            } else if (changed) {
                lastRuntimeEvent = "self_test_preflight";
            }
        } else if (action == UiAction::Back || action == UiAction::Left) {
            changed = selfTestController.back();
            handled = changed;
            if (changed) lastRuntimeEvent = "self_test_modes";
        }
        if (handled) {
            uiController.recordHandledAction(action);
            if (changed && render) renderInteractiveScreen();
            return changed;
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
            std::strcmp(selected->id, "survey") == 0) {
            if (surveyWorkflow.state() != SurveyWorkflowState::Setup) {
                surveyPipeline.resetToSetup();
            }
            closeProductSurveyBackend();
            productSurveyRuntime = {};
            productSurveyRuntime.selected = !selected->simulated;
            const SurveyWorkflowStatus configured = surveyWorkflow.configure(
                productSurveyRuntime.selected, selected->simulated);
            if (configured != SurveyWorkflowStatus::Ready) {
                openable = false;
                lastRuntimeEvent = "survey_config_rejected";
            }
        }
    }
    const bool changed = uiController.apply(
        action, static_cast<std::uint8_t>(appCatalog.size()), openable);
    if (wantsLaunch && launchStatus == LaunchStatus::Started && !changed) {
        appRuntime.stop();
        lastRuntimeEvent = "launch_rolled_back";
    } else if (!wasRoot && uiController.isRoot() && changed) {
        appRuntime.stop();
        lastRuntimeEvent = "stopped";
    }
    if (changed && render) renderInteractiveScreen();
    return changed;
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

    char line[768] = {};
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
                                   unsigned boundaryNumber) {
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
                io, sessionStoreWorkspace, librarySession);
            initialRecovery = leshy1::storage::recoverSession(
                io, sessionStoreWorkspace,
                &sessionStoreWorkspace.validationSession);
            priorUnchanged = initialCommit.complete() &&
                initialCommit.generation == 1 && initialRecovery.valid() &&
                initialRecovery.generation == 1 &&
                inspectStoredGeneration(io, sessionStoreWorkspace, librarySession,
                                        1, &priorEvidence);
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
                    "\"reset_injection\":true,\"physical_power_cut\":false,"
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
                    static_cast<unsigned long>(filesystem.realFrequencyHz()));
                reply.println(line);
                reply.flush();
                ResetBoundaryHookContext hookContext{
                    &reply, runId, boundaryNumber};
                leshy1::storage::SessionStoreBoundaryIo injecting(
                    io, boundary, restartAtSessionStoreBoundary, &hookContext);
                interruptedCommit = leshy1::storage::commitNextSession(
                    injecting, sessionStoreWorkspace, librarySession);
                boundaryStopped = injecting.stopped();
                sequenceValid = injecting.sequenceValid();
                boundariesReached = injecting.boundariesReached();
                status = "reset_not_triggered";
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
        "\"existing_paths_deleted\":false,\"reset_injection\":true,"
        "\"physical_power_cut\":false,\"radio_tx_commands\":0}",
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
        cleanupComplete ? "true" : "false");
    reply.println(line);
}

void emitPhysicalSdSessionResetRecovery(Stream& reply,
                                        const char* expectedFingerprint,
                                        const char* runId,
                                        unsigned boundaryNumber) {
    auto& line = sdPhysicalEvidence.line;
    auto& cidHex = sdPhysicalEvidence.cidHex;
    cidHex[0] = '\0';
    const leshy1::storage::CommitStage boundary =
        resetBoundaryStage(boundaryNumber);
    const esp_reset_reason_t resetReason = esp_reset_reason();
    const bool softwareReset = resetReason == ESP_RST_SW;
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
                io, sessionStoreWorkspace, librarySession, 1, &priorEvidence);
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
        softwareReset && identityAdapterBegun && fingerprintMatched && mounted &&
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
        "\"reset_injection\":true,\"physical_power_cut\":false,"
        "\"radio_tx_commands\":0}",
        valid ? "valid" : "failed", runId, boundaryNumber,
        leshy1::storage::sessionStoreBoundaryName(boundary),
        resetExpectedRecovery(boundaryNumber),
        static_cast<unsigned>(resetReason), softwareReset ? "true" : "false",
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
        cleanupComplete ? "true" : "false");
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
    static char summary[256] = {};
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

    char line[768] = {};
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
    static char summary[256] = {};
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
    static char summary[256] = {};
    const bool valid = libraryDemoReady && entry != nullptr && entry->session != nullptr &&
                       leshy1::storage::formatSessionJsonSummary(
                           *entry->session, summary, sizeof(summary));
    char line[768] = {};
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
    static char artifact[640] = {};
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
        "\"dispatched_press_events\":%lu}",
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
        static_cast<unsigned long>(physicalInputDispatchedPresses));
    reply.println(line);
}

void emitSelfTestReport(Stream& reply) {
    const SelfTestReport& report = selfTestController.report();
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
        "\"side_effects\":{\"radio_tx_commands\":0,"
        "\"storage_write_commands\":0,\"buzzer_activations\":0},"
        "\"facts\":{\"build_identity_present\":%s,"
        "\"profile_matched\":%s,\"display_ready\":%s,"
        "\"input_frontend_ready\":%s,\"input_queue_healthy\":%s,"
        "\"buzzer_inactive\":%s,\"resource_scope_clean\":%s,"
        "\"heap_free\":%lu,\"heap_minimum\":%lu,\"heap_floor\":%lu,"
        "\"input_queue_drops\":%lu,\"run_resource_mask\":%lu},"
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
        report.facts.buildIdentityPresent ? "true" : "false",
        report.facts.profileMatched ? "true" : "false",
        report.facts.displayReady ? "true" : "false",
        report.facts.inputFrontendReady ? "true" : "false",
        report.facts.inputQueueHealthy ? "true" : "false",
        report.facts.buzzerInactive ? "true" : "false",
        report.facts.resourceScopeClean ? "true" : "false",
        static_cast<unsigned long>(report.facts.heapFree),
        static_cast<unsigned long>(report.facts.heapMinimum),
        static_cast<unsigned long>(report.facts.heapFloor),
        static_cast<unsigned long>(report.facts.inputQueueDrops),
        static_cast<unsigned long>(report.facts.activeResources));
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

void handleCommand(Stream& reply, const char* command) {
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
    } else if (std::strcmp(command, "ping") == 0) {
        broadcast("{\"schema\":\"leshy.boot.v1\",\"kind\":\"pong\"}");
    } else if (std::strcmp(command, "ui.state") == 0) {
        emitUiState(reply, UiAction::Unknown, false);
    } else if (std::strcmp(command, "input.state") == 0) {
        emitInputState(reply);
    } else if (std::strcmp(command, "self-test.report") == 0) {
        emitSelfTestReport(reply);
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
    } else if (std::strncmp(command, kSdSessionResetPrefix,
                            std::strlen(kSdSessionResetPrefix)) == 0) {
        char fingerprint[33] = {};
        char runId[33] = {};
        unsigned boundaryNumber = 0;
        if (parseSdSessionResetCommand(
                command, kSdSessionResetPrefix, fingerprint,
                sizeof(fingerprint), runId, sizeof(runId), &boundaryNumber)) {
            emitPhysicalSdSessionResetArm(reply, fingerprint, runId,
                                          boundaryNumber);
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
                                               boundaryNumber);
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
    }
    bootMetrics.appElfSha256 = runningAppElfSha256;
    bootMetrics.resetReason = static_cast<std::uint32_t>(esp_reset_reason());
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
    languageController.restore(loadUiLanguage());
    bootMetrics.displayReadyUs = static_cast<std::uint64_t>(esp_timer_get_time());

    Wire.begin(BoardProfile::kI2cSdaPin, BoardProfile::kI2cSclPin, kI2cHz);
    bootMetrics.inputDetected = readInputRaw(&lastInputRaw);
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
    surveyDemoReady = prepareSurveyDemo();
    libraryDemoReady = prepareLibraryDemo();
    recoverProductCatalogAtBoot();
    storageDiscovery = boardStorageAdapter.discoverReadOnly();
    storageDiscoveryReady = leshy1::storage::validateMediaDiscovery(storageDiscovery) ==
                            leshy1::storage::MediaDiscoveryValidation::Valid;

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
    inventory.add({"input.pcf8574",
                   bootMetrics.inputDetected ? CapabilityState::Detected
                                             : CapabilityState::Unknown,
                   "i2c_read_only_0x20",
                   bootMetrics.inputDetected ? "raw_byte_available" : "no_read_response"});
    inventory.add({"radio.wifi", CapabilityState::Declared, "esp32_s3_builtin",
                   "passive_contract_ready_driver_not_started"});
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
        inventory.add({"survey.persistent_passive", CapabilityState::Available,
                       "boot_readonly_product_catalog",
                       "exact_media_ready_for_explicit_commit"});
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
    inventory.add({"shield.ir", CapabilityState::Unknown, "HW-U09",
                   "explicit_profile_required"});

    appCatalog.rebuild(inventory);
    renderInteractiveScreen();
    bootMetrics.interactiveReadyUs = static_cast<std::uint64_t>(esp_timer_get_time());

    emitMetrics();
    emitInventory();
    broadcast("{\"schema\":\"leshy.boot.v1\",\"kind\":\"help\",\"commands\":["
              "\"hil.begin <session-id> <app-elf-sha256>\","
              "\"hil.end <session-id>\","
              "\"metrics\",\"inventory\",\"hardware.safe-outputs\",\"ping\","
              "\"ui.state\",\"ui.key <action>\",\"input.state\","
              "\"self-test.report\","
              "\"ui.capture\",\"storage.contract\",\"storage.guard\","
              "\"storage.discovery\",\"storage.mount.policy\","
              "\"storage.product.boot-recovery\","
              "\"storage.product.boot-watchdog-test confirm\","
              "\"storage.product.unenroll confirm\","
              "\"survey.product.admission\","
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
              "\"survey.wifi.passive-persist disposable-write <CID32> <run-id> <1..8>\","
              "\"survey.wifi.passive-ingress measure passive-only <1..32>\","
              "\"survey.contract\",\"session.fixture\",\"session.store.fixture\","
              "\"library.fixture\",\"library.export\"]}");
}

void loop() {
    poll(Serial, usbCommand, usbLength, sizeof(usbCommand));
    poll(Serial0, uartCommand, uartLength, sizeof(uartCommand));
    PhysicalInputEvent inputEvent;
    unsigned dispatchedThisBatch = 0;
    bool batchChanged = false;
    UiAction lastBatchAction = UiAction::Unknown;
    while (physicalInputEvents != nullptr &&
           dispatchedThisBatch < kPhysicalInputQueueCapacity &&
           xQueueReceive(physicalInputEvents, &inputEvent, 0) == pdTRUE) {
        lastInputRaw = inputEvent.raw;
        bootMetrics.inputRaw = inputEvent.raw;
        const bool changed = applyUiAction(inputEvent.action, false);
        batchChanged = changed || batchChanged;
        lastBatchAction = inputEvent.action;
        ++physicalInputDispatchedPresses;
        ++dispatchedThisBatch;
    }
    if (dispatchedThisBatch != 0) {
        portENTER_CRITICAL(&physicalInputMux);
        lastInputRaw = physicalButtonInput.stableRaw();
        portEXIT_CRITICAL(&physicalInputMux);
        bootMetrics.inputRaw = lastInputRaw;
        if (batchChanged) renderInteractiveScreen();
        else renderInput(lastInputRaw);
        char line[320] = {};
        std::snprintf(line, sizeof(line),
                      "{\"schema\":\"leshy.input.frontend.v1\","
                      "\"kind\":\"batch\",\"actions\":%u,"
                      "\"last_action\":\"%s\",\"changed\":%s,"
                      "\"dispatched_press_events\":%lu}",
                      dispatchedThisBatch,
                      leshy1::ui::uiActionName(lastBatchAction),
                      batchChanged ? "true" : "false",
                      static_cast<unsigned long>(physicalInputDispatchedPresses));
        broadcast(line);
    }
    delay(2);
}
