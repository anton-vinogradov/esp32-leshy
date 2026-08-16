#include <cstdlib>
#include <cstring>
#include <iostream>

#include "ProbeLogic.h"

namespace {

int failures = 0;

#define CHECK(expression)                                                                      \
    do {                                                                                       \
        if (!(expression)) {                                                                   \
            std::cerr << __FILE__ << ':' << __LINE__ << ": check failed: " #expression << '\n'; \
            ++failures;                                                                        \
        }                                                                                      \
    } while (false)

void testNrfClassificationRejectsFloatingBus() {
    CHECK(!leshy::hil::plausibleNrfObservation({0, 0, 0, 0, 0}));
    CHECK(!leshy::hil::plausibleNrfObservation({0xFF, 0xFF, 0xFF, 0xFF, 0xFF}));
    CHECK(!leshy::hil::plausibleNrfObservation({0x8E, 0x08, 2, 0x0E, 0}));
    CHECK(!leshy::hil::plausibleNrfObservation({0x0E, 0x08, 126, 0x0E, 0}));
}
void testNrfClassificationAcceptsResetLikeRegisters() {
    CHECK(leshy::hil::plausibleNrfObservation({0x0E, 0x08, 2, 0x0E, 0}));
}

void testCcClassification() {
    CHECK(leshy::hil::plausibleCcObservation(0x0F, 0x00, 0x14));
    CHECK(!leshy::hil::plausibleCcObservation(0xFF, 0xFF, 0xFF));
    CHECK(!leshy::hil::plausibleCcObservation(0x0F, 0x00, 0x00));
}

void testNmeaChecksum() {
    const char valid[] = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47";
    const char invalid[] = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*00";
    CHECK(leshy::hil::validNmeaChecksum(valid, std::strlen(valid)));
    CHECK(!leshy::hil::validNmeaChecksum(invalid, std::strlen(invalid)));
    CHECK(!leshy::hil::validNmeaChecksum("garbage", 7));
}

}  // namespace

int main() {
    testNrfClassificationRejectsFloatingBus();
    testNrfClassificationAcceptsResetLikeRegisters();
    testCcClassification();
    testNmeaChecksum();

    if (failures != 0) {
        std::cerr << failures << " test(s) failed\n";
        return EXIT_FAILURE;
    }
    std::cout << "HIL probe logic tests passed\n";
    return EXIT_SUCCESS;
}
