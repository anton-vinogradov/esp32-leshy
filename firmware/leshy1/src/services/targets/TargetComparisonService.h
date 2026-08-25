#pragma once

#include <cstdint>

#include "domain/targets/TargetComparison.h"
#include "kernel/runtime/Resources.h"

namespace leshy1::services::targets {

constexpr std::uint16_t kTargetComparisonActionSchemaVersion = 1;
constexpr std::uint16_t kTargetComparisonResultSchemaVersion = 1;

struct TargetComparisonActionDescriptor final {
    const char* id = nullptr;
    std::uint16_t requestSchemaVersion = 0;
    std::uint16_t resultSchemaVersion = 0;
    const char* requiredCapability = nullptr;
    const char* requiredPermission = nullptr;
    kernel::runtime::ResourceMask requiredResources = 0;
    std::uint16_t timeoutMs = 0;
    bool cancellable = false;
};

const TargetComparisonActionDescriptor& targetComparisonActionDescriptor();

struct TargetComparisonAction final {
    std::uint16_t schemaVersion = kTargetComparisonActionSchemaVersion;
    domain::targets::TargetComparisonSource baseline{};
    domain::targets::TargetComparisonSource current{};
};

// Read-only Action boundary shared by the future TFT and local companion. It
// has no radio access and never mutates either Session or the Target graph.
class TargetComparisonService final {
public:
    TargetComparisonService(
        const domain::targets::TargetCatalog& catalog,
        const domain::targets::TargetComparisonEvidenceLookup& evidenceLookup)
        : catalog_(catalog), evidenceLookup_(evidenceLookup) {}

    domain::targets::TargetComparisonStatus executeInto(
        const TargetComparisonAction& action,
        domain::targets::TargetComparisonResult* output) const;

private:
    const domain::targets::TargetCatalog& catalog_;
    const domain::targets::TargetComparisonEvidenceLookup& evidenceLookup_;
};

}  // namespace leshy1::services::targets
