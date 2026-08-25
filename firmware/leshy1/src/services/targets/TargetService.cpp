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

}  // namespace leshy1::services::targets
