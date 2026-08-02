#pragma once

#include <TFT_eSPI.h>

// One shared display for the whole app. Call displayInit() once at startup.
extern TFT_eSPI tft;
void displayInit();

// List geometry shared by the on-screen scanners.
static const int UI_LIST_TOP = 30;
static const int UI_ROW_H    = 24;
static const int UI_VISIBLE  = 11;   // list runs 30..294, right up to the footer band

// Shared UI helpers (colors computed via tft.color565 at call time).
uint16_t uiBg();
uint16_t uiRssiColor(int rssi);
void uiHeader(const char* title, const char* right);   // top bar
void uiFooter(const char* hint);                        // bottom hint line

// TFT backlight (PWM on the ESP32-DIV v2 backlight pin). Default is full — matching
// how the board looked before this was adjustable — and the user can dim it down.
void    uiBacklightBegin();     // attach PWM and apply the saved level
uint8_t uiBacklightCycle();     // 100% -> 69% -> 44% -> 25% -> 9% -> wrap; persists; returns the 0..255 duty
uint8_t uiBacklightLevel();     // current 0..255 duty

// A reusable off-screen row sprite (240 x UI_ROW_H) — draw a list row into it
// and pushSprite() it so rows update without flicker.
TFT_eSprite& uiRow();
void uiSignalBars(TFT_eSprite& s, int x, int y, int rssi, uint16_t color);
