#pragma once

#include <cstddef>
#include <cstdint>

#include "apps/library/LibraryController.h"
#include "storage/SessionStore.h"

namespace leshy1::apps::library {

enum class SessionCatalogStatus : std::uint8_t {
    Admitted,
    Empty,
    StoreRejected,
    AdmissionRejected,
};

const char* sessionCatalogStatusName(SessionCatalogStatus status);

struct SessionCatalogResult final {
    SessionCatalogStatus status = SessionCatalogStatus::StoreRejected;
    storage::SessionStoreStatus storeStatus =
        storage::SessionStoreStatus::NoGeneration;
    std::uint32_t generation = 0;
    std::size_t observations = 0;
    SessionIntegrity integrity = SessionIntegrity::Valid;

    bool admitted() const { return status == SessionCatalogStatus::Admitted; }
};

// Read-only bridge from one validated SessionStore root into the bounded Library.
// The caller owns both the recovered Session and the Library, so catalog rebuilds
// require no heap and can be repeated after boot/remount without hidden writes.
class SessionCatalog final {
public:
    SessionCatalogResult recoverLatest(
        storage::SessionStoreIo& store,
        storage::SessionStoreWorkspace& workspace,
        services::survey::SurveySession& recoveredSession,
        LibraryController& library, bool persistent, bool simulated) const;

    SessionCatalogResult admitRecovered(
        const services::survey::SurveySession& recoveredSession,
        const storage::SessionStoreRecoveryResult& recovery,
        LibraryController& library, bool persistent, bool simulated) const;
};

}  // namespace leshy1::apps::library
