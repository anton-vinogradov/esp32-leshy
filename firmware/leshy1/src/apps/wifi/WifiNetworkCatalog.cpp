#include "WifiNetworkCatalog.h"

#include <cstring>

namespace leshy1::apps::wifi {

void WifiNetworkCatalog::reset() {
    entries_.fill(domain::observations::Observation{});
    size_ = 0;
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
    return left.channel != right.channel || left.rssiDbm != right.rssiDbm ||
        left.labelLength != right.labelLength ||
        std::memcmp(left.label.data(), right.label.data(),
                    left.labelLength) != 0;
}

std::size_t WifiNetworkCatalog::weakestIndex() const {
    std::size_t weakest = 0;
    for (std::size_t index = 1; index < size_; ++index) {
        if (entries_[index].rssiDbm < entries_[weakest].rssiDbm) {
            weakest = index;
        }
    }
    return weakest;
}

bool WifiNetworkCatalog::upsert(
    const domain::observations::Observation& observation) {
    if (observation.radio != domain::observations::RadioKind::Wifi ||
        observation.identityLength == 0 ||
        observation.identityLength > observation.identity.size()) {
        return false;
    }
    for (std::size_t index = 0; index < size_; ++index) {
        if (!sameIdentity(entries_[index], observation)) continue;
        const bool changed = visibleFieldsDiffer(entries_[index], observation);
        entries_[index] = observation;
        if (changed) ++revision_;
        return changed;
    }
    if (size_ < entries_.size()) {
        entries_[size_++] = observation;
        ++revision_;
        return true;
    }
    const std::size_t weakest = weakestIndex();
    if (observation.rssiDbm <= entries_[weakest].rssiDbm) return false;
    entries_[weakest] = observation;
    ++revision_;
    return true;
}

const domain::observations::Observation* WifiNetworkCatalog::at(
    std::size_t index) const {
    return index < size_ ? &entries_[index] : nullptr;
}

}  // namespace leshy1::apps::wifi
