#include "kernel/safety/WorkerDeadlineSupervisor.h"

namespace leshy1::kernel::safety {

const char* supervisedWorkerName(SupervisedWorker worker) {
    switch (worker) {
        case SupervisedWorker::ProductSurveyPreparation:
            return "product_survey_preparation";
        case SupervisedWorker::ProductSurvey:
            return "product_survey";
        case SupervisedWorker::WifiCaptureStore:
            return "wifi_capture_store";
        case SupervisedWorker::SubGhzCaptureStore:
            return "subghz_capture_store";
        case SupervisedWorker::InfraredCaptureStore:
            return "infrared_capture_store";
        case SupervisedWorker::TargetsStore:
            return "targets_store";
        case SupervisedWorker::AirspaceGuardBle:
            return "airspace_guard_ble";
        case SupervisedWorker::None:
        default:
            return "none";
    }
}

bool WorkerDeadlineSupervisor::arm(SupervisedWorker worker,
                                   std::uint64_t nowUs,
                                   std::uint64_t deadlineUs) {
    if (state_.armed || worker == SupervisedWorker::None || nowUs == 0 ||
        deadlineUs == 0) {
        return false;
    }
    state_.activeWorker = worker;
    state_.armed = true;
    state_.expired = false;
    state_.lastHeartbeatUs = nowUs;
    state_.deadlineUs = deadlineUs;
    state_.lastObservedAgeUs = 0;
    ++state_.armCount;
    ++state_.heartbeatCount;
    return true;
}

bool WorkerDeadlineSupervisor::heartbeat(SupervisedWorker worker,
                                         std::uint64_t nowUs) {
    if (!state_.armed || state_.expired || worker != state_.activeWorker ||
        nowUs == 0 || nowUs < state_.lastHeartbeatUs) {
        return false;
    }
    state_.lastHeartbeatUs = nowUs;
    state_.lastObservedAgeUs = 0;
    ++state_.heartbeatCount;
    return true;
}

bool WorkerDeadlineSupervisor::disarm(SupervisedWorker worker) {
    if (!state_.armed || worker != state_.activeWorker) return false;
    state_.activeWorker = SupervisedWorker::None;
    state_.armed = false;
    return true;
}

bool WorkerDeadlineSupervisor::evaluate(std::uint64_t nowUs) {
    if (!state_.armed || state_.expired) return false;
    if (nowUs < state_.lastHeartbeatUs) {
        state_.lastObservedAgeUs = state_.deadlineUs;
    } else {
        state_.lastObservedAgeUs = nowUs - state_.lastHeartbeatUs;
    }
    if (state_.lastObservedAgeUs < state_.deadlineUs) return false;
    state_.expired = true;
    state_.lastExpiredWorker = state_.activeWorker;
    ++state_.tripCount;
    return true;
}

}  // namespace leshy1::kernel::safety
