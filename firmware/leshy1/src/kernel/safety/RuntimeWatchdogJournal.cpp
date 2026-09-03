#include "kernel/safety/RuntimeWatchdogJournal.h"

#include <cstdio>
#include <cstring>

namespace leshy1::kernel::safety {
namespace {

bool boundedVersion(const char* value) {
    if (value == nullptr || value[0] == '\0') return false;
    for (std::size_t index = 0;
         index < kRuntimeWatchdogJournalVersionCapacity; ++index) {
        const char current = value[index];
        if (current == '\0') return index != 0U;
        const bool accepted =
            (current >= 'a' && current <= 'z') ||
            (current >= 'A' && current <= 'Z') ||
            (current >= '0' && current <= '9') ||
            current == '.' || current == '-' || current == '+';
        if (!accepted) return false;
    }
    return false;
}

bool exactLowerSha256(const char* value) {
    if (value == nullptr) return false;
    for (std::size_t index = 0U; index < 64U; ++index) {
        const char current = value[index];
        if (!((current >= '0' && current <= '9') ||
              (current >= 'a' && current <= 'f'))) {
            return false;
        }
    }
    return value[64] == '\0';
}

bool scalarPairsValid(const RuntimeWatchdogJournalRecord& record) {
    return record.sequenceInverse == ~record.sequence &&
        record.appIdentityInverse == ~record.appIdentity &&
        record.resetReasonInverse == ~record.resetReason &&
        record.safetyReasonInverse == ~record.safetyReason &&
        record.triggeredCpuMaskInverse == ~record.triggeredCpuMask &&
        record.stageInverse == ~record.stage &&
        record.pageInverse == ~record.page &&
        record.wifiViewInverse == ~record.wifiView &&
        record.tripCountInverse == ~record.tripCount &&
        record.quiesceCountInverse == ~record.quiesceCount;
}

}  // namespace

RuntimeWatchdogJournalRecord makeRuntimeWatchdogJournalRecord(
    std::uint32_t sequence, std::uint32_t appIdentity,
    std::uint32_t resetReason, std::uint32_t safetyReason,
    std::uint32_t triggeredCpuMask, std::uint32_t stage,
    std::uint32_t page, std::uint32_t wifiView,
    std::uint32_t tripCount, std::uint32_t quiesceCount,
    const char* version, const char* appElfSha256) {
    RuntimeWatchdogJournalRecord record;
    if (sequence == 0U || appIdentity == 0U || resetReason == 0U ||
        safetyReason == 0U || tripCount == 0U || quiesceCount == 0U ||
        !boundedVersion(version) || !exactLowerSha256(appElfSha256)) {
        return record;
    }
    record.magic = kRuntimeWatchdogJournalMagic;
    record.schema = kRuntimeWatchdogJournalSchema;
    record.sequence = sequence;
    record.sequenceInverse = ~sequence;
    record.appIdentity = appIdentity;
    record.appIdentityInverse = ~appIdentity;
    record.resetReason = resetReason;
    record.resetReasonInverse = ~resetReason;
    record.safetyReason = safetyReason;
    record.safetyReasonInverse = ~safetyReason;
    record.triggeredCpuMask = triggeredCpuMask;
    record.triggeredCpuMaskInverse = ~triggeredCpuMask;
    record.stage = stage;
    record.stageInverse = ~stage;
    record.page = page;
    record.pageInverse = ~page;
    record.wifiView = wifiView;
    record.wifiViewInverse = ~wifiView;
    record.tripCount = tripCount;
    record.tripCountInverse = ~tripCount;
    record.quiesceCount = quiesceCount;
    record.quiesceCountInverse = ~quiesceCount;
    std::snprintf(record.version, sizeof(record.version), "%s", version);
    std::memcpy(record.appElfSha256, appElfSha256, 65U);
    return record;
}

bool validateRuntimeWatchdogJournalRecord(
    const RuntimeWatchdogJournalRecord& record,
    std::uint32_t maximumStage, std::uint32_t maximumWifiView) {
    return record.magic == kRuntimeWatchdogJournalMagic &&
        record.schema == kRuntimeWatchdogJournalSchema &&
        record.sequence != 0U && record.appIdentity != 0U &&
        record.resetReason != 0U && record.safetyReason != 0U &&
        record.tripCount != 0U && record.quiesceCount != 0U &&
        record.stage <= maximumStage && record.wifiView <= maximumWifiView &&
        scalarPairsValid(record) && boundedVersion(record.version) &&
        exactLowerSha256(record.appElfSha256);
}

bool sameRuntimeWatchdogIncident(
    const RuntimeWatchdogJournalRecord& record,
    std::uint32_t sequence, std::uint32_t appIdentity,
    std::uint32_t resetReason,
    std::uint32_t safetyReason,
    std::uint32_t triggeredCpuMask, std::uint32_t stage,
    std::uint32_t page, std::uint32_t wifiView,
    std::uint32_t tripCount, std::uint32_t quiesceCount,
    const char* version, const char* appElfSha256) {
    return version != nullptr && appElfSha256 != nullptr &&
        sequence != 0U && record.sequence == sequence &&
        record.appIdentity == appIdentity &&
        record.resetReason == resetReason &&
        record.safetyReason == safetyReason &&
        record.triggeredCpuMask == triggeredCpuMask &&
        record.stage == stage && record.page == page &&
        record.wifiView == wifiView && record.tripCount == tripCount &&
        record.quiesceCount == quiesceCount &&
        std::strcmp(record.version, version) == 0 &&
        std::strcmp(record.appElfSha256, appElfSha256) == 0;
}

bool formatRuntimeWatchdogJournalJson(
    const RuntimeWatchdogJournalRecord& record,
    const char* stageName, const char* wifiViewName,
    char* output, std::size_t capacity) {
    if (output == nullptr || capacity == 0U || stageName == nullptr ||
        wifiViewName == nullptr) {
        return false;
    }
    const int written = std::snprintf(
        output, capacity,
        "{\"schema\":\"leshy.runtime_watchdog.crash.v1\","
        "\"sequence\":%lu,\"reason\":\"runtime_watchdog\","
        "\"version\":\"%s\",\"app_elf_sha256\":\"%s\","
        "\"reset_reason_code\":%lu,\"triggered_cpu_mask\":%lu,"
        "\"stage\":\"%s\",\"page\":%lu,\"wifi_view\":\"%s\","
        "\"trip_count\":%lu,\"emergency_quiesce_count\":%lu}\n",
        static_cast<unsigned long>(record.sequence), record.version,
        record.appElfSha256,
        static_cast<unsigned long>(record.resetReason),
        static_cast<unsigned long>(record.triggeredCpuMask), stageName,
        static_cast<unsigned long>(record.page), wifiViewName,
        static_cast<unsigned long>(record.tripCount),
        static_cast<unsigned long>(record.quiesceCount));
    return written > 0 && static_cast<std::size_t>(written) < capacity;
}

}  // namespace leshy1::kernel::safety
