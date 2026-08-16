#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "storage/SdReadOnlyProtocol.h"

namespace leshy1::storage {

struct SdIdentificationTranscript final {
    std::uint8_t cmd0R1 = 0xFF;
    std::uint8_t cmd8R1 = 0xFF;
    std::uint32_t cmd8Echo = 0;
    std::uint8_t cmd55R1 = 0xFF;
    std::uint8_t acmd41R1 = 0xFF;
    std::uint16_t initAttempts = 0;
    std::uint8_t cmd58R1 = 0xFF;
    std::uint32_t ocr = 0;
    std::uint8_t cmd10R1 = 0xFF;
    std::array<std::uint8_t, 16> cid{};
    std::uint16_t cidCrc16 = 0;
    std::uint8_t cmd9R1 = 0xFF;
    std::array<std::uint8_t, 16> csd{};
    std::uint16_t csdCrc16 = 0;
};

struct SdIdentity final {
    std::array<std::uint8_t, 16> cid{};
    std::array<std::uint8_t, 16> csd{};
    std::uint32_t ocr = 0;
    std::uint64_t capacityBytes = 0;
    std::uint16_t initAttempts = 0;
    bool highCapacity = false;
};

enum class SdIdentificationStatus : std::uint8_t {
    Valid,
    InvalidPlan,
    ResponseInvalid,
    VoltageEchoInvalid,
    InitAttemptsInvalid,
    OcrInvalid,
    CidChecksumInvalid,
    CidInvalid,
    CsdChecksumInvalid,
    CsdUnsupported,
    CapacityInvalid,
};

const char* sdIdentificationStatusName(SdIdentificationStatus status);
std::uint16_t sdCrc16(const std::uint8_t* data, std::size_t size);
SdIdentificationTranscript goldenSdIdentificationTranscript();
SdIdentificationStatus parseSdIdentification(const SdReadOnlyPlan& plan,
                                             const SdIdentificationTranscript& transcript,
                                             SdIdentity* output);
bool formatSdIdentificationJson(const SdIdentity& identity, char* output,
                                std::size_t capacity);

}  // namespace leshy1::storage
