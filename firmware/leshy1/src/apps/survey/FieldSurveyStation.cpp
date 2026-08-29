#include "apps/survey/FieldSurveyStation.h"

#include <algorithm>
#include <cstring>

#include "drivers/wifi/WifiPassiveContract.h"

namespace leshy1::apps::survey {
namespace {

template <std::size_t Capacity>
void copyPreferredLabel(const std::array<char, Capacity>& source,
                        std::uint8_t sourceLength,
                        domain::observations::Observation* output) {
    if (output == nullptr || sourceLength == 0U ||
        output->labelLength != 0U) {
        return;
    }
    const std::size_t length = std::min<std::size_t>(
        sourceLength, domain::observations::Observation::kLabelCapacity);
    std::memcpy(output->label.data(), source.data(), length);
    output->label[length] = '\0';
    output->labelLength = static_cast<std::uint8_t>(length);
}

}  // namespace

bool normalizeFieldSurveyStation(
    const apps::wifi::WifiDeviceObservation& station,
    domain::observations::Observation* output) {
    if (output == nullptr || station.monotonicUs == 0U ||
        station.channel == 0U || station.channel > 14U ||
        station.rssiDbm < -127 || station.rssiDbm > 0 ||
        station.evidence == apps::wifi::WifiDeviceEvidenceNone) {
        return false;
    }
    const std::uint32_t frequencyKhz =
        drivers::wifi::channelFrequencyKhz(station.channel);
    if (frequencyKhz == 0U) return false;

    domain::observations::Observation normalized{};
    normalized.monotonicUs = station.monotonicUs;
    normalized.radio = domain::observations::RadioKind::Wifi;
    normalized.wifiKind =
        domain::observations::WifiObservationKind::Station;
    normalized.frequencyKhz = frequencyKhz;
    normalized.channel = station.channel;
    normalized.rssiDbm = station.rssiDbm;
    normalized.identity = station.address;
    normalized.identityLength = static_cast<std::uint8_t>(
        normalized.identity.size());

    // Prefer user-facing identity over manufacturer hints. The native export
    // always retains the exact station address separately.
    copyPreferredLabel(station.wpsDeviceName, station.wpsDeviceNameLength,
                       &normalized);
    copyPreferredLabel(station.ssid, station.ssidLength, &normalized);
    copyPreferredLabel(station.wpsModel, station.wpsModelLength, &normalized);
    copyPreferredLabel(station.wpsManufacturer,
                       station.wpsManufacturerLength, &normalized);
    copyPreferredLabel(station.ouiVendor, station.ouiVendorLength,
                       &normalized);
    *output = normalized;
    return true;
}

bool fieldSurveyStationSweepCovered(std::uint32_t channelHops,
                                    std::uint8_t channelCount,
                                    std::uint8_t sweepCount) {
    if (channelCount == 0U || sweepCount == 0U) return false;
    const std::uint32_t requiredDwells =
        static_cast<std::uint32_t>(channelCount) * sweepCount;
    return channelHops >= requiredDwells - 1U;
}

}  // namespace leshy1::apps::survey
