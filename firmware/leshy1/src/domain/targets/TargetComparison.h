#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"
#include "domain/targets/TargetCatalog.h"

namespace leshy1::domain::targets {

struct TargetComparisonSource final {
    SourceId id{};
    std::uint32_t generation = 0;
};

bool targetComparisonSourceValid(const TargetComparisonSource& source);
bool targetComparisonSourceEqual(const TargetComparisonSource& left,
                                 const TargetComparisonSource& right);

// Comparison reads immutable observations through exact retained references.
// Implementations must not substitute a newer record when the requested
// generation/sequence is unavailable.
class TargetComparisonEvidenceLookup {
public:
    virtual ~TargetComparisonEvidenceLookup() = default;
    virtual bool sourceAvailable(
        const TargetComparisonSource& source) const = 0;
    virtual bool loadExact(
        const TargetEvidenceRef& evidence,
        observations::Observation* output) const = 0;
};

enum class TargetComparisonClass : std::uint8_t {
    Added,
    Removed,
    Changed,
    Unchanged,
};

enum class TargetChangeKind : std::uint16_t {
    IdentitySet = 1U << 0U,
    Radio = 1U << 1U,
    Frequency = 1U << 2U,
    Channel = 1U << 3U,
    Signal = 1U << 4U,
    Label = 1U << 5U,
    WifiFacts = 1U << 6U,
    BleFacts = 1U << 7U,
};

using TargetChangeMask = std::uint16_t;

constexpr TargetChangeMask targetChangeMask(TargetChangeKind kind) {
    return static_cast<TargetChangeMask>(kind);
}

struct TargetComparisonEvidence final {
    TargetIdentity identity{};
    TargetEvidenceRef reference{};
};

struct TargetComparisonItem final {
    static constexpr std::size_t kEvidencePerSideCapacity =
        TargetRecord::kIdentityCapacity;

    TargetId targetId{};
    TargetComparisonClass classification = TargetComparisonClass::Unchanged;
    TargetChangeMask changes = 0;
    std::array<TargetComparisonEvidence, kEvidencePerSideCapacity>
        baselineEvidence{};
    std::array<TargetComparisonEvidence, kEvidencePerSideCapacity>
        currentEvidence{};
    std::uint8_t baselineEvidenceCount = 0;
    std::uint8_t currentEvidenceCount = 0;
};

enum class TargetComparisonStatus : std::uint8_t {
    Compared,
    InvalidArgument,
    SourceUnavailable,
    EvidenceUnavailable,
    EvidenceMismatch,
    ResultFull,
};

const char* targetComparisonStatusName(TargetComparisonStatus status);
const char* targetComparisonClassName(TargetComparisonClass classification);

struct TargetComparisonResult final {
    static constexpr std::size_t kCapacity = TargetCatalog::kCapacity;

    TargetComparisonStatus status = TargetComparisonStatus::InvalidArgument;
    TargetComparisonSource baseline{};
    TargetComparisonSource current{};
    std::array<TargetComparisonItem, kCapacity> items{};
    std::uint8_t size = 0;
    std::uint8_t added = 0;
    std::uint8_t removed = 0;
    std::uint8_t changed = 0;
    std::uint8_t unchanged = 0;

    bool compared() const { return status == TargetComparisonStatus::Compared; }
    const TargetComparisonItem* get(std::size_t index) const {
        return index < size ? &items[index] : nullptr;
    }
};

// RSSI commonly moves a few dB between adjacent passive scans. A delta becomes
// a user-visible Target change only at this explicit, shared threshold.
constexpr std::int16_t kMeaningfulTargetSignalDeltaDb = 6;

TargetComparisonResult compareTargetSessions(
    const TargetCatalog& catalog, const TargetComparisonSource& baseline,
    const TargetComparisonSource& current,
    const TargetComparisonEvidenceLookup& evidenceLookup);

}  // namespace leshy1::domain::targets
