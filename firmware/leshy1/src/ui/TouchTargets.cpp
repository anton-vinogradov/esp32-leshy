#include "ui/TouchTargets.h"

#include "ui/UiComponents.h"

namespace leshy1::ui {

TouchTarget hitTouchTarget(TouchTargetLayout layout, TouchPoint point,
                           std::uint8_t firstVisible,
                           std::uint8_t itemCount) {
    using visual::Components;
    using visual::containsPoint;

    std::uint8_t rows = 0;
    bool home = false;
    switch (layout) {
        case TouchTargetLayout::HomeRows:
            rows = 4;
            home = true;
            break;
        case TouchTargetLayout::TwoChoices: rows = 2; break;
        case TouchTargetLayout::ThreeChoices: rows = 3; break;
        case TouchTargetLayout::None: return {};
    }

    for (std::uint8_t row = 0; row < rows; ++row) {
        const visual::Rect bounds =
            home ? Components::homeRow(row) : Components::choiceRow(row);
        if (!containsPoint(bounds, static_cast<std::int16_t>(point.x),
                           static_cast<std::int16_t>(point.y))) {
            continue;
        }
        const std::uint8_t index = home
            ? static_cast<std::uint8_t>(firstVisible + row) : row;
        if (itemCount != 0 && index >= itemCount) return {};
        return {true, index};
    }
    return {};
}

}  // namespace leshy1::ui
