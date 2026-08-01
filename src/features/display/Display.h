#pragma once

#include <TFT_eSPI.h>

// One shared display for the whole app. Call displayInit() once at startup.
extern TFT_eSPI tft;
void displayInit();
