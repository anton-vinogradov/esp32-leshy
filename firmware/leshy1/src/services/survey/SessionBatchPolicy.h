#pragma once

#include <cstddef>
#include <cstdint>

namespace leshy1::services::survey {

struct SessionBatchPolicy final {
    std::size_t observationCapacity = 64;
    std::size_t targetEncodedBytes = 2048;
    std::uint64_t maximumLatencyUs = 5000000;
};

enum class SessionBatchTrigger : std::uint8_t {
    None,
    Capacity,
    EncodedSize,
    Latency,
    Stop,
    SafeShutdown,
};

const char* sessionBatchTriggerName(SessionBatchTrigger trigger);
bool validateSessionBatchPolicy(const SessionBatchPolicy& policy);
std::uint64_t minimumBatchBytesForRate(
    std::uint64_t sourceP99BytesPerSecond, std::uint32_t safetyMultiplier,
    std::uint64_t storageCommitP99Us);
SessionBatchTrigger sessionBatchTrigger(
    const SessionBatchPolicy& policy, std::size_t observations,
    std::size_t encodedBytes, std::uint64_t oldestQueuedUs,
    std::uint64_t nowUs, bool stopRequested, bool safeShutdownRequested);

}  // namespace leshy1::services::survey
