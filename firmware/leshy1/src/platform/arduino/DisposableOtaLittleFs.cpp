#include "DisposableOtaLittleFs.h"

#include <array>
#include <cstdio>
#include <cstring>

#include <sys/stat.h>

#include <esp_littlefs.h>
#include <esp_ota_ops.h>
#include <mbedtls/sha256.h>

namespace leshy1::platform::arduino {
namespace {

std::array<std::uint8_t, 1024> hashWorkspace{};

}  // namespace

bool DisposableOtaLittleFs::inspect() {
    if (mounted_) return false;
    target_ = esp_partition_find_first(
        ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_APP_OTA_1,
        kPartitionLabel);
    running_ = esp_ota_get_running_partition();
    boot_ = esp_ota_get_boot_partition();
    return target_ != nullptr && running_ != nullptr && boot_ != nullptr;
}

bool DisposableOtaLittleFs::safeInactiveTarget() const {
    if (target_ == nullptr || running_ == nullptr || boot_ == nullptr) {
        return false;
    }
    const esp_partition_t* product = esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_DATA_SPIFFS, "spiffs");
    if (product == nullptr) return false;
    const std::uint64_t targetEnd =
        static_cast<std::uint64_t>(target_->address) + target_->size;
    const std::uint64_t productEnd =
        static_cast<std::uint64_t>(product->address) + product->size;
    const bool disjoint = targetEnd <= product->address ||
        productEnd <= target_->address;
    return target_->address == kExpectedAddress &&
        target_->size == kExpectedSize &&
        target_->type == ESP_PARTITION_TYPE_APP &&
        target_->subtype == ESP_PARTITION_SUBTYPE_APP_OTA_1 &&
        std::strcmp(target_->label, kPartitionLabel) == 0 &&
        running_->address != target_->address &&
        boot_->address != target_->address && disjoint;
}

bool DisposableOtaLittleFs::hashTarget(char* output,
                                       std::size_t capacity) const {
    if (!safeInactiveTarget() || output == nullptr || capacity < 65) {
        return false;
    }
    mbedtls_sha256_context context;
    mbedtls_sha256_init(&context);
    bool valid = mbedtls_sha256_starts(&context, 0) == 0;
    for (std::size_t offset = 0;
         valid && offset < target_->size; offset += hashWorkspace.size()) {
        const std::size_t remaining = target_->size - offset;
        const std::size_t size = remaining < hashWorkspace.size()
            ? remaining : hashWorkspace.size();
        valid = esp_partition_read(target_, offset, hashWorkspace.data(), size) ==
                    ESP_OK &&
            mbedtls_sha256_update(&context, hashWorkspace.data(), size) == 0;
    }
    std::array<std::uint8_t, 32> digest{};
    valid = valid && mbedtls_sha256_finish(&context, digest.data()) == 0;
    mbedtls_sha256_free(&context);
    hashWorkspace.fill(0);
    if (!valid) return false;
    for (std::size_t index = 0; index < digest.size(); ++index) {
        std::snprintf(output + index * 2, capacity - index * 2, "%02x",
                      static_cast<unsigned>(digest[index]));
    }
    output[64] = '\0';
    return true;
}

bool DisposableOtaLittleFs::mount(bool readOnly) {
    if (!safeInactiveTarget() || mounted_) return false;
    esp_vfs_littlefs_conf_t config{};
    config.base_path = kBasePath;
    config.partition_label = nullptr;
    config.partition = target_;
    config.format_if_mount_failed = false;
    config.read_only = readOnly;
    config.dont_mount = false;
    config.grow_on_mount = false;
    lastError_ = esp_vfs_littlefs_register(&config);
    mounted_ = lastError_ == ESP_OK;
    readOnly_ = mounted_ && readOnly;
    return mounted_;
}

bool DisposableOtaLittleFs::formatAndMountWritable() {
    if (!safeInactiveTarget() || mounted_) return false;
    lastError_ = esp_littlefs_format_partition(target_);
    formatted_ = lastError_ == ESP_OK;
    return formatted_ && mount(false);
}

bool DisposableOtaLittleFs::mountExistingWritable() {
    return mount(false);
}

bool DisposableOtaLittleFs::mountReadOnly() {
    return mount(true);
}

void DisposableOtaLittleFs::end() {
    if (mounted_) {
        lastError_ = esp_vfs_littlefs_unregister_partition(target_);
    }
    mounted_ = false;
    readOnly_ = false;
}

bool DisposableOtaLittleFs::cleanupComplete() const {
    return !mounted_ &&
        (target_ == nullptr || !esp_littlefs_partition_mounted(target_));
}

bool DisposableOtaLittleFs::validPath(const char* path) const {
    if (path == nullptr || path[0] != '/') return false;
    const std::size_t length = std::strlen(path);
    return length != 0 && length < 96 && std::strstr(path, "..") == nullptr;
}

bool DisposableOtaLittleFs::exists(const char* path) const {
    if (!mounted_ || !validPath(path)) return false;
    char fullPath[128] = {};
    const int written = std::snprintf(fullPath, sizeof(fullPath), "%s%s",
                                      kBasePath, path);
    if (written <= 0 || static_cast<std::size_t>(written) >= sizeof(fullPath)) {
        return false;
    }
    struct stat information {};
    return ::stat(fullPath, &information) == 0;
}

std::uint64_t DisposableOtaLittleFs::totalBytes() const {
    if (!mounted_) return 0;
    std::size_t total = 0;
    std::size_t used = 0;
    return esp_littlefs_partition_info(target_, &total, &used) == ESP_OK
        ? total : 0;
}

std::uint64_t DisposableOtaLittleFs::freeBytes() const {
    if (!mounted_) return 0;
    std::size_t total = 0;
    std::size_t used = 0;
    if (esp_littlefs_partition_info(target_, &total, &used) != ESP_OK ||
        used > total) {
        return 0;
    }
    return total - used;
}

std::uint32_t DisposableOtaLittleFs::targetAddress() const {
    return target_ == nullptr ? 0 : target_->address;
}

std::uint32_t DisposableOtaLittleFs::targetSize() const {
    return target_ == nullptr ? 0 : target_->size;
}

std::uint32_t DisposableOtaLittleFs::runningAddress() const {
    return running_ == nullptr ? 0 : running_->address;
}

std::uint32_t DisposableOtaLittleFs::bootAddress() const {
    return boot_ == nullptr ? 0 : boot_->address;
}

}  // namespace leshy1::platform::arduino
