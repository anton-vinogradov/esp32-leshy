#pragma once

#include <stddef.h>
#include <stdint.h>

#include "Resources.h"

namespace leshy {
namespace runtime {

using OwnerId = uint16_t;
constexpr OwnerId kNoOwner = 0;

struct ResourceConflict {
    Resource resource = Resource::Count;
    OwnerId owner = kNoOwner;
};

// Fixed-size, allocation-free resource arbitration. Acquisition is atomic: if
// one requested resource is busy, none of the free resources are claimed.
class ResourceBroker {
public:
    bool tryAcquire(OwnerId owner, ResourceSet requested, ResourceConflict* conflict = nullptr);
    void release(OwnerId owner, ResourceSet resources);
    void releaseAll(OwnerId owner);

    OwnerId ownerOf(Resource resource) const;
    bool owns(OwnerId owner, ResourceSet resources) const;

private:
    static constexpr size_t kResourceCount = static_cast<size_t>(Resource::Count);
    OwnerId owners_[kResourceCount] = {};
};

}  // namespace runtime
}  // namespace leshy
