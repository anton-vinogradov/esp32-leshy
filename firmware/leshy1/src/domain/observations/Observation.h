#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace leshy1::domain::observations {

enum class RadioKind : std::uint8_t {
    Wifi = 1,
    Ble = 2,
};

struct Observation final {
    static constexpr std::size_t kIdentityCapacity = 6;
    static constexpr std::size_t kLabelCapacity = 32;

    std::uint64_t sequence = 0;
    std::uint64_t monotonicUs = 0;
    RadioKind radio = RadioKind::Wifi;
    std::uint32_t frequencyKhz = 0;
    std::uint16_t channel = 0;
    std::int16_t rssiDbm = 0;
    std::array<std::uint8_t, kIdentityCapacity> identity{};
    std::uint8_t identityLength = 0;
    std::array<char, kLabelCapacity + 1> label{};
    std::uint8_t labelLength = 0;
};

}  // namespace leshy1::domain::observations
