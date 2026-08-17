#include "LanguageController.h"

namespace leshy1::ui {

void LanguageController::restore(UiLanguage language) {
    active_ = language;
    selection_ = language == UiLanguage::Russian ? 1U : 0U;
}

void LanguageController::enter() {
    selection_ = active_ == UiLanguage::Russian ? 1U : 0U;
}

bool LanguageController::previous() {
    if (selection_ == 0) return false;
    --selection_;
    return true;
}

bool LanguageController::next() {
    if (selection_ >= 1) return false;
    ++selection_;
    return true;
}

bool LanguageController::apply() {
    const UiLanguage nextLanguage = selected();
    if (nextLanguage == active_) return false;
    active_ = nextLanguage;
    return true;
}

UiLanguage LanguageController::selected() const {
    return selection_ == 1 ? UiLanguage::Russian : UiLanguage::English;
}

}  // namespace leshy1::ui
