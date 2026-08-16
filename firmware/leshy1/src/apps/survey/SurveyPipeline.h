#pragma once

#include <cstddef>
#include <cstdint>

#include "apps/survey/SurveyWorkflow.h"
#include "services/survey/ObservationQueue.h"
#include "services/survey/SessionBatchPolicy.h"

namespace leshy1::apps::survey {

enum class SurveyPipelineStatus : std::uint8_t {
    Ready,
    Started,
    Queued,
    Drained,
    Dropped,
    Cancelled,
    Committed,
    AlreadyCommitted,
    InvalidState,
    WorkflowRejected,
};

const char* surveyPipelineStatusName(SurveyPipelineStatus status);

struct SurveyPipelineProgress final {
    std::uint64_t received = 0;
    std::uint64_t queued = 0;
    std::uint64_t forwarded = 0;
    std::uint64_t dropped = 0;
    std::uint64_t rejected = 0;
    std::size_t queueDepth = 0;
    std::size_t queueHighWater = 0;
    services::survey::SessionBatchTrigger trigger =
        services::survey::SessionBatchTrigger::None;
};

// Allocation-free source→FIFO→Session workflow boundary. Source drivers enqueue
// normalized observations and a worker drains them outside driver callbacks. The
// same counters/state are suitable for simulated HIL and real passive adapters.
class SurveyPipeline final {
public:
    SurveyPipeline(SurveyWorkflow& workflow,
                   services::survey::ObservationQueue& queue,
                   services::survey::SessionBatchPolicy policy = {})
        : workflow_(workflow), queue_(queue), policy_(policy) {}

    SurveyPipelineStatus resetToSetup();
    SurveyPipelineStatus cancel();
    SurveyPipelineStatus start(const char* sessionId,
                               std::uint64_t monotonicUs);
    SurveyPipelineStatus enqueue(
        const domain::observations::Observation& observation);
    SurveyPipelineStatus drain(std::size_t maximumObservations);
    SurveyPipelineStatus stopAndCommit(std::uint64_t monotonicUs);

    SurveyPipelineStatus lastStatus() const { return lastStatus_; }
    SurveyPipelineProgress progress() const;
    const services::survey::SessionBatchPolicy& policy() const {
        return policy_;
    }

private:
    void resetProgress();
    SurveyPipelineStatus finish(SurveyPipelineStatus status);

    SurveyWorkflow& workflow_;
    services::survey::ObservationQueue& queue_;
    services::survey::SessionBatchPolicy policy_{};
    SurveyPipelineStatus lastStatus_ = SurveyPipelineStatus::Ready;
    std::uint64_t received_ = 0;
    std::uint64_t forwarded_ = 0;
    std::uint64_t capacityDropped_ = 0;
    std::uint64_t rejected_ = 0;
    std::uint64_t oldestQueuedUs_ = 0;
    services::survey::SessionBatchTrigger lastTrigger_ =
        services::survey::SessionBatchTrigger::None;
};

}  // namespace leshy1::apps::survey
