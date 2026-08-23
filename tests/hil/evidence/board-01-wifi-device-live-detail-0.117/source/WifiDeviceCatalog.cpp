#include "WifiDeviceCatalog.h"

#include <algorithm>
#include <cstring>

namespace leshy1::apps::wifi {
namespace {

bool usableClientAddress(const std::uint8_t* address) {
    if (address == nullptr || (address[0] & 0x01U) != 0U) return false;
    bool any = false;
    for (std::size_t index = 0; index < 6; ++index) {
        any = any || address[index] != 0U;
    }
    return any;
}

std::uint8_t stateRank(WifiDeviceState state) {
    switch (state) {
        case WifiDeviceState::Searching: return 0;
        case WifiDeviceState::Connecting: return 1;
        case WifiDeviceState::Connected: return 2;
    }
    return 0;
}

std::uint8_t generationRank(WifiDeviceGeneration generation) {
    return static_cast<std::uint8_t>(generation);
}

template <std::size_t Capacity>
void copyVisibleText(const std::uint8_t* source, std::size_t length,
                     std::array<char, Capacity>* destination,
                     std::uint8_t* copiedLength) {
    if (source == nullptr || destination == nullptr || copiedLength == nullptr ||
        Capacity < 2U) {
        return;
    }
    const std::size_t count = std::min(length, Capacity - 1U);
    for (std::size_t index = 0; index < count; ++index) {
        const std::uint8_t value = source[index];
        (*destination)[index] = value >= 0x20U && value <= 0x7eU
            ? static_cast<char>(value) : '?';
    }
    (*destination)[count] = '\0';
    *copiedLength = static_cast<std::uint8_t>(count);
}

void parseWpsAttributes(const std::uint8_t* payload, std::size_t length,
                        WifiDeviceObservation* output) {
    if (payload == nullptr || output == nullptr || length < 4U ||
        payload[0] != 0x00U || payload[1] != 0x50U ||
        payload[2] != 0xf2U || payload[3] != 0x04U) {
        return;
    }
    std::size_t offset = 4U;
    while (offset + 4U <= length) {
        const std::uint16_t kind =
            static_cast<std::uint16_t>(payload[offset] << 8U) |
            payload[offset + 1U];
        const std::size_t valueLength =
            static_cast<std::size_t>(payload[offset + 2U] << 8U) |
            payload[offset + 3U];
        offset += 4U;
        if (valueLength > length - offset) return;
        if (kind == 0x1011U && output->wpsDeviceNameLength == 0U) {
            copyVisibleText(payload + offset, valueLength,
                            &output->wpsDeviceName,
                            &output->wpsDeviceNameLength);
        } else if (kind == 0x1021U &&
                   output->wpsManufacturerLength == 0U) {
            copyVisibleText(payload + offset, valueLength,
                            &output->wpsManufacturer,
                            &output->wpsManufacturerLength);
        } else if ((kind == 0x1023U || kind == 0x1024U) &&
                   output->wpsModelLength == 0U) {
            copyVisibleText(payload + offset, valueLength,
                            &output->wpsModel, &output->wpsModelLength);
        }
        offset += valueLength;
    }
}

void parseInformationElements(const std::uint8_t* payload, std::size_t length,
                              WifiDeviceObservation* output) {
    if (payload == nullptr || output == nullptr) return;
    bool capabilitiesSeen = false;
    std::size_t offset = 0U;
    while (offset + 2U <= length) {
        const std::uint8_t kind = payload[offset];
        const std::size_t valueLength = payload[offset + 1U];
        offset += 2U;
        if (valueLength > length - offset) return;
        const std::uint8_t* value = payload + offset;
        if (kind == 0U && valueLength > 0U &&
            output->ssidLength == 0U) {
            copyVisibleText(value, valueLength, &output->ssid,
                            &output->ssidLength);
        } else if (kind == 1U || kind == 50U) {
            capabilitiesSeen = true;
            for (std::size_t rate = 0; rate < valueLength; ++rate) {
                const std::uint8_t halfMbps = value[rate] & 0x7fU;
                output->maxLegacyRateHalfMbps = std::max(
                    output->maxLegacyRateHalfMbps, halfMbps);
            }
        } else if (kind == 45U) {
            capabilitiesSeen = true;
            if (generationRank(output->generation) <
                generationRank(WifiDeviceGeneration::Wifi4)) {
                output->generation = WifiDeviceGeneration::Wifi4;
            }
        } else if (kind == 191U) {
            capabilitiesSeen = true;
            output->generation = WifiDeviceGeneration::Wifi5;
        } else if (kind == 255U && valueLength > 0U && value[0] == 35U) {
            capabilitiesSeen = true;
            output->generation = WifiDeviceGeneration::Wifi6;
        } else if (kind == 221U) {
            parseWpsAttributes(value, valueLength, output);
        }
        offset += valueLength;
    }
    if (capabilitiesSeen && output->generation ==
            WifiDeviceGeneration::Unknown) {
        output->generation = WifiDeviceGeneration::Legacy;
    }
}

template <std::size_t Capacity>
void updateKnownText(const std::array<char, Capacity>& incoming,
                     std::uint8_t incomingLength,
                     std::array<char, Capacity>* current,
                     std::uint8_t* currentLength) {
    if (incomingLength == 0U || current == nullptr || currentLength == nullptr) {
        return;
    }
    *current = incoming;
    *currentLength = incomingLength;
}

}  // namespace

const char* wifiDeviceStateName(WifiDeviceState state) {
    switch (state) {
        case WifiDeviceState::Searching: return "searching";
        case WifiDeviceState::Connecting: return "connecting";
        case WifiDeviceState::Connected: return "connected";
    }
    return "unknown";
}

const char* wifiDeviceGenerationName(WifiDeviceGeneration generation) {
    switch (generation) {
        case WifiDeviceGeneration::Legacy: return "legacy";
        case WifiDeviceGeneration::Wifi4: return "wifi4";
        case WifiDeviceGeneration::Wifi5: return "wifi5";
        case WifiDeviceGeneration::Wifi6: return "wifi6";
        case WifiDeviceGeneration::Unknown:
        default: return "unknown";
    }
}

bool decodeWifiClientFrame(const std::uint8_t* payload, std::size_t length,
                           std::int16_t rssiDbm, std::uint8_t channel,
                           std::uint64_t monotonicUs,
                           WifiDeviceObservation* output) {
    if (payload == nullptr || output == nullptr || length < 24U ||
        channel == 0U || channel > 14U || monotonicUs == 0U) {
        return false;
    }
    const std::uint16_t control = static_cast<std::uint16_t>(payload[0]) |
        (static_cast<std::uint16_t>(payload[1]) << 8U);
    const std::uint8_t type = static_cast<std::uint8_t>((control >> 2U) & 0x03U);
    const std::uint8_t subtype =
        static_cast<std::uint8_t>((control >> 4U) & 0x0fU);
    const bool toDistribution = (control & 0x0100U) != 0U;
    const bool fromDistribution = (control & 0x0200U) != 0U;

    WifiDeviceState state = WifiDeviceState::Searching;
    std::uint8_t evidence = WifiDeviceEvidenceNone;
    const std::uint8_t* bssid = nullptr;
    std::size_t informationOffset = length;
    if (type == 0U) {
        if (subtype == 4U) {
            state = WifiDeviceState::Searching;
            evidence = WifiDeviceEvidenceProbe;
            informationOffset = 24U;
        } else if (subtype == 0U || subtype == 2U) {
            state = WifiDeviceState::Connecting;
            evidence = WifiDeviceEvidenceAssociation;
            bssid = payload + 16U;
            informationOffset = subtype == 0U ? 28U : 34U;
            if (length < informationOffset) return false;
        } else {
            return false;
        }
    } else if (type == 2U && toDistribution && !fromDistribution) {
        state = WifiDeviceState::Connected;
        evidence = WifiDeviceEvidenceData;
        bssid = payload + 4U;
    } else {
        return false;
    }

    const std::uint8_t* transmitter = payload + 10U;
    if (!usableClientAddress(transmitter)) return false;
    WifiDeviceObservation decoded{};
    std::memcpy(decoded.address.data(), transmitter, decoded.address.size());
    if (bssid != nullptr && usableClientAddress(bssid)) {
        std::memcpy(decoded.bssid.data(), bssid, decoded.bssid.size());
        decoded.bssidKnown = true;
    }
    decoded.state = state;
    decoded.evidence = evidence;
    decoded.channel = channel;
    decoded.rssiDbm = rssiDbm;
    decoded.monotonicUs = monotonicUs;
    decoded.locallyAdministered = (decoded.address[0] & 0x02U) != 0U;
    if (informationOffset < length) {
        parseInformationElements(payload + informationOffset,
                                 length - informationOffset, &decoded);
    }
    *output = decoded;
    return true;
}

void WifiDeviceCatalog::reset() {
    entries_.fill(WifiDeviceRecord{});
    size_ = 0;
    ++revision_;
}

std::size_t WifiDeviceCatalog::oldestIndex() const {
    std::size_t oldest = 0;
    for (std::size_t index = 1; index < size_; ++index) {
        if (entries_[index].monotonicUs < entries_[oldest].monotonicUs) {
            oldest = index;
        }
    }
    return oldest;
}

void WifiDeviceCatalog::sortStrongestFirst() {
    // Stable insertion sort keeps the fixed-capacity catalog allocation-free.
    for (std::size_t index = 1; index < size_; ++index) {
        const auto current = entries_[index];
        std::size_t position = index;
        while (position > 0U &&
               entries_[position - 1U].rssiDbm < current.rssiDbm) {
            entries_[position] = entries_[position - 1U];
            --position;
        }
        entries_[position] = current;
    }
}

bool WifiDeviceCatalog::strongestFirst() const {
    for (std::size_t index = 1; index < size_; ++index) {
        if (entries_[index - 1U].rssiDbm < entries_[index].rssiDbm) {
            return false;
        }
    }
    return true;
}

bool WifiDeviceCatalog::upsert(const WifiDeviceObservation& observation) {
    if (!usableClientAddress(observation.address.data()) ||
        observation.channel == 0U || observation.channel > 14U ||
        observation.monotonicUs == 0U) {
        return false;
    }
    for (std::size_t index = 0; index < size_; ++index) {
        WifiDeviceRecord& current = entries_[index];
        if (std::memcmp(current.address.data(), observation.address.data(),
                        current.address.size()) != 0) {
            continue;
        }
        if (stateRank(observation.state) > stateRank(current.state)) {
            current.state = observation.state;
        }
        current.channel = observation.channel;
        current.evidence |= observation.evidence;
        current.locallyAdministered = observation.locallyAdministered;
        current.previousRssiDbm = current.rssiDbm;
        current.rssiTrendDb = static_cast<std::int16_t>(
            observation.rssiDbm - current.rssiDbm);
        current.rssiDbm = observation.rssiDbm;
        current.minimumRssiDbm = std::min(current.minimumRssiDbm,
                                          observation.rssiDbm);
        current.maximumRssiDbm = std::max(current.maximumRssiDbm,
                                          observation.rssiDbm);
        current.monotonicUs = observation.monotonicUs;
        if (observation.bssidKnown) {
            current.bssid = observation.bssid;
            current.bssidKnown = true;
        }
        updateKnownText(observation.ssid, observation.ssidLength,
                        &current.ssid, &current.ssidLength);
        updateKnownText(observation.wpsDeviceName,
                        observation.wpsDeviceNameLength,
                        &current.wpsDeviceName,
                        &current.wpsDeviceNameLength);
        updateKnownText(observation.wpsManufacturer,
                        observation.wpsManufacturerLength,
                        &current.wpsManufacturer,
                        &current.wpsManufacturerLength);
        updateKnownText(observation.wpsModel, observation.wpsModelLength,
                        &current.wpsModel, &current.wpsModelLength);
        updateKnownText(observation.ouiVendor, observation.ouiVendorLength,
                        &current.ouiVendor, &current.ouiVendorLength);
        if (generationRank(observation.generation) >
            generationRank(current.generation)) {
            current.generation = observation.generation;
        }
        current.maxLegacyRateHalfMbps = std::max(
            current.maxLegacyRateHalfMbps,
            observation.maxLegacyRateHalfMbps);
        ++current.framesSeen;
        sortStrongestFirst();
        ++revision_;
        return true;
    }

    WifiDeviceRecord record{};
    static_cast<WifiDeviceObservation&>(record) = observation;
    record.framesSeen = 1;
    record.firstSeenUs = observation.monotonicUs;
    record.previousRssiDbm = observation.rssiDbm;
    record.minimumRssiDbm = observation.rssiDbm;
    record.maximumRssiDbm = observation.rssiDbm;
    if (size_ < entries_.size()) {
        entries_[size_++] = record;
    } else {
        entries_[oldestIndex()] = record;
    }
    sortStrongestFirst();
    ++revision_;
    return true;
}

const WifiDeviceRecord* WifiDeviceCatalog::at(std::size_t index) const {
    return index < size_ ? &entries_[index] : nullptr;
}

std::size_t WifiDeviceCatalog::indexOfAddress(
    const std::array<std::uint8_t, 6>& address) const {
    for (std::size_t index = 0; index < size_; ++index) {
        if (entries_[index].address == address) return index;
    }
    return size_;
}

}  // namespace leshy1::apps::wifi
