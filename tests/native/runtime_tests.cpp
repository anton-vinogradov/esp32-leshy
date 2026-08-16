#include <cstdlib>
#include <iostream>

#include "core/navigation/Navigator.h"
#include "core/runtime/Application.h"

using leshy::navigation::Navigator;
using namespace leshy::runtime;

namespace {

int failures = 0;

#define CHECK(expression)                                                                      \
    do {                                                                                       \
        if (!(expression)) {                                                                   \
            std::cerr << __FILE__ << ':' << __LINE__ << ": check failed: " #expression << '\n'; \
            ++failures;                                                                        \
        }                                                                                      \
    } while (false)

class FakeApp : public Application {
public:
    explicit FakeApp(AppDescriptor descriptor, bool starts = true)
        : descriptor_(descriptor), starts_(starts) {}

    const AppDescriptor& descriptor() const override { return descriptor_; }
    bool onStart() override { ++starts; return starts_; }
    void onStop() override { ++stops; }
    void onEvent(const AppEvent& event) override { ++events; lastEvent = event; }
    void onTick(uint32_t nowMs) override { ++ticks; lastTick = nowMs; }

    int starts = 0;
    int stops = 0;
    int events = 0;
    int ticks = 0;
    uint32_t lastTick = 0;
    AppEvent lastEvent;

private:
    AppDescriptor descriptor_;
    bool starts_;
};

void testNavigatorKeepsSelectionPerLevel() {
    Navigator navigator(4);
    CHECK(navigator.menu() == 4);
    CHECK(navigator.selection() == 0);
    CHECK(!navigator.canGoBack());

    uint8_t previous = 99;
    CHECK(navigator.moveSelection(1, 4, &previous));
    CHECK(previous == 0);
    CHECK(navigator.selection() == 1);
    CHECK(navigator.push(8));
    CHECK(navigator.menu() == 8);
    CHECK(navigator.selection() == 0);
    CHECK(navigator.setSelection(2, 3));
    CHECK(navigator.pop());
    CHECK(navigator.menu() == 4);
    CHECK(navigator.selection() == 1);
}

void testNavigatorRejectsInvalidEdges() {
    Navigator navigator;
    CHECK(!navigator.pop());
    CHECK(!navigator.moveSelection(-1, 3));
    CHECK(!navigator.moveSelection(1, 1));
    CHECK(!navigator.setSelection(-1, 3));
    CHECK(!navigator.setSelection(3, 3));

    for (size_t i = 1; i < Navigator::kMaxDepth; ++i) CHECK(navigator.push(static_cast<uint8_t>(i)));
    CHECK(!navigator.push(99));
    navigator.clampSelection(0);
    CHECK(navigator.selection() == 0);
}

void testResourceAcquisitionIsAtomic() {
    ResourceBroker broker;
    const ResourceSet wifi = resource(Resource::EspWifiRadio);
    const ResourceSet bluetooth = resource(Resource::EspBluetoothRadio);
    CHECK(!broker.tryAcquire(kNoOwner, wifi));
    CHECK(!broker.tryAcquire(10, ResourceSet{1} << 31));
    CHECK(broker.tryAcquire(10, wifi));

    ResourceConflict conflict;
    CHECK(!broker.tryAcquire(20, wifi | bluetooth, &conflict));
    CHECK(conflict.resource == Resource::EspWifiRadio);
    CHECK(conflict.owner == 10);
    CHECK(broker.ownerOf(Resource::EspBluetoothRadio) == kNoOwner);

    CHECK(broker.tryAcquire(10, wifi | bluetooth));
    CHECK(broker.owns(10, wifi | bluetooth));
    broker.release(10, bluetooth);
    CHECK(broker.ownerOf(Resource::EspWifiRadio) == 10);
    CHECK(broker.ownerOf(Resource::EspBluetoothRadio) == kNoOwner);
    broker.releaseAll(10);
    CHECK(broker.ownerOf(Resource::EspWifiRadio) == kNoOwner);
}

void testRuntimeChecksCapabilitiesAndReleasesFailedStart() {
    ResourceBroker broker;
    AppRuntime runtime(broker, capability(Capability::Wifi));
    const AppDescriptor descriptor{
        41,
        "wifi.scan",
        capability(Capability::Wifi) | capability(Capability::Nrf24),
        resource(Resource::EspWifiRadio),
        SafetyLevel::Passive
    };
    FakeApp missingCapability(descriptor);
    CHECK(runtime.start(missingCapability) == StartResult::MissingCapability);
    CHECK(missingCapability.starts == 0);

    runtime.setAvailableCapabilities(
        capability(Capability::Wifi) | capability(Capability::Nrf24));
    FakeApp failedStart(descriptor, false);
    CHECK(runtime.start(failedStart) == StartResult::StartFailed);
    CHECK(failedStart.starts == 1);
    CHECK(broker.ownerOf(Resource::EspWifiRadio) == kNoOwner);
}

void testRuntimeOwnsLifecycle() {
    ResourceBroker broker;
    AppRuntime runtime(broker, capability(Capability::Cc1101));
    const ResourceSet resources =
        resource(Resource::SharedRadioSpi) | resource(Resource::Cc1101);
    FakeApp app({52, "subghz.spectrum", capability(Capability::Cc1101), resources,
                 SafetyLevel::Passive});
    FakeApp second({53, "subghz.capture", capability(Capability::Cc1101), resources,
                    SafetyLevel::Passive});

    CHECK(runtime.start(app) == StartResult::Started);
    CHECK(runtime.active() == &app);
    CHECK(broker.owns(52, resources));
    CHECK(runtime.start(second) == StartResult::AlreadyRunning);

    const AppEvent event{AppEventType::Input, 7, -1};
    runtime.dispatch(event);
    runtime.tick(1234);
    CHECK(app.events == 1);
    CHECK(app.lastEvent.code == 7);
    CHECK(app.ticks == 1);
    CHECK(app.lastTick == 1234);

    runtime.stop();
    CHECK(app.stops == 1);
    CHECK(runtime.active() == nullptr);
    CHECK(broker.ownerOf(Resource::Cc1101) == kNoOwner);
    CHECK(runtime.start(second) == StartResult::Started);
}

}  // namespace

int main() {
    testNavigatorKeepsSelectionPerLevel();
    testNavigatorRejectsInvalidEdges();
    testResourceAcquisitionIsAtomic();
    testRuntimeChecksCapabilitiesAndReleasesFailedStart();
    testRuntimeOwnsLifecycle();

    if (failures) {
        std::cerr << failures << " test(s) failed\n";
        return EXIT_FAILURE;
    }
    std::cout << "runtime tests passed\n";
    return EXIT_SUCCESS;
}
