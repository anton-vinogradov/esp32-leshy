#pragma once

#include <cstdint>

#include <esp_err.h>
#include <sdmmc_cmd.h>

namespace leshy1::platform::arduino {

// Explicit writable SD fixture adapter. Callers must hold Storage+RadioSpi and
// obtain a StorageGuard permit before creating any path. Formatting is disabled.
class BoardSdFilesystem final {
public:
    static constexpr std::uint32_t kSpiHz = 4000000;

    bool begin();
    void end();

    std::uint8_t driveNumber() const { return driveNumber_; }
    bool mounted() const { return mounted_; }
    std::uint64_t cardCapacityBytes() const;
    std::uint64_t filesystemCapacityBytes() const;
    std::uint64_t freeBytes() const;
    bool exists(const char* path) const;
    bool gpio21StableHigh() const { return gpio21StableHigh_; }
    bool cleanupComplete() const { return cleanupComplete_; }
    bool formatAllowed() const { return false; }
    int mountError() const { return static_cast<int>(mountError_); }
    std::uint32_t realFrequencyHz() const;

private:
    bool guardSharedChipSelect();

    sdmmc_card_t* card_ = nullptr;
    std::uint8_t driveNumber_ = 0xFF;
    bool busInitialized_ = false;
    bool mounted_ = false;
    bool gpio21StableHigh_ = true;
    bool cleanupComplete_ = false;
    esp_err_t mountError_ = ESP_OK;
};

}  // namespace leshy1::platform::arduino
