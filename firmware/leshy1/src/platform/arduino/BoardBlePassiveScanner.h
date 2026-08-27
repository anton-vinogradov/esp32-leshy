#pragma once

#include <cstdint>

#include "drivers/ble/BlePassiveContract.h"

namespace leshy1::platform::arduino {

enum class BleRecordDisposition : std::uint8_t {
    Accepted,
    Rejected,
    Dropped,
};

using BleRecordVisitor = BleRecordDisposition (*)(
    const drivers::ble::BleAdvertisementRecord& record,
    std::uint64_t monotonicUs, void* context);

enum class BoardBleScanStatus : std::uint8_t {
    Valid,
    NotStarted,
    InvalidPlan,
    StackInitFailed,
    ScannerUnavailable,
    ScanTimedOut,
};

const char* boardBleScanStatusName(BoardBleScanStatus status);

struct BoardBlePassiveScanResult final {
    BoardBleScanStatus status = BoardBleScanStatus::NotStarted;
    std::uint64_t durationUs = 0;
    std::uint16_t attempts = 0;
    std::uint16_t transientRetries = 0;
    std::uint16_t recordsReported = 0;
    std::uint16_t recordsRead = 0;
    std::uint16_t accepted = 0;
    std::uint16_t rejected = 0;
    std::uint16_t dropped = 0;

    bool valid() const { return status == BoardBleScanStatus::Valid; }
};

class BoardBlePassiveScanner final {
public:
    static constexpr std::uint16_t kMaximumScanAttempts = 2U;
    static constexpr std::uint32_t kCompletionGraceMs = 1000U;
    static constexpr std::uint32_t kRetryDelayMs = 100U;

    static constexpr std::uint64_t worstCaseScanDurationUs(
        const drivers::ble::BleScanPlan& plan) {
        return (static_cast<std::uint64_t>(plan.durationMs) +
                kCompletionGraceMs) *
                   kMaximumScanAttempts * 1000ULL +
               static_cast<std::uint64_t>(kMaximumScanAttempts - 1U) *
                   kRetryDelayMs * 1000ULL;
    }

    ~BoardBlePassiveScanner() { end(); }

    // Initialize the receive-only Bluetooth controller while the boot heap is
    // still contiguous. The controller is intentionally process-lifetime;
    // individual scanner instances only own passive scan windows.
    static bool prewarmProcessController();
    static bool processControllerReady();
    bool begin();
    BoardBlePassiveScanResult scan(
        const drivers::ble::BleScanPlan& plan,
        BleRecordVisitor visitor, void* context);
    static bool cancelActiveScan();
    bool end();

    bool initialized() const { return initialized_; }
    bool passiveOnly() const { return passiveOnly_; }
    bool cleanupComplete() const { return cleanupComplete_; }

private:
    bool initialized_ = false;
    bool passiveOnly_ = true;
    bool cleanupComplete_ = true;
    static volatile bool activeScan_;
};

}  // namespace leshy1::platform::arduino
