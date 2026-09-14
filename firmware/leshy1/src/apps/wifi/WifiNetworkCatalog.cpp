#include "WifiNetworkCatalog.h"

#include <algorithm>
#include <cstring>

namespace leshy1::apps::wifi {

void WifiNetworkCatalog::reset() {
    entries_.fill(domain::observations::Observation{});
    signals_.fill(WifiNetworkSignalStats{});
    names_.fill(WifiNetworkNameFacts{});
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
        const auto currentName = names_[index];
        std::size_t position = index;
        while (position > 0U &&
               entries_[position - 1U].rssiDbm < current.rssiDbm) {
            entries_[position] = entries_[position - 1U];
            signals_[position] = signals_[position - 1U];
            names_[position] = names_[position - 1U];
            --position;
        }
        entries_[position] = current;
        signals_[position] = currentSignal;
        names_[position] = currentName;
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
        bool nameChanged = false;
        if (observation.identityLength == 6U && observation.labelLength != 0U &&
            observation.labelLength <= 32U && observation.channel <= 13U) {
            WifiNetworkNameEvidence name{};
            std::copy_n(observation.identity.begin(), 6U, name.bssid.begin());
            std::memcpy(name.name.data(), observation.label.data(), observation.labelLength);
            name.length = observation.labelLength;
            name.channel = static_cast<std::uint8_t>(observation.channel);
            name.observedUs = observation.monotonicUs;
            name.source = WifiNameSource::AccessPoint;
            nameChanged = learnName(name);
        }
        if (entries_[index].labelLength != 0U) {
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
        const bool changed = nameChanged || visibleFieldsDiffer(entries_[index], merged) ||
            signal.minimumRssiDbm != signals_[index].minimumRssiDbm ||
            signal.maximumRssiDbm != signals_[index].maximumRssiDbm ||
            signal.rssiTrendDb != signals_[index].rssiTrendDb;
        entries_[index] = merged;
        signals_[index] = signal;
        if (changed) {
            sortStrongestFirst();
            ++revision_;
        }
        return changed;
    }
    if (size_ < entries_.size()) {
        entries_[size_] = observation;
        signals_[size_] = {1U, observation.rssiDbm, observation.rssiDbm, 0};
        names_[size_] = {observation.labelLength ? observation.monotonicUs : 0U,
            observation.labelLength ? WifiNameSource::AccessPoint : WifiNameSource::None,
            observation.labelLength != 0U, false};
        ++size_;
        sortStrongestFirst();
        ++revision_;
        return true;
    }
    if (!allowReplacement ||
        observation.rssiDbm <= entries_[size_ - 1U].rssiDbm) return false;
    entries_[size_ - 1U] = observation;
    names_[size_ - 1U] = {observation.labelLength ? observation.monotonicUs : 0U,
        observation.labelLength ? WifiNameSource::AccessPoint : WifiNameSource::None,
        observation.labelLength != 0U, false};
    signals_[size_ - 1U] = {
        1U, observation.rssiDbm, observation.rssiDbm, 0};
    sortStrongestFirst();
    ++revision_;
    return true;
}

bool WifiNetworkCatalog::learnNames(const WifiNetworkNameTracker& tracker) {
    std::array<WifiNetworkNameEvidence, 4> evidence{
        tracker.primary(), tracker.conflict(), tracker.primary(), tracker.primary()};
    evidence[2].source = WifiNameSource::AccessPoint;
    evidence[2].observedUs = tracker.apConfirmationUs();
    evidence[3].observedUs = tracker.primaryLastSeenUs();
    // Replay a snapshot in time order: a later repeat must not hide an earlier
    // conflict or confirmation when several packets arrive between UI ticks.
    for (std::size_t i = 1; i < evidence.size(); ++i) {
        const auto item = evidence[i];
        std::size_t j = i;
        while (j > 0 && evidence[j - 1U].observedUs > item.observedUs) {
            evidence[j] = evidence[j - 1U]; --j;
        }
        evidence[j] = item;
    }
    bool changed = false;
    for (const auto& item : evidence) changed = learnName(item) || changed;
    return changed;
}

bool WifiNetworkCatalog::learnName(const WifiNetworkNameEvidence& evidence) {
    if (evidence.length == 0U || evidence.length > 32U || evidence.observedUs == 0U ||
        evidence.channel == 0U || evidence.channel > 13U ||
        !wifiNameUnicast(evidence.bssid.data()) ||
        (evidence.source != WifiNameSource::AccessPoint &&
         evidence.source != WifiNameSource::ClientConnection)) return false;
    std::uint8_t nonzero = 0;
    for (std::uint8_t i = 0; i < evidence.length; ++i) nonzero |= evidence.name[i];
    if (nonzero == 0U) return false;
    for (std::size_t i = 0; i < size_; ++i) {
        auto& entry = entries_[i];
        auto& facts = names_[i];
        if (entry.identityLength != 6U || entry.channel != evidence.channel ||
            std::memcmp(entry.identity.data(), evidence.bssid.data(), 6U) != 0 ||
            evidence.observedUs < facts.observedUs) continue;
        if (entry.labelLength != 0U && (entry.labelLength != evidence.length ||
            std::memcmp(entry.label.data(), evidence.name.data(), evidence.length) != 0)) {
            if (facts.conflict) return false;
            facts.conflict = true; ++revision_; return true;
        }
        bool changed = entry.labelLength == 0U;
        if (changed) {
            entry.label.fill(0);
            std::memcpy(entry.label.data(), evidence.name.data(), evidence.length);
            entry.labelLength = evidence.length;
            facts.source = evidence.source;
            ++hiddenResolutions_;
        }
        if (!facts.apConfirmed && evidence.source == WifiNameSource::AccessPoint) {
            facts.apConfirmed = true; changed = true;
        }
        facts.observedUs = evidence.observedUs;
        if (changed) ++revision_;
        return changed;
    }
    return false;
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
