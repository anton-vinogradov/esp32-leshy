#include "BoardBlePassiveScanner.h"

#include <algorithm>
#include <cstdio>
#include <cstring>

#include <BLEAdvertisedDevice.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include <BLEUUID.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

namespace leshy1::platform::arduino {

namespace {

bool advertisesUuid(BLEAdvertisedDevice& source, std::uint16_t value) {
    const BLEUUID expected(value);
    for (int index = 0; index < source.getServiceUUIDCount(); ++index) {
        if (source.getServiceUUID(index).equals(expected)) return true;
    }
    for (int index = 0; index < source.getServiceDataUUIDCount(); ++index) {
        if (source.getServiceDataUUID(index).equals(expected)) return true;
    }
    return false;
}

std::uint16_t knownServiceMask(BLEAdvertisedDevice& source) {
    using Facts = domain::observations::BleAdvertisementFacts;
    struct Known final {
        std::uint16_t uuid;
        std::uint16_t mask;
    };
    static constexpr Known kKnown[] = {
        {0x1812, Facts::kServiceHid},
        {0x180f, Facts::kServiceBattery},
        {0x180d, Facts::kServiceHeartRate},
        {0x1809, Facts::kServiceThermometer},
        {0x1826, Facts::kServiceFitness},
        {0xfeaa, Facts::kServiceEddystone},
        {0xfe95, Facts::kServiceXiaomi},
        {0xfd5a, Facts::kServiceSmartTag},
        {0xfeed, Facts::kServiceTile},
        {0xfe9f, Facts::kServiceFastPair},
        {0xfd6f, Facts::kServiceExposure},
    };
    std::uint16_t mask = 0U;
    for (const Known& known : kKnown) {
        if (advertisesUuid(source, known.uuid)) mask |= known.mask;
    }
    return mask;
}

void populateAdvertisementFacts(
        BLEAdvertisedDevice& source,
        domain::observations::BleAdvertisementFacts* facts) {
    if (facts == nullptr) return;
    *facts = {};
    facts->present = true;
    facts->addressType = source.getAddressType();
    facts->advertisementType = source.getAdvType();
    facts->legacy = source.isLegacyAdvertisement();
    facts->scannable = source.isScannable();
    facts->connectable = source.isConnectable();
    facts->txPowerKnown = source.haveTXPower();
    if (facts->txPowerKnown) facts->txPowerDbm = source.getTXPower();
    facts->appearanceKnown = source.haveAppearance();
    if (facts->appearanceKnown) facts->appearance = source.getAppearance();
    const String manufacturer = source.haveManufacturerData()
        ? source.getManufacturerData() : String();
    facts->manufacturerDataLength = static_cast<std::uint8_t>(
        std::min<std::size_t>(manufacturer.length(), UINT8_MAX));
    if (manufacturer.length() >= 2U) {
        facts->companyKnown = true;
        facts->companyId = static_cast<std::uint16_t>(
            static_cast<std::uint8_t>(manufacturer[0]) |
            (static_cast<std::uint16_t>(
                static_cast<std::uint8_t>(manufacturer[1])) << 8U));
        if (facts->companyId == 0x004cU && manufacturer.length() >= 3U) {
            facts->appleContinuityType =
                static_cast<std::uint8_t>(manufacturer[2]);
        }
    }
    facts->knownServiceMask = knownServiceMask(source);
    const int advertised = source.getServiceUUIDCount();
    const int serviceData = source.getServiceDataUUIDCount();
    facts->serviceUuidCount = static_cast<std::uint8_t>(
        std::min(advertised + serviceData, static_cast<int>(UINT8_MAX)));
    facts->serviceDataCount = static_cast<std::uint8_t>(
        std::min(source.getServiceDataCount(), static_cast<int>(UINT8_MAX)));
    if (advertised > 0 || serviceData > 0) {
        const String uuid = advertised > 0
            ? source.getServiceUUID(0).toString()
            : source.getServiceDataUUID(0).toString();
        std::uint32_t hash = 2166136261UL;
        for (std::size_t index = 0; index < uuid.length(); ++index) {
            hash ^= static_cast<std::uint8_t>(uuid[index]);
            hash *= 16777619UL;
        }
        facts->firstServiceUuidHash = hash;
        const char* visible = uuid.c_str();
        char compact[7] = {};
        if (uuid.length() > 10U) {
            std::snprintf(compact, sizeof(compact), "0x%.4s", uuid.c_str() + 4);
            visible = compact;
        }
        const std::size_t length = std::min<std::size_t>(
            std::strlen(visible), facts->firstServiceUuid.size() - 1U);
        std::copy_n(visible, length, facts->firstServiceUuid.begin());
        facts->firstServiceUuid[length] = '\0';
        facts->firstServiceUuidLength =
            static_cast<std::uint8_t>(length);
    }
    facts->payloadLength = static_cast<std::uint8_t>(
        std::min<std::size_t>(source.getPayloadLength(), UINT8_MAX));
}

class BoundedAdvertisementCallbacks final
    : public BLEAdvertisedDeviceCallbacks {
public:
    BoundedAdvertisementCallbacks(
        BLEScan* scanner, std::uint16_t maximumRecords,
        BleRecordVisitor visitor, void* context,
        BoardBlePassiveScanResult* result)
        : scanner_(scanner), maximumRecords_(maximumRecords),
          visitor_(visitor), context_(context), result_(result) {}

    void onResult(BLEAdvertisedDevice source) override {
        if (result_ == nullptr || scanner_ == nullptr) return;
        if (result_->recordsReported != UINT16_MAX) {
            ++result_->recordsReported;
        }
        if (result_->recordsRead < maximumRecords_) {
            BLEAddress address = source.getAddress();
            const std::uint8_t* native = address.getNative();
            const String name = source.haveName() ? source.getName() : String();
            drivers::ble::BleAdvertisementRecord record;
            if (native != nullptr) {
#if defined(CONFIG_NIMBLE_ENABLED)
                std::reverse_copy(native, native + record.address.size(),
                                  record.address.begin());
#else
                std::copy_n(native, record.address.size(),
                            record.address.begin());
#endif
            }
            record.addressType = source.getAddressType();
            record.rssiDbm = static_cast<std::int16_t>(source.getRSSI());
            record.name = name.c_str();
            record.nameLength = std::min<std::size_t>(
                name.length(),
                domain::observations::Observation::kLabelCapacity);
            populateAdvertisementFacts(source, &record.advertisement);
            ++result_->recordsRead;
            switch (visitor_(
                record, static_cast<std::uint64_t>(esp_timer_get_time()),
                context_)) {
                case BleRecordDisposition::Accepted:
                    ++result_->accepted;
                    break;
                case BleRecordDisposition::Rejected:
                    ++result_->rejected;
                    break;
                case BleRecordDisposition::Dropped:
                    ++result_->dropped;
                    break;
            }
        } else if (result_->dropped != UINT16_MAX) {
            ++result_->dropped;
        }
        // Arduino BLE stores every unique advertiser before invoking us. Erase
        // it immediately so hostile/dense RF environments cannot grow an
        // unbounded std::map and terminate the NimBLE host task on OOM.
        scanner_->erase(source.getAddress());
    }

private:
    BLEScan* scanner_ = nullptr;
    std::uint16_t maximumRecords_ = 0;
    BleRecordVisitor visitor_ = nullptr;
    void* context_ = nullptr;
    BoardBlePassiveScanResult* result_ = nullptr;
};

}  // namespace

BLEScan* BoardBlePassiveScanner::activeScan_ = nullptr;

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
    activeScan_ = BLEDevice::getScan();
    if (activeScan_ == nullptr) {
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
    if (!initialized_ || activeScan_ == nullptr) return result;
    if (!drivers::ble::validatePassivePlan(plan) || visitor == nullptr) {
        result.status = BoardBleScanStatus::InvalidPlan;
        return result;
    }

    // Receive-only is a product invariant. Active scanning would transmit GAP
    // scan requests and is intentionally never exposed by this adapter.
    activeScan_->setActiveScan(false);
    activeScan_->setInterval(plan.intervalMs);
    activeScan_->setWindow(plan.windowMs);
    BoundedAdvertisementCallbacks callbacks(
        activeScan_, plan.maximumRecords, visitor, context, &result);
    activeScan_->setAdvertisedDeviceCallbacks(&callbacks, false, true);
#if defined(CONFIG_NIMBLE_ENABLED)
    activeScan_->setDuplicateFilter(true);
#endif
    const std::uint64_t startedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    // The blocking BLEScan overload waits forever when NimBLE loses its
    // discovery-complete notification. Run asynchronously with a local,
    // fail-closed deadline so the worker can always release its resources.
    // One bounded passive retry recovers the observed ESP BLE transport case
    // where start succeeds but that completion notification is lost. A second
    // failure is terminal; this never enables active scanning or transmission.
    constexpr std::uint16_t kMaximumScanAttempts = 2U;
    constexpr std::uint32_t kCompletionGraceMs = 1000U;
    for (std::uint16_t attempt = 1U;
         attempt <= kMaximumScanAttempts; ++attempt) {
        result.attempts = attempt;
        const std::uint64_t attemptStartedUs =
            static_cast<std::uint64_t>(esp_timer_get_time());
        const bool started = activeScan_->start(
            plan.durationMs / 1000U, nullptr, false);
        if (!started) {
            result.status = BoardBleScanStatus::ScannerUnavailable;
        } else {
            const std::uint64_t deadlineUs = attemptStartedUs +
                static_cast<std::uint64_t>(
                    plan.durationMs + kCompletionGraceMs) * 1000ULL;
            while (activeScan_->isScanning() &&
                   static_cast<std::uint64_t>(esp_timer_get_time()) <
                       deadlineUs) {
                vTaskDelay(pdMS_TO_TICKS(20));
            }
            if (activeScan_->isScanning()) {
                activeScan_->stop();
                result.status = BoardBleScanStatus::ScanTimedOut;
            } else {
                result.status = BoardBleScanStatus::Valid;
            }
        }
        if (result.valid() || attempt == kMaximumScanAttempts) break;
        if (result.status != BoardBleScanStatus::ScannerUnavailable &&
            result.status != BoardBleScanStatus::ScanTimedOut) {
            break;
        }
        ++result.transientRetries;
        activeScan_->clearResults();
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    activeScan_->setAdvertisedDeviceCallbacks(nullptr, false, true);
    result.durationUs =
        static_cast<std::uint64_t>(esp_timer_get_time()) - startedUs;
    activeScan_->clearResults();
    return result;
}

bool BoardBlePassiveScanner::cancelActiveScan() {
    return activeScan_ == nullptr || !activeScan_->isScanning() ||
           activeScan_->stop();
}

bool BoardBlePassiveScanner::end() {
    bool complete = true;
    if (activeScan_ != nullptr) {
        if (activeScan_->isScanning() && !activeScan_->stop()) complete = false;
        activeScan_->clearResults();
    }
    activeScan_ = nullptr;
    if (initialized_) BLEDevice::deinit(false);
    initialized_ = false;
    cleanupComplete_ = complete;
    return complete;
}

}  // namespace leshy1::platform::arduino
