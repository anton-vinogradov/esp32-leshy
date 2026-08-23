#include "WifiNetworkCatalog.h"

#include <cstring>

namespace leshy1::apps::wifi {

void WifiNetworkCatalog::reset() {
    entries_.fill(domain::observations::Observation{});
    signals_.fill(WifiNetworkSignalStats{});
    size_ = 0;
    hiddenResolutions_ = 0;
    ++revision_;
}

bool WifiNetworkCatalog::sameIdentity(
    const domain::observations::Observation& left,
    const domain::observations::Observation& right) {
    return left.radio == domain::observations::RadioKind::Wifi &&
        right.radio == domain::observations::RadioKind::Wifi &&
        left.identityLength != 0 &&
        left.identityLength == right.identityLength &&
        std::memcmp(left.identity.data(), right.identity.data(),
                    left.identityLength) == 0;
}

bool WifiNetworkCatalog::visibleFieldsDiffer(
    const domain::observations::Observation& left,
    const domain::observations::Observation& right) {
    const bool factsDiffer = !domain::observations::wifiNetworkFactsEqual(
        left.wifiNetwork, right.wifiNetwork);
    return left.channel != right.channel || left.rssiDbm != right.rssiDbm ||
        left.labelLength != right.labelLength ||
        std::memcmp(left.label.data(), right.label.data(),
                    left.labelLength) != 0 || factsDiffer;
}

void WifiNetworkCatalog::sortStrongestFirst() {
    // Stable insertion sort keeps the fixed-capacity catalog allocation-free.
    for (std::size_t index = 1; index < size_; ++index) {
        const auto current = entries_[index];
        const auto currentSignal = signals_[index];
        std::size_t position = index;
        while (position > 0U &&
               entries_[position - 1U].rssiDbm < current.rssiDbm) {
            entries_[position] = entries_[position - 1U];
            signals_[position] = signals_[position - 1U];
            --position;
        }
        entries_[position] = current;
        signals_[position] = currentSignal;
    }
}

bool WifiNetworkCatalog::strongestFirst() const {
    for (std::size_t index = 1; index < size_; ++index) {
        if (entries_[index - 1U].rssiDbm < entries_[index].rssiDbm) {
            return false;
        }
    }
    return true;
}

bool WifiNetworkCatalog::upsert(
    const domain::observations::Observation& observation,
    bool allowReplacement) {
    if (observation.radio != domain::observations::RadioKind::Wifi ||
        observation.identityLength == 0 ||
        observation.identityLength > observation.identity.size()) {
        return false;
    }
    for (std::size_t index = 0; index < size_; ++index) {
        if (!sameIdentity(entries_[index], observation)) continue;
        auto merged = observation;
        // A hidden beacon is incomplete information, not a new name.  Once a
        // beacon or probe response reveals the SSID for this BSSID, later
        // zero-length SSIDs must never erase it again.
        const bool resolvedHidden = entries_[index].labelLength == 0U &&
            observation.labelLength != 0U;
        if (observation.labelLength == 0U &&
            entries_[index].labelLength != 0U) {
            merged.label = entries_[index].label;
            merged.labelLength = entries_[index].labelLength;
        }
        if (!observation.wifiNetwork.present &&
            entries_[index].wifiNetwork.present) {
            merged.wifiNetwork = entries_[index].wifiNetwork;
        }
        auto signal = signals_[index];
        if (signal.samples == 0U) {
            signal.samples = 1U;
            signal.minimumRssiDbm = observation.rssiDbm;
            signal.maximumRssiDbm = observation.rssiDbm;
        } else {
            if (signal.samples != 0xffffU) ++signal.samples;
            signal.rssiTrendDb = static_cast<std::int16_t>(
                observation.rssiDbm - entries_[index].rssiDbm);
            if (observation.rssiDbm < signal.minimumRssiDbm) {
                signal.minimumRssiDbm = observation.rssiDbm;
            }
            if (observation.rssiDbm > signal.maximumRssiDbm) {
                signal.maximumRssiDbm = observation.rssiDbm;
            }
        }
        const bool changed = visibleFieldsDiffer(entries_[index], merged) ||
            signal.minimumRssiDbm != signals_[index].minimumRssiDbm ||
            signal.maximumRssiDbm != signals_[index].maximumRssiDbm ||
            signal.rssiTrendDb != signals_[index].rssiTrendDb;
        entries_[index] = merged;
        signals_[index] = signal;
        if (resolvedHidden) ++hiddenResolutions_;
        if (changed) {
            sortStrongestFirst();
            ++revision_;
        }
        return changed;
    }
    if (size_ < entries_.size()) {
        entries_[size_] = observation;
        signals_[size_] = {1U, observation.rssiDbm, observation.rssiDbm, 0};
        ++size_;
        sortStrongestFirst();
        ++revision_;
        return true;
    }
    if (!allowReplacement ||
        observation.rssiDbm <= entries_[size_ - 1U].rssiDbm) return false;
    entries_[size_ - 1U] = observation;
    signals_[size_ - 1U] = {
        1U, observation.rssiDbm, observation.rssiDbm, 0};
    sortStrongestFirst();
    ++revision_;
    return true;
}

const domain::observations::Observation* WifiNetworkCatalog::at(
    std::size_t index) const {
    return index < size_ ? &entries_[index] : nullptr;
}

const WifiNetworkSignalStats* WifiNetworkCatalog::signalAt(
    std::size_t index) const {
    return index < size_ ? &signals_[index] : nullptr;
}

std::size_t WifiNetworkCatalog::indexOfIdentity(
    const domain::observations::Observation& observation) const {
    for (std::size_t index = 0; index < size_; ++index) {
        if (sameIdentity(entries_[index], observation)) return index;
    }
    return size_;
}

}  // namespace leshy1::apps::wifi
