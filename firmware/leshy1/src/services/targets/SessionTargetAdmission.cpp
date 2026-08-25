#include "SessionTargetAdmission.h"

#include <cstring>

namespace leshy1::services::targets {
namespace {

constexpr std::uint64_t kFnvOffset = 14695981039346656037ULL;
constexpr std::uint64_t kFnvPrime = 1099511628211ULL;

void hashByte(std::uint64_t* hash, std::uint8_t value) {
    *hash ^= value;
    *hash *= kFnvPrime;
}

void hashBytes(std::uint64_t* hash, const std::uint8_t* bytes,
               std::size_t size) {
    for (std::size_t index = 0; index < size; ++index) {
        hashByte(hash, bytes[index]);
    }
}

void hashU32(std::uint64_t* hash, std::uint32_t value) {
    for (std::uint8_t shift = 0; shift < 32; shift += 8) {
        hashByte(hash, static_cast<std::uint8_t>(value >> shift));
    }
}

void hashU64(std::uint64_t* hash, std::uint64_t value) {
    for (std::uint8_t shift = 0; shift < 64; shift += 8) {
        hashByte(hash, static_cast<std::uint8_t>(value >> shift));
    }
}

template <std::size_t Size>
void writeHashes(std::uint64_t first, std::uint64_t second,
                 std::array<std::uint8_t, Size>* output) {
    static_assert(Size == 16, "stable identifiers are 128 bit");
    for (std::size_t index = 0; index < 8; ++index) {
        (*output)[index] = static_cast<std::uint8_t>(first >> (index * 8));
        (*output)[index + 8] =
            static_cast<std::uint8_t>(second >> (index * 8));
    }
}

bool laterIdentityExists(const survey::SurveySession& session,
                         std::size_t after,
                         const domain::targets::SourceId& sourceId,
                         std::uint32_t generation,
                         const domain::targets::TargetIdentity& identity) {
    for (std::size_t index = after + 1; index < session.size(); ++index) {
        const auto* observation = session.get(index);
        if (observation == nullptr) return false;
        const ObservationTargetAdmission candidate = admitObservationToTarget(
            sourceId, generation, *observation);
        if (candidate.valid() &&
            domain::targets::targetIdentityEqual(candidate.identity,
                                                   identity)) {
            return true;
        }
    }
    return false;
}

bool identitySelected(const SessionTargetIdentityFilter* filter,
                      const domain::targets::TargetIdentity& identity) {
    if (filter == nullptr) return true;
    for (std::size_t index = 0; index < filter->size; ++index) {
        if (domain::targets::targetIdentityEqual(filter->identities[index],
                                                  identity)) {
            return true;
        }
    }
    return false;
}

}  // namespace

const char* sessionTargetAdmissionStatusName(
    SessionTargetAdmissionStatus status) {
    switch (status) {
        case SessionTargetAdmissionStatus::Valid: return "valid";
        case SessionTargetAdmissionStatus::InvalidArgument:
            return "invalid_argument";
        case SessionTargetAdmissionStatus::SessionUnavailable:
            return "session_unavailable";
        case SessionTargetAdmissionStatus::ObservationRejected:
            return "observation_rejected";
        case SessionTargetAdmissionStatus::TargetRejected:
            return "target_rejected";
    }
    return "invalid_argument";
}

bool sourceIdForSession(const survey::SurveySession& session,
                        domain::targets::SourceId* output) {
    if (output == nullptr || session.state() != survey::SessionState::Stopped ||
        session.id() == nullptr || session.id()[0] == '\0' ||
        session.startedUs() == 0 || session.stoppedUs() < session.startedUs()) {
        return false;
    }
    std::uint64_t first = kFnvOffset;
    std::uint64_t second = kFnvOffset;
    constexpr char kFirstDomain[] = "leshy.session.source.v1.a";
    constexpr char kSecondDomain[] = "leshy.session.source.v1.b";
    hashBytes(&first, reinterpret_cast<const std::uint8_t*>(kFirstDomain),
              sizeof(kFirstDomain) - 1);
    hashBytes(&second, reinterpret_cast<const std::uint8_t*>(kSecondDomain),
              sizeof(kSecondDomain) - 1);
    const std::size_t idLength = std::strlen(session.id());
    hashBytes(&first,
              reinterpret_cast<const std::uint8_t*>(session.id()), idLength);
    hashBytes(&second,
              reinterpret_cast<const std::uint8_t*>(session.id()), idLength);
    hashU64(&first, session.startedUs());
    hashU64(&first, session.stoppedUs());
    hashU64(&second, session.stoppedUs());
    hashU64(&second, session.startedUs());
    hashU64(&second, static_cast<std::uint64_t>(session.size()));
    writeHashes(first, second, &output->bytes);
    if (!domain::targets::sourceIdValid(*output)) {
        output->bytes.back() = 1;
    }
    return domain::targets::sourceIdValid(*output);
}

bool targetIdForEvidence(const domain::targets::TargetEvidenceRef& evidence,
                         domain::targets::TargetId* output) {
    if (output == nullptr || !domain::targets::targetEvidenceValid(evidence)) {
        return false;
    }
    std::uint64_t first = kFnvOffset;
    std::uint64_t second = kFnvOffset;
    constexpr char kFirstDomain[] = "leshy.target.id.v1.a";
    constexpr char kSecondDomain[] = "leshy.target.id.v1.b";
    hashBytes(&first, reinterpret_cast<const std::uint8_t*>(kFirstDomain),
              sizeof(kFirstDomain) - 1);
    hashBytes(&second, reinterpret_cast<const std::uint8_t*>(kSecondDomain),
              sizeof(kSecondDomain) - 1);
    hashBytes(&first, evidence.sourceId.bytes.data(),
              evidence.sourceId.bytes.size());
    hashBytes(&second, evidence.sourceId.bytes.data(),
              evidence.sourceId.bytes.size());
    hashU32(&first, evidence.sourceGeneration);
    hashU64(&first, evidence.observationSequence);
    hashU64(&second, evidence.observationSequence);
    hashU32(&second, evidence.sourceGeneration);
    writeHashes(first, second, &output->bytes);
    if (!domain::targets::targetIdValid(*output)) output->bytes.back() = 1;
    return domain::targets::targetIdValid(*output);
}

SessionTargetAdmissionResult admitSessionTargets(
    const survey::SurveySession& session, std::uint32_t generation,
    domain::targets::TargetCatalog& catalog,
    domain::targets::TargetCatalog& scratch,
    const SessionTargetIdentityFilter* filter) {
    SessionTargetAdmissionResult result{};
    if (&catalog == &scratch || generation == 0 ||
        (filter != nullptr &&
         filter->size > domain::targets::TargetCatalog::kCapacity)) {
        return result;
    }
    if (!sourceIdForSession(session, &result.sourceId)) {
        result.status = SessionTargetAdmissionStatus::SessionUnavailable;
        return result;
    }
    result.observations = session.size();

    // Validate every record before changing even the scratch candidate.
    for (std::size_t index = 0; index < session.size(); ++index) {
        const auto* observation = session.get(index);
        if (observation == nullptr) {
            result.status = SessionTargetAdmissionStatus::ObservationRejected;
            return result;
        }
        const ObservationTargetAdmission admitted = admitObservationToTarget(
            result.sourceId, generation, *observation);
        if (!admitted.valid()) {
            result.status = SessionTargetAdmissionStatus::ObservationRejected;
            result.observationStatus = admitted.status;
            return result;
        }
    }

    scratch = catalog;
    for (std::size_t index = 0; index < session.size(); ++index) {
        const auto* observation = session.get(index);
        const ObservationTargetAdmission admitted = admitObservationToTarget(
            result.sourceId, generation, *observation);
        if (laterIdentityExists(session, index, result.sourceId, generation,
                                admitted.identity)) {
            continue;
        }
        if (!identitySelected(filter, admitted.identity)) continue;
        ++result.identities;
        const domain::targets::TargetRecord* existing =
            scratch.findByIdentity(admitted.identity);
        domain::targets::TargetMutationStatus status{};
        if (existing == nullptr) {
            if (scratch.size() >=
                domain::targets::TargetCatalog::kCapacity) {
                ++result.capacitySkipped;
                result.targetStatus =
                    domain::targets::TargetMutationStatus::CatalogFull;
                continue;
            }
            domain::targets::TargetId id{};
            if (!targetIdForEvidence(admitted.evidence, &id)) {
                result.status = SessionTargetAdmissionStatus::TargetRejected;
                return result;
            }
            status = scratch.create(id, admitted.identity, admitted.evidence);
            if (status == domain::targets::TargetMutationStatus::Created) {
                ++result.created;
            }
        } else {
            status = scratch.attachEvidence(existing->id, admitted.identity,
                                            admitted.evidence);
            if (status == domain::targets::TargetMutationStatus::Applied) {
                ++result.evidenceAttached;
            } else if (status ==
                       domain::targets::TargetMutationStatus::Unchanged) {
                ++result.unchanged;
            }
        }
        if (status != domain::targets::TargetMutationStatus::Created &&
            status != domain::targets::TargetMutationStatus::Applied &&
            status != domain::targets::TargetMutationStatus::Unchanged) {
            result.status = SessionTargetAdmissionStatus::TargetRejected;
            result.targetStatus = status;
            return result;
        }
        if (result.capacitySkipped == 0) result.targetStatus = status;
    }
    catalog = scratch;
    result.status = SessionTargetAdmissionStatus::Valid;
    result.observationStatus = ObservationTargetStatus::Valid;
    return result;
}

}  // namespace leshy1::services::targets
