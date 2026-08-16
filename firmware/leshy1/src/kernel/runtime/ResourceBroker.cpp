#include "ResourceBroker.h"

namespace leshy1::kernel::runtime {
namespace {

bool bitSet(ResourceMask mask, std::size_t bit) {
    return (mask & (1U << bit)) != 0;
}

}  // namespace

bool ResourceBroker::acquire(ResourceOwner owner, ResourceMask resources) {
    if (owner == kNoOwner || resources == 0 || (resources & ~kKnownResources) != 0) return false;
    for (std::size_t bit = 0; bit < owners_.size(); ++bit) {
        if (bitSet(resources, bit) && owners_[bit] != kNoOwner && owners_[bit] != owner) {
            return false;
        }
    }
    for (std::size_t bit = 0; bit < owners_.size(); ++bit) {
        if (bitSet(resources, bit)) owners_[bit] = owner;
    }
    return true;
}

void ResourceBroker::release(ResourceOwner owner, ResourceMask resources) {
    if (owner == kNoOwner) return;
    for (std::size_t bit = 0; bit < owners_.size(); ++bit) {
        if (bitSet(resources, bit) && owners_[bit] == owner) owners_[bit] = kNoOwner;
    }
}

void ResourceBroker::releaseAll(ResourceOwner owner) {
    if (owner == kNoOwner) return;
    for (ResourceOwner& current : owners_) {
        if (current == owner) current = kNoOwner;
    }
}

ResourceMask ResourceBroker::ownedBy(ResourceOwner owner) const {
    if (owner == kNoOwner) return 0;
    ResourceMask result = 0;
    for (std::size_t bit = 0; bit < owners_.size(); ++bit) {
        if (owners_[bit] == owner) result |= 1U << bit;
    }
    return result;
}

ResourceOwner ResourceBroker::ownerOf(Resource resource) const {
    const ResourceMask mask = resourceMask(resource);
    for (std::size_t bit = 0; bit < owners_.size(); ++bit) {
        if (bitSet(mask, bit)) return owners_[bit];
    }
    return kNoOwner;
}

}  // namespace leshy1::kernel::runtime
