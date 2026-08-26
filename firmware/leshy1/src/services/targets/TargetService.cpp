#include "TargetService.h"

#include <cstring>

namespace leshy1::services::targets {
namespace {

using domain::targets::TargetMutationStatus;

constexpr kernel::runtime::ResourceMask kTargetWriteResources =
    kernel::runtime::resourceMask(kernel::runtime::Resource::Storage);

constexpr std::array<TargetActionDescriptor, 7> kDescriptors{{
    {"target.create", 1, 1, "targets.write", "local_library_write",
     kTargetWriteResources, TargetActionSafetyClass::DataMutation, 50, false},
    {"target.evidence.attach", 1, 1, "targets.write", "local_library_write",
     kTargetWriteResources, TargetActionSafetyClass::DataMutation, 50, false},
    {"target.name.set", 1, 1, "targets.write", "local_library_write",
     kTargetWriteResources, TargetActionSafetyClass::DataMutation, 50, false},
    {"target.notes.set", 1, 1, "targets.write", "local_library_write",
     kTargetWriteResources, TargetActionSafetyClass::DataMutation, 50, false},
    {"target.tag.add", 1, 1, "targets.write", "local_library_write",
     kTargetWriteResources, TargetActionSafetyClass::DataMutation, 50, false},
    {"target.tag.remove", 1, 1, "targets.write", "local_library_write",
     kTargetWriteResources, TargetActionSafetyClass::DataMutation, 50, false},
    {"target.favorite.set", 1, 1, "targets.write", "local_library_write",
     kTargetWriteResources, TargetActionSafetyClass::DataMutation, 50, false},
}};

bool actionTextValid(const TargetAction& action, std::size_t maximum,
                     bool allowEmpty) {
    if (action.textLength > maximum ||
        action.textLength >= action.text.size() ||
        (!allowEmpty && action.textLength == 0) ||
        action.text[action.textLength] != '\0') {
        return false;
    }
    for (std::size_t index = 0; index < action.textLength; ++index) {
        if (action.text[index] == '\0') return false;
    }
    return true;
}

TargetActionResult previewMetadataAction(
    const domain::targets::TargetCatalog& catalog,
    const TargetAction& action) {
    TargetActionResult result{};
    result.kind = action.kind;
    result.targetId = action.targetId;
    const auto* current = catalog.find(action.targetId);
    if (current == nullptr) {
        result.status = TargetMutationStatus::NotFound;
        return result;
    }
    result.revision = current->revision;
    if (action.expectedRevision == 0 ||
        action.expectedRevision != current->revision) {
        result.status = TargetMutationStatus::RevisionConflict;
        return result;
    }

    domain::targets::TargetRecord candidate = *current;
    switch (action.kind) {
        case TargetActionKind::SetName:
            if (!actionTextValid(
                    action, domain::targets::TargetRecord::kNameCapacity,
                    true)) {
                result.status = action.textLength >
                        domain::targets::TargetRecord::kNameCapacity
                    ? TargetMutationStatus::TextTooLong
                    : TargetMutationStatus::InvalidArgument;
                return result;
            }
            if (candidate.nameLength == action.textLength &&
                std::memcmp(candidate.name.data(), action.text.data(),
                            action.textLength) == 0) {
                result.status = TargetMutationStatus::Unchanged;
                return result;
            }
            candidate.name.fill('\0');
            if (action.textLength != 0) {
                std::memcpy(candidate.name.data(), action.text.data(),
                            action.textLength);
            }
            candidate.nameLength = static_cast<std::uint8_t>(action.textLength);
            break;
        case TargetActionKind::SetNotes:
            if (!actionTextValid(
                    action, domain::targets::TargetRecord::kNotesCapacity,
                    true)) {
                result.status = action.textLength >
                        domain::targets::TargetRecord::kNotesCapacity
                    ? TargetMutationStatus::TextTooLong
                    : TargetMutationStatus::InvalidArgument;
                return result;
            }
            if (candidate.notesLength == action.textLength &&
                std::memcmp(candidate.notes.data(), action.text.data(),
                            action.textLength) == 0) {
                result.status = TargetMutationStatus::Unchanged;
                return result;
            }
            candidate.notes.fill('\0');
            if (action.textLength != 0) {
                std::memcpy(candidate.notes.data(), action.text.data(),
                            action.textLength);
            }
            candidate.notesLength = action.textLength;
            break;
        case TargetActionKind::AddTag:
        case TargetActionKind::RemoveTag: {
            if (!actionTextValid(
                    action, domain::targets::TargetRecord::kTagCapacity,
                    false)) {
                result.status = action.textLength >
                        domain::targets::TargetRecord::kTagCapacity
                    ? TargetMutationStatus::TextTooLong
                    : TargetMutationStatus::InvalidArgument;
                return result;
            }
            std::size_t found = candidate.tagCount;
            for (std::size_t index = 0; index < candidate.tagCount; ++index) {
                if (candidate.tagLengths[index] == action.textLength &&
                    std::memcmp(candidate.tags[index].data(),
                                action.text.data(), action.textLength) == 0) {
                    found = index;
                    break;
                }
            }
            if (action.kind == TargetActionKind::AddTag) {
                if (found != candidate.tagCount) {
                    result.status = TargetMutationStatus::Unchanged;
                    return result;
                }
                if (candidate.tagCount >= candidate.tags.size()) {
                    result.status = TargetMutationStatus::TagFull;
                    return result;
                }
                const std::size_t index = candidate.tagCount++;
                candidate.tags[index].fill('\0');
                std::memcpy(candidate.tags[index].data(), action.text.data(),
                            action.textLength);
                candidate.tagLengths[index] =
                    static_cast<std::uint8_t>(action.textLength);
            } else {
                if (found == candidate.tagCount) {
                    result.status = TargetMutationStatus::Unchanged;
                    return result;
                }
                for (std::size_t index = found + 1U;
                     index < candidate.tagCount; ++index) {
                    candidate.tags[index - 1U] = candidate.tags[index];
                    candidate.tagLengths[index - 1U] =
                        candidate.tagLengths[index];
                }
                --candidate.tagCount;
                candidate.tags[candidate.tagCount].fill('\0');
                candidate.tagLengths[candidate.tagCount] = 0;
            }
            break;
        }
        case TargetActionKind::SetFavorite:
            if (candidate.favorite == action.favorite) {
                result.status = TargetMutationStatus::Unchanged;
                return result;
            }
            candidate.favorite = action.favorite;
            break;
        case TargetActionKind::Create:
        case TargetActionKind::AttachEvidence:
            result.status = TargetMutationStatus::InvalidArgument;
            return result;
    }
    ++candidate.revision;
    const TargetMutationStatus validation =
        domain::targets::validateTargetRecord(candidate);
    if (validation != TargetMutationStatus::Created) {
        result.status = validation;
        return result;
    }
    result.status = TargetMutationStatus::Applied;
    result.revision = candidate.revision;
    return result;
}

}  // namespace

const TargetActionDescriptor* targetActionDescriptor(TargetActionKind kind) {
    const std::uint8_t raw = static_cast<std::uint8_t>(kind);
    if (raw == 0 || raw > kDescriptors.size()) return nullptr;
    return &kDescriptors[raw - 1U];
}

bool setTargetActionText(TargetAction* action, const char* value,
                         std::size_t length) {
    if (action == nullptr || value == nullptr ||
        length > TargetAction::kTextCapacity) {
        return false;
    }
    for (std::size_t index = 0; index < length; ++index) {
        if (value[index] == '\0') return false;
    }
    action->text.fill('\0');
    if (length != 0) std::memcpy(action->text.data(), value, length);
    action->textLength = static_cast<std::uint16_t>(length);
    return true;
}

TargetActionResult TargetService::execute(const TargetAction& action) {
    TargetActionResult result{};
    result.kind = action.kind;
    result.targetId = action.targetId;
    const TargetActionDescriptor* descriptor =
        targetActionDescriptor(action.kind);
    if (action.schemaVersion != kTargetActionSchemaVersion ||
        descriptor == nullptr) {
        return result;
    }

    if (action.kind != TargetActionKind::Create &&
        action.kind != TargetActionKind::AttachEvidence) {
        const TargetActionResult inspected = preview(action);
        if (inspected.status != TargetMutationStatus::Applied) {
            return inspected;
        }
    }

    switch (action.kind) {
        case TargetActionKind::Create:
            result.status = catalog_.create(
                action.targetId, action.identity, action.evidence);
            break;
        case TargetActionKind::AttachEvidence:
            result.status = catalog_.attachEvidence(
                action.targetId, action.identity, action.evidence);
            break;
        case TargetActionKind::SetName:
            if (!actionTextValid(
                    action, domain::targets::TargetRecord::kNameCapacity, true)) {
                break;
            }
            result.status = catalog_.setName(
                action.targetId, action.text.data(), action.textLength);
            break;
        case TargetActionKind::SetNotes:
            if (!actionTextValid(
                    action, domain::targets::TargetRecord::kNotesCapacity, true)) {
                break;
            }
            result.status = catalog_.setNotes(
                action.targetId, action.text.data(), action.textLength);
            break;
        case TargetActionKind::AddTag:
            if (!actionTextValid(
                    action, domain::targets::TargetRecord::kTagCapacity, false)) {
                break;
            }
            result.status = catalog_.addTag(
                action.targetId, action.text.data(), action.textLength);
            break;
        case TargetActionKind::RemoveTag:
            if (!actionTextValid(
                    action, domain::targets::TargetRecord::kTagCapacity, false)) {
                break;
            }
            result.status = catalog_.removeTag(
                action.targetId, action.text.data(), action.textLength);
            break;
        case TargetActionKind::SetFavorite:
            result.status = catalog_.setFavorite(
                action.targetId, action.favorite);
            break;
    }

    const domain::targets::TargetRecord* record = catalog_.find(action.targetId);
    if (record != nullptr) result.revision = record->revision;
    return result;
}

TargetActionResult TargetService::preview(const TargetAction& action) const {
    return previewTargetAction(catalog_, action);
}

TargetActionResult previewTargetAction(
    const domain::targets::TargetCatalog& catalog,
    const TargetAction& action) {
    const TargetActionDescriptor* descriptor =
        targetActionDescriptor(action.kind);
    if (action.schemaVersion != kTargetActionSchemaVersion ||
        descriptor == nullptr || action.kind == TargetActionKind::Create ||
        action.kind == TargetActionKind::AttachEvidence) {
        TargetActionResult result{};
        result.kind = action.kind;
        result.targetId = action.targetId;
        return result;
    }
    return previewMetadataAction(catalog, action);
}

}  // namespace leshy1::services::targets
