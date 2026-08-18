#pragma once

#include <cstddef>
#include <cstdint>

#include <esp_err.h>
#include <esp_partition.h>

namespace leshy1::platform::arduino {

// HIL-only LittleFS target. The normal product filesystem is deliberately never
// selected: this adapter accepts only the inactive 4 MiB OTA1 partition from the
// pinned board layout. The host runner must back up and byte-verify that region
// before the explicit destructive command and restore it before resetting.
class DisposableOtaLittleFs final {
public:
    static constexpr std::uint32_t kExpectedAddress = 0x410000;
    static constexpr std::uint32_t kExpectedSize = 0x400000;
    static constexpr const char* kPartitionLabel = "app1";
    static constexpr const char* kBasePath = "/hil-lfs";

    bool inspect();
    bool safeInactiveTarget() const;
    bool hashTarget(char* output, std::size_t capacity) const;
    bool formatAndMountWritable();
    bool mountReadOnly();
    void end();

    bool mounted() const { return mounted_; }
    bool readOnly() const { return readOnly_; }
    bool formatted() const { return formatted_; }
    bool cleanupComplete() const;
    bool exists(const char* path) const;
    std::uint64_t totalBytes() const;
    std::uint64_t freeBytes() const;
    std::uint32_t targetAddress() const;
    std::uint32_t targetSize() const;
    std::uint32_t runningAddress() const;
    std::uint32_t bootAddress() const;
    esp_err_t lastError() const { return lastError_; }

private:
    bool mount(bool readOnly);
    bool validPath(const char* path) const;

    const esp_partition_t* target_ = nullptr;
    const esp_partition_t* running_ = nullptr;
    const esp_partition_t* boot_ = nullptr;
    bool mounted_ = false;
    bool readOnly_ = false;
    bool formatted_ = false;
    esp_err_t lastError_ = ESP_OK;
};

}  // namespace leshy1::platform::arduino
