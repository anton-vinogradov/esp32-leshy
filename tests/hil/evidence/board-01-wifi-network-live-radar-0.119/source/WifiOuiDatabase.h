#pragma once

#include <cstddef>
#include <cstdint>

namespace leshy1::apps::wifi {

// Allocation-free lookup over the release-pinned IEEE MA-L asset embedded in
// the application image. Records are sorted and fixed-width:
//   3-byte OUI (big-endian) + 29-byte, zero-padded display name.
class WifiOuiDatabase final {
public:
    static constexpr std::size_t kRecordSize = 32;
    static constexpr std::size_t kNameSize = 29;

    WifiOuiDatabase() = default;
    WifiOuiDatabase(const std::uint8_t* data, std::size_t size) {
        reset(data, size);
    }

    bool reset(const std::uint8_t* data, std::size_t size);
    bool available() const { return data_ != nullptr && records_ != 0U; }
    std::size_t records() const { return records_; }
    bool lookup(const std::uint8_t* mac, char* output,
                std::size_t capacity) const;

private:
    const std::uint8_t* data_ = nullptr;
    std::size_t records_ = 0;
};

}  // namespace leshy1::apps::wifi
