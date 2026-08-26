#include "CompanionConnectivity.h"

#include <cstdio>

namespace leshy1::services::companion {
namespace {

constexpr char kCredentialAlphabet[] =
    "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
constexpr std::size_t kCredentialAlphabetSize =
    sizeof(kCredentialAlphabet) - 1U;

void secureClear(char* bytes, std::size_t size) {
    volatile char* cursor = bytes;
    while (size-- != 0U) *cursor++ = '\0';
}

}  // namespace

const char* companionLocalStopReasonName(CompanionLocalStopReason reason) {
    switch (reason) {
        case CompanionLocalStopReason::None: return "none";
        case CompanionLocalStopReason::User: return "user";
        case CompanionLocalStopReason::LeftForeground:
            return "left_foreground";
        case CompanionLocalStopReason::IdleTimeout: return "idle_timeout";
        case CompanionLocalStopReason::LifetimeTimeout:
            return "lifetime_timeout";
        case CompanionLocalStopReason::SafetyStop: return "safety_stop";
        case CompanionLocalStopReason::StartFailed: return "start_failed";
    }
    return "start_failed";
}

bool CompanionLocalCredentials::valid() const {
    std::size_t ssidLength = 0;
    while (ssidLength < ssid.size() && ssid[ssidLength] != '\0') {
        ++ssidLength;
    }
    std::size_t passphraseLength = 0;
    while (passphraseLength < passphrase.size() &&
           passphrase[passphraseLength] != '\0') {
        ++passphraseLength;
    }
    return ssidLength >= 7U && ssidLength <= kCompanionLocalSsidCapacity &&
        passphraseLength == kCompanionLocalPassphraseCapacity;
}

void CompanionLocalCredentials::clear() {
    secureClear(ssid.data(), ssid.size());
    secureClear(passphrase.data(), passphrase.size());
}

bool makeCompanionLocalCredentials(
    const std::array<std::uint8_t, 6>& deviceMac,
    const std::array<std::uint8_t, 16>& entropy,
    CompanionLocalCredentials* output) {
    if (output == nullptr) return false;
    CompanionLocalCredentials candidate{};
    const int ssidLength = std::snprintf(
        candidate.ssid.data(), candidate.ssid.size(), "Leshy-%02X%02X%02X",
        static_cast<unsigned>(deviceMac[3]),
        static_cast<unsigned>(deviceMac[4]),
        static_cast<unsigned>(deviceMac[5]));
    if (ssidLength <= 0 ||
        static_cast<std::size_t>(ssidLength) >= candidate.ssid.size()) {
        return false;
    }
    std::uint32_t accumulator = 0x6c657368U;
    for (std::size_t index = 0; index < entropy.size(); ++index) {
        accumulator ^= static_cast<std::uint32_t>(entropy[index])
            << ((index & 3U) * 8U);
        accumulator = accumulator * 1664525U + 1013904223U +
            static_cast<std::uint32_t>(deviceMac[index % deviceMac.size()]);
        if (index < kCompanionLocalPassphraseCapacity) {
            candidate.passphrase[index] = kCredentialAlphabet[
                (accumulator ^ (accumulator >> 16U)) %
                kCredentialAlphabetSize];
        }
    }
    candidate.passphrase[kCompanionLocalPassphraseCapacity] = '\0';
    if (!candidate.valid()) {
        candidate.clear();
        return false;
    }
    *output = candidate;
    candidate.clear();
    return true;
}

bool CompanionConnectivity::authorize(std::uint64_t nowUs,
                                      std::uint32_t generation) {
    if (authorized_ || nowUs == 0 || generation == 0) return false;
    authorized_ = true;
    generation_ = generation;
    startedUs_ = nowUs;
    lastActivityUs_ = nowUs;
    stopReason_ = CompanionLocalStopReason::None;
    return true;
}

bool CompanionConnectivity::recordActivity(std::uint64_t nowUs,
                                           std::uint32_t generation) {
    if (!authorized_ || generation == 0 || generation != generation_ ||
        nowUs < lastActivityUs_ || nowUs < startedUs_) {
        return false;
    }
    if (nowUs - startedUs_ >= kCompanionLocalMaximumLifetimeUs) {
        revoke(CompanionLocalStopReason::LifetimeTimeout);
        return false;
    }
    if (nowUs - lastActivityUs_ >= kCompanionLocalIdleTimeoutUs) {
        revoke(CompanionLocalStopReason::IdleTimeout);
        return false;
    }
    lastActivityUs_ = nowUs;
    return true;
}

bool CompanionConnectivity::service(std::uint64_t nowUs) {
    if (!authorized_) return false;
    if (nowUs < startedUs_ || nowUs < lastActivityUs_) {
        revoke(CompanionLocalStopReason::SafetyStop);
        return true;
    }
    if (nowUs - startedUs_ >= kCompanionLocalMaximumLifetimeUs) {
        revoke(CompanionLocalStopReason::LifetimeTimeout);
        return true;
    }
    if (nowUs - lastActivityUs_ >= kCompanionLocalIdleTimeoutUs) {
        revoke(CompanionLocalStopReason::IdleTimeout);
        return true;
    }
    return false;
}

void CompanionConnectivity::revoke(CompanionLocalStopReason reason) {
    authorized_ = false;
    generation_ = 0;
    startedUs_ = 0;
    lastActivityUs_ = 0;
    stopReason_ = reason == CompanionLocalStopReason::None
        ? CompanionLocalStopReason::User : reason;
}

}  // namespace leshy1::services::companion
