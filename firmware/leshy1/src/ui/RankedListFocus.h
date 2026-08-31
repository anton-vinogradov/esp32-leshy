#pragma once

#include <cstddef>

namespace leshy1::ui {

// A live strongest-first list owns its cursor until the first user action.
// While automatic, row zero always means "the current strongest item" even
// when identities reorder. After claimByUser(), automatic row-zero selection
// stops; callers may keep the selected identity while sorting remains live.
class RankedListFocus final {
public:
    void reset() { userOwned_ = false; }

    void claimByUser() { userOwned_ = true; }

    bool userOwned() const { return userOwned_; }

    void reconcile(std::size_t visibleSize, std::size_t* selection) const {
        if (selection == nullptr) return;
        if (visibleSize == 0U || !userOwned_) {
            *selection = 0U;
            return;
        }
        if (*selection >= visibleSize) *selection = visibleSize - 1U;
    }

private:
    bool userOwned_ = false;
};

}  // namespace leshy1::ui
