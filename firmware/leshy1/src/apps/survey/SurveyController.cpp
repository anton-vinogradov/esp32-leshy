#include "SurveyController.h"

#include <cstring>

namespace leshy1::apps::survey {

const char* surveyViewName(SurveyView view) {
    switch (view) {
        case SurveyView::List: return "list";
        case SurveyView::Detail: return "detail";
        case SurveyView::Filter: return "filter";
    }
    return "unknown";
}

const char* surveyFilterName(SurveyFilter filter) {
    switch (filter) {
        case SurveyFilter::All: return "all";
        case SurveyFilter::Wifi: return "wifi";
        case SurveyFilter::Ble: return "ble";
    }
    return "unknown";
}

void SurveyController::reset() {
    session_.reset();
    selection_ = 0;
    filterFocused_ = false;
    filter_ = SurveyFilter::All;
    draftFilter_ = SurveyFilter::All;
    view_ = SurveyView::List;
}

services::survey::SessionStatus SurveyController::start(const char* sessionId,
                                                        std::uint64_t monotonicUs) {
    selection_ = 0;
    filterFocused_ = false;
    filter_ = SurveyFilter::All;
    draftFilter_ = SurveyFilter::All;
    view_ = SurveyView::List;
    return session_.start(sessionId, monotonicUs);
}

services::survey::SessionStatus SurveyController::publish(
    const domain::observations::Observation& observation) {
    return session_.append(observation);
}

services::survey::SessionStatus SurveyController::stop(std::uint64_t monotonicUs) {
    return session_.stop(monotonicUs);
}

bool SurveyController::next() {
    if (view_ == SurveyView::Filter) {
        if (draftFilter_ == SurveyFilter::Ble) return false;
        draftFilter_ = static_cast<SurveyFilter>(
            static_cast<std::uint8_t>(draftFilter_) + 1U);
        return true;
    }
    if (view_ != SurveyView::List) return false;
    if (filterFocused_) {
        if (visibleSize() == 0) return false;
        filterFocused_ = false;
        selection_ = 0;
        return true;
    }
    if (selection_ + 1 >= visibleSize()) return false;
    ++selection_;
    return true;
}

bool SurveyController::previous() {
    if (view_ == SurveyView::Filter) {
        if (draftFilter_ == SurveyFilter::All) return false;
        draftFilter_ = static_cast<SurveyFilter>(
            static_cast<std::uint8_t>(draftFilter_) - 1U);
        return true;
    }
    if (view_ != SurveyView::List || filterFocused_) return false;
    if (selection_ == 0) {
        filterFocused_ = true;
        return true;
    }
    --selection_;
    return true;
}

bool SurveyController::openSelected() {
    if (view_ != SurveyView::List) return false;
    if (filterFocused_) {
        draftFilter_ = filter_;
        view_ = SurveyView::Filter;
        return true;
    }
    if (selected() == nullptr) return false;
    view_ = SurveyView::Detail;
    return true;
}

bool SurveyController::activateFilter() {
    if (view_ != SurveyView::Filter) return false;
    filter_ = draftFilter_;
    selection_ = 0;
    filterFocused_ = true;
    view_ = SurveyView::List;
    return true;
}

bool SurveyController::back() {
    if (view_ != SurveyView::Detail && view_ != SurveyView::Filter) return false;
    if (view_ == SurveyView::Filter) {
        draftFilter_ = filter_;
        filterFocused_ = true;
    }
    view_ = SurveyView::List;
    return true;
}

bool SurveyController::matchesFilter(
    const domain::observations::Observation& observation,
    SurveyFilter filter) const {
    if (filter == SurveyFilter::All) return true;
    if (filter == SurveyFilter::Wifi) {
        return observation.radio == domain::observations::RadioKind::Wifi;
    }
    return observation.radio == domain::observations::RadioKind::Ble;
}

std::size_t SurveyController::filterCount(SurveyFilter filter) const {
    std::size_t count = 0;
    for (std::size_t index = 0; index < session_.size(); ++index) {
        const auto* observation = session_.get(index);
        if (observation != nullptr && matchesFilter(*observation, filter)) ++count;
    }
    return count;
}

std::size_t SurveyController::visibleSize() const {
    return filterCount(filter_);
}

const domain::observations::Observation* SurveyController::visibleAt(
    std::size_t index) const {
    std::size_t visible = 0;
    for (std::size_t sessionIndex = 0; sessionIndex < session_.size(); ++sessionIndex) {
        const auto* observation = session_.get(sessionIndex);
        if (observation == nullptr || !matchesFilter(*observation, filter_)) continue;
        if (visible == index) return observation;
        ++visible;
    }
    return nullptr;
}

const domain::observations::Observation* SurveyController::selected() const {
    if (filterFocused_) return nullptr;
    return visibleAt(selection_);
}

ObservationHistory SurveyController::selectedHistory() const {
    ObservationHistory history;
    const auto* target = selected();
    if (target == nullptr || target->identityLength == 0) return history;
    for (std::size_t index = 0; index < session_.size(); ++index) {
        const auto* observation = session_.get(index);
        if (observation == nullptr || observation->radio != target->radio ||
            observation->identityLength != target->identityLength ||
            std::memcmp(observation->identity.data(), target->identity.data(),
                        target->identityLength) != 0) {
            continue;
        }
        if (!history.valid) {
            history.valid = true;
            history.minimumRssiDbm = observation->rssiDbm;
            history.maximumRssiDbm = observation->rssiDbm;
        }
        if (observation->rssiDbm < history.minimumRssiDbm) {
            history.minimumRssiDbm = observation->rssiDbm;
        }
        if (observation->rssiDbm > history.maximumRssiDbm) {
            history.maximumRssiDbm = observation->rssiDbm;
        }
        history.latestRssiDbm = observation->rssiDbm;
        ++history.sampleCount;
        if (history.retainedSamples < ObservationHistory::kSampleCapacity) {
            history.samples[history.retainedSamples++] = observation->rssiDbm;
        } else {
            for (std::size_t sample = 1;
                 sample < ObservationHistory::kSampleCapacity; ++sample) {
                history.samples[sample - 1U] = history.samples[sample];
            }
            history.samples.back() = observation->rssiDbm;
        }
    }
    return history;
}

}  // namespace leshy1::apps::survey
