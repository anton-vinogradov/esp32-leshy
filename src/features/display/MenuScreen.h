#pragma once

#include <Arduino.h>

// A menu item: a card with a title + one-line description. `kind` says whether
// it opens a submenu or launches a feature; `target` is the submenu index or
// feature id (interpreted by the caller).
struct MenuItem {
    const char* title;
    const char* desc;
    uint8_t     kind;      // 0 = submenu, 1 = feature
    uint8_t     target;
};

struct Menu {
    const char*     title;
    const MenuItem* items;
    uint8_t         n;
};

// MenuScreen — renders one Menu (feature cards). Selectable by keypad or touch.
class MenuScreen {
public:
    void show(const Menu* m, int sel);   // store menu + full render
    void repaint(int prev, int cur);     // repaint just the two changed cards
    int  hitTest(int x, int y);          // card index at (x,y), or -1
    int  count() const { return m_ ? m_->n : 0; }

private:
    const Menu* m_ = nullptr;
    void card(int i, bool selected);
};
