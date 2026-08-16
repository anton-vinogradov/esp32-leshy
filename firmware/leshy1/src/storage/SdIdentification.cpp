#include "SdIdentification.h"

#include <cstdio>

namespace leshy1::storage {
namespace {

std::uint32_t extractBits(const std::array<std::uint8_t, 16>& value,
                          std::uint8_t msb, std::uint8_t lsb) {
    std::uint32_t result = 0;
    for (int bit = msb; bit >= static_cast<int>(lsb); --bit) {
        const std::size_t offset = static_cast<std::size_t>(127 - bit);
        const std::uint8_t current =
            static_cast<std::uint8_t>((value[offset / 8] >> (7 - (offset % 8))) & 1U);
        result = static_cast<std::uint32_t>((result << 1U) | current);
    }
    return result;
}

void setBits(std::array<std::uint8_t, 16>& value, std::uint8_t msb, std::uint8_t lsb,
             std::uint32_t bits) {
    for (int bit = lsb; bit <= static_cast<int>(msb); ++bit) {
        const std::size_t offset = static_cast<std::size_t>(127 - bit);
        const std::uint8_t source =
            static_cast<std::uint8_t>((bits >> (bit - static_cast<int>(lsb))) & 1U);
        const std::uint8_t mask = static_cast<std::uint8_t>(1U << (7 - (offset % 8)));
        if (source != 0) value[offset / 8] |= mask;
        else value[offset / 8] &= static_cast<std::uint8_t>(~mask);
    }
}

bool uniform(const std::array<std::uint8_t, 16>& value, std::uint8_t expected) {
    for (const std::uint8_t current : value) {
        if (current != expected) return false;
    }
    return true;
}

}  // namespace

const char* sdIdentificationStatusName(SdIdentificationStatus status) {
    switch (status) {
        case SdIdentificationStatus::Valid: return "valid";
        case SdIdentificationStatus::InvalidPlan: return "invalid_plan";
        case SdIdentificationStatus::ResponseInvalid: return "response_invalid";
        case SdIdentificationStatus::VoltageEchoInvalid: return "voltage_echo_invalid";
        case SdIdentificationStatus::InitAttemptsInvalid: return "init_attempts_invalid";
        case SdIdentificationStatus::OcrInvalid: return "ocr_invalid";
        case SdIdentificationStatus::CidChecksumInvalid: return "cid_checksum_invalid";
        case SdIdentificationStatus::CidInvalid: return "cid_invalid";
        case SdIdentificationStatus::CsdChecksumInvalid: return "csd_checksum_invalid";
        case SdIdentificationStatus::CsdUnsupported: return "csd_unsupported";
        case SdIdentificationStatus::CapacityInvalid: return "capacity_invalid";
    }
    return "response_invalid";
}

std::uint16_t sdCrc16(const std::uint8_t* data, std::size_t size) {
    if (data == nullptr && size != 0) return 0;
    std::uint16_t crc = 0;
    for (std::size_t index = 0; index < size; ++index) {
        crc ^= static_cast<std::uint16_t>(data[index]) << 8U;
        for (std::uint8_t bit = 0; bit < 8; ++bit) {
            crc = (crc & 0x8000U) != 0
                      ? static_cast<std::uint16_t>((crc << 1U) ^ 0x1021U)
                      : static_cast<std::uint16_t>(crc << 1U);
        }
    }
    return crc;
}

SdIdentificationTranscript goldenSdIdentificationTranscript() {
    SdIdentificationTranscript transcript;
    transcript.cmd0R1 = 0x01;
    transcript.cmd8R1 = 0x01;
    transcript.cmd8Echo = 0x000001AAU;
    transcript.cmd55R1 = 0x01;
    transcript.acmd41R1 = 0x00;
    transcript.initAttempts = 3;
    transcript.cmd58R1 = 0x00;
    transcript.ocr = 0xC0FF8000U;
    transcript.cmd10R1 = 0x00;
    transcript.cid = {0x03, 0x53, 0x44, 0x4C, 0x45, 0x53, 0x48, 0x59,
                      0x10, 0x5A, 0x12, 0x34, 0x56, 0x78, 0x01, 0xA5};
    transcript.cidCrc16 = sdCrc16(transcript.cid.data(), transcript.cid.size());
    transcript.cmd9R1 = 0x00;
    setBits(transcript.csd, 127, 126, 1);  // CSD v2
    setBits(transcript.csd, 69, 48, 31);   // 16 MiB synthetic bounded fixture
    transcript.csdCrc16 = sdCrc16(transcript.csd.data(), transcript.csd.size());
    return transcript;
}

SdIdentificationStatus parseSdIdentification(const SdReadOnlyPlan& plan,
                                             const SdIdentificationTranscript& transcript,
                                             SdIdentity* output) {
    if (output == nullptr ||
        validateSdIdentificationPlan(plan) != SdReadOnlyPlanStatus::Valid) {
        return SdIdentificationStatus::InvalidPlan;
    }
    *output = {};
    if (transcript.cmd0R1 != 0x01 || transcript.cmd8R1 != 0x01 ||
        transcript.cmd55R1 != 0x01 || transcript.acmd41R1 != 0x00 ||
        transcript.cmd58R1 != 0x00 || transcript.cmd10R1 != 0x00 ||
        transcript.cmd9R1 != 0x00) {
        return SdIdentificationStatus::ResponseInvalid;
    }
    if ((transcript.cmd8Echo & 0xFFFU) != 0x1AAU) {
        return SdIdentificationStatus::VoltageEchoInvalid;
    }
    if (transcript.initAttempts == 0 ||
        transcript.initAttempts > plan.maxInitAttempts) {
        return SdIdentificationStatus::InitAttemptsInvalid;
    }
    if ((transcript.ocr & 0x80000000U) == 0 ||
        (transcript.ocr & 0x00FF8000U) == 0) {
        return SdIdentificationStatus::OcrInvalid;
    }
    if (sdCrc16(transcript.cid.data(), transcript.cid.size()) != transcript.cidCrc16) {
        return SdIdentificationStatus::CidChecksumInvalid;
    }
    if (uniform(transcript.cid, 0x00) || uniform(transcript.cid, 0xFF)) {
        return SdIdentificationStatus::CidInvalid;
    }
    if (sdCrc16(transcript.csd.data(), transcript.csd.size()) != transcript.csdCrc16) {
        return SdIdentificationStatus::CsdChecksumInvalid;
    }
    if (extractBits(transcript.csd, 127, 126) != 1U) {
        return SdIdentificationStatus::CsdUnsupported;
    }
    const std::uint32_t cSize = extractBits(transcript.csd, 69, 48);
    const std::uint64_t capacity =
        (static_cast<std::uint64_t>(cSize) + 1U) * 512U * 1024U;
    if (capacity == 0) return SdIdentificationStatus::CapacityInvalid;
    output->cid = transcript.cid;
    output->csd = transcript.csd;
    output->ocr = transcript.ocr;
    output->capacityBytes = capacity;
    output->initAttempts = transcript.initAttempts;
    output->highCapacity = (transcript.ocr & 0x40000000U) != 0;
    return SdIdentificationStatus::Valid;
}

bool formatSdIdentificationJson(const SdIdentity& identity, char* output,
                                std::size_t capacity) {
    if (output == nullptr || capacity == 0 || identity.capacityBytes == 0) return false;
    char cidHex[33] = {};
    for (std::size_t index = 0; index < identity.cid.size(); ++index) {
        std::snprintf(cidHex + index * 2, sizeof(cidHex) - index * 2, "%02X",
                      static_cast<unsigned>(identity.cid[index]));
    }
    const int written = std::snprintf(
        output, capacity,
        "{\"schema\":\"leshy.storage.sd.identification.v1\",\"kind\":\"result\","
        "\"status\":\"valid\",\"transport\":\"golden_fake\","
        "\"physical_spi_executed\":false,\"commands_executed\":0,"
        "\"init_attempts\":%u,\"ocr\":%lu,\"high_capacity\":%s,"
        "\"cid_hex\":\"%s\",\"cid_crc16_valid\":true,"
        "\"csd_crc16_valid\":true,\"capacity_bytes\":%llu,"
        "\"write_commands\":false,\"radio_touched\":false}",
        static_cast<unsigned>(identity.initAttempts),
        static_cast<unsigned long>(identity.ocr),
        identity.highCapacity ? "true" : "false", cidHex,
        static_cast<unsigned long long>(identity.capacityBytes));
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

}  // namespace leshy1::storage
