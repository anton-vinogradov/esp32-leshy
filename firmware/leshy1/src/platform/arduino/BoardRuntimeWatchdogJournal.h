#pragma once

#include <cstddef>
#include <cstdint>

#include "kernel/safety/RuntimeWatchdogJournal.h"

namespace leshy1::platform::arduino {

enum class RuntimeWatchdogJournalLoadStatus : std::uint8_t {
    Missing,
    Valid,
    Invalid,
    IoError,
};

enum class RuntimeWatchdogJournalSdWriteStatus : std::uint8_t {
    Written,
    AlreadyPresent,
    InvalidInput,
    WorkspaceUnavailable,
    DirectoryFailed,
    OpenFailed,
    WriteFailed,
    SyncFailed,
    VerifyFailed,
    RenameFailed,
};

const char* runtimeWatchdogJournalLoadStatusName(
    RuntimeWatchdogJournalLoadStatus status);
const char* runtimeWatchdogJournalSdWriteStatusName(
    RuntimeWatchdogJournalSdWriteStatus status);

// Dedicated system journal store. It is intentionally separate from user UI
// preferences and the encrypted product session catalog.
class BoardRuntimeWatchdogJournal final {
public:
    RuntimeWatchdogJournalLoadStatus load(
        kernel::safety::RuntimeWatchdogJournalRecord* output) const;
    bool save(const kernel::safety::RuntimeWatchdogJournalRecord& record) const;
    std::uint32_t loadSdMirroredSequence() const;
    bool saveSdMirroredSequence(std::uint32_t sequence) const;

    // The caller owns an exact-CID-verified writable mount and the shared
    // Storage+RadioSPI lease. This writer has one hard-coded, append-only path
    // and cannot mutate session data.
    RuntimeWatchdogJournalSdWriteStatus writeSd(
        std::uint8_t driveNumber, std::uint32_t sequence,
        const char* json, std::size_t size) const;
};

}  // namespace leshy1::platform::arduino
