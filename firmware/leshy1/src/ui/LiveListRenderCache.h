#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace leshy1::ui {

// Retained-mode contract for live, sorted lists.  A catalog revision is not a
// rendering instruction: the renderer compares the final visible model and
// touches only slots whose pixels actually changed.
enum class LiveListRowChange : std::uint8_t {
    None,
    DynamicFields,
    Replace,
    Clear,
};

enum class LiveListSceneState : std::uint8_t {
    Unknown,
    Rows,
    Searching,
    Unavailable,
};

template <typename Visual, std::size_t Capacity>
class LiveListRenderCache final {
  public:
    static constexpr std::size_t capacity() { return Capacity; }

    void reset() {
        rows_ = {};
        valid_ = {};
        state_ = LiveListSceneState::Unknown;
    }

    bool valid(std::size_t slot) const {
        return slot < Capacity && valid_[slot];
    }

    const Visual& row(std::size_t slot) const { return rows_[slot]; }

    LiveListRowChange classify(std::size_t slot,
                               const Visual& next) const {
        if (slot >= Capacity) return LiveListRowChange::None;
        if (!valid_[slot]) {
            return next.present ? LiveListRowChange::Replace
                                : LiveListRowChange::None;
        }
        const Visual& previous = rows_[slot];
        if (previous == next) return LiveListRowChange::None;
        if (!next.present) {
            return previous.present ? LiveListRowChange::Clear
                                    : LiveListRowChange::None;
        }
        if (previous.present && previous.sameIdentity(next) &&
            previous.staticFieldsEqual(next)) {
            return LiveListRowChange::DynamicFields;
        }
        return LiveListRowChange::Replace;
    }

    void publish(std::size_t slot, const Visual& visual) {
        if (slot >= Capacity) return;
        rows_[slot] = visual;
        valid_[slot] = true;
    }

    LiveListSceneState state() const { return state_; }
    void setState(LiveListSceneState state) { state_ = state; }

  private:
    std::array<Visual, Capacity> rows_{};
    std::array<bool, Capacity> valid_{};
    LiveListSceneState state_ = LiveListSceneState::Unknown;
};

}  // namespace leshy1::ui
