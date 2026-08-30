#pragma once

#include <atomic>
#include <array>
#include <cstdint>

#include "drivers/ble/BlePassiveContract.h"
#include "services/ble/BleInspector.h"

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

enum class BoardBleBeginStage : std::uint8_t {
    NotAttempted,
    ReusedReady,
    ControllerInit,
    HostSync,
    Ready,
};

const char* boardBleBeginStageName(BoardBleBeginStage stage);

// One-shot physical-HIL faults for the connected CAP-051 lifecycle. They are
// armed only by an active HIL session in ArduinoEntry and never add a pairing,
// characteristic read/write or subscription operation to the product API.
enum class BoardBleGattHilFault : std::uint8_t {
    None,
    UnexpectedPeer,
    Timeout,
    ResourceConflict,
    DisconnectFailure,
};

const char* boardBleGattHilFaultName(BoardBleGattHilFault fault);

// Bounded, PII-free evidence for the most recent controller/host bootstrap.
// The exact native error and internal-heap snapshots make an unavailable BLE
// receiver diagnosable without exposing any observed radio identity.
struct BoardBleBeginDiagnostic final {
    BoardBleBeginStage stage = BoardBleBeginStage::NotAttempted;
    int error = 0;
    std::uint32_t heapFreeBefore = 0;
    std::uint32_t heapLargestBefore = 0;
    std::uint32_t heapFreeAfter = 0;
    std::uint32_t heapLargestAfter = 0;
    bool cleanupComplete = true;
};

struct BoardBlePassiveScanResult final {
    BoardBleScanStatus status = BoardBleScanStatus::NotStarted;
    std::uint64_t durationUs = 0;
    std::uint16_t attempts = 0;
    std::uint16_t transientRetries = 0;
    std::uint16_t recordsObserved = 0;
    std::uint16_t recordsReported = 0;
    std::uint16_t recordsRead = 0;
    std::uint16_t accepted = 0;
    std::uint16_t rejected = 0;
    std::uint16_t dropped = 0;
    std::uint16_t queueHighWater = 0;

    bool valid() const { return status == BoardBleScanStatus::Valid; }
};

class BoardBlePassiveScanner final {
public:
    // The callback queue is drained every 5 ms. Keeping this burst buffer
    // bounded at 32 reports returns 1280 bytes of scarce internal RAM to the
    // subsequent connected GATT transport. Any insufficient burst capacity
    // remains observable and fail-closed through dropped/queueHighWater.
    static constexpr std::size_t kReportQueueCapacity = 32U;
    static constexpr std::uint16_t kMaximumScanAttempts = 2U;
    static constexpr std::uint32_t kCompletionGraceMs = 1000U;
    static constexpr std::uint32_t kRetryDelayMs = 100U;
    static constexpr std::uint32_t kHostShutdownTimeoutMs = 2000U;

    static constexpr std::uint64_t worstCaseScanDurationUs(
        const drivers::ble::BleScanPlan& plan) {
        return (static_cast<std::uint64_t>(plan.durationMs) +
                kCompletionGraceMs) *
                   kMaximumScanAttempts * 1000ULL +
               static_cast<std::uint64_t>(kMaximumScanAttempts - 1U) *
                   kRetryDelayMs * 1000ULL;
    }

    ~BoardBlePassiveScanner() { end(); }

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
    const BoardBleBeginDiagnostic& beginDiagnostic() const {
        return beginDiagnostic_;
    }

private:
    bool initialized_ = false;
    bool passiveOnly_ = true;
    bool cleanupComplete_ = true;
    BoardBleBeginDiagnostic beginDiagnostic_{};
    static volatile bool activeScan_;
    static std::atomic_bool cancelRequested_;
};

// One-shot connected transport for CAP-051. The public virtual surface stays
// limited to connect, metadata discovery and disconnect; pairing, reads,
// writes and subscriptions are deliberately not representable. The concrete
// helpers serialize the asynchronous NimBLE callbacks with the foreground
// controller and expose only copied, bounded facts to the UI.
class BoardBleGattInspectorTransport final
    : public services::ble::BleGattInspectorTransport {
public:
    static constexpr std::uint32_t kConnectTimeoutMs = 8000U;

    bool bind(services::ble::BleGattInspector* inspector);
    bool unbind();
    bool service(std::uint64_t nowMonotonicUs);

    bool selectTarget(const services::ble::BleInspectorTarget& target,
                      std::uint64_t nowMonotonicUs);
    bool reviewPermission(
        services::ble::BleGattInspectorPermission permission);
    std::uint64_t confirmationToken() const;
    bool confirm(std::uint64_t token, std::uint64_t nowMonotonicUs);
    bool back(std::uint64_t nowMonotonicUs);
    bool tick(std::uint64_t nowMonotonicUs);
    services::ble::BleGattInspectorState state() const;
    services::ble::BleGattInspectorFailure failure() const;
    services::ble::BleGattInspectorFailure cleanupCause() const;
    std::size_t serviceCount() const;
    std::size_t characteristicCount() const;
    bool copyService(std::size_t index,
                     services::ble::BleGattServiceFact* output) const;
    bool copyCharacteristic(
        std::size_t index,
        services::ble::BleGattCharacteristicFact* output) const;
    bool copyTarget(services::ble::BleInspectorTarget* output) const;
    bool cleanupComplete() const;
    bool ownsRadio() const;
    bool hostReady() const;
    bool connected() const;
    bool connecting() const;
    bool disconnected() const;
    bool cleanupRequested() const;
    bool armHilFault(BoardBleGattHilFault fault);
    void clearHilFault();
    bool consumeHilFault(BoardBleGattHilFault fault);
    BoardBleGattHilFault armedHilFault() const;
    BoardBleGattHilFault lastConsumedHilFault() const;
    std::uint32_t hilFaultConsumedCount() const;
    std::uint32_t heapFreeBefore() const { return heapFreeBefore_; }
    std::uint32_t heapLargestBefore() const { return heapLargestBefore_; }
    std::uint32_t heapFreeAfterInit() const { return heapFreeAfterInit_; }
    std::uint32_t heapLargestAfterInit() const {
        return heapLargestAfterInit_;
    }
    std::uint32_t heapMinimum() const {
        return heapFreeBefore_ == 0U ? 0U : heapMinimum_;
    }

    bool startConnect(
        const services::ble::BleInspectorTarget& target) override;
    bool startServiceDiscovery() override;
    services::ble::BleGattDisconnectStatus requestDisconnect() override;
    services::ble::BleGattDisconnectStatus pollDisconnect() override;

    int handleGapEvent(void* event);
    int handleServiceDiscovery(std::uint16_t connHandle,
                               const void* error, const void* service);
    int handleCharacteristicDiscovery(std::uint16_t connHandle,
                                      const void* error,
                                      const void* characteristic);

private:
    bool startNextCharacteristicDiscovery(
        std::uint64_t nowMonotonicUs);
    void updateHeapMinimum();

    services::ble::BleGattInspector* inspector_ = nullptr;
    services::ble::BleInspectorTarget target_{};
    std::uint16_t connectionHandle_ = 0xffffU;
    std::size_t characteristicServiceIndex_ = 0U;
    std::atomic_bool connecting_{false};
    std::atomic_bool connected_{false};
    std::atomic_bool disconnected_{true};
    std::atomic_bool remoteDisconnectPending_{false};
    std::atomic_bool cleanupRequested_{false};
    std::atomic<std::uint8_t> armedHilFault_{
        static_cast<std::uint8_t>(BoardBleGattHilFault::None)};
    std::atomic<std::uint8_t> lastConsumedHilFault_{
        static_cast<std::uint8_t>(BoardBleGattHilFault::None)};
    std::atomic<std::uint32_t> hilFaultConsumedCount_{0U};
    bool hostReady_ = false;
    std::uint32_t heapFreeBefore_ = 0U;
    std::uint32_t heapLargestBefore_ = 0U;
    std::uint32_t heapFreeAfterInit_ = 0U;
    std::uint32_t heapLargestAfterInit_ = 0U;
    std::uint32_t heapMinimum_ = UINT32_MAX;
};

}  // namespace leshy1::platform::arduino
