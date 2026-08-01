#pragma once

#include <Arduino.h>

// Resistive touch (XPT2046 via TFT_eSPI). Calibration is stored in NVS: the
// first run calibrates (tap the arrows) and saves it; later boots just load it,
// so it survives reflashes.
void touchBegin();
void touchRecalibrate();                  // force re-calibration and save (Settings)
bool touchGet(uint16_t& x, uint16_t& y);
