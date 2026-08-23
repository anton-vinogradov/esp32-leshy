#include "apps/spectrum/Cc1101SignalFinder.h"

#include <limits>

namespace leshy1::apps::spectrum {
namespace {

struct FinderWindow final {
    std::uint32_t firstKHz;
    std::uint32_t lastKHz;
};

constexpr FinderWindow kWindows[] = {
    {300000U, 348000U},
    {387000U, 464000U},
    {779000U, 928000U},
};
constexpr std::uint8_t kHoldDecayDb = 3;

bool crystalSpurFrequency(std::uint32_t frequencyKHz) {
    constexpr std::uint32_t crystalKHz[] = {26000U, 40000U};
    for (const std::uint32_t crystal : crystalKHz) {
        const std::uint32_t harmonic =
            (frequencyKHz + crystal / 2U) / crystal * crystal;
        const std::uint32_t distance = frequencyKHz > harmonic
            ? frequencyKHz - harmonic : harmonic - frequencyKHz;
        if (distance <= 500U) return true;
    }
    return false;
}

constexpr std::size_t windowBins(const FinderWindow& window) {
    return static_cast<std::size_t>(
        (window.lastKHz - window.firstKHz) /
            Cc1101SignalFinder::kStepKHz + 1U);
}

static_assert(windowBins(kWindows[0]) + windowBins(kWindows[1]) +
                  windowBins(kWindows[2]) ==
              Cc1101SignalFinder::kBinCount,
              "finder bin count must cover every declared tuning window");

}  // namespace

const char* cc1101SignalFinderStateName(Cc1101SignalFinderState state) {
    switch (state) {
        case Cc1101SignalFinderState::Idle: return "idle";
        case Cc1101SignalFinderState::Calibrating: return "calibrating";
        case Cc1101SignalFinderState::Searching: return "searching";
        case Cc1101SignalFinderState::Fault: return "fault";
    }
    return "unknown";
}

std::uint32_t Cc1101SignalFinder::frequencyKHz(std::size_t index) {
    for (const FinderWindow& window : kWindows) {
        const std::size_t bins = windowBins(window);
        if (index < bins) {
            return window.firstKHz +
                static_cast<std::uint32_t>(index) * kStepKHz;
        }
        index -= bins;
    }
    return 0;
}

bool Cc1101SignalFinder::tunableFrequency(std::uint32_t frequencyKHz) {
    for (const FinderWindow& window : kWindows) {
        if (frequencyKHz >= window.firstKHz &&
            frequencyKHz <= window.lastKHz) return true;
    }
    return false;
}

void Cc1101SignalFinder::reset() {
    baseline_.fill(0);
    rawRise_.fill(0);
    heldRise_.fill(0);
    state_ = Cc1101SignalFinderState::Idle;
    nextBin_ = 0;
    strongestBin_ = 0;
    calibrationPasses_ = 0;
    strongestRiseDb_ = 0;
    sweeps_ = 0;
    revision_ = 0;
    startedUs_ = 0;
    updatedUs_ = 0;
}

bool Cc1101SignalFinder::start(std::uint64_t monotonicUs) {
    if (state_ != Cc1101SignalFinderState::Idle || monotonicUs == 0U) {
        return false;
    }
    reset();
    state_ = Cc1101SignalFinderState::Calibrating;
    startedUs_ = monotonicUs;
    updatedUs_ = monotonicUs;
    return true;
}

void Cc1101SignalFinder::finishSweep() {
    bool clearRawRise = true;
    if (state_ == Cc1101SignalFinderState::Calibrating) {
        ++calibrationPasses_;
        heldRise_.fill(0);
        strongestRiseDb_ = 0;
        if (calibrationPasses_ >= kCalibrationPasses) {
            state_ = Cc1101SignalFinderState::Searching;
        } else {
            // The calibration path temporarily uses rawRise_ for the first
            // two samples' maximum; keep it until the median pass completes.
            clearRawRise = false;
        }
    } else {
        std::int32_t totalDelta = 0;
        for (const std::int8_t rise : rawRise_) totalDelta += rise;
        const std::int16_t meanDelta = static_cast<std::int16_t>(
            totalDelta / static_cast<std::int32_t>(kBinCount));
        strongestRiseDb_ = 0;
        for (std::size_t index = 0; index < kBinCount; ++index) {
            std::int16_t rise =
                static_cast<std::int16_t>(rawRise_[index]) - meanDelta;
            if (rise < 0) rise = 0;
            if (rise > std::numeric_limits<std::uint8_t>::max()) {
                rise = std::numeric_limits<std::uint8_t>::max();
            }
            const std::uint8_t decayed = heldRise_[index] > kHoldDecayDb
                ? static_cast<std::uint8_t>(heldRise_[index] - kHoldDecayDb)
                : 0U;
            heldRise_[index] = rise > decayed
                ? static_cast<std::uint8_t>(rise) : decayed;
            if (heldRise_[index] > strongestRiseDb_) {
                strongestRiseDb_ = heldRise_[index];
                strongestBin_ = index;
            }
        }
    }
    if (sweeps_ != std::numeric_limits<std::uint32_t>::max()) ++sweeps_;
    if (revision_ != std::numeric_limits<std::uint32_t>::max()) ++revision_;
    if (clearRawRise) rawRise_.fill(0);
    nextBin_ = 0;
}

bool Cc1101SignalFinder::ingest(std::uint32_t frequencyKHz,
                                std::int16_t rssiDbm,
                                std::uint64_t startedUs,
                                std::uint64_t endedUs) {
    if ((state_ != Cc1101SignalFinderState::Calibrating &&
         state_ != Cc1101SignalFinderState::Searching) ||
        nextBin_ >= kBinCount || frequencyKHz != nextFrequencyKHz() ||
        !tunableFrequency(frequencyKHz) || rssiDbm < -128 || rssiDbm > 0 ||
        startedUs < updatedUs_ || endedUs < startedUs) {
        return false;
    }
    const std::int8_t sample = static_cast<std::int8_t>(rssiDbm);
    if (state_ == Cc1101SignalFinderState::Calibrating) {
        // baseline_ and rawRise_ temporarily retain the minimum and maximum
        // of the first two passes. On pass three, min + max + sample minus the
        // outer two values is the median, without another 1099-bin buffer.
        if (calibrationPasses_ == 0U) {
            baseline_[nextBin_] = sample;
            rawRise_[nextBin_] = sample;
        } else if (calibrationPasses_ == 1U) {
            if (sample < baseline_[nextBin_]) baseline_[nextBin_] = sample;
            if (sample > rawRise_[nextBin_]) rawRise_[nextBin_] = sample;
        } else {
            const std::int16_t firstMinimum = baseline_[nextBin_];
            const std::int16_t firstMaximum = rawRise_[nextBin_];
            const std::int16_t minimum = sample < firstMinimum
                ? sample : firstMinimum;
            const std::int16_t maximum = sample > firstMaximum
                ? sample : firstMaximum;
            baseline_[nextBin_] = static_cast<std::int8_t>(
                firstMinimum + firstMaximum + sample - minimum - maximum);
        }
    } else {
        if (crystalSpurFrequency(frequencyKHz)) {
            rawRise_[nextBin_] = 0;
            updatedUs_ = endedUs;
            ++nextBin_;
            if (nextBin_ == kBinCount) finishSweep();
            return true;
        }
        std::int16_t rise = static_cast<std::int16_t>(sample) -
                            static_cast<std::int16_t>(baseline_[nextBin_]);
        if (rise < -120) rise = -120;
        if (rise > 120) rise = 120;
        rawRise_[nextBin_] = static_cast<std::int8_t>(rise);
    }
    updatedUs_ = endedUs;
    ++nextBin_;
    if (nextBin_ == kBinCount) finishSweep();
    return true;
}

bool Cc1101SignalFinder::restart(std::uint64_t monotonicUs) {
    if ((state_ != Cc1101SignalFinderState::Calibrating &&
         state_ != Cc1101SignalFinderState::Searching) || monotonicUs == 0U) {
        return false;
    }
    reset();
    state_ = Cc1101SignalFinderState::Calibrating;
    startedUs_ = monotonicUs;
    updatedUs_ = monotonicUs;
    return true;
}

bool Cc1101SignalFinder::fail() {
    if (state_ == Cc1101SignalFinderState::Fault) return false;
    state_ = Cc1101SignalFinderState::Fault;
    return true;
}

bool Cc1101SignalFinder::stop() {
    if (state_ == Cc1101SignalFinderState::Idle) return false;
    state_ = Cc1101SignalFinderState::Idle;
    return true;
}

const char* Cc1101SignalFinder::bandHint() const {
    if (!found()) return "";
    const std::uint32_t frequency = strongestFrequencyKHz();
    if (frequency >= 314000U && frequency <= 316000U) return "315";
    if (frequency >= 386000U && frequency <= 392000U) return "390";
    if (frequency >= 417000U && frequency <= 419000U) return "418";
    if (frequency >= 433050U && frequency <= 434790U) return "433 ISM";
    if (frequency >= 863000U && frequency <= 870000U) return "868 ISM";
    if (frequency >= 902000U && frequency <= 928000U) return "915 ISM";
    return "";
}

}  // namespace leshy1::apps::spectrum
