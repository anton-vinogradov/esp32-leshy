#include <cstring>
#include <iostream>

#include "FixtureSession.h"

namespace {

int failures = 0;

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::cerr << "FAIL " << __FILE__ << ':' << __LINE__ << " "       \
                      << #condition << '\n';                                    \
            ++failures;                                                        \
        }                                                                       \
    } while (false)

using leshy::hil::fixture::FixtureSession;
using leshy::hil::fixture::FixtureState;

constexpr const char* kSession = "0123456789abcdef0123456789abcdef";
constexpr const char* kOtherSession = "11111111111111111111111111111111";
constexpr const char* kApp =
    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
constexpr const char* kFixture = "0123456789ABCDEF";

void acceptsOneExactBoundedVector() {
    FixtureSession session;
    CHECK(session.begin(kSession, kApp, kApp, kFixture, kFixture, 100, true));
    CHECK(session.report().state == FixtureState::Armed);
    CHECK(session.authorizeNecOnce(
        kSession, leshy::hil::fixture::kNecVectorId, 101));
    CHECK(session.report().state == FixtureState::Running);
    CHECK(session.complete(68000, true));
    CHECK(session.report().state == FixtureState::Complete);
    CHECK(session.report().startCount == 1);
    CHECK(session.report().stopCount == 1);
    CHECK(session.report().emissionCount == 1);
    CHECK(!session.authorizeNecOnce(
        kSession, leshy::hil::fixture::kNecVectorId, 102));
}

void rejectsIdentityAndVectorMismatch() {
    FixtureSession session;
    CHECK(!session.begin(kSession, "bad", kApp, kFixture, kFixture, 1, true));
    CHECK(std::strcmp(session.report().lastError,
                      "app_identity_mismatch") == 0);
    CHECK(!session.begin(kSession, kApp, kApp, "0000000000000000",
                         kFixture, 1, true));
    CHECK(std::strcmp(session.report().lastError,
                      "fixture_identity_mismatch") == 0);
    CHECK(session.begin(kSession, kApp, kApp, kFixture, kFixture, 1, true));
    CHECK(!session.authorizeNecOnce(kOtherSession,
                                    leshy::hil::fixture::kNecVectorId, 2));
    CHECK(!session.authorizeNecOnce(kSession, "user-replay", 2));
    CHECK(session.report().startCount == 0);
}

void expiresWithoutEmission() {
    FixtureSession session;
    CHECK(session.begin(kSession, kApp, kApp, kFixture, kFixture, 10, true));
    CHECK(session.service(5010, true));
    CHECK(session.report().state == FixtureState::Expired);
    CHECK(session.report().emissionCount == 0);
    CHECK(session.report().stopCount == 1);
    CHECK(!session.authorizeNecOnce(
        kSession, leshy::hil::fixture::kNecVectorId, 5011));
}

void panicAndFaultFailClosed() {
    FixtureSession session;
    CHECK(session.begin(kSession, kApp, kApp, kFixture, kFixture, 1, true));
    session.panic(true);
    CHECK(session.report().state == FixtureState::Panicked);
    CHECK(session.report().panicCount == 1);
    CHECK(session.report().outputInactive);

    FixtureSession duration;
    CHECK(duration.begin(kSession, kApp, kApp, kFixture, kFixture, 1, true));
    CHECK(duration.authorizeNecOnce(
        kSession, leshy::hil::fixture::kNecVectorId, 2));
    CHECK(!duration.complete(
        leshy::hil::fixture::kMaximumEmissionUs + 1, true));
    CHECK(duration.report().state == FixtureState::Fault);

    FixtureSession output;
    CHECK(!output.begin(kSession, kApp, kApp, kFixture, kFixture, 1, false));
    CHECK(output.report().state == FixtureState::Fault);
}

void supportsExplicitStopAndFreshSession() {
    FixtureSession session;
    CHECK(session.begin(kSession, kApp, kApp, kFixture, kFixture, 1, true));
    CHECK(!session.stop(kOtherSession, true));
    CHECK(session.stop(kSession, true));
    CHECK(session.report().state == FixtureState::Stopped);
    CHECK(session.begin(kOtherSession, kApp, kApp, kFixture, kFixture, 20, true));
    CHECK(std::strcmp(session.sessionId(), kOtherSession) == 0);
}

}  // namespace

int main() {
    acceptsOneExactBoundedVector();
    rejectsIdentityAndVectorMismatch();
    expiresWithoutEmission();
    panicAndFaultFailClosed();
    supportsExplicitStopAndFreshSession();
    if (failures != 0) return 1;
    std::cout << "IR fixture controller tests passed\n";
    return 0;
}
