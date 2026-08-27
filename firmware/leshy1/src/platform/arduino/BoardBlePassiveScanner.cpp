#include "BoardBlePassiveScanner.h"

#include <algorithm>
#include <array>
#include <cstdio>
#include <cstring>

#include <esp_bt.h>
#include <esp_err.h>
#include <esp_timer.h>
#include <esp32-hal-bt.h>
#include <freertos/FreeRTOS.h>
#include <freertos/portmacro.h>
#include <freertos/task.h>

namespace leshy1::platform::arduino {

namespace {

using AdvertisementFacts =
    domain::observations::BleAdvertisementFacts;

constexpr std::uint8_t kHciCommandPacket = 0x01U;
constexpr std::uint8_t kHciEventPacket = 0x04U;
constexpr std::uint8_t kHciCommandCompleteEvent = 0x0eU;
constexpr std::uint8_t kHciCommandStatusEvent = 0x0fU;
constexpr std::uint8_t kHciLeMetaEvent = 0x3eU;
constexpr std::uint8_t kHciLeAdvertisingReport = 0x02U;
constexpr std::uint16_t kHciLeSetScanParameters = 0x200bU;
constexpr std::uint16_t kHciLeSetScanEnable = 0x200cU;
constexpr std::uint32_t kHciCommandTimeoutMs = 1000U;

struct RawAdvertisement final {
    std::array<std::uint8_t, 6> address{};
    std::array<std::uint8_t, 31> payload{};
    std::uint8_t addressType = 0;
    std::uint8_t eventType = 0;
    std::uint8_t payloadLength = 0;
    std::int8_t rssiDbm = 0;
};

struct HciObserverState final {
    static constexpr std::size_t kQueueCapacity = 64U;

    portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
    std::array<RawAdvertisement, kQueueCapacity> queue{};
    std::size_t readIndex = 0;
    std::size_t writeIndex = 0;
    std::size_t queued = 0;
    std::uint16_t queueDrops = 0;
    bool acceptingReports = false;
    bool commandInFlight = false;
    bool commandComplete = false;
    std::uint16_t expectedOpcode = 0;
    std::uint8_t commandStatus = 0xffU;
};

HciObserverState hciObserver;
bool processControllerInitializationAttempted = false;
bool processControllerAvailable = false;

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
    portENTER_CRITICAL(&hciObserver.lock);
    hciObserver.readIndex = 0U;
    hciObserver.writeIndex = 0U;
    hciObserver.queued = 0U;
    hciObserver.queueDrops = 0U;
    portEXIT_CRITICAL(&hciObserver.lock);
}

bool popReport(RawAdvertisement* report) {
    if (report == nullptr) return false;
    bool available = false;
    portENTER_CRITICAL(&hciObserver.lock);
    if (hciObserver.queued != 0U) {
        *report = hciObserver.queue[hciObserver.readIndex];
        hciObserver.readIndex =
            (hciObserver.readIndex + 1U) % HciObserverState::kQueueCapacity;
        --hciObserver.queued;
        available = true;
    }
    portEXIT_CRITICAL(&hciObserver.lock);
    return available;
}

std::uint16_t takeQueueDrops() {
    portENTER_CRITICAL(&hciObserver.lock);
    const std::uint16_t drops = hciObserver.queueDrops;
    hciObserver.queueDrops = 0U;
    portEXIT_CRITICAL(&hciObserver.lock);
    return drops;
}

void queueReport(const RawAdvertisement& report) {
    portENTER_CRITICAL(&hciObserver.lock);
    if (hciObserver.acceptingReports) {
        if (hciObserver.queued < HciObserverState::kQueueCapacity) {
            hciObserver.queue[hciObserver.writeIndex] = report;
            hciObserver.writeIndex =
                (hciObserver.writeIndex + 1U) %
                HciObserverState::kQueueCapacity;
            ++hciObserver.queued;
        } else if (hciObserver.queueDrops != UINT16_MAX) {
            ++hciObserver.queueDrops;
        }
    }
    portEXIT_CRITICAL(&hciObserver.lock);
}

void handleCommandResult(std::uint16_t opcode, std::uint8_t status) {
    portENTER_CRITICAL(&hciObserver.lock);
    if (hciObserver.commandInFlight &&
        hciObserver.expectedOpcode == opcode) {
        hciObserver.commandStatus = status;
        hciObserver.commandComplete = true;
    }
    portEXIT_CRITICAL(&hciObserver.lock);
}

void handleLegacyAdvertisingReports(const std::uint8_t* parameters,
                                    std::size_t length) {
    if (parameters == nullptr || length < 1U) return;
    const std::uint8_t reportCount = parameters[0];
    std::size_t offset = 1U;
    for (std::uint8_t index = 0U; index < reportCount; ++index) {
        if (offset + 9U > length) return;
        RawAdvertisement report;
        report.eventType = parameters[offset++];
        report.addressType = parameters[offset++];
        std::copy_n(parameters + offset, report.address.size(),
                    report.address.begin());
        offset += report.address.size();
        report.payloadLength = parameters[offset++];
        if (report.payloadLength > report.payload.size() ||
            offset + report.payloadLength + 1U > length) {
            return;
        }
        std::copy_n(parameters + offset, report.payloadLength,
                    report.payload.begin());
        offset += report.payloadLength;
        report.rssiDbm = static_cast<std::int8_t>(parameters[offset++]);
        queueReport(report);
    }
}

int handleHciReceive(std::uint8_t* packet, std::uint16_t length) {
    if (packet == nullptr || length < 3U ||
        packet[0] != kHciEventPacket) {
        return 0;
    }
    const std::uint8_t event = packet[1];
    const std::size_t parameterLength = packet[2];
    if (parameterLength + 3U > length) return 0;
    const std::uint8_t* parameters = packet + 3U;
    if (event == kHciCommandCompleteEvent && parameterLength >= 4U) {
        handleCommandResult(readLittleEndian16(parameters + 1U),
                            parameters[3]);
    } else if (event == kHciCommandStatusEvent &&
               parameterLength >= 4U) {
        handleCommandResult(readLittleEndian16(parameters + 2U),
                            parameters[0]);
    } else if (event == kHciLeMetaEvent && parameterLength >= 2U &&
               parameters[0] == kHciLeAdvertisingReport) {
        handleLegacyAdvertisingReports(parameters + 1U,
                                       parameterLength - 1U);
    }
    return 0;
}

void handleHciSendAvailable() {}

const esp_vhci_host_callback_t kHciCallbacks = {
    handleHciSendAvailable,
    handleHciReceive,
};

bool claimCommandSlot(std::uint16_t opcode, std::uint64_t deadlineUs) {
    while (static_cast<std::uint64_t>(esp_timer_get_time()) < deadlineUs) {
        bool claimed = false;
        portENTER_CRITICAL(&hciObserver.lock);
        if (!hciObserver.commandInFlight) {
            hciObserver.commandInFlight = true;
            hciObserver.commandComplete = false;
            hciObserver.expectedOpcode = opcode;
            hciObserver.commandStatus = 0xffU;
            claimed = true;
        }
        portEXIT_CRITICAL(&hciObserver.lock);
        if (claimed) return true;
        vTaskDelay(pdMS_TO_TICKS(1U));
    }
    return false;
}

void releaseCommandSlot() {
    portENTER_CRITICAL(&hciObserver.lock);
    hciObserver.commandInFlight = false;
    hciObserver.commandComplete = false;
    hciObserver.expectedOpcode = 0U;
    portEXIT_CRITICAL(&hciObserver.lock);
}

bool sendHciCommand(std::uint16_t opcode,
                    const std::uint8_t* parameters,
                    std::size_t parameterLength) {
    const bool observerCommand = opcode == kHciLeSetScanParameters ||
        opcode == kHciLeSetScanEnable;
    if (!observerCommand || parameterLength > 12U) return false;
    const std::uint64_t deadlineUs =
        static_cast<std::uint64_t>(esp_timer_get_time()) +
        static_cast<std::uint64_t>(kHciCommandTimeoutMs) * 1000ULL;
    if (!claimCommandSlot(opcode, deadlineUs)) return false;

    while (!esp_vhci_host_check_send_available() &&
           static_cast<std::uint64_t>(esp_timer_get_time()) < deadlineUs) {
        vTaskDelay(pdMS_TO_TICKS(1U));
    }
    if (!esp_vhci_host_check_send_available()) {
        releaseCommandSlot();
        return false;
    }

    std::array<std::uint8_t, 16> packet{};
    packet[0] = kHciCommandPacket;
    packet[1] = static_cast<std::uint8_t>(opcode & 0xffU);
    packet[2] = static_cast<std::uint8_t>(opcode >> 8U);
    packet[3] = static_cast<std::uint8_t>(parameterLength);
    if (parameters != nullptr && parameterLength != 0U) {
        std::copy_n(parameters, parameterLength, packet.begin() + 4U);
    }
    esp_vhci_host_send_packet(packet.data(),
                              static_cast<std::uint16_t>(
                                  parameterLength + 4U));

    bool complete = false;
    std::uint8_t status = 0xffU;
    while (static_cast<std::uint64_t>(esp_timer_get_time()) < deadlineUs) {
        portENTER_CRITICAL(&hciObserver.lock);
        complete = hciObserver.commandComplete;
        status = hciObserver.commandStatus;
        portEXIT_CRITICAL(&hciObserver.lock);
        if (complete) break;
        vTaskDelay(pdMS_TO_TICKS(1U));
    }
    releaseCommandSlot();
    return complete && status == 0U;
}

std::uint16_t scanUnits(std::uint16_t milliseconds) {
    return static_cast<std::uint16_t>(
        (static_cast<std::uint32_t>(milliseconds) * 1000U) / 625U);
}

bool configurePassiveScan(const drivers::ble::BleScanPlan& plan) {
    const std::uint16_t interval = scanUnits(plan.intervalMs);
    const std::uint16_t window = scanUnits(plan.windowMs);
    const std::array<std::uint8_t, 7> parameters = {
        0U,  // passive scan: never transmit scan requests
        static_cast<std::uint8_t>(interval & 0xffU),
        static_cast<std::uint8_t>(interval >> 8U),
        static_cast<std::uint8_t>(window & 0xffU),
        static_cast<std::uint8_t>(window >> 8U),
        0U,  // public own-address type; unused by passive scanning
        0U,  // accept all advertisements
    };
    return sendHciCommand(kHciLeSetScanParameters,
                          parameters.data(), parameters.size());
}

bool setPassiveScanEnabled(bool enabled) {
    const std::array<std::uint8_t, 2> parameters = {
        static_cast<std::uint8_t>(enabled ? 1U : 0U),
        0U,  // controller duplicate filter disabled; fixed host set owns it
    };
    return sendHciCommand(kHciLeSetScanEnable,
                          parameters.data(), parameters.size());
}

void setAcceptingReports(bool accepting) {
    portENTER_CRITICAL(&hciObserver.lock);
    hciObserver.acceptingReports = accepting;
    portEXIT_CRITICAL(&hciObserver.lock);
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

bool deinitializeControllerAfterFailedBootInit() {
    setAcceptingReports(false);
    clearReportQueue();
    return btStop() &&
        esp_bt_controller_get_status() == ESP_BT_CONTROLLER_STATUS_IDLE;
}

bool initializeProcessControllerObserver() {
    if (processControllerInitializationAttempted) {
        return processControllerAvailable &&
            esp_bt_controller_get_status() ==
                ESP_BT_CONTROLLER_STATUS_ENABLED;
    }
    processControllerInitializationAttempted = true;
    if (esp_bt_controller_get_status() != ESP_BT_CONTROLLER_STATUS_IDLE) {
        return false;
    }

    clearReportQueue();
    setAcceptingReports(false);
    // This is the only controller start in the process. It runs during early
    // boot, before any Wi-Fi lifecycle can fragment the internal heap. The
    // controller remains scan-idle between bounded receive windows; terminal
    // paths never repeat the fragile controller init/deinit lifecycle.
    if (!btStart() ||
        esp_vhci_host_register_callback(&kHciCallbacks) != ESP_OK) {
        deinitializeControllerAfterFailedBootInit();
        return false;
    }
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

    // The process-lifetime controller was prewarmed before any Wi-Fi use.
    // sendHciCommand() admits only legacy passive scan parameters and
    // enable/disable opcodes. No HCI RF-TX operation (advertising, initiating,
    // connecting, or active scanning) is representable through this adapter.
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
        const bool started = configurePassiveScan(plan) &&
            setPassiveScanEnabled(true);
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
            const bool disabled = completedWindow
                ? setPassiveScanEnabled(false)
                : true;
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
    const bool cancelled = setPassiveScanEnabled(false);
    activeScan_ = false;
    setAcceptingReports(false);
    return cancelled;
}

bool BoardBlePassiveScanner::prewarmProcessController() {
    return initializeProcessControllerObserver();
}

bool BoardBlePassiveScanner::processControllerReady() {
    return processControllerAvailable &&
        esp_bt_controller_get_status() == ESP_BT_CONTROLLER_STATUS_ENABLED;
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
