#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "kernel/runtime/Resources.h"

namespace leshy1::apps::self_test {

enum class SelfTestMode : std::uint8_t {
    Quick,
    FullGuided,
};

enum class SelfTestView : std::uint8_t {
    ModeMenu,
    Preflight,
    VisualCheck,
    ActiveChecks,
    Result,
};

enum class SelfTestResultStatus : std::uint8_t {
    NotRun,
    Pass,
    Fail,
    Blocked,
    NotApplicable,
};

const char* selfTestModeName(SelfTestMode mode);
const char* selfTestViewName(SelfTestView view);
const char* selfTestVisualStateName(std::uint8_t state);
const char* selfTestResultStatusName(SelfTestResultStatus status);

struct SelfTestFacts final {
    bool buildIdentityPresent = false;
    bool profileMatched = false;
    bool displayReady = false;
    bool touchFrontendReady = false;
    bool inputFrontendReady = false;
    bool inputQueueHealthy = false;
    bool buzzerInactive = false;
    bool resourceScopeClean = false;
    std::uint32_t heapFree = 0;
    std::uint32_t heapMinimum = 0;
    // Current product headroom gates. heapFree protects the next foreground
    // transition; heapMinimum catches cumulative pressure observed since boot.
    std::uint32_t heapFreeFloor = 80U * 1024U;
    std::uint32_t heapMinimumFloor = 64U * 1024U;
    std::uint32_t inputQueueDrops = 0;
    kernel::runtime::ResourceMask activeResources = 0;
    bool persistentSurveyReady = false;
    bool passiveBleReady = false;
    bool passiveWifiCaptureReady = false;
    bool enrolledStorageReady = false;
    bool persistentLibraryReady = false;
    bool persistentWifiCaptureReady = false;
    bool gpsDeclared = false;
    bool pn532Declared = false;
    bool irDeclared = false;
    bool shieldReceiversApplicable = false;
    bool shieldReceiverProbeComplete = false;
    bool shieldReceiverProbePassed = false;
    bool nrf24SpectrumExerciseComplete = false;
    bool nrf24SpectrumExercisePassed = false;
    bool cc1101SpectrumExerciseComplete = false;
    bool cc1101SpectrumExercisePassed = false;
    bool subGhzOokExerciseComplete = false;
    bool subGhzOokExercisePassed = false;
    bool subGhzFskExerciseComplete = false;
    bool subGhzFskExercisePassed = false;
    bool infraredReceiverExerciseComplete = false;
    bool infraredReceiverExercisePassed = false;
    bool persistentRecoveryAuditComplete = false;
    bool persistentRecoveryAuditPassed = false;
    bool libraryExportAuditComplete = false;
    bool libraryExportAuditPassed = false;
    bool capturePcapAuditComplete = false;
    bool capturePcapAuditApplicable = false;
    bool capturePcapAuditPassed = false;
    bool disposableCommitComplete = false;
    bool disposableCommitPassed = false;
    bool disposableRemountComplete = false;
    bool disposableRemountPassed = false;
    bool disposableExportComplete = false;
    bool disposableExportPassed = false;
    bool disposableCleanupComplete = false;
    bool disposableCleanupPassed = false;
    std::uint32_t disposableStorageWriteCalls = 0;
    std::uint64_t disposableStorageWriteBytes = 0;
};

struct SelfTestCheckResult final {
    const char* id = nullptr;
    SelfTestResultStatus status = SelfTestResultStatus::NotRun;
};

struct SelfTestReport final {
    static constexpr std::uint16_t kSchemaVersion = 1;
    static constexpr std::uint16_t kPlanVersion = 10;
    static constexpr std::size_t kCapacity = 32;

    SelfTestMode mode = SelfTestMode::Quick;
    SelfTestResultStatus status = SelfTestResultStatus::NotRun;
    std::uint32_t sequence = 0;
    std::uint64_t startedUs = 0;
    std::uint64_t durationUs = 0;
    std::array<SelfTestCheckResult, kCapacity> checks{};
    std::size_t checkCount = 0;
    std::uint8_t passed = 0;
    std::uint8_t failed = 0;
    std::uint8_t blocked = 0;
    std::uint8_t notApplicable = 0;
    bool readOnly = true;
    bool cancelled = false;
    SelfTestFacts facts{};
};

// Allocation-free application model shared by physical buttons and diagnostic
// Actions. Quick evaluates only already-observable facts and never starts a
// driver, radio, filesystem, or feedback output. Full/Guided deliberately ends
// blocked until every applicable capability has registered a check.
class SelfTestController final {
public:
    static constexpr std::uint8_t kModeCount = 2;
    static constexpr std::uint8_t kVisualStateCount = 5;

    bool previousMode();
    bool nextMode();
    bool activate(const SelfTestFacts& facts, std::uint64_t startedUs);
    bool completeActiveChecks(const SelfTestFacts& facts,
                              std::uint64_t finishedUs);
    void finishRun(std::uint64_t finishedUs);
    bool back();

    SelfTestView view() const { return view_; }
    std::uint8_t selection() const { return selection_; }
    SelfTestMode selectedMode() const;
    const SelfTestReport& report() const { return report_; }
    bool hasReport() const {
        return report_.status != SelfTestResultStatus::NotRun;
    }
    bool runAwaitingFinish() const { return runAwaitingFinish_; }
    std::uint8_t visualState() const { return visualState_; }

private:
    void beginReport(SelfTestMode mode, const SelfTestFacts& facts,
                     std::uint64_t startedUs);
    void append(const char* id, SelfTestResultStatus status);
    void evaluateQuick(const SelfTestFacts& facts);
    void evaluateCapabilityCoverage(const SelfTestFacts& facts);
    void finishResult();

    SelfTestView view_ = SelfTestView::ModeMenu;
    std::uint8_t selection_ = 0;
    SelfTestReport report_{};
    bool runAwaitingFinish_ = false;
    std::uint8_t visualState_ = 0;
};

}  // namespace leshy1::apps::self_test
