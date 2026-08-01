#include "Buttons.h"

#include <Wire.h>

bool Buttons::begin() {
    Wire.begin();                               // default I2C pins (ESP32-S3: SDA 8 / SCL 9)
    for (uint8_t a = 0x20; a <= 0x27; a++) {
        Wire.beginTransmission(a);
        if (Wire.endTransmission() == 0) {
            addr_ = a;
            found_ = true;
            break;
        }
    }
    if (found_) last_ = readRaw();
    return found_;
}

uint8_t Buttons::readRaw() {
    if (!found_) return 0xFF;
    if (Wire.requestFrom((int)addr_, 1) && Wire.available()) return Wire.read();
    return 0xFF;
}

Buttons::Key Buttons::poll() {
    if (!found_) return NONE;
    uint32_t now = millis();
    if (now - lastMs_ < 35) return NONE;        // debounce / sample rate
    lastMs_ = now;

    uint8_t v = readRaw();
    uint8_t edge = last_ & ~v;                  // bits that went high(released) -> low(pressed)
    last_ = v;

    if (edge & (1 << bitSelect_)) return SELECT;
    if (edge & (1 << bitUp_))     return UP;
    if (edge & (1 << bitDown_))   return DOWN;
    if (edge & (1 << bitLeft_))   return LEFT;
    if (edge & (1 << bitRight_))  return RIGHT;
    return NONE;
}
