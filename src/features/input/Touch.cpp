#include "Touch.h"

#include "../display/Display.h"

#include <Preferences.h>

static bool s_ready = false;

void touchBegin() {
    uint16_t cal[5];
    Preferences p;
    p.begin("leshy", false);
    size_t got = p.getBytes("tcal", cal, sizeof(cal));
    if (got == sizeof(cal)) {                 // stored calibration → just use it
        tft.setTouch(cal);
        s_ready = true;
        p.end();
        return;
    }

    // first run: calibrate and persist
    tft.fillScreen(TFT_BLACK);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.drawString("Calibrate touch", 120, 140, 4);
    tft.drawString("tap each arrow", 120, 172, 2);
    tft.calibrateTouch(cal, TFT_WHITE, TFT_BLACK, 18);
    p.putBytes("tcal", cal, sizeof(cal));
    p.end();
    tft.setTouch(cal);
    s_ready = true;
}

void touchRecalibrate() {
    uint16_t cal[5];
    tft.fillScreen(TFT_BLACK);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.drawString("Calibrate touch", 120, 140, 4);
    tft.drawString("tap each arrow", 120, 172, 2);
    tft.calibrateTouch(cal, TFT_WHITE, TFT_BLACK, 18);
    Preferences p;
    p.begin("leshy", false);
    p.putBytes("tcal", cal, sizeof(cal));
    p.end();
    tft.setTouch(cal);
    s_ready = true;
}

bool touchGet(uint16_t& x, uint16_t& y) {
    return s_ready && tft.getTouch(&x, &y);
}
