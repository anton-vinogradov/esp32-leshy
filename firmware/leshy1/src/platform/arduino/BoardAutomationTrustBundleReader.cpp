#include "BoardAutomationTrustBundleReader.h"

#include <cstdio>

namespace leshy1::platform::arduino {

const char* boardAutomationTrustBundleStatusName(
    BoardAutomationTrustBundleStatus status) {
    switch (status) {
        case BoardAutomationTrustBundleStatus::Ready: return "ready";
        case BoardAutomationTrustBundleStatus::InvalidArgument:
            return "invalid_argument";
        case BoardAutomationTrustBundleStatus::OpenFailed: return "open_failed";
        case BoardAutomationTrustBundleStatus::SizeMismatch:
            return "size_mismatch";
        case BoardAutomationTrustBundleStatus::ReadFailed: return "read_failed";
        case BoardAutomationTrustBundleStatus::CloseFailed: return "close_failed";
    }
    return "invalid";
}

BoardAutomationTrustBundleStatus BoardAutomationTrustBundleReader::read(
    std::uint8_t driveNumber, const char* root,
    apps::automation::AutomationTrustBundle* output) {
    if (root == nullptr || root[0] != '/' || output == nullptr ||
        driveNumber >= FF_VOLUMES || driveNumber > 9U) {
        return BoardAutomationTrustBundleStatus::InvalidArgument;
    }
    output->fill(0U);
    char path[96] = {};
    const int written = std::snprintf(
        path, sizeof(path), "%u:%s/%s",
        static_cast<unsigned>(driveNumber), root,
        kAutomationTrustBundleName);
    if (written <= 0 || static_cast<std::size_t>(written) >= sizeof(path)) {
        return BoardAutomationTrustBundleStatus::InvalidArgument;
    }
    workspace_.file = {};
    const FRESULT opened = f_open(&workspace_.file, path, FA_READ);
    if (opened != FR_OK) return BoardAutomationTrustBundleStatus::OpenFailed;

    BoardAutomationTrustBundleStatus status =
        BoardAutomationTrustBundleStatus::Ready;
    const FSIZE_t observed = f_size(&workspace_.file);
    if (observed != output->size()) {
        status = BoardAutomationTrustBundleStatus::SizeMismatch;
    } else {
        UINT bytesRead = 0U;
        const FRESULT read = f_read(
            &workspace_.file, output->data(),
            static_cast<UINT>(output->size()), &bytesRead);
        if (read != FR_OK || bytesRead != output->size()) {
            status = BoardAutomationTrustBundleStatus::ReadFailed;
        }
    }
    const FRESULT closed = f_close(&workspace_.file);
    workspace_.file = {};
    if (closed != FR_OK && status == BoardAutomationTrustBundleStatus::Ready) {
        status = BoardAutomationTrustBundleStatus::CloseFailed;
    }
    if (status != BoardAutomationTrustBundleStatus::Ready) output->fill(0U);
    return status;
}

}  // namespace leshy1::platform::arduino
