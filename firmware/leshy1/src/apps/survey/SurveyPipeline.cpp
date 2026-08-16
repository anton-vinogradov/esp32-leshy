#include "SurveyPipeline.h"

#include "services/survey/SurveySession.h"

namespace leshy1::apps::survey {

const char* surveyPipelineStatusName(SurveyPipelineStatus status) {
    switch (status) {
        case SurveyPipelineStatus::Ready: return "ready";
        case SurveyPipelineStatus::Started: return "started";
        case SurveyPipelineStatus::Queued: return "queued";
        case SurveyPipelineStatus::Drained: return "drained";
        case SurveyPipelineStatus::Dropped: return "dropped";
        case SurveyPipelineStatus::Cancelled: return "cancelled";
        case SurveyPipelineStatus::Committed: return "committed";
        case SurveyPipelineStatus::AlreadyCommitted: return "already_committed";
        case SurveyPipelineStatus::InvalidState: return "invalid_state";
        case SurveyPipelineStatus::WorkflowRejected: return "workflow_rejected";
    }
    return "invalid_state";
}

SurveyPipelineStatus SurveyPipeline::finish(SurveyPipelineStatus status) {
    lastStatus_ = status;
    return status;
}

void SurveyPipeline::resetProgress() {
    queue_.reset();
    received_ = 0;
    forwarded_ = 0;
    capacityDropped_ = 0;
    rejected_ = 0;
    oldestQueuedUs_ = 0;
    lastTrigger_ = services::survey::SessionBatchTrigger::None;
}

SurveyPipelineStatus SurveyPipeline::resetToSetup() {
    if (workflow_.resetToSetup() != SurveyWorkflowStatus::Ready) {
        return finish(SurveyPipelineStatus::InvalidState);
    }
    resetProgress();
    return finish(SurveyPipelineStatus::Ready);
}

SurveyPipelineStatus SurveyPipeline::cancel() {
    if (workflow_.cancel() != SurveyWorkflowStatus::Cancelled) {
        return finish(SurveyPipelineStatus::InvalidState);
    }
    resetProgress();
    return finish(SurveyPipelineStatus::Cancelled);
}

SurveyPipelineStatus SurveyPipeline::start(const char* sessionId,
                                           std::uint64_t monotonicUs) {
    if (workflow_.state() != SurveyWorkflowState::Setup) {
        return finish(SurveyPipelineStatus::InvalidState);
    }
    resetProgress();
    if (workflow_.start(sessionId, monotonicUs) !=
        SurveyWorkflowStatus::Started) {
        return finish(SurveyPipelineStatus::WorkflowRejected);
    }
    return finish(SurveyPipelineStatus::Started);
}

SurveyPipelineStatus SurveyPipeline::enqueue(
    const domain::observations::Observation& observation) {
    if (workflow_.state() != SurveyWorkflowState::Running) {
        return finish(SurveyPipelineStatus::InvalidState);
    }
    ++received_;
    if (forwarded_ + queue_.size() >=
        services::survey::SurveySession::kObservationCapacity) {
        ++capacityDropped_;
        return finish(SurveyPipelineStatus::Dropped);
    }
    if (!queue_.push(observation)) {
        return finish(SurveyPipelineStatus::Dropped);
    }
    if (oldestQueuedUs_ == 0 || observation.monotonicUs < oldestQueuedUs_) {
        oldestQueuedUs_ = observation.monotonicUs == 0 ? 1
                                                       : observation.monotonicUs;
    }
    return finish(SurveyPipelineStatus::Queued);
}

SurveyPipelineStatus SurveyPipeline::drain(
    std::size_t maximumObservations) {
    if (workflow_.state() != SurveyWorkflowState::Running ||
        maximumObservations == 0) {
        return finish(SurveyPipelineStatus::InvalidState);
    }
    domain::observations::Observation observation;
    std::size_t drained = 0;
    while (drained < maximumObservations && queue_.pop(&observation)) {
        if (workflow_.publish(observation) != SurveyWorkflowStatus::Appended) {
            ++rejected_;
            observation = {};
            return finish(SurveyPipelineStatus::WorkflowRejected);
        }
        ++forwarded_;
        ++drained;
        observation = {};
    }
    if (queue_.empty()) oldestQueuedUs_ = 0;
    return finish(SurveyPipelineStatus::Drained);
}

SurveyPipelineStatus SurveyPipeline::stopAndCommit(
    std::uint64_t monotonicUs) {
    if (workflow_.state() == SurveyWorkflowState::Result) {
        const SurveyWorkflowStatus status = workflow_.stopAndCommit(monotonicUs);
        return finish(status == SurveyWorkflowStatus::AlreadyCommitted
                          ? SurveyPipelineStatus::AlreadyCommitted
                          : SurveyPipelineStatus::WorkflowRejected);
    }
    if (workflow_.state() != SurveyWorkflowState::Running) {
        return finish(SurveyPipelineStatus::InvalidState);
    }
    if (!queue_.empty() &&
        drain(services::survey::ObservationQueue::kCapacity) !=
            SurveyPipelineStatus::Drained) {
        return finish(SurveyPipelineStatus::WorkflowRejected);
    }
    lastTrigger_ = services::survey::sessionBatchTrigger(
        policy_, static_cast<std::size_t>(forwarded_), 0, oldestQueuedUs_,
        monotonicUs, true, false);
    const SurveyWorkflowStatus status = workflow_.stopAndCommit(monotonicUs);
    if (status == SurveyWorkflowStatus::Committed) {
        return finish(SurveyPipelineStatus::Committed);
    }
    if (status == SurveyWorkflowStatus::AlreadyCommitted) {
        return finish(SurveyPipelineStatus::AlreadyCommitted);
    }
    return finish(SurveyPipelineStatus::WorkflowRejected);
}

SurveyPipelineProgress SurveyPipeline::progress() const {
    return {
        received_,
        queue_.pushed(),
        forwarded_,
        queue_.dropped() + capacityDropped_,
        rejected_,
        queue_.size(),
        queue_.highWater(),
        lastTrigger_,
    };
}

}  // namespace leshy1::apps::survey
