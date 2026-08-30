#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "Resources.h"

namespace leshy1::kernel::runtime {

using ResourceOwner = std::uint8_t;
constexpr ResourceOwner kNoOwner = 0;

class ResourceBroker final {
public:
    static constexpr std::size_t kResourceBits = 7;

    bool acquire(ResourceOwner owner, ResourceMask resources);
    void release(ResourceOwner owner, ResourceMask resources);
    void releaseAll(ResourceOwner owner);
    ResourceMask ownedBy(ResourceOwner owner) const;
    ResourceOwner ownerOf(Resource resource) const;

private:
    std::array<ResourceOwner, kResourceBits> owners_{};
};

}  // namespace leshy1::kernel::runtime
