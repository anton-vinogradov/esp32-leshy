#pragma once

#include <cstdint>

#include <esp_err.h>
#include <ff.h>
#include <sdmmc_cmd.h>

namespace leshy1::platform::arduino {

enum class BoardSdFilesystemMountStage : std::uint8_t {
    Idle,
    BusInitializing,
    VfsMounting,
    Mounted,
};

const char* boardSdFilesystemMountStageName(
    BoardSdFilesystemMountStage stage);

// Explicit writable SD fixture adapter. Callers must hold Storage+RadioSpi and
// obtain a StorageGuard permit before creating any path. Formatting is disabled.
class BoardSdFilesystem final {
public:
    static constexpr std::uint32_t kSpiHz = 4000000;

    bool begin();
    // Mounts through ESP-IDF, then replaces the drive's disk-I/O table before
    // returning so every write/trim attempt is rejected with write-protected.
    bool beginReadOnly();
    void end();

    std::uint8_t driveNumber() const { return driveNumber_; }
    bool mounted() const { return mounted_; }
    std::uint64_t cardCapacityBytes() const;
    std::uint64_t filesystemCapacityBytes() const;
    std::uint64_t freeBytes() const;
    // Returns the FATFS/FSInfo cached free-cluster hint without walking the FAT.
    // Zero means either full media or unavailable evidence; product admission
    // treats both cases fail-closed as insufficient space.
    std::uint64_t cachedFreeBytes() const;
    bool exists(const char* path) const;
    bool gpio21StableHigh() const { return gpio21StableHigh_; }
    bool cleanupComplete() const { return cleanupComplete_; }
    bool formatAllowed() const { return false; }
    bool readOnlyGuaranteed() const { return readOnlyGuaranteed_; }
    std::uint32_t blockedWriteAttempts() const;
    int mountError() const { return static_cast<int>(mountError_); }
    BoardSdFilesystemMountStage mountStage() const { return mountStage_; }
    const char* mountStageName() const {
        return boardSdFilesystemMountStageName(mountStage_);
    }
    int busInitializeError() const {
        return static_cast<int>(busInitializeError_);
    }
    std::uint32_t heapFreeBeforeBus() const { return heapFreeBeforeBus_; }
    std::uint32_t heapLargestBeforeBus() const {
        return heapLargestBeforeBus_;
    }
    std::uint32_t heapFreeBeforeVfs() const { return heapFreeBeforeVfs_; }
    std::uint32_t heapLargestBeforeVfs() const {
        return heapLargestBeforeVfs_;
    }
    bool driveAvailableBeforeVfs() const {
        return driveAvailableBeforeVfs_;
    }
    std::uint32_t realFrequencyHz() const;

private:
    bool beginWithMode(bool readOnly);
    bool guardSharedChipSelect();
    bool installReadOnlyDiskIo();

    sdmmc_card_t* card_ = nullptr;
    // Owned by the ESP-IDF VFS mount and valid only while mounted_. Keeping
    // this registration pointer avoids opening the root directory merely to
    // read FatFs' already-cached FSInfo fields on every product remount.
    FATFS* filesystem_ = nullptr;
    std::uint8_t driveNumber_ = 0xFF;
    bool busInitialized_ = false;
    bool mounted_ = false;
    bool gpio21StableHigh_ = true;
    bool cleanupComplete_ = false;
    bool readOnlyGuaranteed_ = false;
    std::uint32_t blockedWriteAttemptsAfterEnd_ = 0;
    esp_err_t mountError_ = ESP_OK;
    BoardSdFilesystemMountStage mountStage_ =
        BoardSdFilesystemMountStage::Idle;
    esp_err_t busInitializeError_ = ESP_OK;
    std::uint32_t heapFreeBeforeBus_ = 0;
    std::uint32_t heapLargestBeforeBus_ = 0;
    std::uint32_t heapFreeBeforeVfs_ = 0;
    std::uint32_t heapLargestBeforeVfs_ = 0;
    bool driveAvailableBeforeVfs_ = false;
};

}  // namespace leshy1::platform::arduino
