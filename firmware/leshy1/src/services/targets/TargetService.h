#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/targets/TargetCatalog.h"
#include "kernel/runtime/Resources.h"

namespace leshy1::services::targets {

constexpr std::uint16_t kTargetActionSchemaVersion = 1;
constexpr std::uint16_t kTargetActionResultSchemaVersion = 1;

enum class TargetActionKind : std::uint8_t {
    Create = 1,
    AttachEvidence = 2,
    SetName = 3,
    SetNotes = 4,
    AddTag = 5,
    RemoveTag = 6,
    SetFavorite = 7,
};

enum class TargetActionSafetyClass : std::uint8_t {
    DataMutation,
};

struct TargetActionDescriptor final {
    const char* id = nullptr;
    std::uint16_t requestSchemaVersion = 0;
    std::uint16_t resultSchemaVersion = 0;
    const char* requiredCapability = nullptr;
    const char* requiredPermission = nullptr;
    kernel::runtime::ResourceMask requiredResources = 0;
    TargetActionSafetyClass safetyClass = TargetActionSafetyClass::DataMutation;
    std::uint16_t timeoutMs = 0;
    bool cancellable = false;
};

const TargetActionDescriptor* targetActionDescriptor(TargetActionKind kind);

struct TargetAction final {
    static constexpr std::size_t kTextCapacity =
        domain::targets::TargetRecord::kNotesCapacity;

    std::uint16_t schemaVersion = kTargetActionSchemaVersion;
    TargetActionKind kind = TargetActionKind::Create;
    domain::targets::TargetId targetId{};
    domain::targets::TargetIdentity identity{};
    domain::targets::TargetEvidenceRef evidence{};
    // Existing-record mutations require the exact revision presented to the
    // caller. Create and AttachEvidence retain their original identity/evidence
    // conflict rules and leave this field zero.
    std::uint32_t expectedRevision = 0;
    std::array<char, kTextCapacity + 1> text{};
    std::uint16_t textLength = 0;
    bool favorite = false;
};

struct TargetActionResult final {
    std::uint16_t schemaVersion = kTargetActionResultSchemaVersion;
    TargetActionKind kind = TargetActionKind::Create;
    domain::targets::TargetMutationStatus status =
        domain::targets::TargetMutationStatus::InvalidArgument;
    domain::targets::TargetId targetId{};
    std::uint32_t revision = 0;

    bool applied() const {
        return status == domain::targets::TargetMutationStatus::Created ||
            status == domain::targets::TargetMutationStatus::Applied;
    }
};

// The same typed request/result is intended for UI, serial automation and the
// S6 companion adapter. This service has no radio/driver access.
class TargetService final {
public:
    explicit TargetService(domain::targets::TargetCatalog& catalog)
        : catalog_(catalog) {}

    TargetActionResult execute(const TargetAction& action);
    TargetActionResult preview(const TargetAction& action) const;

private:
    domain::targets::TargetCatalog& catalog_;
};

bool setTargetActionText(TargetAction* action, const char* value,
                         std::size_t length);

// Const preview entry point for adapters that are intentionally given only a
// read-only snapshot. It applies the same schema, value and optimistic-
// revision validation as TargetService::execute without changing the catalog.
TargetActionResult previewTargetAction(
    const domain::targets::TargetCatalog& catalog,
    const TargetAction& action);

}  // namespace leshy1::services::targets
