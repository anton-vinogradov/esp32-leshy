#pragma once

#include <Arduino.h>
#include <Adafruit_NeoPixel.h>

// The four WS2812 status LEDs in a row under the antenna connectors (verified on
// real ESP32-DIV v2 hardware: a single chain on GPIO1). They answer what the
// screen can't: "is this on the air right now, and with which radio?" — colour by
// activity, so a glance at the board is enough.
//
// Brightness is user-chosen (Settings) and kept very low: these sit under your
// fingers and the board is often used in the dark. 1/255 was below the LEDs'
// turn-on threshold, so the levels start at 2. The palette uses only pure channels
// (0 or 255) so hue survives even at these tiny brightnesses (partial channels
// would round to 0) — states differ by hue + motion, never by intensity.
class StatusLeds {
public:
    enum Activity { IDLE, WIFI_SCAN, BLE_SCAN, PROMISC, OTA, PORTAL, ERR };

    static const uint8_t PIN   = 1;
    static const uint8_t COUNT = 4;
    static const uint8_t DEFAULT_BRIGHT = 2;

    void begin();                        // loads the brightness level from NVS
    void set(Activity a);                // what the radio is doing now
    void setTx(uint8_t ledMask);         // force these LEDs solid yellow (an antenna is transmitting); 0 = none
    void tick();                         // animate; call from loop()
    uint8_t cycleBrightness();           // Off -> 2 -> 3 -> 5 -> 8 -> 12 -> Off; persists; returns new value
    uint8_t brightness() const { return bright_; }   // 0 = off
    void selfTest();                     // light all four in distinct colours (QA)

private:
    void show_(uint8_t i, uint8_t r, uint8_t g, uint8_t b);
    void paint_();                       // draw the current activity frame now (ignores the tick gate)
    void allOff_();

    Adafruit_NeoPixel px_{COUNT, PIN, NEO_GRB + NEO_KHZ800};
    Activity act_     = IDLE;
    uint8_t  txMask_  = 0;               // LEDs overridden to yellow (their antenna is on the air)
    uint8_t  bright_  = DEFAULT_BRIGHT;   // 0 = off, else WS2812 master brightness (kept tiny)
    bool     ready_   = false;
    uint8_t  step_    = 0;
    uint32_t last_    = 0;
};
