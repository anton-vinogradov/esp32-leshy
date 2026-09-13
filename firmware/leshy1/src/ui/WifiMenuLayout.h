#pragma once
#include <cstdint>

namespace leshy1::ui {
// Stable task IDs 0..4 keep task exit paths intact; the fourth root row is a
// container, not an implicit start. In its child, IDs 3/4 mean Visit/Anomalies.
struct WifiMenuWindow final {
    std::uint8_t first;
    std::uint8_t end;
    constexpr std::uint8_t count() const {
        return static_cast<std::uint8_t>(end - first);
    }
    constexpr bool contains(std::uint8_t id) const {
        return id >= first && id < end;
    }
};
constexpr WifiMenuWindow wifiMenuWindow(bool observationMenu) {
    return observationMenu ? WifiMenuWindow{3, 5} : WifiMenuWindow{0, 4};
}
}  // namespace leshy1::ui
