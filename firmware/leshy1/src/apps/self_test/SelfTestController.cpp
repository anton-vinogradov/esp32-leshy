#include "SelfTestController.h"

namespace leshy1::apps::self_test {

const char* selfTestModeName(SelfTestMode mode) {
    switch (mode) {
        case SelfTestMode::Quick: return "quick";
        case SelfTestMode::FullGuided: return "full_guided";
    }
    return "unknown";
}

const char* selfTestViewName(SelfTestView view) {
    switch (view) {
        case SelfTestView::ModeMenu: return "mode_menu";
        case SelfTestView::Preflight: return "preflight";
        case SelfTestView::VisualCheck: return "visual_check";
        case SelfTestView::Result: return "result";
    }
    return "unknown";
}

const char* selfTestVisualStateName(std::uint8_t state) {
    switch (state) {
        case 0: return "dialog_confirm";
        case 1: return "unavailable";
        case 2: return "degraded";
        case 3: return "error";
        case 4: return "running";
    }
    return "none";
}

const char* selfTestResultStatusName(SelfTestResultStatus status) {
    switch (status) {
        case SelfTestResultStatus::NotRun: return "not_run";
        case SelfTestResultStatus::Pass: return "pass";
        case SelfTestResultStatus::Fail: return "fail";
        case SelfTestResultStatus::Blocked: return "blocked";
        case SelfTestResultStatus::NotApplicable: return "not_applicable";
    }
    return "unknown";
}

bool SelfTestController::previousMode() {
    if (view_ != SelfTestView::ModeMenu || selection_ == 0) return false;
    --selection_;
    return true;
}

bool SelfTestController::nextMode() {
    if (view_ != SelfTestView::ModeMenu || selection_ + 1U >= kModeCount) {
        return false;
    }
    ++selection_;
    return true;
}

SelfTestMode SelfTestController::selectedMode() const {
    return selection_ == 0 ? SelfTestMode::Quick : SelfTestMode::FullGuided;
}

void SelfTestController::beginReport(SelfTestMode mode,
                                     const SelfTestFacts& facts,
                                     std::uint64_t startedUs) {
    const std::uint32_t nextSequence = report_.sequence + 1U;
    report_ = {};
    report_.mode = mode;
    report_.sequence = nextSequence;
    report_.startedUs = startedUs;
    report_.facts = facts;
    runAwaitingFinish_ = true;
    visualState_ = 0;
}

void SelfTestController::append(const char* id, SelfTestResultStatus status) {
    if (report_.checkCount >= report_.checks.size()) return;
    report_.checks[report_.checkCount++] = {id, status};
    if (status == SelfTestResultStatus::Pass) {
        ++report_.passed;
    } else if (status == SelfTestResultStatus::Fail) {
        ++report_.failed;
    } else if (status == SelfTestResultStatus::Blocked) {
        ++report_.blocked;
    } else if (status == SelfTestResultStatus::NotApplicable) {
        ++report_.notApplicable;
    }
}

void SelfTestController::evaluateCapabilityCoverage(
    const SelfTestFacts& facts) {
    append("full.s3.survey.persistence",
           facts.persistentSurveyReady ? SelfTestResultStatus::Pass
                                       : SelfTestResultStatus::Fail);
    append("full.s4.radio.ble.passive",
           facts.passiveBleReady ? SelfTestResultStatus::Pass
                                 : SelfTestResultStatus::Fail);
    append("full.s4.capture.wifi.passive",
           facts.passiveWifiCaptureReady ? SelfTestResultStatus::Pass
                                         : SelfTestResultStatus::Fail);
    append("full.s4.storage.enrolled",
           facts.enrolledStorageReady ? SelfTestResultStatus::Pass
                                      : SelfTestResultStatus::Fail);
    append("full.s4.library.recovery",
           facts.persistentLibraryReady ? SelfTestResultStatus::Pass
                                        : SelfTestResultStatus::Fail);
    append("full.s4.capture.persistence",
           facts.persistentWifiCaptureReady ? SelfTestResultStatus::Pass
                                            : SelfTestResultStatus::Fail);
    append("full.assembly.gps",
           facts.gpsDeclared ? SelfTestResultStatus::Blocked
                             : SelfTestResultStatus::NotApplicable);
    append("full.assembly.pn532",
           facts.pn532Declared ? SelfTestResultStatus::Blocked
                               : SelfTestResultStatus::NotApplicable);
    append("full.shield.ir",
           facts.irDeclared ? SelfTestResultStatus::Blocked
                            : SelfTestResultStatus::NotApplicable);
    append("full.s4.shield.receivers",
           !facts.shieldReceiversApplicable
               ? SelfTestResultStatus::NotApplicable
               : (!facts.shieldReceiverProbeComplete
                      ? SelfTestResultStatus::Blocked
                      : (facts.shieldReceiverProbePassed
                             ? SelfTestResultStatus::Pass
                             : SelfTestResultStatus::Fail)));
}

void SelfTestController::evaluateQuick(const SelfTestFacts& facts) {
    append("quick.build.identity",
           facts.buildIdentityPresent ? SelfTestResultStatus::Pass
                                      : SelfTestResultStatus::Fail);
    append("quick.board.profile",
           facts.profileMatched ? SelfTestResultStatus::Pass
                                : SelfTestResultStatus::Fail);
    append("quick.runtime.heap",
           facts.heapFree >= facts.heapFloor &&
                   facts.heapMinimum >= facts.heapFloor
               ? SelfTestResultStatus::Pass
               : SelfTestResultStatus::Fail);
    append("quick.display.ready",
           facts.displayReady ? SelfTestResultStatus::Pass
                              : SelfTestResultStatus::Fail);
    append("quick.input.frontend",
           facts.inputFrontendReady ? SelfTestResultStatus::Pass
                                    : SelfTestResultStatus::Fail);
    append("quick.input.queue",
           facts.inputQueueHealthy && facts.inputQueueDrops == 0
               ? SelfTestResultStatus::Pass
               : SelfTestResultStatus::Fail);
    append("quick.output.buzzer",
           facts.buzzerInactive ? SelfTestResultStatus::Pass
                                : SelfTestResultStatus::Fail);
    append("quick.resource.scope",
           facts.resourceScopeClean ? SelfTestResultStatus::Pass
                                    : SelfTestResultStatus::Fail);
}

void SelfTestController::finishResult() {
    report_.status = report_.failed != 0
                         ? SelfTestResultStatus::Fail
                         : (report_.blocked != 0
                                ? SelfTestResultStatus::Blocked
                                : SelfTestResultStatus::Pass);
    view_ = SelfTestView::Result;
}

bool SelfTestController::activate(const SelfTestFacts& facts,
                                  std::uint64_t startedUs) {
    if (view_ == SelfTestView::Result) return false;
    if (view_ == SelfTestView::ModeMenu &&
        selectedMode() == SelfTestMode::FullGuided) {
        view_ = SelfTestView::Preflight;
        return true;
    }

    if (view_ == SelfTestView::VisualCheck) {
        if (visualState_ + 1U < kVisualStateCount) {
            ++visualState_;
            return true;
        }
        report_.facts = facts;
        append("full.ui.common_states", SelfTestResultStatus::Pass);
        evaluateCapabilityCoverage(report_.facts);
        append("full.capability.coverage", SelfTestResultStatus::Blocked);
        finishResult();
        return true;
    }

    const SelfTestMode mode = view_ == SelfTestView::Preflight
                                  ? SelfTestMode::FullGuided
                                  : SelfTestMode::Quick;
    beginReport(mode, facts, startedUs);
    evaluateQuick(facts);
    if (mode == SelfTestMode::FullGuided) {
        view_ = SelfTestView::VisualCheck;
        return true;
    }
    finishResult();
    return true;
}

void SelfTestController::finishRun(std::uint64_t finishedUs) {
    if (!runAwaitingFinish_) return;
    report_.durationUs = finishedUs >= report_.startedUs
                             ? finishedUs - report_.startedUs
                             : 0;
    runAwaitingFinish_ = false;
}

bool SelfTestController::back() {
    if (view_ == SelfTestView::ModeMenu) return false;
    if (view_ == SelfTestView::VisualCheck) {
        report_.cancelled = true;
        runAwaitingFinish_ = false;
        view_ = SelfTestView::Preflight;
        return true;
    }
    view_ = SelfTestView::ModeMenu;
    return true;
}

}  // namespace leshy1::apps::self_test
