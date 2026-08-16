#pragma once

#include <stddef.h>
#include <stdint.h>

namespace leshy::hil {

struct NrfObservation {
    uint8_t status;
    uint8_t config;
    uint8_t channel;
    uint8_t rfSetup;
    uint8_t feature;
};

inline bool allEqual(const NrfObservation& value, uint8_t expected) {
    return value.status == expected && value.config == expected &&
           value.channel == expected && value.rfSetup == expected &&
           value.feature == expected;
}

inline bool plausibleNrfObservation(const NrfObservation& value) {
    if (allEqual(value, 0x00) || allEqual(value, 0xFF)) return false;
    if ((value.status & 0x80U) != 0U) return false;
    if (value.channel > 125U) return false;
    return true;
}

inline bool plausibleCcObservation(uint8_t chipStatus, uint8_t partNumber,
                                   uint8_t version) {
    if (chipStatus == 0xFFU) return false;
    if (partNumber == 0xFFU && version == 0xFFU) return false;
    if (partNumber == 0x00U && (version == 0x00U || version == 0xFFU)) return false;
    return true;
}

inline int hexNibble(char value) {
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'A' && value <= 'F') return value - 'A' + 10;
    if (value >= 'a' && value <= 'f') return value - 'a' + 10;
    return -1;
}

inline bool validNmeaChecksum(const char* line, size_t length) {
    if (line == nullptr || length < 7 || line[0] != '$') return false;

    size_t star = 1;
    while (star < length && line[star] != '*') ++star;
    if (star + 2 >= length || line[star] != '*') return false;

    uint8_t checksum = 0;
    for (size_t index = 1; index < star; ++index) {
        checksum ^= static_cast<uint8_t>(line[index]);
    }

    const int high = hexNibble(line[star + 1]);
    const int low = hexNibble(line[star + 2]);
    if (high < 0 || low < 0) return false;
    return checksum == static_cast<uint8_t>((high << 4) | low);
}

}  // namespace leshy::hil
