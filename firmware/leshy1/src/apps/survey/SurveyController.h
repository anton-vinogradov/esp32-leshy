#pragma once

#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"
#include "services/survey/SurveySession.h"

namespace leshy1::apps::survey {

enum class SurveyView : std::uint8_t {
    List,
    Detail,
};

class SurveyController final {
public:
    explicit SurveyController(services::survey::SurveySession& session) : session_(session) {}

    services::survey::SessionStatus start(const char* sessionId, std::uint64_t monotonicUs);
    services::survey::SessionStatus publish(
        const domain::observations::Observation& observation);
    services::survey::SessionStatus stop(std::uint64_t monotonicUs);

    bool next();
    bool previous();
    bool openSelected();
    bool back();

    SurveyView view() const { return view_; }
    std::size_t selection() const { return selection_; }
    const domain::observations::Observation* selected() const;
    const services::survey::SurveySession& session() const { return session_; }

private:
    services::survey::SurveySession& session_;
    SurveyView view_ = SurveyView::List;
    std::size_t selection_ = 0;
};

}  // namespace leshy1::apps::survey
