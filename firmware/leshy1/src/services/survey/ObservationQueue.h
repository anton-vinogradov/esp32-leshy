#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"

namespace leshy1::services::survey {

class ObservationQueue final {
public:
    static constexpr std::size_t kCapacity = 64;

    bool push(const domain::observations::Observation& observation);
    bool pop(domain::observations::Observation* output);
    void reset();

    std::size_t size() const { return size_; }
    bool empty() const { return size_ == 0; }
    bool full() const { return size_ == entries_.size(); }
    std::size_t highWater() const { return highWater_; }
    std::uint64_t pushed() const { return pushed_; }
    std::uint64_t popped() const { return popped_; }
    std::uint64_t dropped() const { return dropped_; }

private:
    std::array<domain::observations::Observation, kCapacity> entries_{};
    std::size_t head_ = 0;
    std::size_t tail_ = 0;
    std::size_t size_ = 0;
    std::size_t highWater_ = 0;
    std::uint64_t pushed_ = 0;
    std::uint64_t popped_ = 0;
    std::uint64_t dropped_ = 0;
};

}  // namespace leshy1::services::survey
