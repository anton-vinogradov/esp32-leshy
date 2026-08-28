#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"

namespace leshy1::drivers::ble {

struct BleScanPlan final {
    bool passive = true;
    // Product Survey keeps one row per address. Defensive evidence capture
    // explicitly opts out so repeated advertisements from the same identity
    // remain available to a threshold/window detector.
    bool deduplicateAddresses = true;
    std::uint32_t durationMs = 2000;
    std::uint16_t intervalMs = 100;
    std::uint16_t windowMs = 90;
    std::uint16_t maximumRecords = 64;
};

struct BleAdvertisementRecord final {
    std::array<std::uint8_t, 6> address{};
    std::uint8_t addressType = 0;
    std::int16_t rssiDbm = 0;
    const char* name = nullptr;
    std::size_t nameLength = 0;
    domain::observations::BleAdvertisementFacts advertisement{};
};

constexpr BleScanPlan defaultPassivePlan() { return {}; }

bool validatePassivePlan(const BleScanPlan& plan);

bool normalizePassiveRecord(
    const BleAdvertisementRecord& record, std::uint64_t monotonicUs,
    domain::observations::Observation* observation);

}  // namespace leshy1::drivers::ble
