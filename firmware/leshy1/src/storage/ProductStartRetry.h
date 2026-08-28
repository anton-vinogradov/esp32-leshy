#pragma once

#include <cstdint>

#include "storage/SdIdentificationTransport.h"

namespace leshy1::storage {

struct ProductStartIdentityRetryEvidence final {
    bool explicitStart = false;
    bool enrolled = false;
    bool expectedFingerprintValid = false;
    bool requiredResourcesHeld = false;
    bool physicalSpiStarted = false;
    SdTransportRunStatus identityStatus = SdTransportRunStatus::InvalidPlan;
    bool observedFingerprintEmpty = false;
    bool identityCleanupComplete = false;
    bool filesystemAttempted = false;
};

// A writable FAT mount may be repeated only while the surrounding product
// lifecycle is quiescent. Every failed attempt must have released the VFS,
// disk-I/O registration and SPI bus before this policy is consulted; otherwise
// retrying could conceal a live owner or permit writes against an uncertain
// card. This applies both to initial admission and to a terminal reopen after
// radio teardown.
struct ProductStartFilesystemRetryEvidence final {
    bool explicitStart = false;
    bool enrolled = false;
    bool expectedFingerprintValid = false;
    bool requiredResourcesHeld = false;
    bool identityValid = false;
    bool identityCleanupComplete = false;
    bool observedFingerprintMatches = false;
    bool mountAttempted = false;
    bool mountSucceeded = false;
    int mountError = 0;
    bool filesystemCleanupComplete = false;
    bool filesystemStillMounted = false;
    bool storeCurrentlyOpen = false;
    bool radioCurrentlyActive = false;
    bool cancelRequested = false;
};

constexpr std::uint8_t kProductStartMaximumIdentityAttempts = 8;
constexpr std::uint32_t kProductStartIdentityRetryBaseDelayMs = 250;
constexpr std::uint8_t kProductStartMaximumFilesystemAttempts = 3;
constexpr std::uint32_t kProductStartFilesystemRetryBaseDelayMs = 50;
constexpr int kProductStartTransientFilesystemMountError = 0x101;

// Only raw, read-only identification may be repeated here. The caller must not
// have attempted a filesystem mount or write before consulting this policy.
bool shouldRetryProductStartIdentity(
    const ProductStartIdentityRetryEvidence& evidence,
    std::uint8_t completedAttempts);

std::uint32_t productStartIdentityRetryDelayMs(
    std::uint8_t completedAttempts);

// Retries only the observed ESP_ERR_NO_MEM failure after complete cleanup.
// Media, wire, VFS, GPIO and ownership failures remain single-attempt failures.
bool shouldRetryProductStartFilesystem(
    const ProductStartFilesystemRetryEvidence& evidence,
    std::uint8_t completedAttempts);

std::uint32_t productStartFilesystemRetryDelayMs(
    std::uint8_t completedAttempts);

}  // namespace leshy1::storage
