#pragma once

#include <Arduino.h>

// Cyrillic smooth fonts (TFT_eSPI .vlw, generated from Verdana). Only one smooth
// font can be loaded at a time, so call fontBig()/fontSmall() around localized
// text and fontOff() before drawing with the built-in numbered fonts again.
void fontBig();
void fontSmall();
void fontTiny();
void fontOff();

// Localized top bar / bottom hint drawn with the smooth font (Cyrillic-capable).
// Header `right` (optional) is a small right-aligned label, e.g. a live count.
// Footer: `left` hint hugs the left edge, `right` hint (optional) the right edge —
//   e.g. uiFooterRu("◀ назад", "опции ▶").
void uiHeaderRu(const char* title, const char* right = nullptr);
void uiFooterRu(const char* left, const char* right = nullptr);
