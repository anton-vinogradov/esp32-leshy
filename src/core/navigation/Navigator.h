#pragma once

#include <stddef.h>
#include <stdint.h>

namespace leshy {
namespace navigation {

// Allocation-free menu stack. Keeping this independent of Arduino and the TFT
// makes every navigation edge testable on the host.
class Navigator {
public:
    static constexpr size_t kMaxDepth = 8;

    explicit Navigator(uint8_t rootMenu = 0) { reset(rootMenu); }

    void reset(uint8_t rootMenu = 0);
    bool push(uint8_t menu);
    bool pop();

    uint8_t menu() const { return frames_[depth_].menu; }
    uint8_t selection() const { return frames_[depth_].selection; }
    size_t depth() const { return depth_; }
    bool canGoBack() const { return depth_ > 0; }

    bool setSelection(int selection, int itemCount);
    bool moveSelection(int delta, int itemCount, uint8_t* previous = nullptr);
    void clampSelection(int itemCount);

private:
    struct Frame {
        uint8_t menu = 0;
        uint8_t selection = 0;
    };

    Frame frames_[kMaxDepth] = {};
    size_t depth_ = 0;
};

}  // namespace navigation
}  // namespace leshy
