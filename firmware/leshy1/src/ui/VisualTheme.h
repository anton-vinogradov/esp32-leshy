#pragma once

#include <cstdint>

#include "ui/InterfaceSettingsController.h"

namespace leshy1::ui::visual {

constexpr std::uint16_t rgb565(std::uint8_t red, std::uint8_t green,
                               std::uint8_t blue) {
    return static_cast<std::uint16_t>(
        ((static_cast<std::uint16_t>(red) & 0xF8U) << 8U) |
        ((static_cast<std::uint16_t>(green) & 0xFCU) << 3U) |
        (static_cast<std::uint16_t>(blue) >> 3U));
}

// UX-03 semantic color roles. Screens consume roles rather than raw colors so a
// state remains consistent across Home, Survey, Library, and Diagnostics.
struct Palette final {
    static inline std::uint16_t Canvas = rgb565(7, 16, 12);
    static inline std::uint16_t Header = rgb565(26, 58, 40);
    static inline std::uint16_t Surface = rgb565(13, 22, 17);
    static inline std::uint16_t SurfaceFocus = rgb565(26, 78, 52);
    static inline std::uint16_t SurfaceFocusDisabled = rgb565(66, 78, 52);
    static inline std::uint16_t Divider = rgb565(60, 72, 64);

    static inline std::uint16_t TextPrimary = rgb565(231, 207, 143);
    static inline std::uint16_t TextSecondary = rgb565(198, 208, 200);
    static inline std::uint16_t TextMuted = rgb565(104, 117, 107);
    static inline std::uint16_t Focus = rgb565(245, 197, 66);
    static inline std::uint16_t Positive = rgb565(85, 217, 138);
    static inline std::uint16_t Warning = rgb565(247, 166, 65);
    static inline std::uint16_t Danger = rgb565(240, 93, 94);
};

inline void applyTheme(InterfaceTheme theme) {
    if (theme == InterfaceTheme::HighContrast) {
        Palette::Canvas = rgb565(0, 0, 0);
        Palette::Header = rgb565(18, 18, 18);
        Palette::Surface = rgb565(8, 8, 8);
        Palette::SurfaceFocus = rgb565(62, 52, 0);
        Palette::SurfaceFocusDisabled = rgb565(52, 52, 52);
        Palette::Divider = rgb565(150, 150, 150);
        Palette::TextPrimary = rgb565(255, 255, 255);
        Palette::TextSecondary = rgb565(220, 220, 220);
        Palette::TextMuted = rgb565(145, 145, 145);
        Palette::Focus = rgb565(255, 224, 48);
        Palette::Positive = rgb565(72, 255, 150);
        Palette::Warning = rgb565(255, 178, 48);
        Palette::Danger = rgb565(255, 92, 92);
        return;
    }
    Palette::Canvas = rgb565(7, 16, 12);
    Palette::Header = rgb565(26, 58, 40);
    Palette::Surface = rgb565(13, 22, 17);
    Palette::SurfaceFocus = rgb565(26, 78, 52);
    Palette::SurfaceFocusDisabled = rgb565(66, 78, 52);
    Palette::Divider = rgb565(60, 72, 64);
    Palette::TextPrimary = rgb565(231, 207, 143);
    Palette::TextSecondary = rgb565(198, 208, 200);
    Palette::TextMuted = rgb565(104, 117, 107);
    Palette::Focus = rgb565(245, 197, 66);
    Palette::Positive = rgb565(85, 217, 138);
    Palette::Warning = rgb565(247, 166, 65);
    Palette::Danger = rgb565(240, 93, 94);
}

// UX-03 240x320 geometry. The compact header carries truthful system status;
// the footer is reserved for physical-key hints and never shows diagnostics.
struct Layout final {
    static constexpr std::int16_t ScreenWidth = 240;
    static constexpr std::int16_t ScreenHeight = 320;
    static constexpr std::int16_t Edge = 12;
    static constexpr std::int16_t ContentWidth = 216;
    static constexpr std::int16_t HeaderHeight = 26;
    static constexpr std::int16_t TitleY = 5;
    static constexpr std::int16_t ContentTop = 32;
    static constexpr std::int16_t RowHeight = 40;
    static constexpr std::int16_t RowGap = 7;
    static constexpr std::int16_t HomeRowHeight = 60;
    static constexpr std::int16_t HomeRowGap = 5;
    static constexpr std::int16_t Radius = 4;
    static constexpr std::int16_t FooterDividerY = 293;
    static constexpr std::int16_t HintY = 294;
    static constexpr std::int16_t HintHeight = 26;
};

static_assert(Layout::Edge * 2 + Layout::ContentWidth == Layout::ScreenWidth,
              "content must fit the 240 px screen exactly");
static_assert(Layout::FooterDividerY > Layout::ContentTop,
              "footer must remain below product content");
static_assert(Layout::ContentTop + 4 * Layout::HomeRowHeight +
                  3 * Layout::HomeRowGap < Layout::FooterDividerY,
              "four touch-sized Home rows must fit above the footer");
static_assert(Layout::HintY < Layout::ScreenHeight,
              "button hint must remain visible");
static_assert(Layout::HintY + Layout::HintHeight == Layout::ScreenHeight,
              "button hint must terminate at the screen edge");

}  // namespace leshy1::ui::visual
