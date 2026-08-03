#pragma once

#include <Arduino.h>

// Buttons — the 5-way keypad on the ESP32-DIV, wired through a PCF8574 I2C
// expander (address auto-detected 0x20-0x27). Raw I2C, no library. Active-low
// (a pressed button pulls its bit to 0). The bit->key map differs between board
// revisions, so it's calibratable — see the button-test demo.
class Buttons {
public:
    enum Key { NONE, UP, DOWN, LEFT, RIGHT, SELECT };

    bool begin();               // Wire.begin + scan for the PCF8574
    Key  poll();                // returns a key on the press edge (debounced)
    bool held(Key k);           // is key k currently pressed right now (for long-press timing)
    uint8_t readRaw();          // raw PCF byte (bit low = pressed)

    bool    found() const { return found_; }
    uint8_t addr()  const { return addr_; }

    // bit positions on the PCF8574 (default = shared.h set #1)
    void setMap(uint8_t up, uint8_t down, uint8_t left, uint8_t right, uint8_t select) {
        bitUp_ = up; bitDown_ = down; bitLeft_ = left; bitRight_ = right; bitSelect_ = select;
    }

private:
    uint8_t  addr_ = 0;
    bool     found_ = false;
    uint8_t  last_ = 0xFF;
    uint32_t lastMs_ = 0;
    // confirmed on this ESP32-DIV v2 (shared.h "set #2"); other revisions use
    // up=6 down=3 left=4 right=5 select=7 — override with setMap() if needed.
    uint8_t  bitUp_ = 7, bitDown_ = 5, bitLeft_ = 3, bitRight_ = 4, bitSelect_ = 6;
};
