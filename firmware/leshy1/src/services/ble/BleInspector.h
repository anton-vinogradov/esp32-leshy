#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "drivers/ble/BlePassiveContract.h"
#include "kernel/runtime/ResourceBroker.h"

namespace leshy1::services::ble {

struct BleInspectorTarget final {
    std::array<std::uint8_t, 6> address{};
    std::uint8_t addressType = 0;
    std::uint64_t observedMonotonicUs = 0;
};

bool validBleInspectorTarget(const BleInspectorTarget& target);

enum class BleInspectorCaptureState : std::uint8_t {
    Idle,
    Running,
    Frozen,
};

enum class BleInspectorCaptureDisposition : std::uint8_t {
    Accepted,
    DifferentTarget,
    InvalidRecord,
    CapacityReached,
    NotRunning,
};

struct BleInspectorRawAdvertisement final {
    std::array<std::uint8_t, 6> address{};
    std::array<std::uint8_t,
               drivers::ble::kLegacyAdvertisementPayloadCapacity>
        payload{};
    std::uint64_t monotonicUs = 0;
    std::int16_t rssiDbm = 0;
    std::uint8_t addressType = 0;
    std::uint8_t eventType = 0;
    std::uint8_t payloadLength = 0;
};

struct BleInspectorCaptureCounters final {
    std::uint32_t observed = 0;
    std::uint32_t accepted = 0;
    std::uint32_t differentTarget = 0;
    std::uint32_t invalid = 0;
    std::uint32_t dropped = 0;
};

// Allocation-free retention for legacy advertising payloads belonging to one
// explicitly selected identity. Exact packet bytes are copied immediately;
// caller-owned name pointers and parsed presentation facts are never retained.
class BleInspectorCapture final {
public:
    static constexpr std::size_t kRecordCapacity = 32U;

    bool begin(const BleInspectorTarget& target);
    BleInspectorCaptureDisposition ingest(
        const drivers::ble::BleAdvertisementRecord& record,
        std::uint64_t monotonicUs);
    bool freeze();
    void reset();

    BleInspectorCaptureState state() const { return state_; }
    const BleInspectorTarget& target() const { return target_; }
    const BleInspectorCaptureCounters& counters() const { return counters_; }
    std::size_t size() const { return size_; }
    const BleInspectorRawAdvertisement* at(std::size_t index) const;

private:
    BleInspectorCaptureState state_ = BleInspectorCaptureState::Idle;
    BleInspectorTarget target_{};
    BleInspectorCaptureCounters counters_{};
    std::array<BleInspectorRawAdvertisement, kRecordCapacity> records_{};
    std::size_t size_ = 0U;
    std::uint64_t latestMonotonicUs_ = 0U;
};

enum class BleGattInspectorPermission : std::uint8_t {
    None,
    EnumerateServicesAndCharacteristics,
};

enum class BleGattInspectorState : std::uint8_t {
    Idle,
    PermissionReview,
    AwaitingConfirmation,
    Connecting,
    Discovering,
    Ready,
    CleanupPending,
    Complete,
    Failed,
};

enum class BleGattInspectorFailure : std::uint8_t {
    None,
    InvalidTarget,
    PermissionDenied,
    StaleConfirmation,
    ResourceBusy,
    ConnectStartFailed,
    ConnectRefused,
    UnexpectedPeer,
    DiscoveryStartFailed,
    InvalidGattFact,
    CapacityReached,
    Timeout,
    TransportError,
    DisconnectFailed,
};

enum class BleGattDisconnectStatus : std::uint8_t {
    Disconnected,
    Pending,
    Failed,
};

// The transport surface deliberately exposes no pairing, characteristic read,
// write or subscription operation. CAP-051 connected mode can only connect,
// enumerate metadata and disconnect.
class BleGattInspectorTransport {
public:
    virtual ~BleGattInspectorTransport() = default;
    virtual bool startConnect(const BleInspectorTarget& target) = 0;
    virtual bool startServiceDiscovery() = 0;
    virtual BleGattDisconnectStatus requestDisconnect() = 0;
    virtual BleGattDisconnectStatus pollDisconnect() = 0;
};

struct BleGattUuid final {
    std::array<std::uint8_t, 16> bytes{};
    std::uint8_t widthBytes = 0;
};

struct BleGattServiceFact final {
    std::uint64_t discoveredMonotonicUs = 0;
    std::uint16_t startHandle = 0;
    std::uint16_t endHandle = 0;
    BleGattUuid uuid{};
};

struct BleGattCharacteristicFact final {
    std::uint64_t discoveredMonotonicUs = 0;
    std::uint16_t serviceStartHandle = 0;
    std::uint16_t declarationHandle = 0;
    std::uint16_t valueHandle = 0;
    std::uint8_t properties = 0;
    BleGattUuid uuid{};
};

class BleGattInspector final {
public:
    static constexpr kernel::runtime::ResourceOwner kDefaultResourceOwner = 6U;
    static constexpr std::size_t kServiceCapacity = 16U;
    static constexpr std::size_t kCharacteristicCapacity = 48U;
    static constexpr std::uint64_t kConfirmationWindowUs = 10000000ULL;
    static constexpr std::uint64_t kConnectedSessionTimeoutUs = 60000000ULL;

    BleGattInspector(
        kernel::runtime::ResourceBroker& broker,
        BleGattInspectorTransport& transport,
        kernel::runtime::ResourceOwner owner = kDefaultResourceOwner);

    bool selectTarget(const BleInspectorTarget& target,
                      std::uint64_t nowMonotonicUs);
    bool reviewPermission(BleGattInspectorPermission permission);
    std::uint64_t confirmationToken() const;
    bool confirm(std::uint64_t token, std::uint64_t nowMonotonicUs);

    bool onConnected(const std::array<std::uint8_t, 6>& address,
                     std::uint8_t addressType,
                     std::uint64_t nowMonotonicUs);
    bool onConnectionRefused(std::uint64_t nowMonotonicUs);
    bool recordService(const BleGattServiceFact& service,
                       std::uint64_t nowMonotonicUs);
    bool recordCharacteristic(const BleGattCharacteristicFact& characteristic,
                              std::uint64_t nowMonotonicUs);
    bool onDiscoveryComplete(std::uint64_t nowMonotonicUs);
    bool onTransportError(std::uint64_t nowMonotonicUs);
    bool back(std::uint64_t nowMonotonicUs);
    bool tick(std::uint64_t nowMonotonicUs);
    bool pollCleanup(std::uint64_t nowMonotonicUs);
    bool reset();

    BleGattInspectorState state() const { return state_; }
    BleGattInspectorFailure failure() const { return failure_; }
    BleGattInspectorFailure cleanupCause() const { return cleanupCause_; }
    BleGattInspectorPermission permission() const { return permission_; }
    const BleInspectorTarget& target() const { return target_; }
    std::size_t serviceCount() const { return serviceCount_; }
    std::size_t characteristicCount() const { return characteristicCount_; }
    const BleGattServiceFact* serviceAt(std::size_t index) const;
    const BleGattCharacteristicFact* characteristicAt(std::size_t index) const;
    bool cleanupComplete() const;
    bool ownsRadio() const;

private:
    bool requestCleanup(BleGattInspectorFailure failure,
                        bool terminalFailure,
                        std::uint64_t nowMonotonicUs);
    void finishCleanup(bool failed);
    bool activeConnectionState() const;
    bool validEventTime(std::uint64_t nowMonotonicUs) const;
    std::uint64_t deriveConfirmationToken() const;

    kernel::runtime::ResourceBroker& broker_;
    BleGattInspectorTransport& transport_;
    kernel::runtime::ResourceOwner owner_;
    BleGattInspectorState state_ = BleGattInspectorState::Idle;
    BleGattInspectorFailure failure_ = BleGattInspectorFailure::None;
    BleGattInspectorFailure cleanupCause_ = BleGattInspectorFailure::None;
    BleGattInspectorPermission permission_ = BleGattInspectorPermission::None;
    BleInspectorTarget target_{};
    std::array<BleGattServiceFact, kServiceCapacity> services_{};
    std::array<BleGattCharacteristicFact, kCharacteristicCapacity>
        characteristics_{};
    std::size_t serviceCount_ = 0U;
    std::size_t characteristicCount_ = 0U;
    std::uint64_t selectedAtUs_ = 0U;
    std::uint64_t deadlineUs_ = 0U;
    std::uint64_t lastEventUs_ = 0U;
    bool cleanupShouldFail_ = false;
};

const char* bleGattInspectorStateName(BleGattInspectorState state);
const char* bleGattInspectorFailureName(BleGattInspectorFailure failure);

}  // namespace leshy1::services::ble
