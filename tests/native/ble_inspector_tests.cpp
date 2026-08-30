#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <type_traits>

#include "services/ble/BleInspector.h"
#include "services/ble/BleInspectorExport.h"

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__,      \
                         __LINE__, #condition);                                 \
            std::abort();                                                       \
        }                                                                       \
    } while (false)

namespace {

using namespace leshy1::services::ble;

BleInspectorTarget targetFixture() {
    BleInspectorTarget target{};
    target.address = {0x90U, 0x70U, 0x69U, 0x0dU, 0x15U, 0xe0U};
    target.addressType = 1U;
    target.observedMonotonicUs = 1000000ULL;
    return target;
}

leshy1::drivers::ble::BleAdvertisementRecord advertisementFixture() {
    leshy1::drivers::ble::BleAdvertisementRecord record{};
    const BleInspectorTarget target = targetFixture();
    record.address = target.address;
    record.addressType = target.addressType;
    record.eventType = 3U;
    record.rssiDbm = -51;
    record.payloadLength = 5U;
    record.payload[0] = 4U;
    record.payload[1] = 0xffU;
    record.payload[2] = 0x4cU;
    record.payload[3] = 0x00U;
    record.payload[4] = 0x12U;
    record.name = "temporary";
    record.nameLength = 9U;
    return record;
}

BleGattUuid uuid16(std::uint16_t value) {
    BleGattUuid uuid{};
    uuid.widthBytes = 2U;
    uuid.bytes[0] = static_cast<std::uint8_t>(value & 0xffU);
    uuid.bytes[1] = static_cast<std::uint8_t>(value >> 8U);
    return uuid;
}

class FakeTransport final : public BleGattInspectorTransport {
public:
    bool startConnect(const BleInspectorTarget& target) override {
        ++connectCalls;
        connectedTarget = target;
        return connectStarts;
    }

    bool startServiceDiscovery() override {
        ++discoveryCalls;
        return discoveryStarts;
    }

    BleGattDisconnectStatus requestDisconnect() override {
        ++disconnectCalls;
        return disconnectStatus;
    }

    BleGattDisconnectStatus pollDisconnect() override {
        ++pollCalls;
        return pollStatus;
    }

    BleInspectorTarget connectedTarget{};
    BleGattDisconnectStatus disconnectStatus =
        BleGattDisconnectStatus::Disconnected;
    BleGattDisconnectStatus pollStatus = BleGattDisconnectStatus::Disconnected;
    std::size_t connectCalls = 0U;
    std::size_t discoveryCalls = 0U;
    std::size_t disconnectCalls = 0U;
    std::size_t pollCalls = 0U;
    bool connectStarts = true;
    bool discoveryStarts = true;
};

void advanceToConnecting(BleGattInspector* inspector,
                         std::uint64_t confirmAtUs = 1100000ULL) {
    CHECK(inspector != nullptr);
    CHECK(inspector->selectTarget(targetFixture(), 1050000ULL));
    CHECK(inspector->state() == BleGattInspectorState::PermissionReview);
    CHECK(inspector->reviewPermission(
        BleGattInspectorPermission::EnumerateServicesAndCharacteristics));
    const std::uint64_t token = inspector->confirmationToken();
    CHECK(token != 0U);
    CHECK(inspector->confirm(token, confirmAtUs));
    CHECK(inspector->state() == BleGattInspectorState::Connecting);
}

void testRawCaptureCopiesOnlyExactSelectedPackets() {
    BleInspectorCapture capture;
    CHECK(capture.begin(targetFixture()));
    auto record = advertisementFixture();
    CHECK(capture.ingest(record, 1100000ULL) ==
          BleInspectorCaptureDisposition::Accepted);
    record.payload[4] = 0xffU;
    record.name = "changed";
    const BleInspectorRawAdvertisement* retained = capture.at(0U);
    CHECK(retained != nullptr);
    CHECK(retained->payloadLength == 5U);
    CHECK(retained->payload[4] == 0x12U);
    CHECK(retained->eventType == 3U);
    CHECK(retained->rssiDbm == -51);

    record.address[5] ^= 1U;
    CHECK(capture.ingest(record, 1200000ULL) ==
          BleInspectorCaptureDisposition::DifferentTarget);
    CHECK(capture.counters().observed == 2U);
    CHECK(capture.counters().accepted == 1U);
    CHECK(capture.counters().differentTarget == 1U);
    CHECK(capture.freeze());
    CHECK(capture.ingest(record, 1300000ULL) ==
          BleInspectorCaptureDisposition::NotRunning);
}

void testRawCaptureRejectsMalformedAndReportsCapacityLoss() {
    BleInspectorCapture capture;
    CHECK(capture.begin(targetFixture()));
    auto record = advertisementFixture();
    record.payloadLength = 32U;
    CHECK(capture.ingest(record, 1100000ULL) ==
          BleInspectorCaptureDisposition::InvalidRecord);
    record.payloadLength = 1U;
    for (std::size_t index = 0U;
         index < BleInspectorCapture::kRecordCapacity; ++index) {
        CHECK(capture.ingest(record, 1200000ULL + index) ==
              BleInspectorCaptureDisposition::Accepted);
    }
    CHECK(capture.ingest(record, 1300000ULL) ==
          BleInspectorCaptureDisposition::CapacityReached);
    CHECK(capture.size() == BleInspectorCapture::kRecordCapacity);
    CHECK(capture.counters().invalid == 1U);
    CHECK(capture.counters().dropped == 1U);
    CHECK(capture.at(BleInspectorCapture::kRecordCapacity) == nullptr);
}

void testFrozenRawCaptureHasVersionedExactExport() {
    BleInspectorCapture capture;
    CHECK(capture.begin(targetFixture()));
    auto record = advertisementFixture();
    CHECK(capture.ingest(record, 1100000ULL) ==
          BleInspectorCaptureDisposition::Accepted);
    char line[512] = {};
    std::size_t size = 0U;
    CHECK(formatBleInspectorExportHeader(capture, line, sizeof(line), &size) ==
          BleInspectorExportStatus::NotFrozen);
    CHECK(capture.freeze());
    CHECK(formatBleInspectorExportHeader(capture, line, sizeof(line), &size) ==
          BleInspectorExportStatus::Formatted);
    CHECK(size == std::strlen(line));
    CHECK(std::strstr(line, "leshy.ble.inspector.capture.v1") != nullptr);
    CHECK(std::strstr(line, "\"complete\":false") != nullptr);
    CHECK(std::strstr(line, "90:70:69:0D:15:E0") != nullptr);
    CHECK(std::strstr(line, "\"records\":1") != nullptr);
    CHECK(formatBleInspectorExportRecord(
              capture, 0U, line, sizeof(line), &size) ==
          BleInspectorExportStatus::Formatted);
    CHECK(std::strstr(line, "\"payload_hex\":\"04FF4C0012\"") != nullptr);
    CHECK(std::strstr(line, "\"event_type\":3") != nullptr);
    CHECK(std::strstr(line, "\"rssi_dbm\":-51") != nullptr);
    CHECK(formatBleInspectorExportRecord(
              capture, 1U, line, sizeof(line), &size) ==
          BleInspectorExportStatus::InvalidArgument);
    CHECK(formatBleInspectorExportEnd(capture, line, sizeof(line), &size) ==
          BleInspectorExportStatus::Formatted);
    CHECK(std::strstr(line, "\"kind\":\"end\"") != nullptr);
    CHECK(std::strstr(line, "\"complete\":true") != nullptr);
    CHECK(formatBleInspectorExportHeader(capture, line, 8U, &size) ==
          BleInspectorExportStatus::BufferTooSmall);
}

void testGattRequiresFreshExactPermissionConfirmationAndSeparateLease() {
    leshy1::kernel::runtime::ResourceBroker broker;
    FakeTransport transport;
    BleGattInspector inspector(broker, transport);
    CHECK(!inspector.confirm(1U, 1000000ULL));
    CHECK(inspector.selectTarget(targetFixture(), 1050000ULL));
    CHECK(!inspector.ownsRadio());
    CHECK(!inspector.reviewPermission(BleGattInspectorPermission::None));
    CHECK(inspector.failure() == BleGattInspectorFailure::PermissionDenied);
    CHECK(inspector.reset());

    advanceToConnecting(&inspector);
    CHECK(inspector.ownsRadio());
    CHECK(broker.ownerOf(leshy1::kernel::runtime::Resource::EspRf) ==
          BleGattInspector::kDefaultResourceOwner);
    CHECK(transport.connectCalls == 1U);
    CHECK(transport.connectedTarget.address == targetFixture().address);
    CHECK(transport.discoveryCalls == 0U);
}

void testGattHappyPathPreservesMetadataAndBackCleansPendingConnection() {
    leshy1::kernel::runtime::ResourceBroker broker;
    FakeTransport transport;
    BleGattInspector inspector(broker, transport);
    advanceToConnecting(&inspector);
    const BleInspectorTarget target = targetFixture();
    CHECK(inspector.onConnected(target.address, target.addressType,
                                1200000ULL));
    CHECK(inspector.state() == BleGattInspectorState::Discovering);
    CHECK(transport.discoveryCalls == 1U);

    BleGattServiceFact service{};
    service.uuid = uuid16(0x180fU);
    service.startHandle = 1U;
    service.endHandle = 5U;
    CHECK(inspector.recordService(service, 1300000ULL));
    BleGattCharacteristicFact characteristic{};
    characteristic.uuid = uuid16(0x2a19U);
    characteristic.serviceStartHandle = 1U;
    characteristic.declarationHandle = 2U;
    characteristic.valueHandle = 3U;
    characteristic.properties = 0x02U;
    CHECK(inspector.recordCharacteristic(characteristic, 1400000ULL));
    CHECK(inspector.onDiscoveryComplete(1500000ULL));
    CHECK(inspector.state() == BleGattInspectorState::Ready);
    CHECK(inspector.serviceCount() == 1U);
    CHECK(inspector.characteristicCount() == 1U);
    CHECK(inspector.serviceAt(0U)->uuid.bytes[0] == 0x0fU);
    CHECK(inspector.serviceAt(0U)->discoveredMonotonicUs == 1300000ULL);
    CHECK(inspector.characteristicAt(0U)->uuid.bytes[0] == 0x19U);
    CHECK(inspector.characteristicAt(0U)->discoveredMonotonicUs ==
          1400000ULL);

    transport.disconnectStatus = BleGattDisconnectStatus::Pending;
    CHECK(inspector.back(1600000ULL));
    CHECK(inspector.state() == BleGattInspectorState::CleanupPending);
    CHECK(inspector.ownsRadio());
    transport.pollStatus = BleGattDisconnectStatus::Disconnected;
    CHECK(inspector.pollCleanup(1700000ULL));
    CHECK(inspector.state() == BleGattInspectorState::Complete);
    CHECK(inspector.cleanupComplete());
    CHECK(!inspector.ownsRadio());
}

void testGattNeverFallsBackToUnexpectedIdentity() {
    leshy1::kernel::runtime::ResourceBroker broker;
    FakeTransport transport;
    BleGattInspector inspector(broker, transport);
    advanceToConnecting(&inspector);
    auto other = targetFixture().address;
    other[5] ^= 1U;
    CHECK(!inspector.onConnected(other, targetFixture().addressType,
                                 1200000ULL));
    CHECK(inspector.state() == BleGattInspectorState::Failed);
    CHECK(inspector.failure() == BleGattInspectorFailure::UnexpectedPeer);
    CHECK(transport.connectCalls == 1U);
    CHECK(transport.discoveryCalls == 0U);
    CHECK(transport.disconnectCalls == 1U);
    CHECK(!inspector.ownsRadio());
}

void testGattTimeoutDisconnectFailureRemainsFailClosed() {
    leshy1::kernel::runtime::ResourceBroker broker;
    FakeTransport transport;
    BleGattInspector inspector(broker, transport);
    advanceToConnecting(&inspector);
    transport.disconnectStatus = BleGattDisconnectStatus::Failed;
    CHECK(!inspector.tick(1100000ULL +
                          BleGattInspector::kConnectedSessionTimeoutUs));
    CHECK(inspector.state() == BleGattInspectorState::CleanupPending);
    CHECK(inspector.failure() == BleGattInspectorFailure::DisconnectFailed);
    CHECK(inspector.cleanupCause() == BleGattInspectorFailure::Timeout);
    CHECK(inspector.ownsRadio());
    CHECK(!inspector.cleanupComplete());
    CHECK(!inspector.reset());
    transport.pollStatus = BleGattDisconnectStatus::Disconnected;
    CHECK(inspector.pollCleanup(1100001ULL +
                                BleGattInspector::kConnectedSessionTimeoutUs));
    CHECK(inspector.state() == BleGattInspectorState::Failed);
    CHECK(!inspector.ownsRadio());
}

void testGattResourceConflictAndStaleConfirmationFailClosed() {
    leshy1::kernel::runtime::ResourceBroker broker;
    FakeTransport transport;
    BleGattInspector inspector(broker, transport);
    CHECK(broker.acquire(
        9U, leshy1::kernel::runtime::resourceMask(
                leshy1::kernel::runtime::Resource::EspRf)));
    CHECK(inspector.selectTarget(targetFixture(), 1050000ULL));
    CHECK(inspector.reviewPermission(
        BleGattInspectorPermission::EnumerateServicesAndCharacteristics));
    CHECK(!inspector.confirm(inspector.confirmationToken(), 1100000ULL));
    CHECK(inspector.failure() == BleGattInspectorFailure::ResourceBusy);
    CHECK(transport.connectCalls == 0U);
    broker.releaseAll(9U);
    CHECK(inspector.reset());

    CHECK(inspector.selectTarget(targetFixture(), 1050000ULL));
    CHECK(inspector.reviewPermission(
        BleGattInspectorPermission::EnumerateServicesAndCharacteristics));
    CHECK(!inspector.confirm(
        inspector.confirmationToken(),
        1050001ULL + BleGattInspector::kConfirmationWindowUs));
    CHECK(inspector.failure() == BleGattInspectorFailure::StaleConfirmation);
    CHECK(!inspector.ownsRadio());
}

static_assert(std::is_trivially_copyable_v<BleInspectorRawAdvertisement>);
static_assert(sizeof(BleInspectorCapture) <= 2048U);
static_assert(sizeof(BleGattInspector) <= 3072U);

}  // namespace

int main() {
    testRawCaptureCopiesOnlyExactSelectedPackets();
    testRawCaptureRejectsMalformedAndReportsCapacityLoss();
    testFrozenRawCaptureHasVersionedExactExport();
    testGattRequiresFreshExactPermissionConfirmationAndSeparateLease();
    testGattHappyPathPreservesMetadataAndBackCleansPendingConnection();
    testGattNeverFallsBackToUnexpectedIdentity();
    testGattTimeoutDisconnectFailureRemainsFailClosed();
    testGattResourceConflictAndStaleConfirmationFailClosed();
    std::puts("BLE Inspector tests passed");
    return 0;
}
