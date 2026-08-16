#include <array>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include <fcntl.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#include "drivers/wifi/WifiPassiveContract.h"
#include "services/survey/SurveySession.h"
#include "storage/AtomicHead.h"
#include "storage/SessionCodec.h"
#include "storage/SessionStore.h"
#include "storage/StorageGuard.h"

using namespace leshy1::domain::observations;
using namespace leshy1::drivers::wifi;
using namespace leshy1::services::survey;
using namespace leshy1::storage;

namespace {

struct IoCounters final {
    std::size_t fileSyncs = 0;
    std::size_t directorySyncs = 0;
};

struct EncodedSession final {
    std::array<std::uint8_t, kSessionSegmentMaxBytes> segment{};
    std::array<std::uint8_t, kSessionManifestMaxBytes> manifest{};
    std::size_t segmentSize = 0;
    std::size_t manifestSize = 0;
};

struct ScenarioResult final {
    CommitStage injected = CommitStage::Complete;
    bool commitComplete = false;
    CommitStage stoppedAt = CommitStage::Complete;
    std::uint32_t recoveredGeneration = 0;
    std::size_t reopenedObservations = 0;
    bool priorBytesUnchanged = false;
    bool passed = false;
    IoCounters io{};
};

struct CrashScenarioResult final {
    CommitStage killedAfter = CommitStage::Complete;
    bool childKilled = false;
    std::uint32_t recoveredGeneration = 0;
    std::size_t reopenedObservations = 0;
    bool priorBytesUnchanged = false;
    bool passed = false;
};

const char* stageName(CommitStage stage) {
    switch (stage) {
        case CommitStage::WritePayloads: return "write_payloads";
        case CommitStage::SyncPayloads: return "sync_payloads";
        case CommitStage::WriteManifest: return "write_manifest";
        case CommitStage::SyncManifest: return "sync_manifest";
        case CommitStage::WriteHead: return "write_head";
        case CommitStage::SyncHead: return "sync_head";
        case CommitStage::Complete: return "complete";
    }
    return "unknown";
}

std::filesystem::path generationPath(const std::filesystem::path& root, const char* kind,
                                     std::uint32_t generation) {
    char name[64] = {};
    std::snprintf(name, sizeof(name), "%s-%08lu.bin", kind,
                  static_cast<unsigned long>(generation));
    return root / name;
}

bool writeFile(const std::filesystem::path& path, const std::uint8_t* data,
               std::size_t size) {
    const int descriptor = ::open(path.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (descriptor < 0) return false;
    std::size_t offset = 0;
    bool ok = true;
    while (offset < size) {
        const ssize_t written = ::write(descriptor, data + offset, size - offset);
        if (written <= 0) {
            ok = false;
            break;
        }
        offset += static_cast<std::size_t>(written);
    }
    if (::close(descriptor) != 0) ok = false;
    return ok;
}

bool readFile(const std::filesystem::path& path, std::vector<std::uint8_t>* output) {
    if (output == nullptr) return false;
    std::ifstream stream(path, std::ios::binary);
    if (!stream) return false;
    output->assign(std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>());
    return stream.good() || stream.eof();
}

bool syncFile(const std::filesystem::path& path, IoCounters* counters) {
    const int descriptor = ::open(path.c_str(), O_RDONLY);
    if (descriptor < 0) return false;
    const bool ok = ::fsync(descriptor) == 0;
    const bool closed = ::close(descriptor) == 0;
    if (ok && counters != nullptr) ++counters->fileSyncs;
    return ok && closed;
}

bool syncDirectory(const std::filesystem::path& path, IoCounters* counters) {
#ifdef O_DIRECTORY
    const int descriptor = ::open(path.c_str(), O_RDONLY | O_DIRECTORY);
#else
    const int descriptor = ::open(path.c_str(), O_RDONLY);
#endif
    if (descriptor < 0) return false;
    const bool ok = ::fsync(descriptor) == 0;
    const bool closed = ::close(descriptor) == 0;
    if (ok && counters != nullptr) ++counters->directorySyncs;
    return ok && closed;
}

SurveySession makeSession(const char* id, std::uint64_t stoppedUs) {
    SurveySession session;
    if (session.start(id, 1000) != SessionStatus::Started) return session;
    static constexpr std::array<std::array<std::uint8_t, 6>, 3> kBssids{{
        {0x02, 0x00, 0x00, 0x00, 0x00, 0x01},
        {0x02, 0x00, 0x00, 0x00, 0x00, 0x02},
        {0x02, 0x00, 0x00, 0x00, 0x00, 0x03},
    }};
    static constexpr std::array<std::uint8_t, 3> kChannels{{1, 6, 11}};
    static constexpr std::array<std::int16_t, 3> kRssi{{-71, -55, -83}};
    static constexpr std::array<const char*, 3> kSsids{{"alpha", "bravo", "charlie"}};
    for (std::size_t index = 0; index < kBssids.size(); ++index) {
        WifiScanRecord record;
        record.bssid = kBssids[index];
        record.channel = kChannels[index];
        record.rssiDbm = kRssi[index];
        record.ssid = kSsids[index];
        record.ssidLength = std::strlen(kSsids[index]);
        Observation observation;
        if (!normalizePassiveRecord(record, 2000 + index, &observation) ||
            session.append(observation) != SessionStatus::Appended) {
            return SurveySession{};
        }
    }
    if (session.stop(stoppedUs) != SessionStatus::Stopped) return SurveySession{};
    return session;
}

bool encodeSession(const SurveySession& session, EncodedSession* encoded) {
    if (encoded == nullptr || session.state() != SessionState::Stopped) return false;
    if (encodeObservationSegment(session, encoded->segment.data(), encoded->segment.size(),
                                 &encoded->segmentSize) != SessionCodecStatus::Valid) {
        return false;
    }
    return encodeSessionManifest(session, encoded->segment.data(), encoded->segmentSize,
                                 encoded->manifest.data(), encoded->manifest.size(),
                                 &encoded->manifestSize) == SessionCodecStatus::Valid;
}

class FilesystemBackend final : public CommitBackend {
public:
    FilesystemBackend(std::filesystem::path root, std::uint32_t generation,
                      const EncodedSession& encoded, CommitStage failure,
                      CommitStage notifyAfter = CommitStage::Complete, int notifyFd = -1)
        : root_(std::move(root)), generation_(generation), encoded_(encoded),
          failure_(failure), notifyAfter_(notifyAfter), notifyFd_(notifyFd) {}

    bool writePayloads() override {
        const std::size_t size = failure_ == CommitStage::WritePayloads
                                     ? encoded_.segmentSize / 2
                                     : encoded_.segmentSize;
        if (!writeFile(segmentPath(), encoded_.segment.data(), size)) return false;
        if (failure_ == CommitStage::WritePayloads) return false;
        return finishStage(CommitStage::WritePayloads);
    }

    bool syncPayloads() override {
        if (failure_ == CommitStage::SyncPayloads) return false;
        if (!syncFile(segmentPath(), &counters_) || !syncDirectory(root_, &counters_)) {
            return false;
        }
        return finishStage(CommitStage::SyncPayloads);
    }

    bool writeManifest() override {
        const std::size_t size = failure_ == CommitStage::WriteManifest
                                     ? encoded_.manifestSize / 2
                                     : encoded_.manifestSize;
        if (!writeFile(manifestPath(), encoded_.manifest.data(), size)) return false;
        if (failure_ == CommitStage::WriteManifest) return false;
        return finishStage(CommitStage::WriteManifest);
    }

    bool syncManifest() override {
        if (failure_ == CommitStage::SyncManifest) return false;
        if (!syncFile(manifestPath(), &counters_) || !syncDirectory(root_, &counters_)) {
            return false;
        }
        return finishStage(CommitStage::SyncManifest);
    }

    bool writeOlderHead(const std::uint8_t* wire, std::size_t size) override {
        if (wire == nullptr || size != kHeadWireSize) return false;
        std::memcpy(pendingHead_.data(), wire, size);
        const std::size_t persisted = failure_ == CommitStage::WriteHead ? size / 2 : size;
        if (!writeFile(root_ / "head-b.bin", pendingHead_.data(), persisted)) return false;
        if (failure_ == CommitStage::WriteHead) return false;
        return finishStage(CommitStage::WriteHead);
    }

    bool syncHead() override {
        if (failure_ == CommitStage::SyncHead) {
            // A failed durability barrier may leave a torn/absent new head after a crash.
            // Persist that conservative crash image; synced payload/manifest remain orphans.
            return writeFile(root_ / "head-b.bin", pendingHead_.data(), kHeadWireSize / 2) &&
                   false;
        }
        if (!syncFile(root_ / "head-b.bin", &counters_) ||
            !syncDirectory(root_, &counters_)) {
            return false;
        }
        return finishStage(CommitStage::SyncHead);
    }

    const IoCounters& counters() const { return counters_; }

private:
    bool finishStage(CommitStage stage) {
        if (stage != notifyAfter_) return true;
        if (notifyFd_ < 0) return false;
        const std::uint8_t reached = 1;
        if (::write(notifyFd_, &reached, sizeof(reached)) !=
            static_cast<ssize_t>(sizeof(reached))) {
            return false;
        }
        for (;;) ::pause();
    }

    std::filesystem::path segmentPath() const {
        return generationPath(root_, "segment", generation_);
    }
    std::filesystem::path manifestPath() const {
        return generationPath(root_, "manifest", generation_);
    }

    std::filesystem::path root_;
    std::uint32_t generation_ = 0;
    const EncodedSession& encoded_;
    CommitStage failure_ = CommitStage::Complete;
    CommitStage notifyAfter_ = CommitStage::Complete;
    int notifyFd_ = -1;
    std::array<std::uint8_t, kHeadWireSize> pendingHead_{};
    IoCounters counters_{};
};

bool initializeGeneration(const std::filesystem::path& root, std::uint32_t generation,
                          const EncodedSession& encoded, IoCounters* counters) {
    const auto segment = generationPath(root, "segment", generation);
    const auto manifest = generationPath(root, "manifest", generation);
    const HeadRecord head{generation, static_cast<std::uint32_t>(encoded.manifestSize),
                          crc32c(encoded.manifest.data(), encoded.manifestSize)};
    std::array<std::uint8_t, kHeadWireSize> wire{};
    return encodeHead(head, wire.data(), wire.size()) &&
           writeFile(segment, encoded.segment.data(), encoded.segmentSize) &&
           syncFile(segment, counters) && writeFile(manifest, encoded.manifest.data(),
                                                    encoded.manifestSize) &&
           syncFile(manifest, counters) &&
           writeFile(root / "head-a.bin", wire.data(), wire.size()) &&
           syncFile(root / "head-a.bin", counters) && syncDirectory(root, counters);
}

class PosixSessionStoreIo final : public SessionStoreIo {
public:
    explicit PosixSessionStoreIo(std::filesystem::path root) : root_(std::move(root)) {}

    bool writeFile(const char* path, const std::uint8_t* data, std::size_t size) override {
        return path != nullptr && ::writeFile(root_ / path, data, size);
    }

    ReadStatus readFile(const char* path, std::uint8_t* output, std::size_t capacity,
                        std::size_t* outputSize) override {
        if (path == nullptr || output == nullptr || outputSize == nullptr) {
            return ReadStatus::IoError;
        }
        std::error_code existsError;
        const bool exists = std::filesystem::exists(root_ / path, existsError);
        if (existsError) return ReadStatus::IoError;
        if (!exists) return ReadStatus::NotFound;
        std::vector<std::uint8_t> bytes;
        if (!::readFile(root_ / path, &bytes)) return ReadStatus::IoError;
        if (bytes.size() > capacity) return ReadStatus::TooLarge;
        std::memcpy(output, bytes.data(), bytes.size());
        *outputSize = bytes.size();
        return ReadStatus::Ok;
    }

    bool syncFile(const char* path) override {
        return path != nullptr && ::syncFile(root_ / path, &counters_);
    }
    bool syncDirectory() override { return ::syncDirectory(root_, &counters_); }

private:
    std::filesystem::path root_;
    IoCounters counters_{};
};

SessionStoreRecoveryResult recoverFromStore(const std::filesystem::path& root,
                                            SessionStoreWorkspace& workspace,
                                            SurveySession* output) {
    PosixSessionStoreIo io(root);
    return recoverSession(io, workspace, output);
}

bool priorGenerationUnchanged(const std::filesystem::path& root,
                              const EncodedSession& prior) {
    std::vector<std::uint8_t> priorManifest;
    std::vector<std::uint8_t> priorSegment;
    return readFile(generationPath(root, "manifest", 1), &priorManifest) &&
           readFile(generationPath(root, "segment", 1), &priorSegment) &&
           priorManifest.size() == prior.manifestSize &&
           priorSegment.size() == prior.segmentSize &&
           crc32c(priorManifest.data(), priorManifest.size()) ==
               crc32c(prior.manifest.data(), prior.manifestSize) &&
           crc32c(priorSegment.data(), priorSegment.size()) ==
               crc32c(prior.segment.data(), prior.segmentSize);
}

ScenarioResult runScenario(const std::filesystem::path& root, CommitStage failure,
                           const EncodedSession& prior, const EncodedSession& next) {
    ScenarioResult scenario;
    scenario.injected = failure;
    IoCounters initialCounters;
    if (!std::filesystem::create_directories(root) ||
        !initializeGeneration(root, 1, prior, &initialCounters)) {
        return scenario;
    }
    FilesystemBackend backend(root, 2, next, failure);
    const HeadRecord nextHead{2, static_cast<std::uint32_t>(next.manifestSize),
                              crc32c(next.manifest.data(), next.manifestSize)};
    const CommitResult committed = commitGeneration(backend, nextHead);
    scenario.commitComplete = committed.complete;
    scenario.stoppedAt = committed.stage;
    scenario.io.fileSyncs = initialCounters.fileSyncs + backend.counters().fileSyncs;
    scenario.io.directorySyncs =
        initialCounters.directorySyncs + backend.counters().directorySyncs;

    SessionStoreWorkspace storeWorkspace;
    SurveySession reopened;
    const SessionStoreRecoveryResult recovery =
        recoverFromStore(root, storeWorkspace, &reopened);
    if (!recovery.valid()) return scenario;
    scenario.recoveredGeneration = recovery.generation;
    scenario.reopenedObservations = recovery.observations;

    scenario.priorBytesUnchanged = priorGenerationUnchanged(root, prior);

    const std::uint32_t expectedGeneration = failure == CommitStage::Complete ? 2U : 1U;
    scenario.passed = scenario.recoveredGeneration == expectedGeneration &&
                      scenario.reopenedObservations == 3 && scenario.priorBytesUnchanged &&
                      scenario.commitComplete == (failure == CommitStage::Complete) &&
                      scenario.stoppedAt == failure;
    return scenario;
}

CrashScenarioResult runCrashScenario(const std::filesystem::path& root,
                                     CommitStage killedAfter,
                                     const EncodedSession& prior,
                                     const EncodedSession& next) {
    CrashScenarioResult scenario;
    scenario.killedAfter = killedAfter;
    IoCounters initialCounters;
    if (!std::filesystem::create_directories(root) ||
        !initializeGeneration(root, 1, prior, &initialCounters)) {
        return scenario;
    }
    int notification[2] = {-1, -1};
    if (::pipe(notification) != 0) return scenario;
    const pid_t child = ::fork();
    if (child < 0) {
        ::close(notification[0]);
        ::close(notification[1]);
        return scenario;
    }
    if (child == 0) {
        ::close(notification[0]);
        FilesystemBackend backend(root, 2, next, CommitStage::Complete, killedAfter,
                                  notification[1]);
        const HeadRecord nextHead{2, static_cast<std::uint32_t>(next.manifestSize),
                                  crc32c(next.manifest.data(), next.manifestSize)};
        const CommitResult result = commitGeneration(backend, nextHead);
        ::close(notification[1]);
        ::_exit(result.complete ? 0 : 3);
    }

    ::close(notification[1]);
    std::uint8_t reached = 0;
    const ssize_t notified = ::read(notification[0], &reached, sizeof(reached));
    ::close(notification[0]);
    if (notified != static_cast<ssize_t>(sizeof(reached)) || reached != 1) {
        ::kill(child, SIGKILL);
        ::waitpid(child, nullptr, 0);
        return scenario;
    }
    if (::kill(child, SIGKILL) != 0) {
        ::waitpid(child, nullptr, 0);
        return scenario;
    }
    int status = 0;
    if (::waitpid(child, &status, 0) != child) return scenario;
    scenario.childKilled = WIFSIGNALED(status) && WTERMSIG(status) == SIGKILL;

    SessionStoreWorkspace storeWorkspace;
    SurveySession reopened;
    const SessionStoreRecoveryResult recovery =
        recoverFromStore(root, storeWorkspace, &reopened);
    if (!recovery.valid()) return scenario;
    scenario.recoveredGeneration = recovery.generation;
    scenario.reopenedObservations = recovery.observations;
    scenario.priorBytesUnchanged = priorGenerationUnchanged(root, prior);

    bool generationAllowed = scenario.recoveredGeneration == 1;
    if (killedAfter == CommitStage::WriteHead) {
        generationAllowed = scenario.recoveredGeneration == 1 ||
                            scenario.recoveredGeneration == 2;
    } else if (killedAfter == CommitStage::SyncHead) {
        generationAllowed = scenario.recoveredGeneration == 2;
    }
    scenario.passed = scenario.childKilled && generationAllowed &&
                      scenario.reopenedObservations == 3 && scenario.priorBytesUnchanged;
    return scenario;
}

std::string jsonEscape(const std::string& input) {
    std::string output;
    for (char value : input) {
        if (value == '\\' || value == '"') output.push_back('\\');
        output.push_back(value);
    }
    return output;
}

bool writeEvidence(const std::filesystem::path& output, const std::vector<ScenarioResult>& runs,
                   const std::vector<CrashScenarioResult>& crashRuns,
                   const SurveySession& reopened, const WritePermit& permit, bool allPassed,
                   bool cleaned) {
    char summary[256] = {};
    if (!formatSessionJsonSummary(reopened, summary, sizeof(summary))) return false;
    std::ofstream stream(output, std::ios::binary | std::ios::trunc);
    if (!stream) return false;
    std::size_t totalFileSyncs = 0;
    std::size_t totalDirectorySyncs = 0;
    for (const ScenarioResult& run : runs) {
        totalFileSyncs += run.io.fileSyncs;
        totalDirectorySyncs += run.io.directorySyncs;
    }
    stream << "{\n"
           << "  \"schema\": \"leshy.storage.fs-fixture.v1\",\n"
           << "  \"status\": \"" << (allPassed ? "pass" : "fail") << "\",\n"
           << "  \"fixture_root\": \"temporary_mkdtemp\",\n"
           << "  \"host_storage_written\": true,\n"
           << "  \"physical_device_written\": false,\n"
           << "  \"guard_status\": \"" << permitStatusName(permit.status) << "\",\n"
           << "  \"guard_scratch_path\": \"" << permit.scratchPath << "\",\n"
           << "  \"guard_byte_limit\": " << permit.byteLimit << ",\n"
           << "  \"fixture_cleaned\": " << (cleaned ? "true" : "false") << ",\n"
           << "  \"modeled_failure_scenario_count\": " << runs.size() << ",\n"
           << "  \"process_kill_scenario_count\": " << crashRuns.size() << ",\n"
           << "  \"file_fsync_calls\": " << totalFileSyncs << ",\n"
           << "  \"directory_fsync_calls\": " << totalDirectorySyncs << ",\n"
           << "  \"failure_scenarios\": [\n";
    for (std::size_t index = 0; index < runs.size(); ++index) {
        const ScenarioResult& run = runs[index];
        stream << "    {\"injected\": \"" << jsonEscape(stageName(run.injected))
               << "\", \"commit_complete\": "
               << (run.commitComplete ? "true" : "false")
               << ", \"stopped_at\": \"" << jsonEscape(stageName(run.stoppedAt))
               << "\", \"recovered_generation\": " << run.recoveredGeneration
               << ", \"reopened_observations\": " << run.reopenedObservations
               << ", \"prior_bytes_unchanged\": "
               << (run.priorBytesUnchanged ? "true" : "false")
               << ", \"passed\": " << (run.passed ? "true" : "false") << "}";
        if (index + 1 != runs.size()) stream << ',';
        stream << '\n';
    }
    stream << "  ],\n"
           << "  \"process_kill_scenarios\": [\n";
    for (std::size_t index = 0; index < crashRuns.size(); ++index) {
        const CrashScenarioResult& run = crashRuns[index];
        stream << "    {\"killed_after\": \"" << jsonEscape(stageName(run.killedAfter))
               << "\", \"signal\": \"SIGKILL\", \"child_killed\": "
               << (run.childKilled ? "true" : "false")
               << ", \"recovered_generation\": " << run.recoveredGeneration
               << ", \"reopened_observations\": " << run.reopenedObservations
               << ", \"prior_bytes_unchanged\": "
               << (run.priorBytesUnchanged ? "true" : "false")
               << ", \"passed\": " << (run.passed ? "true" : "false") << "}";
        if (index + 1 != crashRuns.size()) stream << ',';
        stream << '\n';
    }
    stream << "  ],\n"
           << "  \"complete_reopen_summary\": " << summary << "\n"
           << "}\n";
    return stream.good();
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 3 || std::strcmp(argv[1], "--output") != 0) {
        std::cerr << "usage: storage_filesystem_fixture --output <evidence.json>\n";
        return 2;
    }
    const SurveySession priorSession = makeSession("golden-wifi-001", 3000);
    const SurveySession nextSession = makeSession("golden-wifi-002", 4000);
    EncodedSession prior;
    EncodedSession next;
    if (!encodeSession(priorSession, &prior) || !encodeSession(nextSession, &next)) {
        std::cerr << "failed to encode fixture sessions\n";
        return 1;
    }

    char rootTemplate[] = "/tmp/leshy-storage-fixture.XXXXXX";
    char* created = ::mkdtemp(rootTemplate);
    if (created == nullptr) {
        std::cerr << "mkdtemp failed: " << std::strerror(errno) << '\n';
        return 1;
    }
    const std::filesystem::path root(created);
    const MediaIdentity media{true, MediaKind::LittleFs, "HOST-TEMP-MKDTEMP",
                              16U * 1024U * 1024U, 16U * 1024U * 1024U};
    const WriteRequest request{true, "HOST-TEMP-MKDTEMP", "fs_fixture_20260816", false,
                               1U * 1024U * 1024U, 1U * 1024U * 1024U};
    const WritePermit permit = authorizeScratchWrite(media, request);
    if (!permit.allowed()) {
        std::filesystem::remove_all(root);
        std::cerr << "storage guard rejected host fixture\n";
        return 1;
    }
    static constexpr std::array<CommitStage, 7> kScenarios{{
        CommitStage::WritePayloads, CommitStage::SyncPayloads, CommitStage::WriteManifest,
        CommitStage::SyncManifest, CommitStage::WriteHead, CommitStage::SyncHead,
        CommitStage::Complete,
    }};
    std::vector<ScenarioResult> runs;
    std::vector<CrashScenarioResult> crashRuns;
    bool allPassed = true;
    SurveySession completeReopened;
    for (std::size_t index = 0; index < kScenarios.size(); ++index) {
        const auto scenarioRoot = root / ("scenario-" + std::to_string(index));
        ScenarioResult run = runScenario(scenarioRoot, kScenarios[index], prior, next);
        allPassed = allPassed && run.passed;
        if (kScenarios[index] == CommitStage::Complete) {
            SessionStoreWorkspace storeWorkspace;
            const SessionStoreRecoveryResult recovered =
                recoverFromStore(scenarioRoot, storeWorkspace, &completeReopened);
            allPassed = allPassed && recovered.valid() && recovered.generation == 2;
        }
        runs.push_back(run);
    }
    static constexpr std::array<CommitStage, 6> kCrashStages{{
        CommitStage::WritePayloads, CommitStage::SyncPayloads, CommitStage::WriteManifest,
        CommitStage::SyncManifest, CommitStage::WriteHead, CommitStage::SyncHead,
    }};
    for (std::size_t index = 0; index < kCrashStages.size(); ++index) {
        const auto scenarioRoot = root / ("crash-" + std::to_string(index));
        CrashScenarioResult run =
            runCrashScenario(scenarioRoot, kCrashStages[index], prior, next);
        allPassed = allPassed && run.passed;
        crashRuns.push_back(run);
    }
    std::error_code cleanupError;
    const std::uintmax_t removed = std::filesystem::remove_all(root, cleanupError);
    const bool cleaned = !cleanupError && removed > 0 && !std::filesystem::exists(root);
    allPassed = allPassed && cleaned;
    if (!writeEvidence(argv[2], runs, crashRuns, completeReopened, permit, allPassed,
                       cleaned)) {
        std::cerr << "failed to write evidence\n";
        return 1;
    }
    std::cout << "storage filesystem fixture " << (allPassed ? "passed" : "failed")
              << ": " << argv[2] << '\n';
    return allPassed ? 0 : 1;
}
