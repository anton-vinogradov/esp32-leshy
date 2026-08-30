#include "BoardBlePassiveScanner.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cstdio>
#include <cstring>

#include <esp_err.h>
#include <esp32-hal-alloc-ble-mem.h>
#include <esp_heap_caps.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/portmacro.h>
#include <freertos/task.h>
#include <host/ble_gap.h>
#include <host/ble_gatt.h>
#include <host/ble_hs.h>
#include <host/ble_hs_id.h>
#include <host/ble_uuid.h>
#include <host/util/util.h>
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
    std::uint16_t reportsObserved = 0;
    std::uint16_t queueDrops = 0;
    bool acceptingReports = false;
};

NimbleObserverState nimbleObserver;
portMUX_TYPE gattInspectorMux = portMUX_INITIALIZER_UNLOCKED;
bool processControllerInitialized = false;
std::atomic_bool processControllerAvailable{false};
std::atomic_bool processNimbleSynced{false};
std::atomic_bool processNimbleHostRunning{false};
std::atomic<std::uint8_t> processOwnAddressType{BLE_OWN_ADDR_PUBLIC};
std::atomic_int processNimbleSyncError{0};

struct RawScanContext final {
    std::array<std::array<std::uint8_t, 6>, 128> seenAddresses{};
    std::uint16_t seenCount = 0;
    std::uint16_t maximumRecords = 0;
    bool deduplicateAddresses = true;
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
    nimbleObserver.reportsObserved = 0U;
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

std::uint16_t takeReportsObserved() {
    portENTER_CRITICAL(&nimbleObserver.lock);
    const std::uint16_t observed = nimbleObserver.reportsObserved;
    nimbleObserver.reportsObserved = 0U;
    portEXIT_CRITICAL(&nimbleObserver.lock);
    return observed;
}

void queueReport(const RawAdvertisement& report) {
    portENTER_CRITICAL(&nimbleObserver.lock);
    if (nimbleObserver.acceptingReports) {
        if (nimbleObserver.reportsObserved != UINT16_MAX) {
            ++nimbleObserver.reportsObserved;
        }
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
    return ble_gap_disc(
        processOwnAddressType.load(std::memory_order_acquire),
        BLE_HS_FOREVER, &parameters, handleNimbleGapEvent, nullptr) == 0;
}

bool stopPassiveScan() {
    const int result = ble_gap_disc_cancel();
    return result == 0 || result == BLE_HS_EALREADY;
}

std::uint64_t monotonicUs() {
    std::uint64_t value = static_cast<std::uint64_t>(esp_timer_get_time());
    return value == 0U ? 1U : value;
}

services::ble::BleGattUuid copyGattUuid(const ble_uuid_t* source) {
    services::ble::BleGattUuid result{};
    if (source == nullptr) return result;
    if (source->type == BLE_UUID_TYPE_16) {
        const std::uint16_t value = BLE_UUID16(source)->value;
        result.widthBytes = 2U;
        result.bytes[0] = static_cast<std::uint8_t>(value);
        result.bytes[1] = static_cast<std::uint8_t>(value >> 8U);
    } else if (source->type == BLE_UUID_TYPE_32) {
        const std::uint32_t value = BLE_UUID32(source)->value;
        result.widthBytes = 4U;
        for (std::size_t index = 0U; index < 4U; ++index) {
            result.bytes[index] = static_cast<std::uint8_t>(
                value >> (index * 8U));
        }
    } else if (source->type == BLE_UUID_TYPE_128) {
        result.widthBytes = 16U;
        std::copy_n(BLE_UUID128(source)->value, result.bytes.size(),
                    result.bytes.begin());
    }
    return result;
}

int handleGattGapEvent(struct ble_gap_event* event, void* context) {
    auto* transport = static_cast<BoardBleGattInspectorTransport*>(context);
    return transport == nullptr ? BLE_HS_EINVAL
                                : transport->handleGapEvent(event);
}

int handleGattServiceDiscovery(std::uint16_t connHandle,
                               const struct ble_gatt_error* error,
                               const struct ble_gatt_svc* service,
                               void* context) {
    auto* transport = static_cast<BoardBleGattInspectorTransport*>(context);
    return transport == nullptr
        ? BLE_HS_EINVAL
        : transport->handleServiceDiscovery(connHandle, error, service);
}

int handleGattCharacteristicDiscovery(
    std::uint16_t connHandle, const struct ble_gatt_error* error,
    const struct ble_gatt_chr* characteristic, void* context) {
    auto* transport = static_cast<BoardBleGattInspectorTransport*>(context);
    return transport == nullptr
        ? BLE_HS_EINVAL
        : transport->handleCharacteristicDiscovery(
              connHandle, error, characteristic);
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
    if (context->deduplicateAddresses) {
        for (std::uint16_t index = 0; index < context->seenCount; ++index) {
            if (context->seenAddresses[index] == canonicalAddress) return;
        }
        if (context->seenCount >= context->seenAddresses.size()) {
            increment(&context->result->dropped);
            return;
        }
        context->seenAddresses[context->seenCount++] = canonicalAddress;
    }
    increment(&context->result->recordsReported);
    if (context->result->recordsRead >= context->maximumRecords) {
        increment(&context->result->dropped);
        return;
    }

    drivers::ble::BleAdvertisementRecord record;
    record.address = canonicalAddress;
    record.addressType = source.addressType;
    record.eventType = source.eventType;
    record.rssiDbm = source.rssiDbm;
    record.payloadLength = source.payloadLength;
    std::copy_n(source.payload.begin(), source.payloadLength,
                record.payload.begin());
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
    const std::uint16_t observed = takeReportsObserved();
    const std::uint16_t queueDrops = takeQueueDrops();
    if (context == nullptr || context->result == nullptr) return;
    for (std::uint16_t index = 0U; index < observed; ++index) {
        increment(&context->result->recordsObserved);
    }
    for (std::uint16_t index = 0U; index < queueDrops; ++index) {
        increment(&context->result->dropped);
    }
}

void handleNimbleReset(int reason) {
    processNimbleSyncError.store(reason, std::memory_order_release);
    processNimbleSynced = false;
    processControllerAvailable = false;
}

void handleNimbleSync() {
    // nimble_port_init() synchronizes the host transport, but it does not
    // establish an own address. The Arduino BLE wrapper used by the accepted
    // 0.156 HIL performs this step in BLEDevice::onSync(). Without it the GAP
    // discovery command can return success while the controller delivers no
    // advertising reports. Resolve the address before publishing readiness.
    std::uint8_t ownAddressType = BLE_OWN_ADDR_PUBLIC;
    const int ensured = ble_hs_util_ensure_addr(0);
    const int inferred = ensured == 0
        ? ble_hs_id_infer_auto(0, &ownAddressType)
        : ensured;
    if (inferred != 0) {
        processNimbleSyncError.store(inferred, std::memory_order_release);
        processControllerAvailable.store(false, std::memory_order_release);
        processNimbleSynced.store(false, std::memory_order_release);
        return;
    }
    processOwnAddressType.store(
        ownAddressType, std::memory_order_release);
    processNimbleSyncError.store(0, std::memory_order_release);
    processNimbleSynced.store(true, std::memory_order_release);
}

void runProcessNimbleHost(void*) {
    processNimbleHostRunning = true;
    nimble_port_run();
    processNimbleSynced = false;
    processControllerAvailable = false;
    // The FreeRTOS port deinitializer deletes the current host task and is not
    // required to return. Publish the exit path before handing it ownership.
    processNimbleHostRunning = false;
    nimble_port_freertos_deinit();
}

bool shutdownProcessControllerObserver() {
    setAcceptingReports(false);
    clearReportQueue();
    processControllerAvailable = false;
    processNimbleSynced = false;
    processOwnAddressType.store(
        BLE_OWN_ADDR_PUBLIC, std::memory_order_release);
    if (!processControllerInitialized) return true;

    const bool stopRequested = nimble_port_stop() == ESP_OK;
    const std::uint64_t deadlineUs =
        static_cast<std::uint64_t>(esp_timer_get_time()) +
        static_cast<std::uint64_t>(
            BoardBlePassiveScanner::kHostShutdownTimeoutMs) * 1000ULL;
    while (processNimbleHostRunning &&
           static_cast<std::uint64_t>(esp_timer_get_time()) < deadlineUs) {
        vTaskDelay(pdMS_TO_TICKS(1U));
    }
    if (processNimbleHostRunning) return false;
    // Let the host task execute its immediate self-delete before deinitializing
    // the controller/host pools from this worker task on a different core.
    vTaskDelay(pdMS_TO_TICKS(1U));

    const bool deinitialized = nimble_port_deinit() == ESP_OK;
    if (deinitialized) processControllerInitialized = false;
    return stopRequested && deinitialized;
}

bool initializeProcessControllerObserver(
    BoardBleBeginDiagnostic* diagnostic) {
    if (processControllerInitialized) {
        const bool ready = processControllerAvailable && processNimbleSynced &&
            ble_hs_synced();
        if (diagnostic != nullptr) {
            diagnostic->stage = ready ? BoardBleBeginStage::ReusedReady
                                      : BoardBleBeginStage::HostSync;
            diagnostic->error = ready
                ? 0 : processNimbleSyncError.load(std::memory_order_acquire);
            if (!ready && diagnostic->error == 0) {
                diagnostic->error = ESP_ERR_INVALID_STATE;
            }
        }
        if (!ready) {
            const bool cleanupComplete = shutdownProcessControllerObserver();
            if (diagnostic != nullptr) {
                diagnostic->cleanupComplete = cleanupComplete;
            }
        }
        return ready;
    }
    clearReportQueue();
    setAcceptingReports(false);
    processNimbleSyncError.store(0, std::memory_order_release);

    // esp32-hal-alloc-ble-mem.h registers this low-level adapter as a BLE
    // consumer before initArduino(). Without that constructor marker the core
    // permanently releases BLE controller memory before setup(), and the
    // later NimBLE bootstrap enters an invalid controller lifecycle.
    // Arduino-ESP32 3.3.9 is built with NimBLE, not Bluedroid. The Arduino
    // controller-only shortcut enters a lifecycle that crashes on this S3;
    // nimble_port_init() is the framework's supported controller + transport
    // bootstrap. The complete host lifecycle is bounded by one Product Survey
    // run so FAT/SDSPI can mount before and after radio observation without
    // competing for the same internal heap. This adapter never calls
    // advertising, initiating, connecting or active-scan APIs, so no RF-TX operation
    // is reachable from the product observer.
    if (diagnostic != nullptr) {
        diagnostic->stage = BoardBleBeginStage::ControllerInit;
    }
    const int initError = nimble_port_init();
    if (initError != ESP_OK) {
        if (diagnostic != nullptr) diagnostic->error = initError;
        return false;
    }
    processControllerInitialized = true;

    ble_hs_cfg.reset_cb = handleNimbleReset;
    ble_hs_cfg.sync_cb = handleNimbleSync;
    ble_hs_cfg.sm_io_cap = BLE_HS_IO_NO_INPUT_OUTPUT;
    ble_hs_cfg.sm_bonding = 0U;
    ble_hs_cfg.sm_mitm = 0U;
    ble_hs_cfg.sm_sc = 0U;
    processNimbleSynced = false;
    processNimbleHostRunning = false;
    if (diagnostic != nullptr) {
        diagnostic->stage = BoardBleBeginStage::HostSync;
    }
    nimble_port_freertos_init(runProcessNimbleHost);

    const std::uint64_t deadlineUs =
        static_cast<std::uint64_t>(esp_timer_get_time()) +
        static_cast<std::uint64_t>(kNimbleSyncTimeoutMs) * 1000ULL;
    while (!processNimbleSynced &&
           static_cast<std::uint64_t>(esp_timer_get_time()) < deadlineUs) {
        vTaskDelay(pdMS_TO_TICKS(1U));
    }
    if (!processNimbleSynced || !ble_hs_synced()) {
        int syncError =
            processNimbleSyncError.load(std::memory_order_acquire);
        if (syncError == 0) syncError = ESP_ERR_TIMEOUT;
        if (diagnostic != nullptr) diagnostic->error = syncError;
        const bool cleanupComplete = shutdownProcessControllerObserver();
        if (diagnostic != nullptr) {
            diagnostic->cleanupComplete = cleanupComplete;
        }
        return false;
    }
    processControllerAvailable = true;
    if (diagnostic != nullptr) {
        diagnostic->stage = BoardBleBeginStage::Ready;
        diagnostic->error = 0;
    }
    return true;
}

}  // namespace

volatile bool BoardBlePassiveScanner::activeScan_ = false;
std::atomic_bool BoardBlePassiveScanner::cancelRequested_{false};

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

const char* boardBleBeginStageName(BoardBleBeginStage stage) {
    switch (stage) {
        case BoardBleBeginStage::NotAttempted: return "not_attempted";
        case BoardBleBeginStage::ReusedReady: return "reused_ready";
        case BoardBleBeginStage::ControllerInit: return "controller_init";
        case BoardBleBeginStage::HostSync: return "host_sync";
        case BoardBleBeginStage::Ready: return "ready";
    }
    return "unknown";
}

bool BoardBlePassiveScanner::begin() {
    beginDiagnostic_ = {};
    beginDiagnostic_.heapFreeBefore = static_cast<std::uint32_t>(
        heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    beginDiagnostic_.heapLargestBefore = static_cast<std::uint32_t>(
        heap_caps_get_largest_free_block(
            MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    if (initialized_) {
        beginDiagnostic_.stage = BoardBleBeginStage::ReusedReady;
        beginDiagnostic_.heapFreeAfter = beginDiagnostic_.heapFreeBefore;
        beginDiagnostic_.heapLargestAfter = beginDiagnostic_.heapLargestBefore;
        beginDiagnostic_.cleanupComplete = false;
        return true;
    }
    cancelRequested_.store(false, std::memory_order_release);
    cleanupComplete_ = false;
    passiveOnly_ = true;
    clearReportQueue();
    setAcceptingReports(false);

    // Storage admission and its FAT mount have already completed and released
    // their heap. Only passive ble_gap_disc() is exposed by this adapter; no
    // advertising, initiating, connecting or active scanning is representable.
    const bool ready = initializeProcessControllerObserver(&beginDiagnostic_);
    beginDiagnostic_.heapFreeAfter = static_cast<std::uint32_t>(
        heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    beginDiagnostic_.heapLargestAfter = static_cast<std::uint32_t>(
        heap_caps_get_largest_free_block(
            MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    if (!ready) {
        cleanupComplete_ = beginDiagnostic_.cleanupComplete;
        return false;
    }
    initialized_ = true;
    beginDiagnostic_.cleanupComplete = false;
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
    scanContext.deduplicateAddresses = plan.deduplicateAddresses;
    scanContext.visitor = visitor;
    scanContext.visitorContext = context;
    scanContext.result = &result;
    const std::uint64_t startedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    for (std::uint16_t attempt = 1U;
         attempt <= kMaximumScanAttempts; ++attempt) {
        result.attempts = attempt;
        if (cancelRequested_.load(std::memory_order_acquire)) {
            result.status = BoardBleScanStatus::ScanTimedOut;
            break;
        }
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
                   !cancelRequested_.load(std::memory_order_acquire) &&
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
            result.status = completedWindow && disabled &&
                    !cancelRequested_.load(std::memory_order_acquire)
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
    cancelRequested_.store(true, std::memory_order_release);
    if (!activeScan_) return true;
    const bool cancelled = stopPassiveScan();
    activeScan_ = false;
    setAcceptingReports(false);
    return cancelled;
}

bool BoardBlePassiveScanner::processControllerReady() {
    return processControllerAvailable && processNimbleSynced &&
        ble_hs_synced();
}

bool BoardBlePassiveScanner::end() {
    bool complete = cancelActiveScan();
    initialized_ = false;
    activeScan_ = false;
    complete = shutdownProcessControllerObserver() && complete;
    cleanupComplete_ = complete && !processControllerReady() &&
        !processNimbleHostRunning && !processControllerInitialized;
    beginDiagnostic_.cleanupComplete = cleanupComplete_;
    return cleanupComplete_;
}

bool BoardBleGattInspectorTransport::bind(
    services::ble::BleGattInspector* inspector) {
    if (inspector == nullptr) return false;
    portENTER_CRITICAL(&gattInspectorMux);
    const bool available = inspector_ == nullptr && !hostReady_ &&
        !connecting_.load(std::memory_order_acquire) &&
        !connected_.load(std::memory_order_acquire);
    if (available) inspector_ = inspector;
    portEXIT_CRITICAL(&gattInspectorMux);
    return available;
}

bool BoardBleGattInspectorTransport::unbind() {
    portENTER_CRITICAL(&gattInspectorMux);
    const bool clean = inspector_ != nullptr &&
        inspector_->cleanupComplete() && !hostReady_ &&
        !connecting_.load(std::memory_order_acquire) &&
        !connected_.load(std::memory_order_acquire);
    if (clean) inspector_ = nullptr;
    portEXIT_CRITICAL(&gattInspectorMux);
    return clean;
}

bool BoardBleGattInspectorTransport::selectTarget(
    const services::ble::BleInspectorTarget& target,
    std::uint64_t nowMonotonicUs) {
    portENTER_CRITICAL(&gattInspectorMux);
    const bool selected = inspector_ != nullptr &&
        inspector_->selectTarget(target, nowMonotonicUs);
    portEXIT_CRITICAL(&gattInspectorMux);
    return selected;
}

bool BoardBleGattInspectorTransport::reviewPermission(
    services::ble::BleGattInspectorPermission permission) {
    portENTER_CRITICAL(&gattInspectorMux);
    const bool reviewed = inspector_ != nullptr &&
        inspector_->reviewPermission(permission);
    portEXIT_CRITICAL(&gattInspectorMux);
    return reviewed;
}

std::uint64_t BoardBleGattInspectorTransport::confirmationToken() const {
    portENTER_CRITICAL(&gattInspectorMux);
    const std::uint64_t token = inspector_ == nullptr
        ? 0U : inspector_->confirmationToken();
    portEXIT_CRITICAL(&gattInspectorMux);
    return token;
}

bool BoardBleGattInspectorTransport::confirm(
    std::uint64_t token, std::uint64_t nowMonotonicUs) {
    portENTER_CRITICAL(&gattInspectorMux);
    const bool confirmed = inspector_ != nullptr &&
        inspector_->confirm(token, nowMonotonicUs);
    portEXIT_CRITICAL(&gattInspectorMux);
    return confirmed;
}

bool BoardBleGattInspectorTransport::back(std::uint64_t nowMonotonicUs) {
    portENTER_CRITICAL(&gattInspectorMux);
    const bool changed = inspector_ != nullptr &&
        inspector_->back(nowMonotonicUs);
    portEXIT_CRITICAL(&gattInspectorMux);
    return changed;
}

bool BoardBleGattInspectorTransport::tick(std::uint64_t nowMonotonicUs) {
    portENTER_CRITICAL(&gattInspectorMux);
    const bool changed = inspector_ != nullptr &&
        inspector_->tick(nowMonotonicUs);
    portEXIT_CRITICAL(&gattInspectorMux);
    updateHeapMinimum();
    return changed;
}

services::ble::BleGattInspectorState
BoardBleGattInspectorTransport::state() const {
    portENTER_CRITICAL(&gattInspectorMux);
    const auto value = inspector_ == nullptr
        ? services::ble::BleGattInspectorState::Idle : inspector_->state();
    portEXIT_CRITICAL(&gattInspectorMux);
    return value;
}

services::ble::BleGattInspectorFailure
BoardBleGattInspectorTransport::failure() const {
    portENTER_CRITICAL(&gattInspectorMux);
    const auto value = inspector_ == nullptr
        ? services::ble::BleGattInspectorFailure::None
        : inspector_->failure();
    portEXIT_CRITICAL(&gattInspectorMux);
    return value;
}

services::ble::BleGattInspectorFailure
BoardBleGattInspectorTransport::cleanupCause() const {
    portENTER_CRITICAL(&gattInspectorMux);
    const auto value = inspector_ == nullptr
        ? services::ble::BleGattInspectorFailure::None
        : inspector_->cleanupCause();
    portEXIT_CRITICAL(&gattInspectorMux);
    return value;
}

std::size_t BoardBleGattInspectorTransport::serviceCount() const {
    portENTER_CRITICAL(&gattInspectorMux);
    const std::size_t value = inspector_ == nullptr
        ? 0U : inspector_->serviceCount();
    portEXIT_CRITICAL(&gattInspectorMux);
    return value;
}

std::size_t BoardBleGattInspectorTransport::characteristicCount() const {
    portENTER_CRITICAL(&gattInspectorMux);
    const std::size_t value = inspector_ == nullptr
        ? 0U : inspector_->characteristicCount();
    portEXIT_CRITICAL(&gattInspectorMux);
    return value;
}

bool BoardBleGattInspectorTransport::copyService(
    std::size_t index, services::ble::BleGattServiceFact* output) const {
    if (output == nullptr) return false;
    portENTER_CRITICAL(&gattInspectorMux);
    const auto* source = inspector_ == nullptr
        ? nullptr : inspector_->serviceAt(index);
    if (source != nullptr) *output = *source;
    portEXIT_CRITICAL(&gattInspectorMux);
    return source != nullptr;
}

bool BoardBleGattInspectorTransport::copyCharacteristic(
    std::size_t index,
    services::ble::BleGattCharacteristicFact* output) const {
    if (output == nullptr) return false;
    portENTER_CRITICAL(&gattInspectorMux);
    const auto* source = inspector_ == nullptr
        ? nullptr : inspector_->characteristicAt(index);
    if (source != nullptr) *output = *source;
    portEXIT_CRITICAL(&gattInspectorMux);
    return source != nullptr;
}

bool BoardBleGattInspectorTransport::copyTarget(
    services::ble::BleInspectorTarget* output) const {
    if (output == nullptr) return false;
    portENTER_CRITICAL(&gattInspectorMux);
    const bool available = inspector_ != nullptr &&
        services::ble::validBleInspectorTarget(inspector_->target());
    if (available) *output = inspector_->target();
    portEXIT_CRITICAL(&gattInspectorMux);
    return available;
}

bool BoardBleGattInspectorTransport::cleanupComplete() const {
    portENTER_CRITICAL(&gattInspectorMux);
    const bool clean = inspector_ == nullptr || inspector_->cleanupComplete();
    portEXIT_CRITICAL(&gattInspectorMux);
    return clean && !hostReady_ &&
        !connecting_.load(std::memory_order_acquire) &&
        !connected_.load(std::memory_order_acquire);
}

bool BoardBleGattInspectorTransport::ownsRadio() const {
    portENTER_CRITICAL(&gattInspectorMux);
    const bool owned = inspector_ != nullptr && inspector_->ownsRadio();
    portEXIT_CRITICAL(&gattInspectorMux);
    return owned;
}

bool BoardBleGattInspectorTransport::hostReady() const {
    return hostReady_ && BoardBlePassiveScanner::processControllerReady();
}

bool BoardBleGattInspectorTransport::connected() const {
    return connected_.load(std::memory_order_acquire);
}

bool BoardBleGattInspectorTransport::startConnect(
    const services::ble::BleInspectorTarget& target) {
    if (hostReady_ || connecting_.load(std::memory_order_acquire) ||
        connected_.load(std::memory_order_acquire)) {
        return false;
    }
    heapFreeBefore_ = static_cast<std::uint32_t>(
        heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    heapLargestBefore_ = static_cast<std::uint32_t>(
        heap_caps_get_largest_free_block(
            MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    heapMinimum_ = heapFreeBefore_;
    BoardBleBeginDiagnostic diagnostic{};
    if (!initializeProcessControllerObserver(&diagnostic)) return false;
    hostReady_ = true;
    heapFreeAfterInit_ = static_cast<std::uint32_t>(
        heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    heapLargestAfterInit_ = static_cast<std::uint32_t>(
        heap_caps_get_largest_free_block(
            MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    updateHeapMinimum();

    ble_addr_t peer{};
    peer.type = target.addressType;
    std::reverse_copy(target.address.begin(), target.address.end(), peer.val);
    target_ = target;
    connectionHandle_ = BLE_HS_CONN_HANDLE_NONE;
    characteristicServiceIndex_ = 0U;
    disconnected_.store(false, std::memory_order_release);
    remoteDisconnectPending_.store(false, std::memory_order_release);
    cleanupRequested_.store(false, std::memory_order_release);
    connecting_.store(true, std::memory_order_release);
    const int started = ble_gap_connect(
        processOwnAddressType.load(std::memory_order_acquire), &peer,
        static_cast<std::int32_t>(kConnectTimeoutMs), nullptr,
        handleGattGapEvent, this);
    if (started == 0) return true;
    connecting_.store(false, std::memory_order_release);
    disconnected_.store(true, std::memory_order_release);
    cleanupRequested_.store(true, std::memory_order_release);
    hostReady_ = !shutdownProcessControllerObserver();
    if (!hostReady_) {
        cleanupRequested_.store(false, std::memory_order_release);
        return false;
    }
    // The host exists but could not be torn down synchronously. Keep the
    // controller's radio lease and report the transport error on service();
    // the ordinary fail-closed disconnect path will retry teardown before the
    // lease can be released.
    remoteDisconnectPending_.store(true, std::memory_order_release);
    return true;
}

bool BoardBleGattInspectorTransport::startServiceDiscovery() {
    if (!hostReady_ || !connected_.load(std::memory_order_acquire) ||
        connectionHandle_ == BLE_HS_CONN_HANDLE_NONE) {
        return false;
    }
    characteristicServiceIndex_ = 0U;
    return ble_gattc_disc_all_svcs(
        connectionHandle_, handleGattServiceDiscovery, this) == 0;
}

services::ble::BleGattDisconnectStatus
BoardBleGattInspectorTransport::requestDisconnect() {
    cleanupRequested_.store(true, std::memory_order_release);
    if (connecting_.load(std::memory_order_acquire)) {
        const int result = ble_gap_conn_cancel();
        return result == 0 || result == BLE_HS_EALREADY
            ? services::ble::BleGattDisconnectStatus::Pending
            : services::ble::BleGattDisconnectStatus::Failed;
    }
    if (connected_.load(std::memory_order_acquire) &&
        connectionHandle_ != BLE_HS_CONN_HANDLE_NONE) {
        const int result = ble_gap_terminate(
            connectionHandle_, BLE_ERR_REM_USER_CONN_TERM);
        return result == 0 || result == BLE_HS_ENOTCONN
            ? services::ble::BleGattDisconnectStatus::Pending
            : services::ble::BleGattDisconnectStatus::Failed;
    }
    return hostReady_ ? services::ble::BleGattDisconnectStatus::Pending
                      : services::ble::BleGattDisconnectStatus::Disconnected;
}

services::ble::BleGattDisconnectStatus
BoardBleGattInspectorTransport::pollDisconnect() {
    if (connecting_.load(std::memory_order_acquire) ||
        connected_.load(std::memory_order_acquire)) {
        return services::ble::BleGattDisconnectStatus::Pending;
    }
    if (!hostReady_) {
        return services::ble::BleGattDisconnectStatus::Disconnected;
    }
    if (!cleanupRequested_.load(std::memory_order_acquire) ||
        !disconnected_.load(std::memory_order_acquire)) {
        return services::ble::BleGattDisconnectStatus::Pending;
    }
    const bool shutdown = shutdownProcessControllerObserver();
    if (!shutdown) return services::ble::BleGattDisconnectStatus::Failed;
    hostReady_ = false;
    connectionHandle_ = BLE_HS_CONN_HANDLE_NONE;
    cleanupRequested_.store(false, std::memory_order_release);
    updateHeapMinimum();
    return services::ble::BleGattDisconnectStatus::Disconnected;
}

bool BoardBleGattInspectorTransport::service(std::uint64_t nowMonotonicUs) {
    bool changed = false;
    if (remoteDisconnectPending_.exchange(false,
                                          std::memory_order_acq_rel)) {
        portENTER_CRITICAL(&gattInspectorMux);
        if (inspector_ != nullptr &&
            inspector_->state() != services::ble::BleGattInspectorState::
                                      CleanupPending) {
            changed = inspector_->onTransportError(nowMonotonicUs);
        }
        portEXIT_CRITICAL(&gattInspectorMux);
    }
    changed = tick(nowMonotonicUs) || changed;
    return changed;
}

int BoardBleGattInspectorTransport::handleGapEvent(void* rawEvent) {
    auto* event = static_cast<ble_gap_event*>(rawEvent);
    if (event == nullptr) return 0;
    if (event->type == BLE_GAP_EVENT_CONNECT) {
        connecting_.store(false, std::memory_order_release);
        if (event->connect.status != 0) {
            disconnected_.store(true, std::memory_order_release);
            cleanupRequested_.store(true, std::memory_order_release);
            portENTER_CRITICAL(&gattInspectorMux);
            if (inspector_ != nullptr) {
                (void)inspector_->onConnectionRefused(monotonicUs());
            }
            portEXIT_CRITICAL(&gattInspectorMux);
            return 0;
        }
        connectionHandle_ = event->connect.conn_handle;
        connected_.store(true, std::memory_order_release);
        disconnected_.store(false, std::memory_order_release);
        std::array<std::uint8_t, 6> address{};
        std::uint8_t addressType = target_.addressType;
        ble_gap_conn_desc description{};
        if (ble_gap_conn_find(connectionHandle_, &description) == 0) {
            std::reverse_copy(description.peer_id_addr.val,
                              description.peer_id_addr.val + 6U,
                              address.begin());
            addressType = description.peer_id_addr.type;
        }
        portENTER_CRITICAL(&gattInspectorMux);
        if (inspector_ != nullptr) {
            (void)inspector_->onConnected(
                address, addressType, monotonicUs());
        }
        portEXIT_CRITICAL(&gattInspectorMux);
        updateHeapMinimum();
        return 0;
    }
    if (event->type == BLE_GAP_EVENT_DISCONNECT) {
        connecting_.store(false, std::memory_order_release);
        connected_.store(false, std::memory_order_release);
        disconnected_.store(true, std::memory_order_release);
        cleanupRequested_.store(true, std::memory_order_release);
        connectionHandle_ = BLE_HS_CONN_HANDLE_NONE;
        portENTER_CRITICAL(&gattInspectorMux);
        const bool cleanupPending = inspector_ != nullptr &&
            inspector_->state() ==
                services::ble::BleGattInspectorState::CleanupPending;
        portEXIT_CRITICAL(&gattInspectorMux);
        if (!cleanupPending) {
            remoteDisconnectPending_.store(true, std::memory_order_release);
        }
        return 0;
    }
    return 0;
}

int BoardBleGattInspectorTransport::handleServiceDiscovery(
    std::uint16_t connHandle, const void* rawError, const void* rawService) {
    const auto* error = static_cast<const ble_gatt_error*>(rawError);
    const auto* service = static_cast<const ble_gatt_svc*>(rawService);
    portENTER_CRITICAL(&gattInspectorMux);
    if (inspector_ == nullptr || connHandle != connectionHandle_ ||
        error == nullptr) {
        portEXIT_CRITICAL(&gattInspectorMux);
        return BLE_HS_EINVAL;
    }
    const std::uint64_t nowUs = monotonicUs();
    if (error->status == 0 && service != nullptr) {
        services::ble::BleGattServiceFact fact{};
        fact.startHandle = service->start_handle;
        fact.endHandle = service->end_handle;
        fact.uuid = copyGattUuid(&service->uuid.u);
        const bool accepted = inspector_->recordService(fact, nowUs);
        portEXIT_CRITICAL(&gattInspectorMux);
        updateHeapMinimum();
        return accepted ? 0 : BLE_HS_EAPP;
    }
    if (error->status == BLE_HS_EDONE) {
        characteristicServiceIndex_ = 0U;
        portEXIT_CRITICAL(&gattInspectorMux);
        const bool started = startNextCharacteristicDiscovery(nowUs);
        updateHeapMinimum();
        return started ? 0 : BLE_HS_EAPP;
    }
    (void)inspector_->onTransportError(nowUs);
    portEXIT_CRITICAL(&gattInspectorMux);
    return BLE_HS_EAPP;
}

bool BoardBleGattInspectorTransport::startNextCharacteristicDiscovery(
    std::uint64_t nowMonotonicUs) {
    services::ble::BleGattServiceFact service{};
    std::uint16_t connectionHandle = BLE_HS_CONN_HANDLE_NONE;
    bool discoveryComplete = false;
    bool servicePresent = false;
    portENTER_CRITICAL(&gattInspectorMux);
    if (inspector_ == nullptr) {
        portEXIT_CRITICAL(&gattInspectorMux);
        return false;
    }
    if (characteristicServiceIndex_ >= inspector_->serviceCount()) {
        discoveryComplete = inspector_->onDiscoveryComplete(nowMonotonicUs);
        portEXIT_CRITICAL(&gattInspectorMux);
        return discoveryComplete;
    }
    const auto* source = inspector_->serviceAt(characteristicServiceIndex_);
    servicePresent = source != nullptr;
    if (servicePresent) service = *source;
    connectionHandle = connectionHandle_;
    portEXIT_CRITICAL(&gattInspectorMux);
    return servicePresent && connectionHandle != BLE_HS_CONN_HANDLE_NONE &&
        ble_gattc_disc_all_chrs(
        connectionHandle, service.startHandle, service.endHandle,
        handleGattCharacteristicDiscovery, this) == 0;
}

int BoardBleGattInspectorTransport::handleCharacteristicDiscovery(
    std::uint16_t connHandle, const void* rawError,
    const void* rawCharacteristic) {
    const auto* error = static_cast<const ble_gatt_error*>(rawError);
    const auto* characteristic =
        static_cast<const ble_gatt_chr*>(rawCharacteristic);
    portENTER_CRITICAL(&gattInspectorMux);
    if (inspector_ == nullptr || connHandle != connectionHandle_ ||
        error == nullptr) {
        portEXIT_CRITICAL(&gattInspectorMux);
        return BLE_HS_EINVAL;
    }
    const std::uint64_t nowUs = monotonicUs();
    if (error->status == 0 && characteristic != nullptr) {
        const auto* service = inspector_->serviceAt(
            characteristicServiceIndex_);
        services::ble::BleGattCharacteristicFact fact{};
        if (service != nullptr) {
            fact.serviceStartHandle = service->startHandle;
        }
        fact.declarationHandle = characteristic->def_handle;
        fact.valueHandle = characteristic->val_handle;
        fact.properties = characteristic->properties;
        fact.uuid = copyGattUuid(&characteristic->uuid.u);
        const bool accepted = inspector_->recordCharacteristic(fact, nowUs);
        portEXIT_CRITICAL(&gattInspectorMux);
        updateHeapMinimum();
        return accepted ? 0 : BLE_HS_EAPP;
    }
    if (error->status == BLE_HS_EDONE) {
        ++characteristicServiceIndex_;
        portEXIT_CRITICAL(&gattInspectorMux);
        const bool started = startNextCharacteristicDiscovery(nowUs);
        updateHeapMinimum();
        return started ? 0 : BLE_HS_EAPP;
    }
    (void)inspector_->onTransportError(nowUs);
    portEXIT_CRITICAL(&gattInspectorMux);
    return BLE_HS_EAPP;
}

void BoardBleGattInspectorTransport::updateHeapMinimum() {
    const std::uint32_t free = static_cast<std::uint32_t>(
        heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    if (free < heapMinimum_) heapMinimum_ = free;
}

}  // namespace leshy1::platform::arduino
