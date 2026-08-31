#include "SessionCatalog.h"

namespace leshy1::apps::library {
namespace {

bool indicatesFallback(storage::CandidateStatus status) {
    return status == storage::CandidateStatus::ManifestMismatch ||
           status == storage::CandidateStatus::InvalidPayload;
}

SessionIntegrity integrityOf(
    const storage::SessionStoreRecoveryResult& recovery) {
    const storage::CandidateStatus rejected =
        recovery.choice == storage::RecoveryChoice::A ? recovery.bStatus
                                                      : recovery.aStatus;
    return indicatesFallback(rejected) ? SessionIntegrity::RecoveredFallback
                                       : SessionIntegrity::Valid;
}

}  // namespace

const char* sessionCatalogStatusName(SessionCatalogStatus status) {
    switch (status) {
        case SessionCatalogStatus::Admitted: return "admitted";
        case SessionCatalogStatus::Empty: return "empty";
        case SessionCatalogStatus::StoreRejected: return "store_rejected";
        case SessionCatalogStatus::AdmissionRejected: return "admission_rejected";
    }
    return "store_rejected";
}

SessionCatalogResult SessionCatalog::recoverLatest(
    storage::SessionStoreIo& store, storage::SessionStoreWorkspace& workspace,
    services::survey::SurveySession& recoveredSession,
    LibraryController& library, bool persistent, bool simulated) const {
    services::survey::SurveySession& staged = workspace.validationSession;
    const storage::SessionStoreRecoveryResult recovery =
        storage::recoverSession(store, workspace, &staged);
    if (recovery.status == storage::SessionStoreStatus::Empty) {
        return {SessionCatalogStatus::Empty, recovery.status, 0, 0,
                SessionIntegrity::Valid};
    }
    if (!recovery.valid()) {
        return {SessionCatalogStatus::StoreRejected, recovery.status,
                recovery.generation, recovery.observations,
                SessionIntegrity::Valid};
    }
    LibraryController replacement;
    const SessionCatalogResult validated = admitRecovered(
        staged, recovery, replacement, persistent, simulated);
    if (!validated.admitted()) return validated;
    if (!replacement.replaceWithOwnedCopy(
            staged, recoveredSession, recovery.generation,
            validated.integrity, persistent, simulated)) {
        return {SessionCatalogStatus::AdmissionRejected, recovery.status,
                recovery.generation, recovery.observations,
                validated.integrity};
    }
    if (!replacement.copyScreenshotEntriesFrom(library)) {
        return {SessionCatalogStatus::AdmissionRejected, recovery.status,
                recovery.generation, recovery.observations,
                validated.integrity};
    }
    library = replacement;
    return validated;
}

SessionCatalogResult SessionCatalog::admitRecovered(
    const services::survey::SurveySession& recoveredSession,
    const storage::SessionStoreRecoveryResult& recovery,
    LibraryController& library, bool persistent, bool simulated) const {
    SessionCatalogResult result;
    result.storeStatus = recovery.status;
    result.generation = recovery.generation;
    result.observations = recovery.observations;
    result.integrity = integrityOf(recovery);
    if (!recovery.valid() || recovery.observations != recoveredSession.size() ||
        recoveredSession.state() != services::survey::SessionState::Stopped) {
        result.status = SessionCatalogStatus::StoreRejected;
        return result;
    }
    if (!library.add(recoveredSession, recovery.generation, result.integrity,
                     persistent, simulated)) {
        result.status = SessionCatalogStatus::AdmissionRejected;
        return result;
    }
    result.status = SessionCatalogStatus::Admitted;
    return result;
}

}  // namespace leshy1::apps::library
