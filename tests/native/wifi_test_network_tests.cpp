#include <cassert>
#include <cstdint>
#include <iostream>
#include "apps/self_test/WifiTestNetwork.h"
#include "apps/self_test/SelfTestController.h"
using namespace leshy1::apps::self_test;
int main() {
    WifiTestNetwork network;
    assert(!network.running() && !network.due(100));
    assert(!network.begin(100, false, true));
    assert(!network.begin(100, true, false));
    assert(network.begin(100, true, true));
    assert(network.remainingSeconds(100) == 60);
    assert(!network.begin(59999, true, true)); // No renewal.
    assert(!network.due(60099) && network.due(60100));
    assert(network.remainingSeconds(60100) == 0);
    network.stop(WifiTestNetwork::StopReason::Deadline);
    assert(!network.running());
    assert(network.begin(UINT32_MAX - 50U, true, true));
    assert(!network.due(10));
    assert(network.due(60000));
    network.stop(WifiTestNetwork::StopReason::User);
    network.stop(WifiTestNetwork::StopReason::User);
    SelfTestController menu;
    assert(menu.nextMode() && menu.nextMode() && !menu.nextMode());
    assert(menu.selectedMode() == SelfTestMode::WifiNetwork);
    assert(menu.activate({}, 1));
    assert(menu.view() == SelfTestView::WifiNetwork);
    assert(!menu.hasReport() && !menu.runAwaitingFinish());
    assert(!menu.activate({}, 2));
    assert(menu.back() && menu.view() == SelfTestView::ModeMenu);
    assert(menu.selection() == 2);
    std::cout << "Wi-Fi product test network: admission, deadline, no renewal, menu-only entry passed\n";
}
