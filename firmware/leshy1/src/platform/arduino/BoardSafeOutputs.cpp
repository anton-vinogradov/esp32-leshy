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
    for (const int pin : BoardProfile::kNrfCePins) {
        digitalWrite(pin, LOW);
        pinMode(pin, OUTPUT);
    }
    configured = true;
}

void BoardSafeOutputs::emergencyQuiesce() {
    // Idempotent task-context stop. The Task-WDT ISR uses the same inactive
    // levels through direct write-one-to-clear GPIO registers.
    digitalWrite(BoardProfile::kBuzzerPin, LOW);
    for (const int pin : BoardProfile::kNrfCePins) {
        digitalWrite(pin, LOW);
    }
}

bool BoardSafeOutputs::buzzerHeldInactive() {
    const gpio_num_t pin = static_cast<gpio_num_t>(BoardProfile::kBuzzerPin);
    // Direction is established only by the guarded adapter above; the clean
    // target static check rejects GPIO reconfiguration elsewhere. Runtime
    // evidence therefore verifies the independently readable pad level.
    return configured && gpio_get_level(pin) == 0;
}

bool BoardSafeOutputs::radioTransmitPathsHeldInactive() {
    for (const int pin : BoardProfile::kNrfCePins) {
        if (gpio_get_level(static_cast<gpio_num_t>(pin)) != 0) return false;
    }
    return configured;
}

}  // namespace leshy1::platform::arduino
