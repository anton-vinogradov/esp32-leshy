#pragma once

#include <cstdint>

#include "kernel/runtime/ResourceBroker.h"

namespace leshy1::services::actions {

using ActionCapabilityMask = std::uint32_t;
using ActionPermissionMask = std::uint32_t;

enum class ActionPermission : ActionPermissionMask {
    DeviceControl = 1U << 0U,
    SerialMonitor = 1U << 1U,
    SerialWrite = 1U << 2U,
};

constexpr ActionPermissionMask actionPermission(ActionPermission permission) {
    return static_cast<ActionPermissionMask>(permission);
}

constexpr ActionPermissionMask kKnownActionPermissions =
    actionPermission(ActionPermission::DeviceControl) |
    actionPermission(ActionPermission::SerialMonitor) |
    actionPermission(ActionPermission::SerialWrite);

enum class ActionSafetyClass : std::uint8_t {
    Passive,
    Protected,
    ActiveConfirmed,
};

struct ActionDescriptor final {
    const char* id = nullptr;
    std::uint16_t version = 0;
    std::uint16_t requestSchemaVersion = 0;
    std::uint16_t resultSchemaVersion = 0;
    ActionCapabilityMask requiredCapabilities = 0;
    kernel::runtime::ResourceMask requiredResources = 0;
    ActionPermissionMask requiredPermissions = 0;
    ActionSafetyClass safety = ActionSafetyClass::Passive;
    std::uint32_t timeoutMs = 0;
    bool cancellable = false;
};

struct ActionContext final {
    std::uint16_t requestSchemaVersion = 0;
    ActionCapabilityMask availableCapabilities = 0;
    ActionPermissionMask grantedPermissions = 0;
    bool authenticated = false;
    bool confirmed = false;
};

enum class ActionStatus : std::uint8_t {
    Ready,
    InvalidDescriptor,
    SchemaMismatch,
    AuthenticationRequired,
    PermissionDenied,
    CapabilityUnavailable,
    ConfirmationRequired,
    Busy,
    StartFailed,
    Running,
    Completed,
    Cancelled,
    TimedOut,
    Failed,
};

const char* actionStatusName(ActionStatus status);

struct ActionAssessment final {
    ActionStatus status = ActionStatus::InvalidDescriptor;
    bool confirmationRequired = false;

    bool ready() const { return status == ActionStatus::Ready; }
};

enum class ActionEndpointState : std::uint8_t {
    Running,
    Completed,
    Failed,
};

class ActionEndpoint {
public:
    virtual ~ActionEndpoint() = default;
    virtual bool start(std::uint32_t nowMs) = 0;
    virtual ActionEndpointState tick(std::uint32_t nowMs) = 0;
    virtual void cancel() = 0;
};

class ActionDispatcher final {
public:
    static constexpr kernel::runtime::ResourceOwner kDefaultOwner = 8U;

    explicit ActionDispatcher(
        kernel::runtime::ResourceBroker& broker,
        kernel::runtime::ResourceOwner owner = kDefaultOwner)
        : broker_(broker), owner_(owner) {}

    ActionAssessment preview(const ActionDescriptor& descriptor,
                             const ActionContext& context) const;
    ActionStatus invoke(const ActionDescriptor& descriptor,
                        const ActionContext& context,
                        ActionEndpoint& endpoint,
                        std::uint32_t nowMs);
    ActionStatus tick(std::uint32_t nowMs);
    ActionStatus cancel();

    bool running() const { return endpoint_ != nullptr; }
    ActionStatus status() const { return status_; }
    const char* activeActionId() const;
    kernel::runtime::ResourceMask ownedResources() const {
        return broker_.ownedBy(owner_);
    }

private:
    ActionAssessment assess(const ActionDescriptor& descriptor,
                            const ActionContext& context,
                            bool requireConfirmation) const;
    void finish(ActionStatus status);

    kernel::runtime::ResourceBroker& broker_;
    kernel::runtime::ResourceOwner owner_;
    ActionEndpoint* endpoint_ = nullptr;
    ActionDescriptor descriptor_{};
    bool descriptorActive_ = false;
    std::uint32_t startedMs_ = 0;
    ActionStatus status_ = ActionStatus::Ready;
};

}  // namespace leshy1::services::actions
