#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/hardware/HardwareInventory.h"
#include "kernel/runtime/Resources.h"

namespace leshy1::domain::apps {

struct AppMenuItem final {
    const char* id = nullptr;
    const char* label = nullptr;
    const char* reason = nullptr;
    std::uint8_t page = 0;
    bool enabled = false;
    bool simulated = false;
    kernel::runtime::ResourceMask resources = 0;
};

class AppCatalog final {
public:
    static constexpr std::size_t kCapacity = 5;

    void rebuild(const hardware::HardwareInventory& inventory);
    const AppMenuItem* get(std::size_t index) const;
    std::size_t size() const { return size_; }

private:
    std::array<AppMenuItem, kCapacity> items_{};
    std::size_t size_ = 0;
};

}  // namespace leshy1::domain::apps
