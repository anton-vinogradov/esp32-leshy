#pragma once

#include <cstdint>

namespace leshy1::kernel::runtime {

using ResourceMask = std::uint32_t;

enum class Resource : ResourceMask {
    UiForeground = 1U << 0U,
    EspRf = 1U << 1U,
    Storage = 1U << 2U,
    RadioSpi = 1U << 3U,
    DisplaySpi = 1U << 4U,
    Console = 1U << 5U,
    Mux56 = 1U << 6U,
};

constexpr ResourceMask resourceMask(Resource resource) {
    return static_cast<ResourceMask>(resource);
}

constexpr ResourceMask operator|(Resource left, Resource right) {
    return resourceMask(left) | resourceMask(right);
}

constexpr ResourceMask kKnownResources =
    resourceMask(Resource::UiForeground) | resourceMask(Resource::EspRf) |
    resourceMask(Resource::Storage) | resourceMask(Resource::RadioSpi) |
    resourceMask(Resource::DisplaySpi) | resourceMask(Resource::Console) |
    resourceMask(Resource::Mux56);

}  // namespace leshy1::kernel::runtime
