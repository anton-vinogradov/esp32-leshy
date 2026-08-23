#include "WifiOuiDatabase.h"

#include <algorithm>
#include <cstring>

namespace leshy1::apps::wifi {

bool WifiOuiDatabase::reset(const std::uint8_t* data, std::size_t size) {
    data_ = nullptr;
    records_ = 0;
    if (data == nullptr || size == 0U || size % kRecordSize != 0U) {
        return false;
    }
    data_ = data;
    records_ = size / kRecordSize;
    return true;
}

bool WifiOuiDatabase::lookup(const std::uint8_t* mac, char* output,
                             std::size_t capacity) const {
    if (output != nullptr && capacity != 0U) output[0] = '\0';
    if (!available() || mac == nullptr || output == nullptr || capacity < 2U ||
        (mac[0] & 0x03U) != 0U) {
        return false;
    }
    const std::uint32_t key = (static_cast<std::uint32_t>(mac[0]) << 16U) |
        (static_cast<std::uint32_t>(mac[1]) << 8U) | mac[2];
    std::size_t low = 0U;
    std::size_t high = records_;
    while (low < high) {
        const std::size_t middle = low + (high - low) / 2U;
        const std::uint8_t* record = data_ + middle * kRecordSize;
        const std::uint32_t recordKey =
            (static_cast<std::uint32_t>(record[0]) << 16U) |
            (static_cast<std::uint32_t>(record[1]) << 8U) | record[2];
        if (recordKey < key) {
            low = middle + 1U;
        } else {
            high = middle;
        }
    }
    if (low >= records_) return false;
    const std::uint8_t* record = data_ + low * kRecordSize;
    const bool match = record[0] == mac[0] && record[1] == mac[1] &&
        record[2] == mac[2];
    if (!match) return false;
    const char* name = reinterpret_cast<const char*>(record + 3U);
    std::size_t length = 0U;
    while (length < kNameSize && name[length] != '\0') ++length;
    length = std::min(length, capacity - 1U);
    std::memcpy(output, name, length);
    output[length] = '\0';
    return length != 0U;
}

}  // namespace leshy1::apps::wifi
