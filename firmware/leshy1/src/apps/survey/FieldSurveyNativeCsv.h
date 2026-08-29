#pragma once

#include <cstddef>
#include <cstdint>

#include "apps/survey/FieldSurveyCatalog.h"

namespace leshy1::apps::survey {

enum class FieldSurveyNativeStatus : std::uint8_t {
    Valid,
    InvalidArgument,
    BufferTooSmall,
};

const char* fieldSurveyNativeStatusName(FieldSurveyNativeStatus status);

struct FieldSurveyNativeResult final {
    FieldSurveyNativeStatus status = FieldSurveyNativeStatus::InvalidArgument;
    std::size_t bytes = 0;

    bool valid() const { return status == FieldSurveyNativeStatus::Valid; }
};

FieldSurveyNativeResult formatFieldSurveyNativeHeader(
    char* output, std::size_t capacity);
FieldSurveyNativeResult formatFieldSurveyNativeRow(
    const FieldSurveyRecord& record, char* output, std::size_t capacity);

}  // namespace leshy1::apps::survey
