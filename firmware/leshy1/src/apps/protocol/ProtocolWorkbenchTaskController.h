#pragma once

#include <cstddef>
#include <cstdint>

namespace leshy1::apps::protocol {

// User-facing navigation deliberately starts from goals, not protocol jargon.
// The annotation editor remains a child workflow and owns its finer-grained
// range/kind state independently.
enum class ProtocolWorkbenchTaskView : std::uint8_t {
    Tasks,
    Waveform,
    Explain,
    Annotate,
    Comparison,
    Decode,
};

const char* protocolWorkbenchTaskViewName(ProtocolWorkbenchTaskView view);

enum class ProtocolWorkbenchTaskActivation : std::uint8_t {
    None,
    Changed,
    CompareRequested,
    DecodeRequested,
};

class ProtocolWorkbenchTaskController final {
public:
    static constexpr std::size_t kTaskCount = 3U;
    static constexpr std::size_t kExplainTaskCount = 2U;

    void enter();
    bool previous();
    bool next();
    ProtocolWorkbenchTaskActivation activate();
    bool back();

    void noteComparison(std::size_t regionCount);
    void noteDecode(std::size_t fieldCount);

    ProtocolWorkbenchTaskView view() const { return view_; }
    std::size_t selection() const { return selection_; }
    std::size_t resultCount() const { return resultCount_; }

private:
    std::size_t navigationCount() const;

    ProtocolWorkbenchTaskView view_ = ProtocolWorkbenchTaskView::Tasks;
    std::size_t selection_ = 0U;
    std::size_t resultCount_ = 0U;
};

}  // namespace leshy1::apps::protocol
