#include <iostream>

#include "platform/arduino/RamSessionStoreIo.h"
#include "services/survey/SurveySession.h"
#include "storage/SessionStore.h"

using namespace leshy1::domain::observations;
using namespace leshy1::platform::arduino;
using namespace leshy1::services::survey;
using namespace leshy1::storage;

namespace {

int failures = 0;
#define CHECK(condition)                                                     \
    do {                                                                     \
        if (!(condition)) {                                                  \
            std::cerr << __FILE__ << ':' << __LINE__ << ": CHECK("          \
                      << #condition << ") failed\n";                         \
            ++failures;                                                      \
        }                                                                    \
    } while (false)

SurveySession session(const char* id, std::uint64_t base,
                      std::uint8_t suffix) {
    SurveySession value;
    CHECK(value.start(id, base) == SessionStatus::Started);
    Observation observation{};
    observation.sequence = 1;
    observation.monotonicUs = base + 1;
    observation.radio = RadioKind::Wifi;
    observation.frequencyKhz = 2412000;
    observation.channel = 1;
    observation.rssiDbm = -50;
    observation.identity = {2, 0, 0, 0, 0, suffix};
    observation.identityLength = 6;
    observation.wifiNetwork.present = true;
    CHECK(value.append(observation) == SessionStatus::Appended);
    CHECK(value.stop(base + 2) == SessionStatus::Stopped);
    return value;
}

void exactPairAndOrdering() {
    RamSessionStoreIo io;
    SessionStoreWorkspace workspace;
    SurveySession first = session("first", 100, 1);
    SurveySession second = session("second", 200, 2);
    CHECK(commitNextSession(io, workspace, first).complete());

    SurveySession baseline;
    SurveySession current;
    auto one = recoverSessionPair(io, workspace, &baseline, &current);
    CHECK(one.status == SessionStoreStatus::NoGeneration);
    CHECK(baseline.state() == SessionState::Idle);
    CHECK(current.state() == SessionState::Idle);

    CHECK(commitNextSession(io, workspace, second).complete());
    auto pair = recoverSessionPair(io, workspace, &baseline, &current);
    CHECK(pair.valid());
    CHECK(pair.baselineGeneration == 1);
    CHECK(pair.currentGeneration == 2);
    CHECK(pair.baselineObservations == 1);
    CHECK(pair.currentObservations == 1);
    CHECK(std::string(baseline.id()) == "first");
    CHECK(std::string(current.id()) == "second");
}

void corruptHeadGenerationIsNotAComparisonSource() {
    RamSessionStoreIo io;
    SessionStoreWorkspace workspace;
    SurveySession first = session("first", 100, 1);
    SurveySession second = session("second", 200, 2);
    CHECK(commitNextSession(io, workspace, first).complete());
    CHECK(commitNextSession(io, workspace, second).complete());
    CHECK(io.flipSegmentByte(2, 0));
    SurveySession baseline;
    SurveySession current;
    const auto pair = recoverSessionPair(io, workspace, &baseline, &current);
    CHECK(pair.status == SessionStoreStatus::NoGeneration);
    CHECK(baseline.state() == SessionState::Idle);
    CHECK(current.state() == SessionState::Idle);
}

void workspaceValidationSessionCanHoldCurrent() {
    RamSessionStoreIo io;
    SessionStoreWorkspace workspace;
    SurveySession first = session("first", 100, 1);
    SurveySession second = session("second", 200, 2);
    CHECK(commitNextSession(io, workspace, first).complete());
    CHECK(commitNextSession(io, workspace, second).complete());

    SurveySession baseline;
    const auto pair = recoverSessionPair(
        io, workspace, &baseline, &workspace.validationSession);
    CHECK(pair.valid());
    CHECK(pair.baselineGeneration == 1);
    CHECK(pair.currentGeneration == 2);
    CHECK(std::string(baseline.id()) == "first");
    CHECK(std::string(workspace.validationSession.id()) == "second");
    CHECK(workspace.generation == 2);
}

}  // namespace

int main() {
    exactPairAndOrdering();
    corruptHeadGenerationIsNotAComparisonSource();
    workspaceValidationSessionCanHoldCurrent();
    if (failures != 0) {
        std::cerr << failures << " session pair recovery test(s) failed\n";
        return 1;
    }
    std::cout << "session pair recovery tests passed\n";
    return 0;
}
