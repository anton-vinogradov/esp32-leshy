#include "BootScreen.h"

#include <TFT_eSPI.h>

// TFT_eSPI reads its pin map from the build flags in platformio.ini.
static TFT_eSPI tft;

void BootScreen::show() {
    tft.init();
    tft.setRotation(2);                 // 240 x 320 portrait (ESP32-DIV panel is flipped vs rotation 0)

    const uint16_t bg    = tft.color565(0x12, 0x2a, 0x1c);
    const uint16_t gold  = tft.color565(0xe7, 0xcf, 0x8f);
    const uint16_t amber = tft.color565(0xff, 0xcf, 0x3f);
    const uint16_t green = tft.color565(0x2f, 0x5d, 0x3a);
    const uint16_t dim   = tft.color565(0x8f, 0xa9, 0x8f);

    tft.fillScreen(bg);

    // pine silhouettes along the bottom
    for (int i = 0; i < 4; i++) {
        int x = 30 + i * 60;
        tft.fillTriangle(x, 250, x - 24, 302, x + 24, 302, green);
        tft.fillTriangle(x, 274, x - 28, 314, x + 28, 314, green);
    }

    // Wi-Fi fan broadcasting upward (TFT_eSPI angles: 0 = 6 o'clock, clockwise)
    const int cx = 120, cy = 118;
    for (int r = 22; r <= 54; r += 16) {
        tft.drawSmoothArc(cx, cy, r, r - 4, 128, 232, amber, bg);
    }
    tft.fillCircle(cx, cy + 6, 5, amber);

    // title + subtitle (built-in fonts are ASCII-only)
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(gold, bg);
    tft.drawString("ESP32-Leshy", cx, 172, 4);
    tft.setTextColor(dim, bg);
    tft.drawString("firmware for ESP32-DIV", cx, 200, 2);
}
