#pragma once

#include <cstddef>
#include <cstdint>

namespace leshy1::kernel::safety {

constexpr std::uint32_t kRuntimeWatchdogJournalMagic = 0x4C574A31U;
constexpr std::uint32_t kRuntimeWatchdogJournalSchema = 1U;
constexpr std::size_t kRuntimeWatchdogJournalVersionCapacity = 32U;
constexpr std::size_t kRuntimeWatchdogJournalSha256Capacity = 65U;

// Fixed, allocation-free record copied from RTC into wear-levelled internal
// NVS on the first boot after a runtime watchdog reset. NVS provides atomic
// blob replacement; value/complement pairs and bounded text make corrupt or
// incompatible records fail closed when read by a later firmware.
struct RuntimeWatchdogJournalRecord final {
    std::uint32_t magic = 0;
    std::uint32_t schema = 0;
    std::uint32_t sequence = 0;
    std::uint32_t sequenceInverse = 0;
    std::uint32_t appIdentity = 0;
    std::uint32_t appIdentityInverse = 0;
    std::uint32_t resetReason = 0;
    std::uint32_t resetReasonInverse = 0;
    std::uint32_t safetyReason = 0;
    std::uint32_t safetyReasonInverse = 0;
    std::uint32_t triggeredCpuMask = 0;
    std::uint32_t triggeredCpuMaskInverse = 0;
    std::uint32_t stage = 0;
    std::uint32_t stageInverse = 0;
    std::uint32_t page = 0;
    std::uint32_t pageInverse = 0;
    std::uint32_t wifiView = 0;
    std::uint32_t wifiViewInverse = 0;
    std::uint32_t tripCount = 0;
    std::uint32_t tripCountInverse = 0;
    std::uint32_t quiesceCount = 0;
    std::uint32_t quiesceCountInverse = 0;
    char version[kRuntimeWatchdogJournalVersionCapacity] = {};
    char appElfSha256[kRuntimeWatchdogJournalSha256Capacity] = {};
};

RuntimeWatchdogJournalRecord makeRuntimeWatchdogJournalRecord(
    std::uint32_t sequence, std::uint32_t appIdentity,
    std::uint32_t resetReason, std::uint32_t safetyReason,
    std::uint32_t triggeredCpuMask, std::uint32_t stage,
    std::uint32_t page, std::uint32_t wifiView,
    std::uint32_t tripCount, std::uint32_t quiesceCount,
    const char* version, const char* appElfSha256);

bool validateRuntimeWatchdogJournalRecord(
    const RuntimeWatchdogJournalRecord& record,
    std::uint32_t maximumStage, std::uint32_t maximumWifiView);

bool sameRuntimeWatchdogIncident(
    const RuntimeWatchdogJournalRecord& record,
    std::uint32_t sequence, std::uint32_t appIdentity,
    std::uint32_t resetReason,
    std::uint32_t safetyReason,
    std::uint32_t triggeredCpuMask, std::uint32_t stage,
    std::uint32_t page, std::uint32_t wifiView,
    std::uint32_t tripCount, std::uint32_t quiesceCount,
    const char* version, const char* appElfSha256);

// Emits one privacy-minimal, human-readable JSON object. Names are supplied by
// the platform so the durable codec stays independent of UI and ESP-IDF enums.
bool formatRuntimeWatchdogJournalJson(
    const RuntimeWatchdogJournalRecord& record,
    const char* stageName, const char* wifiViewName,
    char* output, std::size_t capacity);

}  // namespace leshy1::kernel::safety
