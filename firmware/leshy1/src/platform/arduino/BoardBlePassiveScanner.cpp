#include "BoardBlePassiveScanner.h"

#include <algorithm>

#include <BLEAdvertisedDevice.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

namespace leshy1::platform::arduino {

namespace {

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
    const bool started = activeScan_->start(
        plan.durationMs / 1000U, nullptr, false);
    if (!started) {
        activeScan_->setAdvertisedDeviceCallbacks(nullptr, false, true);
        result.status = BoardBleScanStatus::ScannerUnavailable;
        return result;
    }
    constexpr std::uint32_t kCompletionGraceMs = 1000U;
    const std::uint64_t deadlineUs = startedUs +
        static_cast<std::uint64_t>(plan.durationMs + kCompletionGraceMs) *
            1000ULL;
    while (activeScan_->isScanning()) {
        if (static_cast<std::uint64_t>(esp_timer_get_time()) >= deadlineUs) {
            activeScan_->stop();
            activeScan_->setAdvertisedDeviceCallbacks(nullptr, false, true);
            activeScan_->clearResults();
            result.durationUs =
                static_cast<std::uint64_t>(esp_timer_get_time()) - startedUs;
            result.status = BoardBleScanStatus::ScanTimedOut;
            return result;
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
    activeScan_->setAdvertisedDeviceCallbacks(nullptr, false, true);
    result.durationUs =
        static_cast<std::uint64_t>(esp_timer_get_time()) - startedUs;
    activeScan_->clearResults();
    result.status = BoardBleScanStatus::Valid;
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
