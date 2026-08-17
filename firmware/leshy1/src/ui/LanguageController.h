#pragma once

#include <cstdint>

#include "ui/UiStrings.h"

namespace leshy1::ui {

class LanguageController final {
public:
    void restore(UiLanguage language);
    void enter();
    bool previous();
    bool next();
    bool apply();

    UiLanguage active() const { return active_; }
    UiLanguage selected() const;
    std::uint8_t selection() const { return selection_; }

private:
    UiLanguage active_ = UiLanguage::English;
    std::uint8_t selection_ = 0;
};

}  // namespace leshy1::ui
