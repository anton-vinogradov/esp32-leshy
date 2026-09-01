#include "LibraryController.h"

#include <cstdio>
#include <cstring>

#include "storage/SessionCodec.h"

namespace leshy1::apps::library {

const char* sessionIntegrityName(SessionIntegrity integrity) {
    switch (integrity) {
        case SessionIntegrity::Valid: return "valid";
        case SessionIntegrity::RecoveredFallback: return "recovered_fallback";
    }
    return "unknown";
}

const char* libraryExportStatusName(LibraryExportStatus status) {
    switch (status) {
        case LibraryExportStatus::Valid: return "valid";
        case LibraryExportStatus::InvalidArgument: return "invalid_argument";
        case LibraryExportStatus::SessionUnavailable: return "session_unavailable";
        case LibraryExportStatus::BufferTooSmall: return "buffer_too_small";
        case LibraryExportStatus::CaptureMetadataUnavailable:
            return "capture_metadata_unavailable";
        case LibraryExportStatus::RecordOutOfRange: return "record_out_of_range";
    }
    return "invalid_argument";
}

namespace {

char hexDigit(std::uint8_t value) {
    return value < 10 ? static_cast<char>('0' + value)
                      : static_cast<char>('a' + value - 10);
}

template <std::size_t Capacity>
void formatHex(const std::uint8_t* input, std::size_t size,
               std::array<char, Capacity>& output) {
    output.fill('\0');
    if (input == nullptr || size * 2U + 1U > output.size()) return;
    for (std::size_t index = 0; index < size; ++index) {
        output[index * 2U] = hexDigit(input[index] >> 4U);
        output[index * 2U + 1U] = hexDigit(input[index] & 0x0FU);
    }
}

LibraryExportResult formatResult(char* output, std::size_t capacity,
                                 int written) {
    if (written < 0 || static_cast<std::size_t>(written) >= capacity) {
        if (output != nullptr && capacity != 0) output[0] = '\0';
        return {LibraryExportStatus::BufferTooSmall, 0};
    }
    return {LibraryExportStatus::Valid, static_cast<std::size_t>(written)};
}

}  // namespace

void LibraryController::clear() {
    entries_.fill({});
    size_ = 0;
    selection_ = 0;
    view_ = LibraryView::SessionList;
    exportReturnView_ = LibraryView::SessionDetail;
}

bool LibraryController::add(const services::survey::SurveySession& session,
                            std::uint32_t generation, SessionIntegrity integrity,
                            bool persistent, bool simulated) {
    if (size_ >= entries_.size() ||
        session.state() != services::survey::SessionState::Stopped ||
        session.id() == nullptr || session.id()[0] == '\0') {
        return false;
    }
    for (std::size_t index = 0; index < size_; ++index) {
        const LibraryEntry& entry = entries_[index];
        if (entry.session != nullptr && entry.generation == generation &&
            std::strcmp(entry.session->id(), session.id()) == 0) {
            return false;
        }
    }
    entries_[size_++] = {&session, generation, integrity, persistent,
                         simulated, LibraryEntryKind::Session, nullptr};
    return true;
}

bool LibraryController::addScreenshot(
    const storage::ScreenshotMetadata& screenshot, SessionIntegrity integrity,
    bool persistent) {
    if (screenshot.generation == 0U) return false;
    for (std::size_t index = 0; index < size_; ++index) {
        const LibraryEntry& entry = entries_[index];
        if (entry.kind == LibraryEntryKind::Screenshot) {
            entries_[index] = {
                nullptr, screenshot.generation, integrity, persistent, false,
                LibraryEntryKind::Screenshot, &screenshot};
            return true;
        }
    }
    if (size_ >= entries_.size()) return false;
    entries_[size_++] = {nullptr, screenshot.generation, integrity, persistent,
                         false, LibraryEntryKind::Screenshot, &screenshot};
    return true;
}

bool LibraryController::copyScreenshotEntriesFrom(
    const LibraryController& source) {
    for (std::size_t index = 0U; index < source.size_; ++index) {
        const LibraryEntry& entry = source.entries_[index];
        if (entry.kind != LibraryEntryKind::Screenshot) continue;
        if (entry.screenshot == nullptr ||
            !addScreenshot(*entry.screenshot, entry.integrity,
                           entry.persistent)) {
            return false;
        }
    }
    return true;
}

bool LibraryController::replaceWithOwnedCopy(
    const services::survey::SurveySession& staged,
    services::survey::SurveySession& owned, std::uint32_t generation,
    SessionIntegrity integrity, bool persistent, bool simulated) {
    if (staged.state() != services::survey::SessionState::Stopped ||
        staged.id() == nullptr || staged.id()[0] == '\0') {
        return false;
    }
    std::array<LibraryEntry, kCapacity> retainedScreenshots{};
    std::size_t retainedCount = 0U;
    for (std::size_t index = 0; index < size_; ++index) {
        if (entries_[index].kind == LibraryEntryKind::Screenshot &&
            entries_[index].screenshot != nullptr &&
            retainedCount < retainedScreenshots.size()) {
            retainedScreenshots[retainedCount++] = entries_[index];
        }
    }
    owned = staged;
    entries_.fill({});
    entries_[0] = {&owned, generation, integrity, persistent, simulated,
                   LibraryEntryKind::Session, nullptr};
    size_ = 1;
    for (std::size_t index = 0; index < retainedCount &&
         size_ < entries_.size(); ++index) {
        entries_[size_++] = retainedScreenshots[index];
    }
    selection_ = 0;
    view_ = LibraryView::SessionList;
    exportReturnView_ = LibraryView::SessionDetail;
    return true;
}

LibraryExportResult LibraryController::formatSelectedScreenshotMetadata(
    char* output, std::size_t capacity) const {
    if (output == nullptr || capacity == 0U) {
        return {LibraryExportStatus::InvalidArgument, 0U};
    }
    const LibraryEntry* entry = selected();
    if (entry == nullptr || entry->kind != LibraryEntryKind::Screenshot ||
        entry->screenshot == nullptr) {
        output[0] = '\0';
        return {LibraryExportStatus::SessionUnavailable, 0U};
    }
    if (!storage::formatScreenshotJsonSummary(
            *entry->screenshot, output, capacity)) {
        output[0] = '\0';
        return {LibraryExportStatus::BufferTooSmall, 0U};
    }
    return {LibraryExportStatus::Valid, std::strlen(output)};
}

bool LibraryController::next() {
    if (view_ != LibraryView::SessionList || selection_ + 1 >= size_) return false;
    ++selection_;
    return true;
}

bool LibraryController::previous() {
    if (view_ != LibraryView::SessionList || selection_ == 0) return false;
    --selection_;
    return true;
}

bool LibraryController::openSelected() {
    if (view_ != LibraryView::SessionList || selected() == nullptr) return false;
    view_ = LibraryView::SessionDetail;
    return true;
}

bool LibraryController::openActions() {
    if (view_ != LibraryView::SessionDetail || selected() == nullptr) {
        return false;
    }
    view_ = LibraryView::Actions;
    return true;
}

bool LibraryController::requestExport() {
    if ((view_ != LibraryView::SessionDetail &&
         view_ != LibraryView::Actions) || selected() == nullptr) {
        return false;
    }
    exportReturnView_ = view_;
    view_ = LibraryView::ExportReady;
    return true;
}

bool LibraryController::back() {
    if (view_ == LibraryView::ExportReady) {
        view_ = exportReturnView_;
        return true;
    }
    if (view_ == LibraryView::Actions) {
        view_ = LibraryView::SessionDetail;
        return true;
    }
    if (view_ != LibraryView::SessionDetail) return false;
    view_ = LibraryView::SessionList;
    return true;
}

LibraryExportResult LibraryController::formatSelectedJsonExport(char* output,
                                                                std::size_t capacity) const {
    if (output == nullptr || capacity == 0) {
        return {LibraryExportStatus::InvalidArgument, 0};
    }
    const LibraryEntry* entry = selected();
    if (entry != nullptr && entry->kind == LibraryEntryKind::Screenshot) {
        return formatSelectedScreenshotMetadata(output, capacity);
    }
    if (entry == nullptr || entry->session == nullptr ||
        entry->session->state() != services::survey::SessionState::Stopped) {
        output[0] = '\0';
        return {LibraryExportStatus::SessionUnavailable, 0};
    }
    char sessionSummary[768] = {};
    if (!storage::formatSessionJsonSummary(
            *entry->session, sessionSummary, sizeof(sessionSummary))) {
        output[0] = '\0';
        return {LibraryExportStatus::BufferTooSmall, 0};
    }
    const int written = std::snprintf(
        output, capacity,
        "{\"schema\":\"leshy.library.export.v1\",\"kind\":\"artifact\","
        "\"status\":\"valid\",\"generation\":%lu,\"integrity\":\"%s\","
        "\"simulated\":%s,\"persistent\":%s,\"transport\":\"serial_ndjson\","
        "\"storage_backend\":\"%s\",\"radio_touched\":false,\"session\":%s%s",
        static_cast<unsigned long>(entry->generation),
        sessionIntegrityName(entry->integrity), entry->simulated ? "true" : "false",
        entry->persistent ? "true" : "false",
        entry->persistent ? "persistent_media" : "bounded_ram",
        sessionSummary, entry->session->timeline().present
            ? ",\"timeline_windows\":[" : "}");
    if (written < 0 || static_cast<std::size_t>(written) >= capacity) {
        output[0] = '\0';
        return {LibraryExportStatus::BufferTooSmall, 0};
    }
    std::size_t position = static_cast<std::size_t>(written);
    if (entry->session->timeline().present) {
        for (std::size_t index = 0;
             index < entry->session->timelineWindowCount(); ++index) {
            const services::survey::SourceWindow* window =
                entry->session->timelineWindow(index);
            if (window == nullptr) {
                output[0] = '\0';
                return {LibraryExportStatus::SessionUnavailable, 0};
            }
            const int appended = std::snprintf(
                output + position, capacity - position,
                "%s{\"source\":\"%s\",\"state\":\"%s\",\"reason\":\"%s\","
                "\"started_us\":%llu,\"ended_us\":%llu,"
                "\"accepted\":%llu,\"dropped\":%llu}",
                index == 0 ? "" : ",",
                window->source == domain::observations::RadioKind::Wifi
                    ? "wifi" : "ble",
                services::survey::sourceWindowStateName(window->state),
                services::survey::sourceWindowReasonName(window->reason),
                static_cast<unsigned long long>(window->startedUs),
                static_cast<unsigned long long>(window->endedUs),
                static_cast<unsigned long long>(window->accepted),
                static_cast<unsigned long long>(window->dropped));
            if (appended < 0 ||
                static_cast<std::size_t>(appended) >= capacity - position) {
                output[0] = '\0';
                return {LibraryExportStatus::BufferTooSmall, 0};
            }
            position += static_cast<std::size_t>(appended);
        }
        const int closed = std::snprintf(
            output + position, capacity - position, "]}");
        if (closed < 0 ||
            static_cast<std::size_t>(closed) >= capacity - position) {
            output[0] = '\0';
            return {LibraryExportStatus::BufferTooSmall, 0};
        }
        position += static_cast<std::size_t>(closed);
    }
    return {LibraryExportStatus::Valid, position};
}

LibraryExportResult LibraryController::formatSelectedCaptureMetadata(
    char* output, std::size_t capacity) const {
    if (output == nullptr || capacity == 0) {
        return {LibraryExportStatus::InvalidArgument, 0};
    }
    const LibraryEntry* entry = selected();
    if (entry == nullptr || entry->session == nullptr ||
        entry->session->state() != services::survey::SessionState::Stopped) {
        output[0] = '\0';
        return {LibraryExportStatus::SessionUnavailable, 0};
    }
    const auto& capture = entry->session->captureMetadata();
    if (!capture.present || capture.appIdentityLength != capture.appIdentity.size()) {
        output[0] = '\0';
        return {LibraryExportStatus::CaptureMetadataUnavailable, 0};
    }
    std::size_t wifiCount = 0;
    std::size_t bleCount = 0;
    for (std::size_t index = 0; index < entry->session->size(); ++index) {
        const auto* observation = entry->session->get(index);
        if (observation == nullptr) continue;
        if (observation->radio == domain::observations::RadioKind::Wifi) {
            ++wifiCount;
        } else if (observation->radio == domain::observations::RadioKind::Ble) {
            ++bleCount;
        }
    }
    std::array<char, services::survey::CaptureMetadata::kAppIdentityBytes * 2U + 1U>
        identity{};
    formatHex(capture.appIdentity.data(), capture.appIdentityLength, identity);
    const bool wifiSelected = (capture.selectedSourceMask &
        services::survey::sourceMask(domain::observations::RadioKind::Wifi)) != 0;
    const bool bleSelected = (capture.selectedSourceMask &
        services::survey::sourceMask(domain::observations::RadioKind::Ble)) != 0;
    if (capture.infraredRawCaptured) {
        const int written = std::snprintf(
            output, capacity,
            "{\"schema\":\"leshy.capture.metadata.v1\",\"kind\":\"capture\","
            "\"status\":\"valid\",\"generation\":%lu,\"integrity\":\"%s\","
            "\"persistent\":%s,\"immutable\":true,\"session_id\":\"%s\","
            "\"timebase\":\"monotonic_us\",\"started_us\":%llu,"
            "\"stopped_us\":%llu,\"build\":{\"app_elf_sha256\":\"%s\"},"
            "\"receive\":{\"mode\":\"passive\",\"rx_only\":true,"
            "\"source\":\"infrared\"},"
            "\"decode\":{\"protocol\":\"%s\",\"raw_code\":%lu,"
            "\"address\":%u,\"command\":%u,\"integrity_valid\":%s},"
            "\"payload\":{\"status\":\"captured_infrared_raw\","
            "\"records\":%u,\"bytes\":%lu,\"start_level\":%s,"
            "\"truncated\":%s},\"exports\":{"
            "\"json_summary\":\"available\","
            "\"pulse_csv\":\"available_from_validated_segment\","
            "\"pcap\":\"not_applicable\"},\"radio_touched\":false}",
            static_cast<unsigned long>(entry->generation),
            sessionIntegrityName(entry->integrity),
            entry->persistent ? "true" : "false", entry->session->id(),
            static_cast<unsigned long long>(entry->session->startedUs()),
            static_cast<unsigned long long>(entry->session->stoppedUs()),
            identity.data(), domain::captures::infraredProtocolName(
                capture.infraredDecode.protocol),
            static_cast<unsigned long>(capture.infraredDecode.rawCode),
            static_cast<unsigned>(capture.infraredDecode.address),
            static_cast<unsigned>(capture.infraredDecode.command),
            capture.infraredDecode.integrityValid ? "true" : "false",
            static_cast<unsigned>(capture.infraredPulseRecords),
            static_cast<unsigned long>(capture.infraredPulseBytes),
            capture.infraredStartLevel ? "true" : "false",
            capture.infraredTruncated ? "true" : "false");
        return formatResult(output, capacity, written);
    }
    if (capture.subGhzRawCaptured) {
        const int written = std::snprintf(
            output, capacity,
            "{\"schema\":\"leshy.capture.metadata.v1\",\"kind\":\"capture\","
            "\"status\":\"valid\",\"generation\":%lu,\"integrity\":\"%s\","
            "\"persistent\":%s,\"immutable\":true,\"session_id\":\"%s\","
            "\"timebase\":\"monotonic_us\",\"started_us\":%llu,"
            "\"stopped_us\":%llu,\"build\":{\"app_elf_sha256\":\"%s\"},"
            "\"receive\":{\"mode\":\"passive\",\"rx_only\":true,"
            "\"source\":\"cc1101\",\"frequency_khz\":%lu,"
            "\"threshold_dbm\":%d,\"modulation\":\"%s\"},"
            "\"payload\":{\"status\":\"captured_subghz_raw\","
            "\"records\":%u,\"bytes\":%lu,\"start_level\":%s,"
            "\"truncated\":%s},\"exports\":{"
            "\"json_summary\":\"available\","
            "\"pulse_csv\":\"available_from_validated_segment\","
            "\"pcap\":\"not_applicable\"},\"radio_touched\":false}",
            static_cast<unsigned long>(entry->generation),
            sessionIntegrityName(entry->integrity),
            entry->persistent ? "true" : "false", entry->session->id(),
            static_cast<unsigned long long>(entry->session->startedUs()),
            static_cast<unsigned long long>(entry->session->stoppedUs()),
            identity.data(),
            static_cast<unsigned long>(capture.subGhzFrequencyKHz),
            static_cast<int>(capture.subGhzThresholdDbm),
            domain::captures::subGhzRawModulationName(
                capture.subGhzModulation),
            static_cast<unsigned>(capture.subGhzPulseRecords),
            static_cast<unsigned long>(capture.subGhzPulseBytes),
            capture.subGhzStartLevel ? "true" : "false",
            capture.subGhzTruncated ? "true" : "false");
        return formatResult(output, capacity, written);
    }
    const int written = std::snprintf(
        output, capacity,
        "{\"schema\":\"leshy.capture.metadata.v1\",\"kind\":\"capture\","
        "\"status\":\"valid\",\"generation\":%lu,\"integrity\":\"%s\","
        "\"persistent\":%s,\"immutable\":true,\"session_id\":\"%s\","
        "\"timebase\":\"monotonic_us\",\"started_us\":%llu,"
        "\"stopped_us\":%llu,\"observations\":%u,\"dropped\":%lu,"
        "\"sources\":{\"wifi\":%u,\"ble\":%u},"
        "\"build\":{\"app_elf_sha256\":\"%s\"},"
        "\"receive\":{\"mode\":\"passive\",\"selected_mask\":%u,"
        "\"wifi\":{\"selected\":%s,\"show_hidden\":%s,\"channel\":%u,"
        "\"max_ms_per_channel\":%lu},"
        "\"ble\":{\"selected\":%s,\"duration_ms\":%lu,"
        "\"interval_ms\":%u,\"window_ms\":%u,\"maximum_records\":%u}},"
        "\"location\":{\"status\":\"not_recorded\"},"
        "\"payload\":{\"status\":\"%s\",\"bytes\":%llu,"
        "\"records\":%u,\"snap_length\":%u,\"format\":\"%s\"},"
        "\"exports\":{\"json_summary\":\"available\","
        "\"csv_observations\":\"available\","
        "\"pcap\":\"%s\"},"
        "\"radio_touched\":false}",
        static_cast<unsigned long>(entry->generation),
        sessionIntegrityName(entry->integrity),
        entry->persistent ? "true" : "false", entry->session->id(),
        static_cast<unsigned long long>(entry->session->startedUs()),
        static_cast<unsigned long long>(entry->session->stoppedUs()),
        static_cast<unsigned>(entry->session->size()),
        static_cast<unsigned long>(entry->session->dropped()),
        static_cast<unsigned>(wifiCount), static_cast<unsigned>(bleCount),
        identity.data(), static_cast<unsigned>(capture.selectedSourceMask),
        wifiSelected ? "true" : "false",
        capture.wifiShowHidden ? "true" : "false",
        static_cast<unsigned>(capture.wifiChannel),
        static_cast<unsigned long>(capture.wifiMaxMsPerChannel),
        bleSelected ? "true" : "false",
        static_cast<unsigned long>(capture.bleDurationMs),
        static_cast<unsigned>(capture.bleIntervalMs),
        static_cast<unsigned>(capture.bleWindowMs),
        static_cast<unsigned>(capture.bleMaximumRecords),
        capture.framePayloadCaptured ? "captured_raw_80211" : "not_captured",
        static_cast<unsigned long long>(capture.framePayloadBytes),
        static_cast<unsigned>(capture.framePayloadRecords),
        static_cast<unsigned>(capture.framePayloadSnapLength),
        capture.framePayloadFormat ==
                services::survey::FramePayloadFormat::Ieee80211
            ? "ieee80211" : "none",
        capture.framePayloadCaptured ? "available_radiotap" :
                                       "unavailable_no_frame_payload");
    return formatResult(output, capacity, written);
}

LibraryExportResult LibraryController::formatSelectedCsvHeader(
    char* output, std::size_t capacity) const {
    if (output == nullptr || capacity == 0) {
        return {LibraryExportStatus::InvalidArgument, 0};
    }
    const LibraryEntry* entry = selected();
    if (entry == nullptr || entry->session == nullptr ||
        entry->session->state() != services::survey::SessionState::Stopped) {
        output[0] = '\0';
        return {LibraryExportStatus::SessionUnavailable, 0};
    }
    if (!entry->session->captureMetadata().present) {
        output[0] = '\0';
        return {LibraryExportStatus::CaptureMetadataUnavailable, 0};
    }
    const int written = std::snprintf(
        output, capacity,
        "session_id,sequence,monotonic_us,radio,frequency_khz,channel,"
        "rssi_dbm,identity_hex,label_hex\r\n");
    return formatResult(output, capacity, written);
}

LibraryExportResult LibraryController::formatSelectedCsvRow(
    std::size_t index, char* output, std::size_t capacity) const {
    if (output == nullptr || capacity == 0) {
        return {LibraryExportStatus::InvalidArgument, 0};
    }
    const LibraryEntry* entry = selected();
    if (entry == nullptr || entry->session == nullptr ||
        entry->session->state() != services::survey::SessionState::Stopped) {
        output[0] = '\0';
        return {LibraryExportStatus::SessionUnavailable, 0};
    }
    if (!entry->session->captureMetadata().present) {
        output[0] = '\0';
        return {LibraryExportStatus::CaptureMetadataUnavailable, 0};
    }
    const auto* observation = entry->session->get(index);
    if (observation == nullptr) {
        output[0] = '\0';
        return {LibraryExportStatus::RecordOutOfRange, 0};
    }
    std::array<char, domain::observations::Observation::kIdentityCapacity * 2U + 1U>
        identity{};
    std::array<char, domain::observations::Observation::kLabelCapacity * 2U + 1U>
        label{};
    formatHex(observation->identity.data(), observation->identityLength, identity);
    formatHex(reinterpret_cast<const std::uint8_t*>(observation->label.data()),
              observation->labelLength, label);
    const int written = std::snprintf(
        output, capacity, "%s,%llu,%llu,%s,%lu,%u,%d,%s,%s\r\n",
        entry->session->id(),
        static_cast<unsigned long long>(observation->sequence),
        static_cast<unsigned long long>(observation->monotonicUs),
        observation->radio == domain::observations::RadioKind::Wifi
            ? "wifi" : "ble",
        static_cast<unsigned long>(observation->frequencyKhz),
        static_cast<unsigned>(observation->channel),
        static_cast<int>(observation->rssiDbm), identity.data(), label.data());
    return formatResult(output, capacity, written);
}

LibraryExportResult LibraryController::formatSelectedPcapStatus(
    char* output, std::size_t capacity) const {
    if (output == nullptr || capacity == 0) {
        return {LibraryExportStatus::InvalidArgument, 0};
    }
    const LibraryEntry* entry = selected();
    if (entry == nullptr || entry->session == nullptr ||
        entry->session->state() != services::survey::SessionState::Stopped) {
        output[0] = '\0';
        return {LibraryExportStatus::SessionUnavailable, 0};
    }
    if (!entry->session->captureMetadata().present) {
        output[0] = '\0';
        return {LibraryExportStatus::CaptureMetadataUnavailable, 0};
    }
    const auto& capture = entry->session->captureMetadata();
    const std::uint64_t pcapBytes = capture.framePayloadCaptured
        ? 24ULL + static_cast<std::uint64_t>(capture.framePayloadRecords) * 31ULL +
              capture.framePayloadBytes
        : 0ULL;
    const int written = std::snprintf(
        output, capacity,
        "{\"schema\":\"leshy.library.pcap.v1\",\"kind\":\"artifact\","
        "\"status\":\"%s\",\"generation\":%lu,"
        "\"session_id\":\"%s\",\"records\":%u,\"bytes\":%llu,"
        "\"radio_touched\":false}",
        capture.framePayloadCaptured ? "available" :
                                       "unavailable_no_frame_payload",
        static_cast<unsigned long>(entry->generation), entry->session->id(),
        static_cast<unsigned>(capture.framePayloadRecords),
        static_cast<unsigned long long>(pcapBytes));
    return formatResult(output, capacity, written);
}

const LibraryEntry* LibraryController::selected() const { return get(selection_); }

const LibraryEntry* LibraryController::get(std::size_t index) const {
    return index < size_ ? &entries_[index] : nullptr;
}

}  // namespace leshy1::apps::library
