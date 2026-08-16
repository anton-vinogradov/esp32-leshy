#include "AppRuntime.h"

namespace leshy1::kernel::runtime {

const char* launchStatusName(LaunchStatus status) {
    switch (status) {
        case LaunchStatus::Started: return "started";
        case LaunchStatus::Disabled: return "disabled";
        case LaunchStatus::Busy: return "busy";
        case LaunchStatus::AlreadyRunning: return "already_running";
        case LaunchStatus::InvalidDescriptor: return "invalid_descriptor";
    }
    return "invalid_status";
}

LaunchStatus AppRuntime::launch(const char* appId, bool enabled, ResourceMask resources) {
    if (appId == nullptr || appId[0] == '\0' || resources == 0 ||
        (resources & ~kKnownResources) != 0) {
        return LaunchStatus::InvalidDescriptor;
    }
    if (!enabled) return LaunchStatus::Disabled;
    if (running()) return LaunchStatus::AlreadyRunning;
    if (!broker_.acquire(kForegroundOwner, resources)) return LaunchStatus::Busy;
    activeApp_ = appId;
    return LaunchStatus::Started;
}

bool AppRuntime::stop() {
    if (!running()) return false;
    broker_.releaseAll(kForegroundOwner);
    activeApp_ = nullptr;
    return true;
}

}  // namespace leshy1::kernel::runtime
