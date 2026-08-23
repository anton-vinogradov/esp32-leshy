#include "BleDeviceCatalog.h"

#include <algorithm>
#include <cstring>

namespace leshy1::apps::ble {

void BleDeviceCatalog::reset() {
    entries_.fill(domain::observations::Observation{});
    size_ = 0;
    ++revision_;
}

bool BleDeviceCatalog::sameIdentity(
    const domain::observations::Observation& left,
    const domain::observations::Observation& right) {
    return left.radio == domain::observations::RadioKind::Ble &&
        right.radio == domain::observations::RadioKind::Ble &&
        left.identityLength != 0 &&
        left.identityLength == right.identityLength &&
        std::memcmp(left.identity.data(), right.identity.data(),
                    left.identityLength) == 0;
}

bool BleDeviceCatalog::visibleFieldsDiffer(
    const domain::observations::Observation& left,
    const domain::observations::Observation& right) {
    return left.rssiDbm != right.rssiDbm ||
        left.labelLength != right.labelLength ||
        std::memcmp(left.label.data(), right.label.data(),
                    left.labelLength) != 0;
}

void BleDeviceCatalog::sortStrongestFirst() {
    std::stable_sort(
        entries_.begin(), entries_.begin() + size_,
        [](const auto& left, const auto& right) {
            return left.rssiDbm > right.rssiDbm;
        });
}

bool BleDeviceCatalog::upsert(
    const domain::observations::Observation& observation) {
    if (observation.radio != domain::observations::RadioKind::Ble ||
        observation.identityLength == 0 ||
        observation.identityLength > observation.identity.size()) {
        return false;
    }
    for (std::size_t index = 0; index < size_; ++index) {
        if (!sameIdentity(entries_[index], observation)) continue;
        const bool changed = visibleFieldsDiffer(entries_[index], observation);
        entries_[index] = observation;
        if (changed) {
            sortStrongestFirst();
            ++revision_;
        }
        return changed;
    }
    if (size_ < entries_.size()) {
        entries_[size_++] = observation;
        sortStrongestFirst();
        ++revision_;
        return true;
    }
    if (observation.rssiDbm <= entries_[size_ - 1U].rssiDbm) return false;
    entries_[size_ - 1U] = observation;
    sortStrongestFirst();
    ++revision_;
    return true;
}

const domain::observations::Observation* BleDeviceCatalog::at(
    std::size_t index) const {
    return index < size_ ? &entries_[index] : nullptr;
}

}  // namespace leshy1::apps::ble
