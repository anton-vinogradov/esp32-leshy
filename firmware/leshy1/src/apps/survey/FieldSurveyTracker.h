#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "apps/survey/FieldSurveyCatalog.h"
#include "services/survey/SurveySession.h"

namespace leshy1::apps::survey {

enum class FieldSurveyVisitStatus : std::uint8_t {
    Empty,
    FirstVisit,
    Compared,
    Incomplete,
};

const char* fieldSurveyVisitStatusName(FieldSurveyVisitStatus status);

struct FieldSurveyCycleEvidence final {
    bool fieldVisit = false;
    bool scanFailed = false;
    bool stopRequested = false;
    std::uint8_t selectedSourceMask = 0;
    std::uint8_t attemptedSourceMask = 0;
    std::uint8_t unavailableSourceMask = 0;
};

// A field visit is one bounded snapshot, not a continuous monitor. Pause only
// after every selected source has either completed its first attempt or has
// been reported unavailable. Generic Wi-Fi/BLE monitoring never enables this
// policy and remains continuous.
bool shouldAutoPauseFieldVisit(const FieldSurveyCycleEvidence& evidence);

struct FieldSurveyVisitResult final {
    FieldSurveyVisitStatus status = FieldSurveyVisitStatus::Empty;
    FieldSurveyBuildStatus buildStatus =
        FieldSurveyBuildStatus::SessionNotStopped;
    std::uint16_t currentUnique = 0;
    std::uint16_t baselineUnique = 0;
    std::uint16_t seenAgain = 0;
    std::uint16_t newThisVisit = 0;
    std::uint16_t missingThisVisit = 0;
    std::uint16_t wifiAccessPoints = 0;
    std::uint16_t wifiStations = 0;
    std::uint16_t bleDevices = 0;

    bool complete() const {
        return status == FieldSurveyVisitStatus::FirstVisit ||
               status == FieldSurveyVisitStatus::Compared;
    }
};

// Product-facing state for a retained field visit. It keeps only identity and
// entity kind from the previous visit. The caller lends one terminal-only
// catalog scratch while loading/comparing; no 5.6 KiB catalog remains resident
// while Wi-Fi or NimBLE owns the no-PSRAM board's internal heap.
class FieldSurveyTracker final {
public:
    static constexpr const char* kSessionId = "field-visit-live";

    void reset();
    bool capturePrevious(const services::survey::SurveySession& session,
                         FieldSurveyCatalog& scratch);
    void clearPrevious();

    bool previousAvailable() const { return previousAvailable_; }
    bool comparePrevious() const {
        return previousAvailable_ && comparePrevious_;
    }
    void setComparePrevious(bool enabled) {
        comparePrevious_ = previousAvailable_ && enabled;
    }
    bool toggleComparePrevious();

    const FieldSurveyVisitResult& completeVisit(
        const services::survey::SurveySession& session,
        FieldSurveyCatalog& scratch);
    const FieldSurveyVisitResult& rejectVisit(
        FieldSurveyBuildStatus status = FieldSurveyBuildStatus::InputRejected);
    const FieldSurveyVisitResult& result() const { return result_; }

private:
    struct BaselineIdentity final {
        FieldSurveyEntityKind kind =
            FieldSurveyEntityKind::WifiAccessPoint;
        std::array<std::uint8_t,
                   domain::observations::Observation::kIdentityCapacity>
            identity{};
        std::uint8_t identityLength = 0;
    };

    bool baselineContains(const FieldSurveyRecord& record) const;
    bool currentContains(const FieldSurveyCatalog& current,
                         const BaselineIdentity& baseline) const;

    std::array<BaselineIdentity, FieldSurveyCatalog::kCapacity> previous_{};
    std::size_t previousSize_ = 0;
    bool previousAvailable_ = false;
    bool comparePrevious_ = false;
    FieldSurveyVisitResult result_{};
};

static_assert(sizeof(FieldSurveyTracker) <= 640U,
              "field survey retained state exceeded its foreground RAM budget");

}  // namespace leshy1::apps::survey
