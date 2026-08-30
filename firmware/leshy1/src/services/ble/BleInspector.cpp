#include "BleInspector.h"

#include <algorithm>
#include <limits>

namespace leshy1::services::ble {
namespace {

bool validAddress(const std::array<std::uint8_t, 6>& address) {
    bool any = false;
    bool allFf = true;
    for (const std::uint8_t byte : address) {
        any = any || byte != 0U;
        allFf = allFf && byte == 0xffU;
    }
    return any && !allFf;
}

void increment(std::uint32_t* value) {
    if (value != nullptr && *value != std::numeric_limits<std::uint32_t>::max()) {
        ++*value;
    }
}

bool sameTarget(const BleInspectorTarget& target,
                const drivers::ble::BleAdvertisementRecord& record) {
    return target.address == record.address &&
        target.addressType == record.addressType;
}

bool validUuid(const BleGattUuid& uuid) {
    if (uuid.widthBytes != 2U && uuid.widthBytes != 4U &&
        uuid.widthBytes != 16U) {
        return false;
    }
    bool any = false;
    for (std::size_t index = 0U; index < uuid.bytes.size(); ++index) {
        if (index < uuid.widthBytes) {
            any = any || uuid.bytes[index] != 0U;
        } else if (uuid.bytes[index] != 0U) {
            return false;
        }
    }
    return any;
}

}  // namespace

bool validBleInspectorTarget(const BleInspectorTarget& target) {
    return validAddress(target.address) && target.addressType <= 3U &&
        target.observedMonotonicUs != 0U;
}

bool BleInspectorCapture::begin(const BleInspectorTarget& target) {
    reset();
    if (!validBleInspectorTarget(target)) return false;
    target_ = target;
    state_ = BleInspectorCaptureState::Running;
    latestMonotonicUs_ = target.observedMonotonicUs;
    return true;
}

BleInspectorCaptureDisposition BleInspectorCapture::ingest(
    const drivers::ble::BleAdvertisementRecord& record,
    std::uint64_t monotonicUs) {
    if (state_ != BleInspectorCaptureState::Running) {
        return BleInspectorCaptureDisposition::NotRunning;
    }
    increment(&counters_.observed);
    if (!sameTarget(target_, record)) {
        increment(&counters_.differentTarget);
        return BleInspectorCaptureDisposition::DifferentTarget;
    }
    if (!validAddress(record.address) || record.addressType > 3U ||
        monotonicUs == 0U || monotonicUs < latestMonotonicUs_ ||
        record.rssiDbm < -127 || record.rssiDbm > 20 ||
        record.payloadLength > record.payload.size()) {
        increment(&counters_.invalid);
        return BleInspectorCaptureDisposition::InvalidRecord;
    }
    latestMonotonicUs_ = monotonicUs;
    if (size_ >= records_.size()) {
        increment(&counters_.dropped);
        return BleInspectorCaptureDisposition::CapacityReached;
    }
    BleInspectorRawAdvertisement& destination = records_[size_++];
    destination.address = record.address;
    destination.addressType = record.addressType;
    destination.eventType = record.eventType;
    destination.monotonicUs = monotonicUs;
    destination.rssiDbm = record.rssiDbm;
    destination.payloadLength = record.payloadLength;
    std::copy_n(record.payload.begin(), record.payloadLength,
                destination.payload.begin());
    increment(&counters_.accepted);
    return BleInspectorCaptureDisposition::Accepted;
}

bool BleInspectorCapture::freeze() {
    if (state_ != BleInspectorCaptureState::Running) return false;
    state_ = BleInspectorCaptureState::Frozen;
    return true;
}

void BleInspectorCapture::reset() {
    state_ = BleInspectorCaptureState::Idle;
    target_ = {};
    counters_ = {};
    records_ = {};
    size_ = 0U;
    latestMonotonicUs_ = 0U;
}

const BleInspectorRawAdvertisement* BleInspectorCapture::at(
    std::size_t index) const {
    return index < size_ ? &records_[index] : nullptr;
}

BleGattInspector::BleGattInspector(
    kernel::runtime::ResourceBroker& broker,
    BleGattInspectorTransport& transport,
    kernel::runtime::ResourceOwner owner)
    : broker_(broker), transport_(transport), owner_(owner) {}

bool BleGattInspector::selectTarget(const BleInspectorTarget& target,
                                    std::uint64_t nowMonotonicUs) {
    if ((state_ != BleGattInspectorState::Idle &&
         state_ != BleGattInspectorState::Complete &&
         state_ != BleGattInspectorState::Failed) ||
        ownsRadio()) {
        return false;
    }
    reset();
    if (!validBleInspectorTarget(target) || nowMonotonicUs == 0U ||
        nowMonotonicUs < target.observedMonotonicUs ||
        nowMonotonicUs - target.observedMonotonicUs >
            kConfirmationWindowUs) {
        state_ = BleGattInspectorState::Failed;
        failure_ = BleGattInspectorFailure::InvalidTarget;
        return false;
    }
    target_ = target;
    selectedAtUs_ = nowMonotonicUs;
    lastEventUs_ = nowMonotonicUs;
    state_ = BleGattInspectorState::PermissionReview;
    return true;
}

bool BleGattInspector::reviewPermission(
    BleGattInspectorPermission permission) {
    if (state_ != BleGattInspectorState::PermissionReview) return false;
    if (permission !=
        BleGattInspectorPermission::EnumerateServicesAndCharacteristics) {
        state_ = BleGattInspectorState::Failed;
        failure_ = BleGattInspectorFailure::PermissionDenied;
        return false;
    }
    permission_ = permission;
    state_ = BleGattInspectorState::AwaitingConfirmation;
    return true;
}

std::uint64_t BleGattInspector::confirmationToken() const {
    return state_ == BleGattInspectorState::AwaitingConfirmation
        ? deriveConfirmationToken() : 0U;
}

bool BleGattInspector::confirm(std::uint64_t token,
                               std::uint64_t nowMonotonicUs) {
    if (state_ != BleGattInspectorState::AwaitingConfirmation || token == 0U ||
        token != deriveConfirmationToken() || nowMonotonicUs < selectedAtUs_ ||
        nowMonotonicUs - selectedAtUs_ > kConfirmationWindowUs) {
        if (state_ == BleGattInspectorState::AwaitingConfirmation) {
            state_ = BleGattInspectorState::Failed;
            failure_ = BleGattInspectorFailure::StaleConfirmation;
        }
        return false;
    }
    if (nowMonotonicUs >
        std::numeric_limits<std::uint64_t>::max() -
            kConnectedSessionTimeoutUs) {
        state_ = BleGattInspectorState::Failed;
        failure_ = BleGattInspectorFailure::StaleConfirmation;
        return false;
    }
    const kernel::runtime::ResourceMask radio =
        kernel::runtime::resourceMask(kernel::runtime::Resource::EspRf);
    if (owner_ == kernel::runtime::kNoOwner || !broker_.acquire(owner_, radio)) {
        state_ = BleGattInspectorState::Failed;
        failure_ = BleGattInspectorFailure::ResourceBusy;
        return false;
    }
    if (!transport_.startConnect(target_)) {
        broker_.releaseAll(owner_);
        state_ = BleGattInspectorState::Failed;
        failure_ = BleGattInspectorFailure::ConnectStartFailed;
        return false;
    }
    lastEventUs_ = nowMonotonicUs;
    deadlineUs_ = nowMonotonicUs + kConnectedSessionTimeoutUs;
    state_ = BleGattInspectorState::Connecting;
    return true;
}

bool BleGattInspector::onConnected(
    const std::array<std::uint8_t, 6>& address, std::uint8_t addressType,
    std::uint64_t nowMonotonicUs) {
    if (state_ != BleGattInspectorState::Connecting ||
        !validEventTime(nowMonotonicUs)) {
        return false;
    }
    if (nowMonotonicUs >= deadlineUs_) {
        requestCleanup(BleGattInspectorFailure::Timeout, true,
                       nowMonotonicUs);
        return false;
    }
    lastEventUs_ = nowMonotonicUs;
    if (address != target_.address || addressType != target_.addressType) {
        requestCleanup(BleGattInspectorFailure::UnexpectedPeer, true,
                       nowMonotonicUs);
        return false;
    }
    if (!transport_.startServiceDiscovery()) {
        requestCleanup(BleGattInspectorFailure::DiscoveryStartFailed, true,
                       nowMonotonicUs);
        return false;
    }
    state_ = BleGattInspectorState::Discovering;
    return true;
}

bool BleGattInspector::onConnectionRefused(std::uint64_t nowMonotonicUs) {
    if (state_ != BleGattInspectorState::Connecting ||
        !validEventTime(nowMonotonicUs)) {
        return false;
    }
    return requestCleanup(BleGattInspectorFailure::ConnectRefused, true,
                          nowMonotonicUs);
}

bool BleGattInspector::recordService(const BleGattServiceFact& service,
                                     std::uint64_t nowMonotonicUs) {
    if (state_ != BleGattInspectorState::Discovering ||
        !validEventTime(nowMonotonicUs)) {
        return false;
    }
    if (nowMonotonicUs >= deadlineUs_) {
        requestCleanup(BleGattInspectorFailure::Timeout, true,
                       nowMonotonicUs);
        return false;
    }
    lastEventUs_ = nowMonotonicUs;
    if (!validUuid(service.uuid) || service.startHandle == 0U ||
        service.endHandle < service.startHandle ||
        service.discoveredMonotonicUs != 0U ||
        (serviceCount_ != 0U &&
         service.startHandle <= services_[serviceCount_ - 1U].endHandle)) {
        requestCleanup(BleGattInspectorFailure::InvalidGattFact, true,
                       nowMonotonicUs);
        return false;
    }
    if (serviceCount_ >= services_.size()) {
        requestCleanup(BleGattInspectorFailure::CapacityReached, true,
                       nowMonotonicUs);
        return false;
    }
    services_[serviceCount_] = service;
    services_[serviceCount_].discoveredMonotonicUs = nowMonotonicUs;
    ++serviceCount_;
    return true;
}

bool BleGattInspector::recordCharacteristic(
    const BleGattCharacteristicFact& characteristic,
    std::uint64_t nowMonotonicUs) {
    if (state_ != BleGattInspectorState::Discovering ||
        !validEventTime(nowMonotonicUs)) {
        return false;
    }
    if (nowMonotonicUs >= deadlineUs_) {
        requestCleanup(BleGattInspectorFailure::Timeout, true,
                       nowMonotonicUs);
        return false;
    }
    lastEventUs_ = nowMonotonicUs;
    const BleGattServiceFact* parent = nullptr;
    for (std::size_t index = 0U; index < serviceCount_; ++index) {
        if (services_[index].startHandle ==
            characteristic.serviceStartHandle) {
            parent = &services_[index];
            break;
        }
    }
    if (!validUuid(characteristic.uuid) || parent == nullptr ||
        characteristic.discoveredMonotonicUs != 0U ||
        characteristic.declarationHandle < parent->startHandle ||
        characteristic.valueHandle <= characteristic.declarationHandle ||
        characteristic.valueHandle > parent->endHandle ||
        characteristic.properties == 0U ||
        (characteristicCount_ != 0U &&
         characteristic.declarationHandle <=
             characteristics_[characteristicCount_ - 1U].declarationHandle)) {
        requestCleanup(BleGattInspectorFailure::InvalidGattFact, true,
                       nowMonotonicUs);
        return false;
    }
    if (characteristicCount_ >= characteristics_.size()) {
        requestCleanup(BleGattInspectorFailure::CapacityReached, true,
                       nowMonotonicUs);
        return false;
    }
    characteristics_[characteristicCount_] = characteristic;
    characteristics_[characteristicCount_].discoveredMonotonicUs =
        nowMonotonicUs;
    ++characteristicCount_;
    return true;
}

bool BleGattInspector::onDiscoveryComplete(std::uint64_t nowMonotonicUs) {
    if (state_ != BleGattInspectorState::Discovering ||
        !validEventTime(nowMonotonicUs)) {
        return false;
    }
    if (nowMonotonicUs >= deadlineUs_) {
        requestCleanup(BleGattInspectorFailure::Timeout, true,
                       nowMonotonicUs);
        return false;
    }
    lastEventUs_ = nowMonotonicUs;
    state_ = BleGattInspectorState::Ready;
    return true;
}

bool BleGattInspector::onTransportError(std::uint64_t nowMonotonicUs) {
    if (!activeConnectionState() || !validEventTime(nowMonotonicUs)) {
        return false;
    }
    return requestCleanup(BleGattInspectorFailure::TransportError, true,
                          nowMonotonicUs);
}

bool BleGattInspector::back(std::uint64_t nowMonotonicUs) {
    if (state_ == BleGattInspectorState::PermissionReview ||
        state_ == BleGattInspectorState::AwaitingConfirmation) {
        state_ = BleGattInspectorState::Complete;
        failure_ = BleGattInspectorFailure::None;
        permission_ = BleGattInspectorPermission::None;
        return true;
    }
    if (!activeConnectionState() || !validEventTime(nowMonotonicUs)) {
        return false;
    }
    return requestCleanup(BleGattInspectorFailure::None, false,
                          nowMonotonicUs);
}

bool BleGattInspector::tick(std::uint64_t nowMonotonicUs) {
    if (state_ == BleGattInspectorState::CleanupPending) {
        return pollCleanup(nowMonotonicUs);
    }
    if (state_ == BleGattInspectorState::PermissionReview ||
        state_ == BleGattInspectorState::AwaitingConfirmation) {
        if (nowMonotonicUs >= selectedAtUs_ &&
            nowMonotonicUs - selectedAtUs_ > kConfirmationWindowUs) {
            state_ = BleGattInspectorState::Failed;
            failure_ = BleGattInspectorFailure::StaleConfirmation;
            return true;
        }
        return false;
    }
    if (activeConnectionState() && nowMonotonicUs >= deadlineUs_) {
        return requestCleanup(BleGattInspectorFailure::Timeout, true,
                              nowMonotonicUs);
    }
    return false;
}

bool BleGattInspector::timeoutForHil(std::uint64_t nowMonotonicUs) {
    if (!activeConnectionState() || !validEventTime(nowMonotonicUs)) {
        return false;
    }
    return requestCleanup(BleGattInspectorFailure::Timeout, true,
                          nowMonotonicUs);
}

bool BleGattInspector::pollCleanup(std::uint64_t nowMonotonicUs) {
    if (state_ != BleGattInspectorState::CleanupPending ||
        nowMonotonicUs < lastEventUs_) {
        return false;
    }
    lastEventUs_ = nowMonotonicUs;
    const BleGattDisconnectStatus status = transport_.pollDisconnect();
    if (status == BleGattDisconnectStatus::Disconnected) {
        finishCleanup(cleanupShouldFail_);
        return true;
    }
    if (status == BleGattDisconnectStatus::Failed) {
        failure_ = BleGattInspectorFailure::DisconnectFailed;
        cleanupShouldFail_ = true;
    }
    return false;
}

bool BleGattInspector::reset() {
    if (!cleanupComplete()) return false;
    broker_.releaseAll(owner_);
    state_ = BleGattInspectorState::Idle;
    failure_ = BleGattInspectorFailure::None;
    cleanupCause_ = BleGattInspectorFailure::None;
    permission_ = BleGattInspectorPermission::None;
    target_ = {};
    services_ = {};
    characteristics_ = {};
    serviceCount_ = 0U;
    characteristicCount_ = 0U;
    selectedAtUs_ = 0U;
    deadlineUs_ = 0U;
    lastEventUs_ = 0U;
    cleanupShouldFail_ = false;
    return true;
}

const BleGattServiceFact* BleGattInspector::serviceAt(
    std::size_t index) const {
    return index < serviceCount_ ? &services_[index] : nullptr;
}

const BleGattCharacteristicFact* BleGattInspector::characteristicAt(
    std::size_t index) const {
    return index < characteristicCount_ ? &characteristics_[index] : nullptr;
}

bool BleGattInspector::cleanupComplete() const {
    return (state_ == BleGattInspectorState::Idle ||
            state_ == BleGattInspectorState::Complete ||
            state_ == BleGattInspectorState::Failed) &&
        !ownsRadio();
}

bool BleGattInspector::ownsRadio() const {
    return broker_.ownedBy(owner_) != 0U;
}

bool BleGattInspector::requestCleanup(BleGattInspectorFailure failure,
                                      bool terminalFailure,
                                      std::uint64_t nowMonotonicUs) {
    if (!activeConnectionState()) return false;
    failure_ = failure;
    cleanupCause_ = failure;
    cleanupShouldFail_ = terminalFailure;
    lastEventUs_ = nowMonotonicUs;
    const BleGattDisconnectStatus status = transport_.requestDisconnect();
    if (status == BleGattDisconnectStatus::Disconnected) {
        finishCleanup(terminalFailure);
        return true;
    }
    state_ = BleGattInspectorState::CleanupPending;
    if (status == BleGattDisconnectStatus::Failed) {
        failure_ = BleGattInspectorFailure::DisconnectFailed;
        cleanupShouldFail_ = true;
    }
    return status != BleGattDisconnectStatus::Failed;
}

void BleGattInspector::finishCleanup(bool failed) {
    broker_.releaseAll(owner_);
    permission_ = BleGattInspectorPermission::None;
    state_ = failed ? BleGattInspectorState::Failed
                    : BleGattInspectorState::Complete;
    cleanupShouldFail_ = false;
}

bool BleGattInspector::activeConnectionState() const {
    return state_ == BleGattInspectorState::Connecting ||
        state_ == BleGattInspectorState::Discovering ||
        state_ == BleGattInspectorState::Ready;
}

bool BleGattInspector::validEventTime(std::uint64_t nowMonotonicUs) const {
    return nowMonotonicUs != 0U && nowMonotonicUs >= lastEventUs_;
}

std::uint64_t BleGattInspector::deriveConfirmationToken() const {
    std::uint64_t hash = 1469598103934665603ULL;
    const auto mix = [&hash](std::uint8_t value) {
        hash ^= value;
        hash *= 1099511628211ULL;
    };
    for (const std::uint8_t byte : target_.address) mix(byte);
    mix(target_.addressType);
    for (unsigned shift = 0U; shift < 64U; shift += 8U) {
        mix(static_cast<std::uint8_t>(target_.observedMonotonicUs >> shift));
        mix(static_cast<std::uint8_t>(selectedAtUs_ >> shift));
    }
    mix(static_cast<std::uint8_t>(permission_));
    return hash == 0U ? 1U : hash;
}

const char* bleGattInspectorStateName(BleGattInspectorState state) {
    switch (state) {
        case BleGattInspectorState::Idle: return "idle";
        case BleGattInspectorState::PermissionReview: return "permission_review";
        case BleGattInspectorState::AwaitingConfirmation:
            return "awaiting_confirmation";
        case BleGattInspectorState::Connecting: return "connecting";
        case BleGattInspectorState::Discovering: return "discovering";
        case BleGattInspectorState::Ready: return "ready";
        case BleGattInspectorState::CleanupPending: return "cleanup_pending";
        case BleGattInspectorState::Complete: return "complete";
        case BleGattInspectorState::Failed: return "failed";
    }
    return "failed";
}

const char* bleGattInspectorFailureName(BleGattInspectorFailure failure) {
    switch (failure) {
        case BleGattInspectorFailure::None: return "none";
        case BleGattInspectorFailure::InvalidTarget: return "invalid_target";
        case BleGattInspectorFailure::PermissionDenied: return "permission_denied";
        case BleGattInspectorFailure::StaleConfirmation:
            return "stale_confirmation";
        case BleGattInspectorFailure::ResourceBusy: return "resource_busy";
        case BleGattInspectorFailure::ConnectStartFailed:
            return "connect_start_failed";
        case BleGattInspectorFailure::ConnectRefused: return "connect_refused";
        case BleGattInspectorFailure::UnexpectedPeer: return "unexpected_peer";
        case BleGattInspectorFailure::DiscoveryStartFailed:
            return "discovery_start_failed";
        case BleGattInspectorFailure::InvalidGattFact: return "invalid_gatt_fact";
        case BleGattInspectorFailure::CapacityReached: return "capacity_reached";
        case BleGattInspectorFailure::Timeout: return "timeout";
        case BleGattInspectorFailure::TransportError: return "transport_error";
        case BleGattInspectorFailure::DisconnectFailed:
            return "disconnect_failed";
    }
    return "transport_error";
}

}  // namespace leshy1::services::ble
