#pragma once

#include <Arduino.h>

// Minimal bilingual (EN / RU) support for the whole app. Strings live next to
// their use as tr("english", "русский") — no key registry to keep in sync. A
// single global current language; the menu (Phase 0) and the captive portal
// both flip it via i18n::set().
enum class Lang : uint8_t { EN, RU };

namespace i18n {

inline Lang& _slot() {
    static Lang lang = Lang::EN;   // international default; UI/menu may switch to RU
    return lang;
}

inline Lang current() { return _slot(); }
inline void set(Lang l) { _slot() = l; }
inline bool isRu() { return current() == Lang::RU; }

// Pick the string for the current language.
inline const char* tr(const char* en, const char* ru) { return isRu() ? ru : en; }

// BCP-47-ish code for <html lang="..">.
inline const char* code() { return isRu() ? "ru" : "en"; }

}  // namespace i18n
