#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>

#include "services/companion/CompanionConnectivity.h"

using namespace leshy1::services::companion;

namespace {

int failures = 0;

#define CHECK(expression)                                                        \
    do {                                                                         \
        if (!(expression)) {                                                     \
            std::cerr << __FILE__ << ':' << __LINE__                             \
                      << ": check failed: " #expression << '\n';                \
            ++failures;                                                          \
        }                                                                        \
    } while (false)

void testEphemeralCredentialsAreBoundedAndClearable() {
    const std::array<std::uint8_t, 6> mac = {0x1c, 0xdb, 0xd4,
                                             0x87, 0x90, 0xd4};
    std::array<std::uint8_t, 16> entropy{};
    for (std::size_t index = 0; index < entropy.size(); ++index) {
        entropy[index] = static_cast<std::uint8_t>(index * 17U + 3U);
    }
    CompanionLocalCredentials first{};
    CompanionLocalCredentials second{};
    CHECK(makeCompanionLocalCredentials(mac, entropy, &first));
    CHECK(first.valid());
    CHECK(std::strcmp(first.ssid.data(), "Leshy-8790D4") == 0);
    CHECK(std::strlen(first.passphrase.data()) ==
          kCompanionLocalPassphraseCapacity);
    entropy[0] ^= 0x5aU;
    CHECK(makeCompanionLocalCredentials(mac, entropy, &second));
    CHECK(std::strcmp(first.passphrase.data(), second.passphrase.data()) != 0);
    first.clear();
    for (char value : first.ssid) CHECK(value == '\0');
    for (char value : first.passphrase) CHECK(value == '\0');
    CHECK(!first.valid());
    CHECK(!makeCompanionLocalCredentials(mac, entropy, nullptr));
}

void testHilEntropyParsingIsExactAndFailClosed() {
    std::array<std::uint8_t, 16> entropy{};
    CHECK(parseCompanionHilEntropyHex(
        "000102030405060708090A0B0C0D0E0F", &entropy));
    for (std::size_t index = 0; index < entropy.size(); ++index) {
        CHECK(entropy[index] == index);
    }
    CHECK(!parseCompanionHilEntropyHex(
        "00000000000000000000000000000000", &entropy));
    for (std::uint8_t value : entropy) CHECK(value == 0);
    CHECK(!parseCompanionHilEntropyHex("00010203", &entropy));
    CHECK(!parseCompanionHilEntropyHex(
        "000102030405060708090A0B0C0D0E0Z", &entropy));
    CHECK(!parseCompanionHilEntropyHex(
        "000102030405060708090A0B0C0D0E0F", nullptr));
}

void testAuthorizationIsExplicitAndGenerationBound() {
    CompanionConnectivity session;
    CHECK(!session.authorized());
    CHECK(!session.authorize(0, 7));
    CHECK(!session.authorize(1, 0));
    CHECK(session.authorize(1, 7));
    CHECK(session.authorized());
    CHECK(!session.authorize(2, 8));
    CHECK(!session.recordActivity(2, 8));
    CHECK(session.recordActivity(2, 7));
    CHECK(session.lastActivityUs() == 2);
    session.revoke(CompanionLocalStopReason::LeftForeground);
    CHECK(!session.authorized());
    CHECK(session.generation() == 0);
    CHECK(session.stopReason() == CompanionLocalStopReason::LeftForeground);
    CHECK(!session.recordActivity(3, 7));
}

void testIdleAndAbsoluteTimeoutsFailClosed() {
    CompanionConnectivity idle;
    CHECK(idle.authorize(1, 1));
    CHECK(!idle.service(kCompanionLocalIdleTimeoutUs));
    CHECK(idle.service(kCompanionLocalIdleTimeoutUs + 1U));
    CHECK(!idle.authorized());
    CHECK(idle.stopReason() == CompanionLocalStopReason::IdleTimeout);

    CompanionConnectivity lifetime;
    CHECK(lifetime.authorize(1, 2));
    std::uint64_t now = kCompanionLocalIdleTimeoutUs;
    while (now < kCompanionLocalMaximumLifetimeUs) {
        CHECK(lifetime.recordActivity(now, 2));
        now += kCompanionLocalIdleTimeoutUs - 1U;
    }
    CHECK(lifetime.service(kCompanionLocalMaximumLifetimeUs + 1U));
    CHECK(lifetime.stopReason() ==
          CompanionLocalStopReason::LifetimeTimeout);
}

void testClockRollbackRevokesInsteadOfExtending() {
    CompanionConnectivity session;
    CHECK(session.authorize(100, 3));
    CHECK(session.recordActivity(200, 3));
    CHECK(session.service(150));
    CHECK(!session.authorized());
    CHECK(session.stopReason() == CompanionLocalStopReason::SafetyStop);
    CHECK(std::strcmp(companionLocalStopReasonName(session.stopReason()),
                      "safety_stop") == 0);
}

}  // namespace

int main() {
    testEphemeralCredentialsAreBoundedAndClearable();
    testHilEntropyParsingIsExactAndFailClosed();
    testAuthorizationIsExplicitAndGenerationBound();
    testIdleAndAbsoluteTimeoutsFailClosed();
    testClockRollbackRevokesInsteadOfExtending();
    if (failures != 0) {
        std::cerr << failures << " companion connectivity checks failed\n";
        return EXIT_FAILURE;
    }
    std::cout << "companion connectivity tests passed\n";
    return EXIT_SUCCESS;
}
