#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "apps/ble/BleDeviceCatalog.h"

namespace leshy1::apps::ble {

// Discovery is strongest-first. Once the user navigates, this bounded identity
// snapshot keeps rows and the object under the cursor stable while their live
// signal and advertisement facts continue to update in place.
class BleDeviceNavigationOrder final {
public:
    void reset() {
        identities_.fill({});
        identityLengths_.fill(0U);
        size_ = 0U;
        locked_ = false;
    }

    bool lock(const BleDeviceCatalog& catalog) {
        if (locked_) return true;
        if (catalog.size() == 0U) return false;
        size_ = catalog.size();
        for (std::size_t index = 0; index < size_; ++index) {
            const auto* observation = catalog.at(index);
            if (observation == nullptr || observation->identityLength == 0U ||
                observation->identityLength > identities_[index].size()) {
                reset();
                return false;
            }
            identities_[index] = observation->identity;
            identityLengths_[index] = observation->identityLength;
        }
        locked_ = true;
        return true;
    }

    bool locked() const { return locked_; }

    std::size_t size(const BleDeviceCatalog& catalog) const {
        return locked_ ? size_ : catalog.size();
    }

    const domain::observations::Observation* at(
            const BleDeviceCatalog& catalog, std::size_t index) const {
        if (!locked_) return catalog.at(index);
        if (index >= size_) return nullptr;
        domain::observations::Observation identity;
        identity.radio = domain::observations::RadioKind::Ble;
        identity.identity = identities_[index];
        identity.identityLength = identityLengths_[index];
        return catalog.at(catalog.indexOfIdentity(identity));
    }

    std::uint32_t orderHash(const BleDeviceCatalog& catalog) const {
        std::uint32_t hash = 2166136261UL;
        const std::size_t count = size(catalog);
        for (std::size_t index = 0; index < count; ++index) {
            const auto* observation = at(catalog, index);
            if (observation == nullptr) continue;
            hash ^= observation->identityLength;
            hash *= 16777619UL;
            for (std::size_t byte = 0;
                 byte < observation->identityLength; ++byte) {
                hash ^= observation->identity[byte];
                hash *= 16777619UL;
            }
        }
        return hash;
    }

    std::uint32_t identityHash(const BleDeviceCatalog& catalog,
                               std::size_t index) const {
        const auto* observation = at(catalog, index);
        if (observation == nullptr) return 0U;
        std::uint32_t hash = 2166136261UL;
        for (std::size_t byte = 0;
             byte < observation->identityLength; ++byte) {
            hash ^= observation->identity[byte];
            hash *= 16777619UL;
        }
        return hash;
    }

    static std::uint64_t labelHash(
        const domain::observations::Observation& observation) {
        if (observation.labelLength == 0U ||
            observation.labelLength > observation.label.size() - 1U) {
            return 0U;
        }
        std::uint64_t hash = 14695981039346656037ULL;
        for (std::size_t byte = 0; byte < observation.labelLength; ++byte) {
            hash ^= static_cast<std::uint8_t>(observation.label[byte]);
            hash *= 1099511628211ULL;
        }
        return hash;
    }

    // HIL binds an authorized connection test to an exact visible fixture
    // label without disclosing its address or label through diagnostics. The
    // caller must require an unlocked strongest-first catalog.
    std::size_t indexOfLabelHash(const BleDeviceCatalog& catalog,
                                 std::uint64_t requestedHash,
                                 std::size_t* matchCount = nullptr) const {
        std::size_t matches = 0U;
        const std::size_t count = size(catalog);
        std::size_t first = count;
        for (std::size_t index = 0; index < count; ++index) {
            const auto* observation = at(catalog, index);
            if (observation == nullptr ||
                labelHash(*observation) != requestedHash) {
                continue;
            }
            if (matches == 0U) first = index;
            ++matches;
        }
        if (matchCount != nullptr) *matchCount = matches;
        return first;
    }

private:
    std::array<std::array<std::uint8_t,
                          domain::observations::Observation::kIdentityCapacity>,
               BleDeviceCatalog::kCapacity> identities_{};
    std::array<std::uint8_t, BleDeviceCatalog::kCapacity> identityLengths_{};
    std::size_t size_ = 0U;
    bool locked_ = false;
};

}  // namespace leshy1::apps::ble
