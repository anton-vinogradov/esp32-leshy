#include "TargetRadar.h"

#include <algorithm>
#include <cstring>
#include <limits>

namespace leshy1::apps::targets {
namespace {

constexpr std::size_t kNoIdentity =
    domain::targets::TargetRecord::kIdentityCapacity;

domain::targets::TargetIdentity identityForObservation(
        const domain::observations::Observation& observation) {
    domain::targets::TargetIdentity identity{};
    identity.value = observation.identity;
    identity.length = observation.identityLength;
    if (observation.radio == domain::observations::RadioKind::Ble) {
        identity.kind = domain::targets::TargetIdentityKind::BleAddress;
        identity.discriminator = observation.bleAdvertisement.addressType;
    } else {
        identity.kind = observation.wifiKind ==
                domain::observations::WifiObservationKind::Station
            ? domain::targets::TargetIdentityKind::WifiStation
            : domain::targets::TargetIdentityKind::WifiBssid;
        identity.discriminator = 0;
    }
    return identity;
}

bool observationValid(
        const domain::observations::Observation& observation) {
    if (observation.monotonicUs == 0 ||
        observation.identityLength !=
            domain::targets::TargetIdentity::kValueCapacity) {
        return false;
    }
    if (observation.radio == domain::observations::RadioKind::Wifi) {
        return observation.channel >= 1U && observation.channel <= 14U;
    }
    return observation.radio == domain::observations::RadioKind::Ble &&
        observation.bleAdvertisement.present &&
        observation.bleAdvertisement.addressType <= 3U;
}

}  // namespace

const char* targetRadarStatusName(TargetRadarStatus status) {
    switch (status) {
        case TargetRadarStatus::Idle: return "idle";
        case TargetRadarStatus::Waiting: return "waiting";
        case TargetRadarStatus::Tracking: return "tracking";
        case TargetRadarStatus::Partial: return "partial";
        case TargetRadarStatus::SourceLost: return "source_lost";
        case TargetRadarStatus::Stopped: return "stopped";
        case TargetRadarStatus::Failed: return "failed";
    }
    return "failed";
}

const char* targetRadarIngestStatusName(TargetRadarIngestStatus status) {
    switch (status) {
        case TargetRadarIngestStatus::InvalidArgument:
            return "invalid_argument";
        case TargetRadarIngestStatus::Unmatched: return "unmatched";
        case TargetRadarIngestStatus::Stale: return "stale";
        case TargetRadarIngestStatus::Matched: return "matched";
    }
    return "invalid_argument";
}

bool TargetRadar::begin(const domain::targets::TargetRecord& target,
                        bool wifiStationSupported) {
    reset();
    if (!domain::targets::targetIdValid(target.id) ||
        target.identityCount == 0U ||
        target.identityCount > target.identities.size()) {
        return false;
    }
    snapshot_.wifiStationSupported = wifiStationSupported;
    snapshot_.identityCount = target.identityCount;
    for (std::size_t index = 0; index < target.identityCount; ++index) {
        const auto& identity = target.identities[index];
        if (!domain::targets::targetIdentityValid(identity)) {
            reset();
            return false;
        }
        auto& signal = snapshot_.signals[index];
        signal.identity = identity;
        signal.radio = identity.kind ==
                domain::targets::TargetIdentityKind::BleAddress
            ? domain::observations::RadioKind::Ble
            : domain::observations::RadioKind::Wifi;
        signal.supported = identity.kind !=
                domain::targets::TargetIdentityKind::WifiStation ||
            wifiStationSupported;
        if (signal.supported) ++snapshot_.supportedIdentityCount;
    }
    if (snapshot_.supportedIdentityCount == 0U) {
        snapshot_.status = TargetRadarStatus::SourceLost;
    } else if (snapshot_.supportedIdentityCount < snapshot_.identityCount) {
        snapshot_.status = TargetRadarStatus::Partial;
    } else {
        snapshot_.status = TargetRadarStatus::Waiting;
    }
    snapshot_.revision = 1U;
    return true;
}

std::size_t TargetRadar::findIdentity(
        const domain::observations::Observation& observation) const {
    const auto identity = identityForObservation(observation);
    if (!domain::targets::targetIdentityValid(identity)) return kNoIdentity;
    for (std::size_t index = 0; index < snapshot_.identityCount; ++index) {
        if (snapshot_.signals[index].supported &&
            domain::targets::targetIdentityEqual(
                snapshot_.signals[index].identity, identity)) {
            return index;
        }
    }
    return kNoIdentity;
}

TargetRadarIngestStatus TargetRadar::ingest(
        const domain::observations::Observation& observation) {
    if ((snapshot_.status != TargetRadarStatus::Waiting &&
         snapshot_.status != TargetRadarStatus::Tracking &&
         snapshot_.status != TargetRadarStatus::Partial) ||
        !observationValid(observation)) {
        return TargetRadarIngestStatus::InvalidArgument;
    }
    const std::size_t index = findIdentity(observation);
    if (index == kNoIdentity) {
        ++snapshot_.unmatched;
        return TargetRadarIngestStatus::Unmatched;
    }
    auto& signal = snapshot_.signals[index];
    if (signal.lastSeenUs != 0U &&
        observation.monotonicUs <= signal.lastSeenUs) {
        ++snapshot_.stale;
        return TargetRadarIngestStatus::Stale;
    }
    if (signal.samples == 0U) {
        signal.firstSeenUs = observation.monotonicUs;
        signal.minimumRssiDbm = observation.rssiDbm;
        signal.maximumRssiDbm = observation.rssiDbm;
        signal.previousRssiDbm = observation.rssiDbm;
    } else {
        signal.previousRssiDbm = signal.rssiDbm;
        signal.minimumRssiDbm = std::min(signal.minimumRssiDbm,
                                         observation.rssiDbm);
        signal.maximumRssiDbm = std::max(signal.maximumRssiDbm,
                                         observation.rssiDbm);
    }
    signal.rssiDbm = observation.rssiDbm;
    signal.trendDb = static_cast<std::int16_t>(
        signal.rssiDbm - signal.previousRssiDbm);
    signal.channel = observation.radio ==
            domain::observations::RadioKind::Wifi
        ? observation.channel : 0U;
    signal.lastSeenUs = observation.monotonicUs;
    if (signal.samples != std::numeric_limits<std::uint32_t>::max()) {
        ++signal.samples;
    }
    if (snapshot_.samples != std::numeric_limits<std::uint32_t>::max()) {
        ++snapshot_.samples;
    }
    std::uint32_t& sourceSamples = observation.radio ==
            domain::observations::RadioKind::Wifi
        ? snapshot_.wifiSamples : snapshot_.bleSamples;
    if (sourceSamples != std::numeric_limits<std::uint32_t>::max()) {
        ++sourceSamples;
    }
    snapshot_.matchedIdentityIndex = static_cast<std::uint8_t>(index);
    snapshot_.status = snapshot_.supportedIdentityCount <
            snapshot_.identityCount
        ? TargetRadarStatus::Partial : TargetRadarStatus::Tracking;
    ++snapshot_.revision;
    return TargetRadarIngestStatus::Matched;
}

void TargetRadar::setTerminal(TargetRadarStatus status) {
    if (snapshot_.status == TargetRadarStatus::Idle) return;
    snapshot_.status = status;
    ++snapshot_.revision;
}

void TargetRadar::sourceLost() { setTerminal(TargetRadarStatus::SourceLost); }

void TargetRadar::stop() { setTerminal(TargetRadarStatus::Stopped); }

void TargetRadar::fail() { setTerminal(TargetRadarStatus::Failed); }

void TargetRadar::reset() { snapshot_ = {}; }

}  // namespace leshy1::apps::targets
