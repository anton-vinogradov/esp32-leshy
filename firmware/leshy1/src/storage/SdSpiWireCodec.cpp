#include "SdSpiWireCodec.h"

#include <cstdio>

#include "storage/SdIdentification.h"

namespace leshy1::storage {
namespace {

bool expectedArgument(std::uint8_t command, std::uint32_t* argument) {
    if (argument == nullptr) return false;
    switch (command) {
        case 8: *argument = 0x000001AAU; return true;
        case 41: *argument = 0x40000000U; return true;
        case 0:
        case 55:
        case 58:
        case 10:
        case 9: *argument = 0; return true;
        default: return false;
    }
}

}  // namespace

const char* sdWireStatusName(SdWireStatus status) {
    switch (status) {
        case SdWireStatus::Valid: return "valid";
        case SdWireStatus::InvalidPlan: return "invalid_plan";
        case SdWireStatus::CommandNotAllowed: return "command_not_allowed";
        case SdWireStatus::ArgumentInvalid: return "argument_invalid";
        case SdWireStatus::InvalidBound: return "invalid_bound";
        case SdWireStatus::IoError: return "io_error";
        case SdWireStatus::ResponseTimeout: return "response_timeout";
        case SdWireStatus::ResponseInvalid: return "response_invalid";
        case SdWireStatus::DataTokenTimeout: return "data_token_timeout";
        case SdWireStatus::DataTokenInvalid: return "data_token_invalid";
        case SdWireStatus::DataChecksumInvalid: return "data_checksum_invalid";
    }
    return "io_error";
}

std::uint8_t sdCrc7(const std::uint8_t* data, std::size_t size) {
    if (data == nullptr && size != 0) return 0;
    std::uint8_t crc = 0;
    for (std::size_t index = 0; index < size; ++index) {
        std::uint8_t value = data[index];
        for (std::uint8_t bit = 0; bit < 8; ++bit) {
            crc <<= 1U;
            if (((value ^ crc) & 0x80U) != 0) crc ^= 0x09U;
            value <<= 1U;
        }
    }
    return static_cast<std::uint8_t>(crc & 0x7FU);
}

SdWireStatus encodeSdIdentificationCommand(const SdReadOnlyPlan& plan,
                                           std::uint8_t command,
                                           std::uint32_t argument,
                                           SdCommandFrame* output) {
    if (output == nullptr ||
        validateSdIdentificationPlan(plan) != SdReadOnlyPlanStatus::Valid) {
        return SdWireStatus::InvalidPlan;
    }
    *output = {};
    std::uint32_t expected = 0;
    if (!expectedArgument(command, &expected)) return SdWireStatus::CommandNotAllowed;
    if (argument != expected) return SdWireStatus::ArgumentInvalid;
    output->bytes[0] = static_cast<std::uint8_t>(0x40U | command);
    output->bytes[1] = static_cast<std::uint8_t>(argument >> 24U);
    output->bytes[2] = static_cast<std::uint8_t>(argument >> 16U);
    output->bytes[3] = static_cast<std::uint8_t>(argument >> 8U);
    output->bytes[4] = static_cast<std::uint8_t>(argument);
    output->bytes[5] = static_cast<std::uint8_t>((sdCrc7(output->bytes.data(), 5) << 1U) | 1U);
    return SdWireStatus::Valid;
}

SdWireStatus encodeSdReadSingleBlockCommand(std::uint32_t lba,
                                            SdCommandFrame* output) {
    if (output == nullptr) return SdWireStatus::InvalidBound;
    *output = {};
    output->bytes[0] = static_cast<std::uint8_t>(0x40U | 17U);
    output->bytes[1] = static_cast<std::uint8_t>(lba >> 24U);
    output->bytes[2] = static_cast<std::uint8_t>(lba >> 16U);
    output->bytes[3] = static_cast<std::uint8_t>(lba >> 8U);
    output->bytes[4] = static_cast<std::uint8_t>(lba);
    output->bytes[5] = static_cast<std::uint8_t>(
        (sdCrc7(output->bytes.data(), 5) << 1U) | 1U);
    return SdWireStatus::Valid;
}

SdWireStatus readSdR1(SdByteSource& source, std::uint8_t maxPollBytes,
                      std::uint8_t* response) {
    if (response == nullptr || maxPollBytes == 0 || maxPollBytes > kSdMaxR1PollBytes) {
        return SdWireStatus::InvalidBound;
    }
    *response = 0xFF;
    for (std::uint8_t index = 0; index < maxPollBytes; ++index) {
        std::uint8_t value = 0xFF;
        if (!source.readByte(&value)) return SdWireStatus::IoError;
        if (value == 0xFF) continue;
        if ((value & 0x80U) != 0) return SdWireStatus::ResponseInvalid;
        *response = value;
        return SdWireStatus::Valid;
    }
    return SdWireStatus::ResponseTimeout;
}

SdWireStatus readSdTrailing32(SdByteSource& source, std::uint32_t* value) {
    if (value == nullptr) return SdWireStatus::InvalidBound;
    *value = 0;
    for (std::uint8_t index = 0; index < 4; ++index) {
        std::uint8_t current = 0;
        if (!source.readByte(&current)) return SdWireStatus::IoError;
        *value = static_cast<std::uint32_t>((*value << 8U) | current);
    }
    return SdWireStatus::Valid;
}

SdWireStatus readSdData16(SdByteSource& source, std::uint8_t maxTokenPollBytes,
                          std::array<std::uint8_t, 16>* data,
                          std::uint16_t* receivedCrc16) {
    if (data == nullptr || receivedCrc16 == nullptr || maxTokenPollBytes == 0 ||
        maxTokenPollBytes > kSdMaxDataTokenPollBytes) {
        return SdWireStatus::InvalidBound;
    }
    *data = {};
    *receivedCrc16 = 0;
    bool token = false;
    for (std::uint8_t index = 0; index < maxTokenPollBytes; ++index) {
        std::uint8_t value = 0xFF;
        if (!source.readByte(&value)) return SdWireStatus::IoError;
        if (value == 0xFE) {
            token = true;
            break;
        }
        if (value != 0xFF) return SdWireStatus::DataTokenInvalid;
    }
    if (!token) return SdWireStatus::DataTokenTimeout;
    for (std::uint8_t index = 0; index < data->size(); ++index) {
        if (!source.readByte(&(*data)[index])) return SdWireStatus::IoError;
    }
    std::uint8_t high = 0;
    std::uint8_t low = 0;
    if (!source.readByte(&high) || !source.readByte(&low)) return SdWireStatus::IoError;
    *receivedCrc16 = static_cast<std::uint16_t>((static_cast<std::uint16_t>(high) << 8U) | low);
    if (sdCrc16(data->data(), data->size()) != *receivedCrc16) {
        return SdWireStatus::DataChecksumInvalid;
    }
    return SdWireStatus::Valid;
}

SdWireStatus readSdData512(SdByteSource& source, std::uint8_t maxTokenPollBytes,
                           std::array<std::uint8_t, 512>* data,
                           std::uint16_t* receivedCrc16) {
    if (data == nullptr || receivedCrc16 == nullptr || maxTokenPollBytes == 0 ||
        maxTokenPollBytes > kSdMaxBlockTokenPollBytes) {
        return SdWireStatus::InvalidBound;
    }
    *data = {};
    *receivedCrc16 = 0;
    bool token = false;
    for (std::uint8_t index = 0; index < maxTokenPollBytes; ++index) {
        std::uint8_t value = 0xFF;
        if (!source.readByte(&value)) return SdWireStatus::IoError;
        if (value == 0xFE) {
            token = true;
            break;
        }
        if (value != 0xFF) return SdWireStatus::DataTokenInvalid;
    }
    if (!token) return SdWireStatus::DataTokenTimeout;
    for (std::size_t index = 0; index < data->size(); ++index) {
        if (!source.readByte(&(*data)[index])) return SdWireStatus::IoError;
    }
    std::uint8_t high = 0;
    std::uint8_t low = 0;
    if (!source.readByte(&high) || !source.readByte(&low)) return SdWireStatus::IoError;
    *receivedCrc16 = static_cast<std::uint16_t>(
        (static_cast<std::uint16_t>(high) << 8U) | low);
    if (sdCrc16(data->data(), data->size()) != *receivedCrc16) {
        return SdWireStatus::DataChecksumInvalid;
    }
    return SdWireStatus::Valid;
}

bool formatSdWireContractJson(char* output, std::size_t capacity) {
    if (output == nullptr || capacity == 0) return false;
    const SdReadOnlyPlan plan = defaultSdIdentificationPlan();
    SdCommandFrame cmd0;
    SdCommandFrame cmd8;
    if (encodeSdIdentificationCommand(plan, 0, 0, &cmd0) != SdWireStatus::Valid ||
        encodeSdIdentificationCommand(plan, 8, 0x1AAU, &cmd8) != SdWireStatus::Valid) {
        output[0] = '\0';
        return false;
    }
    const int written = std::snprintf(
        output, capacity,
        "{\"schema\":\"leshy.storage.sd.wire.v1\",\"kind\":\"report\","
        "\"status\":\"valid\",\"cmd0_frame\":\"400000000095\","
        "\"cmd8_frame\":\"48000001AA87\",\"crc7\":true,"
        "\"crc16\":true,\"max_r1_poll_bytes\":%u,"
        "\"max_data_token_poll_bytes\":%u,\"execution_enabled\":false,"
        "\"physical_spi_executed\":false,\"commands_executed\":0,"
        "\"write_commands\":false,\"radio_touched\":false}",
        static_cast<unsigned>(kSdMaxR1PollBytes),
        static_cast<unsigned>(kSdMaxDataTokenPollBytes));
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

}  // namespace leshy1::storage
