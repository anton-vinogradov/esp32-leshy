#pragma once

#include <cstdint>

#include <Adafruit_NeoPixel.h>

#include "boards/esp32_div_v2/BoardProfile.h"

namespace leshy1::platform::arduino {

// Thin physical adapter for the single four-pixel WS2812 chain. It redraws only
// when the state changes, so radio sampling never inherits a periodic LED update.
class BoardAntennaStatusLeds final {
public:
    bool begin(std::uint8_t brightnessRaw);
    bool apply(std::uint8_t brightnessRaw, std::uint8_t receiveMask,
               std::uint8_t faultMask);
    bool ready() const { return ready_; }

private:
    Adafruit_NeoPixel pixels_{
        boards::esp32_div_v2::BoardProfile::kStatusLedCount,
        boards::esp32_div_v2::BoardProfile::kStatusLedPin,
        NEO_GRB + NEO_KHZ800};
    std::uint8_t brightnessRaw_ = 0xffU;
    std::uint8_t receiveMask_ = 0xffU;
    std::uint8_t faultMask_ = 0xffU;
    bool ready_ = false;
};

}  // namespace leshy1::platform::arduino
