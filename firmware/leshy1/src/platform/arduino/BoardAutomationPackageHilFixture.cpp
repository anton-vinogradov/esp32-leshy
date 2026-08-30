#include "BoardAutomationPackageHilFixture.h"

#include <array>
#include <cstdio>
#include <cstring>

namespace leshy1::platform::arduino {
namespace {

constexpr std::array<std::uint8_t, kAutomationMalformedFixtureBytes>
    kMalformedPackage = {'N', 'O', 'T', '-', 'A', '-', 'P', 'A', 'C', 'K',
                         'A', 'G'};

constexpr std::array<std::uint8_t, kAutomationUnsignedFixtureBytes>
unsignedPackage() {
    std::array<std::uint8_t, kAutomationUnsignedFixtureBytes> bytes{};
    bytes[0] = 'L';
    bytes[1] = 'H';
    bytes[2] = 'A';
    bytes[3] = 'U';
    bytes[4] = 1U;  // wire version
    bytes[5] = 1U;  // ActionScript
    bytes[6] = 1U;  // ECDSA P-256/SHA-256
    bytes[7] = 1U;  // Device target
    bytes[8] = static_cast<std::uint8_t>(kAutomationUnsignedFixtureBytes);
    bytes[9] = 0U;
    constexpr std::uint16_t kSignedBytes =
        kAutomationUnsignedFixtureBytes - 64U;
    bytes[10] = static_cast<std::uint8_t>(kSignedBytes);
    bytes[11] = 0U;
    bytes[12] = 1U;  // script version
    bytes[14] = 1U;  // minimum Action API
    bytes[16] = 1U;  // InvokeAction permission
    bytes[20] = 0xd0U;  // runtime ceiling 2000 ms
    bytes[21] = 0x07U;
    bytes[24] = 8U;  // event ceiling
    bytes[26] = 128U;  // output ceiling
    bytes[28] = 1U;  // one step
    for (std::size_t index = 0U; index < 16U; ++index) {
        bytes[32U + index] = static_cast<std::uint8_t>(index + 1U);
    }
    for (std::size_t index = 0U; index < 8U; ++index) {
        bytes[48U + index] = static_cast<std::uint8_t>(0xa0U + index);
    }
    constexpr std::size_t kStep = 64U;
    constexpr char kAction[] = "device.info";
    bytes[kStep] = 2U;  // InvokeAction
    bytes[kStep + 2U] = 19U;  // 8-byte record + 11-byte action id
    bytes[kStep + 4U] = 0xf4U;  // 500 ms
    bytes[kStep + 5U] = 0x01U;
    for (std::size_t index = 0U; index < sizeof(kAction) - 1U; ++index) {
        bytes[kStep + 8U + index] =
            static_cast<std::uint8_t>(kAction[index]);
    }
    // The trailing 64-byte signature remains all-zero by construction.
    return bytes;
}

constexpr auto kUnsignedPackage = unsignedPackage();

bool fixtureName(const char* name) {
    return name != nullptr &&
        (std::strcmp(name, kAutomationMalformedFixtureName) == 0 ||
         std::strcmp(name, kAutomationUnsignedFixtureName) == 0);
}

}  // namespace

bool BoardAutomationPackageHilFixture::formatVolumePath(
    const char* path, char* output, std::size_t capacity) const {
    if (path == nullptr || path[0] != '/' || output == nullptr ||
        capacity == 0U || driveNumber_ >= FF_VOLUMES || driveNumber_ > 9U) {
        return false;
    }
    const int written = std::snprintf(
        output, capacity, "%u:%s", static_cast<unsigned>(driveNumber_), path);
    return written > 0 && static_cast<std::size_t>(written) < capacity;
}

bool BoardAutomationPackageHilFixture::scanExactEntries(
    const char* scratchPath, bool* exact, std::uint16_t* count,
    const char** failure, unsigned* fresult) {
    if (exact == nullptr || count == nullptr || failure == nullptr ||
        fresult == nullptr) {
        return false;
    }
    *exact = false;
    *count = 0U;
    char root[128] = {};
    if (!formatVolumePath(scratchPath, root, sizeof(root))) {
        *failure = "scan_path";
        *fresult = static_cast<unsigned>(FR_INVALID_NAME);
        return false;
    }
    FF_DIR directory{};
    FRESULT result = f_opendir(&directory, root);
    if (result != FR_OK) {
        *failure = "scan_open";
        *fresult = static_cast<unsigned>(result);
        return false;
    }
    bool malformed = false;
    bool unsignedPackageFound = false;
    bool safe = true;
    for (;;) {
        workspace_.information = {};
        result = f_readdir(&directory, &workspace_.information);
        if (result != FR_OK) {
            safe = false;
            *failure = "scan_read";
            *fresult = static_cast<unsigned>(result);
            break;
        }
        const char* name = workspace_.information.fname;
        if (name[0] == '\0') break;
        if ((workspace_.information.fattrib & AM_DIR) != 0U ||
            !fixtureName(name) || *count >= 2U) {
            safe = false;
            *failure = "scan_unknown_entry";
            *fresult = static_cast<unsigned>(FR_DENIED);
            break;
        }
        malformed = malformed ||
            std::strcmp(name, kAutomationMalformedFixtureName) == 0;
        unsignedPackageFound = unsignedPackageFound ||
            std::strcmp(name, kAutomationUnsignedFixtureName) == 0;
        ++*count;
    }
    const FRESULT closed = f_closedir(&directory);
    if (safe && closed != FR_OK) {
        safe = false;
        *failure = "scan_close";
        *fresult = static_cast<unsigned>(closed);
    }
    *exact = safe && *count == 2U && malformed && unsignedPackageFound;
    return safe;
}

bool BoardAutomationPackageHilFixture::create(
    const storage::WritePermit& permit,
    BoardAutomationPackageHilFixtureReport* report) {
    if (report == nullptr) return false;
    *report = {};
    ArduinoFsSessionStoreIo io(driveNumber_, workspace_);
    report->prepared = io.prepare(permit);
    if (report->prepared) {
        report->malformedWritten = io.writeFile(
            kAutomationMalformedFixtureName, kMalformedPackage.data(),
            kMalformedPackage.size());
        if (report->malformedWritten) {
            report->malformedWritten =
                io.syncFile(kAutomationMalformedFixtureName);
        }
        report->unsignedWritten = report->malformedWritten && io.writeFile(
            kAutomationUnsignedFixtureName, kUnsignedPackage.data(),
            kUnsignedPackage.size());
        if (report->unsignedWritten) {
            report->unsignedWritten =
                io.syncFile(kAutomationUnsignedFixtureName);
        }
        report->fileBarriersComplete =
            report->malformedWritten && report->unsignedWritten &&
            io.fileSyncs() == 2U;
        report->directoryBarrierComplete =
            report->fileBarriersComplete && io.syncDirectory();
    }
    report->bytesWritten = io.bytesWritten();
    report->writeCalls = io.writeCalls();
    report->fileSyncs = io.fileSyncs();
    report->directorySyncs = io.directorySyncs();
    report->lastFailure = io.lastFailure();
    report->lastFresult = io.lastFresult();
    io.end();
    std::uint16_t count = 0U;
    const char* scanFailure = "none";
    unsigned scanFresult = 0U;
    const bool scanned = report->directoryBarrierComplete && scanExactEntries(
        permit.scratchPath, &report->exactEntries, &count, &scanFailure,
        &scanFresult);
    if (!scanned) {
        report->lastFailure = scanFailure;
        report->lastFresult = scanFresult;
    }
    return report->prepared && report->malformedWritten &&
        report->unsignedWritten && report->fileBarriersComplete &&
        report->directoryBarrierComplete && report->exactEntries &&
        report->bytesWritten == kAutomationHilFixtureRequiredBytes &&
        report->writeCalls == 2U && report->fileSyncs == 2U &&
        report->directorySyncs == 1U;
}

bool BoardAutomationPackageHilFixture::remove(
    const storage::ScratchCleanupPermit& permit,
    BoardAutomationPackageHilFixtureReport* report) {
    if (report == nullptr) return false;
    *report = {};
    bool exact = false;
    std::uint16_t count = 0U;
    const char* failure = "none";
    unsigned fresult = 0U;
    if (!permit.allowed() || !scanExactEntries(
            permit.scratchPath, &exact, &count, &failure, &fresult)) {
        report->lastFailure = permit.allowed() ? failure : "cleanup_permit";
        report->lastFresult = permit.allowed()
            ? fresult : static_cast<unsigned>(FR_DENIED);
        return false;
    }
    // Cleanup accepts a partial set of the two known files after an
    // interrupted create, but never an unknown file or nested directory.
    report->exactEntries = exact;
    char root[128] = {};
    if (!formatVolumePath(permit.scratchPath, root, sizeof(root))) {
        report->lastFailure = "cleanup_path";
        report->lastFresult = static_cast<unsigned>(FR_INVALID_NAME);
        return false;
    }
    constexpr const char* names[] = {
        kAutomationMalformedFixtureName, kAutomationUnsignedFixtureName};
    for (const char* name : names) {
        char child[160] = {};
        const int written = std::snprintf(child, sizeof(child), "%s/%s",
                                          root, name);
        if (written <= 0 ||
            static_cast<std::size_t>(written) >= sizeof(child)) {
            report->lastFailure = "cleanup_child_path";
            report->lastFresult = static_cast<unsigned>(FR_INVALID_NAME);
            return false;
        }
        workspace_.information = {};
        const FRESULT present = f_stat(child, &workspace_.information);
        if (present == FR_NO_FILE || present == FR_NO_PATH) continue;
        if (present != FR_OK ||
            (workspace_.information.fattrib & AM_DIR) != 0U) {
            report->lastFailure = "cleanup_entry";
            report->lastFresult = static_cast<unsigned>(present);
            return false;
        }
        const FRESULT removed = f_unlink(child);
        if (removed != FR_OK) {
            report->lastFailure = "cleanup_file";
            report->lastFresult = static_cast<unsigned>(removed);
            return false;
        }
        ++report->filesRemoved;
    }
    const FRESULT removedRoot = f_unlink(root);
    if (removedRoot != FR_OK) {
        report->lastFailure = "cleanup_directory";
        report->lastFresult = static_cast<unsigned>(removedRoot);
        return false;
    }
    workspace_.information = {};
    const FRESULT verified = f_stat(root, &workspace_.information);
    report->cleanupComplete =
        (verified == FR_NO_FILE || verified == FR_NO_PATH) &&
        report->filesRemoved == count;
    report->lastFailure = report->cleanupComplete ? "none" : "cleanup_verify";
    report->lastFresult = static_cast<unsigned>(verified);
    return report->cleanupComplete;
}

}  // namespace leshy1::platform::arduino
