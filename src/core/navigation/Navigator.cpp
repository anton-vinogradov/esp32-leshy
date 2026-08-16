#include "Navigator.h"

namespace leshy {
namespace navigation {

void Navigator::reset(uint8_t rootMenu) {
    depth_ = 0;
    frames_[0].menu = rootMenu;
    frames_[0].selection = 0;
}

bool Navigator::push(uint8_t menu) {
    if (depth_ + 1 >= kMaxDepth) return false;
    ++depth_;
    frames_[depth_].menu = menu;
    frames_[depth_].selection = 0;
    return true;
}

bool Navigator::pop() {
    if (!canGoBack()) return false;
    --depth_;
    return true;
}

bool Navigator::setSelection(int selection, int itemCount) {
    if (selection < 0 || selection >= itemCount || selection > UINT8_MAX) return false;
    frames_[depth_].selection = static_cast<uint8_t>(selection);
    return true;
}

bool Navigator::moveSelection(int delta, int itemCount, uint8_t* previous) {
    if (itemCount <= 0) return false;
    const int before = selection();
    const int after = before + delta;
    if (after < 0 || after >= itemCount || after > UINT8_MAX) return false;
    if (previous) *previous = static_cast<uint8_t>(before);
    frames_[depth_].selection = static_cast<uint8_t>(after);
    return after != before;
}

void Navigator::clampSelection(int itemCount) {
    if (itemCount <= 0) {
        frames_[depth_].selection = 0;
        return;
    }
    if (selection() >= itemCount) frames_[depth_].selection = static_cast<uint8_t>(itemCount - 1);
}

}  // namespace navigation
}  // namespace leshy
