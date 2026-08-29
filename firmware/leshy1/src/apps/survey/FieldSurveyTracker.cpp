#include "apps/survey/FieldSurveyTracker.h"

#include <cstring>

namespace leshy1::apps::survey {

const char* fieldSurveyVisitStatusName(FieldSurveyVisitStatus status) {
    switch (status) {
        case FieldSurveyVisitStatus::Empty: return "empty";
        case FieldSurveyVisitStatus::FirstVisit: return "first_visit";
        case FieldSurveyVisitStatus::Compared: return "compared";
        case FieldSurveyVisitStatus::Incomplete: return "incomplete";
    }
    return "incomplete";
}

bool shouldAutoPauseFieldVisit(const FieldSurveyCycleEvidence& evidence) {
    if (!evidence.fieldVisit || evidence.scanFailed ||
        evidence.stopRequested || evidence.selectedSourceMask == 0U) {
        return false;
    }
    const std::uint8_t covered = static_cast<std::uint8_t>(
        evidence.attemptedSourceMask | evidence.unavailableSourceMask);
    return (covered & evidence.selectedSourceMask) ==
           evidence.selectedSourceMask;
}

void FieldSurveyTracker::reset() {
    previous_.fill({});
    previousSize_ = 0;
    previousAvailable_ = false;
    comparePrevious_ = false;
    result_ = {};
}

void FieldSurveyTracker::clearPrevious() {
    previous_.fill({});
    previousSize_ = 0;
    previousAvailable_ = false;
    comparePrevious_ = false;
    result_ = {};
}

bool FieldSurveyTracker::capturePrevious(
    const services::survey::SurveySession& session,
    FieldSurveyCatalog& scratch) {
    clearPrevious();
    if (session.state() != services::survey::SessionState::Stopped ||
        session.id() == nullptr || std::strcmp(session.id(), kSessionId) != 0) {
        return false;
    }
    if (scratch.build(session) != FieldSurveyBuildStatus::Complete ||
        !scratch.complete()) {
        scratch.reset();
        return false;
    }
    previousSize_ = scratch.size();
    for (std::size_t index = 0; index < previousSize_; ++index) {
        const FieldSurveyRecord* record = scratch.get(index);
        if (record == nullptr) {
            clearPrevious();
            return false;
        }
        previous_[index].kind = record->kind;
        previous_[index].identity = record->identity;
        previous_[index].identityLength = record->identityLength;
    }
    scratch.reset();
    previousAvailable_ = true;
    comparePrevious_ = true;
    return true;
}

bool FieldSurveyTracker::toggleComparePrevious() {
    if (!previousAvailable_) return false;
    comparePrevious_ = !comparePrevious_;
    result_ = {};
    return true;
}

bool FieldSurveyTracker::baselineContains(
    const FieldSurveyRecord& record) const {
    for (std::size_t index = 0; index < previousSize_; ++index) {
        const BaselineIdentity& baseline = previous_[index];
        if (baseline.kind == record.kind &&
            baseline.identityLength == record.identityLength &&
            std::memcmp(baseline.identity.data(), record.identity.data(),
                        record.identityLength) == 0) {
            return true;
        }
    }
    return false;
}

bool FieldSurveyTracker::currentContains(
    const FieldSurveyCatalog& current,
    const BaselineIdentity& baseline) const {
    return current.indexOf(baseline.kind, baseline.identity.data(),
                           baseline.identityLength) < current.size();
}

const FieldSurveyVisitResult& FieldSurveyTracker::completeVisit(
    const services::survey::SurveySession& session,
    FieldSurveyCatalog& scratch) {
    result_ = {};
    result_.buildStatus = scratch.build(session);
    result_.currentUnique = static_cast<std::uint16_t>(scratch.size());
    if (result_.buildStatus != FieldSurveyBuildStatus::Complete ||
        !scratch.complete()) {
        result_.status = FieldSurveyVisitStatus::Incomplete;
        return result_;
    }

    for (std::size_t index = 0; index < scratch.size(); ++index) {
        const FieldSurveyRecord* record = scratch.get(index);
        if (record == nullptr) {
            result_.status = FieldSurveyVisitStatus::Incomplete;
            return result_;
        }
        switch (record->kind) {
            case FieldSurveyEntityKind::WifiAccessPoint:
                ++result_.wifiAccessPoints;
                break;
            case FieldSurveyEntityKind::WifiStation:
                ++result_.wifiStations;
                break;
            case FieldSurveyEntityKind::BleDevice:
                ++result_.bleDevices;
                break;
        }
    }

    if (!comparePrevious()) {
        result_.status = FieldSurveyVisitStatus::FirstVisit;
        result_.newThisVisit = result_.currentUnique;
        return result_;
    }

    result_.baselineUnique = static_cast<std::uint16_t>(previousSize_);
    for (std::size_t index = 0; index < scratch.size(); ++index) {
        const FieldSurveyRecord* record = scratch.get(index);
        if (record != nullptr && baselineContains(*record)) {
            ++result_.seenAgain;
        } else {
            ++result_.newThisVisit;
        }
    }
    for (std::size_t index = 0; index < previousSize_; ++index) {
        if (!currentContains(scratch, previous_[index])) {
            ++result_.missingThisVisit;
        }
    }
    result_.status = FieldSurveyVisitStatus::Compared;
    return result_;
}

const FieldSurveyVisitResult& FieldSurveyTracker::rejectVisit(
    FieldSurveyBuildStatus status) {
    result_ = {};
    result_.status = FieldSurveyVisitStatus::Incomplete;
    result_.buildStatus = status;
    return result_;
}

}  // namespace leshy1::apps::survey
