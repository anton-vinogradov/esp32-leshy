#pragma once

#include <cstdint>

#include "ui/VisualTheme.h"

namespace leshy1::ui::visual {

// UX-04 component geometry. The platform renderer consumes these rectangles;
// product screens select components and content but do not invent coordinates.
struct Rect final {
    std::int16_t x = 0;
    std::int16_t y = 0;
    std::int16_t width = 0;
    std::int16_t height = 0;
};

enum class Tone : std::uint8_t {
    Neutral,
    Focus,
    Positive,
    Warning,
    Danger,
    Muted,
};

struct Components final {
    static constexpr std::int16_t ChoiceTop = 42;
    static constexpr std::int16_t ChoiceHeight = 52;
    static constexpr std::int16_t ChoiceGap = 6;
    static constexpr std::int16_t MetricTop = 46;
    static constexpr std::int16_t MetricHeight = 28;
    static constexpr std::int16_t MetricGap = 0;
    static constexpr std::int16_t NavigationGap = 0;
    static constexpr std::int16_t NavigationWidth = 80;

    static constexpr Rect header() {
        return {0, 0, Layout::ScreenWidth, Layout::HeaderHeight};
    }

    static constexpr Rect title() {
        return {10, Layout::TitleY, 126, 15};
    }

    static constexpr Rect homeRow(std::uint8_t index) {
        return {
            Layout::Edge,
            static_cast<std::int16_t>(
                Layout::ContentTop +
                static_cast<std::int16_t>(index) *
                    (Layout::HomeRowHeight + Layout::HomeRowGap)),
            Layout::ContentWidth,
            Layout::HomeRowHeight,
        };
    }

    static constexpr Rect choiceRow(std::uint8_t index) {
        return {
            Layout::Edge,
            static_cast<std::int16_t>(
                ChoiceTop + static_cast<std::int16_t>(index) *
                                (ChoiceHeight + ChoiceGap)),
            Layout::ContentWidth,
            ChoiceHeight,
        };
    }

    static constexpr Rect metricRow(std::uint8_t index) {
        return {
            Layout::Edge,
            static_cast<std::int16_t>(
                MetricTop + static_cast<std::int16_t>(index) *
                                (MetricHeight + MetricGap)),
            Layout::ContentWidth,
            MetricHeight,
        };
    }

    static constexpr Rect stateCard() {
        return {Layout::Edge, 58, Layout::ContentWidth, 112};
    }

    static constexpr Rect footerDivider() {
        return {0, Layout::FooterDividerY, Layout::ScreenWidth, 1};
    }

    static constexpr Rect footerHint() {
        return {0, Layout::HintY, Layout::ScreenWidth,
                Layout::HintHeight};
    }

    static constexpr Rect navigationCell(std::uint8_t index) {
        return {
            static_cast<std::int16_t>(
                static_cast<std::int16_t>(index) *
                    (NavigationWidth + NavigationGap)),
            Layout::HintY,
            NavigationWidth,
            Layout::HintHeight,
        };
    }

    // A selected row has a geometric cue in addition to palette changes. The
    // filled chevron and outline keep keyboard focus visible without color.
    static constexpr Rect focusMarker(Rect row) {
        return {static_cast<std::int16_t>(row.x + 3),
                static_cast<std::int16_t>(row.y + row.height / 2 - 4), 4, 8};
    }
};

constexpr bool insideScreen(Rect rect) {
    return rect.x >= 0 && rect.y >= 0 && rect.width >= 0 && rect.height >= 0 &&
           rect.x + rect.width <= Layout::ScreenWidth &&
           rect.y + rect.height <= Layout::ScreenHeight;
}

constexpr bool beforeFooter(Rect rect) {
    return insideScreen(rect) && rect.y + rect.height < Layout::FooterDividerY;
}

constexpr bool overlaps(Rect left, Rect right) {
    return left.x < right.x + right.width && left.x + left.width > right.x &&
           left.y < right.y + right.height && left.y + left.height > right.y;
}

constexpr bool contains(Rect outer, Rect inner) {
    return inner.x >= outer.x && inner.y >= outer.y &&
           inner.x + inner.width <= outer.x + outer.width &&
           inner.y + inner.height <= outer.y + outer.height;
}

constexpr bool containsPoint(Rect rect, std::int16_t x, std::int16_t y) {
    return x >= rect.x && y >= rect.y && x < rect.x + rect.width &&
           y < rect.y + rect.height;
}

static_assert(insideScreen(Components::header()), "header must fit the TFT");
static_assert(insideScreen(Components::title()), "title must fit the TFT");
static_assert(contains(Components::header(), Components::title()),
              "page title must live inside the information header");
static_assert(beforeFooter(Components::homeRow(3)),
              "four touch-sized Home rows must fit above the footer");
static_assert(beforeFooter(Components::choiceRow(2)),
              "three touch-sized choices must fit above the footer");
static_assert(beforeFooter(Components::metricRow(4)),
              "five result metrics must fit above the footer");
static_assert(beforeFooter(Components::stateCard()),
              "guided common-state card must fit above the footer");
static_assert(!overlaps(Components::homeRow(1), Components::homeRow(2)),
              "touch-sized Home rows must be visually separated");
static_assert(!overlaps(Components::choiceRow(1), Components::choiceRow(2)),
              "touch-sized choice rows must be visually separated");
static_assert(insideScreen(Components::navigationCell(0)) &&
                  insideScreen(Components::navigationCell(1)) &&
                  insideScreen(Components::navigationCell(2)),
              "navigation cells must fit the TFT");
static_assert(!overlaps(Components::navigationCell(0),
                        Components::navigationCell(1)) &&
                  !overlaps(Components::navigationCell(1),
                            Components::navigationCell(2)),
              "navigation cells must remain spatially distinct");
static_assert(Components::navigationCell(2).x +
                      Components::navigationCell(2).width ==
                  Layout::ScreenWidth,
              "navigation cells must span the content width");
static_assert(contains(Components::homeRow(0),
                       Components::focusMarker(Components::homeRow(0))),
              "non-color focus marker must fit its row");
static_assert(Layout::HomeRowHeight >= 44,
              "interactive Home rows require a finger-sized touch target");
static_assert(Components::ChoiceHeight >= 44,
              "interactive choice rows require a finger-sized touch target");

}  // namespace leshy1::ui::visual
