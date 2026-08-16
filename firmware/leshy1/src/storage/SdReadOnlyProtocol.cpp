#include "SdReadOnlyProtocol.h"

#include <cstdio>

namespace leshy1::storage {
namespace {

constexpr std::array<std::uint8_t, kSdIdentificationCommandCount> kIdentificationSequence{
    0, 8, 55, 41, 58, 10, 9};

}  // namespace

const char* sdReadOnlyPlanStatusName(SdReadOnlyPlanStatus status) {
    switch (status) {
        case SdReadOnlyPlanStatus::Valid: return "valid";
        case SdReadOnlyPlanStatus::InvalidCount: return "invalid_count";
        case SdReadOnlyPlanStatus::InvalidSequence: return "invalid_sequence";
        case SdReadOnlyPlanStatus::InvalidInitBound: return "invalid_init_bound";
        case SdReadOnlyPlanStatus::MutatingCommand: return "mutating_command";
        case SdReadOnlyPlanStatus::ExecutionEnabled: return "execution_enabled";
    }
    return "invalid_sequence";
}

bool isMutatingSdCommand(std::uint8_t command) {
    switch (command) {
        case 24:  // WRITE_BLOCK
        case 25:  // WRITE_MULTIPLE_BLOCK
        case 26:  // PROGRAM_CID
        case 27:  // PROGRAM_CSD
        case 28:  // SET_WRITE_PROT
        case 29:  // CLR_WRITE_PROT
        case 32:  // ERASE_WR_BLK_START
        case 33:  // ERASE_WR_BLK_END
        case 38:  // ERASE
        case 42:  // LOCK_UNLOCK
        case 56:  // GEN_CMD may carry card-specific writes
            return true;
        default: return false;
    }
}

SdReadOnlyPlan defaultSdIdentificationPlan() {
    SdReadOnlyPlan plan;
    plan.commands = kIdentificationSequence;
    plan.commandCount = plan.commands.size();
    plan.maxInitAttempts = kSdMaxInitAttempts;
    plan.executionEnabled = false;
    return plan;
}

SdReadOnlyPlanStatus validateSdIdentificationPlan(const SdReadOnlyPlan& plan) {
    if (plan.commandCount != kIdentificationSequence.size()) {
        return SdReadOnlyPlanStatus::InvalidCount;
    }
    for (std::size_t index = 0; index < plan.commandCount; ++index) {
        if (isMutatingSdCommand(plan.commands[index])) {
            return SdReadOnlyPlanStatus::MutatingCommand;
        }
        if (plan.commands[index] != kIdentificationSequence[index]) {
            return SdReadOnlyPlanStatus::InvalidSequence;
        }
    }
    if (plan.maxInitAttempts == 0 || plan.maxInitAttempts > kSdMaxInitAttempts) {
        return SdReadOnlyPlanStatus::InvalidInitBound;
    }
    if (plan.executionEnabled) return SdReadOnlyPlanStatus::ExecutionEnabled;
    return SdReadOnlyPlanStatus::Valid;
}

bool formatSdReadOnlyProtocolJson(const SdReadOnlyPlan& plan, char* output,
                                  std::size_t capacity) {
    if (output == nullptr || capacity == 0 ||
        validateSdIdentificationPlan(plan) != SdReadOnlyPlanStatus::Valid) {
        if (output != nullptr && capacity > 0) output[0] = '\0';
        return false;
    }
    const int written = std::snprintf(
        output, capacity,
        "{\"schema\":\"leshy.storage.sd.protocol.v1\",\"kind\":\"report\","
        "\"status\":\"valid\",\"mode\":\"identification_only\","
        "\"commands\":[0,8,55,41,58,10,9],\"max_init_attempts\":%u,"
        "\"reads_cid\":true,\"reads_csd\":true,\"reads_data_blocks\":false,"
        "\"write_commands\":false,\"erase_commands\":false,"
        "\"format_allowed\":false,\"execution_enabled\":false,"
        "\"requires_mount_permit\":true,\"requires_disposable_card\":true}",
        static_cast<unsigned>(plan.maxInitAttempts));
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

}  // namespace leshy1::storage
