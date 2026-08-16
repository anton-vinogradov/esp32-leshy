#include "LibraryController.h"

#include <cstdio>
#include <cstring>

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
    }
    return "invalid_argument";
}

void LibraryController::clear() {
    entries_.fill({});
    size_ = 0;
    selection_ = 0;
    view_ = LibraryView::SessionList;
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
    entries_[size_++] = {&session, generation, integrity, persistent, simulated};
    return true;
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

bool LibraryController::requestExport() {
    if (view_ != LibraryView::SessionDetail || selected() == nullptr) return false;
    view_ = LibraryView::ExportReady;
    return true;
}

bool LibraryController::back() {
    if (view_ == LibraryView::ExportReady) {
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
    if (entry == nullptr || entry->session == nullptr ||
        entry->session->state() != services::survey::SessionState::Stopped) {
        output[0] = '\0';
        return {LibraryExportStatus::SessionUnavailable, 0};
    }
    std::size_t wifiCount = 0;
    for (std::size_t index = 0; index < entry->session->size(); ++index) {
        const domain::observations::Observation* observation = entry->session->get(index);
        if (observation != nullptr &&
            observation->radio == domain::observations::RadioKind::Wifi) {
            ++wifiCount;
        }
    }
    const int written = std::snprintf(
        output, capacity,
        "{\"schema\":\"leshy.library.export.v1\",\"kind\":\"artifact\","
        "\"status\":\"valid\",\"generation\":%lu,\"integrity\":\"%s\","
        "\"simulated\":%s,\"persistent\":%s,\"transport\":\"serial_ndjson\","
        "\"storage_backend\":\"%s\",\"radio_touched\":false,\"session\":{"
        "\"schema\":\"leshy.session.summary.v1\",\"id\":\"%s\","
        "\"started_us\":%llu,\"stopped_us\":%llu,\"observations\":%u,"
        "\"dropped\":%lu,\"sources\":{\"wifi\":%u}}}",
        static_cast<unsigned long>(entry->generation),
        sessionIntegrityName(entry->integrity), entry->simulated ? "true" : "false",
        entry->persistent ? "true" : "false",
        entry->persistent ? "persistent_media" : "bounded_ram", entry->session->id(),
        static_cast<unsigned long long>(entry->session->startedUs()),
        static_cast<unsigned long long>(entry->session->stoppedUs()),
        static_cast<unsigned>(entry->session->size()),
        static_cast<unsigned long>(entry->session->dropped()),
        static_cast<unsigned>(wifiCount));
    if (written < 0 || static_cast<std::size_t>(written) >= capacity) {
        output[0] = '\0';
        return {LibraryExportStatus::BufferTooSmall, 0};
    }
    return {LibraryExportStatus::Valid, static_cast<std::size_t>(written)};
}

const LibraryEntry* LibraryController::selected() const { return get(selection_); }

const LibraryEntry* LibraryController::get(std::size_t index) const {
    return index < size_ ? &entries_[index] : nullptr;
}

}  // namespace leshy1::apps::library
