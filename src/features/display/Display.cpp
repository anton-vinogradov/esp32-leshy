#include "Display.h"
#include "font_ru_small.h"

#include <Preferences.h>

TFT_eSPI tft;

// Backlight on GPIO7 for ESP32-DIV v2 (CiferTech BoardConfig). arduino-esp32 3.x
// LEDC API: ledcAttach(pin, freq, res) then ledcWrite(pin, duty).
static const uint8_t  BL_PIN      = 7;
static const uint8_t  BL_LEVELS[] = { 255, 176, 112, 64, 24 };   // never fully off — a dark screen reads as "bricked"
static uint8_t        s_bl        = 255;

void displayInit() {
    tft.init();
    tft.setRotation(2);      // ESP32-DIV v2 panel is flipped vs rotation 0
}

void uiBacklightBegin() {
    Preferences p;
    p.begin("leshy", true);
    s_bl = p.getUChar("bl", 255);   // default full = how the board looked before this was adjustable
    p.end();
    ledcAttach(BL_PIN, 5000, 8);
    ledcWrite(BL_PIN, s_bl);
}

uint8_t uiBacklightCycle() {
    uint8_t idx = 0;
    for (uint8_t i = 0; i < sizeof(BL_LEVELS); i++) if (BL_LEVELS[i] == s_bl) { idx = i; break; }
    s_bl = BL_LEVELS[(idx + 1) % sizeof(BL_LEVELS)];
    ledcWrite(BL_PIN, s_bl);
    Preferences p;
    p.begin("leshy", false);
    p.putUChar("bl", s_bl);
    p.end();
    return s_bl;
}

uint8_t uiBacklightLevel() { return s_bl; }

uint16_t uiBg() { return tft.color565(0x10, 0x18, 0x12); }

uint16_t uiRssiColor(int rssi) {
    if (rssi > -60) return tft.color565(0x4c, 0xd1, 0x64);   // green
    if (rssi > -75) return tft.color565(0xf0, 0xc4, 0x3a);   // yellow
    return tft.color565(0xd1, 0x4c, 0x4c);                   // red
}

void uiHeader(const char* title, const char* right) {
    const uint16_t hdr  = tft.color565(0x1e, 0x3a, 0x28);
    const uint16_t gold = tft.color565(0xe7, 0xcf, 0x8f);
    const uint16_t dim  = tft.color565(0x8f, 0xa9, 0x8f);
    tft.fillRect(0, 0, 240, 28, hdr);
    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(gold, hdr);
    tft.drawString(title, 6, 14, 4);
    tft.setTextDatum(MR_DATUM);
    tft.setTextColor(dim, hdr);
    tft.drawString(right, 234, 14, 2);
}

void uiFooter(const char* hint) {
    const uint16_t bg  = uiBg();
    const uint16_t dim = tft.color565(0x7a, 0x8a, 0x7a);
    tft.fillRect(0, 306, 240, 14, bg);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(dim, bg);
    tft.drawString(hint, 120, 313, 1);
}

TFT_eSprite& uiRow() {
    static TFT_eSprite row(&tft);
    static bool made = false;
    if (!made) {
        row.createSprite(240, UI_ROW_H);
        row.loadFont(font_ru_small);   // Cyrillic-capable rows (SSID names, "раскрываю", etc.)
        made = true;
    }
    return row;
}

void uiSignalBars(TFT_eSprite& s, int x, int y, int rssi, uint16_t color) {
    int bars = rssi > -55 ? 4 : rssi > -67 ? 3 : rssi > -78 ? 2 : rssi > -88 ? 1 : 0;
    uint16_t off = tft.color565(0x33, 0x3a, 0x33);
    for (int b = 0; b < 4; b++) {
        int h = 4 + b * 3;
        s.fillRect(x + b * 5, y + 13 - h, 3, h, b < bars ? color : off);
    }
}
