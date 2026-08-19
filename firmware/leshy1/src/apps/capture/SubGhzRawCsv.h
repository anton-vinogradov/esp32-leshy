#pragma once

#include <cstddef>

#include "domain/captures/SubGhzRaw.h"

namespace leshy1::apps::capture {

struct SubGhzRawCsvResult final {
    bool valid = false;
    std::size_t bytes = 0;
};

SubGhzRawCsvResult formatSubGhzRawCsvHeader(char* output,
                                             std::size_t capacity);
SubGhzRawCsvResult formatSubGhzRawCsvRow(
    const domain::captures::SubGhzRawSource& source, std::size_t index,
    bool startLevel, char* output, std::size_t capacity);

}  // namespace leshy1::apps::capture
