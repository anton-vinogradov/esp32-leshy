#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"

namespace leshy1::apps::ble {

// Bounded, allocation-free product view of nearby BLE advertisers. One row is
// retained per address and the strongest devices stay at the top. Timestamp-
// only repeats do not advance the revision, which lets the TFT leave unchanged
// rows untouched.
class BleDeviceCatalog final {
public:
    static constexpr std::size_t kCapacity = 32;

    void reset();
    bool upsert(const domain::observations::Observation& observation);

    std::size_t size() const { return size_; }
    std::uint32_t revision() const { return revision_; }
    bool strongestFirst() const;
    const domain::observations::Observation* at(std::size_t index) const;
    std::size_t indexOfIdentity(
        const domain::observations::Observation& observation) const;

private:
    static bool sameIdentity(
        const domain::observations::Observation& left,
        const domain::observations::Observation& right);
    static bool visibleFieldsDiffer(
        const domain::observations::Observation& left,
        const domain::observations::Observation& right);
    void sortStrongestFirst();

    std::array<domain::observations::Observation, kCapacity> entries_{};
    std::size_t size_ = 0;
    std::uint32_t revision_ = 0;
};

}  // namespace leshy1::apps::ble
