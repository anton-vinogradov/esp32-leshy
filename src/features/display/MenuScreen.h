#pragma once

#include <Arduino.h>

// A menu item: card title + one-line description, in EN and RU. `kind` says
// whether it opens a submenu or launches a feature; `target` is the submenu
// index or feature id (interpreted by the caller).
struct MenuItem {
    const char* en;
    const char* enDesc;
    const char* ru;
    const char* ruDesc;
    uint8_t     kind;      // 0 = submenu, 1 = feature
    uint8_t     target;
};

struct Menu {
    const char*     en;
    const char*     ru;
    const MenuItem* items;
    uint8_t         n;
};

// MenuScreen — renders one Menu (feature cards) with the Cyrillic smooth font,
// localized to the current language. Selectable by keypad or touch.
class MenuScreen {
public:
    void show(const Menu* m, int sel);   // store menu + full render
    void repaint(int prev, int cur);     // repaint just the two changed cards
    int  hitTest(int x, int y);          // card index at (x,y), or -1
    int  count() const { return m_ ? m_->n : 0; }

private:
    const Menu* m_ = nullptr;
    void bg_(int i, bool sel);
    void title_(int i, bool sel);        // big font must be loaded
    void desc_(int i, bool sel);         // small font must be loaded
};
