#include "apps/spectrum/SpectrumViewport.h"

namespace leshy1::apps::spectrum {

const char* spectrumDisplayModeName(SpectrumDisplayMode mode) {
    switch (mode) {
        case SpectrumDisplayMode::Spectrum: return "spectrum";
        case SpectrumDisplayMode::Waterfall: return "waterfall";
    }
    return "unknown";
}

bool SpectrumViewport::reset(std::size_t bins) {
    if (bins == 0 || bins > kMaxBins) return false;
    history_.fill(0);
    mode_ = SpectrumDisplayMode::Spectrum;
    binCount_ = bins;
    rowsStored_ = 0;
    nextRow_ = 0;
    return true;
}

bool SpectrumViewport::push(const std::uint8_t* intensity,
                            std::size_t bins) {
    if (intensity == nullptr || bins == 0 || bins != binCount_) return false;
    const std::size_t offset = nextRow_ * kRowBytes;
    for (std::size_t column = 0; column < kDisplayColumns; ++column) {
        history_[offset + column] = resample(intensity, bins, column);
    }
    nextRow_ = (nextRow_ + 1U) % kHistoryRows;
    if (rowsStored_ < kHistoryRows) ++rowsStored_;
    return true;
}

bool SpectrumViewport::setMode(SpectrumDisplayMode mode) {
    if (mode_ == mode) return false;
    mode_ = mode;
    return true;
}

bool SpectrumViewport::previousMode() {
    return setMode(mode_ == SpectrumDisplayMode::Spectrum
                       ? SpectrumDisplayMode::Waterfall
                       : SpectrumDisplayMode::Spectrum);
}

bool SpectrumViewport::nextMode() { return previousMode(); }

std::uint8_t SpectrumViewport::resample(const std::uint8_t* intensity,
                                        std::size_t bins,
                                        std::size_t column) {
    if (intensity == nullptr || bins == 0 || bins > kMaxBins ||
        column >= kDisplayColumns) {
        return 0;
    }
    const std::size_t source = column * bins / kDisplayColumns;
    return intensity[source < bins ? source : bins - 1U];
}

std::size_t SpectrumViewport::latestRow() const {
    if (rowsStored_ == 0) return 0;
    return nextRow_ == 0 ? kHistoryRows - 1U : nextRow_ - 1U;
}

bool SpectrumViewport::rowValid(std::size_t row) const {
    if (row >= kHistoryRows || rowsStored_ == 0) return false;
    return rowsStored_ == kHistoryRows || row < rowsStored_;
}

std::uint8_t SpectrumViewport::intensity(std::size_t row,
                                         std::size_t column) const {
    if (!rowValid(row) || column >= kDisplayColumns) return 0;
    return history_[row * kRowBytes + column];
}

}  // namespace leshy1::apps::spectrum
