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
    const std::size_t offset = nextRow_ * kPackedRowBytes;
    for (std::size_t byte = 0; byte < kPackedRowBytes; ++byte) {
        history_[offset + byte] = 0;
    }
    for (std::size_t bin = 0; bin < bins; ++bin) {
        const std::uint8_t packed =
            static_cast<std::uint8_t>(intensity[bin] >> 4U);
        std::uint8_t& destination = history_[offset + bin / 2U];
        destination = static_cast<std::uint8_t>(
            destination | (bin % 2U == 0 ? packed : packed << 4U));
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

std::size_t SpectrumViewport::latestRow() const {
    if (rowsStored_ == 0) return 0;
    return nextRow_ == 0 ? kHistoryRows - 1U : nextRow_ - 1U;
}

bool SpectrumViewport::rowValid(std::size_t row) const {
    if (row >= kHistoryRows || rowsStored_ == 0) return false;
    return rowsStored_ == kHistoryRows || row < rowsStored_;
}

std::uint8_t SpectrumViewport::intensity(std::size_t row,
                                         std::size_t bin) const {
    if (!rowValid(row) || bin >= binCount_) return 0;
    const std::uint8_t packed =
        history_[row * kPackedRowBytes + bin / 2U];
    const std::uint8_t nibble = static_cast<std::uint8_t>(
        bin % 2U == 0 ? packed & 0x0FU : packed >> 4U);
    return static_cast<std::uint8_t>(nibble * 17U);
}

}  // namespace leshy1::apps::spectrum
