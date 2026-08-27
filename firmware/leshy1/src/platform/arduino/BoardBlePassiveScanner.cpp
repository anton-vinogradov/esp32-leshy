#include "BoardBlePassiveScanner.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cstdio>
#include <cstring>

#include <esp_err.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/portmacro.h>
#include <freertos/task.h>
#include <host/ble_gap.h>
#include <host/ble_hs.h>
#include <nimble/nimble_port.h>
#include <nimble/nimble_port_freertos.h>

namespace leshy1::platform::arduino {

namespace {

using AdvertisementFacts =
    domain::observations::BleAdvertisementFacts;

constexpr std::uint32_t kNimbleSyncTimeoutMs = 5000U;

struct RawAdvertisement final {
    std::array<std::uint8_t, 6> address{};
    std::array<std::uint8_t, 31> payload{};
    std::uint8_t addressType = 0;
    std::uint8_t eventType = 0;
    std::uint8_t payloadLength = 0;
    std::int8_t rssiDbm = 0;
};

struct NimbleObserverState final {
    static constexpr std::size_t kQueueCapacity = 64U;

    portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
    std::array<RawAdvertisement, kQueueCapacity> queue{};
    std::size_t readIndex = 0;
    std::size_t writeIndex = 0;
    std::size_t queued = 0;
    std::uint16_t queueDrops = 0;
    bool acceptingReports = false;
};

NimbleObserverState nimbleObserver;
bool processControllerInitializationAttempted = false;
std::atomic_bool processControllerAvailable{false};
std::atomic_bool processNimbleSynced{false};

struct RawScanContext final {
    std::array<std::array<std::uint8_t, 6>, 128> seenAddresses{};
    std::uint16_t seenCount = 0;
    std::uint16_t maximumRecords = 0;
    BleRecordVisitor visitor = nullptr;
    void* visitorContext = nullptr;
    BoardBlePassiveScanResult* result = nullptr;
};

struct UuidCandidates final {
    const std::uint8_t* uuid16 = nullptr;
    const std::uint8_t* uuid32 = nullptr;
    const std::uint8_t* uuid128 = nullptr;
    const std::uint8_t* service16 = nullptr;
    const std::uint8_t* service32 = nullptr;
    const std::uint8_t* service128 = nullptr;
};

void increment(std::uint16_t* value) {
    if (value != nullptr && *value != UINT16_MAX) ++*value;
}

std::uint8_t saturatingAdd(std::uint8_t value, std::size_t amount) {
    return static_cast<std::uint8_t>(std::min<std::size_t>(
        static_cast<std::size_t>(value) + amount, UINT8_MAX));
}

std::uint16_t serviceMask(std::uint16_t uuid) {
    struct Known final {
        std::uint16_t uuid;
        std::uint16_t mask;
    };
    static constexpr Known kKnown[] = {
        {0x1812, AdvertisementFacts::kServiceHid},
        {0x180f, AdvertisementFacts::kServiceBattery},
        {0x180d, AdvertisementFacts::kServiceHeartRate},
        {0x1809, AdvertisementFacts::kServiceThermometer},
        {0x1826, AdvertisementFacts::kServiceFitness},
        {0xfeaa, AdvertisementFacts::kServiceEddystone},
        {0xfe95, AdvertisementFacts::kServiceXiaomi},
        {0xfd5a, AdvertisementFacts::kServiceSmartTag},
        {0xfeed, AdvertisementFacts::kServiceTile},
        {0xfe9f, AdvertisementFacts::kServiceFastPair},
        {0xfd6f, AdvertisementFacts::kServiceExposure},
    };
    for (const Known& known : kKnown) {
        if (known.uuid == uuid) return known.mask;
    }
    return 0U;
}

std::uint16_t readLittleEndian16(const std::uint8_t* value) {
    return static_cast<std::uint16_t>(value[0]) |
        (static_cast<std::uint16_t>(value[1]) << 8U);
}

std::uint32_t readLittleEndian32(const std::uint8_t* value) {
    return static_cast<std::uint32_t>(value[0]) |
        (static_cast<std::uint32_t>(value[1]) << 8U) |
        (static_cast<std::uint32_t>(value[2]) << 16U) |
        (static_cast<std::uint32_t>(value[3]) << 24U);
}

void retainFirstServiceUuid(const std::uint8_t* value,
                            std::size_t width,
                            AdvertisementFacts* facts) {
    if (value == nullptr || facts == nullptr) return;
    char uuid[37] = {};
    if (width == 2U) {
        std::snprintf(uuid, sizeof(uuid), "%04x",
                      static_cast<unsigned>(readLittleEndian16(value)));
    } else if (width == 4U) {
        std::snprintf(uuid, sizeof(uuid), "%08lx",
                      static_cast<unsigned long>(readLittleEndian32(value)));
    } else if (width == 16U) {
        // Bluetooth transmits a 128-bit UUID least-significant octet first.
        std::snprintf(
            uuid, sizeof(uuid),
            "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-"
            "%02x%02x%02x%02x%02x%02x",
            value[15], value[14], value[13], value[12],
            value[11], value[10], value[9], value[8],
            value[7], value[6], value[5], value[4],
            value[3], value[2], value[1], value[0]);
    } else {
        return;
    }

    std::uint32_t hash = 2166136261UL;
    for (const char* character = uuid; *character != '\0'; ++character) {
        hash ^= static_cast<std::uint8_t>(*character);
        hash *= 16777619UL;
    }
    facts->firstServiceUuidHash = hash;
    const char* visible = uuid;
    char compact[7] = {};
    const std::size_t uuidLength = std::strlen(uuid);
    if (uuidLength > 10U) {
        std::snprintf(compact, sizeof(compact), "0x%.4s", uuid + 4);
        visible = compact;
    }
    const std::size_t visibleLength = std::min<std::size_t>(
        std::strlen(visible), facts->firstServiceUuid.size() - 1U);
    std::copy_n(visible, visibleLength, facts->firstServiceUuid.begin());
    facts->firstServiceUuid[visibleLength] = '\0';
    facts->firstServiceUuidLength =
        static_cast<std::uint8_t>(visibleLength);
}

void parseAdvertisementPayload(const RawAdvertisement& source,
                               const char** name,
                               std::size_t* nameLength,
                               AdvertisementFacts* facts) {
    if (name == nullptr || nameLength == nullptr || facts == nullptr) return;
    *name = nullptr;
    *nameLength = 0U;
    *facts = {};
    facts->present = true;
    facts->addressType = source.addressType;
    facts->advertisementType = source.eventType;
    facts->legacy = true;
    facts->scannable = source.eventType == 0U || source.eventType == 2U;
    facts->connectable = source.eventType == 0U || source.eventType == 1U;
    facts->payloadLength = source.payloadLength;

    UuidCandidates candidates;
    bool completeName = false;
    std::size_t offset = 0U;
    while (offset < source.payloadLength) {
        const std::uint8_t fieldLength = source.payload[offset++];
        if (fieldLength == 0U) break;
        if (fieldLength > source.payloadLength - offset) break;
        const std::uint8_t type = source.payload[offset];
        const std::uint8_t* data = source.payload.data() + offset + 1U;
        const std::size_t dataLength = fieldLength - 1U;

        switch (type) {
            case 0x08U:
            case 0x09U:
                if (dataLength != 0U &&
                    (!completeName || type == 0x09U)) {
                    *name = reinterpret_cast<const char*>(data);
                    *nameLength = std::min<std::size_t>(
                        dataLength,
                        domain::observations::Observation::kLabelCapacity);
                    completeName = type == 0x09U;
                }
                break;
            case 0x0aU:
                if (dataLength >= 1U) {
                    facts->txPowerKnown = true;
                    facts->txPowerDbm = static_cast<std::int8_t>(data[0]);
                }
                break;
            case 0x19U:
                if (dataLength >= 2U) {
                    facts->appearanceKnown = true;
                    facts->appearance = readLittleEndian16(data);
                }
                break;
            case 0xffU:
                facts->manufacturerDataLength = static_cast<std::uint8_t>(
                    std::min<std::size_t>(dataLength, UINT8_MAX));
                if (dataLength >= 2U) {
                    facts->companyKnown = true;
                    facts->companyId = readLittleEndian16(data);
                    if (facts->companyId == 0x004cU && dataLength >= 3U) {
                        facts->appleContinuityType = data[2];
                    }
                }
                break;
            case 0x02U:
            case 0x03U: {
                const std::size_t count = dataLength / 2U;
                facts->serviceUuidCount = saturatingAdd(
                    facts->serviceUuidCount, count);
                if (candidates.uuid16 == nullptr && count != 0U) {
                    candidates.uuid16 = data;
                }
                for (std::size_t index = 0U; index < count; ++index) {
                    facts->knownServiceMask |= serviceMask(
                        readLittleEndian16(data + index * 2U));
                }
                break;
            }
            case 0x04U:
            case 0x05U: {
                const std::size_t count = dataLength / 4U;
                facts->serviceUuidCount = saturatingAdd(
                    facts->serviceUuidCount, count);
                if (candidates.uuid32 == nullptr && count != 0U) {
                    candidates.uuid32 = data;
                }
                break;
            }
            case 0x06U:
            case 0x07U: {
                const std::size_t count = dataLength / 16U;
                facts->serviceUuidCount = saturatingAdd(
                    facts->serviceUuidCount, count);
                if (candidates.uuid128 == nullptr && count != 0U) {
                    candidates.uuid128 = data;
                }
                break;
            }
            case 0x16U:
                if (dataLength >= 2U) {
                    facts->serviceDataCount = saturatingAdd(
                        facts->serviceDataCount, 1U);
                    facts->serviceUuidCount = saturatingAdd(
                        facts->serviceUuidCount, 1U);
                    facts->knownServiceMask |= serviceMask(
                        readLittleEndian16(data));
                    if (candidates.service16 == nullptr) {
                        candidates.service16 = data;
                    }
                }
                break;
            case 0x20U:
                if (dataLength >= 4U) {
                    facts->serviceDataCount = saturatingAdd(
                        facts->serviceDataCount, 1U);
                    facts->serviceUuidCount = saturatingAdd(
                        facts->serviceUuidCount, 1U);
                    if (candidates.service32 == nullptr) {
                        candidates.service32 = data;
                    }
                }
                break;
            case 0x21U:
                if (dataLength >= 16U) {
                    facts->serviceDataCount = saturatingAdd(
                        facts->serviceDataCount, 1U);
                    facts->serviceUuidCount = saturatingAdd(
                        facts->serviceUuidCount, 1U);
                    if (candidates.service128 == nullptr) {
                        candidates.service128 = data;
                    }
                }
                break;
            default:
                break;
        }
        offset += fieldLength;
    }

    if (candidates.uuid16 != nullptr) {
        retainFirstServiceUuid(candidates.uuid16, 2U, facts);
    } else if (candidates.uuid32 != nullptr) {
        retainFirstServiceUuid(candidates.uuid32, 4U, facts);
    } else if (candidates.uuid128 != nullptr) {
        retainFirstServiceUuid(candidates.uuid128, 16U, facts);
    } else if (candidates.service16 != nullptr) {
        retainFirstServiceUuid(candidates.service16, 2U, facts);
    } else if (candidates.service32 != nullptr) {
        retainFirstServiceUuid(candidates.service32, 4U, facts);
    } else if (candidates.service128 != nullptr) {
        retainFirstServiceUuid(candidates.service128, 16U, facts);
    }
}

void clearReportQueue() {
    portENTER_CRITICAL(&nimbleObserver.lock);
    nimbleObserver.readIndex = 0U;
    nimbleObserver.writeIndex = 0U;
    nimbleObserver.queued = 0U;
    nimbleObserver.queueDrops = 0U;
    portEXIT_CRITICAL(&nimbleObserver.lock);
}

bool popReport(RawAdvertisement* report) {
    if (report == nullptr) return false;
    bool available = false;
    portENTER_CRITICAL(&nimbleObserver.lock);
    if (nimbleObserver.queued != 0U) {
        *report = nimbleObserver.queue[nimbleObserver.readIndex];
        nimbleObserver.readIndex =
            (nimbleObserver.readIndex + 1U) %
            NimbleObserverState::kQueueCapacity;
        --nimbleObserver.queued;
        available = true;
    }
    portEXIT_CRITICAL(&nimbleObserver.lock);
    return available;
}

std::uint16_t takeQueueDrops() {
    portENTER_CRITICAL(&nimbleObserver.lock);
    const std::uint16_t drops = nimbleObserver.queueDrops;
    nimbleObserver.queueDrops = 0U;
    portEXIT_CRITICAL(&nimbleObserver.lock);
    return drops;
}

void queueReport(const RawAdvertisement& report) {
    portENTER_CRITICAL(&nimbleObserver.lock);
    if (nimbleObserver.acceptingReports) {
        if (nimbleObserver.queued < NimbleObserverState::kQueueCapacity) {
            nimbleObserver.queue[nimbleObserver.writeIndex] = report;
            nimbleObserver.writeIndex =
                (nimbleObserver.writeIndex + 1U) %
                NimbleObserverState::kQueueCapacity;
            ++nimbleObserver.queued;
        } else if (nimbleObserver.queueDrops != UINT16_MAX) {
            ++nimbleObserver.queueDrops;
        }
    }
    portEXIT_CRITICAL(&nimbleObserver.lock);
}

std::uint16_t scanUnits(std::uint16_t milliseconds) {
    return static_cast<std::uint16_t>(
        (static_cast<std::uint32_t>(milliseconds) * 1000U) / 625U);
}

void setAcceptingReports(bool accepting) {
    portENTER_CRITICAL(&nimbleObserver.lock);
    nimbleObserver.acceptingReports = accepting;
    portEXIT_CRITICAL(&nimbleObserver.lock);
}

int handleNimbleGapEvent(struct ble_gap_event* event, void*) {
    if (event == nullptr || event->type != BLE_GAP_EVENT_DISC) return 0;
    const ble_gap_disc_desc& source = event->disc;
    RawAdvertisement report;
    report.addressType = source.addr.type;
    report.eventType = source.event_type;
    std::copy_n(source.addr.val, report.address.size(),
                report.address.begin());
    report.payloadLength = static_cast<std::uint8_t>(
        std::min<std::size_t>(source.length_data, report.payload.size()));
    if (source.data != nullptr && report.payloadLength != 0U) {
        std::copy_n(source.data, report.payloadLength,
                    report.payload.begin());
    }
    report.rssiDbm = source.rssi;
    queueReport(report);
    return 0;
}

bool startPassiveScan(const drivers::ble::BleScanPlan& plan) {
    ble_gap_disc_params parameters{};
    parameters.itvl = scanUnits(plan.intervalMs);
    parameters.window = scanUnits(plan.windowMs);
    parameters.filter_policy = 0U;
    parameters.limited = 0U;
    parameters.passive = 1U;  // passive scan: never transmit scan requests
    parameters.filter_duplicates = 0U;
    parameters.disable_observer_mode = 0U;
    return ble_gap_disc(BLE_OWN_ADDR_PUBLIC, BLE_HS_FOREVER, &parameters,
                        handleNimbleGapEvent, nullptr) == 0;
}

bool stopPassiveScan() {
    const int result = ble_gap_disc_cancel();
    return result == 0 || result == BLE_HS_EALREADY;
}

void processAdvertisement(const RawAdvertisement& source,
                          RawScanContext* context) {
    if (context == nullptr || context->result == nullptr ||
        context->visitor == nullptr) {
        return;
    }
    std::array<std::uint8_t, 6> canonicalAddress{};
    std::reverse_copy(source.address.begin(), source.address.end(),
                      canonicalAddress.begin());
    for (std::uint16_t index = 0; index < context->seenCount; ++index) {
        if (context->seenAddresses[index] == canonicalAddress) return;
    }
    if (context->seenCount >= context->seenAddresses.size()) {
        increment(&context->result->dropped);
        return;
    }
    context->seenAddresses[context->seenCount++] = canonicalAddress;
    increment(&context->result->recordsReported);
    if (context->result->recordsRead >= context->maximumRecords) {
        increment(&context->result->dropped);
        return;
    }

    drivers::ble::BleAdvertisementRecord record;
    record.address = canonicalAddress;
    record.addressType = source.addressType;
    record.rssiDbm = source.rssiDbm;
    parseAdvertisementPayload(source, &record.name, &record.nameLength,
                              &record.advertisement);
    increment(&context->result->recordsRead);
    switch (context->visitor(
        record, static_cast<std::uint64_t>(esp_timer_get_time()),
        context->visitorContext)) {
        case BleRecordDisposition::Accepted:
            increment(&context->result->accepted);
            break;
        case BleRecordDisposition::Rejected:
            increment(&context->result->rejected);
            break;
        case BleRecordDisposition::Dropped:
            increment(&context->result->dropped);
            break;
    }
}

void drainReports(RawScanContext* context) {
    RawAdvertisement report;
    while (popReport(&report)) processAdvertisement(report, context);
    const std::uint16_t queueDrops = takeQueueDrops();
    if (context == nullptr || context->result == nullptr) return;
    for (std::uint16_t index = 0U; index < queueDrops; ++index) {
        increment(&context->result->dropped);
    }
}

void handleNimbleReset(int) {
    processNimbleSynced = false;
    processControllerAvailable = false;
}

void handleNimbleSync() {
    processNimbleSynced = true;
}

void runProcessNimbleHost(void*) {
    nimble_port_run();
    processNimbleSynced = false;
    processControllerAvailable = false;
    nimble_port_freertos_deinit();
}

bool initializeProcessControllerObserver() {
    if (processControllerInitializationAttempted) {
        return processControllerAvailable && processNimbleSynced &&
            ble_hs_synced();
    }
    processControllerInitializationAttempted = true;
    clearReportQueue();
    setAcceptingReports(false);

    // Arduino-ESP32 3.3.9 is built with NimBLE, not Bluedroid. The Arduino
    // controller-only shortcut enters a lifecycle that crashes on this S3;
    // nimble_port_init() is the framework's supported controller + transport
    // bootstrap. Keep one minimal host task process-lifetime and scan-idle
    // between bounded receive windows. This adapter never calls advertising,
    // initiating, connecting or active-scan APIs, so no RF-TX operation is
    // reachable from the product observer.
    if (nimble_port_init() != ESP_OK) {
        return false;
    }

    ble_hs_cfg.reset_cb = handleNimbleReset;
    ble_hs_cfg.sync_cb = handleNimbleSync;
    ble_hs_cfg.sm_io_cap = BLE_HS_IO_NO_INPUT_OUTPUT;
    ble_hs_cfg.sm_bonding = 0U;
    ble_hs_cfg.sm_mitm = 0U;
    ble_hs_cfg.sm_sc = 0U;
    processNimbleSynced = false;
    nimble_port_freertos_init(runProcessNimbleHost);

    const std::uint64_t deadlineUs =
        static_cast<std::uint64_t>(esp_timer_get_time()) +
        static_cast<std::uint64_t>(kNimbleSyncTimeoutMs) * 1000ULL;
    while (!processNimbleSynced &&
           static_cast<std::uint64_t>(esp_timer_get_time()) < deadlineUs) {
        vTaskDelay(pdMS_TO_TICKS(1U));
    }
    if (!processNimbleSynced || !ble_hs_synced()) return false;
    processControllerAvailable = true;
    return true;
}

}  // namespace

volatile bool BoardBlePassiveScanner::activeScan_ = false;

const char* boardBleScanStatusName(BoardBleScanStatus status) {
    switch (status) {
        case BoardBleScanStatus::Valid: return "valid";
        case BoardBleScanStatus::NotStarted: return "not_started";
        case BoardBleScanStatus::InvalidPlan: return "invalid_plan";
        case BoardBleScanStatus::StackInitFailed: return "stack_init_failed";
        case BoardBleScanStatus::ScannerUnavailable:
            return "scanner_unavailable";
        case BoardBleScanStatus::ScanTimedOut: return "scan_timed_out";
    }
    return "unknown";
}

bool BoardBlePassiveScanner::begin() {
    if (initialized_) return true;
    cleanupComplete_ = false;
    passiveOnly_ = true;
    clearReportQueue();
    setAcceptingReports(false);

    // The process-lifetime minimal NimBLE observer was prewarmed before any
    // Wi-Fi use. Only passive ble_gap_disc() is exposed by this adapter; no
    // advertising, initiating, connecting or active scanning is representable.
    if (!prewarmProcessController()) {
        cleanupComplete_ = true;
        return false;
    }
    initialized_ = true;
    return true;
}

BoardBlePassiveScanResult BoardBlePassiveScanner::scan(
    const drivers::ble::BleScanPlan& plan,
    BleRecordVisitor visitor, void* context) {
    BoardBlePassiveScanResult result;
    if (!initialized_) return result;
    if (!drivers::ble::validatePassivePlan(plan) || visitor == nullptr) {
        result.status = BoardBleScanStatus::InvalidPlan;
        return result;
    }

    RawScanContext scanContext;
    scanContext.maximumRecords = plan.maximumRecords;
    scanContext.visitor = visitor;
    scanContext.visitorContext = context;
    scanContext.result = &result;
    const std::uint64_t startedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    for (std::uint16_t attempt = 1U;
         attempt <= kMaximumScanAttempts; ++attempt) {
        result.attempts = attempt;
        clearReportQueue();
        setAcceptingReports(true);
        const bool started = startPassiveScan(plan);
        if (!started) {
            setAcceptingReports(false);
            activeScan_ = false;
            result.status = BoardBleScanStatus::ScannerUnavailable;
        } else {
            activeScan_ = true;
            const std::uint64_t deadlineUs =
                static_cast<std::uint64_t>(esp_timer_get_time()) +
                static_cast<std::uint64_t>(plan.durationMs) * 1000ULL;
            while (activeScan_ &&
                   static_cast<std::uint64_t>(esp_timer_get_time()) <
                       deadlineUs) {
                drainReports(&scanContext);
                vTaskDelay(pdMS_TO_TICKS(5U));
            }
            drainReports(&scanContext);
            const bool completedWindow = activeScan_;
            const bool disabled = completedWindow ? stopPassiveScan() : true;
            activeScan_ = false;
            setAcceptingReports(false);
            drainReports(&scanContext);
            result.status = completedWindow && disabled
                ? BoardBleScanStatus::Valid
                : BoardBleScanStatus::ScanTimedOut;
        }
        if (result.valid() || attempt == kMaximumScanAttempts) break;
        if (result.status != BoardBleScanStatus::ScannerUnavailable &&
            result.status != BoardBleScanStatus::ScanTimedOut) {
            break;
        }
        increment(&result.transientRetries);
        vTaskDelay(pdMS_TO_TICKS(kRetryDelayMs));
    }
    result.durationUs =
        static_cast<std::uint64_t>(esp_timer_get_time()) - startedUs;
    return result;
}

bool BoardBlePassiveScanner::cancelActiveScan() {
    if (!activeScan_) return true;
    const bool cancelled = stopPassiveScan();
    activeScan_ = false;
    setAcceptingReports(false);
    return cancelled;
}

bool BoardBlePassiveScanner::prewarmProcessController() {
    return initializeProcessControllerObserver();
}

bool BoardBlePassiveScanner::processControllerReady() {
    return processControllerAvailable && processNimbleSynced &&
        ble_hs_synced();
}

bool BoardBlePassiveScanner::end() {
    if (!initialized_) {
        activeScan_ = false;
        return cleanupComplete_;
    }
    bool complete = cancelActiveScan();
    initialized_ = false;
    activeScan_ = false;
    cleanupComplete_ = complete && processControllerReady();
    return cleanupComplete_;
}

}  // namespace leshy1::platform::arduino
