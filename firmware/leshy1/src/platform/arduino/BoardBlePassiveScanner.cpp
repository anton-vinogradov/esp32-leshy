#include "BoardBlePassiveScanner.h"

#include <algorithm>
#include <array>
#include <cstdio>
#include <cstring>

#include <BLEDevice.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

extern "C" {
#include <host/ble_gap.h>
#include <host/ble_hs_adv.h>
#include <host/ble_hs_id.h>
#include <host/ble_uuid.h>
#include <nimble/hci_common.h>
}

namespace leshy1::platform::arduino {

namespace {

using AdvertisementFacts =
    domain::observations::BleAdvertisementFacts;

struct RawScanContext final {
    std::array<std::array<std::uint8_t, 6>, 128> seenAddresses{};
    std::uint16_t seenCount = 0;
    std::uint16_t maximumRecords = 0;
    BleRecordVisitor visitor = nullptr;
    void* visitorContext = nullptr;
    BoardBlePassiveScanResult* result = nullptr;
    volatile bool completionReported = false;
    volatile int completionReason = 0;
};

void increment(std::uint16_t* value) {
    if (value != nullptr && *value != UINT16_MAX) ++*value;
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

void retainFirstServiceUuid(const ble_hs_adv_fields& fields,
                            AdvertisementFacts* facts) {
    if (facts == nullptr) return;
    char uuid[BLE_UUID_STR_LEN] = {};
    if (fields.num_uuids16 != 0U && fields.uuids16 != nullptr) {
        std::snprintf(uuid, sizeof(uuid), "%04x",
                      static_cast<unsigned>(fields.uuids16[0].value));
    } else if (fields.num_uuids32 != 0U && fields.uuids32 != nullptr) {
        std::snprintf(uuid, sizeof(uuid), "%08lx",
                      static_cast<unsigned long>(fields.uuids32[0].value));
    } else if (fields.num_uuids128 != 0U && fields.uuids128 != nullptr) {
        ble_uuid_to_str(&fields.uuids128[0].u, uuid);
    } else if (fields.svc_data_uuid16 != nullptr &&
               fields.svc_data_uuid16_len >= 2U) {
        std::snprintf(uuid, sizeof(uuid), "%04x", static_cast<unsigned>(
            readLittleEndian16(fields.svc_data_uuid16)));
    } else if (fields.svc_data_uuid32 != nullptr &&
               fields.svc_data_uuid32_len >= 4U) {
        std::snprintf(uuid, sizeof(uuid), "%08lx",
                      static_cast<unsigned long>(
                          readLittleEndian32(fields.svc_data_uuid32)));
    } else if (fields.svc_data_uuid128 != nullptr &&
               fields.svc_data_uuid128_len >= 16U) {
        ble_uuid128_t service{};
        service.u.type = BLE_UUID_TYPE_128;
        std::copy_n(fields.svc_data_uuid128, sizeof(service.value),
                    service.value);
        ble_uuid_to_str(&service.u, uuid);
    } else {
        return;
    }

    std::uint32_t hash = 2166136261UL;
    for (const char* value = uuid; *value != '\0'; ++value) {
        hash ^= static_cast<std::uint8_t>(*value);
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

void populateAdvertisementFacts(const ble_gap_disc_desc& source,
                                const ble_hs_adv_fields* parsed,
                                AdvertisementFacts* facts) {
    if (facts == nullptr) return;
    *facts = {};
    facts->present = true;
    facts->addressType = source.addr.type;
    facts->advertisementType = source.event_type;
    facts->legacy = true;
    facts->scannable =
        source.event_type == BLE_HCI_ADV_RPT_EVTYPE_ADV_IND ||
        source.event_type == BLE_HCI_ADV_RPT_EVTYPE_SCAN_IND;
    facts->connectable =
        source.event_type == BLE_HCI_ADV_RPT_EVTYPE_ADV_IND ||
        source.event_type == BLE_HCI_ADV_RPT_EVTYPE_DIR_IND;
    facts->payloadLength = source.length_data;
    if (parsed == nullptr) return;

    facts->txPowerKnown = parsed->tx_pwr_lvl_is_present != 0U;
    if (facts->txPowerKnown) facts->txPowerDbm = parsed->tx_pwr_lvl;
    facts->appearanceKnown = parsed->appearance_is_present != 0U;
    if (facts->appearanceKnown) facts->appearance = parsed->appearance;
    facts->manufacturerDataLength = parsed->mfg_data_len;
    if (parsed->mfg_data != nullptr && parsed->mfg_data_len >= 2U) {
        facts->companyKnown = true;
        facts->companyId = readLittleEndian16(parsed->mfg_data);
        if (facts->companyId == 0x004cU && parsed->mfg_data_len >= 3U) {
            facts->appleContinuityType = parsed->mfg_data[2];
        }
    }

    for (std::uint8_t index = 0; index < parsed->num_uuids16; ++index) {
        facts->knownServiceMask |= serviceMask(parsed->uuids16[index].value);
    }
    if (parsed->svc_data_uuid16 != nullptr &&
        parsed->svc_data_uuid16_len >= 2U) {
        facts->knownServiceMask |= serviceMask(
            readLittleEndian16(parsed->svc_data_uuid16));
    }
    const std::uint16_t serviceDataCount =
        static_cast<std::uint16_t>(
            parsed->svc_data_uuid16 != nullptr &&
            parsed->svc_data_uuid16_len >= 2U) +
        static_cast<std::uint16_t>(
            parsed->svc_data_uuid32 != nullptr &&
            parsed->svc_data_uuid32_len >= 4U) +
        static_cast<std::uint16_t>(
            parsed->svc_data_uuid128 != nullptr &&
            parsed->svc_data_uuid128_len >= 16U);
    facts->serviceDataCount = static_cast<std::uint8_t>(serviceDataCount);
    const std::uint16_t serviceUuidCount =
        static_cast<std::uint16_t>(parsed->num_uuids16) +
        static_cast<std::uint16_t>(parsed->num_uuids32) +
        static_cast<std::uint16_t>(parsed->num_uuids128) + serviceDataCount;
    facts->serviceUuidCount = static_cast<std::uint8_t>(
        std::min<std::uint16_t>(serviceUuidCount, UINT8_MAX));
    retainFirstServiceUuid(*parsed, facts);
}

void processAdvertisement(const ble_gap_disc_desc& source,
                          RawScanContext* context) {
    if (context == nullptr || context->result == nullptr ||
        context->visitor == nullptr) {
        return;
    }
    std::array<std::uint8_t, 6> canonicalAddress{};
    std::reverse_copy(source.addr.val,
                      source.addr.val + canonicalAddress.size(),
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

    ble_hs_adv_fields fields{};
    const bool parsed = source.data != nullptr &&
        ble_hs_adv_parse_fields(&fields, source.data,
                                source.length_data) == 0;
    drivers::ble::BleAdvertisementRecord record;
    record.address = canonicalAddress;
    record.addressType = source.addr.type;
    record.rssiDbm = static_cast<std::int16_t>(source.rssi);
    if (parsed && fields.name != nullptr) {
        record.name = reinterpret_cast<const char*>(fields.name);
        record.nameLength = std::min<std::size_t>(
            fields.name_len,
            domain::observations::Observation::kLabelCapacity);
    }
    populateAdvertisementFacts(source, parsed ? &fields : nullptr,
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

int handleGapEvent(ble_gap_event* event, void* argument) {
    auto* context = static_cast<RawScanContext*>(argument);
    if (event == nullptr || context == nullptr) return 0;
    if (event->type == BLE_GAP_EVENT_DISC) {
        processAdvertisement(event->disc, context);
    } else if (event->type == BLE_GAP_EVENT_DISC_COMPLETE) {
        context->completionReason = event->disc_complete.reason;
        context->completionReported = true;
    }
    return 0;
}

std::uint16_t scanUnits(std::uint16_t milliseconds) {
    return static_cast<std::uint16_t>(
        (static_cast<std::uint32_t>(milliseconds) * 1000U) / 625U);
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
    if (initialized_) return false;
    cleanupComplete_ = false;
    passiveOnly_ = true;
    if (!BLEDevice::init("")) {
        cleanupComplete_ = true;
        return false;
    }
    if (ble_hs_id_infer_auto(0, &ownAddressType_) != 0) {
        BLEDevice::deinit(false);
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

    ble_gap_disc_params parameters{};
    parameters.passive = 1;
    parameters.limited = 0;
    // Receive every advertisement and deduplicate into a fixed 128-address
    // array. This preserves later enrichment packets without the Arduino BLE
    // wrapper's unbounded heap-backed result objects and address map.
    parameters.filter_duplicates = 0;
    parameters.filter_policy = BLE_HCI_SCAN_FILT_NO_WL;
    parameters.itvl = scanUnits(plan.intervalMs);
    parameters.window = scanUnits(plan.windowMs);

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
        scanContext.completionReported = false;
        scanContext.completionReason = 0;
        const std::uint64_t attemptStartedUs =
            static_cast<std::uint64_t>(esp_timer_get_time());
        activeScan_ = true;
        const int started = ble_gap_disc(
            ownAddressType_, static_cast<std::int32_t>(plan.durationMs),
            &parameters, handleGapEvent, &scanContext);
        if (started != 0) {
            activeScan_ = false;
            result.status = BoardBleScanStatus::ScannerUnavailable;
        } else {
            const std::uint64_t deadlineUs = attemptStartedUs +
                static_cast<std::uint64_t>(
                    plan.durationMs + kCompletionGraceMs) * 1000ULL;
            while (!scanContext.completionReported &&
                   ble_gap_disc_active() != 0 &&
                   static_cast<std::uint64_t>(esp_timer_get_time()) <
                       deadlineUs) {
                vTaskDelay(pdMS_TO_TICKS(20));
            }
            if (ble_gap_disc_active() != 0) {
                ble_gap_disc_cancel();
                result.status = BoardBleScanStatus::ScanTimedOut;
            } else if (scanContext.completionReported) {
                result.status = BoardBleScanStatus::Valid;
            } else {
                result.status = BoardBleScanStatus::ScannerUnavailable;
            }
            activeScan_ = false;
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
    if (!activeScan_ || ble_gap_disc_active() == 0) return true;
    const int cancelled = ble_gap_disc_cancel();
    activeScan_ = false;
    return cancelled == 0 || cancelled == BLE_HS_EALREADY;
}

bool BoardBlePassiveScanner::end() {
    if (!initialized_) {
        activeScan_ = false;
        return cleanupComplete_;
    }
    bool complete = cancelActiveScan();
    complete = complete && ble_gap_disc_active() == 0;
    BLEDevice::deinit(false);
    initialized_ = false;
    activeScan_ = false;
    cleanupComplete_ = complete;
    return cleanupComplete_;
}

}  // namespace leshy1::platform::arduino
