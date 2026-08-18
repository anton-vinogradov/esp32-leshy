#include "BoardBlePassiveScanner.h"

#include <algorithm>

#include <BLEAdvertisedDevice.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

namespace leshy1::platform::arduino {

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
    activeScan_->setAdvertisedDeviceCallbacks(nullptr, false, true);
    const std::uint64_t startedUs =
        static_cast<std::uint64_t>(esp_timer_get_time());
    // The blocking BLEScan overload waits forever when NimBLE loses its
    // discovery-complete notification. Run asynchronously with a local,
    // fail-closed deadline so the worker can always release its resources.
    const bool started = activeScan_->start(
        plan.durationMs / 1000U, nullptr, false);
    if (!started) {
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
            activeScan_->clearResults();
            result.durationUs =
                static_cast<std::uint64_t>(esp_timer_get_time()) - startedUs;
            result.status = BoardBleScanStatus::ScanTimedOut;
            return result;
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
    BLEScanResults* results = activeScan_->getResults();
    result.durationUs =
        static_cast<std::uint64_t>(esp_timer_get_time()) - startedUs;
    if (results == nullptr) {
        result.status = BoardBleScanStatus::ScannerUnavailable;
        return result;
    }

    const int reported = std::max(0, results->getCount());
    result.recordsReported = static_cast<std::uint16_t>(
        std::min<int>(reported, 0xffff));
    const std::uint16_t recordsToRead = static_cast<std::uint16_t>(
        std::min<int>(reported, plan.maximumRecords));
    for (std::uint16_t index = 0; index < recordsToRead; ++index) {
        BLEAdvertisedDevice source = results->getDevice(index);
        BLEAddress address = source.getAddress();
        const std::uint8_t* native = address.getNative();
        const String name = source.haveName() ? source.getName() : String();
        drivers::ble::BleAdvertisementRecord record;
        if (native != nullptr) {
#if defined(CONFIG_NIMBLE_ENABLED)
            // NimBLE exposes its native address least-significant byte first;
            // store the same canonical order users see in BLEAddress::toString.
            std::reverse_copy(native, native + record.address.size(),
                              record.address.begin());
#else
            std::copy_n(native, record.address.size(), record.address.begin());
#endif
        }
        record.addressType = source.getAddressType();
        record.rssiDbm = static_cast<std::int16_t>(source.getRSSI());
        record.name = name.c_str();
        record.nameLength = std::min<std::size_t>(
            name.length(), domain::observations::Observation::kLabelCapacity);
        ++result.recordsRead;
        switch (visitor(record,
                        static_cast<std::uint64_t>(esp_timer_get_time()),
                        context)) {
            case BleRecordDisposition::Accepted: ++result.accepted; break;
            case BleRecordDisposition::Rejected: ++result.rejected; break;
            case BleRecordDisposition::Dropped: ++result.dropped; break;
        }
    }
    if (result.recordsReported > result.recordsRead) {
        result.dropped = static_cast<std::uint16_t>(
            result.dropped + result.recordsReported - result.recordsRead);
    }
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
