#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

#include "services/companion/CompanionReadAdapter.h"

using namespace leshy1::domain::targets;
using namespace leshy1::services::companion;
using namespace leshy1::services::survey;

namespace {

int failures = 0;

#define CHECK(expression)                                                                       \
    do {                                                                                        \
        if (!(expression)) {                                                                    \
            std::cerr << __FILE__ << ':' << __LINE__ << ": check failed: " #expression << '\n'; \
            ++failures;                                                                         \
        }                                                                                       \
    } while (false)

constexpr const char* kSourceA = "01000000000000000000000000000000";
constexpr const char* kSourceB = "02000000000000000000000000000000";
constexpr const char* kTarget = "A1000000000000000000000000000000";

SourceId sourceId(std::uint8_t first) {
    SourceId result{};
    result.bytes[0] = first;
    return result;
}

TargetId targetId(std::uint8_t first) {
    TargetId result{};
    result.bytes[0] = first;
    return result;
}

struct Fixture final {
    SurveySession baseline{};
    SurveySession current{};
    TargetCatalog targets{};
    TargetComparisonResult comparison{};
    CompanionReadContext context{};
    CompanionConnection connection{};

    Fixture() {
        CHECK(baseline.start("baseline", 1000) == SessionStatus::Started);
        CHECK(baseline.stop(2000) == SessionStatus::Stopped);
        CHECK(current.start("current", 3000) == SessionStatus::Started);
        CHECK(current.stop(4000) == SessionStatus::Stopped);

        TargetIdentity identity{};
        identity.kind = TargetIdentityKind::WifiBssid;
        identity.length = 6;
        identity.value = {{0x10, 0x20, 0x30, 0x40, 0x50, 0x60}};
        TargetEvidenceRef evidence{};
        evidence.sourceId = sourceId(2);
        evidence.sourceGeneration = 12;
        evidence.observationSequence = 7;
        evidence.observedMonotonicUs = 3500;
        CHECK(targets.create(targetId(0xa1), identity, evidence) ==
              TargetMutationStatus::Created);
        CHECK(targets.setName(targetId(0xa1), "Alpha", 5) ==
              TargetMutationStatus::Applied);
        std::array<char, TargetRecord::kNotesCapacity> notes{};
        notes.fill('N');
        CHECK(targets.setNotes(targetId(0xa1), notes.data(), notes.size()) ==
              TargetMutationStatus::Applied);
        for (std::size_t index = 0; index < TargetRecord::kTagCountCapacity;
             ++index) {
            std::array<char, TargetRecord::kTagCapacity> tag{};
            tag.fill(static_cast<char>('A' + index));
            CHECK(targets.addTag(targetId(0xa1), tag.data(), tag.size()) ==
                  TargetMutationStatus::Applied);
        }

        comparison.status = TargetComparisonStatus::Compared;
        comparison.baseline = {sourceId(1), 11};
        comparison.current = {sourceId(2), 12};
        comparison.size = 1;
        comparison.changed = 1;
        comparison.items[0].targetId = targetId(0xa1);
        comparison.items[0].classification = TargetComparisonClass::Changed;
        comparison.items[0].changes =
            targetChangeMask(TargetChangeKind::Signal);
        comparison.items[0].baselineEvidenceCount = 1;
        comparison.items[0].currentEvidenceCount = 1;

        context.sessions[0] = {{sourceId(1), 11}, &baseline};
        context.sessions[1] = {{sourceId(2), 12}, &current};
        context.sessionCount = 2;
        context.targets = &targets;
        context.comparison = &comparison;

        CompanionConnectRequest connect{};
        connect.protocolVersion = 1;
        std::memcpy(connect.requestId.data(), "connect-1", 9);
        connect.requestIdLength = 9;
        connect.requestedScopes = kCompanionS65ReadScopes;
        CompanionConnectionPolicy policy{};
        policy.deviceSessionScopes = kCompanionS65ReadScopes;
        policy.availableScopes = kCompanionS65ReadScopes;
        policy.availableCapabilities = companionReadCapabilities(context);
        connection = negotiateCompanionConnection(connect, policy);
        CHECK(connection.ready());
    }
};

CompanionReadRequest parse(const std::string& frame,
                           CompanionReadParseStatus expected =
                               CompanionReadParseStatus::Parsed) {
    CompanionReadRequest request{};
    const CompanionReadParseStatus status = parseCompanionReadRequest(
        frame.data(), frame.size(), &request);
    CHECK(status == expected);
    return request;
}

std::string encode(const Fixture& fixture,
                   const CompanionReadRequest& request) {
    std::array<char, kCompanionMaxFrameBytes + 1U> output{};
    std::size_t length = 0;
    CHECK(encodeCompanionReadResponse(
        fixture.connection, fixture.context, request, output.data(),
        output.size(), &length));
    CHECK(length <= kCompanionMaxFrameBytes);
    CHECK(output[length] == '\0');
    return std::string(output.data(), length);
}

std::string sessionListFrame() {
    return "{\"schema\":\"leshy.companion.request.v1\","
           "\"kind\":\"session.list\",\"request_id\":\"s-list\","
           "\"offset\":0}";
}

void testExactFieldSetsAndOrderIndependentParser() {
    const CompanionReadRequest list = parse(sessionListFrame());
    CHECK(list.kind == CompanionReadKind::SessionList);
    CHECK(list.offset == 0);
    CHECK(std::strcmp(list.requestId.data(), "s-list") == 0);

    const CompanionReadRequest detail = parse(
        std::string("{\"generation\":11,\"request_id\":\"detail_1\","
                    "\"source_id\":\"") + kSourceA +
        "\",\"kind\":\"session.detail\",\"schema\":"
        "\"leshy.companion.request.v1\"}");
    CHECK(detail.kind == CompanionReadKind::SessionDetail);
    CHECK(detail.source.id.bytes[0] == 1);
    CHECK(detail.source.generation == 11);

    const CompanionReadRequest target = parse(
        std::string("{\"schema\":\"leshy.companion.request.v1\","
                    "\"kind\":\"target.detail\",\"request_id\":\"td\","
                    "\"target_id\":\"") + kTarget +
        "\",\"section\":\"evidence\",\"offset\":0}");
    CHECK(target.kind == CompanionReadKind::TargetDetail);
    CHECK(target.section == CompanionTargetDetailSection::Evidence);

    const CompanionReadRequest compare = parse(
        std::string("{\"schema\":\"leshy.companion.request.v1\","
                    "\"kind\":\"target.compare\",\"request_id\":\"cmp\","
                    "\"baseline_source_id\":\"") + kSourceA +
        "\",\"baseline_generation\":11,\"current_source_id\":\"" +
        kSourceB + "\",\"current_generation\":12,\"offset\":0}");
    CHECK(compare.kind == CompanionReadKind::TargetCompare);
    CHECK(compare.baseline.generation == 11);
    CHECK(compare.current.generation == 12);
}

void testMalformedFramesFailWithoutPublishingPartialRequest() {
    const std::vector<std::pair<std::string, CompanionReadParseStatus>> cases{
        {"", CompanionReadParseStatus::Empty},
        {"{}", CompanionReadParseStatus::MissingField},
        {"[]", CompanionReadParseStatus::MalformedJson},
        {"{\"schema\":\"leshy.companion.request.v2\",\"kind\":"
         "\"session.list\",\"request_id\":\"x\",\"offset\":0}",
         CompanionReadParseStatus::UnsupportedSchema},
        {"{\"schema\":\"leshy.companion.request.v1\",\"kind\":"
         "\"target.mutate\",\"request_id\":\"x\",\"offset\":0}",
         CompanionReadParseStatus::UnsupportedKind},
        {"{\"schema\":\"leshy.companion.request.v1\",\"kind\":"
         "\"session.list\",\"request_id\":\"bad id\",\"offset\":0}",
         CompanionReadParseStatus::InvalidRequestId},
        {"{\"schema\":\"leshy.companion.request.v1\",\"kind\":"
         "\"session.list\",\"request_id\":\"x\",\"offset\":256}",
         CompanionReadParseStatus::InvalidNumber},
        {"{\"schema\":\"leshy.companion.request.v1\",\"kind\":"
         "\"session.list\",\"request_id\":\"x\",\"offset\":0,"
         "\"target_id\":\"A1000000000000000000000000000000\"}",
         CompanionReadParseStatus::FieldNotAllowed},
        {"{\"schema\":\"leshy.companion.request.v1\",\"kind\":"
         "\"session.list\",\"request_id\":\"x\",\"offset\":0,"
         "\"offset\":1}", CompanionReadParseStatus::DuplicateField},
        {"{\"schema\":\"leshy.companion.request.v1\",\"kind\":"
         "\"target.detail\",\"request_id\":\"x\",\"target_id\":"
         "\"A1000000000000000000000000000000\",\"section\":\"raw\","
         "\"offset\":0}", CompanionReadParseStatus::InvalidSection},
        {"{\"schema\":\"leshy.companion.request.v1\",\"kind\":"
         "\"session.detail\",\"request_id\":\"x\",\"source_id\":"
         "\"00000000000000000000000000000000\",\"generation\":1}",
         CompanionReadParseStatus::InvalidIdentifier},
    };
    for (const auto& item : cases) {
        CompanionReadRequest output{};
        output.offset = 77;
        output.requestId[0] = 'Q';
        const CompanionReadParseStatus status = parseCompanionReadRequest(
            item.first.data(), item.first.size(), &output);
        CHECK(status == item.second);
        CHECK(output.offset == 77);
        CHECK(output.requestId[0] == 'Q');
        CHECK(std::strcmp(companionReadParseReason(status), "none") != 0);
    }
    CompanionReadRequest output{};
    std::string oversized(kCompanionMaxFrameBytes + 1U, 'x');
    CHECK(parseCompanionReadRequest(
              oversized.data(), oversized.size(), &output) ==
          CompanionReadParseStatus::TooLarge);
}

void testEveryTruncatedFrameIsRejected() {
    const std::string golden = sessionListFrame();
    for (std::size_t length = 0; length < golden.size(); ++length) {
        CompanionReadRequest output{};
        output.offset = 91;
        const auto status = parseCompanionReadRequest(
            golden.data(), length, &output);
        CHECK(status != CompanionReadParseStatus::Parsed);
        CHECK(output.offset == 91);
    }
}

void testCapabilitiesReflectOnlyTheCurrentSharedSnapshot() {
    CompanionReadContext empty{};
    CHECK(companionReadCapabilities(empty) == 0);

    Fixture fixture;
    CHECK(companionReadCapabilities(fixture.context) ==
          kCompanionReadCapabilities);
    CompanionReadContext sessions = fixture.context;
    sessions.targets = nullptr;
    sessions.comparison = nullptr;
    CHECK(companionReadCapabilities(sessions) ==
          (companionCapabilityMask(CompanionCapability::SessionList) |
           companionCapabilityMask(CompanionCapability::SessionDetail)));
    CompanionReadContext targets = fixture.context;
    targets.comparison = nullptr;
    CHECK((companionReadCapabilities(targets) &
           companionCapabilityMask(CompanionCapability::TargetCompare)) == 0);
}

void testAllReadOnlyProjectionsStayBounded() {
    Fixture fixture;
    const std::string sessions = encode(fixture, parse(sessionListFrame()));
    CHECK(sessions.find(kSourceA) != std::string::npos);
    CHECK(sessions.find(kSourceB) != std::string::npos);
    CHECK(sessions.find("\"session_id\":\"baseline\"") != std::string::npos);

    const std::string sessionDetail = encode(fixture, parse(
        std::string("{\"schema\":\"leshy.companion.request.v1\","
                    "\"kind\":\"session.detail\",\"request_id\":\"sd\","
                    "\"source_id\":\"") + kSourceA +
        "\",\"generation\":11}"));
    CHECK(sessionDetail.find("\"state\":\"stopped\"") != std::string::npos);

    const std::string targets = encode(fixture, parse(
        "{\"schema\":\"leshy.companion.request.v1\",\"kind\":"
        "\"target.list\",\"request_id\":\"tl\",\"offset\":0}"));
    CHECK(targets.find(kTarget) != std::string::npos);
    CHECK(targets.find("416C706861") != std::string::npos);

    const std::array<const char*, 5> sections{{
        "summary", "notes", "tags", "identities", "evidence"}};
    for (const char* section : sections) {
        const std::string frame =
            std::string("{\"schema\":\"leshy.companion.request.v1\","
                        "\"kind\":\"target.detail\",\"request_id\":\"td\","
                        "\"target_id\":\"") + kTarget +
            "\",\"section\":\"" + section + "\",\"offset\":0}";
        const std::string detail = encode(fixture, parse(frame));
        CHECK(detail.find(std::string("\"section\":\"") + section + "\"") !=
              std::string::npos);
        CHECK(detail.size() <= kCompanionMaxFrameBytes);
    }

    const std::string notesSecond = encode(fixture, parse(
        std::string("{\"schema\":\"leshy.companion.request.v1\","
                    "\"kind\":\"target.detail\",\"request_id\":\"td2\","
                    "\"target_id\":\"") + kTarget +
        "\",\"section\":\"notes\",\"offset\":80}"));
    CHECK(notesSecond.find("\"offset\":80") != std::string::npos);
    CHECK(notesSecond.find("\"next_offset\":null") != std::string::npos);
    CHECK(notesSecond.size() <= kCompanionMaxFrameBytes);

    const std::string tagsSecond = encode(fixture, parse(
        std::string("{\"schema\":\"leshy.companion.request.v1\","
                    "\"kind\":\"target.detail\",\"request_id\":\"td3\","
                    "\"target_id\":\"") + kTarget +
        "\",\"section\":\"tags\",\"offset\":2}"));
    CHECK(tagsSecond.find("\"offset\":2") != std::string::npos);
    CHECK(tagsSecond.find("\"next_offset\":null") != std::string::npos);
    CHECK(tagsSecond.size() <= kCompanionMaxFrameBytes);

    const std::string compareFrame =
        std::string("{\"schema\":\"leshy.companion.request.v1\","
                    "\"kind\":\"target.compare\",\"request_id\":\"cmp\","
                    "\"baseline_source_id\":\"") + kSourceA +
        "\",\"baseline_generation\":11,\"current_source_id\":\"" +
        kSourceB + "\",\"current_generation\":12,\"offset\":0}";
    const std::string compare = encode(fixture, parse(compareFrame));
    CHECK(compare.find("\"class\":\"changed\"") != std::string::npos);
    CHECK(compare.find("\"changed\":1") != std::string::npos);
}

void testAuthorizationAndExactCoordinatesFailClosed() {
    Fixture fixture;
    const CompanionReadRequest targetList = parse(
        "{\"schema\":\"leshy.companion.request.v1\",\"kind\":"
        "\"target.list\",\"request_id\":\"tl\",\"offset\":0}");
    CompanionConnection disconnected{};
    std::array<char, kCompanionMaxFrameBytes + 1U> output{};
    std::size_t length = 0;
    CHECK(encodeCompanionReadResponse(
        disconnected, fixture.context, targetList, output.data(),
        output.size(), &length));
    CHECK(std::strstr(output.data(), "\"reason\":\"not_connected\"") != nullptr);

    CompanionConnection sessionOnly = fixture.connection;
    sessionOnly.grantedCapabilities =
        companionCapabilityMask(CompanionCapability::SessionList);
    CHECK(encodeCompanionReadResponse(
        sessionOnly, fixture.context, targetList, output.data(),
        output.size(), &length));
    CHECK(std::strstr(output.data(), "\"reason\":\"capability_denied\"") != nullptr);

    CompanionReadContext noTargets = fixture.context;
    noTargets.targets = nullptr;
    noTargets.comparison = nullptr;
    CHECK(encodeCompanionReadResponse(
        fixture.connection, noTargets, targetList, output.data(),
        output.size(), &length));
    CHECK(std::strstr(output.data(),
                      "\"reason\":\"capability_unavailable\"") != nullptr);

    const CompanionReadRequest missingSession = parse(
        "{\"schema\":\"leshy.companion.request.v1\",\"kind\":"
        "\"session.detail\",\"request_id\":\"sd\",\"source_id\":"
        "\"03000000000000000000000000000000\",\"generation\":11}");
    CHECK(encodeCompanionReadResponse(
        fixture.connection, fixture.context, missingSession, output.data(),
        output.size(), &length));
    CHECK(std::strstr(output.data(), "\"reason\":\"not_found\"") != nullptr);

    const CompanionReadRequest invalidOffset = parse(
        std::string("{\"schema\":\"leshy.companion.request.v1\",\"kind\":"
                    "\"target.detail\",\"request_id\":\"bad-offset\","
                    "\"target_id\":\"") + kTarget +
        "\",\"section\":\"summary\",\"offset\":1}");
    CHECK(encodeCompanionReadResponse(
        fixture.connection, fixture.context, invalidOffset, output.data(),
        output.size(), &length));
    CHECK(std::strstr(output.data(),
                      "\"reason\":\"offset_out_of_range\"") != nullptr);
}

void testAllOrNothingEncodingAndParseErrors() {
    Fixture fixture;
    const CompanionReadRequest request = parse(sessionListFrame());
    std::array<char, 32> small{};
    small.fill('Q');
    std::size_t length = 99;
    CHECK(!encodeCompanionReadResponse(
        fixture.connection, fixture.context, request, small.data(),
        small.size(), &length));
    CHECK(length == 0);
    for (const char value : small) CHECK(value == 'Q');

    std::array<char, kCompanionMaxFrameBytes + 1U> output{};
    CHECK(encodeCompanionReadParseError(
        CompanionReadParseStatus::UnknownField, output.data(), output.size(),
        &length));
    CHECK(std::strstr(output.data(), "\"kind\":\"error\"") != nullptr);
    CHECK(std::strstr(output.data(), "\"reason\":\"unknown_field\"") != nullptr);
    CHECK(!encodeCompanionReadParseError(
        CompanionReadParseStatus::Parsed, output.data(), output.size(),
        &length));
}

}  // namespace

int main() {
    static_assert(sizeof(CompanionReadRequest) <= 128,
                  "read request must remain a small bounded value");
    testExactFieldSetsAndOrderIndependentParser();
    testMalformedFramesFailWithoutPublishingPartialRequest();
    testEveryTruncatedFrameIsRejected();
    testCapabilitiesReflectOnlyTheCurrentSharedSnapshot();
    testAllReadOnlyProjectionsStayBounded();
    testAuthorizationAndExactCoordinatesFailClosed();
    testAllOrNothingEncodingAndParseErrors();
    if (failures != 0) {
        std::cerr << failures << " companion read adapter checks failed\n";
        return EXIT_FAILURE;
    }
    std::cout << "companion read adapter checks passed\n";
    return EXIT_SUCCESS;
}
