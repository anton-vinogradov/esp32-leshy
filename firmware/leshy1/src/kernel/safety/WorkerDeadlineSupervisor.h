#pragma once

#include <cstdint>

namespace leshy1::kernel::safety {

enum class SupervisedWorker : std::uint8_t {
    None = 0,
    ProductSurveyPreparation = 1,
    ProductSurvey = 2,
    WifiCaptureStore = 3,
    SubGhzCaptureStore = 4,
    InfraredCaptureStore = 5,
};

struct WorkerDeadlineSnapshot final {
    SupervisedWorker activeWorker = SupervisedWorker::None;
    SupervisedWorker lastExpiredWorker = SupervisedWorker::None;
    bool armed = false;
    bool expired = false;
    std::uint64_t lastHeartbeatUs = 0;
    std::uint64_t deadlineUs = 0;
    std::uint64_t lastObservedAgeUs = 0;
    std::uint32_t armCount = 0;
    std::uint32_t heartbeatCount = 0;
    std::uint32_t tripCount = 0;
};

const char* supervisedWorkerName(SupervisedWorker worker);

// A bounded, allocation-free deadline monitor. Synchronization belongs to the
// platform adapter so this core remains host-testable and usable from either
// RTOS tasks or a cooperative runtime.
class WorkerDeadlineSupervisor final {
public:
    bool arm(SupervisedWorker worker, std::uint64_t nowUs,
             std::uint64_t deadlineUs);
    bool heartbeat(SupervisedWorker worker, std::uint64_t nowUs);
    bool disarm(SupervisedWorker worker);
    bool evaluate(std::uint64_t nowUs);

    WorkerDeadlineSnapshot snapshot() const { return state_; }

private:
    WorkerDeadlineSnapshot state_{};
};

}  // namespace leshy1::kernel::safety
