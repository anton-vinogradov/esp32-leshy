#include "WifiDeviceCatalog.h"

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

}  // namespace

const char* wifiDeviceStateName(WifiDeviceState state) {
    switch (state) {
        case WifiDeviceState::Searching: return "searching";
        case WifiDeviceState::Connecting: return "connecting";
        case WifiDeviceState::Connected: return "connected";
    }
    return "unknown";
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
    const std::uint8_t* bssid = nullptr;
    if (type == 0U) {
        if (subtype == 4U) {
            state = WifiDeviceState::Searching;
        } else if (subtype == 0U || subtype == 2U) {
            state = WifiDeviceState::Connecting;
            bssid = payload + 16U;
        } else {
            return false;
        }
    } else if (type == 2U && toDistribution && !fromDistribution) {
        state = WifiDeviceState::Connected;
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
    decoded.channel = channel;
    decoded.rssiDbm = rssiDbm;
    decoded.monotonicUs = monotonicUs;
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
        current.rssiDbm = observation.rssiDbm;
        current.monotonicUs = observation.monotonicUs;
        if (observation.bssidKnown) {
            current.bssid = observation.bssid;
            current.bssidKnown = true;
        }
        ++current.framesSeen;
        sortStrongestFirst();
        ++revision_;
        return true;
    }

    WifiDeviceRecord record{};
    static_cast<WifiDeviceObservation&>(record) = observation;
    record.framesSeen = 1;
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
