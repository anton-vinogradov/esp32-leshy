#pragma once

#include <cstddef>
#include <cstdint>

#include "drivers/wifi/WifiPassiveContract.h"

namespace leshy1::platform::arduino {

enum class WifiRecordDisposition : std::uint8_t {
    Accepted,
    Rejected,
    Dropped,
};

using WifiRecordVisitor = WifiRecordDisposition (*)(
    const drivers::wifi::WifiScanRecord& record,
    std::uint64_t monotonicUs, void* context);

enum class BoardWifiScanStatus : std::uint8_t {
    Valid,
    NotStarted,
    InvalidPlan,
    ScanFailed,
    CountFailed,
    RecordFailed,
};

const char* boardWifiScanStatusName(BoardWifiScanStatus status);

struct BoardWifiPassiveScanResult final {
    BoardWifiScanStatus status = BoardWifiScanStatus::NotStarted;
    int driverError = 0;
    std::uint64_t durationUs = 0;
    std::uint16_t recordsReported = 0;
    std::uint16_t recordsRead = 0;
    std::uint16_t accepted = 0;
    std::uint16_t rejected = 0;
    std::uint16_t dropped = 0;

    bool valid() const { return status == BoardWifiScanStatus::Valid; }
};

class BoardWifiPassiveScanner final {
public:
    static constexpr std::uint16_t kMaximumRecordsVisited = 128;

    ~BoardWifiPassiveScanner() { end(); }

    bool begin();
    BoardWifiPassiveScanResult scan(
        const drivers::wifi::WifiScanPlan& plan,
        WifiRecordVisitor visitor, void* context);
    // Thread-safe cancellation hook for a blocking ESP-IDF scan owned by a
    // worker task. The worker still owns end() and all lifecycle cleanup.
    static bool cancelActiveScan();
    bool end();

    bool initialized() const { return initialized_; }
    bool started() const { return started_; }
    bool nvsDisabled() const { return nvsDisabled_; }
    bool volatileStorageOnly() const { return volatileStorageOnly_; }
    bool eventLoopReady() const { return eventLoopReady_; }
    bool cleanupComplete() const { return cleanupComplete_; }
    int lastError() const { return lastError_; }

private:
    bool initialized_ = false;
    bool started_ = false;
    bool nvsDisabled_ = false;
    bool volatileStorageOnly_ = false;
    bool eventLoopReady_ = false;
    bool eventLoopOwned_ = false;
    bool cleanupComplete_ = true;
    int lastError_ = 0;
};

}  // namespace leshy1::platform::arduino
