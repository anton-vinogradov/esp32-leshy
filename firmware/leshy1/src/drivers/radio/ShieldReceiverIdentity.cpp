#include "drivers/radio/ShieldReceiverIdentity.h"

namespace leshy1::drivers::radio {

const char* shieldReceiverProbeStatusName(ShieldReceiverProbeStatus status) {
    switch (status) {
        case ShieldReceiverProbeStatus::NotRun: return "not_run";
        case ShieldReceiverProbeStatus::Pass: return "pass";
        case ShieldReceiverProbeStatus::Partial: return "partial";
        case ShieldReceiverProbeStatus::Failed: return "failed";
        case ShieldReceiverProbeStatus::RefusedProfile: return "refused_profile";
        case ShieldReceiverProbeStatus::Busy: return "busy";
    }
    return "unknown";
}

bool plausibleNrfReceiverIdentity(const NrfReceiverIdentity& value) {
    const bool allZero = value.status == 0 && value.config == 0 &&
        value.channel == 0 && value.rfSetup == 0 && value.feature == 0;
    const bool allOnes = value.status == 0xFF && value.config == 0xFF &&
        value.channel == 0xFF && value.rfSetup == 0xFF && value.feature == 0xFF;
    if (allZero || allOnes) return false;
    if ((value.status & 0x80U) != 0U || value.channel > 125U) return false;
    return true;
}

bool plausibleCc1101ReceiverIdentity(const Cc1101ReceiverIdentity& value) {
    if (!value.ready || value.status == 0xFFU) return false;
    if (value.partNumber == 0xFFU && value.version == 0xFFU) return false;
    if (value.partNumber == 0x00U &&
        (value.version == 0x00U || value.version == 0xFFU)) {
        return false;
    }
    return true;
}

void finalizeShieldReceiverProbe(ShieldReceiverProbeReport* report) {
    if (report == nullptr) return;
    report->nrf[0].detected = plausibleNrfReceiverIdentity(report->nrf[0]);
    report->nrf[1].detected = plausibleNrfReceiverIdentity(report->nrf[1]);
    report->cc1101.detected = plausibleCc1101ReceiverIdentity(report->cc1101);
    report->detectedReceivers = static_cast<std::uint8_t>(
        (report->nrf[0].detected ? 1U : 0U) +
        (report->nrf[1].detected ? 1U : 0U) +
        (report->cc1101.detected ? 1U : 0U));

    if (!report->profileDeclared || !report->gpsExcludedByProfile ||
        !report->pn532ExcludedByProfile) {
        report->status = ShieldReceiverProbeStatus::RefusedProfile;
        return;
    }
    if (!report->resourceAcquired) {
        report->status = ShieldReceiverProbeStatus::Busy;
        return;
    }
    if (!report->readOnly || report->nrfCeHighEvents != 0 ||
        report->ccCommandStrobes != 0 || report->radioTxCommands != 0 ||
        !report->nrfSlot3Gated || !report->gpio21StableHigh ||
        !report->cleanupComplete || report->nrfRegisterReads != 8 ||
        report->ccStatusReads != 2 || report->spiBytesClocked != 20) {
        report->status = ShieldReceiverProbeStatus::Failed;
        return;
    }
    report->status = report->detectedReceivers == 3
                         ? ShieldReceiverProbeStatus::Pass
                         : (report->detectedReceivers == 0
                                ? ShieldReceiverProbeStatus::Failed
                                : ShieldReceiverProbeStatus::Partial);
}

}  // namespace leshy1::drivers::radio
