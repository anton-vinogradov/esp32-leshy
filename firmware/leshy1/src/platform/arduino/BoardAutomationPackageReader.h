#pragma once

#include <cstddef>
#include <cstdint>

#include "apps/automation/AutomationInspectorController.h"
#include "platform/arduino/ArduinoFsSessionStoreIo.h"

namespace leshy1::platform::arduino {

constexpr const char* kAutomationPackageLibraryRoot =
    "/leshy/automation/v1";

// Product reads stay in the fixed Library namespace. Physical HIL may select
// one exact StorageGuard scratch directory so the same read-only adapter and
// UI path can inspect disposable packages without touching user data.
bool validAutomationPackageLibraryRoot(const char* root);

enum class BoardAutomationPackageStatus : std::uint8_t {
    Ready,
    InvalidArgument,
    DirectoryUnavailable,
    ScanFailed,
    OpenFailed,
    SizeChanged,
    TooLarge,
    ReadFailed,
    CloseFailed,
};

const char* boardAutomationPackageStatusName(
    BoardAutomationPackageStatus status);

// Read-only FatFs adapter for the fixed automation Library namespace. The
// caller owns the mounted read-only filesystem and shared bounded workspace.
class BoardAutomationPackageReader final {
public:
    explicit BoardAutomationPackageReader(
        ArduinoFsSessionStoreWorkspace& workspace,
        const char* root = kAutomationPackageLibraryRoot)
        : workspace_(workspace), root_(root) {}

    BoardAutomationPackageStatus scan(
        std::uint8_t driveNumber,
        apps::automation::AutomationPackageCatalog* catalog,
        std::uint32_t* omittedEntries = nullptr);
    BoardAutomationPackageStatus read(
        std::uint8_t driveNumber,
        const apps::automation::AutomationPackageCatalogEntry& entry,
        std::uint8_t* output, std::size_t capacity,
        std::size_t* outputSize);

private:
    bool formatRoot(std::uint8_t driveNumber, char* output,
                    std::size_t capacity) const;
    bool formatFile(std::uint8_t driveNumber, const char* name, char* output,
                    std::size_t capacity) const;

    ArduinoFsSessionStoreWorkspace& workspace_;
    const char* root_ = kAutomationPackageLibraryRoot;
};

}  // namespace leshy1::platform::arduino
