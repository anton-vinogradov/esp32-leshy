#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/captures/WifiFrame.h"
#include "domain/captures/InfraredRaw.h"
#include "domain/captures/SubGhzRaw.h"
#include "services/survey/SurveySession.h"

namespace leshy1::storage {

constexpr std::uint16_t kLegacySessionSchemaVersion = 1;
constexpr std::uint16_t kTimelineSessionSchemaVersion = 2;
constexpr std::uint16_t kSessionSchemaVersion = 3;
constexpr std::uint16_t kWifiFrameSessionSchemaVersion = 4;
constexpr std::uint16_t kSubGhzRawSessionSchemaVersion = 5;
constexpr std::uint16_t kInfraredRawSessionSchemaVersion = 6;
// Version 7 preserves passive radio facts used by device intelligence and
// stable Target identity (notably the BLE address type). Versions 1..6 remain
// readable.
constexpr std::uint16_t kEnrichedSessionSchemaVersion = 7;
constexpr std::uint16_t kLegacySegmentSchemaVersion = 1;
constexpr std::uint16_t kTimelineSegmentSchemaVersion = 2;
constexpr std::uint16_t kSegmentSchemaVersion = 3;
constexpr std::uint16_t kWifiFrameSegmentSchemaVersion = 4;
constexpr std::uint16_t kSubGhzRawSegmentSchemaVersion = 5;
constexpr std::uint16_t kInfraredRawSegmentSchemaVersion = 6;
constexpr std::uint16_t kEnrichedSegmentSchemaVersion = 7;
constexpr std::size_t kSessionManifestMaxBytes = 256;
constexpr std::size_t kObservationRecordMaxBytes = 128;
constexpr std::size_t kTimelineRecordMaxBytes = 1024;
constexpr std::size_t kSessionSegmentMaxBytes = 12288;
constexpr std::size_t kSegmentFooterBytes = 24;

struct SessionManifest final {
    std::uint16_t schemaVersion = 0;
    std::array<char, services::survey::SurveySession::kSessionIdCapacity + 1> sessionId{};
    std::uint64_t startedUs = 0;
    std::uint64_t stoppedUs = 0;
    std::uint32_t observationCount = 0;
    std::uint32_t segmentLength = 0;
    std::uint32_t segmentCrc32c = 0;
};

enum class SessionCodecStatus : std::uint8_t {
    Valid,
    InvalidArgument,
    BufferTooSmall,
    Malformed,
    UnsupportedSchema,
    BoundsExceeded,
    ChecksumMismatch,
    TimelineInvalid,
    CaptureInvalid,
    TrailingData,
};

const char* sessionCodecStatusName(SessionCodecStatus status);

SessionCodecStatus encodeObservationSegment(const services::survey::SurveySession& session,
                                            std::uint8_t* output, std::size_t capacity,
                                            std::size_t* outputSize);
SessionCodecStatus encodeWifiFrameCaptureSegment(
    const services::survey::SurveySession& session,
    const domain::captures::WifiFrameSource& frames,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize);
SessionCodecStatus encodeSubGhzRawCaptureSegment(
    const services::survey::SurveySession& session,
    const domain::captures::SubGhzRawSource& pulses,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize);
SessionCodecStatus encodeInfraredRawCaptureSegment(
    const services::survey::SurveySession& session,
    const domain::captures::InfraredRawSource& pulses,
    std::uint8_t* output, std::size_t capacity, std::size_t* outputSize);
SessionCodecStatus encodeSessionManifest(const services::survey::SurveySession& session,
                                         const std::uint8_t* segment, std::size_t segmentSize,
                                         std::uint8_t* output, std::size_t capacity,
                                         std::size_t* outputSize);
SessionCodecStatus decodeSessionManifest(const std::uint8_t* input, std::size_t size,
                                         SessionManifest* output);
SessionCodecStatus reopenSession(const std::uint8_t* manifest, std::size_t manifestSize,
                                 const std::uint8_t* segment, std::size_t segmentSize,
                                 services::survey::SurveySession* output);

class PersistedWifiFrameCaptureView final
    : public domain::captures::WifiFrameSource {
public:
    static constexpr std::size_t kFrameCapacity = 16;

    void reset();
    std::size_t frameCount() const override { return count_; }
    std::uint16_t snapLength() const override { return snapLength_; }
    bool frameView(std::size_t index,
                   domain::captures::WifiFrameView* output) const override;

private:
    friend SessionCodecStatus openPersistedWifiFrameCapture(
        const services::survey::SurveySession&, const std::uint8_t*,
        std::size_t, PersistedWifiFrameCaptureView*);
    const std::uint8_t* block_ = nullptr;
    std::size_t blockSize_ = 0;
    std::array<std::uint16_t, kFrameCapacity> recordOffsets_{};
    std::size_t count_ = 0;
    std::uint16_t snapLength_ = 0;
};

SessionCodecStatus openPersistedWifiFrameCapture(
    const services::survey::SurveySession& session,
    const std::uint8_t* segment, std::size_t segmentSize,
    PersistedWifiFrameCaptureView* output);

class PersistedSubGhzRawCaptureView final
    : public domain::captures::SubGhzRawSource {
public:
    static constexpr std::size_t kPulseCapacity = 512;

    void reset();
    std::size_t pulseCount() const override { return count_; }
    bool pulseView(std::size_t index,
                   domain::captures::SubGhzRawPulseView* output) const override;

private:
    friend SessionCodecStatus openPersistedSubGhzRawCapture(
        const services::survey::SurveySession&, const std::uint8_t*,
        std::size_t, PersistedSubGhzRawCaptureView*);
    const std::uint8_t* block_ = nullptr;
    std::size_t blockSize_ = 0;
    std::size_t count_ = 0;
};

SessionCodecStatus openPersistedSubGhzRawCapture(
    const services::survey::SurveySession& session,
    const std::uint8_t* segment, std::size_t segmentSize,
    PersistedSubGhzRawCaptureView* output);

class PersistedInfraredRawCaptureView final
    : public domain::captures::InfraredRawSource {
public:
    static constexpr std::size_t kPulseCapacity = 512;

    void reset();
    std::size_t pulseCount() const override { return count_; }
    bool pulseView(std::size_t index,
                   domain::captures::InfraredRawPulseView* output) const override;

private:
    friend SessionCodecStatus openPersistedInfraredRawCapture(
        const services::survey::SurveySession&, const std::uint8_t*,
        std::size_t, PersistedInfraredRawCaptureView*);
    const std::uint8_t* block_ = nullptr;
    std::size_t blockSize_ = 0;
    std::size_t count_ = 0;
};

SessionCodecStatus openPersistedInfraredRawCapture(
    const services::survey::SurveySession& session,
    const std::uint8_t* segment, std::size_t segmentSize,
    PersistedInfraredRawCaptureView* output);
bool formatSessionJsonSummary(const services::survey::SurveySession& session, char* output,
                              std::size_t capacity);

}  // namespace leshy1::storage
