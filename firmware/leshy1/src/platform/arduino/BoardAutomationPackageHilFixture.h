#pragma once

#include <cstddef>
#include <cstdint>

#include "platform/arduino/ArduinoFsSessionStoreIo.h"
#include "storage/StorageGuard.h"

namespace leshy1::platform::arduino {

constexpr const char* kAutomationMalformedFixtureName = "malformed.lhau";
constexpr const char* kAutomationUnsignedFixtureName = "unsigned.lhau";
constexpr std::size_t kAutomationMalformedFixtureBytes = 12U;
constexpr std::size_t kAutomationUnsignedFixtureBytes = 147U;
constexpr std::uint64_t kAutomationHilFixtureRequiredBytes =
    kAutomationMalformedFixtureBytes + kAutomationUnsignedFixtureBytes;

struct BoardAutomationPackageHilFixtureReport final {
    bool prepared = false;
    bool malformedWritten = false;
    bool unsignedWritten = false;
    bool fileBarriersComplete = false;
    bool directoryBarrierComplete = false;
    bool exactEntries = false;
    bool cleanupComplete = false;
    std::uint64_t bytesWritten = 0U;
    std::uint32_t writeCalls = 0U;
    std::uint32_t fileSyncs = 0U;
    std::uint32_t directorySyncs = 0U;
    std::uint16_t filesRemoved = 0U;
    const char* lastFailure = "not_started";
    unsigned lastFresult = 0U;
};

// Dedicated mutation adapter for the physical Automation Inspector HIL gate.
// It can create and remove only the two fixed fixture files in one exact
// StorageGuard-authorized /leshy-hil/<run-id> directory.
class BoardAutomationPackageHilFixture final {
public:
    BoardAutomationPackageHilFixture(
        std::uint8_t driveNumber, ArduinoFsSessionStoreWorkspace& workspace)
        : driveNumber_(driveNumber), workspace_(workspace) {}

    bool create(
        const storage::WritePermit& permit,
        BoardAutomationPackageHilFixtureReport* report);
    bool remove(
        const storage::ScratchCleanupPermit& permit,
        BoardAutomationPackageHilFixtureReport* report);

private:
    bool scanExactEntries(const char* scratchPath, bool* exact,
                          std::uint16_t* count, const char** failure,
                          unsigned* fresult);
    bool formatVolumePath(const char* path, char* output,
                          std::size_t capacity) const;

    std::uint8_t driveNumber_ = 0xffU;
    ArduinoFsSessionStoreWorkspace& workspace_;
};

}  // namespace leshy1::platform::arduino
