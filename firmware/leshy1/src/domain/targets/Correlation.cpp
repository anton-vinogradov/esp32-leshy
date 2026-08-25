#include "Correlation.h"

namespace leshy1::domain::targets {
namespace {

constexpr std::array<std::uint32_t, 4> kHashSeeds{{
    0x811c9dc5U, 0x9e3779b9U, 0x85ebca6bU, 0xc2b2ae35U,
}};

void mixByte(std::array<std::uint32_t, 4>* lanes, std::uint8_t value) {
    for (std::size_t index = 0; index < lanes->size(); ++index) {
        (*lanes)[index] ^= static_cast<std::uint32_t>(
            value + static_cast<std::uint8_t>(index * 0x3dU));
        (*lanes)[index] *= 0x01000193U;
        (*lanes)[index] ^= (*lanes)[index] >> (13U + index);
    }
}

template <std::size_t Capacity>
void mixBytes(std::array<std::uint32_t, 4>* lanes,
              const std::array<std::uint8_t, Capacity>& bytes) {
    for (const std::uint8_t value : bytes) mixByte(lanes, value);
}

void mix32(std::array<std::uint32_t, 4>* lanes, std::uint32_t value) {
    for (int shift = 24; shift >= 0; shift -= 8) {
        mixByte(lanes, static_cast<std::uint8_t>(value >> shift));
    }
}

void mix64(std::array<std::uint32_t, 4>* lanes, std::uint64_t value) {
    for (int shift = 56; shift >= 0; shift -= 8) {
        mixByte(lanes, static_cast<std::uint8_t>(value >> shift));
    }
}

}  // namespace

bool correlationProposalIdValid(const CorrelationProposalId& id) {
    for (const std::uint8_t value : id.bytes) {
        if (value != 0) return true;
    }
    return false;
}

bool correlationProposalIdEqual(const CorrelationProposalId& left,
                                const CorrelationProposalId& right) {
    return left.bytes == right.bytes;
}

CorrelationProposalId makeCorrelationProposalId(
    const TargetId& targetId, const TargetIdentity& candidateIdentity,
    const TargetEvidenceRef& candidateEvidence) {
    std::array<std::uint32_t, 4> lanes = kHashSeeds;
    mixBytes(&lanes, targetId.bytes);
    mixByte(&lanes, static_cast<std::uint8_t>(candidateIdentity.kind));
    mixByte(&lanes, candidateIdentity.length);
    mixBytes(&lanes, candidateIdentity.value);
    mixByte(&lanes, candidateIdentity.discriminator);
    mixBytes(&lanes, candidateEvidence.sourceId.bytes);
    mix32(&lanes, candidateEvidence.sourceGeneration);
    mix64(&lanes, candidateEvidence.observationSequence);
    mix64(&lanes, candidateEvidence.observedMonotonicUs);

    CorrelationProposalId result{};
    for (std::size_t lane = 0; lane < lanes.size(); ++lane) {
        const std::uint32_t value = lanes[lane];
        for (std::size_t byte = 0; byte < 4; ++byte) {
            result.bytes[lane * 4U + byte] = static_cast<std::uint8_t>(
                value >> ((3U - byte) * 8U));
        }
    }
    return result;
}

bool correlationProposalKeyEqual(const CorrelationProposal& left,
                                 const CorrelationProposal& right) {
    return targetIdEqual(left.targetId, right.targetId) &&
        targetIdentityEqual(left.candidateIdentity,
                            right.candidateIdentity) &&
        targetEvidenceEqual(left.candidateEvidence,
                            right.candidateEvidence);
}

std::uint16_t correlationFeatureMaximumPoints(CorrelationFeatureKind kind) {
    switch (kind) {
        case CorrelationFeatureKind::AssignedVendorMatch: return 180;
        case CorrelationFeatureKind::AdvertisedNameMatch: return 260;
        case CorrelationFeatureKind::CoOccurrencePattern: return 200;
        case CorrelationFeatureKind::ChannelPatternMatch: return 140;
        case CorrelationFeatureKind::SignalTrendMatch: return 220;
    }
    return 0;
}

}  // namespace leshy1::domain::targets
