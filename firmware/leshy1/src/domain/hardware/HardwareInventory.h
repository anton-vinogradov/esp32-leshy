#pragma once

#include <array>
#include <cstddef>

namespace leshy1::domain::hardware {

enum class CapabilityState {
    Declared,
    Detected,
    Available,
    Conflicted,
    Fault,
    Unknown,
};

const char* capabilityStateName(CapabilityState state);

struct CapabilityRecord {
    const char* key = nullptr;
    CapabilityState state = CapabilityState::Unknown;
    const char* evidence = nullptr;
    const char* reason = nullptr;
};

class HardwareInventory final {
public:
    static constexpr std::size_t kCapacity = 16;

    bool add(CapabilityRecord record);
    const CapabilityRecord* find(const char* key) const;
    const CapabilityRecord* get(std::size_t index) const;
    std::size_t size() const { return size_; }

private:
    std::array<CapabilityRecord, kCapacity> records_{};
    std::size_t size_ = 0;
};

}  // namespace leshy1::domain::hardware
