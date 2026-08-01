#include "Fonts.h"

#include "Display.h"
#include "font_ru_big.h"
#include "font_ru_small.h"

static int s_loaded = 0;   // 0 none, 1 big, 2 small

void fontBig()   { if (s_loaded != 1) { tft.loadFont(font_ru_big);   s_loaded = 1; } }
void fontSmall() { if (s_loaded != 2) { tft.loadFont(font_ru_small); s_loaded = 2; } }
void fontOff()   { if (s_loaded)      { tft.unloadFont();            s_loaded = 0; } }

void uiHeaderRu(const char* title, const char* right) {
    const uint16_t hdr  = tft.color565(0x1e, 0x3a, 0x28);
    const uint16_t gold = tft.color565(0xe7, 0xcf, 0x8f);
    tft.fillRect(0, 0, 240, 28, hdr);
    fontBig();
    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(gold, hdr);
    tft.drawString(title, 6, 15);
    if (right && right[0]) {
        fontSmall();
        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(gold, hdr);
        tft.drawString(right, 234, 14);
    }
}

void uiFooterRu(const char* hint) {
    const uint16_t bg  = uiBg();
    const uint16_t dim = tft.color565(0x9a, 0xaa, 0x9a);   // brighter hint
    tft.fillRect(0, 288, 240, 32, bg);                     // raised well clear of the panel's hidden bottom edge
    fontSmall();
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(dim, bg);
    tft.drawString(hint, 120, 301);
}
