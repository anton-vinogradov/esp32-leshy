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
// Rows stay in their physical ring slots and every stored column maps one-to-one
// to a physical TFT pixel, so appending never stretches or redraws old samples.
class SpectrumViewport final {
public:
    static constexpr std::size_t kMaxBins = 83;
    static constexpr std::size_t kDisplayColumns = 240;
    static constexpr std::size_t kHistoryRows = 224;
    static constexpr std::size_t kRowBytes = kDisplayColumns;
    static constexpr std::size_t kHistoryStorageBytes =
        kRowBytes * kHistoryRows;
    static constexpr std::uint64_t kWaterfallFillUs = 3000000ULL;
    static constexpr std::uint64_t kWaterfallRowPeriodUs =
        kWaterfallFillUs / kHistoryRows;

    bool reset(std::size_t bins);
    bool push(const std::uint8_t* intensity, std::size_t bins);
    bool setMode(SpectrumDisplayMode mode);
    bool previousMode();
    bool nextMode();
    static std::uint8_t resample(const std::uint8_t* intensity,
                                 std::size_t bins,
                                 std::size_t column);

    SpectrumDisplayMode mode() const { return mode_; }
    std::size_t binCount() const { return binCount_; }
    std::size_t rowsStored() const { return rowsStored_; }
    std::size_t nextRow() const { return nextRow_; }
    std::size_t latestRow() const;
    bool rowValid(std::size_t row) const;
    std::uint8_t intensity(std::size_t row, std::size_t column) const;

private:
    // The retained history is the exact 240 x 224, eight-bit display raster.
    // Keeping all 256 levels avoids the false block boundaries caused by the
    // earlier four-bit storage while remaining allocation-free.
    std::array<std::uint8_t, kHistoryStorageBytes> history_{};
    SpectrumDisplayMode mode_ = SpectrumDisplayMode::Spectrum;
    std::size_t binCount_ = 0;
    std::size_t rowsStored_ = 0;
    std::size_t nextRow_ = 0;
};

}  // namespace leshy1::apps::spectrum
