#pragma once

#include <cstddef>
#include <cstdint>

#include "domain/hardware/HardwareInventory.h"

namespace leshy1::services::diagnostics {

struct BootMetrics {
    const char* version = nullptr;
    const char* profile = nullptr;
    const char* profileRevision = nullptr;
    const char* appElfSha256 = nullptr;
    std::uint64_t setupEnterUs = 0;
    std::uint64_t runtimeReadyUs = 0;
    std::uint64_t displayReadyUs = 0;
    std::uint64_t inputReadyUs = 0;
    std::uint64_t interactiveReadyUs = 0;
    std::uint32_t resetReason = 0;
    std::uint32_t flashBytes = 0;
    bool psramFound = false;
    std::uint32_t psramBytes = 0;
    std::uint32_t heapTotal = 0;
    std::uint32_t heapFree = 0;
    std::uint32_t heapMinimum = 0;
    bool buzzerSafetyConfigured = false;
    bool buzzerInactive = false;
    bool inputDetected = false;
    std::uint8_t inputRaw = 0xFF;
};

bool formatBootMetrics(const BootMetrics& metrics, char* output, std::size_t capacity);
bool formatCapability(const domain::hardware::CapabilityRecord& record,
                      char* output,
                      std::size_t capacity);

}  // namespace leshy1::services::diagnostics
