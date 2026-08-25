#include "TargetCatalog.h"

#include <cstring>

namespace leshy1::domain::targets {
namespace {

bool exactText(const char* value, std::size_t length) {
    if (value == nullptr) return false;
    for (std::size_t index = 0; index < length; ++index) {
        if (value[index] == '\0') return false;
    }
    return value[length] == '\0';
}

bool sameEvidenceKey(const TargetEvidenceRef& left,
                     const TargetEvidenceRef& right) {
    return left.sourceId.bytes == right.sourceId.bytes &&
        left.sourceGeneration == right.sourceGeneration &&
        left.observationSequence == right.observationSequence;
}

template <std::size_t Capacity>
TargetMutationStatus setText(std::array<char, Capacity + 1>& target,
                             std::size_t* targetLength, const char* value,
                             std::size_t length) {
    if (length > Capacity) return TargetMutationStatus::TextTooLong;
    if (!exactText(value, length)) {
        return TargetMutationStatus::InvalidArgument;
    }
    if (*targetLength == length &&
        std::memcmp(target.data(), value, length) == 0) {
        return TargetMutationStatus::Unchanged;
    }
    target.fill('\0');
    if (length != 0) std::memcpy(target.data(), value, length);
    *targetLength = length;
    return TargetMutationStatus::Applied;
}

}  // namespace

const char* targetMutationStatusName(TargetMutationStatus status) {
    switch (status) {
        case TargetMutationStatus::Created: return "created";
        case TargetMutationStatus::Applied: return "applied";
        case TargetMutationStatus::Unchanged: return "unchanged";
        case TargetMutationStatus::InvalidArgument: return "invalid_argument";
        case TargetMutationStatus::NotFound: return "not_found";
        case TargetMutationStatus::DuplicateId: return "duplicate_id";
        case TargetMutationStatus::IdentityConflict: return "identity_conflict";
        case TargetMutationStatus::EvidenceConflict: return "evidence_conflict";
        case TargetMutationStatus::CatalogFull: return "catalog_full";
        case TargetMutationStatus::IdentityFull: return "identity_full";
        case TargetMutationStatus::EvidenceFull: return "evidence_full";
        case TargetMutationStatus::TagFull: return "tag_full";
        case TargetMutationStatus::TextTooLong: return "text_too_long";
    }
    return "invalid_argument";
}

void TargetCatalog::clear() {
    records_.fill(TargetRecord{});
    size_ = 0;
}

TargetMutationStatus TargetCatalog::create(
    const TargetId& id, const TargetIdentity& identity,
    const TargetEvidenceRef& evidence) {
    if (!targetIdValid(id) || !targetIdentityValid(identity) ||
        !targetEvidenceValid(evidence)) {
        return TargetMutationStatus::InvalidArgument;
    }
    if (find(id) != nullptr) return TargetMutationStatus::DuplicateId;
    if (findByIdentity(identity) != nullptr) {
        return TargetMutationStatus::IdentityConflict;
    }
    if (findByEvidence(evidence) != nullptr) {
        return TargetMutationStatus::EvidenceConflict;
    }
    if (size_ >= records_.size()) return TargetMutationStatus::CatalogFull;

    TargetRecord& record = records_[size_++];
    record = {};
    record.id = id;
    record.identities[0] = identity;
    record.identityCount = 1;
    record.evidence[0] = evidence;
    record.evidenceCount = 1;
    record.revision = 1;
    return TargetMutationStatus::Created;
}

TargetMutationStatus TargetCatalog::attachEvidence(
    const TargetId& id, const TargetIdentity& identity,
    const TargetEvidenceRef& evidence) {
    if (!targetIdValid(id) || !targetIdentityValid(identity) ||
        !targetEvidenceValid(evidence)) {
        return TargetMutationStatus::InvalidArgument;
    }
    TargetRecord* record = findMutable(id);
    if (record == nullptr) return TargetMutationStatus::NotFound;
    TargetRecord* identityOwner = findMutableByIdentity(identity);
    if (identityOwner != nullptr && identityOwner != record) {
        return TargetMutationStatus::IdentityConflict;
    }
    TargetRecord* evidenceOwner = findMutableByEvidence(evidence);
    if (evidenceOwner != nullptr && evidenceOwner != record) {
        return TargetMutationStatus::EvidenceConflict;
    }
    for (std::size_t index = 0; index < record->evidenceCount; ++index) {
        if (sameEvidenceKey(record->evidence[index], evidence)) {
            return targetEvidenceEqual(record->evidence[index], evidence) &&
                    identityOwner == record
                ? TargetMutationStatus::Unchanged
                : TargetMutationStatus::EvidenceConflict;
        }
    }

    const bool identityKnown = identityOwner == record;
    if (!identityKnown && record->identityCount >= record->identities.size()) {
        return TargetMutationStatus::IdentityFull;
    }
    if (record->evidenceCount >= record->evidence.size()) {
        return TargetMutationStatus::EvidenceFull;
    }
    if (!identityKnown) {
        record->identities[record->identityCount++] = identity;
    }
    record->evidence[record->evidenceCount++] = evidence;
    ++record->revision;
    return TargetMutationStatus::Applied;
}

TargetMutationStatus TargetCatalog::setName(const TargetId& id,
                                             const char* value,
                                             std::size_t length) {
    TargetRecord* record = findMutable(id);
    if (record == nullptr) return TargetMutationStatus::NotFound;
    std::size_t currentLength = record->nameLength;
    const TargetMutationStatus status = setText<TargetRecord::kNameCapacity>(
        record->name, &currentLength, value, length);
    if (status == TargetMutationStatus::Applied) {
        record->nameLength = static_cast<std::uint8_t>(currentLength);
        ++record->revision;
    }
    return status;
}

TargetMutationStatus TargetCatalog::setNotes(const TargetId& id,
                                              const char* value,
                                              std::size_t length) {
    TargetRecord* record = findMutable(id);
    if (record == nullptr) return TargetMutationStatus::NotFound;
    std::size_t currentLength = record->notesLength;
    const TargetMutationStatus status = setText<TargetRecord::kNotesCapacity>(
        record->notes, &currentLength, value, length);
    if (status == TargetMutationStatus::Applied) {
        record->notesLength = static_cast<std::uint16_t>(currentLength);
        ++record->revision;
    }
    return status;
}

TargetMutationStatus TargetCatalog::addTag(const TargetId& id,
                                           const char* value,
                                           std::size_t length) {
    TargetRecord* record = findMutable(id);
    if (record == nullptr) return TargetMutationStatus::NotFound;
    if (length > TargetRecord::kTagCapacity) {
        return TargetMutationStatus::TextTooLong;
    }
    if (!exactText(value, length) || length == 0) {
        return TargetMutationStatus::InvalidArgument;
    }
    for (std::size_t index = 0; index < record->tagCount; ++index) {
        if (record->tagLengths[index] == length &&
            std::memcmp(record->tags[index].data(), value, length) == 0) {
            return TargetMutationStatus::Unchanged;
        }
    }
    if (record->tagCount >= record->tags.size()) {
        return TargetMutationStatus::TagFull;
    }
    const std::size_t index = record->tagCount++;
    record->tags[index].fill('\0');
    std::memcpy(record->tags[index].data(), value, length);
    record->tagLengths[index] = static_cast<std::uint8_t>(length);
    ++record->revision;
    return TargetMutationStatus::Applied;
}

TargetMutationStatus TargetCatalog::removeTag(const TargetId& id,
                                              const char* value,
                                              std::size_t length) {
    TargetRecord* record = findMutable(id);
    if (record == nullptr) return TargetMutationStatus::NotFound;
    if (length > TargetRecord::kTagCapacity) {
        return TargetMutationStatus::TextTooLong;
    }
    if (!exactText(value, length) || length == 0) {
        return TargetMutationStatus::InvalidArgument;
    }
    for (std::size_t index = 0; index < record->tagCount; ++index) {
        if (record->tagLengths[index] != length ||
            std::memcmp(record->tags[index].data(), value, length) != 0) {
            continue;
        }
        for (std::size_t move = index + 1; move < record->tagCount; ++move) {
            record->tags[move - 1] = record->tags[move];
            record->tagLengths[move - 1] = record->tagLengths[move];
        }
        --record->tagCount;
        record->tags[record->tagCount].fill('\0');
        record->tagLengths[record->tagCount] = 0;
        ++record->revision;
        return TargetMutationStatus::Applied;
    }
    return TargetMutationStatus::Unchanged;
}

TargetMutationStatus TargetCatalog::setFavorite(const TargetId& id, bool value) {
    TargetRecord* record = findMutable(id);
    if (record == nullptr) return TargetMutationStatus::NotFound;
    if (record->favorite == value) return TargetMutationStatus::Unchanged;
    record->favorite = value;
    ++record->revision;
    return TargetMutationStatus::Applied;
}

const TargetRecord* TargetCatalog::get(std::size_t index) const {
    return index < size_ ? &records_[index] : nullptr;
}

const TargetRecord* TargetCatalog::find(const TargetId& id) const {
    for (std::size_t index = 0; index < size_; ++index) {
        if (targetIdEqual(records_[index].id, id)) return &records_[index];
    }
    return nullptr;
}

const TargetRecord* TargetCatalog::findByIdentity(
    const TargetIdentity& identity) const {
    for (std::size_t index = 0; index < size_; ++index) {
        const TargetRecord& record = records_[index];
        for (std::size_t identityIndex = 0;
             identityIndex < record.identityCount; ++identityIndex) {
            if (targetIdentityEqual(record.identities[identityIndex], identity)) {
                return &record;
            }
        }
    }
    return nullptr;
}

const TargetRecord* TargetCatalog::findByEvidence(
    const TargetEvidenceRef& evidence) const {
    for (std::size_t index = 0; index < size_; ++index) {
        const TargetRecord& record = records_[index];
        for (std::size_t evidenceIndex = 0;
             evidenceIndex < record.evidenceCount; ++evidenceIndex) {
            if (sameEvidenceKey(record.evidence[evidenceIndex], evidence)) {
                return &record;
            }
        }
    }
    return nullptr;
}

TargetRecord* TargetCatalog::findMutable(const TargetId& id) {
    return const_cast<TargetRecord*>(
        static_cast<const TargetCatalog*>(this)->find(id));
}

TargetRecord* TargetCatalog::findMutableByIdentity(
    const TargetIdentity& identity) {
    return const_cast<TargetRecord*>(
        static_cast<const TargetCatalog*>(this)->findByIdentity(identity));
}

TargetRecord* TargetCatalog::findMutableByEvidence(
    const TargetEvidenceRef& evidence) {
    return const_cast<TargetRecord*>(
        static_cast<const TargetCatalog*>(this)->findByEvidence(evidence));
}

}  // namespace leshy1::domain::targets
