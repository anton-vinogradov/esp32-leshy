#pragma once

#include <cstddef>
#include <cstdint>

namespace leshy1::apps::ble {

// Allocation-free lookup over a release-pinned Bluetooth SIG Company
// Identifiers snapshot embedded in flash. Records are sorted fixed-width:
// little-endian uint16 company ID plus a zero-padded 30-byte display name.
class BleCompanyDatabase final {
public:
    static constexpr std::size_t kRecordSize = 32;
    static constexpr std::size_t kNameSize = 30;

    BleCompanyDatabase() = default;
    BleCompanyDatabase(const std::uint8_t* data, std::size_t size) {
        reset(data, size);
    }

    bool reset(const std::uint8_t* data, std::size_t size);
    bool available() const { return data_ != nullptr && records_ != 0U; }
    std::size_t records() const { return records_; }
    bool lookup(std::uint16_t companyId, char* output,
                std::size_t capacity) const;

private:
    const std::uint8_t* data_ = nullptr;
    std::size_t records_ = 0;
};

}  // namespace leshy1::apps::ble
