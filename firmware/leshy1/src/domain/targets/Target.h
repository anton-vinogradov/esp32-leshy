#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace leshy1::domain::targets {

// Target IDs are stable local object identities. They are deliberately not
// derived from a MAC address: one Target may own several radio identities and
// later merge/split operations must not rewrite source observations.
struct TargetId final {
    static constexpr std::size_t kSize = 16;
    std::array<std::uint8_t, kSize> bytes{};
};

struct SourceId final {
    static constexpr std::size_t kSize = 16;
    std::array<std::uint8_t, kSize> bytes{};
};

enum class TargetIdentityKind : std::uint8_t {
    WifiBssid = 1,
    WifiStation = 2,
    BleAddress = 3,
};

struct TargetIdentity final {
    static constexpr std::size_t kValueCapacity = 6;

    TargetIdentityKind kind = TargetIdentityKind::WifiBssid;
    std::array<std::uint8_t, kValueCapacity> value{};
    std::uint8_t length = 0;
    // BLE address type. Wi-Fi identities require zero so the same raw address
    // cannot acquire two spellings accidentally.
    std::uint8_t discriminator = 0;
};

// A reference never copies or edits the source Observation. sourceId identifies
// the immutable Session object; generation and sequence open the exact record.
struct TargetEvidenceRef final {
    SourceId sourceId{};
    std::uint32_t sourceGeneration = 0;
    std::uint64_t observationSequence = 0;
    std::uint64_t observedMonotonicUs = 0;
};

bool targetIdValid(const TargetId& id);
bool targetIdEqual(const TargetId& left, const TargetId& right);
bool sourceIdValid(const SourceId& id);
bool targetIdentityValid(const TargetIdentity& identity);
bool targetIdentityEqual(const TargetIdentity& left,
                         const TargetIdentity& right);
bool targetEvidenceValid(const TargetEvidenceRef& evidence);
bool targetEvidenceEqual(const TargetEvidenceRef& left,
                         const TargetEvidenceRef& right);

struct TargetRecord final {
    static constexpr std::size_t kIdentityCapacity = 4;
    static constexpr std::size_t kEvidenceCapacity = 8;
    static constexpr std::size_t kNameCapacity = 48;
    static constexpr std::size_t kNotesCapacity = 160;
    static constexpr std::size_t kTagCountCapacity = 4;
    static constexpr std::size_t kTagCapacity = 24;

    TargetId id{};
    std::array<TargetIdentity, kIdentityCapacity> identities{};
    std::uint8_t identityCount = 0;
    std::array<TargetEvidenceRef, kEvidenceCapacity> evidence{};
    std::uint8_t evidenceCount = 0;
    std::array<char, kNameCapacity + 1> name{};
    std::uint8_t nameLength = 0;
    std::array<char, kNotesCapacity + 1> notes{};
    std::uint16_t notesLength = 0;
    std::array<std::array<char, kTagCapacity + 1>, kTagCountCapacity> tags{};
    std::array<std::uint8_t, kTagCountCapacity> tagLengths{};
    std::uint8_t tagCount = 0;
    bool favorite = false;
    std::uint32_t revision = 0;
};

}  // namespace leshy1::domain::targets
