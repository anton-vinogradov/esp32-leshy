#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"
#include "services/survey/SurveySession.h"

namespace leshy1::apps::survey {

enum class FieldSurveyEntityKind : std::uint8_t {
    WifiAccessPoint,
    WifiStation,
    BleDevice,
};

const char* fieldSurveyEntityKindName(FieldSurveyEntityKind kind);

enum class FieldSurveyIngestStatus : std::uint8_t {
    Added,
    Updated,
    InvalidObservation,
    OutOfOrder,
    CapacityExceeded,
};

const char* fieldSurveyIngestStatusName(FieldSurveyIngestStatus status);

enum class FieldSurveyBuildStatus : std::uint8_t {
    Complete,
    SessionNotStopped,
    InputRejected,
    CapacityExceeded,
};

const char* fieldSurveyBuildStatusName(FieldSurveyBuildStatus status);

struct FieldSurveyRecord final {
    FieldSurveyEntityKind kind = FieldSurveyEntityKind::WifiAccessPoint;
    std::array<std::uint8_t,
               domain::observations::Observation::kIdentityCapacity> identity{};
    std::uint8_t identityLength = 0;
    std::array<char, domain::observations::Observation::kLabelCapacity + 1U>
        label{};
    std::uint8_t labelLength = 0;
    std::uint64_t firstSeenUs = 0;
    std::uint64_t lastSeenUs = 0;
    std::uint32_t observations = 0;
    std::uint32_t strongestFrequencyKhz = 0;
    std::uint16_t strongestChannel = 0;
    std::int16_t strongestRssiDbm = 0;
    std::int16_t latestRssiDbm = 0;
    bool wifiFactsPresent = false;
    domain::observations::WifiAuthentication wifiAuthentication =
        domain::observations::WifiAuthentication::Unknown;
    domain::observations::WifiCipher wifiPairwiseCipher =
        domain::observations::WifiCipher::Unknown;
    domain::observations::WifiCipher wifiGroupCipher =
        domain::observations::WifiCipher::Unknown;
    bool bleCompanyKnown = false;
    std::uint16_t bleCompanyId = 0;
};

enum class FieldSurveyComparisonStatus : std::uint8_t {
    Valid,
    IncompleteCatalog,
};

const char* fieldSurveyComparisonStatusName(
    FieldSurveyComparisonStatus status);

struct FieldSurveyComparison final {
    FieldSurveyComparisonStatus status =
        FieldSurveyComparisonStatus::IncompleteCatalog;
    std::uint16_t currentUnique = 0;
    std::uint16_t baselineUnique = 0;
    std::uint16_t seenAgain = 0;
    std::uint16_t newThisVisit = 0;
    std::uint16_t missingThisVisit = 0;
    std::uint16_t wifiAccessPoints = 0;
    std::uint16_t wifiStations = 0;
    std::uint16_t bleDevices = 0;
};

class FieldSurveyCatalog final {
public:
    static constexpr std::size_t kCapacity =
        services::survey::SurveySession::kObservationCapacity;

    void reset();
    FieldSurveyIngestStatus ingest(
        const domain::observations::Observation& observation,
        FieldSurveyEntityKind kind);
    FieldSurveyBuildStatus build(
        const services::survey::SurveySession& session);

    std::size_t size() const { return size_; }
    bool complete() const { return complete_; }
    std::uint32_t rejectedInvalid() const { return rejectedInvalid_; }
    std::uint32_t rejectedOutOfOrder() const { return rejectedOutOfOrder_; }
    std::uint32_t droppedCapacity() const { return droppedCapacity_; }
    const FieldSurveyRecord* get(std::size_t index) const;
    std::size_t indexOf(FieldSurveyEntityKind kind,
                        const std::uint8_t* identity,
                        std::size_t identityLength) const;
    FieldSurveyComparison compare(
        const FieldSurveyCatalog& baseline) const;

private:
    std::array<FieldSurveyRecord, kCapacity> records_{};
    std::size_t size_ = 0;
    bool complete_ = true;
    std::uint32_t rejectedInvalid_ = 0;
    std::uint32_t rejectedOutOfOrder_ = 0;
    std::uint32_t droppedCapacity_ = 0;
};

static_assert(sizeof(FieldSurveyRecord) <= 96U,
              "field survey record exceeded its bounded compact form");
static_assert(sizeof(FieldSurveyCatalog) <= 7168U,
              "field survey catalog exceeded its foreground workspace budget");

}  // namespace leshy1::apps::survey
