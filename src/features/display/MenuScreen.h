#pragma once

#include <Arduino.h>

struct MenuItem {
    const char* title;
    const char* desc;
};

// MenuScreen — the home screen: a list of feature cards (title + one-line
// explanation). Selectable by keypad (highlight + activate) or by touch.
class MenuScreen {
public:
    void begin(const MenuItem* items, int n) { items_ = items; n_ = n; }
    void draw(int sel);              // full render with `sel` highlighted
    void repaint(int prev, int cur); // repaint just the two changed cards
    int  hitTest(int x, int y);      // card index at (x,y), or -1
    int  count() const { return n_; }

private:
    const MenuItem* items_ = nullptr;
    int n_ = 0;
    void card(int i, bool selected);
};
