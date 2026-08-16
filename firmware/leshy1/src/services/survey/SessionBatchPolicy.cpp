#include "SessionBatchPolicy.h"

#include "storage/SessionCodec.h"

namespace leshy1::services::survey {

const char* sessionBatchTriggerName(SessionBatchTrigger trigger) {
    switch (trigger) {
        case SessionBatchTrigger::None: return "none";
        case SessionBatchTrigger::Capacity: return "capacity";
        case SessionBatchTrigger::EncodedSize: return "encoded_size";
        case SessionBatchTrigger::Latency: return "latency";
        case SessionBatchTrigger::Stop: return "stop";
        case SessionBatchTrigger::SafeShutdown: return "safe_shutdown";
    }
    return "none";
}

bool validateSessionBatchPolicy(const SessionBatchPolicy& policy) {
    return policy.observationCapacity > 0 &&
           policy.observationCapacity <= 64 &&
           policy.targetEncodedBytes > storage::kSegmentFooterBytes &&
           policy.targetEncodedBytes <= storage::kSessionSegmentMaxBytes &&
           policy.maximumLatencyUs > 0;
}

std::uint64_t minimumBatchBytesForRate(
    std::uint64_t sourceP99BytesPerSecond, std::uint32_t safetyMultiplier,
    std::uint64_t storageCommitP99Us) {
    if (sourceP99BytesPerSecond == 0 || safetyMultiplier == 0 ||
        storageCommitP99Us == 0) {
        return 0;
    }
    const std::uint64_t requiredRate =
        sourceP99BytesPerSecond * safetyMultiplier;
    if (requiredRate / safetyMultiplier != sourceP99BytesPerSecond ||
        requiredRate > UINT64_MAX / storageCommitP99Us) {
        return 0;
    }
    const std::uint64_t product = requiredRate * storageCommitP99Us;
    return product / 1000000ULL + (product % 1000000ULL == 0 ? 0 : 1);
}

SessionBatchTrigger sessionBatchTrigger(
    const SessionBatchPolicy& policy, std::size_t observations,
    std::size_t encodedBytes, std::uint64_t oldestQueuedUs,
    std::uint64_t nowUs, bool stopRequested, bool safeShutdownRequested) {
    if (!validateSessionBatchPolicy(policy) || observations == 0) {
        return SessionBatchTrigger::None;
    }
    if (safeShutdownRequested) return SessionBatchTrigger::SafeShutdown;
    if (stopRequested) return SessionBatchTrigger::Stop;
    if (observations >= policy.observationCapacity) {
        return SessionBatchTrigger::Capacity;
    }
    if (encodedBytes >= policy.targetEncodedBytes) {
        return SessionBatchTrigger::EncodedSize;
    }
    if (oldestQueuedUs != 0 && nowUs >= oldestQueuedUs &&
        nowUs - oldestQueuedUs >= policy.maximumLatencyUs) {
        return SessionBatchTrigger::Latency;
    }
    return SessionBatchTrigger::None;
}

}  // namespace leshy1::services::survey
