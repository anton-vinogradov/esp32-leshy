#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace leshy1::storage {

constexpr std::size_t kSdIdentificationCommandCount = 7;
constexpr std::uint16_t kSdMaxInitAttempts = 100;

struct SdReadOnlyPlan final {
    std::array<std::uint8_t, kSdIdentificationCommandCount> commands{};
    std::size_t commandCount = 0;
    std::uint16_t maxInitAttempts = 0;
    bool executionEnabled = false;
};

enum class SdReadOnlyPlanStatus : std::uint8_t {
    Valid,
    InvalidCount,
    InvalidSequence,
    InvalidInitBound,
    MutatingCommand,
    ExecutionEnabled,
};

const char* sdReadOnlyPlanStatusName(SdReadOnlyPlanStatus status);
bool isMutatingSdCommand(std::uint8_t command);
SdReadOnlyPlan defaultSdIdentificationPlan();
SdReadOnlyPlanStatus validateSdIdentificationPlan(const SdReadOnlyPlan& plan);
bool formatSdReadOnlyProtocolJson(const SdReadOnlyPlan& plan, char* output,
                                  std::size_t capacity);

}  // namespace leshy1::storage
