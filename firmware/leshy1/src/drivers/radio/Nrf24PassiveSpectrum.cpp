#include "drivers/radio/Nrf24PassiveSpectrum.h"

namespace leshy1::drivers::radio {

bool validateNrf24PassiveSpectrumPlan(
    const Nrf24PassiveSpectrumPlan& plan) {
    return plan.firstChannel == Nrf24PassiveSpectrumPlan::kFirstChannel &&
           plan.lastChannel == Nrf24PassiveSpectrumPlan::kLastChannel &&
           plan.dwellUs >= 130U && plan.dwellUs <= 500U &&
           plan.maximumModules >= 1U && plan.maximumModules <= 3U;
}

const char* nrf24PassiveSpectrumStatusName(
    Nrf24PassiveSpectrumStatus status) {
    switch (status) {
        case Nrf24PassiveSpectrumStatus::NotStarted: return "not_started";
        case Nrf24PassiveSpectrumStatus::Ready: return "ready";
        case Nrf24PassiveSpectrumStatus::Fault: return "fault";
        case Nrf24PassiveSpectrumStatus::RefusedProfile:
            return "refused_profile";
        case Nrf24PassiveSpectrumStatus::Busy: return "busy";
        case Nrf24PassiveSpectrumStatus::CleanupFailed:
            return "cleanup_failed";
    }
    return "unknown";
}

bool validateNrf24PassiveSpectrumReport(
    const Nrf24PassiveSpectrumReport& report, bool requireCleanup) {
    if (report.status != Nrf24PassiveSpectrumStatus::Ready ||
        !report.profileDeclared || !report.gpsExcludedByProfile ||
        !report.pn532ExcludedByProfile || !report.resourceOwned ||
        !report.nrfSlot3Gated || !report.gpio21StableHigh ||
        !report.rxOnly || report.detectedModules == 0 ||
        report.detectedModules > 3 || report.activeSlotMask == 0 ||
        report.activeSlotMask > 0x07U ||
        static_cast<std::uint8_t>(
            ((report.activeSlotMask >> 0U) & 1U) +
            ((report.activeSlotMask >> 1U) & 1U) +
            ((report.activeSlotMask >> 2U) & 1U)) != report.detectedModules ||
        report.txModeEntries != 0 ||
        report.txPayloadCommands != 0 || report.ccCommandStrobes != 0) {
        return false;
    }
    if (requireCleanup && !report.cleanupComplete) return false;
    return true;
}

}  // namespace leshy1::drivers::radio
