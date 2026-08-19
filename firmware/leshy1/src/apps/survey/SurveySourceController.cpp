#include "SurveySourceController.h"

namespace leshy1::apps::survey {
namespace {

using domain::hardware::CapabilityRecord;
using domain::hardware::CapabilityState;
using domain::hardware::HardwareInventory;

SurveySourceState sourceState(const CapabilityRecord* record) {
    if (record == nullptr) return SurveySourceState::Unavailable;
    switch (record->state) {
        case CapabilityState::Available:
            return SurveySourceState::Available;
        case CapabilityState::Conflicted:
            return SurveySourceState::Conflicted;
        case CapabilityState::Fault:
            return SurveySourceState::Fault;
        case CapabilityState::Declared:
        case CapabilityState::Detected:
        case CapabilityState::Unknown:
            return SurveySourceState::Unavailable;
    }
    return SurveySourceState::Unavailable;
}

SurveySourceOption option(const char* id, SurveySourceKind kind,
                          const CapabilityRecord* record) {
    const SurveySourceState state = sourceState(record);
    return {id, kind, state,
            record == nullptr || record->reason == nullptr
                ? "capability_not_reported"
                : record->reason,
            state == SurveySourceState::Available};
}

}  // namespace

const char* surveySetupViewName(SurveySetupView view) {
    switch (view) {
        case SurveySetupView::Plan: return "plan";
        case SurveySetupView::Sources: return "sources";
    }
    return "unknown";
}

const char* surveySourceKindName(SurveySourceKind kind) {
    switch (kind) {
        case SurveySourceKind::Wifi: return "wifi";
        case SurveySourceKind::Ble: return "ble";
    }
    return "unknown";
}

const char* surveySourceScopeName(SurveySourceScope scope) {
    switch (scope) {
        case SurveySourceScope::All: return "all";
        case SurveySourceScope::WifiOnly: return "wifi";
        case SurveySourceScope::BleOnly: return "ble";
    }
    return "unknown";
}

const char* surveySourceStateName(SurveySourceState state) {
    switch (state) {
        case SurveySourceState::Available: return "available";
        case SurveySourceState::Unavailable: return "unavailable";
        case SurveySourceState::Conflicted: return "conflicted";
        case SurveySourceState::Fault: return "fault";
    }
    return "unknown";
}

const char* surveySetupActivationName(SurveySetupActivation activation) {
    switch (activation) {
        case SurveySetupActivation::None: return "none";
        case SurveySetupActivation::OpenedSources: return "opened_sources";
        case SurveySetupActivation::OpenedSpectrum: return "opened_spectrum";
        case SurveySetupActivation::SourceChanged: return "source_changed";
        case SurveySetupActivation::SourceUnavailable:
            return "source_unavailable";
        case SurveySetupActivation::StartRequested: return "start_requested";
        case SurveySetupActivation::StartBlocked: return "start_blocked";
    }
    return "unknown";
}

void SurveySourceController::rebuild(const HardwareInventory& inventory,
                                     bool simulatedPreview,
                                     SurveySourceScope scope) {
    const CapabilityRecord* wifi = inventory.find("radio.wifi");
    const CapabilityRecord* persistent =
        inventory.find("survey.persistent_passive");
    if (sourceState(wifi) != SurveySourceState::Available &&
        sourceState(persistent) == SurveySourceState::Available) {
        wifi = persistent;
    }
    sources_[0] = option("wifi", SurveySourceKind::Wifi, wifi);
    sources_[1] = option("ble", SurveySourceKind::Ble,
                         inventory.find("radio.ble"));
    scope_ = scope;
    if (scope_ != SurveySourceScope::All) {
        for (SurveySourceOption& source : sources_) {
            const bool inScope =
                (scope_ == SurveySourceScope::WifiOnly &&
                 source.kind == SurveySourceKind::Wifi) ||
                (scope_ == SurveySourceScope::BleOnly &&
                 source.kind == SurveySourceKind::Ble);
            source.selected = inScope && source.available();
        }
    }
    view_ = SurveySetupView::Plan;
    selection_ = 0;
    simulatedPreview_ = simulatedPreview;
}

bool SurveySourceController::previous() {
    if (selection_ == 0) return false;
    --selection_;
    return true;
}

bool SurveySourceController::next() {
    const std::size_t count = view_ == SurveySetupView::Plan
        ? planItemCount() : sources_.size();
    if (selection_ + 1U >= count) return false;
    ++selection_;
    return true;
}

SurveySetupActivation SurveySourceController::activate() {
    if (view_ == SurveySetupView::Plan) {
        if (scope_ != SurveySourceScope::All) {
            return canStart() ? SurveySetupActivation::StartRequested
                              : SurveySetupActivation::StartBlocked;
        }
        if (selection_ == 0) {
            view_ = SurveySetupView::Sources;
            selection_ = 0;
            return SurveySetupActivation::OpenedSources;
        }
        if (selection_ == 1) {
            return SurveySetupActivation::OpenedSpectrum;
        }
        return canStart() ? SurveySetupActivation::StartRequested
                          : SurveySetupActivation::StartBlocked;
    }

    SurveySourceOption* source = selection_ < sources_.size()
        ? &sources_[selection_] : nullptr;
    if (source == nullptr) return SurveySetupActivation::None;
    if (!source->available()) return SurveySetupActivation::SourceUnavailable;
    source->selected = !source->selected;
    return SurveySetupActivation::SourceChanged;
}

bool SurveySourceController::back() {
    if (view_ != SurveySetupView::Sources) return false;
    view_ = SurveySetupView::Plan;
    selection_ = 0;
    return true;
}

const SurveySourceOption* SurveySourceController::get(std::size_t index) const {
    return index < sources_.size() ? &sources_[index] : nullptr;
}

const SurveySourceOption* SurveySourceController::find(
    SurveySourceKind kind) const {
    for (const SurveySourceOption& source : sources_) {
        if (source.kind == kind) return &source;
    }
    return nullptr;
}

std::size_t SurveySourceController::selectedCount() const {
    std::size_t count = 0;
    for (const SurveySourceOption& source : sources_) {
        if (source.available() && source.selected) ++count;
    }
    return count;
}

std::uint8_t SurveySourceController::selectedMask() const {
    std::uint8_t mask = 0;
    for (std::size_t index = 0; index < sources_.size(); ++index) {
        if (sources_[index].available() && sources_[index].selected) {
            mask |= static_cast<std::uint8_t>(1U << index);
        }
    }
    return mask;
}

}  // namespace leshy1::apps::survey
