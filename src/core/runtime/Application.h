#pragma once

#include <stdint.h>

#include "Capabilities.h"
#include "ResourceBroker.h"

namespace leshy {
namespace runtime {

enum class SafetyLevel : uint8_t {
    Passive = 0,
    Connected,
    Transmit,
    Disruptive
};

enum class AppEventType : uint8_t {
    Input = 0,
    System,
    DataReady
};

struct AppEvent {
    AppEventType type = AppEventType::System;
    uint16_t code = 0;
    int32_t value = 0;
};

struct AppDescriptor {
    OwnerId id = kNoOwner;
    const char* key = nullptr;
    CapabilitySet requiredCapabilities = 0;
    ResourceSet requiredResources = 0;
    SafetyLevel safety = SafetyLevel::Passive;
};

// Small app contract used by the target architecture. Apps do not own global
// navigation or other drivers; their resources are leased by AppRuntime.
class Application {
public:
    virtual ~Application() = default;
    virtual const AppDescriptor& descriptor() const = 0;
    virtual bool onStart() = 0;
    virtual void onStop() = 0;
    virtual void onEvent(const AppEvent& event) = 0;
    virtual void onTick(uint32_t nowMs) = 0;
};

enum class StartResult : uint8_t {
    Started = 0,
    AlreadyRunning,
    InvalidDescriptor,
    MissingCapability,
    ResourceBusy,
    StartFailed
};

class AppRuntime {
public:
    AppRuntime(ResourceBroker& resources, CapabilitySet availableCapabilities)
        : resources_(resources), availableCapabilities_(availableCapabilities) {}

    StartResult start(Application& app, ResourceConflict* conflict = nullptr);
    void stop();
    void dispatch(const AppEvent& event);
    void tick(uint32_t nowMs);

    Application* active() const { return active_; }
    CapabilitySet availableCapabilities() const { return availableCapabilities_; }
    void setAvailableCapabilities(CapabilitySet value) { availableCapabilities_ = value; }

private:
    ResourceBroker& resources_;
    CapabilitySet availableCapabilities_ = 0;
    Application* active_ = nullptr;
};

}  // namespace runtime
}  // namespace leshy
