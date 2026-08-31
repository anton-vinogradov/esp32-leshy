#include "SurveyWorkflow.h"

#include <cstring>

namespace leshy1::apps::survey {

const char* surveyWorkflowStateName(SurveyWorkflowState state) {
    switch (state) {
        case SurveyWorkflowState::Setup: return "setup";
        case SurveyWorkflowState::Running: return "running";
        case SurveyWorkflowState::Committing: return "committing";
        case SurveyWorkflowState::Result: return "result";
        case SurveyWorkflowState::Error: return "error";
    }
    return "error";
}

const char* surveyWorkflowStatusName(SurveyWorkflowStatus status) {
    switch (status) {
        case SurveyWorkflowStatus::Ready: return "ready";
        case SurveyWorkflowStatus::Started: return "started";
        case SurveyWorkflowStatus::Appended: return "appended";
        case SurveyWorkflowStatus::Cancelled: return "cancelled";
        case SurveyWorkflowStatus::Committed: return "committed";
        case SurveyWorkflowStatus::AlreadyCommitted: return "already_committed";
        case SurveyWorkflowStatus::InvalidState: return "invalid_state";
        case SurveyWorkflowStatus::SessionRejected: return "session_rejected";
        case SurveyWorkflowStatus::StoreRejected: return "store_rejected";
        case SurveyWorkflowStatus::RecoveryRejected: return "recovery_rejected";
        case SurveyWorkflowStatus::LibraryRejected: return "library_rejected";
    }
    return "invalid_state";
}

SurveyWorkflowStatus SurveyWorkflow::finish(SurveyWorkflowStatus status,
                                            SurveyWorkflowState state) {
    lastStatus_ = status;
    state_ = state;
    return status;
}

SurveyWorkflowStatus SurveyWorkflow::resetToSetup() {
    if (state_ == SurveyWorkflowState::Running ||
        state_ == SurveyWorkflowState::Committing) {
        return finish(SurveyWorkflowStatus::InvalidState, state_);
    }
    survey_.reset();
    generation_ = 0;
    lastStoreStatus_ = storage::SessionStoreStatus::Empty;
    return finish(SurveyWorkflowStatus::Ready, SurveyWorkflowState::Setup);
}

SurveyWorkflowStatus SurveyWorkflow::configure(bool persistent,
                                               bool simulated) {
    if (state_ != SurveyWorkflowState::Setup || (persistent && simulated)) {
        return finish(SurveyWorkflowStatus::InvalidState, state_);
    }
    persistent_ = persistent;
    simulated_ = simulated;
    return finish(SurveyWorkflowStatus::Ready, state_);
}

SurveyWorkflowStatus SurveyWorkflow::cancel() {
    if (state_ != SurveyWorkflowState::Setup &&
        state_ != SurveyWorkflowState::Running) {
        return finish(SurveyWorkflowStatus::InvalidState, state_);
    }
    survey_.reset();
    generation_ = 0;
    return finish(SurveyWorkflowStatus::Cancelled, SurveyWorkflowState::Setup);
}

SurveyWorkflowStatus SurveyWorkflow::start(const char* sessionId,
                                           std::uint64_t monotonicUs) {
    if (state_ != SurveyWorkflowState::Setup) {
        return finish(SurveyWorkflowStatus::InvalidState, state_);
    }
    survey_.reset();
    if (survey_.start(sessionId, monotonicUs) !=
        services::survey::SessionStatus::Started) {
        return finish(SurveyWorkflowStatus::SessionRejected,
                      SurveyWorkflowState::Error);
    }
    generation_ = 0;
    return finish(SurveyWorkflowStatus::Started,
                  SurveyWorkflowState::Running);
}

SurveyWorkflowStatus SurveyWorkflow::publish(
    const domain::observations::Observation& observation) {
    if (state_ != SurveyWorkflowState::Running) {
        return finish(SurveyWorkflowStatus::InvalidState, state_);
    }
    if (survey_.publish(observation) !=
        services::survey::SessionStatus::Appended) {
        return finish(SurveyWorkflowStatus::SessionRejected, state_);
    }
    return finish(SurveyWorkflowStatus::Appended, state_);
}

SurveyWorkflowStatus SurveyWorkflow::stopAndCommit(
    std::uint64_t monotonicUs) {
    if (state_ == SurveyWorkflowState::Result) {
        return finish(SurveyWorkflowStatus::AlreadyCommitted, state_);
    }
    if (state_ != SurveyWorkflowState::Running) {
        return finish(SurveyWorkflowStatus::InvalidState, state_);
    }
    if (workspace_ == nullptr) {
        return finish(SurveyWorkflowStatus::StoreRejected,
                      SurveyWorkflowState::Error);
    }
    state_ = SurveyWorkflowState::Committing;
    if (survey_.stop(monotonicUs) !=
        services::survey::SessionStatus::Stopped) {
        return finish(SurveyWorkflowStatus::SessionRejected,
                      SurveyWorkflowState::Error);
    }

    const storage::SessionStoreCommitResult committed =
        storage::commitNextSession(store_, *workspace_, survey_.session());
    lastStoreStatus_ = committed.status;
    if (!committed.complete()) {
        return finish(SurveyWorkflowStatus::StoreRejected,
                      SurveyWorkflowState::Error);
    }

    services::survey::SurveySession& staged = workspace_->validationSession;
    const storage::SessionStoreRecoveryResult recovered =
        storage::recoverSession(store_, *workspace_, &staged);
    lastStoreStatus_ = recovered.status;
    if (!recovered.valid() || recovered.generation != committed.generation ||
        staged.id() == nullptr || survey_.session().id() == nullptr ||
        std::strcmp(staged.id(), survey_.session().id()) != 0) {
        return finish(SurveyWorkflowStatus::RecoveryRejected,
                      SurveyWorkflowState::Error);
    }

    apps::library::LibraryController replacement;
    if (!replacement.replaceWithOwnedCopy(
            staged, reopened_, recovered.generation,
            apps::library::SessionIntegrity::Valid, persistent_, simulated_)) {
        return finish(SurveyWorkflowStatus::LibraryRejected,
                      SurveyWorkflowState::Error);
    }
    if (!replacement.copyScreenshotEntriesFrom(library_)) {
        return finish(SurveyWorkflowStatus::LibraryRejected,
                      SurveyWorkflowState::Error);
    }
    library_ = replacement;
    generation_ = recovered.generation;
    return finish(SurveyWorkflowStatus::Committed,
                  SurveyWorkflowState::Result);
}

}  // namespace leshy1::apps::survey
