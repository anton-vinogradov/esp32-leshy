#include "MenuScreen.h"

#include "Display.h"
#include "Fonts.h"
#include "../../core/i18n.h"

static const int CARD_TOP  = 32;
static const int CARD_H    = 52;
static const int CARD_STEP = 54;
static const int CARD_X    = 6;
static const int CARD_W    = 228;

static const int TEXT_X   = CARD_X + 10;
static const int TEXT_MAXW = CARD_W - 16;      // usable text width inside a card

static const int VISIBLE = 5;                       // cards that fit above the footer
static int s_off = 0;                               // shared with cardY (slot = i - off)
static int cardY(int i) { return CARD_TOP + (i - s_off) * CARD_STEP; }
static const char* T(const char* en, const char* ru) { return (i18n::isRu() && ru && ru[0]) ? ru : en; }

// Truncate a UTF-8 string with "..." so it fits maxW at the currently loaded
// font. Steps whole codepoints so multi-byte (Cyrillic) chars are never split.
static String fit(const char* s, int maxW) {
    if (tft.textWidth(s) <= maxW) return String(s);
    String out;
    for (const char* p = s; *p; ) {
        int len = 1;                                   // UTF-8 sequence length
        uint8_t c = (uint8_t)*p;
        if      (c >= 0xF0) len = 4;
        else if (c >= 0xE0) len = 3;
        else if (c >= 0xC0) len = 2;
        String cand = out;
        for (int k = 0; k < len && p[k]; k++) cand += p[k];
        if (tft.textWidth(cand + "...") > maxW) break;
        out = cand;
        p += len;
    }
    return out + "...";
}

void MenuScreen::bg_(int i, bool sel) {
    int y = cardY(i);
    uint16_t bg = sel ? tft.color565(0x24, 0x40, 0x2c) : tft.color565(0x18, 0x24, 0x1a);
    uint16_t bd = sel ? tft.color565(0xe7, 0xcf, 0x8f) : tft.color565(0x35, 0x4a, 0x38);
    tft.fillRoundRect(CARD_X, y, CARD_W, CARD_H, 6, bg);
    tft.drawRoundRect(CARD_X, y, CARD_W, CARD_H, 6, bd);
    if (sel) tft.drawRoundRect(CARD_X + 1, y + 1, CARD_W - 2, CARD_H - 2, 6, bd);
}

void MenuScreen::title_(int i, bool sel) {
    int y = cardY(i);
    uint16_t bg = sel ? tft.color565(0x24, 0x40, 0x2c) : tft.color565(0x18, 0x24, 0x1a);
    uint16_t tc = sel ? tft.color565(0xff, 0xe6, 0xa8) : tft.color565(0xe8, 0xe8, 0xe0);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(tc, bg);
    tft.drawString(fit(T(m_->items[i].en, m_->items[i].ru), TEXT_MAXW), TEXT_X, y + 6);
}

void MenuScreen::desc_(int i, bool sel) {
    const char* d = T(m_->items[i].enDesc, m_->items[i].ruDesc);
    if (!d || !d[0]) return;
    int y = cardY(i);
    uint16_t bg = sel ? tft.color565(0x24, 0x40, 0x2c) : tft.color565(0x18, 0x24, 0x1a);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(tft.color565(0x9a, 0xac, 0x9a), bg);
    tft.drawString(fit(d, TEXT_MAXW), TEXT_X, y + 30);
}

void MenuScreen::redraw_(int sel) {                 // full paint of the visible window
    uiHeaderRu(T(m_->en, m_->ru));
    tft.fillRect(0, 28, 240, 320 - 28, uiBg());
    int last = off_ + VISIBLE; if (last > m_->n) last = m_->n;
    for (int i = off_; i < last; i++) bg_(i, i == sel);
    fontBig();   for (int i = off_; i < last; i++) title_(i, i == sel);
    fontSmall(); for (int i = off_; i < last; i++) desc_(i, i == sel);
    bool more = (m_->n > off_ + VISIBLE);           // hint that the list continues
    uiFooterRu(canBack_ ? (i18n::isRu() ? "◀ назад" : "◀ back") : "",
               more ? (i18n::isRu() ? "ниже ▼" : "more ▼") : (i18n::isRu() ? "выбрать ▶" : "open ▶"));
    fontOff();
}

void MenuScreen::show(const Menu* m, int sel, bool canBack) {
    m_ = m; canBack_ = canBack;
    off_ = 0;
    if (sel >= VISIBLE) off_ = sel - VISIBLE + 1;   // open with the selection visible
    s_off = off_;
    redraw_(sel);
}

void MenuScreen::repaint(int prev, int cur) {
    if (!m_) return;
    int want = off_;                                 // scroll only when the selection leaves the window
    if (cur < off_) want = cur;
    else if (cur >= off_ + VISIBLE) want = cur - VISIBLE + 1;
    if (want != off_) { off_ = want; s_off = off_; redraw_(cur); return; }

    bool pv = (prev >= off_ && prev < off_ + VISIBLE && prev >= 0 && prev < m_->n);
    bool cv = (cur  >= off_ && cur  < off_ + VISIBLE && cur  >= 0 && cur  < m_->n);
    if (pv) bg_(prev, false);
    if (cv) bg_(cur, true);
    fontBig();
    if (pv) title_(prev, false);
    if (cv) title_(cur, true);
    fontSmall();
    if (pv) desc_(prev, false);
    if (cv) desc_(cur, true);
    fontOff();
}

int MenuScreen::hitTest(int x, int y) {
    if (!m_) return -1;
    int last = off_ + VISIBLE; if (last > m_->n) last = m_->n;
    for (int i = off_; i < last; i++) {
        int cy = cardY(i);
        if (x >= CARD_X && x <= CARD_X + CARD_W && y >= cy && y <= cy + CARD_H) return i;
    }
    return -1;
}
