#include "BoardSdFilesystem.h"

#include <Arduino.h>
#include <cstdio>

#include <driver/sdspi_host.h>
#include <driver/spi_master.h>
#include <esp_vfs_fat.h>
#include <ff.h>

extern "C" BYTE ff_diskio_get_pdrv_card(const sdmmc_card_t* card);

#include "boards/esp32_div_v2/BoardProfile.h"
#include "platform/arduino/BoardSdSpiTransport.h"

namespace leshy1::platform::arduino {
namespace {

using boards::esp32_div_v2::BoardProfile;
constexpr const char* kSdMountPoint = "/sd-hil";
constexpr spi_host_device_t kSdHost = SPI2_HOST;

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
    if (busInitialized_ || mounted_ || card_ != nullptr) return false;
    cleanupComplete_ = false;
    gpio21StableHigh_ = true;
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
    return true;
}

void BoardSdFilesystem::end() {
    bool unmounted = true;
    if (card_ != nullptr) {
        unmounted = esp_vfs_fat_sdcard_unmount(kSdMountPoint, card_) == ESP_OK;
        card_ = nullptr;
    }
    mounted_ = false;
    driveNumber_ = 0xFF;
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
