#pragma once

#include <cstddef>
#include <cstdint>

namespace leshy1::services::survey {

constexpr std::size_t kIngressTimingMaxSamples = 32;

struct IngressRateSummary final {
    bool valid = false;
    std::size_t samples = 0;
    std::uint64_t minimumBytesPerSecond = 0;
    std::uint64_t p50BytesPerSecond = 0;
    std::uint64_t p95BytesPerSecond = 0;
    std::uint64_t p99BytesPerSecond = 0;
    std::uint64_t maximumBytesPerSecond = 0;
};

IngressRateSummary summarizeIngressRates(const std::uint64_t* rates,
                                         std::size_t count);

}  // namespace leshy1::services::survey
