#pragma once

#include "ResourceBroker.h"

namespace leshy1::kernel::runtime {

enum class LaunchStatus : std::uint8_t {
    Started,
    Disabled,
    Busy,
    AlreadyRunning,
    InvalidDescriptor,
};

const char* launchStatusName(LaunchStatus status);

class AppRuntime final {
public:
    static constexpr ResourceOwner kForegroundOwner = 1;

    explicit AppRuntime(ResourceBroker& broker) : broker_(broker) {}

    LaunchStatus launch(const char* appId, bool enabled, ResourceMask resources);
    bool stop();

    bool running() const { return activeApp_ != nullptr; }
    const char* activeApp() const { return activeApp_ == nullptr ? "none" : activeApp_; }
    ResourceMask activeResources() const { return broker_.ownedBy(kForegroundOwner); }

private:
    ResourceBroker& broker_;
    const char* activeApp_ = nullptr;
};

}  // namespace leshy1::kernel::runtime
