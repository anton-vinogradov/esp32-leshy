#include "ResourceBroker.h"

namespace leshy {
namespace runtime {

bool ResourceBroker::tryAcquire(OwnerId owner, ResourceSet requested, ResourceConflict* conflict) {
    if (conflict) *conflict = {};
    if (owner == kNoOwner || !isValidResourceSet(requested)) return false;

    for (size_t i = 0; i < kResourceCount; ++i) {
        if (!(requested & (ResourceSet{1} << i))) continue;
        if (owners_[i] != kNoOwner && owners_[i] != owner) {
            if (conflict) {
                conflict->resource = static_cast<Resource>(i);
                conflict->owner = owners_[i];
            }
            return false;
        }
    }

    for (size_t i = 0; i < kResourceCount; ++i) {
        if (requested & (ResourceSet{1} << i)) owners_[i] = owner;
    }
    return true;
}

void ResourceBroker::release(OwnerId owner, ResourceSet resources) {
    if (owner == kNoOwner) return;
    for (size_t i = 0; i < kResourceCount; ++i) {
        if ((resources & (ResourceSet{1} << i)) && owners_[i] == owner) owners_[i] = kNoOwner;
    }
}

void ResourceBroker::releaseAll(OwnerId owner) {
    if (owner == kNoOwner) return;
    for (size_t i = 0; i < kResourceCount; ++i) {
        if (owners_[i] == owner) owners_[i] = kNoOwner;
    }
}

OwnerId ResourceBroker::ownerOf(Resource value) const {
    const size_t index = static_cast<size_t>(value);
    return index < kResourceCount ? owners_[index] : kNoOwner;
}

bool ResourceBroker::owns(OwnerId owner, ResourceSet resources) const {
    if (owner == kNoOwner) return false;
    for (size_t i = 0; i < kResourceCount; ++i) {
        if ((resources & (ResourceSet{1} << i)) && owners_[i] != owner) return false;
    }
    return true;
}

}  // namespace runtime
}  // namespace leshy
