#pragma once

#include <TFT_eSPI.h>

// One shared display for the whole app. Call displayInit() once at startup.
extern TFT_eSPI tft;
void displayInit();

// Shared UI helpers (colors computed via tft.color565 at call time).
uint16_t uiBg();
uint16_t uiRssiColor(int rssi);
void uiHeader(const char* title, const char* right);   // top bar
void uiFooter(const char* hint);                        // bottom hint line
void uiSignalBars(int x, int y, int rssi, uint16_t color);
