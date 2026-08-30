#include "BoardAutomationPackageReader.h"

#include <cstdio>
#include <limits>

namespace leshy1::platform::arduino {

const char* boardAutomationPackageStatusName(
    BoardAutomationPackageStatus status) {
    switch (status) {
        case BoardAutomationPackageStatus::Ready: return "ready";
        case BoardAutomationPackageStatus::InvalidArgument:
            return "invalid_argument";
        case BoardAutomationPackageStatus::DirectoryUnavailable:
            return "directory_unavailable";
        case BoardAutomationPackageStatus::ScanFailed: return "scan_failed";
        case BoardAutomationPackageStatus::OpenFailed: return "open_failed";
        case BoardAutomationPackageStatus::SizeChanged: return "size_changed";
        case BoardAutomationPackageStatus::TooLarge: return "too_large";
        case BoardAutomationPackageStatus::ReadFailed: return "read_failed";
        case BoardAutomationPackageStatus::CloseFailed: return "close_failed";
    }
    return "invalid";
}

bool BoardAutomationPackageReader::formatRoot(
    std::uint8_t driveNumber, char* output, std::size_t capacity) const {
    if (driveNumber >= FF_VOLUMES || driveNumber > 9U || output == nullptr ||
        capacity == 0U) {
        return false;
    }
    const int written = std::snprintf(
        output, capacity, "%u:%s", static_cast<unsigned>(driveNumber),
        kAutomationPackageLibraryRoot);
    return written > 0 && static_cast<std::size_t>(written) < capacity;
}

bool BoardAutomationPackageReader::formatFile(
    std::uint8_t driveNumber, const char* name, char* output,
    std::size_t capacity) const {
    if (!apps::automation::validAutomationPackageName(name) ||
        driveNumber >= FF_VOLUMES || driveNumber > 9U || output == nullptr ||
        capacity == 0U) {
        return false;
    }
    const int written = std::snprintf(
        output, capacity, "%u:%s/%s", static_cast<unsigned>(driveNumber),
        kAutomationPackageLibraryRoot, name);
    return written > 0 && static_cast<std::size_t>(written) < capacity;
}

BoardAutomationPackageStatus BoardAutomationPackageReader::scan(
    std::uint8_t driveNumber,
    apps::automation::AutomationPackageCatalog* catalog,
    std::uint32_t* omittedEntries) {
    if (catalog == nullptr) {
        return BoardAutomationPackageStatus::InvalidArgument;
    }
    catalog->clear();
    if (omittedEntries != nullptr) *omittedEntries = 0U;
    char root[96] = {};
    if (!formatRoot(driveNumber, root, sizeof(root))) {
        return BoardAutomationPackageStatus::InvalidArgument;
    }
    FF_DIR directory{};
    const FRESULT opened = f_opendir(&directory, root);
    if (opened != FR_OK) {
        return BoardAutomationPackageStatus::DirectoryUnavailable;
    }
    BoardAutomationPackageStatus status = BoardAutomationPackageStatus::Ready;
    std::uint32_t eligibleEntries = 0U;
    for (;;) {
        workspace_.information = {};
        const FRESULT read = f_readdir(&directory, &workspace_.information);
        if (read != FR_OK) {
            status = BoardAutomationPackageStatus::ScanFailed;
            break;
        }
        if (workspace_.information.fname[0] == '\0') break;
        if ((workspace_.information.fattrib & AM_DIR) != 0U ||
            !apps::automation::validAutomationPackageName(
                workspace_.information.fname)) {
            continue;
        }
        const FSIZE_t fileSize = workspace_.information.fsize;
        const std::uint32_t boundedSize =
            fileSize > std::numeric_limits<std::uint32_t>::max()
                ? std::numeric_limits<std::uint32_t>::max()
                : static_cast<std::uint32_t>(fileSize);
        if (eligibleEntries != std::numeric_limits<std::uint32_t>::max()) {
            ++eligibleEntries;
        }
        (void)catalog->add(workspace_.information.fname, boundedSize);
    }
    const FRESULT closed = f_closedir(&directory);
    if (closed != FR_OK && status == BoardAutomationPackageStatus::Ready) {
        status = BoardAutomationPackageStatus::CloseFailed;
    }
    if (omittedEntries != nullptr && eligibleEntries > catalog->size()) {
        *omittedEntries = eligibleEntries -
            static_cast<std::uint32_t>(catalog->size());
    }
    return status;
}

BoardAutomationPackageStatus BoardAutomationPackageReader::read(
    std::uint8_t driveNumber,
    const apps::automation::AutomationPackageCatalogEntry& entry,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize) {
    if (outputSize != nullptr) *outputSize = 0U;
    if (output == nullptr || outputSize == nullptr || capacity == 0U ||
        !apps::automation::validAutomationPackageName(entry.name.data())) {
        return BoardAutomationPackageStatus::InvalidArgument;
    }
    char path[144] = {};
    if (!formatFile(driveNumber, entry.name.data(), path, sizeof(path))) {
        return BoardAutomationPackageStatus::InvalidArgument;
    }
    workspace_.file = {};
    const FRESULT opened = f_open(&workspace_.file, path, FA_READ);
    if (opened != FR_OK) return BoardAutomationPackageStatus::OpenFailed;

    BoardAutomationPackageStatus status = BoardAutomationPackageStatus::Ready;
    const FSIZE_t observedSize = f_size(&workspace_.file);
    if (observedSize != entry.size) {
        status = BoardAutomationPackageStatus::SizeChanged;
    } else if (observedSize > capacity ||
               observedSize > apps::automation::kAutomationMaximumPackageBytes) {
        status = BoardAutomationPackageStatus::TooLarge;
    } else {
        UINT bytesRead = 0U;
        const FRESULT result = f_read(
            &workspace_.file, output, static_cast<UINT>(observedSize),
            &bytesRead);
        if (result != FR_OK || bytesRead != observedSize) {
            status = BoardAutomationPackageStatus::ReadFailed;
        } else {
            *outputSize = static_cast<std::size_t>(bytesRead);
        }
    }
    const FRESULT closed = f_close(&workspace_.file);
    workspace_.file = {};
    if (closed != FR_OK && status == BoardAutomationPackageStatus::Ready) {
        status = BoardAutomationPackageStatus::CloseFailed;
        *outputSize = 0U;
    }
    return status;
}

}  // namespace leshy1::platform::arduino
