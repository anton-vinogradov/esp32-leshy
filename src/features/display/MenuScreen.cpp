#include "MenuScreen.h"

#include "Display.h"

static const int CARD_TOP = 32;
static const int CARD_H   = 52;
static const int CARD_STEP = 54;
static const int CARD_X   = 6;
static const int CARD_W   = 228;

static int cardY(int i) { return CARD_TOP + i * CARD_STEP; }

void MenuScreen::card(int i, bool sel) {
    int y = cardY(i);
    uint16_t bg = sel ? tft.color565(0x24, 0x40, 0x2c) : tft.color565(0x18, 0x24, 0x1a);
    uint16_t bd = sel ? tft.color565(0xe7, 0xcf, 0x8f) : tft.color565(0x35, 0x4a, 0x38);
    uint16_t tc = sel ? tft.color565(0xff, 0xe6, 0xa8) : tft.color565(0xe8, 0xe8, 0xe0);
    uint16_t dc = tft.color565(0x9a, 0xac, 0x9a);

    tft.fillRoundRect(CARD_X, y, CARD_W, CARD_H, 6, bg);
    tft.drawRoundRect(CARD_X, y, CARD_W, CARD_H, 6, bd);
    if (sel) tft.drawRoundRect(CARD_X + 1, y + 1, CARD_W - 2, CARD_H - 2, 6, bd);

    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(tc, bg);
    tft.drawString(items_[i].title, CARD_X + 10, y + 6, 4);
    tft.setTextColor(dc, bg);
    tft.drawString(items_[i].desc, CARD_X + 10, y + 33, 2);
}

void MenuScreen::draw(int sel) {
    uiHeader("ESP32-Leshy", "menu");
    tft.fillRect(0, 28, 240, 320 - 28, uiBg());
    for (int i = 0; i < n_; i++) card(i, i == sel);
    uiFooter("UP/DN + SEL, or tap");
}

void MenuScreen::repaint(int prev, int cur) {
    if (prev >= 0 && prev < n_) card(prev, false);
    if (cur  >= 0 && cur  < n_) card(cur, true);
}

int MenuScreen::hitTest(int x, int y) {
    for (int i = 0; i < n_; i++) {
        int cy = cardY(i);
        if (x >= CARD_X && x <= CARD_X + CARD_W && y >= cy && y <= cy + CARD_H) return i;
    }
    return -1;
}
