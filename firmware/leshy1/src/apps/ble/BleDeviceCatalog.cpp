#include "BleDeviceCatalog.h"

#include <cstring>

namespace leshy1::apps::ble {

void BleDeviceCatalog::reset() {
    entries_.fill(domain::observations::Observation{});
    signals_.fill(BleDeviceSignalStats{});
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
                    left.labelLength) != 0 ||
        !domain::observations::bleAdvertisementFactsEqual(
            left.bleAdvertisement, right.bleAdvertisement);
}

void BleDeviceCatalog::sortStrongestFirst() {
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

bool BleDeviceCatalog::strongestFirst() const {
    for (std::size_t index = 1; index < size_; ++index) {
        if (entries_[index - 1U].rssiDbm < entries_[index].rssiDbm) {
            return false;
        }
    }
    return true;
}

bool BleDeviceCatalog::upsert(
    const domain::observations::Observation& observation,
    bool allowReplacement) {
    if (observation.radio != domain::observations::RadioKind::Ble ||
        observation.identityLength == 0 ||
        observation.identityLength > observation.identity.size()) {
        return false;
    }
    for (std::size_t index = 0; index < size_; ++index) {
        if (!sameIdentity(entries_[index], observation)) continue;
        auto merged = observation;
        if (observation.labelLength == 0U &&
            entries_[index].labelLength != 0U) {
            merged.label = entries_[index].label;
            merged.labelLength = entries_[index].labelLength;
        }
        auto& currentFacts = entries_[index].bleAdvertisement;
        auto& mergedFacts = merged.bleAdvertisement;
        if (!mergedFacts.companyKnown && currentFacts.companyKnown) {
            mergedFacts.companyKnown = true;
            mergedFacts.companyId = currentFacts.companyId;
            mergedFacts.appleContinuityType = currentFacts.appleContinuityType;
        } else if (mergedFacts.companyKnown && currentFacts.companyKnown &&
                   mergedFacts.companyId == currentFacts.companyId &&
                   mergedFacts.appleContinuityType == 0U) {
            mergedFacts.appleContinuityType =
                currentFacts.appleContinuityType;
        }
        if (!mergedFacts.appearanceKnown && currentFacts.appearanceKnown) {
            mergedFacts.appearanceKnown = true;
            mergedFacts.appearance = currentFacts.appearance;
        }
        if (!mergedFacts.txPowerKnown && currentFacts.txPowerKnown) {
            mergedFacts.txPowerKnown = true;
            mergedFacts.txPowerDbm = currentFacts.txPowerDbm;
        }
        if (mergedFacts.firstServiceUuidLength == 0U &&
            currentFacts.firstServiceUuidLength != 0U) {
            mergedFacts.firstServiceUuid = currentFacts.firstServiceUuid;
            mergedFacts.firstServiceUuidLength =
                currentFacts.firstServiceUuidLength;
            mergedFacts.firstServiceUuidHash =
                currentFacts.firstServiceUuidHash;
        }
        mergedFacts.knownServiceMask |= currentFacts.knownServiceMask;
        if (mergedFacts.serviceUuidCount < currentFacts.serviceUuidCount) {
            mergedFacts.serviceUuidCount = currentFacts.serviceUuidCount;
        }
        if (mergedFacts.serviceDataCount < currentFacts.serviceDataCount) {
            mergedFacts.serviceDataCount = currentFacts.serviceDataCount;
        }
        if (mergedFacts.manufacturerDataLength <
            currentFacts.manufacturerDataLength) {
            mergedFacts.manufacturerDataLength =
                currentFacts.manufacturerDataLength;
        }
        if (mergedFacts.payloadLength < currentFacts.payloadLength) {
            mergedFacts.payloadLength = currentFacts.payloadLength;
        }
        auto signal = signals_[index];
        if (signal.samples == 0U) {
            signal = {1U, observation.rssiDbm, observation.rssiDbm, 0};
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

const domain::observations::Observation* BleDeviceCatalog::at(
    std::size_t index) const {
    return index < size_ ? &entries_[index] : nullptr;
}

const BleDeviceSignalStats* BleDeviceCatalog::signalAt(
    std::size_t index) const {
    return index < size_ ? &signals_[index] : nullptr;
}

std::size_t BleDeviceCatalog::indexOfIdentity(
    const domain::observations::Observation& observation) const {
    for (std::size_t index = 0; index < size_; ++index) {
        if (sameIdentity(entries_[index], observation)) return index;
    }
    return size_;
}

}  // namespace leshy1::apps::ble
