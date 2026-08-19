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
// Every completed receiver sweep stays in its physical one-pixel row slot.  The
// history preserves real receiver bins; expansion to TFT columns happens only
// while rendering and never invents intermediate measurements.
class SpectrumViewport final {
public:
    static constexpr std::size_t kMaxBins = 83;
    static constexpr std::size_t kDisplayColumns = 240;
    static constexpr std::size_t kHistoryRows = 224;
    static constexpr std::size_t kRowBytes = kMaxBins;
    static constexpr std::size_t kHistoryStorageBytes =
        kRowBytes * kHistoryRows;
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
    // Eight-bit source bins preserve all 256 intensity levels without the false
    // boundaries of the earlier four-bit storage.  A row reserves kMaxBins so
    // nRF24 (83) and CC1101 (64) share one fixed ring without heap allocation.
    std::array<std::uint8_t, kHistoryStorageBytes> history_{};
    SpectrumDisplayMode mode_ = SpectrumDisplayMode::Spectrum;
    std::size_t binCount_ = 0;
    std::size_t rowsStored_ = 0;
    std::size_t nextRow_ = 0;
};

}  // namespace leshy1::apps::spectrum
