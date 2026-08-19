#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace leshy1::apps::spectrum {

enum class SpectrumDisplayMode : std::uint8_t {
    Spectrum,
    Waterfall,
};

const char* spectrumDisplayModeName(SpectrumDisplayMode mode);

// A bounded, allocation-free history shared by mutually exclusive RF views.
// Rows stay in their physical ring slots so the TFT can append a waterfall
// scanline without moving or redrawing older pixels.
class SpectrumViewport final {
public:
    static constexpr std::size_t kMaxBins = 83;
    static constexpr std::size_t kHistoryRows = 224;
    static constexpr std::size_t kPackedRowBytes = (kMaxBins + 1U) / 2U;
    static constexpr std::size_t kHistoryStorageBytes =
        kPackedRowBytes * kHistoryRows;
    static constexpr std::uint64_t kWaterfallFillUs = 3000000ULL;
    static constexpr std::uint64_t kWaterfallRowPeriodUs =
        kWaterfallFillUs / kHistoryRows;

    bool reset(std::size_t bins);
    bool push(const std::uint8_t* intensity, std::size_t bins);
    bool setMode(SpectrumDisplayMode mode);
    bool previousMode();
    bool nextMode();

    SpectrumDisplayMode mode() const { return mode_; }
    std::size_t binCount() const { return binCount_; }
    std::size_t rowsStored() const { return rowsStored_; }
    std::size_t nextRow() const { return nextRow_; }
    std::size_t latestRow() const;
    bool rowValid(std::size_t row) const;
    std::uint8_t intensity(std::size_t row, std::size_t bin) const;

private:
    // Four-bit intensity is sufficient for the 16-step display palette and doubles
    // vertical history without doubling static RAM.
    std::array<std::uint8_t, kHistoryStorageBytes> history_{};
    SpectrumDisplayMode mode_ = SpectrumDisplayMode::Spectrum;
    std::size_t binCount_ = 0;
    std::size_t rowsStored_ = 0;
    std::size_t nextRow_ = 0;
};

}  // namespace leshy1::apps::spectrum
