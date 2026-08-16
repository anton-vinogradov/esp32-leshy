#include "platform/arduino/BoardSafeOutputs.h"

#include <Arduino.h>
#include <driver/gpio.h>

#include "boards/esp32_div_v2/BoardProfile.h"

namespace leshy1::platform::arduino {
namespace {

using boards::esp32_div_v2::BoardProfile;
bool configured = false;

}  // namespace

void BoardSafeOutputs::establishBootInvariant() {
    // Preload the inactive level before enabling the output driver. GPIO2 must
    // remain LOW: HIGH activates the buzzer transistor on ESP32-DIV v2.
    digitalWrite(BoardProfile::kBuzzerPin, LOW);
    pinMode(BoardProfile::kBuzzerPin, OUTPUT);
    configured = true;
}

bool BoardSafeOutputs::buzzerHeldInactive() {
    const gpio_num_t pin = static_cast<gpio_num_t>(BoardProfile::kBuzzerPin);
    // Direction is established only by the guarded adapter above; the clean
    // target static check rejects GPIO reconfiguration elsewhere. Runtime
    // evidence therefore verifies the independently readable pad level.
    return configured && gpio_get_level(pin) == 0;
}

}  // namespace leshy1::platform::arduino
