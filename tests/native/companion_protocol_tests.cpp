#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

#include "services/companion/CompanionProtocol.h"

using namespace leshy1::services::companion;

namespace {

int failures = 0;

#define CHECK(expression)                                                                       \
    do {                                                                                        \
        if (!(expression)) {                                                                    \
            std::cerr << __FILE__ << ':' << __LINE__ << ": check failed: " #expression << '\n'; \
            ++failures;                                                                         \
        }                                                                                       \
    } while (false)

constexpr const char* kReadConnect =
    "{\"schema\":\"leshy.companion.request.v1\",\"kind\":\"connect\","
    "\"request_id\":\"desktop-01\",\"protocol\":1,\"scopes\":["
    "\"session.read\",\"target.read\",\"target.compare\"]}";

CompanionConnectRequest parse(const std::string& frame,
                              CompanionParseStatus expected =
                                  CompanionParseStatus::Parsed) {
    CompanionConnectRequest request{};
    const CompanionParseStatus status = parseCompanionConnectRequest(
        frame.data(), frame.size(), &request);
    CHECK(status == expected);
    return request;
}

CompanionConnection readyConnection() {
    const CompanionConnectRequest request = parse(kReadConnect);
    CompanionConnectionPolicy policy{};
    policy.deviceSessionScopes = kCompanionS65ReadScopes;
    policy.availableScopes = kCompanionS65ReadScopes;
    policy.availableCapabilities = kCompanionReadCapabilities;
    return negotiateCompanionConnection(request, policy);
}

void testBoundedOrderIndependentConnectParser() {
    const CompanionConnectRequest request = parse(kReadConnect);
    CHECK(request.protocolVersion == 1);
    CHECK(std::strcmp(request.requestId.data(), "desktop-01") == 0);
    CHECK(request.requestIdLength == 10);
    CHECK(request.requestedScopes == kCompanionS65ReadScopes);

    const std::string reordered =
        " \n{ \"scopes\" : [\"target.read\", \"session.read\"],"
        "\"protocol\":1,\"request_id\":\"web_2\",\"kind\":\"connect\","
        "\"schema\":\"leshy.companion.request.v1\" }\r\n";
    const CompanionConnectRequest second = parse(reordered);
    CHECK(second.requestedScopes ==
          (companionScopeMask(CompanionScope::SessionRead) |
           companionScopeMask(CompanionScope::TargetRead)));
    CHECK(std::strcmp(second.requestId.data(), "web_2") == 0);
}

void testParserFailsClosedWithoutPublishingPartialOutput() {
    const std::vector<std::pair<std::string, CompanionParseStatus>> cases{
        {"", CompanionParseStatus::Empty},
        {"{}", CompanionParseStatus::MissingField},
        {"[]", CompanionParseStatus::MalformedJson},
        {"{\"schema\":\"leshy.companion.request.v2\",\"kind\":\"connect\","
         "\"request_id\":\"x\",\"protocol\":1,\"scopes\":[\"session.read\"]}",
         CompanionParseStatus::UnsupportedSchema},
        {"{\"schema\":\"leshy.companion.request.v1\",\"kind\":\"invoke\","
         "\"request_id\":\"x\",\"protocol\":1,\"scopes\":[\"session.read\"]}",
         CompanionParseStatus::UnsupportedKind},
        {"{\"schema\":\"leshy.companion.request.v1\",\"kind\":\"connect\","
         "\"request_id\":\"x\",\"protocol\":2,\"scopes\":[\"session.read\"]}",
         CompanionParseStatus::UnsupportedProtocol},
        {"{\"schema\":\"leshy.companion.request.v1\",\"kind\":\"connect\","
         "\"request_id\":\"bad id\",\"protocol\":1,\"scopes\":[\"session.read\"]}",
         CompanionParseStatus::InvalidRequestId},
        {"{\"schema\":\"leshy.companion.request.v1\",\"kind\":\"connect\","
         "\"request_id\":\"x\",\"protocol\":1,\"scopes\":[]}",
         CompanionParseStatus::EmptyScopeSet},
        {"{\"schema\":\"leshy.companion.request.v1\",\"kind\":\"connect\","
         "\"request_id\":\"x\",\"protocol\":1,\"scopes\":[\"radio.tx\"]}",
         CompanionParseStatus::UnknownScope},
        {"{\"schema\":\"leshy.companion.request.v1\",\"kind\":\"connect\","
         "\"request_id\":\"x\",\"protocol\":1,\"scopes\":["
         "\"session.read\",\"session.read\"]}",
         CompanionParseStatus::DuplicateScope},
        {"{\"schema\":\"leshy.companion.request.v1\",\"schema\":"
         "\"leshy.companion.request.v1\",\"kind\":\"connect\","
         "\"request_id\":\"x\",\"protocol\":1,\"scopes\":[\"session.read\"]}",
         CompanionParseStatus::DuplicateField},
        {"{\"schema\":\"leshy.companion.request.v1\",\"kind\":\"connect\","
         "\"request_id\":\"x\",\"protocol\":1,\"scopes\":[\"session.read\"],"
         "\"debug\":true}", CompanionParseStatus::UnknownField},
        {"{\"schema\":\"leshy.companion.request.v1\",\"kind\":\"connect\","
         "\"request_id\":\"x\\u0031\",\"protocol\":1,\"scopes\":["
         "\"session.read\"]}", CompanionParseStatus::MalformedJson},
        {std::string(kReadConnect) + "x", CompanionParseStatus::MalformedJson},
    };

    for (const auto& item : cases) {
        CompanionConnectRequest output{};
        output.protocolVersion = 77;
        output.requestId[0] = 'Q';
        output.requestIdLength = 1;
        output.requestedScopes = 0x55;
        const CompanionParseStatus status = parseCompanionConnectRequest(
            item.first.data(), item.first.size(), &output);
        CHECK(status == item.second);
        CHECK(output.protocolVersion == 77);
        CHECK(output.requestId[0] == 'Q');
        CHECK(output.requestIdLength == 1);
        CHECK(output.requestedScopes == 0x55);
        CHECK(std::strcmp(companionParseReason(status), "none") != 0);
    }

    std::string oversized(kCompanionMaxFrameBytes + 1U, 'x');
    CHECK(parseCompanionConnectRequest(
              oversized.data(), oversized.size(),
              static_cast<CompanionConnectRequest*>(nullptr)) ==
          CompanionParseStatus::InvalidArgument);
    CompanionConnectRequest output{};
    CHECK(parseCompanionConnectRequest(
              oversized.data(), oversized.size(), &output) ==
          CompanionParseStatus::TooLarge);
}

void testEveryTruncatedFrameIsRejected() {
    const std::string golden = kReadConnect;
    for (std::size_t length = 0; length < golden.size(); ++length) {
        CompanionConnectRequest output{};
        output.protocolVersion = 91;
        const CompanionParseStatus status = parseCompanionConnectRequest(
            golden.data(), length, &output);
        CHECK(status != CompanionParseStatus::Parsed);
        CHECK(output.protocolVersion == 91);
    }
}

void testScopesNeverExceedTheBoundDeviceSession() {
    const CompanionConnectRequest request = parse(kReadConnect);
    CompanionConnectionPolicy policy{};
    CompanionConnection denied = negotiateCompanionConnection(request, policy);
    CHECK(denied.status == CompanionConnectionStatus::ScopeDenied);
    CHECK(!denied.ready());
    CHECK(denied.grantedScopes == 0);

    policy.deviceSessionScopes = kCompanionS65ReadScopes;
    policy.availableScopes = kCompanionS65ReadScopes;
    policy.availableCapabilities = kCompanionReadCapabilities;
    CompanionConnection ready = negotiateCompanionConnection(request, policy);
    CHECK(ready.ready());
    CHECK(ready.grantedScopes == request.requestedScopes);
    CHECK(ready.grantedCapabilities == kCompanionReadCapabilities);

    CompanionConnectRequest compareOnly = request;
    compareOnly.requestedScopes =
        companionScopeMask(CompanionScope::TargetCompare);
    policy.deviceSessionScopes = kCompanionKnownScopes;
    policy.availableScopes = kCompanionKnownScopes;
    CompanionConnection missing =
        negotiateCompanionConnection(compareOnly, policy);
    CHECK(missing.status ==
          CompanionConnectionStatus::ScopeDependencyMissing);
    CHECK(missing.grantedScopes == 0);

    CompanionConnectRequest mutation = request;
    mutation.requestedScopes =
        companionScopeMask(CompanionScope::TargetRead) |
        companionScopeMask(CompanionScope::TargetMutate);
    policy.deviceSessionScopes = kCompanionKnownScopes;
    policy.availableScopes = kCompanionS65ReadScopes;
    CompanionConnection unavailable =
        negotiateCompanionConnection(mutation, policy);
    CHECK(unavailable.status == CompanionConnectionStatus::ScopeUnavailable);
    CHECK(unavailable.grantedScopes == 0);
}

void testCapabilitiesAreTruthfulAndActionBound() {
    CHECK(companionCapabilityCount() == 10);
    const CompanionCapabilityDescriptor* compare = nullptr;
    std::size_t readOnlyCount = 0;
    std::size_t mutationCount = 0;
    for (std::size_t index = 0; index < companionCapabilityCount(); ++index) {
        const CompanionCapabilityDescriptor* capability =
            companionCapability(index);
        CHECK(capability != nullptr);
        CHECK(capability->id != nullptr);
        if (capability->readOnly) {
            ++readOnlyCount;
        } else {
            ++mutationCount;
            CHECK(capability->actionId != nullptr);
            CHECK(capability->requestSchemaVersion == 1);
            CHECK(capability->resultSchemaVersion == 1);
            CHECK((capability->requiredScopes & kCompanionS65MutationScopes) ==
                  kCompanionS65MutationScopes);
        }
        if (std::strcmp(capability->id, "target.compare") == 0) {
            compare = capability;
        }
    }
    CHECK(companionCapability(companionCapabilityCount()) == nullptr);
    CHECK(readOnlyCount == 5);
    CHECK(mutationCount == 5);
    CHECK(compare != nullptr);
    CHECK(std::strcmp(compare->actionId, "target.compare") == 0);
    CHECK(compare->requestSchemaVersion == 1);
    CHECK(compare->resultSchemaVersion == 1);
    CHECK(!companionCapabilityGranted(
        *compare, kCompanionKnownCapabilities,
        companionScopeMask(CompanionScope::TargetCompare)));
    CHECK(!companionCapabilityGranted(
        *compare, 0, kCompanionS65ReadScopes));
    CHECK(companionCapabilityGranted(
        *compare, kCompanionKnownCapabilities, kCompanionS65ReadScopes));
}

void testDeterministicUsbAndWebResponses() {
    const CompanionConnection connection = readyConnection();
    CHECK(connection.ready());
    std::array<char, kCompanionMaxFrameBytes + 1U> output{};
    std::size_t length = 0;
    CHECK(encodeCompanionConnectResponse(
        connection, CompanionTransport::UsbSerial, output.data(),
        output.size(), &length));
    const std::string expected =
        "{\"schema\":\"leshy.companion.response.v1\",\"kind\":\"connect\","
        "\"request_id\":\"desktop-01\",\"status\":\"ready\",\"reason\":\"none\","
        "\"protocol\":1,\"transport\":\"usb_serial_ndjson\",\"scopes\":["
        "\"session.read\",\"target.read\",\"target.compare\"],\"capabilities\":["
        "\"session.list\",\"session.detail\",\"target.list\",\"target.detail\","
        "\"target.compare\"],\"max_frame_bytes\":512}\n";
    CHECK(std::string(output.data(), length) == expected);
    CHECK(output[length] == '\0');
    CHECK(length <= kCompanionMaxFrameBytes);

    CHECK(encodeCompanionConnectResponse(
        connection, CompanionTransport::LocalWeb, output.data(),
        output.size(), &length));
    CHECK(std::strstr(output.data(),
                      "\"transport\":\"local_web_json\"") != nullptr);

    std::array<char, 24> tooSmall{};
    tooSmall.fill('Q');
    length = 99;
    CHECK(!encodeCompanionConnectResponse(
        connection, CompanionTransport::UsbSerial, tooSmall.data(),
        tooSmall.size(), &length));
    CHECK(length == 0);
    for (const char value : tooSmall) CHECK(value == 'Q');
}

void testMutationConnectionResponseFitsTheCommonFrame() {
    const std::string frame =
        "{\"schema\":\"leshy.companion.request.v1\",\"kind\":\"connect\","
        "\"request_id\":\"mutate-1\",\"protocol\":1,\"scopes\":["
        "\"target.read\",\"target.mutate\"]}";
    const CompanionConnectRequest request = parse(frame);
    CompanionConnectionPolicy policy{};
    policy.deviceSessionScopes = kCompanionS65MutationScopes;
    policy.availableScopes = kCompanionS65MutationScopes;
    policy.availableCapabilities = kCompanionKnownCapabilities;
    const CompanionConnection connection =
        negotiateCompanionConnection(request, policy);
    CHECK(connection.ready());
    CHECK(connection.grantedCapabilities ==
          (companionCapabilityMask(CompanionCapability::TargetList) |
           companionCapabilityMask(CompanionCapability::TargetDetail) |
           kCompanionTargetMutationCapabilities));
    std::array<char, kCompanionMaxFrameBytes + 1U> output{};
    std::size_t length = 0;
    CHECK(encodeCompanionConnectResponse(
        connection, CompanionTransport::UsbSerial,
        output.data(), output.size(), &length));
    CHECK(length <= kCompanionMaxFrameBytes);
    CHECK(std::strstr(output.data(), "\"target.favorite.set\"") != nullptr);
    CHECK(std::strstr(output.data(), "\"target.tag.remove\"") != nullptr);
}

void testDeniedResponseDisclosesNoCapabilities() {
    const CompanionConnectRequest request = parse(kReadConnect);
    CompanionConnectionPolicy policy{};
    const CompanionConnection connection =
        negotiateCompanionConnection(request, policy);
    std::array<char, kCompanionMaxFrameBytes + 1U> output{};
    std::size_t length = 0;
    CHECK(encodeCompanionConnectResponse(
        connection, CompanionTransport::UsbSerial, output.data(),
        output.size(), &length));
    CHECK(std::strstr(output.data(), "\"status\":\"denied\"") != nullptr);
    CHECK(std::strstr(output.data(), "\"reason\":\"scope_denied\"") != nullptr);
    CHECK(std::strstr(output.data(), "\"scopes\":[]") != nullptr);
    CHECK(std::strstr(output.data(), "\"capabilities\":[]") != nullptr);
}

void testScopesDoNotInventUnwiredCapabilities() {
    const CompanionConnectRequest request = parse(kReadConnect);
    CompanionConnectionPolicy policy{};
    policy.deviceSessionScopes = kCompanionS65ReadScopes;
    policy.availableScopes = kCompanionS65ReadScopes;
    const CompanionConnection connection =
        negotiateCompanionConnection(request, policy);
    CHECK(connection.ready());
    CHECK(connection.grantedScopes == kCompanionS65ReadScopes);
    CHECK(connection.grantedCapabilities == 0);
    std::array<char, kCompanionMaxFrameBytes + 1U> output{};
    std::size_t length = 0;
    CHECK(encodeCompanionConnectResponse(
        connection, CompanionTransport::UsbSerial, output.data(),
        output.size(), &length));
    CHECK(std::strstr(output.data(), "\"capabilities\":[]") != nullptr);
}

}  // namespace

int main() {
    static_assert(sizeof(CompanionConnectRequest) <= 48,
                  "connect request must remain a small bounded value");
    static_assert(sizeof(CompanionConnection) <= 48,
                  "connection result must remain a small bounded value");
    testBoundedOrderIndependentConnectParser();
    testParserFailsClosedWithoutPublishingPartialOutput();
    testEveryTruncatedFrameIsRejected();
    testScopesNeverExceedTheBoundDeviceSession();
    testCapabilitiesAreTruthfulAndActionBound();
    testDeterministicUsbAndWebResponses();
    testMutationConnectionResponseFitsTheCommonFrame();
    testDeniedResponseDisclosesNoCapabilities();
    testScopesDoNotInventUnwiredCapabilities();
    if (failures != 0) {
        std::cerr << failures << " companion protocol checks failed\n";
        return EXIT_FAILURE;
    }
    std::cout << "companion protocol checks passed\n";
    return EXIT_SUCCESS;
}
