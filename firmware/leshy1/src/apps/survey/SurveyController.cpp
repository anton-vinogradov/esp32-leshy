#include "SurveyController.h"

namespace leshy1::apps::survey {

void SurveyController::reset() {
    session_.reset();
    selection_ = 0;
    view_ = SurveyView::List;
}

services::survey::SessionStatus SurveyController::start(const char* sessionId,
                                                        std::uint64_t monotonicUs) {
    selection_ = 0;
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
    if (view_ != SurveyView::List || selection_ + 1 >= session_.size()) return false;
    ++selection_;
    return true;
}

bool SurveyController::previous() {
    if (view_ != SurveyView::List || selection_ == 0) return false;
    --selection_;
    return true;
}

bool SurveyController::openSelected() {
    if (view_ != SurveyView::List || selected() == nullptr) return false;
    view_ = SurveyView::Detail;
    return true;
}

bool SurveyController::back() {
    if (view_ != SurveyView::Detail) return false;
    view_ = SurveyView::List;
    return true;
}

const domain::observations::Observation* SurveyController::selected() const {
    return session_.get(selection_);
}

}  // namespace leshy1::apps::survey
