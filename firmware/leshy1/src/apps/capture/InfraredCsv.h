#pragma once

#include <cstddef>

#include "domain/captures/InfraredRaw.h"

namespace leshy1::apps::capture {

struct InfraredCsvResult final {
    bool valid = false;
    std::size_t bytes = 0;
};

InfraredCsvResult formatInfraredCsvHeader(char* output,
                                          std::size_t capacity);
InfraredCsvResult formatInfraredCsvRow(
    const domain::captures::InfraredRawSource& source, std::size_t index,
    bool startLevel, char* output, std::size_t capacity);

}  // namespace leshy1::apps::capture
