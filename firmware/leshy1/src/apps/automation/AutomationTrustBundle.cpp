#include "AutomationTrustBundle.h"

#include <cstring>

namespace leshy1::apps::automation {
namespace {

constexpr std::size_t kChecksumOffset = kAutomationTrustBundleBytes - 4U;

std::uint16_t read16(const std::uint8_t* bytes) {
    return static_cast<std::uint16_t>(bytes[0]) |
        static_cast<std::uint16_t>(
            static_cast<std::uint16_t>(bytes[1]) << 8U);
}

std::uint32_t read32(const std::uint8_t* bytes) {
    return static_cast<std::uint32_t>(bytes[0]) |
        (static_cast<std::uint32_t>(bytes[1]) << 8U) |
        (static_cast<std::uint32_t>(bytes[2]) << 16U) |
        (static_cast<std::uint32_t>(bytes[3]) << 24U);
}

std::uint32_t crc32(const std::uint8_t* bytes, std::size_t size) {
    std::uint32_t crc = 0xffffffffU;
    for (std::size_t index = 0U; index < size; ++index) {
        crc ^= bytes[index];
        for (std::uint8_t bit = 0U; bit < 8U; ++bit) {
            const std::uint32_t mask =
                static_cast<std::uint32_t>(0U - (crc & 1U));
            crc = (crc >> 1U) ^ (0xedb88320U & mask);
        }
    }
    return ~crc;
}

}  // namespace

const char* automationTrustBundleStatusName(
    AutomationTrustBundleStatus status) {
    switch (status) {
        case AutomationTrustBundleStatus::Parsed: return "parsed";
        case AutomationTrustBundleStatus::InvalidArgument:
            return "invalid_argument";
        case AutomationTrustBundleStatus::InvalidMagic: return "invalid_magic";
        case AutomationTrustBundleStatus::UnsupportedVersion:
            return "unsupported_version";
        case AutomationTrustBundleStatus::UnsupportedAlgorithm:
            return "unsupported_algorithm";
        case AutomationTrustBundleStatus::LengthMismatch:
            return "length_mismatch";
        case AutomationTrustBundleStatus::InvalidReserved:
            return "invalid_reserved";
        case AutomationTrustBundleStatus::InvalidChecksum:
            return "invalid_checksum";
        case AutomationTrustBundleStatus::InvalidKey: return "invalid_key";
    }
    return "invalid";
}

AutomationTrustBundleStatus parseAutomationTrustBundle(
    const std::uint8_t* bytes, std::size_t size,
    AutomationTrustedKey* output) {
    if (bytes == nullptr || output == nullptr) {
        return AutomationTrustBundleStatus::InvalidArgument;
    }
    *output = {};
    if (size != kAutomationTrustBundleBytes || read16(bytes + 6U) != size) {
        return AutomationTrustBundleStatus::LengthMismatch;
    }
    if (std::memcmp(bytes, "LHAK", 4U) != 0) {
        return AutomationTrustBundleStatus::InvalidMagic;
    }
    if (bytes[4U] != 1U) {
        return AutomationTrustBundleStatus::UnsupportedVersion;
    }
    if (bytes[5U] != static_cast<std::uint8_t>(
                           AutomationSignatureAlgorithm::EcdsaP256Sha256)) {
        return AutomationTrustBundleStatus::UnsupportedAlgorithm;
    }
    for (std::size_t index = 105U; index < kChecksumOffset; ++index) {
        if (bytes[index] != 0U) {
            return AutomationTrustBundleStatus::InvalidReserved;
        }
    }
    if (read32(bytes + kChecksumOffset) != crc32(bytes, kChecksumOffset)) {
        return AutomationTrustBundleStatus::InvalidChecksum;
    }
    std::memcpy(output->keyId.data(), bytes + 8U, output->keyId.size());
    std::memcpy(output->publicKey.data(), bytes + 16U,
                output->publicKey.size());
    std::memcpy(output->label.data(), bytes + 81U,
                kAutomationTrustLabelBytes);
    output->label[kAutomationTrustLabelBytes] = '\0';
    if (!validAutomationTrustedKey(*output)) {
        *output = {};
        return AutomationTrustBundleStatus::InvalidKey;
    }
    return AutomationTrustBundleStatus::Parsed;
}

}  // namespace leshy1::apps::automation
