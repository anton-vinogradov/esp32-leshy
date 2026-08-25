#include "TargetMergeService.h"

#include <array>

namespace leshy1::services::targets {
namespace {

constexpr kernel::runtime::ResourceMask kTargetMergeResources =
    kernel::runtime::resourceMask(kernel::runtime::Resource::Storage);

constexpr std::array<TargetMergeActionDescriptor, 2> kDescriptors{{
    {"target.merge", 1, 1, "targets.write", "local_library_write",
     kTargetMergeResources, 75, false},
    {"target.split", 1, 1, "targets.write", "local_library_write",
     kTargetMergeResources, 75, false},
}};

}  // namespace

const TargetMergeActionDescriptor* targetMergeActionDescriptor(
    TargetMergeActionKind kind) {
    const std::uint8_t raw = static_cast<std::uint8_t>(kind);
    if (raw == 0 || raw > kDescriptors.size()) return nullptr;
    return &kDescriptors[raw - 1U];
}

TargetMergeActionResult TargetMergeService::execute(
    const TargetMergeAction& action) {
    TargetMergeActionResult result{};
    result.kind = action.kind;
    result.operationId = action.operationId;
    if (action.schemaVersion != kTargetMergeActionSchemaVersion ||
        targetMergeActionDescriptor(action.kind) == nullptr) {
        return result;
    }
    switch (action.kind) {
        case TargetMergeActionKind::Merge:
            result.status = history_.merge(
                catalog_, action.operationId, action.destinationId,
                action.sourceId, action.expectedDestinationRevision,
                action.expectedSourceRevision);
            break;
        case TargetMergeActionKind::Split:
            result.status = history_.split(catalog_, action.operationId);
            break;
    }
    const domain::targets::TargetMergeRecord* record =
        history_.find(action.operationId);
    if (record != nullptr) {
        const domain::targets::TargetRecord* destination =
            catalog_.find(record->destinationBefore.id);
        const domain::targets::TargetRecord* source =
            catalog_.find(record->sourceBefore.id);
        result.destinationRevision =
            destination == nullptr ? 0 : destination->revision;
        result.sourceRevision = source == nullptr ? 0 : source->revision;
    }
    return result;
}

}  // namespace leshy1::services::targets
