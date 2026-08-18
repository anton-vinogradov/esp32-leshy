#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"
#include "services/survey/SurveySession.h"

namespace leshy1::apps::survey {

enum class SurveyView : std::uint8_t {
    List,
    Detail,
    Filter,
};

const char* surveyViewName(SurveyView view);

enum class SurveyFilter : std::uint8_t {
    All,
    Wifi,
    Ble,
};

const char* surveyFilterName(SurveyFilter filter);

struct ObservationHistory final {
    static constexpr std::size_t kSampleCapacity = 12;

    bool valid = false;
    std::uint16_t sampleCount = 0;
    std::uint8_t retainedSamples = 0;
    std::int16_t minimumRssiDbm = 0;
    std::int16_t maximumRssiDbm = 0;
    std::int16_t latestRssiDbm = 0;
    std::array<std::int16_t, kSampleCapacity> samples{};
};

class SurveyController final {
public:
    explicit SurveyController(services::survey::SurveySession& session) : session_(session) {}

    void reset();
    services::survey::SessionStatus start(const char* sessionId, std::uint64_t monotonicUs);
    services::survey::SessionStatus publish(
        const domain::observations::Observation& observation);
    services::survey::SessionStatus stop(std::uint64_t monotonicUs);

    bool next();
    bool previous();
    bool openSelected();
    bool activateFilter();
    bool back();

    SurveyView view() const { return view_; }
    std::size_t selection() const { return selection_; }
    bool filterFocused() const { return filterFocused_; }
    SurveyFilter filter() const { return filter_; }
    SurveyFilter draftFilter() const { return draftFilter_; }
    std::size_t visibleSize() const;
    std::size_t filterCount(SurveyFilter filter) const;
    const domain::observations::Observation* visibleAt(std::size_t index) const;
    const domain::observations::Observation* selected() const;
    ObservationHistory selectedHistory() const;
    const services::survey::SurveySession& session() const { return session_; }

private:
    bool matchesFilter(const domain::observations::Observation& observation,
                       SurveyFilter filter) const;

    services::survey::SurveySession& session_;
    SurveyView view_ = SurveyView::List;
    std::size_t selection_ = 0;
    bool filterFocused_ = false;
    SurveyFilter filter_ = SurveyFilter::All;
    SurveyFilter draftFilter_ = SurveyFilter::All;
};

}  // namespace leshy1::apps::survey
