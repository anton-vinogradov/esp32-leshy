#include "WifiPassiveContract.h"

#include <algorithm>
#include <cstring>

namespace leshy1::drivers::wifi {

WifiScanPlan defaultPassivePlan() {
    return {};
}

bool validatePassivePlan(const WifiScanPlan& plan) {
    const bool directed = plan.directedSsid != nullptr && plan.directedSsid[0] != '\0';
    return plan.passive && !kActiveProbeAllowed && !directed && plan.channel <= 14 &&
           plan.maxMsPerChannel >= kMinimumDwellMs &&
           plan.maxMsPerChannel <= kMaximumDwellMs;
}

std::uint32_t channelFrequencyKhz(std::uint8_t channel) {
    if (channel >= 1 && channel <= 13) {
        return 2407000U + static_cast<std::uint32_t>(channel) * 5000U;
    }
    return channel == 14 ? 2484000U : 0U;
}

bool normalizePassiveRecord(const WifiScanRecord& record, std::uint64_t monotonicUs,
                            domain::observations::Observation* output) {
    if (output == nullptr || monotonicUs == 0 || channelFrequencyKhz(record.channel) == 0 ||
        record.rssiDbm < -127 || record.rssiDbm > 0 ||
        record.ssidLength > domain::observations::Observation::kLabelCapacity ||
        (record.ssidLength > 0 && record.ssid == nullptr)) {
        return false;
    }
    const bool emptyBssid =
        std::all_of(record.bssid.begin(), record.bssid.end(), [](std::uint8_t value) {
            return value == 0;
        });
    if (emptyBssid) return false;

    domain::observations::Observation normalized;
    normalized.monotonicUs = monotonicUs;
    normalized.radio = domain::observations::RadioKind::Wifi;
    normalized.frequencyKhz = channelFrequencyKhz(record.channel);
    normalized.channel = record.channel;
    normalized.rssiDbm = record.rssiDbm;
    normalized.identity = record.bssid;
    normalized.identityLength = static_cast<std::uint8_t>(record.bssid.size());
    normalized.labelLength = static_cast<std::uint8_t>(record.ssidLength);
    if (record.ssidLength > 0) {
        std::memcpy(normalized.label.data(), record.ssid, record.ssidLength);
    }
    normalized.label[record.ssidLength] = '\0';
    *output = normalized;
    return true;
}

}  // namespace leshy1::drivers::wifi
