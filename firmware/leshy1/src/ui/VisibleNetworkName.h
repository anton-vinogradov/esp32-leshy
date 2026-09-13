#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace leshy1::ui {

// An SSID is up to 32 bytes, not a C string. Preserve valid UTF-8, escape
// controls/invalid bytes, and truncate only between complete display tokens.
inline void formatVisibleNetworkName(const char* bytes, std::size_t length,
                                      const char* hidden, char* output,
                                      std::size_t capacity) {
    if (!output || capacity == 0U) return;
    output[0] = '\0';
    if (!bytes || length == 0U) {
        bytes = hidden; length = std::strlen(hidden);
    }
    std::size_t written = 0;
    constexpr char hex[] = "0123456789ABCDEF";
    for (std::size_t at = 0; at < length;) {
        const auto lead = static_cast<std::uint8_t>(bytes[at]);
        std::size_t count = lead < 0x80U ? 1U :
            (lead >= 0xC2U && lead <= 0xDFU ? 2U :
             (lead >= 0xE0U && lead <= 0xEFU ? 3U :
              (lead >= 0xF0U && lead <= 0xF4U ? 4U : 0U)));
        bool valid = count != 0U && at + count <= length &&
                     lead >= 0x20U && lead != 0x7FU && lead != '\\';
        for (std::size_t i = 1; valid && i < count; ++i) {
            const auto next = static_cast<std::uint8_t>(bytes[at + i]);
            valid = next >= 0x80U && next <= 0xBFU;
            if (i == 1U) valid = valid &&
                !(lead == 0xE0U && next < 0xA0U) &&
                !(lead == 0xEDU && next >= 0xA0U) &&
                !(lead == 0xF0U && next < 0x90U) &&
                !(lead == 0xF4U && next >= 0x90U);
        }
        char escaped[] = {'\\', 'x', hex[lead >> 4U], hex[lead & 15U]};
        const std::size_t tokenSize = valid ? count : 4U;
        const std::size_t consumed = valid ? count : 1U;
        const bool more = at + consumed < length;
        if (written + tokenSize + (more ? 1U : 0U) >= capacity) {
            if (written + 1U < capacity) output[written++] = '~';
            break;
        }
        std::memcpy(output + written, valid ? bytes + at : escaped, tokenSize);
        written += tokenSize;
        at += consumed;
    }
    output[written] = '\0';
}

}  // namespace leshy1::ui
