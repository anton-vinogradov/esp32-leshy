#pragma once

#include <cstdint>

#include "ui/TouchInput.h"

namespace leshy1::ui {

enum class TouchTargetLayout : std::uint8_t {
    None,
    HomeRows,
    TwoChoices,
    ThreeChoices,
};

struct TouchTarget final {
    bool hit = false;
    std::uint8_t index = 0;
};

// Maps only visible product controls. Header, status and physical-key footer
// are deliberately absent from this model; in particular touch never creates
// a Back action.
TouchTarget hitTouchTarget(TouchTargetLayout layout, TouchPoint point,
                           std::uint8_t firstVisible = 0,
                           std::uint8_t itemCount = 0);

}  // namespace leshy1::ui
