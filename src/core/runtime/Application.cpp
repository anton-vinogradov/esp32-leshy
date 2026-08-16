#include "Application.h"

namespace leshy {
namespace runtime {

StartResult AppRuntime::start(Application& app, ResourceConflict* conflict) {
    if (conflict) *conflict = {};
    if (active_) return StartResult::AlreadyRunning;

    const AppDescriptor& descriptor = app.descriptor();
    if (descriptor.id == kNoOwner || !descriptor.key || !descriptor.key[0] ||
        !isValidCapabilitySet(descriptor.requiredCapabilities) ||
        !isValidResourceSet(descriptor.requiredResources)) {
        return StartResult::InvalidDescriptor;
    }
    if (!hasAllCapabilities(availableCapabilities_, descriptor.requiredCapabilities)) {
        return StartResult::MissingCapability;
    }
    if (!resources_.tryAcquire(descriptor.id, descriptor.requiredResources, conflict)) {
        return StartResult::ResourceBusy;
    }
    if (!app.onStart()) {
        resources_.releaseAll(descriptor.id);
        return StartResult::StartFailed;
    }

    active_ = &app;
    return StartResult::Started;
}

void AppRuntime::stop() {
    if (!active_) return;
    const OwnerId owner = active_->descriptor().id;
    active_->onStop();
    resources_.releaseAll(owner);
    active_ = nullptr;
}

void AppRuntime::dispatch(const AppEvent& event) {
    if (active_) active_->onEvent(event);
}

void AppRuntime::tick(uint32_t nowMs) {
    if (active_) active_->onTick(nowMs);
}

}  // namespace runtime
}  // namespace leshy
