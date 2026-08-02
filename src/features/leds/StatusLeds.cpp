#include "StatusLeds.h"

#include <Preferences.h>

// Off + rising dim steps. Starts at 2 because 1/255 is below these LEDs' turn-on
// threshold (verified on hardware: at 1 they stay dark).
static const uint8_t LEVELS[] = { 0, 2, 3, 5, 8, 12 };

void StatusLeds::begin() {
    Preferences p;
    p.begin("leshy", true);
    bright_ = p.getUChar("led_br", DEFAULT_BRIGHT);
    p.end();
    px_.begin();
    px_.setBrightness(bright_ ? bright_ : 1);
    px_.clear();
    px_.show();
    ready_ = true;
}

uint8_t StatusLeds::cycleBrightness() {
    uint8_t idx = 0;
    for (uint8_t i = 0; i < sizeof(LEVELS); i++) if (LEVELS[i] == bright_) { idx = i; break; }
    bright_ = LEVELS[(idx + 1) % sizeof(LEVELS)];
    Preferences p;
    p.begin("leshy", false);
    p.putUChar("led_br", bright_);
    p.end();
    if (bright_) { px_.setBrightness(bright_); paint_(); }
    else         allOff_();
    return bright_;
}

void StatusLeds::allOff_() {
    if (!ready_) return;
    px_.clear();
    px_.show();
}

void StatusLeds::show_(uint8_t i, uint8_t r, uint8_t g, uint8_t b) {
    px_.setPixelColor(i, px_.Color(r, g, b));
}

void StatusLeds::set(Activity a) {
    if (a == act_) return;        // idempotent: the UI syncs this every tick
    act_ = a;
    step_ = 0;
    if (!ready_ || !bright_) return;
    paint_();                     // show the first frame immediately
}

void StatusLeds::tick() {
    if (!ready_ || !bright_ || act_ == IDLE) return;
    uint32_t now = millis();
    if (now - last_ < 90) return;
    step_++;
    paint_();
}

// Draw the frame for the current activity/step. Each state gets its own hue and
// motion so the row is readable at a glance without looking at the screen. Only
// pure channels (0/255) — see the header for why.
void StatusLeds::paint_() {
    if (!ready_ || !bright_) return;
    last_ = millis();
    px_.clear();
    switch (act_) {
        case WIFI_SCAN:                          // single green pixel running the row — a scan in motion
            show_(step_ % COUNT, 0, 255, 0);
            break;
        case BLE_SCAN:                           // slow blue blink — listening
            if ((step_ / 5) % 2 == 0)
                for (uint8_t i = 0; i < COUNT; i++) show_(i, 0, 0, 255);
            break;
        case PROMISC:                            // yellow, alternating pixels — watching for attacks
            for (uint8_t i = 0; i < COUNT; i++)
                if ((i + step_) % 2 == 0) show_(i, 255, 255, 0);
            break;
        case OTA: {                              // white progress bar filling up
            uint8_t lit = (step_ / 3) % (COUNT + 1);
            for (uint8_t i = 0; i < lit; i++) show_(i, 255, 255, 255);
            break;
        }
        case PORTAL:                             // solid magenta — the setup access point is up
            for (uint8_t i = 0; i < COUNT; i++) show_(i, 255, 0, 255);
            break;
        case ERR:                                // red blink
            if (step_ % 2) for (uint8_t i = 0; i < COUNT; i++) show_(i, 255, 0, 0);
            break;
        default: break;
    }
    px_.show();
}

// QA: prove all four pixels and their left-to-right order in one shot.
void StatusLeds::selfTest() {
    if (!ready_) return;
    static const uint8_t C[COUNT][3] = { {255,0,0}, {0,255,0}, {0,0,255}, {255,255,0} };  // pure channels — survive tiny brightness
    px_.setBrightness(bright_ ? bright_ : DEFAULT_BRIGHT);
    for (uint8_t i = 0; i < COUNT; i++) show_(i, C[i][0], C[i][1], C[i][2]);
    px_.show();
    Serial.printf("[leds] self-test @%u/255: 1=red 2=green 3=blue 4=yellow (left to right)\n",
                  bright_ ? bright_ : DEFAULT_BRIGHT);
}
