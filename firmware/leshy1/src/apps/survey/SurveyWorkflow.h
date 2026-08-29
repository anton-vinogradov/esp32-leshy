#pragma once

#include <cstdint>

#include "apps/library/LibraryController.h"
#include "apps/survey/SurveyController.h"
#include "storage/SessionStore.h"

namespace leshy1::apps::survey {

enum class SurveyWorkflowState : std::uint8_t {
    Setup,
    Running,
    Committing,
    Result,
    Error,
};

const char* surveyWorkflowStateName(SurveyWorkflowState state);

enum class SurveyWorkflowStatus : std::uint8_t {
    Ready,
    Started,
    Appended,
    Cancelled,
    Committed,
    AlreadyCommitted,
    InvalidState,
    SessionRejected,
    StoreRejected,
    RecoveryRejected,
    LibraryRejected,
};

const char* surveyWorkflowStatusName(SurveyWorkflowStatus status);

// Allocation-free product orchestration for WF-02/WF-03. Drivers publish through
// SurveyController while storage remains behind SessionStoreIo. The workflow owns
// no hardware directly, so the same state machine can run over bounded RAM in host
// tests and a guarded persistent backend on the board.
class SurveyWorkflow final {
public:
    SurveyWorkflow(SurveyController& survey, storage::SessionStoreIo& store,
                   storage::SessionStoreWorkspace& workspace,
                   services::survey::SurveySession& reopened,
                   apps::library::LibraryController& library,
                   bool persistent, bool simulated)
        : survey_(survey), store_(store), workspace_(&workspace),
          reopened_(reopened), library_(library), persistent_(persistent),
          simulated_(simulated) {}

    // Arduino shares the large codec backing store with other foreground-only
    // workspaces.  Keep the workflow object stable, but explicitly detach its
    // non-owning pointer before that union member's lifetime ends and rebind it
    // after reconstruction.  State/telemetry remain readable while detached;
    // persistence fails closed.
    void bindWorkspace(storage::SessionStoreWorkspace* workspace) {
        workspace_ = workspace;
    }
    bool workspaceBound() const { return workspace_ != nullptr; }

    SurveyWorkflowStatus resetToSetup();
    SurveyWorkflowStatus configure(bool persistent, bool simulated);
    SurveyWorkflowStatus cancel();
    SurveyWorkflowStatus start(const char* sessionId, std::uint64_t monotonicUs);
    SurveyWorkflowStatus publish(
        const domain::observations::Observation& observation);
    SurveyWorkflowStatus stopAndCommit(std::uint64_t monotonicUs);

    SurveyWorkflowState state() const { return state_; }
    SurveyWorkflowStatus lastStatus() const { return lastStatus_; }
    storage::SessionStoreStatus lastStoreStatus() const {
        return lastStoreStatus_;
    }
    std::uint32_t generation() const { return generation_; }
    bool persistent() const { return persistent_; }
    bool simulated() const { return simulated_; }

private:
    SurveyWorkflowStatus finish(SurveyWorkflowStatus status,
                                SurveyWorkflowState state);

    SurveyController& survey_;
    storage::SessionStoreIo& store_;
    storage::SessionStoreWorkspace* workspace_ = nullptr;
    services::survey::SurveySession& reopened_;
    apps::library::LibraryController& library_;
    bool persistent_ = false;
    bool simulated_ = false;
    SurveyWorkflowState state_ = SurveyWorkflowState::Setup;
    SurveyWorkflowStatus lastStatus_ = SurveyWorkflowStatus::Ready;
    storage::SessionStoreStatus lastStoreStatus_ =
        storage::SessionStoreStatus::Empty;
    std::uint32_t generation_ = 0;
};

}  // namespace leshy1::apps::survey
