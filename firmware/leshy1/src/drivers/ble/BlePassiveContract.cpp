#include "BlePassiveContract.h"

#include <algorithm>

namespace leshy1::drivers::ble {

bool validatePassivePlan(const BleScanPlan& plan) {
    return plan.passive && plan.durationMs >= 1000U &&
           plan.durationMs <= 10000U && plan.durationMs % 1000U == 0U &&
           plan.intervalMs >= 10U && plan.intervalMs <= 10240U &&
           plan.windowMs >= 10U && plan.windowMs <= plan.intervalMs &&
           plan.maximumRecords > 0U &&
           plan.maximumRecords <= (plan.deduplicateAddresses
               ? kMaximumDeduplicatedRecords
               : kMaximumStreamingRecords);
}

bool normalizePassiveRecord(
    const BleAdvertisementRecord& record, std::uint64_t monotonicUs,
    domain::observations::Observation* observation) {
    if (observation == nullptr || monotonicUs == 0 ||
        record.rssiDbm < -127 || record.rssiDbm > 20 ||
        record.nameLength > domain::observations::Observation::kLabelCapacity ||
        (record.nameLength != 0 && record.name == nullptr)) {
        return false;
    }
    bool anyAddressByte = false;
    bool everyAddressByteIsFf = true;
    for (const std::uint8_t byte : record.address) {
        anyAddressByte = anyAddressByte || byte != 0;
        everyAddressByteIsFf = everyAddressByteIsFf && byte == 0xff;
    }
    if (!anyAddressByte || everyAddressByteIsFf) return false;

    *observation = {};
    observation->monotonicUs = monotonicUs;
    observation->radio = domain::observations::RadioKind::Ble;
    // Legacy advertising may hop over channels 37/38/39. The high-level stack
    // does not expose the received channel, so zero means unknown rather than a
    // fabricated frequency.
    observation->frequencyKhz = 0;
    observation->channel = 0;
    observation->rssiDbm = record.rssiDbm;
    observation->identity = record.address;
    observation->identityLength = observation->identity.size();
    observation->labelLength = static_cast<std::uint8_t>(record.nameLength);
    if (record.nameLength != 0) {
        std::copy_n(record.name, record.nameLength, observation->label.begin());
    }
    observation->label[record.nameLength] = '\0';
    observation->bleAdvertisement = record.advertisement;
    observation->bleAdvertisement.present = true;
    observation->bleAdvertisement.addressType = record.addressType;
    return true;
}

}  // namespace leshy1::drivers::ble
