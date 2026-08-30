#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "apps/automation/AutomationTrustStore.h"

namespace leshy1::apps::automation {

constexpr std::size_t kAutomationTrustBundleBytes = 128U;
using AutomationTrustBundle =
    std::array<std::uint8_t, kAutomationTrustBundleBytes>;

enum class AutomationTrustBundleStatus : std::uint8_t {
    Parsed,
    InvalidArgument,
    InvalidMagic,
    UnsupportedVersion,
    UnsupportedAlgorithm,
    LengthMismatch,
    InvalidReserved,
    InvalidChecksum,
    InvalidKey,
};

const char* automationTrustBundleStatusName(
    AutomationTrustBundleStatus status);

AutomationTrustBundleStatus parseAutomationTrustBundle(
    const std::uint8_t* bytes, std::size_t size,
    AutomationTrustedKey* output);

}  // namespace leshy1::apps::automation
