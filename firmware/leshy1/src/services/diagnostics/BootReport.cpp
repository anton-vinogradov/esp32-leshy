#include "services/diagnostics/BootReport.h"

#include <cstdio>

namespace leshy1::services::diagnostics {
namespace {

const char* safe(const char* value) { return value == nullptr ? "" : value; }

bool fits(int written, std::size_t capacity) {
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

}  // namespace

bool formatBootMetrics(const BootMetrics& metrics, char* output, std::size_t capacity) {
    if (output == nullptr || capacity == 0) return false;
    const int written = std::snprintf(
        output, capacity,
        "{\"schema\":\"leshy.boot.v1\",\"kind\":\"ready\","
        "\"target\":\"clean_1x_measure\",\"version\":\"%s\","
        "\"profile\":\"%s\",\"profile_revision\":\"%s\","
        "\"app_elf_sha256\":\"%s\","
        "\"legacy_sources\":false,\"setup_enter_us\":%llu,"
        "\"runtime_ready_us\":%llu,\"display_ready_us\":%llu,"
        "\"input_ready_us\":%llu,\"interactive_ready_us\":%llu,"
        "\"reset_reason_code\":%lu,"
        "\"flash_bytes\":%lu,\"psram_found\":%s,\"psram_bytes\":%lu,"
        "\"heap_total\":%lu,\"heap_free\":%lu,\"heap_min_free\":%lu,"
        "\"buzzer_safety_configured\":%s,\"buzzer_inactive\":%s,"
        "\"input_detected\":%s,\"input_raw\":%u,"
        "\"input_probe_attempts\":%u,"
        "\"input_probe_transient_retries\":%u}",
        safe(metrics.version), safe(metrics.profile), safe(metrics.profileRevision),
        safe(metrics.appElfSha256),
        static_cast<unsigned long long>(metrics.setupEnterUs),
        static_cast<unsigned long long>(metrics.runtimeReadyUs),
        static_cast<unsigned long long>(metrics.displayReadyUs),
        static_cast<unsigned long long>(metrics.inputReadyUs),
        static_cast<unsigned long long>(metrics.interactiveReadyUs),
        static_cast<unsigned long>(metrics.resetReason),
        static_cast<unsigned long>(metrics.flashBytes),
        metrics.psramFound ? "true" : "false",
        static_cast<unsigned long>(metrics.psramBytes),
        static_cast<unsigned long>(metrics.heapTotal),
        static_cast<unsigned long>(metrics.heapFree),
        static_cast<unsigned long>(metrics.heapMinimum),
        metrics.buzzerSafetyConfigured ? "true" : "false",
        metrics.buzzerInactive ? "true" : "false",
        metrics.inputDetected ? "true" : "false",
        static_cast<unsigned>(metrics.inputRaw),
        static_cast<unsigned>(metrics.inputProbeAttempts),
        static_cast<unsigned>(metrics.inputProbeTransientRetries));
    return fits(written, capacity);
}

bool formatCapability(const domain::hardware::CapabilityRecord& record,
                      char* output,
                      std::size_t capacity) {
    if (output == nullptr || capacity == 0 || record.key == nullptr) return false;
    const int written = std::snprintf(
        output, capacity,
        "{\"schema\":\"leshy.boot.v1\",\"kind\":\"capability\","
        "\"key\":\"%s\",\"state\":\"%s\",\"evidence\":\"%s\","
        "\"reason\":\"%s\"}",
        safe(record.key), domain::hardware::capabilityStateName(record.state),
        safe(record.evidence), safe(record.reason));
    return fits(written, capacity);
}

}  // namespace leshy1::services::diagnostics
