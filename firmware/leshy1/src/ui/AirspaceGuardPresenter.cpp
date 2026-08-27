#include "AirspaceGuardPresenter.h"

#include <cstdio>

namespace leshy1::ui {

namespace {

using apps::guard::AirspaceGuardController;
using apps::guard::AirspaceGuardLoadStatus;
using apps::guard::AirspaceGuardView;
using services::guard::AirspaceConfidence;
using services::guard::AirspaceEvidenceRef;
using services::guard::AirspaceFinding;
using services::guard::AirspaceGuardStatus;

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

void formatSource(std::array<char, AirspaceGuardUiModel::kContextCapacity>& text,
                  UiLanguage language, const AirspaceFinding& finding) {
    formatText(text, language, UiTextId::AirspaceGuardSourceFormat,
               static_cast<unsigned>(finding.transmitter[0]),
               static_cast<unsigned>(finding.transmitter[1]),
               static_cast<unsigned>(finding.transmitter[2]),
               static_cast<unsigned>(finding.transmitter[3]),
               static_cast<unsigned>(finding.transmitter[4]),
               static_cast<unsigned>(finding.transmitter[5]));
}

void appendIncompleteRows(const AirspaceGuardController& controller,
                          UiLanguage language, AirspaceGuardUiModel& model) {
    if (model.rowCount < model.rows.size()) {
        formatText(model.rows[model.rowCount++].text, language,
                   UiTextId::AirspaceGuardCoverageFormat,
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
            break;
        case AirspaceGuardStatus::Inconclusive:
            model.headline = UiTextId::AirspaceGuardInconclusive;
            model.tone = AirspaceGuardUiTone::Caution;
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
    formatSource(model.context, language, *finding);
    formatText(model.rows[0].text, language,
               UiTextId::AirspaceGuardFindingPositionFormat,
               static_cast<unsigned>(controller.findingSelection() + 1U),
               static_cast<unsigned>(controller.findingCount()));
    formatText(model.rows[1].text, language,
               UiTextId::AirspaceGuardConfidenceFormat,
               uiText(language, confidenceText(finding->confidence)),
               static_cast<unsigned>(finding->detectorVersion));
    formatText(model.rows[2].text, language,
               UiTextId::AirspaceGuardObservedFormat,
               static_cast<unsigned>(finding->observed),
               static_cast<unsigned>(finding->threshold));
    if (controller.findingsDropped() != 0U) {
        formatText(model.rows[3].text, language,
                   UiTextId::AirspaceGuardDroppedFormat,
                   static_cast<unsigned long>(controller.findingsDropped()));
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
    formatSource(model.context, language, *finding);
    const std::size_t selection = controller.evidenceSelection();
    const std::size_t first = selection < model.rows.size()
        ? 0U : selection - model.rows.size() + 1U;
    const std::size_t remaining = finding->evidenceCount - first;
    model.rowCount = remaining < model.rows.size()
        ? remaining : model.rows.size();
    for (std::size_t row = 0; row < model.rowCount; ++row) {
        const std::size_t index = first + row;
        const AirspaceEvidenceRef& evidence = finding->evidence[index];
        formatText(model.rows[row].text, language,
                   UiTextId::AirspaceGuardEvidenceRowFormat,
                   static_cast<unsigned long>(evidence.frameIndex),
                   static_cast<unsigned>(evidence.channel),
                   static_cast<int>(evidence.rssiDbm));
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
    formatSource(model.context, language, *finding);
    formatText(model.rows[0].text, language,
               UiTextId::AirspaceGuardFrameFormat,
               static_cast<unsigned long>(evidence->frameIndex));
    formatText(model.rows[1].text, language,
               UiTextId::AirspaceGuardChannelSignalFormat,
               static_cast<unsigned>(evidence->channel),
               static_cast<int>(evidence->rssiDbm));
    formatText(model.rows[2].text, language,
               UiTextId::AirspaceGuardOffsetFormat,
               static_cast<unsigned long long>(
                   (evidence->monotonicUs - finding->firstUs) / 1000ULL));
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
