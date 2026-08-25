#pragma once

#include <cstdint>

#include "domain/targets/TargetMerge.h"
#include "kernel/runtime/Resources.h"

namespace leshy1::services::targets {

constexpr std::uint16_t kTargetMergeActionSchemaVersion = 1;
constexpr std::uint16_t kTargetMergeResultSchemaVersion = 1;

enum class TargetMergeActionKind : std::uint8_t {
    Merge = 1,
    Split = 2,
};

struct TargetMergeActionDescriptor final {
    const char* id = nullptr;
    std::uint16_t requestSchemaVersion = 0;
    std::uint16_t resultSchemaVersion = 0;
    const char* requiredCapability = nullptr;
    const char* requiredPermission = nullptr;
    kernel::runtime::ResourceMask requiredResources = 0;
    std::uint16_t timeoutMs = 0;
    bool cancellable = false;
};

const TargetMergeActionDescriptor* targetMergeActionDescriptor(
    TargetMergeActionKind kind);

struct TargetMergeAction final {
    std::uint16_t schemaVersion = kTargetMergeActionSchemaVersion;
    TargetMergeActionKind kind = TargetMergeActionKind::Merge;
    domain::targets::TargetMergeId operationId{};
    domain::targets::TargetId destinationId{};
    domain::targets::TargetId sourceId{};
    std::uint32_t expectedDestinationRevision = 0;
    std::uint32_t expectedSourceRevision = 0;
};

struct TargetMergeActionResult final {
    std::uint16_t schemaVersion = kTargetMergeResultSchemaVersion;
    TargetMergeActionKind kind = TargetMergeActionKind::Merge;
    domain::targets::TargetMergeStatus status =
        domain::targets::TargetMergeStatus::InvalidArgument;
    domain::targets::TargetMergeId operationId{};
    std::uint32_t destinationRevision = 0;
    std::uint32_t sourceRevision = 0;

    bool applied() const {
        return status == domain::targets::TargetMergeStatus::Merged ||
            status == domain::targets::TargetMergeStatus::Split;
    }
};

// UI, serial automation and the future companion share this explicit mutation
// boundary. It owns no radio/driver capability and requires Storage only.
class TargetMergeService final {
public:
    TargetMergeService(domain::targets::TargetCatalog& catalog,
                       domain::targets::TargetMergeHistory& history)
        : catalog_(catalog), history_(history) {}

    TargetMergeActionResult execute(const TargetMergeAction& action);

private:
    domain::targets::TargetCatalog& catalog_;
    domain::targets::TargetMergeHistory& history_;
};

}  // namespace leshy1::services::targets
