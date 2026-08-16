#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "storage/SdReadOnlyProtocol.h"

namespace leshy1::storage {

constexpr std::uint8_t kSdMaxR1PollBytes = 16;
constexpr std::uint8_t kSdMaxDataTokenPollBytes = 8;
constexpr std::uint8_t kSdMaxBlockTokenPollBytes = 64;

struct SdCommandFrame final {
    std::array<std::uint8_t, 6> bytes{};
};

enum class SdWireStatus : std::uint8_t {
    Valid,
    InvalidPlan,
    CommandNotAllowed,
    ArgumentInvalid,
    InvalidBound,
    IoError,
    ResponseTimeout,
    ResponseInvalid,
    DataTokenTimeout,
    DataTokenInvalid,
    DataChecksumInvalid,
};

class SdByteSource {
public:
    virtual ~SdByteSource() = default;
    virtual bool readByte(std::uint8_t* value) = 0;
};

const char* sdWireStatusName(SdWireStatus status);
std::uint8_t sdCrc7(const std::uint8_t* data, std::size_t size);
SdWireStatus encodeSdIdentificationCommand(const SdReadOnlyPlan& plan,
                                           std::uint8_t command,
                                           std::uint32_t argument,
                                           SdCommandFrame* output);
SdWireStatus encodeSdReadSingleBlockCommand(std::uint32_t lba,
                                            SdCommandFrame* output);
SdWireStatus readSdR1(SdByteSource& source, std::uint8_t maxPollBytes,
                      std::uint8_t* response);
SdWireStatus readSdTrailing32(SdByteSource& source, std::uint32_t* value);
SdWireStatus readSdData16(SdByteSource& source, std::uint8_t maxTokenPollBytes,
                          std::array<std::uint8_t, 16>* data,
                          std::uint16_t* receivedCrc16);
SdWireStatus readSdData512(SdByteSource& source, std::uint8_t maxTokenPollBytes,
                           std::array<std::uint8_t, 512>* data,
                           std::uint16_t* receivedCrc16);
bool formatSdWireContractJson(char* output, std::size_t capacity);

}  // namespace leshy1::storage
