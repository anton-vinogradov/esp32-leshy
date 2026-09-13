#include <cassert>
#include <cstdint>
#include <iostream>
#include "../hil/fixtures/wifi-name/include/NameFixtureSession.h"

int main() {
    using leshy::hil::NameFixtureSession;
    NameFixtureSession session;
    assert(!session.active());
    assert(!session.begin(nullptr, 0));
    assert(!session.begin("short", 0));
    assert(!session.begin("0123456789abcd?f", 0));
    assert(!session.setHidden("0123456789abcdef", false, 0));
    assert(session.begin("0123456789abcdef", 10));
    assert(session.hidden());
    assert(!session.begin("1111111111111111", 11)); // No renewal.
    assert(!session.setHidden("1111111111111111", false, 11));
    assert(session.setHidden("0123456789abcdef", false, 11));
    assert(!session.hidden());
    assert(!session.expire(60009));
    assert(session.expire(60010));
    assert(!session.active());
    assert(session.token()[0] == '\0');
    assert(session.begin("2222222222222222", UINT32_MAX - 20U));
    assert(!session.setHidden("0123456789abcdef", false, 5));
    assert(!session.expire(59978));
    assert(session.expire(59979)); // millis() wraps; deadline does not extend.
    assert(session.begin("0123456789abcdef", 0));
    assert(!session.setHidden("0123456789abcdef", false, 60000));
    assert(!session.active());
    assert(session.begin("0123456789abcdef", 0));
    session.stop(); session.stop();
    assert(!session.active());
    std::cout << "Wi-Fi name fixture lease tests passed\n";
}
