#include "ActionDispatcher.h"

#include <cstddef>

namespace leshy1::services::actions {
namespace {

constexpr std::size_t kMaximumActionIdLength = 48U;
constexpr std::uint32_t kMaximumActionTimeoutMs = 15U * 60U * 1000U;

bool validActionId(const char* value) {
    if (value == nullptr || value[0] == '\0') return false;
    std::size_t length = 0;
    for (; value[length] != '\0'; ++length) {
        if (length >= kMaximumActionIdLength) return false;
        const char character = value[length];
        const bool valid = (character >= 'a' && character <= 'z') ||
            (character >= '0' && character <= '9') || character == '.' ||
            character == '-' || character == '_';
        if (!valid) return false;
    }
    return length != 0U;
}

bool validDescriptor(const ActionDescriptor& descriptor) {
    return validActionId(descriptor.id) && descriptor.version != 0U &&
        descriptor.requestSchemaVersion != 0U &&
        descriptor.resultSchemaVersion != 0U &&
        descriptor.requiredResources != 0U &&
        (descriptor.requiredResources &
         ~kernel::runtime::kKnownResources) == 0U &&
        descriptor.requiredPermissions != 0U &&
        (descriptor.requiredPermissions & ~kKnownActionPermissions) == 0U &&
        descriptor.timeoutMs != 0U &&
        descriptor.timeoutMs <= kMaximumActionTimeoutMs;
}

}  // namespace

const char* actionStatusName(ActionStatus status) {
    switch (status) {
        case ActionStatus::Ready: return "ready";
        case ActionStatus::InvalidDescriptor: return "invalid_descriptor";
        case ActionStatus::SchemaMismatch: return "schema_mismatch";
        case ActionStatus::AuthenticationRequired:
            return "authentication_required";
        case ActionStatus::PermissionDenied: return "permission_denied";
        case ActionStatus::CapabilityUnavailable:
            return "capability_unavailable";
        case ActionStatus::ConfirmationRequired:
            return "confirmation_required";
        case ActionStatus::Busy: return "busy";
        case ActionStatus::StartFailed: return "start_failed";
        case ActionStatus::Running: return "running";
        case ActionStatus::Completed: return "completed";
        case ActionStatus::Cancelled: return "cancelled";
        case ActionStatus::TimedOut: return "timed_out";
        case ActionStatus::Failed: return "failed";
    }
    return "invalid_status";
}

ActionAssessment ActionDispatcher::assess(
    const ActionDescriptor& descriptor, const ActionContext& context,
    bool requireConfirmation) const {
    ActionAssessment result{};
    result.confirmationRequired =
        descriptor.safety == ActionSafetyClass::ActiveConfirmed;
    if (!validDescriptor(descriptor)) {
        result.status = ActionStatus::InvalidDescriptor;
    } else if (context.requestSchemaVersion !=
               descriptor.requestSchemaVersion) {
        result.status = ActionStatus::SchemaMismatch;
    } else if (descriptor.safety != ActionSafetyClass::Passive &&
               !context.authenticated) {
        result.status = ActionStatus::AuthenticationRequired;
    } else if ((context.grantedPermissions &
                descriptor.requiredPermissions) !=
               descriptor.requiredPermissions) {
        result.status = ActionStatus::PermissionDenied;
    } else if ((context.availableCapabilities &
                descriptor.requiredCapabilities) !=
               descriptor.requiredCapabilities) {
        result.status = ActionStatus::CapabilityUnavailable;
    } else if (requireConfirmation && result.confirmationRequired &&
               !context.confirmed) {
        result.status = ActionStatus::ConfirmationRequired;
    } else if (running()) {
        result.status = ActionStatus::Busy;
    } else {
        result.status = ActionStatus::Ready;
    }
    return result;
}

ActionAssessment ActionDispatcher::preview(
    const ActionDescriptor& descriptor, const ActionContext& context) const {
    return assess(descriptor, context, false);
}

ActionStatus ActionDispatcher::invoke(
    const ActionDescriptor& descriptor, const ActionContext& context,
    ActionEndpoint& endpoint, std::uint32_t nowMs) {
    const ActionAssessment assessment = assess(descriptor, context, true);
    if (!assessment.ready()) {
        if (!running()) status_ = assessment.status;
        return assessment.status;
    }
    if (owner_ == kernel::runtime::kNoOwner ||
        !broker_.acquire(owner_, descriptor.requiredResources)) {
        status_ = ActionStatus::Busy;
        return status_;
    }
    if (!endpoint.start(nowMs)) {
        broker_.releaseAll(owner_);
        status_ = ActionStatus::StartFailed;
        return status_;
    }
    endpoint_ = &endpoint;
    descriptor_ = descriptor;
    descriptorActive_ = true;
    startedMs_ = nowMs;
    status_ = ActionStatus::Running;
    return status_;
}

ActionStatus ActionDispatcher::tick(std::uint32_t nowMs) {
    if (!running() || !descriptorActive_) return status_;
    if (static_cast<std::uint32_t>(nowMs - startedMs_) >=
        descriptor_.timeoutMs) {
        endpoint_->cancel();
        finish(ActionStatus::TimedOut);
        return status_;
    }
    const ActionEndpointState endpointState = endpoint_->tick(nowMs);
    if (endpointState == ActionEndpointState::Completed) {
        finish(ActionStatus::Completed);
    } else if (endpointState == ActionEndpointState::Failed) {
        finish(ActionStatus::Failed);
    }
    return status_;
}

ActionStatus ActionDispatcher::cancel() {
    if (!running() || !descriptorActive_ || !descriptor_.cancellable) {
        return status_;
    }
    endpoint_->cancel();
    finish(ActionStatus::Cancelled);
    return status_;
}

const char* ActionDispatcher::activeActionId() const {
    return !descriptorActive_ ? "none" : descriptor_.id;
}

void ActionDispatcher::finish(ActionStatus status) {
    broker_.releaseAll(owner_);
    endpoint_ = nullptr;
    descriptor_ = {};
    descriptorActive_ = false;
    startedMs_ = 0;
    status_ = status;
}

}  // namespace leshy1::services::actions
