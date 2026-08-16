#pragma once

#include <cstddef>
#include <cstdint>

namespace leshy1::storage {

// Nearest-rank percentiles over positive end-to-end operation durations. The input
// is sorted in place so callers can provide fixed caller-owned storage.
struct StorageTimingSummary final {
    bool valid = false;
    std::size_t samples = 0;
    std::uint64_t totalUs = 0;
    std::uint64_t minimumUs = 0;
    std::uint64_t p50Us = 0;
    std::uint64_t p95Us = 0;
    std::uint64_t p99Us = 0;
    std::uint64_t maximumUs = 0;
};

StorageTimingSummary summarizeStorageTimings(std::uint64_t* samples,
                                             std::size_t count);

}  // namespace leshy1::storage
