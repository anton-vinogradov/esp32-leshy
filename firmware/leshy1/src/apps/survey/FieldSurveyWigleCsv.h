#pragma once

#include <cstddef>
#include <cstdint>

#include "apps/survey/FieldSurveyCatalog.h"

namespace leshy1::apps::survey {

enum class FieldSurveyWigleStatus : std::uint8_t {
    Valid,
    InvalidArgument,
    BufferTooSmall,
    InvalidTimestamp,
    InvalidLocation,
    UnsupportedEntity,
};

const char* fieldSurveyWigleStatusName(FieldSurveyWigleStatus status);

enum class FieldSurveyWigleReadiness : std::uint8_t {
    Located,
    Unlocated,
    UntimedLocated,
    UntimedUnlocated,
};

const char* fieldSurveyWigleReadinessName(
    FieldSurveyWigleReadiness readiness);

struct FieldSurveyLocation final {
    bool present = false;
    std::int32_t latitudeE7 = 0;
    std::int32_t longitudeE7 = 0;
    std::int32_t altitudeCentimeters = 0;
    std::uint32_t accuracyCentimeters = 0;
};

struct FieldSurveyWigleContext final {
    // Empty means that no trusted UTC source is available. The export remains
    // a truthful local WiGLE-schema artifact but is not upload-ready.
    const char* firstSeenUtc = nullptr;
    FieldSurveyLocation location{};
};

struct FieldSurveyWigleResult final {
    FieldSurveyWigleStatus status = FieldSurveyWigleStatus::InvalidArgument;
    FieldSurveyWigleReadiness readiness =
        FieldSurveyWigleReadiness::UntimedUnlocated;
    std::size_t bytes = 0;
    bool uploadReady = false;

    bool valid() const { return status == FieldSurveyWigleStatus::Valid; }
};

FieldSurveyWigleResult formatFieldSurveyWigleMetadata(
    const char* firmwareVersion, char* output, std::size_t capacity);
FieldSurveyWigleResult formatFieldSurveyWigleColumns(
    char* output, std::size_t capacity);
FieldSurveyWigleResult formatFieldSurveyWigleRow(
    const FieldSurveyRecord& record,
    const FieldSurveyWigleContext& context,
    char* output, std::size_t capacity);

}  // namespace leshy1::apps::survey
