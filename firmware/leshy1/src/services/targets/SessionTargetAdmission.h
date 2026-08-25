#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/targets/TargetCatalog.h"
#include "services/survey/SurveySession.h"
#include "services/targets/ObservationTargetAdapter.h"

namespace leshy1::services::targets {

enum class SessionTargetAdmissionStatus : std::uint8_t {
    Valid,
    InvalidArgument,
    SessionUnavailable,
    ObservationRejected,
    TargetRejected,
};

const char* sessionTargetAdmissionStatusName(
    SessionTargetAdmissionStatus status);

struct SessionTargetAdmissionResult final {
    SessionTargetAdmissionStatus status =
        SessionTargetAdmissionStatus::InvalidArgument;
    ObservationTargetStatus observationStatus =
        ObservationTargetStatus::InvalidArgument;
    domain::targets::TargetMutationStatus targetStatus =
        domain::targets::TargetMutationStatus::InvalidArgument;
    domain::targets::SourceId sourceId{};
    std::size_t observations = 0;
    std::size_t identities = 0;
    std::size_t created = 0;
    std::size_t evidenceAttached = 0;
    std::size_t unchanged = 0;

    bool valid() const {
        return status == SessionTargetAdmissionStatus::Valid;
    }
};

// Optional product-view filter. It bounds a derived on-device projection while
// the immutable source Session remains complete and every admitted row still
// points to its exact source Observation.
struct SessionTargetIdentityFilter final {
    std::array<domain::targets::TargetIdentity,
               domain::targets::TargetCatalog::kCapacity> identities{};
    std::size_t size = 0;
};

// Derives the stable local identity of one immutable stopped Session from its
// own metadata. Generation remains a separate exact coordinate in every
// TargetEvidenceRef.
bool sourceIdForSession(const survey::SurveySession& session,
                        domain::targets::SourceId* output);

// Derives a stable local Target ID from the first exact source evidence, not
// from a radio address. Later identity changes, merge and split therefore do
// not rewrite the Target ID.
bool targetIdForEvidence(const domain::targets::TargetEvidenceRef& evidence,
                         domain::targets::TargetId* output);

// Imports only the latest retained Observation for each exact identity in one
// Session. The caller provides a scratch catalog so the admission is
// all-or-nothing without heap allocation or partial mutation on a bound/error.
SessionTargetAdmissionResult admitSessionTargets(
    const survey::SurveySession& session, std::uint32_t generation,
    domain::targets::TargetCatalog& catalog,
    domain::targets::TargetCatalog& scratch,
    const SessionTargetIdentityFilter* filter = nullptr);

}  // namespace leshy1::services::targets
