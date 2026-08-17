#include "BoardSdFilesystem.h"

#include <Arduino.h>
#include <cstdio>

#include <driver/sdspi_host.h>
#include <driver/spi_master.h>
#include <esp_vfs_fat.h>
#include <diskio_impl.h>
#include <ff.h>

extern "C" BYTE ff_diskio_get_pdrv_card(const sdmmc_card_t* card);

#include "boards/esp32_div_v2/BoardProfile.h"
#include "platform/arduino/BoardSdSpiTransport.h"

namespace leshy1::platform::arduino {
namespace {

using boards::esp32_div_v2::BoardProfile;
constexpr const char* kSdMountPoint = "/sd-hil";
constexpr spi_host_device_t kSdHost = SPI2_HOST;
sdmmc_card_t* readOnlyCards[FF_VOLUMES] = {};
std::uint32_t blockedWriteCounts[FF_VOLUMES] = {};

DSTATUS readOnlyInitialize(BYTE drive) {
    if (drive >= FF_VOLUMES || readOnlyCards[drive] == nullptr) {
        return static_cast<DSTATUS>(STA_NOINIT | STA_PROTECT);
    }
    return sdmmc_get_status(readOnlyCards[drive]) == ESP_OK
               ? STA_PROTECT
               : static_cast<DSTATUS>(STA_NOINIT | STA_PROTECT);
}

DSTATUS readOnlyStatus(BYTE drive) {
    return readOnlyInitialize(drive);
}

DRESULT readOnlyRead(BYTE drive, BYTE* output, DWORD sector, UINT count) {
    if (drive >= FF_VOLUMES || readOnlyCards[drive] == nullptr ||
        output == nullptr || count == 0) {
        return RES_PARERR;
    }
    return sdmmc_read_sectors(readOnlyCards[drive], output, sector, count) ==
                   ESP_OK
               ? RES_OK
               : RES_ERROR;
}

DRESULT rejectReadOnlyWrite(BYTE drive, const BYTE*, DWORD, UINT) {
    if (drive < FF_VOLUMES) ++blockedWriteCounts[drive];
    return RES_WRPRT;
}

DRESULT readOnlyIoctl(BYTE drive, BYTE command, void* output) {
    if (drive >= FF_VOLUMES || readOnlyCards[drive] == nullptr) {
        return RES_PARERR;
    }
    switch (command) {
        case CTRL_SYNC:
            return RES_OK;
        case GET_SECTOR_COUNT:
            if (output == nullptr) return RES_PARERR;
            *static_cast<DWORD*>(output) = readOnlyCards[drive]->csd.capacity;
            return RES_OK;
        case GET_SECTOR_SIZE:
            if (output == nullptr) return RES_PARERR;
            *static_cast<WORD*>(output) = readOnlyCards[drive]->csd.sector_size;
            return RES_OK;
        case GET_BLOCK_SIZE:
            if (output == nullptr) return RES_PARERR;
            *static_cast<DWORD*>(output) = 1;
            return RES_OK;
        default:
            return command == CTRL_TRIM ? RES_WRPRT : RES_PARERR;
    }
}

std::uint64_t fatSectorSize(const FATFS* filesystem) {
    if (filesystem == nullptr) return 0;
#if FF_MAX_SS != FF_MIN_SS
    return filesystem->ssize;
#else
    return FF_MAX_SS;
#endif
}

}  // namespace

bool BoardSdFilesystem::guardSharedChipSelect() {
    if (digitalRead(BoardProfile::kNrfCsPins[2]) == HIGH) return true;
    gpio21StableHigh_ = false;
    return false;
}

bool BoardSdFilesystem::begin() {
    return beginWithMode(false);
}

bool BoardSdFilesystem::beginReadOnly() {
    return beginWithMode(true);
}

bool BoardSdFilesystem::beginWithMode(bool readOnly) {
    if (busInitialized_ || mounted_ || card_ != nullptr) return false;
    cleanupComplete_ = false;
    gpio21StableHigh_ = true;
    readOnlyGuaranteed_ = false;
    blockedWriteAttemptsAfterEnd_ = 0;
    mountError_ = ESP_OK;
    driveNumber_ = 0xFF;
    BoardSdSpiTransport::holdRadioTransmitPathsInactive();
    pinMode(BoardProfile::kNrfCsPins[0], OUTPUT);
    pinMode(BoardProfile::kNrfCsPins[1], OUTPUT);
    pinMode(BoardProfile::kCc1101CsPin, OUTPUT);
    pinMode(BoardProfile::kSdCsPin, OUTPUT);
    digitalWrite(BoardProfile::kNrfCsPins[0], HIGH);
    digitalWrite(BoardProfile::kNrfCsPins[1], HIGH);
    digitalWrite(BoardProfile::kCc1101CsPin, HIGH);
    digitalWrite(BoardProfile::kSdCsPin, HIGH);
    if (!guardSharedChipSelect()) {
        end();
        return false;
    }

    spi_bus_config_t busConfig{};
    busConfig.mosi_io_num = BoardProfile::kRadioMosiPin;
    busConfig.miso_io_num = BoardProfile::kRadioMisoPin;
    busConfig.sclk_io_num = BoardProfile::kRadioSckPin;
    busConfig.quadwp_io_num = -1;
    busConfig.quadhd_io_num = -1;
    busConfig.max_transfer_sz = 4096;
    mountError_ = spi_bus_initialize(kSdHost, &busConfig, SPI_DMA_CH_AUTO);
    if (mountError_ != ESP_OK) {
        end();
        return false;
    }
    busInitialized_ = true;

    sdmmc_host_t host = SDSPI_HOST_DEFAULT();
    host.slot = kSdHost;
    host.max_freq_khz = static_cast<int>(kSpiHz / 1000U);
    host.command_timeout_ms = 1000;
    sdspi_device_config_t device = SDSPI_DEVICE_CONFIG_DEFAULT();
    device.host_id = kSdHost;
    device.gpio_cs = static_cast<gpio_num_t>(BoardProfile::kSdCsPin);
    device.gpio_cd = SDSPI_SLOT_NO_CD;
    device.gpio_wp = SDSPI_SLOT_NO_WP;
    device.wait_for_miso = 100;
    esp_vfs_fat_mount_config_t mount = VFS_FAT_MOUNT_DEFAULT_CONFIG();
    mount.format_if_mount_failed = false;
    mount.max_files = 5;
    mount.disk_status_check_enable = true;
    mountError_ = esp_vfs_fat_sdspi_mount(
        kSdMountPoint, &host, &device, &mount, &card_);
    if (mountError_ != ESP_OK || card_ == nullptr) {
        end();
        return false;
    }
    driveNumber_ = ff_diskio_get_pdrv_card(card_);
    mounted_ = driveNumber_ < FF_VOLUMES && guardSharedChipSelect();
    if (!mounted_) {
        mountError_ = ESP_ERR_INVALID_STATE;
        end();
        return false;
    }
    if (readOnly && !installReadOnlyDiskIo()) {
        mountError_ = ESP_ERR_INVALID_STATE;
        end();
        return false;
    }
    return true;
}

bool BoardSdFilesystem::installReadOnlyDiskIo() {
    if (!mounted_ || card_ == nullptr || driveNumber_ >= FF_VOLUMES) {
        return false;
    }
    static const ff_diskio_impl_t implementation = {
        &readOnlyInitialize,
        &readOnlyStatus,
        &readOnlyRead,
        &rejectReadOnlyWrite,
        &readOnlyIoctl,
    };
    readOnlyCards[driveNumber_] = card_;
    blockedWriteCounts[driveNumber_] = 0;
    ff_diskio_register(driveNumber_, &implementation);
    readOnlyGuaranteed_ =
        (readOnlyStatus(driveNumber_) & STA_PROTECT) != 0;
    return readOnlyGuaranteed_;
}

void BoardSdFilesystem::end() {
    const std::uint8_t previousDrive = driveNumber_;
    bool unmounted = true;
    if (card_ != nullptr) {
        unmounted = esp_vfs_fat_sdcard_unmount(kSdMountPoint, card_) == ESP_OK;
        card_ = nullptr;
    }
    if (previousDrive < FF_VOLUMES) {
        blockedWriteAttemptsAfterEnd_ = blockedWriteCounts[previousDrive];
        blockedWriteCounts[previousDrive] = 0;
        readOnlyCards[previousDrive] = nullptr;
    }
    mounted_ = false;
    driveNumber_ = 0xFF;
    readOnlyGuaranteed_ = false;
    bool busFreed = true;
    if (busInitialized_) {
        busFreed = spi_bus_free(kSdHost) == ESP_OK;
        busInitialized_ = false;
    }
    digitalWrite(BoardProfile::kSdCsPin, HIGH);
    pinMode(BoardProfile::kRadioMosiPin, INPUT);
    pinMode(BoardProfile::kRadioMisoPin, INPUT);
    pinMode(BoardProfile::kRadioSckPin, INPUT);
    BoardSdSpiTransport::holdRadioTransmitPathsInactive();
    cleanupComplete_ = unmounted && busFreed &&
        digitalRead(BoardProfile::kSdCsPin) == HIGH &&
        digitalRead(BoardProfile::kNrfCsPins[0]) == HIGH &&
        digitalRead(BoardProfile::kNrfCsPins[1]) == HIGH &&
        digitalRead(BoardProfile::kCc1101CsPin) == HIGH &&
        digitalRead(BoardProfile::kNrfCePins[0]) == LOW &&
        digitalRead(BoardProfile::kNrfCePins[1]) == LOW &&
        digitalRead(BoardProfile::kNrfCePins[2]) == LOW &&
        guardSharedChipSelect();
}

std::uint32_t BoardSdFilesystem::blockedWriteAttempts() const {
    return driveNumber_ < FF_VOLUMES
               ? blockedWriteCounts[driveNumber_]
               : blockedWriteAttemptsAfterEnd_;
}

std::uint64_t BoardSdFilesystem::cardCapacityBytes() const {
    return mounted_ && card_ != nullptr
        ? static_cast<std::uint64_t>(card_->csd.capacity) *
              static_cast<std::uint64_t>(card_->csd.sector_size)
        : 0;
}

std::uint64_t BoardSdFilesystem::filesystemCapacityBytes() const {
    if (!mounted_ || driveNumber_ >= FF_VOLUMES) return 0;
    FATFS* filesystem = nullptr;
    DWORD freeClusters = 0;
    char drive[3] = {static_cast<char>('0' + driveNumber_), ':', '\0'};
    if (f_getfree(drive, &freeClusters, &filesystem) != FR_OK ||
        filesystem == nullptr) {
        return 0;
    }
    return static_cast<std::uint64_t>(filesystem->csize) *
           static_cast<std::uint64_t>(filesystem->n_fatent - 2U) *
           fatSectorSize(filesystem);
}

std::uint64_t BoardSdFilesystem::freeBytes() const {
    if (!mounted_ || driveNumber_ >= FF_VOLUMES) return 0;
    FATFS* filesystem = nullptr;
    DWORD freeClusters = 0;
    char drive[3] = {static_cast<char>('0' + driveNumber_), ':', '\0'};
    if (f_getfree(drive, &freeClusters, &filesystem) != FR_OK ||
        filesystem == nullptr) {
        return 0;
    }
    return static_cast<std::uint64_t>(filesystem->csize) *
           static_cast<std::uint64_t>(freeClusters) *
           fatSectorSize(filesystem);
}

std::uint64_t BoardSdFilesystem::cachedFreeBytes() const {
    if (!mounted_ || driveNumber_ >= FF_VOLUMES) return 0;
    char root[4] = {static_cast<char>('0' + driveNumber_), ':', '/', '\0'};
    FF_DIR directory{};
    if (f_opendir(&directory, root) != FR_OK) return 0;
    const FATFS* filesystem = directory.obj.fs;
    std::uint64_t result = 0;
    if (filesystem != nullptr && filesystem->n_fatent >= 2U &&
        filesystem->free_clst <= filesystem->n_fatent - 2U) {
        result = static_cast<std::uint64_t>(filesystem->csize) *
                 static_cast<std::uint64_t>(filesystem->free_clst) *
                 fatSectorSize(filesystem);
    }
    f_closedir(&directory);
    return result;
}

bool BoardSdFilesystem::exists(const char* path) const {
    if (!mounted_ || driveNumber_ >= FF_VOLUMES || path == nullptr ||
        path[0] != '/') {
        return false;
    }
    char fullPath[96] = {};
    const int written = std::snprintf(fullPath, sizeof(fullPath), "%u:%s",
                                      static_cast<unsigned>(driveNumber_), path);
    if (written <= 0 || static_cast<std::size_t>(written) >= sizeof(fullPath)) {
        return false;
    }
    FILINFO information{};
    return f_stat(fullPath, &information) == FR_OK;
}

std::uint32_t BoardSdFilesystem::realFrequencyHz() const {
    return mounted_ && card_ != nullptr && card_->real_freq_khz > 0
        ? static_cast<std::uint32_t>(card_->real_freq_khz) * 1000U : 0;
}

}  // namespace leshy1::platform::arduino
