#include "platform/arduino/BoardAntennaStatusLeds.h"

namespace leshy1::platform::arduino {

bool BoardAntennaStatusLeds::begin(std::uint8_t brightnessRaw) {
    pixels_.begin();
    ready_ = true;
    brightnessRaw_ = 0xffU;
    receiveMask_ = 0xffU;
    faultMask_ = 0xffU;
    return apply(brightnessRaw, 0, 0);
}

bool BoardAntennaStatusLeds::apply(std::uint8_t brightnessRaw,
                                   std::uint8_t receiveMask,
                                   std::uint8_t faultMask) {
    if (!ready_) return false;
    receiveMask &= 0x0fU;
    faultMask &= 0x0fU;
    receiveMask = static_cast<std::uint8_t>(receiveMask & ~faultMask);
    if (brightnessRaw_ == brightnessRaw && receiveMask_ == receiveMask &&
        faultMask_ == faultMask) {
        return true;
    }
    brightnessRaw_ = brightnessRaw;
    receiveMask_ = receiveMask;
    faultMask_ = faultMask;
    pixels_.setBrightness(brightnessRaw == 0U ? 1U : brightnessRaw);
    pixels_.clear();
    if (brightnessRaw != 0U) {
        for (std::uint8_t pixel = 0; pixel < 4U; ++pixel) {
            const std::uint8_t bit = static_cast<std::uint8_t>(1U << pixel);
            if ((faultMask & bit) != 0U) {
                pixels_.setPixelColor(pixel, pixels_.Color(255, 0, 0));
            } else if ((receiveMask & bit) != 0U) {
                pixels_.setPixelColor(pixel, pixels_.Color(0, 255, 0));
            }
        }
    }
    pixels_.show();
    return true;
}

}  // namespace leshy1::platform::arduino
