#include "AirspaceGuardPresenter.h"

#include <cstdio>
#include <cstring>

namespace leshy1::ui {

namespace {

using apps::guard::AirspaceGuardController;
using apps::guard::AirspaceGuardLoadStatus;
using apps::guard::AirspaceGuardView;
using services::guard::AirspaceBleTrackerProtocol;
using services::guard::AirspaceConfidence;
using services::guard::AirspaceEvidenceRef;
using services::guard::AirspaceFinding;
using services::guard::AirspaceFindingKind;
using services::guard::AirspaceGuardStatus;
using services::guard::AirspaceWifiSecurity;

template <std::size_t Capacity, typename... Args>
void formatText(std::array<char, Capacity>& destination, UiLanguage language,
                UiTextId format, Args... args) {
    const int written = std::snprintf(destination.data(), destination.size(),
                                      uiText(language, format), args...);
    if (written < 0) destination[0] = '\0';
    destination.back() = '\0';
}

template <std::size_t Capacity>
void copyText(std::array<char, Capacity>& destination, UiLanguage language,
              UiTextId text) {
    const int written = std::snprintf(destination.data(), destination.size(),
                                      "%s", uiText(language, text));
    if (written < 0) destination[0] = '\0';
    destination.back() = '\0';
}

UiTextId confidenceText(AirspaceConfidence confidence) {
    switch (confidence) {
        case AirspaceConfidence::High:
            return UiTextId::AirspaceGuardConfidenceHigh;
        case AirspaceConfidence::Medium:
            return UiTextId::AirspaceGuardConfidenceMedium;
        case AirspaceConfidence::Low:
            return UiTextId::AirspaceGuardConfidenceLow;
    }
    return UiTextId::AirspaceGuardConfidenceLow;
}

UiTextId securityText(AirspaceWifiSecurity security) {
    switch (security) {
        case AirspaceWifiSecurity::Open:
            return UiTextId::AirspaceGuardSecurityOpen;
        case AirspaceWifiSecurity::LegacyPrivacy:
            return UiTextId::AirspaceGuardSecurityLegacy;
        case AirspaceWifiSecurity::Wpa:
            return UiTextId::AirspaceGuardSecurityWpa;
        case AirspaceWifiSecurity::Rsn:
            return UiTextId::AirspaceGuardSecurityRsn;
        case AirspaceWifiSecurity::Unknown:
            return UiTextId::AirspaceGuardSecurityLegacy;
    }
    return UiTextId::AirspaceGuardSecurityLegacy;
}

UiTextId bleTrackerProtocolText(AirspaceBleTrackerProtocol protocol) {
    switch (protocol) {
        case AirspaceBleTrackerProtocol::FindMy:
            return UiTextId::AirspaceGuardBleProtocolFindMy;
        case AirspaceBleTrackerProtocol::SmartTag:
            return UiTextId::AirspaceGuardBleProtocolSmartTag;
        case AirspaceBleTrackerProtocol::Tile:
            return UiTextId::AirspaceGuardBleProtocolTile;
        case AirspaceBleTrackerProtocol::None:
            return UiTextId::AirspaceGuardBleProtocolTile;
    }
    return UiTextId::AirspaceGuardBleProtocolTile;
}

bool displayableUtf8(const std::uint8_t* value, std::size_t length) {
    if (value == nullptr || length == 0U) return false;
    std::size_t index = 0U;
    while (index < length) {
        const std::uint8_t first = value[index++];
        if (first <= 0x7fU) {
            if (first < 0x20U || first == 0x7fU) return false;
            continue;
        }
        std::size_t continuationCount = 0U;
        if (first >= 0xc2U && first <= 0xdfU) {
            continuationCount = 1U;
        } else if (first >= 0xe0U && first <= 0xefU) {
            continuationCount = 2U;
        } else if (first >= 0xf0U && first <= 0xf4U) {
            continuationCount = 3U;
        } else {
            return false;
        }
        if (length - index < continuationCount) return false;
        const std::uint8_t second = value[index];
        if ((first == 0xe0U && second < 0xa0U) ||
            (first == 0xedU && second >= 0xa0U) ||
            (first == 0xf0U && second < 0x90U) ||
            (first == 0xf4U && second >= 0x90U)) {
            return false;
        }
        for (std::size_t continuation = 0U;
             continuation < continuationCount; ++continuation) {
            if ((value[index++] & 0xc0U) != 0x80U) return false;
        }
    }
    return true;
}

std::uint32_t networkNameFingerprint(const AirspaceFinding& finding) {
    std::uint32_t fingerprint = 2166136261U;
    for (std::size_t index = 0U; index < finding.networkNameLength; ++index) {
        fingerprint ^= finding.networkName[index];
        fingerprint *= 16777619U;
    }
    return fingerprint;
}

void formatSourceAddress(
    std::array<char, AirspaceGuardUiModel::kContextCapacity>& text,
    UiLanguage language, const std::array<std::uint8_t, 6>& address) {
    formatText(text, language, UiTextId::AirspaceGuardSourceFormat,
               static_cast<unsigned>(address[0]),
               static_cast<unsigned>(address[1]),
               static_cast<unsigned>(address[2]),
               static_cast<unsigned>(address[3]),
               static_cast<unsigned>(address[4]),
               static_cast<unsigned>(address[5]));
}

void formatSource(std::array<char, AirspaceGuardUiModel::kContextCapacity>& text,
                  UiLanguage language, const AirspaceFinding& finding) {
    formatSourceAddress(text, language, finding.transmitter);
}

void formatBleIdentity(
    std::array<char, AirspaceGuardUiModel::kContextCapacity>& text,
    UiLanguage language, const std::array<std::uint8_t, 6>& identity) {
    formatText(text, language, UiTextId::AirspaceGuardBleIdFormat,
               static_cast<unsigned>(identity[0]),
               static_cast<unsigned>(identity[1]),
               static_cast<unsigned>(identity[2]),
               static_cast<unsigned>(identity[3]),
               static_cast<unsigned>(identity[4]),
               static_cast<unsigned>(identity[5]));
}

void formatNetworkName(
    std::array<char, AirspaceGuardUiModel::kContextCapacity>& text,
    UiLanguage language, const AirspaceFinding& finding) {
    if (!displayableUtf8(finding.networkName.data(),
                         finding.networkNameLength)) {
        formatText(text, language,
                   UiTextId::AirspaceGuardSsidFingerprintFormat,
                   static_cast<unsigned long>(
                       networkNameFingerprint(finding)));
        return;
    }
    std::array<char, AirspaceFinding::kNetworkNameCapacity + 1U> name{};
    std::memcpy(name.data(), finding.networkName.data(),
                finding.networkNameLength);
    formatText(text, language, UiTextId::AirspaceGuardSsidFormat,
               static_cast<int>(finding.networkNameLength), name.data());
}

void formatFindingContext(
    std::array<char, AirspaceGuardUiModel::kContextCapacity>& text,
    UiLanguage language, const AirspaceFinding& finding) {
    if (finding.kind == AirspaceFindingKind::WifiSsidSecurityConflict) {
        formatNetworkName(text, language, finding);
    } else if (finding.kind == AirspaceFindingKind::BleTrackerPresence) {
        formatBleIdentity(text, language, finding.transmitter);
    } else {
        formatSource(text, language, finding);
    }
}

void formatEvidenceSource(
    std::array<char, AirspaceGuardUiModel::kContextCapacity>& text,
    UiLanguage language, const AirspaceFinding& finding,
    std::size_t evidenceIndex) {
    if (finding.kind == AirspaceFindingKind::BleTrackerPresence) {
        formatBleIdentity(text, language, finding.transmitter);
        return;
    }
    if (finding.kind != AirspaceFindingKind::WifiSsidSecurityConflict) {
        formatSource(text, language, finding);
        return;
    }
    formatSourceAddress(text, language,
                        evidenceIndex == 1U
                            ? finding.relatedTransmitter
                            : finding.transmitter);
}

void appendIncompleteRows(const AirspaceGuardController& controller,
                          UiLanguage language, AirspaceGuardUiModel& model) {
    if (model.rowCount < model.rows.size()) {
        formatText(model.rows[model.rowCount++].text, language,
                   UiTextId::AirspaceGuardCoverageFormat,
                   static_cast<unsigned long>(
                       controller.sourceFramesObserved()),
                   static_cast<unsigned long>(controller.framesInspected()));
    }
    if (model.rowCount < model.rows.size() &&
        (controller.sourceReadFailures() != 0U ||
         controller.malformedFrames() != 0U)) {
        formatText(model.rows[model.rowCount++].text, language,
                   UiTextId::AirspaceGuardLossFormat,
                   static_cast<unsigned long>(controller.sourceReadFailures()),
                   static_cast<unsigned long>(controller.malformedFrames()));
    }
    if (model.rowCount < model.rows.size() &&
        controller.sourceFramesDropped() != 0U) {
        formatText(model.rows[model.rowCount++].text, language,
                   UiTextId::AirspaceGuardCaptureLossFormat,
                   static_cast<unsigned long>(
                       controller.sourceFramesDropped()));
    }
    if (model.rowCount < model.rows.size() &&
        controller.findingsDropped() != 0U) {
        formatText(model.rows[model.rowCount++].text, language,
                   UiTextId::AirspaceGuardDroppedFormat,
                   static_cast<unsigned long>(controller.findingsDropped()));
    }
    if (model.rowCount < model.rows.size() &&
        controller.inspectionTruncated()) {
        copyText(model.rows[model.rowCount++].text, language,
                 UiTextId::AirspaceGuardTruncated);
    }
}

AirspaceGuardUiModel presentOutcome(const AirspaceGuardController& controller,
                                    UiLanguage language) {
    AirspaceGuardUiModel model{};
    model.evidenceIncomplete = controller.evidenceIncomplete();
    model.note = model.evidenceIncomplete
        ? UiTextId::AirspaceGuardEvidenceIncomplete
        : UiTextId::AirspaceGuardPassiveOnly;
    switch (controller.outcome()) {
        case AirspaceGuardStatus::Clear:
            model.headline = UiTextId::AirspaceGuardClear;
            model.tone = AirspaceGuardUiTone::Healthy;
            formatText(model.rows[0].text, language,
                       UiTextId::AirspaceGuardCoverageFormat,
                       static_cast<unsigned long>(
                           controller.sourceFramesObserved()),
                       static_cast<unsigned long>(
                           controller.framesInspected()));
            formatText(model.rows[1].text, language,
                       UiTextId::AirspaceGuardEvidenceKeptFormat,
                       static_cast<unsigned long>(
                           controller.framesAvailable()));
            model.rowCount = 2U;
            break;
        case AirspaceGuardStatus::Inconclusive:
            model.headline = UiTextId::AirspaceGuardInconclusive;
            model.tone = AirspaceGuardUiTone::Caution;
            if (controller.framesAvailable() == 0U) {
                copyText(model.context, language,
                         UiTextId::AirspaceGuardCaptureNotStarted);
            }
            appendIncompleteRows(controller, language, model);
            break;
        case AirspaceGuardStatus::InvalidPolicy:
            model.headline = UiTextId::AirspaceGuardInvalidPolicy;
            model.tone = AirspaceGuardUiTone::Error;
            break;
        case AirspaceGuardStatus::Finding:
            model.headline = UiTextId::AirspaceGuardReportRejected;
            model.tone = AirspaceGuardUiTone::Error;
            break;
    }
    return model;
}

AirspaceGuardUiModel presentFinding(const AirspaceGuardController& controller,
                                    UiLanguage language) {
    AirspaceGuardUiModel model{};
    model.headline = UiTextId::AirspaceGuardFinding;
    model.tone = AirspaceGuardUiTone::Finding;
    model.openable = true;
    model.evidenceIncomplete = controller.evidenceIncomplete();
    model.note = model.evidenceIncomplete
        ? UiTextId::AirspaceGuardEvidenceIncomplete
        : UiTextId::AirspaceGuardPassiveOnly;
    const AirspaceFinding* finding = controller.selectedFinding();
    if (finding == nullptr) {
        model.headline = UiTextId::AirspaceGuardReportRejected;
        model.tone = AirspaceGuardUiTone::Error;
        model.openable = false;
        return model;
    }
    if (finding->kind ==
        AirspaceFindingKind::WifiSsidSecurityConflict) {
        model.headline = UiTextId::AirspaceGuardIdentityConflict;
    } else if (finding->kind == AirspaceFindingKind::WifiSsidChurn) {
        model.headline = UiTextId::AirspaceGuardSsidChurn;
    } else if (finding->kind == AirspaceFindingKind::BleTrackerPresence) {
        model.headline = UiTextId::AirspaceGuardBleTrackerPresence;
        if (!model.evidenceIncomplete) {
            model.note = UiTextId::AirspaceGuardBlePresenceOnly;
        }
    }
    formatFindingContext(model.context, language, *finding);
    formatText(model.rows[0].text, language,
               UiTextId::AirspaceGuardFindingPositionFormat,
               static_cast<unsigned>(controller.findingSelection() + 1U),
               static_cast<unsigned>(controller.findingCount()));
    formatText(model.rows[1].text, language,
               UiTextId::AirspaceGuardConfidenceFormat,
               uiText(language, confidenceText(finding->confidence)),
               static_cast<unsigned>(finding->detectorVersion));
    if (finding->kind ==
        AirspaceFindingKind::WifiSsidSecurityConflict) {
        formatText(model.rows[2].text, language,
                   UiTextId::AirspaceGuardSecurityPairFormat,
                   uiText(language, securityText(finding->primarySecurity)),
                   uiText(language, securityText(finding->relatedSecurity)));
    } else {
        formatText(model.rows[2].text, language,
                   UiTextId::AirspaceGuardObservedFormat,
                   static_cast<unsigned>(finding->observed),
                   static_cast<unsigned>(finding->threshold));
    }
    if (controller.sourceFramesDropped() != 0U) {
        formatText(model.rows[3].text, language,
                   UiTextId::AirspaceGuardCaptureLossFormat,
                   static_cast<unsigned long>(
                       controller.sourceFramesDropped()));
    } else if (controller.findingsDropped() != 0U) {
        formatText(model.rows[3].text, language,
                   UiTextId::AirspaceGuardDroppedFormat,
                   static_cast<unsigned long>(controller.findingsDropped()));
    } else if (finding->kind ==
               AirspaceFindingKind::WifiSsidSecurityConflict) {
        formatText(model.rows[3].text, language,
                   UiTextId::AirspaceGuardBssidPairFormat,
                   static_cast<unsigned>(finding->transmitter[3]),
                   static_cast<unsigned>(finding->transmitter[4]),
                   static_cast<unsigned>(finding->transmitter[5]),
                   static_cast<unsigned>(finding->relatedTransmitter[3]),
                   static_cast<unsigned>(finding->relatedTransmitter[4]),
                   static_cast<unsigned>(finding->relatedTransmitter[5]));
    } else if (finding->kind == AirspaceFindingKind::WifiSsidChurn) {
        const std::uint64_t spanTenths =
            (finding->lastUs - finding->firstUs + 99999ULL) / 100000ULL;
        formatText(model.rows[3].text, language,
                   UiTextId::AirspaceGuardChurnSpanFormat,
                   static_cast<unsigned>(spanTenths / 10U),
                   static_cast<unsigned>(spanTenths % 10U));
    } else if (finding->kind == AirspaceFindingKind::BleTrackerPresence) {
        const std::uint64_t spanTenths =
            (finding->lastUs - finding->firstUs + 99999ULL) / 100000ULL;
        formatText(model.rows[3].text, language,
                   UiTextId::AirspaceGuardBleProtocolSpanFormat,
                   uiText(language,
                          bleTrackerProtocolText(
                              finding->bleTrackerProtocol)),
                   static_cast<unsigned>(spanTenths / 10U),
                   static_cast<unsigned>(spanTenths % 10U));
    } else {
        formatText(model.rows[3].text, language,
                   UiTextId::AirspaceGuardDisconnectMixFormat,
                   static_cast<unsigned>(finding->deauthenticationFrames),
                   static_cast<unsigned>(finding->disassociationFrames));
    }
    model.rowCount = model.rows.size();
    return model;
}

AirspaceGuardUiModel presentEvidenceList(
    const AirspaceGuardController& controller, UiLanguage language) {
    AirspaceGuardUiModel model{};
    model.headline = UiTextId::AirspaceGuardEvidenceTitle;
    model.tone = AirspaceGuardUiTone::Finding;
    model.openable = true;
    model.evidenceIncomplete = controller.evidenceIncomplete();
    model.note = model.evidenceIncomplete
        ? UiTextId::AirspaceGuardEvidenceIncomplete
        : UiTextId::AirspaceGuardPassiveOnly;
    const AirspaceFinding* finding = controller.selectedFinding();
    if (finding == nullptr || finding->evidenceCount == 0U) {
        model.headline = UiTextId::AirspaceGuardReportRejected;
        model.tone = AirspaceGuardUiTone::Error;
        model.openable = false;
        return model;
    }
    if (finding->kind == AirspaceFindingKind::BleTrackerPresence &&
        !model.evidenceIncomplete) {
        model.note = UiTextId::AirspaceGuardBlePresenceOnly;
    }
    formatFindingContext(model.context, language, *finding);
    const std::size_t selection = controller.evidenceSelection();
    const std::size_t first = selection < model.rows.size()
        ? 0U : selection - model.rows.size() + 1U;
    const std::size_t remaining = finding->evidenceCount - first;
    model.rowCount = remaining < model.rows.size()
        ? remaining : model.rows.size();
    for (std::size_t row = 0; row < model.rowCount; ++row) {
        const std::size_t index = first + row;
        const AirspaceEvidenceRef& evidence = finding->evidence[index];
        if (finding->kind == AirspaceFindingKind::BleTrackerPresence) {
            formatText(model.rows[row].text, language,
                       UiTextId::AirspaceGuardEvidenceRecordRowFormat,
                       static_cast<unsigned long>(evidence.frameIndex),
                       static_cast<int>(evidence.rssiDbm));
        } else {
            formatText(model.rows[row].text, language,
                       UiTextId::AirspaceGuardEvidenceRowFormat,
                       static_cast<unsigned long>(evidence.frameIndex),
                       static_cast<unsigned>(evidence.channel),
                       static_cast<int>(evidence.rssiDbm));
        }
        model.rows[row].selected = index == selection;
    }
    return model;
}

AirspaceGuardUiModel presentEvidenceDetail(
    const AirspaceGuardController& controller, UiLanguage language) {
    AirspaceGuardUiModel model{};
    model.headline = UiTextId::AirspaceGuardEvidenceDetailTitle;
    model.tone = AirspaceGuardUiTone::Finding;
    model.evidenceIncomplete = controller.evidenceIncomplete();
    model.note = model.evidenceIncomplete
        ? UiTextId::AirspaceGuardEvidenceIncomplete
        : UiTextId::AirspaceGuardPassiveOnly;
    const AirspaceFinding* finding = controller.selectedFinding();
    const AirspaceEvidenceRef* evidence = controller.selectedEvidence();
    if (finding == nullptr || evidence == nullptr) {
        model.headline = UiTextId::AirspaceGuardReportRejected;
        model.tone = AirspaceGuardUiTone::Error;
        return model;
    }
    if (finding->kind == AirspaceFindingKind::BleTrackerPresence &&
        !model.evidenceIncomplete) {
        model.note = UiTextId::AirspaceGuardBlePresenceOnly;
    }
    formatEvidenceSource(model.context, language, *finding,
                         controller.evidenceSelection());
    formatText(model.rows[0].text, language,
               finding->kind == AirspaceFindingKind::BleTrackerPresence
                   ? UiTextId::AirspaceGuardRecordFormat
                   : UiTextId::AirspaceGuardFrameFormat,
               static_cast<unsigned long>(evidence->frameIndex));
    if (finding->kind ==
        AirspaceFindingKind::WifiSsidSecurityConflict) {
        const AirspaceWifiSecurity security =
            controller.evidenceSelection() == 0U
                ? finding->primarySecurity : finding->relatedSecurity;
        formatText(model.rows[1].text, language,
                   UiTextId::AirspaceGuardSecurityChannelSignalFormat,
                   uiText(language, securityText(security)),
                   static_cast<unsigned>(evidence->channel),
                   static_cast<int>(evidence->rssiDbm));
        formatText(model.rows[2].text, language,
                   UiTextId::AirspaceGuardFindingOffsetFormat,
                   static_cast<unsigned long long>(
                       (evidence->monotonicUs - finding->firstUs) / 1000ULL));
    } else if (finding->kind == AirspaceFindingKind::WifiSsidChurn) {
        formatText(model.rows[1].text, language,
                   UiTextId::AirspaceGuardChannelSignalFormat,
                   static_cast<unsigned>(evidence->channel),
                   static_cast<int>(evidence->rssiDbm));
        formatText(model.rows[2].text, language,
                   UiTextId::AirspaceGuardFindingOffsetFormat,
                   static_cast<unsigned long long>(
                       (evidence->monotonicUs - finding->firstUs) / 1000ULL));
    } else if (finding->kind == AirspaceFindingKind::BleTrackerPresence) {
        formatText(model.rows[1].text, language,
                   UiTextId::AirspaceGuardProtocolSignalFormat,
                   uiText(language,
                          bleTrackerProtocolText(
                              finding->bleTrackerProtocol)),
                   static_cast<int>(evidence->rssiDbm));
        formatText(model.rows[2].text, language,
                   UiTextId::AirspaceGuardFindingOffsetFormat,
                   static_cast<unsigned long long>(
                       (evidence->monotonicUs - finding->firstUs) / 1000ULL));
    } else {
        formatText(model.rows[1].text, language,
                   UiTextId::AirspaceGuardChannelSignalFormat,
                   static_cast<unsigned>(evidence->channel),
                   static_cast<int>(evidence->rssiDbm));
        formatText(model.rows[2].text, language,
                   UiTextId::AirspaceGuardOffsetFormat,
                   static_cast<unsigned long long>(
                       (evidence->monotonicUs - finding->firstUs) / 1000ULL));
    }
    formatText(model.rows[3].text, language,
               UiTextId::AirspaceGuardConfidenceFormat,
               uiText(language, confidenceText(finding->confidence)),
               static_cast<unsigned>(finding->detectorVersion));
    model.rowCount = model.rows.size();
    return model;
}

}  // namespace

AirspaceGuardUiModel presentAirspaceGuard(
    const AirspaceGuardController& controller, UiLanguage language) {
    if (controller.loadStatus() != AirspaceGuardLoadStatus::Ready) {
        return {};
    }
    switch (controller.view()) {
        case AirspaceGuardView::Outcome:
            return presentOutcome(controller, language);
        case AirspaceGuardView::Finding:
            return presentFinding(controller, language);
        case AirspaceGuardView::EvidenceList:
            return presentEvidenceList(controller, language);
        case AirspaceGuardView::EvidenceDetail:
            return presentEvidenceDetail(controller, language);
    }
    return {};
}

}  // namespace leshy1::ui
