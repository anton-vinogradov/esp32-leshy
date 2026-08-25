#include "TargetComparisonService.h"

namespace leshy1::services::targets {
namespace {

constexpr TargetComparisonActionDescriptor kDescriptor{
    "target.compare", 1, 1, "targets.compare", "local_library_read",
    kernel::runtime::resourceMask(kernel::runtime::Resource::Storage),
    100, false,
};

}  // namespace

const TargetComparisonActionDescriptor& targetComparisonActionDescriptor() {
    return kDescriptor;
}

domain::targets::TargetComparisonStatus TargetComparisonService::executeInto(
    const TargetComparisonAction& action,
    domain::targets::TargetComparisonResult* output) const {
    if (action.schemaVersion != kTargetComparisonActionSchemaVersion) {
        if (output != nullptr) *output = {};
        return domain::targets::TargetComparisonStatus::InvalidArgument;
    }
    return domain::targets::compareTargetSessionsInto(
        catalog_, action.baseline, action.current, evidenceLookup_, output);
}

}  // namespace leshy1::services::targets
