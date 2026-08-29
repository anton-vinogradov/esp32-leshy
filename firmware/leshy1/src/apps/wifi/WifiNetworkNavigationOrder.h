#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "apps/wifi/WifiNetworkCatalog.h"

namespace leshy1::apps::wifi {

// The catalog remains strongest-first for discovery. Once the user starts
// navigating, this allocation-free identity snapshot prevents RSSI changes from
// moving rows or replacing the object under the cursor. Visible fields are still
// read live from the catalog by identity.
class WifiNetworkNavigationOrder final {
public:
    void reset() {
        identities_.fill({});
        identityLengths_.fill(0);
        size_ = 0;
        locked_ = false;
    }

    bool lock(const WifiNetworkCatalog& catalog) {
        if (locked_) return true;
        if (catalog.size() == 0) return false;
        size_ = catalog.size();
        for (std::size_t index = 0; index < size_; ++index) {
            const auto* observation = catalog.at(index);
            if (observation == nullptr || observation->identityLength == 0 ||
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

    std::size_t size(const WifiNetworkCatalog& catalog) const {
        return locked_ ? size_ : catalog.size();
    }

    const domain::observations::Observation* at(
        const WifiNetworkCatalog& catalog, std::size_t index) const {
        if (!locked_) return catalog.at(index);
        if (index >= size_) return nullptr;
        domain::observations::Observation identity;
        identity.radio = domain::observations::RadioKind::Wifi;
        identity.identity = identities_[index];
        identity.identityLength = identityLengths_[index];
        const std::size_t catalogIndex = catalog.indexOfIdentity(identity);
        return catalog.at(catalogIndex);
    }

    std::uint32_t orderHash(const WifiNetworkCatalog& catalog) const {
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

    std::uint32_t identityHash(const WifiNetworkCatalog& catalog,
                               std::size_t index) const {
        const auto* observation = at(catalog, index);
        if (observation == nullptr) return 0;
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

    // HIL can bind an authorized passive capture to an exact visible network
    // name without exposing that name or a BSSID through the diagnostic API.
    // The first match is strongest because an unlocked catalog is maintained
    // strongest-first. Callers must reject a locked order before using this
    // helper so the selected index remains the live catalog index.
    std::size_t indexOfLabelHash(const WifiNetworkCatalog& catalog,
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
               WifiNetworkCatalog::kCapacity> identities_{};
    std::array<std::uint8_t, WifiNetworkCatalog::kCapacity> identityLengths_{};
    std::size_t size_ = 0;
    bool locked_ = false;
};

}  // namespace leshy1::apps::wifi
