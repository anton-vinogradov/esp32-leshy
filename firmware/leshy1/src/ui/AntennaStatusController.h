#pragma once

#include <cstddef>
#include <cstdint>

namespace leshy1::ui {

// Product-level model for the four LEDs below the external antenna connectors.
// Pixel 0 belongs to CC1101; pixels 1..3 belong to nRF24 slots 1..3. The
// controller is allocation-free and hardware-independent so the mapping and
// deliberately tiny 0.x brightness ladder remain host-testable.
class AntennaStatusController final {
public:
    static constexpr std::uint8_t kLedCount = 4;
    static constexpr std::uint8_t kAllMask = 0x0fU;
    static constexpr std::uint8_t kCc1101Mask = 0x01U;
    static constexpr std::uint8_t kBrightnessCount = 6;
    static constexpr std::uint8_t kDefaultBrightnessIndex = 1;

    void restoreBrightness(std::uint8_t index);
    bool cycleBrightness();
    std::uint8_t brightnessIndex() const { return brightnessIndex_; }
    std::uint8_t brightnessRaw() const;

    bool setActivity(std::uint8_t receiveMask, std::uint8_t faultMask);
    std::uint8_t receiveMask() const { return receiveMask_; }
    std::uint8_t faultMask() const { return faultMask_; }

    static constexpr std::uint8_t nrf24Mask(std::uint8_t zeroBasedSlot) {
        return zeroBasedSlot < 3U
            ? static_cast<std::uint8_t>(1U << (zeroBasedSlot + 1U)) : 0U;
    }
    static constexpr std::uint8_t nrf24MaskFromSlots(std::uint8_t slotMask) {
        return static_cast<std::uint8_t>((slotMask & 0x07U) << 1U);
    }
    static std::uint8_t brightnessRawAt(std::uint8_t index);
    static std::uint8_t brightnessIndexForRaw(std::uint8_t raw);

private:
    std::uint8_t brightnessIndex_ = kDefaultBrightnessIndex;
    std::uint8_t receiveMask_ = 0;
    std::uint8_t faultMask_ = 0;
};

}  // namespace leshy1::ui
