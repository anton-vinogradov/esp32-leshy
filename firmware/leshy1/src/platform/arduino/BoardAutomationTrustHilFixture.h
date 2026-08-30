#pragma once

#include <cstddef>
#include <cstdint>

#include "apps/automation/AutomationTrustBundle.h"
#include "platform/arduino/ArduinoFsSessionStoreIo.h"
#include "storage/StorageGuard.h"

namespace leshy1::platform::arduino {

constexpr std::uint64_t kAutomationTrustHilFixtureRequiredBytes =
    apps::automation::kAutomationTrustBundleBytes;

struct BoardAutomationTrustHilFixtureReport final {
    bool prepared = false;
    bool bundleWritten = false;
    bool fileBarrierComplete = false;
    bool directoryBarrierComplete = false;
    bool exactEntries = false;
    bool bundleRead = false;
    bool bundleMatched = false;
    bool cleanupComplete = false;
    std::uint64_t bytesWritten = 0U;
    std::uint32_t writeCalls = 0U;
    std::uint32_t fileSyncs = 0U;
    std::uint32_t directorySyncs = 0U;
    std::uint16_t filesRemoved = 0U;
    const char* lastFailure = "not_started";
    unsigned lastFresult = 0U;
};

// Writes only one public trust bundle into an exact StorageGuard-authorized
// /leshy-hil/<run-id> directory. Product storage paths are never mutated.
class BoardAutomationTrustHilFixture final {
public:
    BoardAutomationTrustHilFixture(
        std::uint8_t driveNumber, ArduinoFsSessionStoreWorkspace& workspace)
        : driveNumber_(driveNumber), workspace_(workspace) {}

    bool create(
        const storage::WritePermit& permit,
        const apps::automation::AutomationTrustBundle& bundle,
        BoardAutomationTrustHilFixtureReport* report);
    bool inspect(
        const char* scratchPath,
        apps::automation::AutomationTrustBundle* bundle,
        BoardAutomationTrustHilFixtureReport* report);
    bool remove(
        const storage::ScratchCleanupPermit& permit,
        const apps::automation::AutomationTrustBundle& expected,
        BoardAutomationTrustHilFixtureReport* report);

private:
    bool scanExactEntry(const char* scratchPath, bool* exact,
                        std::uint16_t* count, const char** failure,
                        unsigned* fresult);
    bool formatVolumePath(const char* path, char* output,
                          std::size_t capacity) const;

    std::uint8_t driveNumber_ = 0xffU;
    ArduinoFsSessionStoreWorkspace& workspace_;
};

}  // namespace leshy1::platform::arduino
