#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"

namespace leshy1::drivers::ble {

// Upper bound for a streaming passive scan. The platform adapter processes
// records as they arrive, so this limits CPU/evidence accounting rather than
// reserving a matching packet buffer. Product Survey keeps its smaller
// per-address default while repeat-sensitive detectors may explicitly use the
// larger bounded budget.
constexpr std::uint16_t kMaximumDeduplicatedRecords = 128U;
constexpr std::uint16_t kMaximumStreamingRecords = 4096U;
constexpr std::size_t kLegacyAdvertisementPayloadCapacity = 31U;

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
    std::uint8_t eventType = 0;
    std::int16_t rssiDbm = 0;
    std::array<std::uint8_t, kLegacyAdvertisementPayloadCapacity> payload{};
    std::uint8_t payloadLength = 0;
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
