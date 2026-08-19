#include "drivers/radio/Cc1101PassiveSpectrum.h"

namespace leshy1::drivers::radio {
namespace {

constexpr bool samePlan(const Cc1101PassiveSpectrumPlan& plan,
                        Cc1101SpectrumBand band,
                        std::uint32_t firstKHz,
                        std::uint32_t lastKHz) {
    return plan.band == band && plan.firstKHz == firstKHz &&
           plan.lastKHz == lastKHz;
}

}  // namespace

const char* cc1101SpectrumBandName(Cc1101SpectrumBand band) {
    switch (band) {
        case Cc1101SpectrumBand::Band315: return "315";
        case Cc1101SpectrumBand::Band433: return "433";
        case Cc1101SpectrumBand::Band868: return "868";
        case Cc1101SpectrumBand::Band915: return "915";
        case Cc1101SpectrumBand::Count: break;
    }
    return "unknown";
}

Cc1101PassiveSpectrumPlan cc1101PassiveSpectrumPlan(
    Cc1101SpectrumBand band) {
    switch (band) {
        case Cc1101SpectrumBand::Band315:
            return {band, 300000, 348000, 500, 3000};
        case Cc1101SpectrumBand::Band433:
            return {band, 433050, 434790, 500, 3000};
        case Cc1101SpectrumBand::Band868:
            return {band, 863000, 870000, 500, 3000};
        case Cc1101SpectrumBand::Band915:
            return {band, 902000, 928000, 500, 3000};
        case Cc1101SpectrumBand::Count:
            break;
    }
    return {};
}

bool validateCc1101PassiveSpectrumPlan(
    const Cc1101PassiveSpectrumPlan& plan) {
    const bool knownBand =
        samePlan(plan, Cc1101SpectrumBand::Band315, 300000, 348000) ||
        samePlan(plan, Cc1101SpectrumBand::Band433, 433050, 434790) ||
        samePlan(plan, Cc1101SpectrumBand::Band868, 863000, 870000) ||
        samePlan(plan, Cc1101SpectrumBand::Band915, 902000, 928000);
    return knownBand && plan.settleUs >= 300U && plan.settleUs <= 1000U &&
           plan.readyTimeoutUs >= 1000U && plan.readyTimeoutUs <= 5000U &&
           plan.firstKHz < plan.lastKHz;
}

std::uint32_t cc1101SpectrumFrequencyKHz(
    const Cc1101PassiveSpectrumPlan& plan, std::size_t bin) {
    if (!validateCc1101PassiveSpectrumPlan(plan) ||
        bin >= Cc1101PassiveSpectrumPlan::kBinCount) {
        return 0;
    }
    return plan.firstKHz + static_cast<std::uint32_t>(
        static_cast<std::uint64_t>(plan.lastKHz - plan.firstKHz) * bin /
        (Cc1101PassiveSpectrumPlan::kBinCount - 1U));
}

const char* cc1101PassiveSpectrumStatusName(
    Cc1101PassiveSpectrumStatus status) {
    switch (status) {
        case Cc1101PassiveSpectrumStatus::NotStarted: return "not_started";
        case Cc1101PassiveSpectrumStatus::Ready: return "ready";
        case Cc1101PassiveSpectrumStatus::Fault: return "fault";
        case Cc1101PassiveSpectrumStatus::RefusedProfile:
            return "refused_profile";
        case Cc1101PassiveSpectrumStatus::Busy: return "busy";
        case Cc1101PassiveSpectrumStatus::CleanupFailed:
            return "cleanup_failed";
    }
    return "unknown";
}

bool validateCc1101PassiveSpectrumReport(
    const Cc1101PassiveSpectrumReport& report, bool requireCleanup) {
    if (report.status != Cc1101PassiveSpectrumStatus::Ready ||
        !report.profileDeclared || !report.gpsExcludedByProfile ||
        !report.pn532ExcludedByProfile || !report.resourceOwned ||
        !report.nrfSlot3Gated || !report.gpio21StableHigh ||
        !report.rxOnly || !report.receiverDetected ||
        report.partNumber != 0x00U || report.version == 0x00U ||
        report.version == 0xFFU || report.rejectedStrobes != 0U ||
        report.txStrobes != 0U || report.paTableWrites != 0U ||
        report.fifoWrites != 0U) {
        return false;
    }
    if (report.transientRetries > report.receiveReadyTimeouts) return false;
    if (report.commandStrobes != report.resetStrobes +
            report.receiveStrobes + report.idleStrobes) {
        return false;
    }
    if (requireCleanup && !report.cleanupComplete) return false;
    return true;
}

}  // namespace leshy1::drivers::radio
