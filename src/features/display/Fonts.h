#pragma once

#include <Arduino.h>

// Cyrillic smooth fonts (TFT_eSPI .vlw, generated from Verdana). Only one smooth
// font can be loaded at a time, so call fontBig()/fontSmall() around localized
// text and fontOff() before drawing with the built-in numbered fonts again.
void fontBig();
void fontSmall();
void fontOff();

// Localized top bar / bottom hint drawn with the smooth font (Cyrillic-capable).
void uiHeaderRu(const char* title);
void uiFooterRu(const char* hint);
