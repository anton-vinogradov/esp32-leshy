#include "IngressTiming.h"

#include <array>

namespace leshy1::services::survey {
namespace {

std::size_t nearestRank(std::size_t count, std::size_t percentile) {
    const std::size_t rank = (count * percentile + 99U) / 100U;
    return rank == 0 ? 0 : rank - 1U;
}

}  // namespace

IngressRateSummary summarizeIngressRates(const std::uint64_t* rates,
                                         std::size_t count) {
    IngressRateSummary result;
    if (rates == nullptr || count == 0 || count > kIngressTimingMaxSamples) {
        return result;
    }
    std::array<std::uint64_t, kIngressTimingMaxSamples> ordered{};
    for (std::size_t index = 0; index < count; ++index) {
        if (rates[index] == 0) return result;
        ordered[index] = rates[index];
    }
    for (std::size_t left = 0; left + 1U < count; ++left) {
        std::size_t smallest = left;
        for (std::size_t right = left + 1U; right < count; ++right) {
            if (ordered[right] < ordered[smallest]) smallest = right;
        }
        if (smallest != left) {
            const std::uint64_t value = ordered[left];
            ordered[left] = ordered[smallest];
            ordered[smallest] = value;
        }
    }
    result.valid = true;
    result.samples = count;
    result.minimumBytesPerSecond = ordered[0];
    result.p50BytesPerSecond = ordered[nearestRank(count, 50)];
    result.p95BytesPerSecond = ordered[nearestRank(count, 95)];
    result.p99BytesPerSecond = ordered[nearestRank(count, 99)];
    result.maximumBytesPerSecond = ordered[count - 1U];
    return result;
}

}  // namespace leshy1::services::survey
