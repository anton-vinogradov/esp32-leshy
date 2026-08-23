#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "apps/wifi/WifiDeviceCatalog.h"

namespace leshy1::apps::wifi {

// The discovery catalog is strongest-first until the user interacts. This
// fixed MAC snapshot then keeps the cursor and rows stable while live facts
// continue to refresh by identity.
class WifiDeviceNavigationOrder final {
public:
    void reset() {
        addresses_.fill({});
        size_ = 0U;
        locked_ = false;
    }

    bool lock(const WifiDeviceCatalog& catalog) {
        if (locked_) return true;
        if (catalog.size() == 0U) return false;
        size_ = catalog.size();
        for (std::size_t index = 0; index < size_; ++index) {
            const WifiDeviceRecord* record = catalog.at(index);
            if (record == nullptr) {
                reset();
                return false;
            }
            addresses_[index] = record->address;
        }
        locked_ = true;
        return true;
    }

    bool locked() const { return locked_; }
    std::size_t size(const WifiDeviceCatalog& catalog) const {
        return locked_ ? size_ : catalog.size();
    }
    const WifiDeviceRecord* at(const WifiDeviceCatalog& catalog,
                               std::size_t index) const {
        if (!locked_) return catalog.at(index);
        if (index >= size_) return nullptr;
        return catalog.at(catalog.indexOfAddress(addresses_[index]));
    }
    std::uint32_t orderHash(const WifiDeviceCatalog& catalog) const {
        std::uint32_t hash = 2166136261UL;
        const std::size_t count = size(catalog);
        for (std::size_t index = 0; index < count; ++index) {
            const WifiDeviceRecord* record = at(catalog, index);
            if (record == nullptr) continue;
            for (std::uint8_t byte : record->address) {
                hash ^= byte;
                hash *= 16777619UL;
            }
        }
        return hash;
    }

private:
    std::array<std::array<std::uint8_t, 6>, WifiDeviceCatalog::kCapacity>
        addresses_{};
    std::size_t size_ = 0U;
    bool locked_ = false;
};

}  // namespace leshy1::apps::wifi
