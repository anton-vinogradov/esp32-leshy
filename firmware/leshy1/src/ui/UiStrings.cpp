#include "UiStrings.h"

#include <cstring>

namespace leshy1::ui {
namespace {

constexpr std::array<UiTextSpec, kUiTextCount> kCatalog = {{
#define LESHY_UI_TEXT(id, role, maximum, english, russian) \
    {UiTextRole::role, maximum, english, russian},
#include "ui/UiStrings.def"
#undef LESHY_UI_TEXT
}};

constexpr UiTextSpec kInvalid = {UiTextRole::Body, 0, "", ""};

}  // namespace

const UiTextSpec& uiTextSpec(UiTextId id) {
    const std::size_t index = static_cast<std::size_t>(id);
    return index < kCatalog.size() ? kCatalog[index] : kInvalid;
}

const char* uiText(UiLanguage language, UiTextId id) {
    const UiTextSpec& spec = uiTextSpec(id);
    return language == UiLanguage::Russian ? spec.russian : spec.english;
}

const char* uiLanguageName(UiLanguage language) {
    return language == UiLanguage::Russian ? "ru" : "en";
}

bool uiLanguageFromName(const char* value, UiLanguage* language) {
    if (value == nullptr || language == nullptr) return false;
    if (std::strcmp(value, "en") == 0) {
        *language = UiLanguage::English;
        return true;
    }
    if (std::strcmp(value, "ru") == 0) {
        *language = UiLanguage::Russian;
        return true;
    }
    return false;
}

}  // namespace leshy1::ui
