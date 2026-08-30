#include "BoardAutomationTrustHilFixture.h"

#include <cstdio>
#include <cstring>

#include "platform/arduino/BoardAutomationTrustBundleReader.h"

namespace leshy1::platform::arduino {

bool BoardAutomationTrustHilFixture::formatVolumePath(
    const char* path, char* output, std::size_t capacity) const {
    if (path == nullptr || path[0] != '/' || output == nullptr ||
        capacity == 0U || driveNumber_ >= FF_VOLUMES || driveNumber_ > 9U) {
        return false;
    }
    const int written = std::snprintf(
        output, capacity, "%u:%s", static_cast<unsigned>(driveNumber_), path);
    return written > 0 && static_cast<std::size_t>(written) < capacity;
}

bool BoardAutomationTrustHilFixture::scanExactEntry(
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
    bool safe = true;
    bool bundleFound = false;
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
            std::strcmp(name, kAutomationTrustBundleName) != 0 ||
            *count >= 1U) {
            safe = false;
            *failure = "scan_unknown_entry";
            *fresult = static_cast<unsigned>(FR_DENIED);
            break;
        }
        bundleFound = true;
        ++*count;
    }
    const FRESULT closed = f_closedir(&directory);
    if (safe && closed != FR_OK) {
        safe = false;
        *failure = "scan_close";
        *fresult = static_cast<unsigned>(closed);
    }
    *exact = safe && bundleFound && *count == 1U;
    return safe;
}

bool BoardAutomationTrustHilFixture::inspect(
    const char* scratchPath, apps::automation::AutomationTrustBundle* bundle,
    BoardAutomationTrustHilFixtureReport* report) {
    if (bundle == nullptr || report == nullptr) return false;
    *report = {};
    bundle->fill(0U);
    std::uint16_t count = 0U;
    const char* failure = "none";
    unsigned fresult = 0U;
    const bool scanned = scanExactEntry(
        scratchPath, &report->exactEntries, &count, &failure, &fresult);
    if (!scanned || !report->exactEntries) {
        report->lastFailure = scanned ? "scan_not_exact" : failure;
        report->lastFresult = scanned ? static_cast<unsigned>(FR_DENIED)
                                      : fresult;
        return false;
    }
    char root[128] = {};
    char child[160] = {};
    if (!formatVolumePath(scratchPath, root, sizeof(root))) {
        report->lastFailure = "read_path";
        report->lastFresult = static_cast<unsigned>(FR_INVALID_NAME);
        return false;
    }
    const int written = std::snprintf(child, sizeof(child), "%s/%s", root,
                                      kAutomationTrustBundleName);
    if (written <= 0 || static_cast<std::size_t>(written) >= sizeof(child)) {
        report->lastFailure = "read_child_path";
        report->lastFresult = static_cast<unsigned>(FR_INVALID_NAME);
        return false;
    }
    workspace_.file = {};
    FRESULT result = f_open(&workspace_.file, child, FA_READ);
    if (result != FR_OK) {
        report->lastFailure = "read_open";
        report->lastFresult = static_cast<unsigned>(result);
        return false;
    }
    bool complete = f_size(&workspace_.file) == bundle->size();
    UINT bytesRead = 0U;
    if (complete) {
        result = f_read(&workspace_.file, bundle->data(),
                        static_cast<UINT>(bundle->size()), &bytesRead);
        complete = result == FR_OK && bytesRead == bundle->size();
    } else {
        result = FR_INVALID_OBJECT;
    }
    const FRESULT closed = f_close(&workspace_.file);
    workspace_.file = {};
    complete = complete && closed == FR_OK;
    report->bundleRead = complete;
    report->lastFailure = complete ? "none" : "read_bundle";
    report->lastFresult = static_cast<unsigned>(
        result != FR_OK ? result : closed);
    if (!complete) bundle->fill(0U);
    return complete;
}

bool BoardAutomationTrustHilFixture::create(
    const storage::WritePermit& permit,
    const apps::automation::AutomationTrustBundle& bundle,
    BoardAutomationTrustHilFixtureReport* report) {
    if (report == nullptr) return false;
    *report = {};
    ArduinoFsSessionStoreIo io(driveNumber_, workspace_);
    report->prepared = io.prepare(permit);
    if (report->prepared) {
        report->bundleWritten = io.writeFile(
            kAutomationTrustBundleName, bundle.data(), bundle.size());
        if (report->bundleWritten) {
            report->fileBarrierComplete =
                io.syncFile(kAutomationTrustBundleName);
        }
        report->directoryBarrierComplete =
            report->fileBarrierComplete && io.syncDirectory();
    }
    report->bytesWritten = io.bytesWritten();
    report->writeCalls = io.writeCalls();
    report->fileSyncs = io.fileSyncs();
    report->directorySyncs = io.directorySyncs();
    report->lastFailure = io.lastFailure();
    report->lastFresult = io.lastFresult();
    io.end();

    apps::automation::AutomationTrustBundle observed{};
    BoardAutomationTrustHilFixtureReport inspection;
    const bool inspected = report->directoryBarrierComplete &&
        inspect(permit.scratchPath, &observed, &inspection);
    report->exactEntries = inspection.exactEntries;
    report->bundleRead = inspection.bundleRead;
    report->bundleMatched = inspected && observed == bundle;
    if (!inspected) {
        report->lastFailure = inspection.lastFailure;
        report->lastFresult = inspection.lastFresult;
    } else if (!report->bundleMatched) {
        report->lastFailure = "bundle_mismatch";
        report->lastFresult = static_cast<unsigned>(FR_DENIED);
    }
    observed.fill(0U);
    return report->prepared && report->bundleWritten &&
        report->fileBarrierComplete && report->directoryBarrierComplete &&
        report->exactEntries && report->bundleRead && report->bundleMatched &&
        report->bytesWritten == kAutomationTrustHilFixtureRequiredBytes &&
        report->writeCalls == 1U && report->fileSyncs == 1U &&
        report->directorySyncs == 1U;
}

bool BoardAutomationTrustHilFixture::remove(
    const storage::ScratchCleanupPermit& permit,
    const apps::automation::AutomationTrustBundle& expected,
    BoardAutomationTrustHilFixtureReport* report) {
    if (report == nullptr) return false;
    *report = {};
    if (!permit.allowed()) {
        report->lastFailure = "cleanup_permit";
        report->lastFresult = static_cast<unsigned>(FR_DENIED);
        return false;
    }
    apps::automation::AutomationTrustBundle observed{};
    BoardAutomationTrustHilFixtureReport inspection;
    if (!inspect(permit.scratchPath, &observed, &inspection) ||
        observed != expected) {
        *report = inspection;
        report->bundleMatched = false;
        if (inspection.bundleRead) {
            report->lastFailure = "cleanup_bundle_mismatch";
            report->lastFresult = static_cast<unsigned>(FR_DENIED);
        }
        observed.fill(0U);
        return false;
    }
    observed.fill(0U);
    report->exactEntries = true;
    report->bundleRead = true;
    report->bundleMatched = true;

    char root[128] = {};
    char child[160] = {};
    if (!formatVolumePath(permit.scratchPath, root, sizeof(root))) {
        report->lastFailure = "cleanup_path";
        report->lastFresult = static_cast<unsigned>(FR_INVALID_NAME);
        return false;
    }
    const int written = std::snprintf(child, sizeof(child), "%s/%s", root,
                                      kAutomationTrustBundleName);
    if (written <= 0 || static_cast<std::size_t>(written) >= sizeof(child)) {
        report->lastFailure = "cleanup_child_path";
        report->lastFresult = static_cast<unsigned>(FR_INVALID_NAME);
        return false;
    }
    FRESULT result = f_unlink(child);
    if (result == FR_OK) {
        report->filesRemoved = 1U;
        result = f_unlink(root);
    }
    if (result != FR_OK) {
        report->lastFailure = "cleanup_remove";
        report->lastFresult = static_cast<unsigned>(result);
        return false;
    }
    workspace_.information = {};
    const FRESULT verified = f_stat(root, &workspace_.information);
    report->cleanupComplete =
        verified == FR_NO_FILE || verified == FR_NO_PATH;
    report->lastFailure = report->cleanupComplete ? "none" : "cleanup_verify";
    report->lastFresult = static_cast<unsigned>(verified);
    return report->cleanupComplete;
}

}  // namespace leshy1::platform::arduino
