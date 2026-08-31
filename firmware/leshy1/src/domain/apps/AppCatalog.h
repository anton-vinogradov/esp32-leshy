#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/hardware/HardwareInventory.h"
#include "kernel/runtime/Resources.h"

namespace leshy1::domain::apps {

// Home stays flat for one-tap access, but every route still carries its
// conceptual place and presentation semantics.  Consumers must not infer a
// warning from a string id: the same metadata is reused by touch, rendering,
// automation and future contextual deep links.
enum class AppSection : std::uint8_t {
    Nearby,
    Air,
    Evidence,
    Controlled,
    Service,
};

enum class AppPresentation : std::uint8_t {
    Standard,
    Controlled,
    Service,
};

struct AppMenuItem final {
    const char* id = nullptr;
    const char* label = nullptr;
    const char* reason = nullptr;
    std::uint8_t page = 0;
    bool enabled = false;
    bool simulated = false;
    kernel::runtime::ResourceMask resources = 0;
    AppSection section = AppSection::Nearby;
    AppPresentation presentation = AppPresentation::Standard;
};

class AppCatalog final {
public:
    static constexpr std::size_t kCapacity = 9;

    void rebuild(const hardware::HardwareInventory& inventory,
                 bool targetsMergeFixture = false);
    const AppMenuItem* get(std::size_t index) const;
    std::size_t size() const { return size_; }

private:
    std::array<AppMenuItem, kCapacity> items_{};
    std::size_t size_ = 0;
};

}  // namespace leshy1::domain::apps
