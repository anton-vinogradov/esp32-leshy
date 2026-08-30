#include <cstdlib>
#include <cstring>
#include <iostream>

#include "kernel/runtime/ResourceBroker.h"
#include "services/actions/ActionDispatcher.h"
#include "services/actions/ActionsCli.h"
#include "services/serial/SerialConsoleContract.h"

using namespace leshy1::kernel::runtime;
using namespace leshy1::services::actions;
using namespace leshy1::services::serial;

namespace {

int failures = 0;

#define CHECK(expression)                                                      \
    do {                                                                       \
        if (!(expression)) {                                                   \
            std::cerr << __FILE__ << ':' << __LINE__                          \
                      << ": check failed: " #expression << '\n';             \
            ++failures;                                                        \
        }                                                                      \
    } while (false)

class FakeEndpoint final : public ActionEndpoint {
public:
    bool start(std::uint32_t nowMs) override {
        ++starts;
        startedMs = nowMs;
        return startResult;
    }

    ActionEndpointState tick(std::uint32_t nowMs) override {
        ++ticks;
        tickedMs = nowMs;
        return nextState;
    }

    void cancel() override { ++cancels; }

    bool startResult = true;
    ActionEndpointState nextState = ActionEndpointState::Running;
    int starts = 0;
    int ticks = 0;
    int cancels = 0;
    std::uint32_t startedMs = 0;
    std::uint32_t tickedMs = 0;
};

SerialConsoleConfig validConfig(SerialConsoleMode mode =
                                    SerialConsoleMode::Monitor) {
    SerialConsoleConfig config{};
    config.mode = mode;
    CHECK(setSerialConsoleTarget(&config, "owned-fixture", 13U));
    return config;
}

SerialConsoleHardware validHardware() {
    SerialConsoleHardware hardware{};
    hardware.externalMux56UartDeclared = true;
    return hardware;
}

ActionContext validContext(const SerialConsoleConfig& config,
                           bool confirmed = true) {
    const ActionDescriptor descriptor =
        serialConsoleActionDescriptor(config);
    ActionContext context{};
    context.requestSchemaVersion = descriptor.requestSchemaVersion;
    context.availableCapabilities = kExternalMux56UartCapability;
    context.grantedPermissions = descriptor.requiredPermissions;
    context.authenticated = true;
    context.confirmed = confirmed;
    return context;
}

ActionsCliParseStatus parse(const char* line, ActionsCliRequest* output) {
    return parseActionsCliRequest(line, std::strlen(line), output);
}

void testSerialPreflightIsNamedAndFailClosed() {
    SerialConsoleConfig config = validConfig();
    SerialConsoleHardware hardware = validHardware();
    CHECK(validateSerialConsoleConfig(config, hardware) ==
          SerialConsolePreflightStatus::Ready);

    hardware.externalMux56UartDeclared = false;
    CHECK(validateSerialConsoleConfig(config, hardware) ==
          SerialConsolePreflightStatus::ProfileUnavailable);
    hardware.externalMux56UartDeclared = true;
    hardware.rfShieldDeclared = true;
    CHECK(validateSerialConsoleConfig(config, hardware) ==
          SerialConsolePreflightStatus::MuxConflict);
    hardware.rfShieldDeclared = false;
    hardware.gpsDeclared = true;
    CHECK(validateSerialConsoleConfig(config, hardware) ==
          SerialConsolePreflightStatus::MuxConflict);
    hardware.gpsDeclared = false;
    hardware.pn532Declared = true;
    CHECK(validateSerialConsoleConfig(config, hardware) ==
          SerialConsolePreflightStatus::MuxConflict);
    hardware.pn532Declared = false;
    hardware.logicMillivolts = 5000U;
    CHECK(validateSerialConsoleConfig(config, hardware) ==
          SerialConsolePreflightStatus::VoltageMismatch);

    hardware = validHardware();
    config.baud = 230400U;
    CHECK(validateSerialConsoleConfig(config, hardware) ==
          SerialConsolePreflightStatus::UnsupportedBaud);
    config.baud = 115200U;
    config.durationMs = 999U;
    CHECK(validateSerialConsoleConfig(config, hardware) ==
          SerialConsolePreflightStatus::InvalidDuration);
    config.durationMs = 300001U;
    CHECK(validateSerialConsoleConfig(config, hardware) ==
          SerialConsolePreflightStatus::InvalidDuration);
    config.durationMs = 60000U;
    config.mode = static_cast<SerialConsoleMode>(0xffU);
    CHECK(validateSerialConsoleConfig(config, hardware) ==
          SerialConsolePreflightStatus::UnsupportedMode);
    config.mode = SerialConsoleMode::Monitor;
    config.target[0] = '!';
    CHECK(validateSerialConsoleConfig(config, hardware) ==
          SerialConsolePreflightStatus::InvalidTarget);
}

void testDescriptorHasBoundedPermissionsAndResources() {
    const SerialConsoleConfig monitor = validConfig();
    const ActionDescriptor monitorAction =
        serialConsoleActionDescriptor(monitor);
    CHECK(std::strcmp(monitorAction.id, "serial.console.start") == 0);
    CHECK(monitorAction.safety == ActionSafetyClass::ActiveConfirmed);
    CHECK((monitorAction.requiredResources &
           resourceMask(Resource::Console)) != 0U);
    CHECK((monitorAction.requiredResources &
           resourceMask(Resource::Mux56)) != 0U);
    CHECK((monitorAction.requiredPermissions &
           actionPermission(ActionPermission::SerialMonitor)) != 0U);
    CHECK((monitorAction.requiredPermissions &
           actionPermission(ActionPermission::SerialWrite)) == 0U);

    const SerialConsoleConfig bridge =
        validConfig(SerialConsoleMode::Bridge);
    const ActionDescriptor bridgeAction =
        serialConsoleActionDescriptor(bridge);
    CHECK((bridgeAction.requiredPermissions &
           actionPermission(ActionPermission::SerialWrite)) != 0U);
    CHECK(bridgeAction.timeoutMs == bridge.durationMs);
    CHECK(bridgeAction.cancellable);
}

void testCliProducesTheSameTypedPreviewAsUi() {
    constexpr const char* line =
        "action.preview serial.console.start profile=mux56-3v3 "
        "target=owned-fixture baud=115200 framing=8N1 mode=monitor "
        "duration_ms=60000";
    ActionsCliRequest cli{};
    CHECK(parse(line, &cli) == ActionsCliParseStatus::Parsed);
    const SerialConsoleConfig ui = validConfig();
    CHECK(cli.kind == ActionsCliRequestKind::Preview);
    CHECK(cli.serialConfig.targetLength == ui.targetLength);
    CHECK(std::memcmp(cli.serialConfig.target.data(), ui.target.data(),
                      ui.targetLength) == 0);
    CHECK(cli.serialConfig.baud == ui.baud);
    CHECK(cli.serialConfig.framing == ui.framing);
    CHECK(cli.serialConfig.mode == ui.mode);
    CHECK(cli.serialConfig.durationMs == ui.durationMs);

    ResourceBroker broker;
    ActionDispatcher dispatcher(broker);
    const ActionDescriptor uiAction = serialConsoleActionDescriptor(ui);
    const ActionDescriptor cliAction =
        serialConsoleActionDescriptor(cli.serialConfig);
    const ActionContext context = validContext(ui, false);
    const ActionAssessment uiPreview = dispatcher.preview(uiAction, context);
    const ActionAssessment cliPreview = dispatcher.preview(cliAction, context);
    CHECK(uiPreview.status == ActionStatus::Ready);
    CHECK(cliPreview.status == uiPreview.status);
    CHECK(uiPreview.confirmationRequired);
    CHECK(cliPreview.confirmationRequired);
    CHECK(dispatcher.ownedResources() == 0U);
}

void testCliRejectsRawGpioAndAmbiguousInput() {
    constexpr const char* base =
        "action.run serial.console.start profile=mux56-3v3 "
        "target=owned-fixture baud=115200 framing=8N1 mode=bridge "
        "duration_ms=60000 confirm=yes";
    ActionsCliRequest request{};
    CHECK(parse(base, &request) == ActionsCliParseStatus::Parsed);
    CHECK(request.confirmed);

    constexpr const char* rawGpio =
        "action.run serial.console.start profile=mux56-3v3 "
        "target=owned-fixture baud=115200 framing=8N1 mode=bridge "
        "duration_ms=60000 rx_pin=5 confirm=yes";
    CHECK(parse(rawGpio, &request) == ActionsCliParseStatus::UnknownField);
    constexpr const char* duplicate =
        "action.run serial.console.start profile=mux56-3v3 "
        "target=owned-fixture baud=9600 baud=115200 framing=8N1 "
        "mode=monitor duration_ms=60000 confirm=yes";
    CHECK(parse(duplicate, &request) ==
          ActionsCliParseStatus::DuplicateField);
    constexpr const char* noConfirm =
        "action.run serial.console.start profile=mux56-3v3 "
        "target=owned-fixture baud=115200 framing=8N1 mode=monitor "
        "duration_ms=60000";
    CHECK(parse(noConfirm, &request) ==
          ActionsCliParseStatus::ConfirmationRequired);
    constexpr const char* missing =
        "action.preview serial.console.start profile=mux56-3v3 "
        "target=owned-fixture baud=115200 framing=8N1 mode=monitor";
    CHECK(parse(missing, &request) == ActionsCliParseStatus::MissingField);
    CHECK(parse("action.preview gpio.write pin=2 value=1", &request) ==
          ActionsCliParseStatus::UnsupportedAction);
    CHECK(parse("action.preview  serial.console.start", &request) ==
          ActionsCliParseStatus::Malformed);
}

void testDispatcherOrderAndLeaseCleanup() {
    const SerialConsoleConfig config = validConfig();
    const ActionDescriptor descriptor = serialConsoleActionDescriptor(config);
    ResourceBroker broker;
    ActionDispatcher dispatcher(broker);
    FakeEndpoint endpoint;

    ActionContext context = validContext(config, false);
    CHECK(dispatcher.invoke(descriptor, context, endpoint, 10U) ==
          ActionStatus::ConfirmationRequired);
    CHECK(endpoint.starts == 0);
    CHECK(dispatcher.ownedResources() == 0U);

    context.confirmed = true;
    context.authenticated = false;
    CHECK(dispatcher.invoke(descriptor, context, endpoint, 10U) ==
          ActionStatus::AuthenticationRequired);
    context.authenticated = true;
    context.grantedPermissions =
        actionPermission(ActionPermission::DeviceControl);
    CHECK(dispatcher.invoke(descriptor, context, endpoint, 10U) ==
          ActionStatus::PermissionDenied);
    context = validContext(config);
    context.availableCapabilities = 0U;
    CHECK(dispatcher.invoke(descriptor, context, endpoint, 10U) ==
          ActionStatus::CapabilityUnavailable);

    context = validContext(config);
    CHECK(dispatcher.invoke(descriptor, context, endpoint, 10U) ==
          ActionStatus::Running);
    CHECK(endpoint.starts == 1);
    CHECK(dispatcher.ownedResources() == descriptor.requiredResources);
    CHECK(broker.ownerOf(Resource::Console) ==
          ActionDispatcher::kDefaultOwner);
    FakeEndpoint secondEndpoint;
    CHECK(dispatcher.invoke(descriptor, context, secondEndpoint, 11U) ==
          ActionStatus::Busy);
    CHECK(dispatcher.status() == ActionStatus::Running);
    CHECK(secondEndpoint.starts == 0);
    CHECK(std::strcmp(dispatcher.activeActionId(),
                      "serial.console.start") == 0);
    CHECK(dispatcher.cancel() == ActionStatus::Cancelled);
    CHECK(endpoint.cancels == 1);
    CHECK(dispatcher.ownedResources() == 0U);
    CHECK(std::strcmp(dispatcher.activeActionId(), "none") == 0);
}

void testDispatcherTimeoutFailureAndConflictAreTerminal() {
    SerialConsoleConfig config = validConfig();
    config.durationMs = 1000U;
    const ActionDescriptor descriptor = serialConsoleActionDescriptor(config);
    const ActionContext context = validContext(config);
    ResourceBroker broker;
    ActionDispatcher dispatcher(broker);
    FakeEndpoint endpoint;

    CHECK(broker.acquire(9U, resourceMask(Resource::Mux56)));
    CHECK(dispatcher.invoke(descriptor, context, endpoint, 0U) ==
          ActionStatus::Busy);
    CHECK(endpoint.starts == 0);
    CHECK(broker.ownerOf(Resource::Console) == kNoOwner);
    broker.releaseAll(9U);

    endpoint.startResult = false;
    CHECK(dispatcher.invoke(descriptor, context, endpoint, 0U) ==
          ActionStatus::StartFailed);
    CHECK(dispatcher.ownedResources() == 0U);
    endpoint.startResult = true;
    CHECK(dispatcher.invoke(descriptor, context, endpoint, UINT32_MAX - 20U) ==
          ActionStatus::Running);
    CHECK(dispatcher.tick(979U) == ActionStatus::TimedOut);
    CHECK(endpoint.cancels == 1);
    CHECK(dispatcher.ownedResources() == 0U);

    endpoint.nextState = ActionEndpointState::Failed;
    CHECK(dispatcher.invoke(descriptor, context, endpoint, 2000U) ==
          ActionStatus::Running);
    CHECK(dispatcher.tick(2001U) == ActionStatus::Failed);
    CHECK(dispatcher.ownedResources() == 0U);
    endpoint.nextState = ActionEndpointState::Completed;
    CHECK(dispatcher.invoke(descriptor, context, endpoint, 3000U) ==
          ActionStatus::Running);
    CHECK(dispatcher.tick(3001U) == ActionStatus::Completed);
    CHECK(dispatcher.ownedResources() == 0U);
}

}  // namespace

int main() {
    testSerialPreflightIsNamedAndFailClosed();
    testDescriptorHasBoundedPermissionsAndResources();
    testCliProducesTheSameTypedPreviewAsUi();
    testCliRejectsRawGpioAndAmbiguousInput();
    testDispatcherOrderAndLeaseCleanup();
    testDispatcherTimeoutFailureAndConflictAreTerminal();

    if (failures != 0) {
        std::cerr << failures << " test(s) failed\n";
        return EXIT_FAILURE;
    }
    std::cout << "serial console Action boundary tests passed\n";
    return EXIT_SUCCESS;
}
