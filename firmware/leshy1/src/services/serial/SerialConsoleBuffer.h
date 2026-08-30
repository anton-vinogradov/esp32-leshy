#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace leshy1::services::serial {

// Volatile, allocation-free receive window. Overflow is observable and never
// overwrites older bytes silently; product code treats it as a terminal
// endpoint failure rather than presenting a corrupted transcript.
class SerialConsoleBuffer final {
public:
    static constexpr std::size_t kCapacity = 256U;

    bool push(std::uint8_t value);
    bool pop(std::uint8_t* output);
    void scrub();
    void reset();

    std::size_t size() const { return size_; }
    std::size_t highWater() const { return highWater_; }
    std::uint32_t dropped() const { return dropped_; }
    bool empty() const { return size_ == 0U; }

private:
    std::array<std::uint8_t, kCapacity> bytes_{};
    std::size_t head_ = 0U;
    std::size_t tail_ = 0U;
    std::size_t size_ = 0U;
    std::size_t highWater_ = 0U;
    std::uint32_t dropped_ = 0U;
};

}  // namespace leshy1::services::serial
