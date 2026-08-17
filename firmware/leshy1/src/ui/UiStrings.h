#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace leshy1::ui {

enum class UiLanguage : std::uint8_t {
    English = 0,
    Russian = 1,
};

enum class UiTextRole : std::uint8_t {
    Body,
    Meta,
};

enum class UiTextId : std::uint16_t {
#define LESHY_UI_TEXT(id, role, maximum, english, russian) id,
#include "ui/UiStrings.def"
#undef LESHY_UI_TEXT
    Count,
};

struct UiTextSpec final {
    UiTextRole role = UiTextRole::Body;
    std::uint16_t maximumPixels = 0;
    const char* english = nullptr;
    const char* russian = nullptr;
};

constexpr std::size_t kUiTextCount = static_cast<std::size_t>(UiTextId::Count);

const UiTextSpec& uiTextSpec(UiTextId id);
const char* uiText(UiLanguage language, UiTextId id);
const char* uiLanguageName(UiLanguage language);
bool uiLanguageFromName(const char* value, UiLanguage* language);

}  // namespace leshy1::ui
