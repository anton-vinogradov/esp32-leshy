#include "BleCompanyDatabase.h"

#include <algorithm>
#include <cstring>

namespace leshy1::apps::ble {

bool BleCompanyDatabase::reset(const std::uint8_t* data, std::size_t size) {
    data_ = nullptr;
    records_ = 0U;
    if (data == nullptr || size == 0U || size % kRecordSize != 0U) {
        return false;
    }
    data_ = data;
    records_ = size / kRecordSize;
    return true;
}

bool BleCompanyDatabase::lookup(std::uint16_t companyId, char* output,
                                std::size_t capacity) const {
    if (output != nullptr && capacity != 0U) output[0] = '\0';
    if (!available() || output == nullptr || capacity < 2U) return false;
    std::size_t low = 0U;
    std::size_t high = records_;
    while (low < high) {
        const std::size_t middle = low + (high - low) / 2U;
        const std::uint8_t* record = data_ + middle * kRecordSize;
        const std::uint16_t key = static_cast<std::uint16_t>(
            record[0] | (static_cast<std::uint16_t>(record[1]) << 8U));
        if (key < companyId) {
            low = middle + 1U;
        } else {
            high = middle;
        }
    }
    if (low >= records_) return false;
    const std::uint8_t* record = data_ + low * kRecordSize;
    const std::uint16_t key = static_cast<std::uint16_t>(
        record[0] | (static_cast<std::uint16_t>(record[1]) << 8U));
    if (key != companyId) return false;
    const char* name = reinterpret_cast<const char*>(record + 2U);
    std::size_t length = 0U;
    while (length < kNameSize && name[length] != '\0') ++length;
    length = std::min(length, capacity - 1U);
    std::memcpy(output, name, length);
    output[length] = '\0';
    return length != 0U;
}

}  // namespace leshy1::apps::ble
