#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "services/survey/SurveySession.h"
#include "storage/ScreenshotStore.h"

namespace leshy1::apps::library {

enum class LibraryView : std::uint8_t {
    SessionList,
    SessionDetail,
    Actions,
    ExportReady,
};

enum class SessionIntegrity : std::uint8_t {
    Valid,
    RecoveredFallback,
};

enum class LibraryEntryKind : std::uint8_t {
    Session,
    Screenshot,
};

const char* sessionIntegrityName(SessionIntegrity integrity);

enum class LibraryExportStatus : std::uint8_t {
    Valid,
    InvalidArgument,
    SessionUnavailable,
    BufferTooSmall,
    CaptureMetadataUnavailable,
    RecordOutOfRange,
};

const char* libraryExportStatusName(LibraryExportStatus status);

struct LibraryExportResult final {
    LibraryExportStatus status = LibraryExportStatus::InvalidArgument;
    std::size_t bytes = 0;

    bool valid() const { return status == LibraryExportStatus::Valid; }
};

struct LibraryEntry final {
    const services::survey::SurveySession* session = nullptr;
    std::uint32_t generation = 0;
    SessionIntegrity integrity = SessionIntegrity::Valid;
    bool persistent = false;
    bool simulated = false;
    LibraryEntryKind kind = LibraryEntryKind::Session;
    const storage::ScreenshotMetadata* screenshot = nullptr;
};

class LibraryController final {
public:
    static constexpr std::size_t kCapacity = 5;

    void clear();
    bool add(const services::survey::SurveySession& session, std::uint32_t generation,
             SessionIntegrity integrity, bool persistent, bool simulated);
    bool addScreenshot(const storage::ScreenshotMetadata& screenshot,
                       SessionIntegrity integrity, bool persistent);
    bool copyScreenshotEntriesFrom(const LibraryController& source);
    bool replaceWithOwnedCopy(
        const services::survey::SurveySession& staged,
        services::survey::SurveySession& owned, std::uint32_t generation,
        SessionIntegrity integrity, bool persistent, bool simulated);
    bool next();
    bool previous();
    bool openSelected();
    bool openActions();
    bool requestExport();
    bool back();
    LibraryExportResult formatSelectedJsonExport(char* output, std::size_t capacity) const;
    LibraryExportResult formatSelectedCaptureMetadata(
        char* output, std::size_t capacity) const;
    LibraryExportResult formatSelectedCsvHeader(
        char* output, std::size_t capacity) const;
    LibraryExportResult formatSelectedCsvRow(
        std::size_t index, char* output, std::size_t capacity) const;
    LibraryExportResult formatSelectedPcapStatus(
        char* output, std::size_t capacity) const;
    LibraryExportResult formatSelectedScreenshotMetadata(
        char* output, std::size_t capacity) const;

    LibraryView view() const { return view_; }
    LibraryView exportReturnView() const { return exportReturnView_; }
    std::size_t selection() const { return selection_; }
    std::size_t size() const { return size_; }
    const LibraryEntry* selected() const;
    const LibraryEntry* get(std::size_t index) const;

private:
    std::array<LibraryEntry, kCapacity> entries_{};
    std::size_t size_ = 0;
    std::size_t selection_ = 0;
    LibraryView view_ = LibraryView::SessionList;
    LibraryView exportReturnView_ = LibraryView::SessionDetail;
};

}  // namespace leshy1::apps::library
