#include "domain/hardware/HardwareInventory.h"

#include <cstring>

namespace leshy1::domain::hardware {

const char* capabilityStateName(CapabilityState state) {
    switch (state) {
        case CapabilityState::Declared: return "declared";
        case CapabilityState::Detected: return "detected";
        case CapabilityState::Available: return "available";
        case CapabilityState::Conflicted: return "conflicted";
        case CapabilityState::Fault: return "fault";
        case CapabilityState::Unknown: return "unknown";
    }
    return "unknown";
}

bool HardwareInventory::add(CapabilityRecord record) {
    if (record.key == nullptr || record.key[0] == '\0' || find(record.key) != nullptr ||
        size_ >= records_.size()) {
        return false;
    }
    records_[size_++] = record;
    return true;
}

const CapabilityRecord* HardwareInventory::find(const char* key) const {
    if (key == nullptr) return nullptr;
    for (std::size_t i = 0; i < size_; ++i) {
        if (std::strcmp(records_[i].key, key) == 0) return &records_[i];
    }
    return nullptr;
}

const CapabilityRecord* HardwareInventory::get(std::size_t index) const {
    return index < size_ ? &records_[index] : nullptr;
}

}  // namespace leshy1::domain::hardware
