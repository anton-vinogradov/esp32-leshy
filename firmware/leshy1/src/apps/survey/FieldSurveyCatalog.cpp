#include "apps/survey/FieldSurveyCatalog.h"

#include <cstring>

namespace leshy1::apps::survey {
namespace {

using domain::observations::Observation;
using domain::observations::RadioKind;

bool validKind(const Observation& observation, FieldSurveyEntityKind kind) {
    switch (observation.radio) {
        case RadioKind::Wifi:
            return kind == FieldSurveyEntityKind::WifiAccessPoint ||
                   kind == FieldSurveyEntityKind::WifiStation;
        case RadioKind::Ble:
            return kind == FieldSurveyEntityKind::BleDevice;
    }
    return false;
}

FieldSurveyEntityKind defaultKind(const Observation& observation) {
    if (observation.radio == RadioKind::Ble) {
        return FieldSurveyEntityKind::BleDevice;
    }
    return observation.wifiKind ==
            domain::observations::WifiObservationKind::Station
        ? FieldSurveyEntityKind::WifiStation
        : FieldSurveyEntityKind::WifiAccessPoint;
}

void copyLabel(const Observation& observation, FieldSurveyRecord* record) {
    if (record == nullptr || observation.labelLength == 0U) return;
    record->label.fill('\0');
    std::memcpy(record->label.data(), observation.label.data(),
                observation.labelLength);
    record->labelLength = observation.labelLength;
}

void copyStrongestFacts(const Observation& observation,
                        FieldSurveyRecord* record) {
    if (record == nullptr) return;
    record->strongestFrequencyKhz = observation.frequencyKhz;
    record->strongestChannel = observation.channel;
    record->strongestRssiDbm = observation.rssiDbm;
    if (observation.radio == RadioKind::Wifi) {
        record->wifiFactsPresent = observation.wifiNetwork.present;
        record->wifiAuthentication = observation.wifiNetwork.authentication;
        record->wifiPairwiseCipher = observation.wifiNetwork.pairwiseCipher;
        record->wifiGroupCipher = observation.wifiNetwork.groupCipher;
    } else {
        record->bleCompanyKnown =
            observation.bleAdvertisement.present &&
            observation.bleAdvertisement.companyKnown;
        record->bleCompanyId = observation.bleAdvertisement.companyId;
    }
}

}  // namespace

const char* fieldSurveyEntityKindName(FieldSurveyEntityKind kind) {
    switch (kind) {
        case FieldSurveyEntityKind::WifiAccessPoint:
            return "wifi_access_point";
        case FieldSurveyEntityKind::WifiStation: return "wifi_station";
        case FieldSurveyEntityKind::BleDevice: return "ble_device";
    }
    return "invalid";
}

const char* fieldSurveyIngestStatusName(FieldSurveyIngestStatus status) {
    switch (status) {
        case FieldSurveyIngestStatus::Added: return "added";
        case FieldSurveyIngestStatus::Updated: return "updated";
        case FieldSurveyIngestStatus::InvalidObservation:
            return "invalid_observation";
        case FieldSurveyIngestStatus::OutOfOrder: return "out_of_order";
        case FieldSurveyIngestStatus::CapacityExceeded:
            return "capacity_exceeded";
    }
    return "invalid_observation";
}

const char* fieldSurveyBuildStatusName(FieldSurveyBuildStatus status) {
    switch (status) {
        case FieldSurveyBuildStatus::Complete: return "complete";
        case FieldSurveyBuildStatus::SessionNotStopped:
            return "session_not_stopped";
        case FieldSurveyBuildStatus::InputRejected: return "input_rejected";
        case FieldSurveyBuildStatus::CapacityExceeded:
            return "capacity_exceeded";
    }
    return "input_rejected";
}

const char* fieldSurveyComparisonStatusName(
    FieldSurveyComparisonStatus status) {
    switch (status) {
        case FieldSurveyComparisonStatus::Valid: return "valid";
        case FieldSurveyComparisonStatus::IncompleteCatalog:
            return "incomplete_catalog";
    }
    return "incomplete_catalog";
}

void FieldSurveyCatalog::reset() {
    records_.fill({});
    size_ = 0;
    complete_ = true;
    rejectedInvalid_ = 0;
    rejectedOutOfOrder_ = 0;
    droppedCapacity_ = 0;
}

std::size_t FieldSurveyCatalog::indexOf(
    FieldSurveyEntityKind kind, const std::uint8_t* identity,
    std::size_t identityLength) const {
    if (identity == nullptr || identityLength !=
            Observation::kIdentityCapacity) {
        return size_;
    }
    for (std::size_t index = 0; index < size_; ++index) {
        const FieldSurveyRecord& record = records_[index];
        if (record.kind == kind && record.identityLength == identityLength &&
            std::memcmp(record.identity.data(), identity,
                        identityLength) == 0) {
            return index;
        }
    }
    return size_;
}

FieldSurveyIngestStatus FieldSurveyCatalog::ingest(
    const Observation& observation, FieldSurveyEntityKind kind) {
    if (!validKind(observation, kind) || observation.monotonicUs == 0U ||
        observation.identityLength != Observation::kIdentityCapacity ||
        observation.labelLength > Observation::kLabelCapacity) {
        ++rejectedInvalid_;
        complete_ = false;
        return FieldSurveyIngestStatus::InvalidObservation;
    }
    const std::size_t existing = indexOf(
        kind, observation.identity.data(), observation.identityLength);
    if (existing < size_) {
        FieldSurveyRecord& record = records_[existing];
        if (observation.monotonicUs < record.lastSeenUs) {
            ++rejectedOutOfOrder_;
            complete_ = false;
            return FieldSurveyIngestStatus::OutOfOrder;
        }
        record.lastSeenUs = observation.monotonicUs;
        record.latestRssiDbm = observation.rssiDbm;
        ++record.observations;
        if (observation.rssiDbm > record.strongestRssiDbm) {
            copyStrongestFacts(observation, &record);
            copyLabel(observation, &record);
        } else if (record.labelLength == 0U &&
                   observation.labelLength != 0U) {
            copyLabel(observation, &record);
        }
        return FieldSurveyIngestStatus::Updated;
    }
    if (size_ >= records_.size()) {
        ++droppedCapacity_;
        complete_ = false;
        return FieldSurveyIngestStatus::CapacityExceeded;
    }
    FieldSurveyRecord& record = records_[size_++];
    record = {};
    record.kind = kind;
    record.identity = observation.identity;
    record.identityLength = observation.identityLength;
    record.firstSeenUs = observation.monotonicUs;
    record.lastSeenUs = observation.monotonicUs;
    record.observations = 1U;
    record.latestRssiDbm = observation.rssiDbm;
    copyStrongestFacts(observation, &record);
    copyLabel(observation, &record);
    return FieldSurveyIngestStatus::Added;
}

FieldSurveyBuildStatus FieldSurveyCatalog::build(
    const services::survey::SurveySession& session) {
    reset();
    if (session.state() != services::survey::SessionState::Stopped) {
        complete_ = false;
        return FieldSurveyBuildStatus::SessionNotStopped;
    }
    if (session.dropped() != 0U) {
        droppedCapacity_ = session.dropped();
        complete_ = false;
    }
    for (std::size_t index = 0; index < session.size(); ++index) {
        const Observation* observation = session.get(index);
        if (observation == nullptr) {
            ++rejectedInvalid_;
            complete_ = false;
            continue;
        }
        (void)ingest(*observation, defaultKind(*observation));
    }
    if (droppedCapacity_ != 0U) {
        return FieldSurveyBuildStatus::CapacityExceeded;
    }
    if (rejectedInvalid_ != 0U || rejectedOutOfOrder_ != 0U) {
        return FieldSurveyBuildStatus::InputRejected;
    }
    return FieldSurveyBuildStatus::Complete;
}

const FieldSurveyRecord* FieldSurveyCatalog::get(std::size_t index) const {
    return index < size_ ? &records_[index] : nullptr;
}

FieldSurveyComparison FieldSurveyCatalog::compare(
    const FieldSurveyCatalog& baseline) const {
    FieldSurveyComparison result;
    result.currentUnique = static_cast<std::uint16_t>(size_);
    result.baselineUnique = static_cast<std::uint16_t>(baseline.size_);
    if (!complete_ || !baseline.complete_) return result;
    result.status = FieldSurveyComparisonStatus::Valid;
    for (std::size_t index = 0; index < size_; ++index) {
        const FieldSurveyRecord& current = records_[index];
        switch (current.kind) {
            case FieldSurveyEntityKind::WifiAccessPoint:
                ++result.wifiAccessPoints;
                break;
            case FieldSurveyEntityKind::WifiStation:
                ++result.wifiStations;
                break;
            case FieldSurveyEntityKind::BleDevice:
                ++result.bleDevices;
                break;
        }
        if (baseline.indexOf(current.kind, current.identity.data(),
                             current.identityLength) < baseline.size_) {
            ++result.seenAgain;
        } else {
            ++result.newThisVisit;
        }
    }
    for (std::size_t index = 0; index < baseline.size_; ++index) {
        const FieldSurveyRecord& previous = baseline.records_[index];
        if (indexOf(previous.kind, previous.identity.data(),
                    previous.identityLength) >= size_) {
            ++result.missingThisVisit;
        }
    }
    return result;
}

}  // namespace leshy1::apps::survey
