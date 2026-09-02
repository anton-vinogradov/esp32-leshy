#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>

#include "apps/lab/InfraredReplay.h"

namespace {

using namespace leshy1::apps::lab;
using leshy1::domain::captures::InfraredDecode;
using leshy1::domain::captures::InfraredProtocol;

constexpr std::uint32_t kNecCode = 0xCB34ED12UL;
constexpr std::uint32_t kNecExtendedCode = 0xA9561234UL;

InfraredDecode necDecode() {
    return {InfraredProtocol::Nec, kNecCode, 0x12U, 0x34U, true};
}

InfraredDecode extendedDecode() {
    return {InfraredProtocol::NecExtended, kNecExtendedCode,
            0x1234U, 0x56U, true};
}

InfraredReplaySource validSource() {
    InfraredReplaySource source{};
    source.capturePresent = true;
    source.persistent = true;
    source.generation = 7U;
    source.decode = necDecode();
    return source;
}

class FakeOutput final : public InfraredReplayOutput {
public:
    bool begin(const InfraredReplayPlan& plan,
               std::uint64_t startedUs) override {
        ++beginCalls;
        copiedPlan = plan;
        lastStartedUs = startedUs;
        active = beginResult;
        state = beginResult ? InfraredReplayOutputState::Running
                            : InfraredReplayOutputState::Fault;
        return beginResult;
    }

    InfraredReplayOutputState service(std::uint64_t) override {
        ++serviceCalls;
        return state;
    }

    bool stop() override {
        ++stopCalls;
        if (stopResult) active = false;
        return stopResult;
    }

    bool inactive() const override { return !active; }

    InfraredReplayPlan copiedPlan{};
    InfraredReplayOutputState state = InfraredReplayOutputState::Idle;
    std::uint64_t lastStartedUs = 0U;
    std::uint32_t beginCalls = 0U;
    std::uint32_t serviceCalls = 0U;
    std::uint32_t stopCalls = 0U;
    bool beginResult = true;
    bool stopResult = true;
    bool active = false;
};

void buildsCanonicalNecPlans() {
    InfraredReplayPlan plan{};
    assert(buildInfraredReplayPlan(necDecode(), &plan));
    assert(plan.protocol == InfraredProtocol::Nec);
    assert(plan.rawCode == kNecCode);
    assert(plan.carrierHz == 38000U);
    assert(plan.dutyPercent == 33U);
    assert(plan.pulseCount == 67U);
    assert(plan.pulseDurationsUs[0] == 9000U);
    assert(plan.pulseDurationsUs[1] == 4500U);
    assert(plan.pulseDurationsUs[2] == 560U);
    assert(plan.pulseDurationsUs[3] == 560U);
    assert(plan.pulseDurationsUs[4] == 560U);
    assert(plan.pulseDurationsUs[5] == 1690U);
    assert(plan.pulseDurationsUs[66] == 560U);
    assert(plan.totalDurationUs > 0U);
    assert(plan.totalDurationUs <= kInfraredReplayMaximumEmissionUs);

    assert(buildInfraredReplayPlan(extendedDecode(), &plan));
    assert(plan.protocol == InfraredProtocol::NecExtended);
    assert(plan.address == 0x1234U);
}

void rejectsInvalidDecodes() {
    InfraredReplayPlan plan{};
    InfraredDecode decode = necDecode();
    decode.integrityValid = false;
    assert(!buildInfraredReplayPlan(decode, &plan));
    decode = necDecode();
    decode.rawCode ^= 1UL << 24U;
    assert(!buildInfraredReplayPlan(decode, &plan));
    decode = necDecode();
    decode.protocol = InfraredProtocol::NecRepeat;
    assert(!buildInfraredReplayPlan(decode, &plan));
    assert(!buildInfraredReplayPlan(necDecode(), nullptr));
}

void refusesUnsafeSources() {
    InfraredReplayController controller;
    InfraredReplaySource source = validSource();
    source.capturePresent = false;
    assert(!controller.prepare(source));
    assert(controller.report().refusal ==
           InfraredReplayRefusal::CaptureMissing);
    assert(std::strcmp(infraredReplayRefusalName(controller.report().refusal),
                       "capture_missing") == 0);

    source = validSource();
    source.persistent = false;
    assert(!controller.prepare(source));
    assert(controller.report().refusal ==
           InfraredReplayRefusal::NotPersistent);
    source = validSource();
    source.simulated = true;
    assert(!controller.prepare(source));
    assert(controller.report().refusal == InfraredReplayRefusal::Simulated);
    source = validSource();
    source.recoveredFallback = true;
    assert(!controller.prepare(source));
    assert(controller.report().refusal ==
           InfraredReplayRefusal::RecoveredFallback);
    source = validSource();
    source.generation = 0U;
    assert(!controller.prepare(source));
    assert(controller.report().refusal ==
           InfraredReplayRefusal::GenerationMissing);
    source = validSource();
    source.truncated = true;
    assert(!controller.prepare(source));
    assert(controller.report().refusal == InfraredReplayRefusal::Truncated);
    source = validSource();
    source.decode.protocol = InfraredProtocol::Unknown;
    assert(!controller.prepare(source));
    assert(controller.report().refusal ==
           InfraredReplayRefusal::UnsupportedProtocol);
}

void requiresPreviewAndExplicitConfirmation() {
    InfraredReplayController controller;
    FakeOutput output;
    assert(controller.prepare(validSource()));
    assert(controller.report().state == InfraredReplayState::Preview);
    assert(controller.report().sourceGeneration == 7U);
    assert(output.beginCalls == 0U);
    assert(!controller.confirmAndStart(output, 100U));
    assert(output.beginCalls == 0U);
    assert(controller.requestConfirmation());
    assert(controller.report().state == InfraredReplayState::Confirmation);
    assert(output.beginCalls == 0U);
    assert(controller.cancelConfirmation());
    assert(controller.report().state == InfraredReplayState::Preview);
    assert(output.beginCalls == 0U);
    assert(controller.requestConfirmation());
    assert(controller.confirmAndStart(output, 100U));
    assert(controller.report().state == InfraredReplayState::Running);
    assert(controller.report().emissions == 1U);
    assert(output.beginCalls == 1U);
    assert(output.copiedPlan.rawCode == kNecCode);
    assert(!controller.confirmAndStart(output, 101U));
    assert(output.beginCalls == 1U);

    output.state = InfraredReplayOutputState::Complete;
    assert(controller.service(output, 90000U));
    assert(controller.report().state == InfraredReplayState::Complete);
    assert(controller.report().outputInactive);
    assert(controller.report().stopAttempts == 1U);
    assert(output.stopCalls == 1U);
}

void stopAndDeadlineAlwaysQuiesceOutput() {
    InfraredReplayController controller;
    FakeOutput output;
    assert(controller.prepare(validSource()));
    assert(controller.requestConfirmation());
    assert(controller.confirmAndStart(output, 1000U));
    assert(controller.stop(output, 2000U));
    assert(controller.report().state == InfraredReplayState::Stopped);
    assert(!controller.report().deadlineExpired);
    assert(controller.report().outputInactive);

    controller.reset();
    assert(controller.prepare(validSource()));
    assert(controller.requestConfirmation());
    assert(controller.confirmAndStart(output, 10000U));
    assert(controller.service(
        output, 10000U + kInfraredReplayMaximumEmissionUs));
    assert(controller.report().state == InfraredReplayState::TimedOut);
    assert(controller.report().deadlineExpired);
    assert(controller.report().outputInactive);
}

void failsClosedWhenOutputCannotStartOrStop() {
    InfraredReplayController controller;
    FakeOutput output;
    output.beginResult = false;
    assert(controller.prepare(validSource()));
    assert(controller.requestConfirmation());
    assert(!controller.confirmAndStart(output, 100U));
    assert(controller.report().state == InfraredReplayState::Fault);
    assert(controller.report().emissions == 0U);
    assert(controller.report().outputInactive);

    output = {};
    controller.reset();
    assert(controller.prepare(validSource()));
    assert(controller.requestConfirmation());
    assert(controller.confirmAndStart(output, 100U));
    output.stopResult = false;
    assert(!controller.stop(output, 200U));
    assert(controller.report().state == InfraredReplayState::Fault);
    assert(!controller.report().outputInactive);
}

}  // namespace

int main() {
    buildsCanonicalNecPlans();
    rejectsInvalidDecodes();
    refusesUnsafeSources();
    requiresPreviewAndExplicitConfirmation();
    stopAndDeadlineAlwaysQuiesceOutput();
    failsClosedWhenOutputCannotStartOrStop();
    std::cout << "Infrared replay controller tests passed\n";
    return 0;
}
