#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"

namespace leshy1::apps::wifi {

// A bounded, allocation-free live view of nearby access points. Survey
// sessions deliberately retain every observation; this catalog instead keeps
// one stable row per BSSID so the product UI does not jump or fill with
// duplicates while a scan remains open.
class WifiNetworkCatalog final {
public:
    static constexpr std::size_t kCapacity = 32;

    void reset();
    bool upsert(const domain::observations::Observation& observation);

    std::size_t size() const { return size_; }
    std::uint32_t revision() const { return revision_; }
    const domain::observations::Observation* at(std::size_t index) const;

private:
    static bool sameIdentity(
        const domain::observations::Observation& left,
        const domain::observations::Observation& right);
    static bool visibleFieldsDiffer(
        const domain::observations::Observation& left,
        const domain::observations::Observation& right);
    std::size_t weakestIndex() const;

    std::array<domain::observations::Observation, kCapacity> entries_{};
    std::size_t size_ = 0;
    std::uint32_t revision_ = 0;
};

}  // namespace leshy1::apps::wifi
