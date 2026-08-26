#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

#include "services/companion/CompanionMutationAdapter.h"

using namespace leshy1::domain::targets;
using namespace leshy1::services::companion;
using namespace leshy1::services::targets;

namespace {

int failures = 0;

#define CHECK(expression)                                                                       \
    do {                                                                                        \
        if (!(expression)) {                                                                    \
            std::cerr << __FILE__ << ':' << __LINE__ << ": check failed: " #expression << '\n'; \
            ++failures;                                                                         \
        }                                                                                       \
    } while (false)

constexpr const char* kTarget = "A1000000000000000000000000000000";
constexpr const char* kMutation = "0102030405060708090A0B0C0D0E0F10";

TargetId targetId() {
    TargetId result{};
    result.bytes[0] = 0xa1;
    return result;
}

std::string base64(const std::string& value) {
    constexpr char alphabet[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string result;
    for (std::size_t offset = 0; offset < value.size(); offset += 3U) {
        const std::size_t remaining = value.size() - offset;
        const unsigned a = static_cast<unsigned char>(value[offset]);
        const unsigned b = remaining > 1U
            ? static_cast<unsigned char>(value[offset + 1U]) : 0U;
        const unsigned c = remaining > 2U
            ? static_cast<unsigned char>(value[offset + 2U]) : 0U;
        result.push_back(alphabet[a >> 2U]);
        result.push_back(alphabet[((a & 0x03U) << 4U) | (b >> 4U)]);
        result.push_back(remaining > 1U
            ? alphabet[((b & 0x0fU) << 2U) | (c >> 6U)] : '=');
        result.push_back(remaining > 2U ? alphabet[c & 0x3fU] : '=');
    }
    return result;
}

std::string previewFrame(const char* action, const char* valueField,
                         const std::string& value,
                         std::uint32_t revision = 1) {
    return std::string(
        "{\"schema\":\"leshy.companion.request.v1\","
        "\"kind\":\"target.mutation.preview\",\"request_id\":\"p1\","
        "\"action\":\"") + action + "\",\"target_id\":\"" + kTarget +
        "\",\"expected_revision\":" + std::to_string(revision) + ",\"" +
        valueField + "\":" + value + "}";
}

std::string textPreview(const char* action, const std::string& value,
                        std::uint32_t revision = 1) {
    return previewFrame(action, "value_base64",
                        "\"" + base64(value) + "\"", revision);
}

CompanionMutationRequest parse(
    const std::string& frame,
    CompanionMutationParseStatus expected =
        CompanionMutationParseStatus::Parsed) {
    CompanionMutationRequest request{};
    const auto status = parseCompanionMutationRequest(
        frame.data(), frame.size(), &request);
    CHECK(status == expected);
    return request;
}

struct Fixture final {
    TargetCatalog targets{};
    CompanionConnection connection{};

    Fixture() {
        TargetIdentity identity{};
        identity.kind = TargetIdentityKind::WifiBssid;
        identity.length = 6;
        identity.value = {{0x10, 0x20, 0x30, 0x40, 0x50, 0x60}};
        TargetEvidenceRef evidence{};
        evidence.sourceId.bytes[0] = 0x52;
        evidence.sourceGeneration = 1;
        evidence.observationSequence = 2;
        evidence.observedMonotonicUs = 3;
        CHECK(targets.create(targetId(), identity, evidence) ==
              TargetMutationStatus::Created);

        CompanionConnectRequest request{};
        request.protocolVersion = kCompanionProtocolVersion;
        std::memcpy(request.requestId.data(), "connect", 7);
        request.requestIdLength = 7;
        request.requestedScopes = kCompanionS65MutationScopes;
        CompanionConnectionPolicy policy{};
        policy.deviceSessionScopes = kCompanionS65MutationScopes;
        policy.availableScopes = kCompanionS65MutationScopes;
        policy.availableCapabilities =
            companionMutationCapabilities(&targets);
        connection = negotiateCompanionConnection(request, policy);
        CHECK(connection.ready());
    }
};

void testAllFiveTypedActionsAndFullNotesFitOneFrame() {
    const auto favorite = parse(previewFrame(
        "target.favorite.set", "favorite", "true"));
    CHECK(favorite.action.kind == TargetActionKind::SetFavorite);
    CHECK(favorite.action.favorite);
    CHECK(favorite.action.expectedRevision == 1);

    const std::vector<std::pair<const char*, TargetActionKind>> textActions{
        {"target.name.set", TargetActionKind::SetName},
        {"target.notes.set", TargetActionKind::SetNotes},
        {"target.tag.add", TargetActionKind::AddTag},
        {"target.tag.remove", TargetActionKind::RemoveTag},
    };
    for (const auto& item : textActions) {
        const std::string value = item.second == TargetActionKind::SetNotes
            ? std::string(TargetRecord::kNotesCapacity, 'N') : "alpha";
        const std::string frame = textPreview(item.first, value);
        CHECK(frame.size() <= kCompanionMaxFrameBytes);
        const auto request = parse(frame);
        CHECK(request.action.kind == item.second);
        CHECK(request.action.textLength == value.size());
        CHECK(std::memcmp(request.action.text.data(), value.data(),
                          value.size()) == 0);
    }

    const std::string confirm = std::string(
        "{\"schema\":\"leshy.companion.request.v1\","
        "\"kind\":\"target.mutation.confirm\",\"request_id\":\"c1\","
        "\"mutation_id\":\"") + kMutation + "\"}";
    CHECK(parse(confirm).kind == CompanionMutationRequestKind::Confirm);
    std::string status = confirm;
    const std::size_t position = status.find("confirm");
    status.replace(position, std::strlen("confirm"), "status");
    CHECK(parse(status).kind == CompanionMutationRequestKind::Status);
}

void testStrictParserRejectsMalformedAndNeverPublishesPartialOutput() {
    const std::vector<std::pair<std::string, CompanionMutationParseStatus>> cases{
        {"", CompanionMutationParseStatus::Empty},
        {"{}", CompanionMutationParseStatus::MissingField},
        {previewFrame("target.favorite.set", "favorite", "true", 0),
         CompanionMutationParseStatus::InvalidNumber},
        {previewFrame("target.favorite.set", "favorite", "true") + "x",
         CompanionMutationParseStatus::MalformedJson},
        {previewFrame("target.create", "value_base64", "\"QQ==\""),
         CompanionMutationParseStatus::InvalidAction},
        {textPreview("target.name.set", std::string(49, 'N')),
         CompanionMutationParseStatus::InvalidValue},
        {textPreview("target.tag.add", ""),
         CompanionMutationParseStatus::InvalidValue},
        {previewFrame("target.name.set", "value_base64", "\"Zh==\""),
         CompanionMutationParseStatus::InvalidBase64},
        {previewFrame("target.name.set", "favorite", "true"),
         CompanionMutationParseStatus::MissingField},
        {std::string(
             "{\"schema\":\"leshy.companion.request.v1\","
             "\"kind\":\"target.mutation.status\",\"request_id\":\"s\","
             "\"mutation_id\":\"00000000000000000000000000000000\"}"),
         CompanionMutationParseStatus::InvalidIdentifier},
    };
    for (const auto& item : cases) {
        CompanionMutationRequest output{};
        output.action.expectedRevision = 77;
        const auto status = parseCompanionMutationRequest(
            item.first.data(), item.first.size(), &output);
        CHECK(status == item.second);
        CHECK(output.action.expectedRevision == 77);
        CHECK(std::strcmp(companionMutationParseReason(status), "none") != 0);
    }

    const std::string golden = textPreview("target.name.set", "alpha");
    for (std::size_t length = 0; length < golden.size(); ++length) {
        CompanionMutationRequest output{};
        output.action.expectedRevision = 91;
        CHECK(parseCompanionMutationRequest(golden.data(), length, &output) !=
              CompanionMutationParseStatus::Parsed);
        CHECK(output.action.expectedRevision == 91);
    }

    std::string oversized(kCompanionMaxFrameBytes + 1U, 'x');
    CompanionMutationRequest output{};
    CHECK(parseCompanionMutationRequest(
              oversized.data(), oversized.size(), &output) ==
          CompanionMutationParseStatus::TooLarge);
}

void testPreviewUsesExactRevisionAndExplicitGrant() {
    Fixture fixture;
    auto request = parse(previewFrame(
        "target.favorite.set", "favorite", "true"));
    auto assessment = assessCompanionMutationPreview(
        fixture.connection, &fixture.targets, request);
    CHECK(assessment.status == CompanionMutationStatus::Ready);
    CHECK(assessment.action.revision == 2);
    CHECK(!fixture.targets.find(targetId())->favorite);

    request.action.expectedRevision = 9;
    assessment = assessCompanionMutationPreview(
        fixture.connection, &fixture.targets, request);
    CHECK(assessment.status == CompanionMutationStatus::RevisionConflict);
    CHECK(assessment.action.revision == 1);

    request.action.expectedRevision = 1;
    request.action.favorite = false;
    CHECK(assessCompanionMutationPreview(
              fixture.connection, &fixture.targets, request).status ==
          CompanionMutationStatus::Unchanged);

    CompanionConnection denied = fixture.connection;
    denied.grantedCapabilities = 0;
    request.action.favorite = true;
    CHECK(assessCompanionMutationPreview(
              denied, &fixture.targets, request).status ==
          CompanionMutationStatus::CapabilityDenied);
    CHECK(assessCompanionMutationPreview(
              fixture.connection, nullptr, request).status ==
          CompanionMutationStatus::CapabilityUnavailable);
}

void testDeterministicBoundedResponses() {
    CompanionMutationResponse response{};
    response.kind = CompanionMutationRequestKind::Preview;
    std::memcpy(response.requestId.data(), "p1", 2);
    response.requestIdLength = 2;
    response.status = CompanionMutationStatus::Ready;
    response.state = CompanionMutationState::Previewed;
    for (std::size_t index = 0; index < response.mutationId.size(); ++index) {
        response.mutationId[index] = static_cast<std::uint8_t>(index + 1U);
    }
    response.actionKind = TargetActionKind::SetFavorite;
    response.targetId = targetId();
    response.expectedRevision = 1;
    response.targetRevision = 2;
    response.stateGeneration = 7;

    std::array<char, kCompanionMaxFrameBytes + 1U> output{};
    std::size_t length = 0;
    CHECK(encodeCompanionMutationResponse(
        response, output.data(), output.size(), &length));
    CHECK(length <= kCompanionMaxFrameBytes);
    CHECK(std::strstr(output.data(),
                      "\"state\":\"previewed\"") != nullptr);
    CHECK(std::strstr(output.data(), kMutation) != nullptr);
    CHECK(std::strstr(output.data(),
                      "\"action\":\"target.favorite.set\"") != nullptr);

    std::array<char, 20> small{};
    small.fill('Q');
    length = 99;
    CHECK(!encodeCompanionMutationResponse(
        response, small.data(), small.size(), &length));
    CHECK(length == 0);
    for (const char value : small) CHECK(value == 'Q');

    CHECK(encodeCompanionMutationParseError(
        CompanionMutationParseStatus::InvalidBase64,
        output.data(), output.size(), &length));
    CHECK(std::strstr(output.data(), "\"reason\":\"invalid_base64\"") !=
          nullptr);
}

}  // namespace

int main() {
    testAllFiveTypedActionsAndFullNotesFitOneFrame();
    testStrictParserRejectsMalformedAndNeverPublishesPartialOutput();
    testPreviewUsesExactRevisionAndExplicitGrant();
    testDeterministicBoundedResponses();
    if (failures != 0) {
        std::cerr << failures << " companion mutation check(s) failed\n";
        return EXIT_FAILURE;
    }
    std::cout << "companion mutation adapter tests passed\n";
    return EXIT_SUCCESS;
}
