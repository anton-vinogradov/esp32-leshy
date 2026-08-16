#include "StorageTiming.h"

#include <limits>

namespace leshy1::storage {
namespace {

std::size_t nearestRankIndex(std::size_t count, std::size_t percentile) {
    const std::size_t rank = (count * percentile + 99U) / 100U;
    return rank == 0 ? 0 : rank - 1U;
}

}  // namespace

StorageTimingSummary summarizeStorageTimings(std::uint64_t* samples,
                                             std::size_t count) {
    StorageTimingSummary summary;
    if (samples == nullptr || count == 0 ||
        count > std::numeric_limits<std::size_t>::max() / 100U) {
        return summary;
    }
    for (std::size_t index = 0; index < count; ++index) {
        if (samples[index] == 0 ||
            summary.totalUs > std::numeric_limits<std::uint64_t>::max() - samples[index]) {
            return StorageTimingSummary{};
        }
        summary.totalUs += samples[index];
        const std::uint64_t value = samples[index];
        std::size_t insertion = index;
        while (insertion > 0 && samples[insertion - 1U] > value) {
            samples[insertion] = samples[insertion - 1U];
            --insertion;
        }
        samples[insertion] = value;
    }
    summary.valid = true;
    summary.samples = count;
    summary.minimumUs = samples[0];
    summary.p50Us = samples[nearestRankIndex(count, 50U)];
    summary.p95Us = samples[nearestRankIndex(count, 95U)];
    summary.p99Us = samples[nearestRankIndex(count, 99U)];
    summary.maximumUs = samples[count - 1U];
    return summary;
}

}  // namespace leshy1::storage
