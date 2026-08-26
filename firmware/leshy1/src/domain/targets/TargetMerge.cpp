#include "TargetMerge.h"

#include <cstring>
#include <limits>

namespace leshy1::domain::targets {
namespace {

bool mergeKeyEqual(const TargetMergeRecord& record,
                   const TargetId& destinationId,
                   const TargetId& sourceId,
                   std::uint32_t expectedDestinationRevision,
                   std::uint32_t expectedSourceRevision) {
    return targetIdEqual(record.destinationBefore.id, destinationId) &&
        targetIdEqual(record.sourceBefore.id, sourceId) &&
        record.destinationBefore.revision == expectedDestinationRevision &&
        record.sourceBefore.revision == expectedSourceRevision;
}

bool sameEvidenceKey(const TargetEvidenceRef& left,
                     const TargetEvidenceRef& right) {
    return left.sourceId.bytes == right.sourceId.bytes &&
        left.sourceGeneration == right.sourceGeneration &&
        left.observationSequence == right.observationSequence;
}

std::size_t catalogIndex(const TargetCatalog& catalog, const TargetId& id) {
    for (std::size_t index = 0; index < catalog.size(); ++index) {
        const TargetRecord* record = catalog.get(index);
        if (record != nullptr && targetIdEqual(record->id, id)) return index;
    }
    return catalog.size();
}

TargetMergeStatus rebuildMergedCatalog(
    TargetCatalog& catalog, std::size_t destinationIndex,
    std::size_t sourceIndex, const TargetRecord& merged) {
    TargetCatalog candidate;
    for (std::size_t index = 0; index < catalog.size(); ++index) {
        if (index == sourceIndex) continue;
        const TargetRecord* current = catalog.get(index);
        const TargetRecord& selected =
            index == destinationIndex ? merged : *current;
        if (candidate.restore(selected) != TargetMutationStatus::Created) {
            return TargetMergeStatus::CatalogConflict;
        }
    }
    catalog = candidate;
    return TargetMergeStatus::Merged;
}

TargetMergeStatus rebuildSplitCatalog(TargetCatalog& catalog,
                                      const TargetMergeRecord& merge) {
    if (catalog.size() + 1U != merge.originalCatalogSize) {
        return TargetMergeStatus::CatalogConflict;
    }
    TargetCatalog candidate;
    std::size_t currentIndex = 0;
    const std::size_t restoredSize = catalog.size() + 1U;
    for (std::size_t index = 0; index < restoredSize; ++index) {
        TargetRecord selected{};
        if (index == merge.destinationIndex) {
            selected = merge.destinationBefore;
            selected.revision = merge.mergedRevision + 1U;
        } else if (index == merge.sourceIndex) {
            selected = merge.sourceBefore;
            selected.revision = merge.sourceBefore.revision + 1U;
        } else {
            const TargetRecord* current = catalog.get(currentIndex);
            if (current != nullptr && targetIdEqual(
                    current->id, merge.destinationBefore.id)) {
                current = catalog.get(++currentIndex);
            }
            if (current == nullptr) return TargetMergeStatus::CatalogConflict;
            selected = *current;
            ++currentIndex;
        }
        if (candidate.restore(selected) != TargetMutationStatus::Created) {
            return TargetMergeStatus::CatalogConflict;
        }
    }
    const TargetRecord* remaining = catalog.get(currentIndex);
    if (remaining != nullptr && targetIdEqual(
            remaining->id, merge.destinationBefore.id)) {
        ++currentIndex;
    }
    if (currentIndex != catalog.size()) {
        return TargetMergeStatus::CatalogConflict;
    }
    catalog = candidate;
    return TargetMergeStatus::Split;
}

bool recordStructurallyValid(const TargetMergeRecord& record) {
    if (!targetMergeIdValid(record.id) ||
        targetIdEqual(record.destinationBefore.id, record.sourceBefore.id) ||
        record.destinationBefore.revision == 0 ||
        record.sourceBefore.revision == 0 ||
        record.destinationBefore.revision >=
            std::numeric_limits<std::uint32_t>::max() - 1U ||
        record.sourceBefore.revision ==
            std::numeric_limits<std::uint32_t>::max() ||
        record.mergedRevision != record.destinationBefore.revision + 1U ||
        record.originalCatalogSize < 2 ||
        record.originalCatalogSize > TargetCatalog::kCapacity ||
        record.destinationIndex >= TargetCatalog::kCapacity ||
        record.sourceIndex >= TargetCatalog::kCapacity ||
        record.destinationIndex >= record.originalCatalogSize ||
        record.sourceIndex >= record.originalCatalogSize ||
        record.destinationBefore.identityCount +
                record.sourceBefore.identityCount >
            TargetRecord::kIdentityCapacity ||
        record.destinationBefore.evidenceCount +
                record.sourceBefore.evidenceCount >
            TargetRecord::kEvidenceCapacity ||
        record.destinationIndex == record.sourceIndex) {
        return false;
    }
    return validateTargetRecord(record.destinationBefore) ==
            TargetMutationStatus::Created &&
        validateTargetRecord(record.sourceBefore) ==
            TargetMutationStatus::Created &&
        validateTargetRecordCompatibility(record.destinationBefore,
                                          record.sourceBefore) ==
            TargetMutationStatus::Created;
}

}  // namespace

bool targetMergeIdValid(const TargetMergeId& id) {
    for (const std::uint8_t value : id.bytes) {
        if (value != 0) return true;
    }
    return false;
}

bool targetMergeIdEqual(const TargetMergeId& left,
                        const TargetMergeId& right) {
    return left.bytes == right.bytes;
}

const char* targetMergeStatusName(TargetMergeStatus status) {
    switch (status) {
        case TargetMergeStatus::Merged: return "merged";
        case TargetMergeStatus::Split: return "split";
        case TargetMergeStatus::Unchanged: return "unchanged";
        case TargetMergeStatus::InvalidArgument: return "invalid_argument";
        case TargetMergeStatus::NotFound: return "not_found";
        case TargetMergeStatus::TargetChanged: return "target_changed";
        case TargetMergeStatus::IdentityFull: return "identity_full";
        case TargetMergeStatus::EvidenceFull: return "evidence_full";
        case TargetMergeStatus::HistoryFull: return "history_full";
        case TargetMergeStatus::OperationIdConflict:
            return "operation_id_conflict";
        case TargetMergeStatus::AlreadySplit: return "already_split";
        case TargetMergeStatus::CatalogConflict: return "catalog_conflict";
    }
    return "invalid_argument";
}

void TargetMergeHistory::clear() {
    std::memset(static_cast<void*>(records_.data()), 0, sizeof(records_));
    size_ = 0;
    persistenceRestorePending_ = false;
}

const TargetMergeRecord* TargetMergeHistory::get(std::size_t index) const {
    return index < size_ ? &records_[index] : nullptr;
}

const TargetMergeRecord* TargetMergeHistory::find(
    const TargetMergeId& id) const {
    for (std::size_t index = 0; index < size_; ++index) {
        if (targetMergeIdEqual(records_[index].id, id)) {
            return &records_[index];
        }
    }
    return nullptr;
}

TargetMergeRecord* TargetMergeHistory::findMutable(
    const TargetMergeId& id) {
    return const_cast<TargetMergeRecord*>(
        static_cast<const TargetMergeHistory*>(this)->find(id));
}

TargetMergeStatus TargetMergeHistory::merge(
    TargetCatalog& catalog, const TargetMergeId& operationId,
    const TargetId& destinationId, const TargetId& sourceId,
    std::uint32_t expectedDestinationRevision,
    std::uint32_t expectedSourceRevision) {
    if (!targetMergeIdValid(operationId) ||
        !targetIdValid(destinationId) || !targetIdValid(sourceId) ||
        targetIdEqual(destinationId, sourceId) ||
        expectedDestinationRevision == 0 || expectedSourceRevision == 0) {
        return TargetMergeStatus::InvalidArgument;
    }
    const TargetMergeRecord* existing = find(operationId);
    if (existing != nullptr) {
        if (!mergeKeyEqual(*existing, destinationId, sourceId,
                           expectedDestinationRevision,
                           expectedSourceRevision)) {
            return TargetMergeStatus::OperationIdConflict;
        }
        return existing->split ? TargetMergeStatus::AlreadySplit
                               : TargetMergeStatus::Unchanged;
    }
    if (size_ >= records_.size()) return TargetMergeStatus::HistoryFull;

    const TargetRecord* destination = catalog.find(destinationId);
    const TargetRecord* source = catalog.find(sourceId);
    if (destination == nullptr || source == nullptr) {
        return TargetMergeStatus::NotFound;
    }
    if (destination->revision != expectedDestinationRevision ||
        source->revision != expectedSourceRevision ||
        destination->revision >=
            std::numeric_limits<std::uint32_t>::max() - 1U ||
        source->revision == std::numeric_limits<std::uint32_t>::max()) {
        return TargetMergeStatus::TargetChanged;
    }
    if (destination->identityCount + source->identityCount >
        destination->identities.size()) {
        return TargetMergeStatus::IdentityFull;
    }
    if (destination->evidenceCount + source->evidenceCount >
        destination->evidence.size()) {
        return TargetMergeStatus::EvidenceFull;
    }

    TargetRecord merged = *destination;
    for (std::size_t index = 0; index < source->identityCount; ++index) {
        for (std::size_t prior = 0; prior < merged.identityCount; ++prior) {
            if (targetIdentityEqual(merged.identities[prior],
                                    source->identities[index])) {
                return TargetMergeStatus::CatalogConflict;
            }
        }
        merged.identities[merged.identityCount++] = source->identities[index];
    }
    for (std::size_t index = 0; index < source->evidenceCount; ++index) {
        for (std::size_t prior = 0; prior < merged.evidenceCount; ++prior) {
            if (sameEvidenceKey(merged.evidence[prior],
                                source->evidence[index])) {
                return TargetMergeStatus::CatalogConflict;
            }
        }
        merged.evidence[merged.evidenceCount++] = source->evidence[index];
    }
    merged.revision = destination->revision + 1U;

    const std::size_t destinationIndex = catalogIndex(catalog, destinationId);
    const std::size_t sourceIndex = catalogIndex(catalog, sourceId);
    if (destinationIndex >= catalog.size() || sourceIndex >= catalog.size()) {
        return TargetMergeStatus::CatalogConflict;
    }
    const TargetMergeRecord history{
        operationId, *destination, *source,
        static_cast<std::uint8_t>(catalog.size()),
        static_cast<std::uint8_t>(destinationIndex),
        static_cast<std::uint8_t>(sourceIndex), merged.revision, false};
    const TargetMergeStatus rebuilt = rebuildMergedCatalog(
        catalog, destinationIndex, sourceIndex, merged);
    if (rebuilt != TargetMergeStatus::Merged) return rebuilt;
    records_[size_++] = history;
    return TargetMergeStatus::Merged;
}

TargetMergeStatus TargetMergeHistory::split(
    TargetCatalog& catalog, const TargetMergeId& operationId) {
    if (!targetMergeIdValid(operationId)) {
        return TargetMergeStatus::InvalidArgument;
    }
    TargetMergeRecord* merge = findMutable(operationId);
    if (merge == nullptr) return TargetMergeStatus::NotFound;
    if (merge->split) return TargetMergeStatus::Unchanged;
    const TargetRecord* destination =
        catalog.find(merge->destinationBefore.id);
    if (destination == nullptr ||
        catalog.find(merge->sourceBefore.id) != nullptr ||
        destination->revision != merge->mergedRevision) {
        return TargetMergeStatus::TargetChanged;
    }
    TargetRecord expectedMerged = merge->destinationBefore;
    for (std::size_t index = 0;
         index < merge->sourceBefore.identityCount; ++index) {
        expectedMerged.identities[expectedMerged.identityCount++] =
            merge->sourceBefore.identities[index];
    }
    for (std::size_t index = 0;
         index < merge->sourceBefore.evidenceCount; ++index) {
        expectedMerged.evidence[expectedMerged.evidenceCount++] =
            merge->sourceBefore.evidence[index];
    }
    expectedMerged.revision = merge->mergedRevision;
    if (!targetRecordGraphEqual(*destination, expectedMerged)) {
        return TargetMergeStatus::TargetChanged;
    }
    const TargetMergeStatus rebuilt = rebuildSplitCatalog(catalog, *merge);
    if (rebuilt != TargetMergeStatus::Split) return rebuilt;
    merge->split = true;
    return TargetMergeStatus::Split;
}

TargetMergeStatus TargetMergeHistory::restore(
    const TargetMergeRecord& record) {
    if (persistenceRestorePending_) {
        return TargetMergeStatus::InvalidArgument;
    }
    if (!recordStructurallyValid(record)) {
        return TargetMergeStatus::InvalidArgument;
    }
    const TargetMergeRecord* existing = find(record.id);
    if (existing != nullptr) {
        return TargetMergeStatus::OperationIdConflict;
    }
    if (size_ >= records_.size()) return TargetMergeStatus::HistoryFull;
    records_[size_++] = record;
    return TargetMergeStatus::Merged;
}

TargetMergeRecord* TargetMergeHistory::beginPersistenceRestore() {
    if (persistenceRestorePending_ || size_ >= records_.size()) {
        return nullptr;
    }
    std::memset(static_cast<void*>(&records_[size_]), 0,
                sizeof(records_[size_]));
    persistenceRestorePending_ = true;
    return &records_[size_];
}

TargetMergeStatus TargetMergeHistory::commitPersistenceRestore() {
    if (!persistenceRestorePending_) {
        return TargetMergeStatus::InvalidArgument;
    }
    TargetMergeRecord& record = records_[size_];
    if (!recordStructurallyValid(record)) {
        cancelPersistenceRestore();
        return TargetMergeStatus::InvalidArgument;
    }
    if (find(record.id) != nullptr) {
        cancelPersistenceRestore();
        return TargetMergeStatus::OperationIdConflict;
    }
    ++size_;
    persistenceRestorePending_ = false;
    return TargetMergeStatus::Merged;
}

void TargetMergeHistory::cancelPersistenceRestore() {
    if (!persistenceRestorePending_) return;
    std::memset(static_cast<void*>(&records_[size_]), 0,
                sizeof(records_[size_]));
    persistenceRestorePending_ = false;
}

}  // namespace leshy1::domain::targets
