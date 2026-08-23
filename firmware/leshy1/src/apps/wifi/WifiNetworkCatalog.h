#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"

namespace leshy1::apps::wifi {

// A bounded, allocation-free live view of nearby access points. Survey
// sessions deliberately retain every observation; this catalog instead keeps
// one row per BSSID, ordered by descending RSSI, so the strongest nearby
// networks remain at the top without filling the UI with duplicates.
class WifiNetworkCatalog final {
public:
    static constexpr std::size_t kCapacity = 32;

    void reset();
    // A locked navigation snapshot disables replacement of its identities when
    // the bounded catalog is full, while existing rows still receive live data.
    bool upsert(const domain::observations::Observation& observation,
                bool allowReplacement = true);

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

}  // namespace leshy1::apps::wifi
