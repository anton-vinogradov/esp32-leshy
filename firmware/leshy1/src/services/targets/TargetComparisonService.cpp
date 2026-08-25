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

domain::targets::TargetComparisonResult TargetComparisonService::execute(
    const TargetComparisonAction& action) const {
    if (action.schemaVersion != kTargetComparisonActionSchemaVersion) {
        return {};
    }
    return domain::targets::compareTargetSessions(
        catalog_, action.baseline, action.current, evidenceLookup_);
}

}  // namespace leshy1::services::targets
