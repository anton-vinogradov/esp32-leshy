#include "SubGhzRawCsv.h"

#include <cstdio>

namespace leshy1::apps::capture {
namespace {

SubGhzRawCsvResult result(char* output, std::size_t capacity, int written) {
    if (output == nullptr || capacity == 0 || written < 0 ||
        static_cast<std::size_t>(written) >= capacity) {
        if (output != nullptr && capacity != 0) output[0] = '\0';
        return {};
    }
    return {true, static_cast<std::size_t>(written)};
}

}  // namespace

SubGhzRawCsvResult formatSubGhzRawCsvHeader(char* output,
                                             std::size_t capacity) {
    return result(output, capacity,
                  std::snprintf(output, capacity,
                                "pulse_index,level,duration_us\r\n"));
}

SubGhzRawCsvResult formatSubGhzRawCsvRow(
    const domain::captures::SubGhzRawSource& source, std::size_t index,
    bool startLevel, char* output, std::size_t capacity) {
    domain::captures::SubGhzRawPulseView pulse;
    if (output == nullptr || capacity == 0 ||
        !source.pulseView(index, &pulse)) {
        if (output != nullptr && capacity != 0) output[0] = '\0';
        return {};
    }
    const bool level = (index & 1U) == 0U ? startLevel : !startLevel;
    return result(output, capacity,
                  std::snprintf(output, capacity, "%u,%u,%u\r\n",
                                static_cast<unsigned>(index),
                                level ? 1U : 0U,
                                static_cast<unsigned>(pulse.durationUs)));
}

}  // namespace leshy1::apps::capture
