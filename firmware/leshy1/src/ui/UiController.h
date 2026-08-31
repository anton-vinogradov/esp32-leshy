#pragma once

#include <cstdint>

namespace leshy1::ui {

enum class UiAction : std::uint8_t {
    Up,
    Down,
    Left,
    Right,
    Select,
    Back,
    Unknown,
};

// Small, allocation-free navigation model used by both physical and diagnostic
// input. Product screens can replace the probe pages without changing the input
// or HIL contracts.
class UiController final {
public:
    static constexpr std::uint8_t kRootPage = 0;

    bool apply(UiAction action, std::uint8_t itemCount, bool selectedOpenable,
               std::uint8_t selectedPage = kRootPage);
    bool openChild(std::uint8_t page);
    bool returnToRoot();
    void recordHandledAction(UiAction action);

    std::uint8_t page() const { return page_; }
    std::uint8_t parentPage() const { return parentPage_; }
    std::uint8_t selection() const { return selection_; }
    std::uint32_t revision() const { return revision_; }
    bool isRoot() const { return page_ == kRootPage; }

private:
    std::uint8_t page_ = kRootPage;
    std::uint8_t parentPage_ = kRootPage;
    std::uint8_t selection_ = 0;
    std::uint32_t revision_ = 0;
};

UiAction uiActionFromName(const char* value);
const char* uiActionName(UiAction action);
const char* probePageName(std::uint8_t page);

}  // namespace leshy1::ui
