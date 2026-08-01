#pragma once

#include <TFT_eSPI.h>

// One shared display for the whole app. Call displayInit() once at startup.
extern TFT_eSPI tft;
void displayInit();

// List geometry shared by the on-screen scanners.
static const int UI_LIST_TOP = 30;
static const int UI_ROW_H    = 24;
static const int UI_VISIBLE  = 11;

// Shared UI helpers (colors computed via tft.color565 at call time).
uint16_t uiBg();
uint16_t uiRssiColor(int rssi);
void uiHeader(const char* title, const char* right);   // top bar
void uiFooter(const char* hint);                        // bottom hint line

// A reusable off-screen row sprite (240 x UI_ROW_H) — draw a list row into it
// and pushSprite() it so rows update without flicker.
TFT_eSprite& uiRow();
void uiSignalBars(TFT_eSprite& s, int x, int y, int rssi, uint16_t color);
