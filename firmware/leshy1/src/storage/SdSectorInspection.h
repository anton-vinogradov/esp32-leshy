#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "kernel/runtime/Resources.h"

namespace leshy1::storage {

struct SdSectorReadRequest final {
    bool explicitlySelected = false;
    bool readOnly = false;
    bool highCapacity = false;
    std::uint64_t capacityBytes = 0;
    std::uint32_t lba = 0;
    std::uint8_t blockCount = 0;
    kernel::runtime::ResourceMask ownedResources = 0;
    bool conflictingOwner = false;
};

enum class SdSectorReadStatus : std::uint8_t {
    Permitted,
    ExplicitTargetRequired,
    ReadOnlyRequired,
    HighCapacityRequired,
    CapacityInvalid,
    LbaForbidden,
    BlockCountInvalid,
    ResourcesMissing,
    ResourceConflict,
};

const char* sdSectorReadStatusName(SdSectorReadStatus status);
SdSectorReadStatus authorizeSdSector0Read(const SdSectorReadRequest& request);

enum class SdSector0Kind : std::uint8_t {
    InvalidSignature,
    ProtectiveMbr,
    PartitionedMbr,
    ExfatBoot,
    FatBoot,
    UnknownBoot,
};

struct SdSector0Inspection final {
    SdSector0Kind kind = SdSector0Kind::InvalidSignature;
    std::uint32_t crc32c = 0;
    std::uint8_t partitionCount = 0;
    std::uint8_t firstPartitionType = 0;
    std::uint32_t firstPartitionLba = 0;
    std::uint32_t firstPartitionSectors = 0;
    bool signatureValid = false;
};

const char* sdSector0KindName(SdSector0Kind kind);
SdSector0Inspection inspectSdSector0(const std::array<std::uint8_t, 512>& sector,
                                    std::uint64_t capacityBytes);
bool formatSdSector0Json(const SdSector0Inspection& inspection, char* output,
                         std::size_t capacity);

SdSectorReadStatus authorizeSdPartitionBootRead(
    const SdSector0Inspection& sector0, const SdSectorReadRequest& request);

enum class SdFilesystemBootKind : std::uint8_t {
    Invalid,
    Fat12,
    Fat16,
    Fat32,
    Exfat,
    Unsupported,
};

struct SdFilesystemBootInspection final {
    SdFilesystemBootKind kind = SdFilesystemBootKind::Invalid;
    std::uint32_t crc32c = 0;
    std::uint16_t bytesPerSector = 0;
    std::uint32_t sectorsPerCluster = 0;
    std::uint32_t totalSectors = 0;
    std::uint32_t sectorsPerFat = 0;
    std::uint32_t rootCluster = 0;
    std::uint16_t reservedSectors = 0;
    std::uint8_t fatCount = 0;
    std::uint8_t mediaDescriptor = 0;
    std::uint16_t fsInfoSector = 0;
    std::uint16_t backupBootSector = 0;
    std::uint32_t volumeSerial = 0;
    std::array<char, 12> volumeLabel{};
    bool signatureValid = false;
    bool geometryValid = false;
};

const char* sdFilesystemBootKindName(SdFilesystemBootKind kind);
SdFilesystemBootInspection inspectSdFilesystemBoot(
    const std::array<std::uint8_t, 512>& sector,
    std::uint32_t partitionSectors);
bool formatSdFilesystemBootJson(const SdFilesystemBootInspection& inspection,
                                char* output, std::size_t capacity);

bool calculateSdFat32RootDirectoryLba(
    const SdSector0Inspection& sector0,
    const SdFilesystemBootInspection& boot,
    std::uint32_t* rootDirectoryLba);
SdSectorReadStatus authorizeSdFat32RootDirectoryRead(
    const SdSector0Inspection& sector0,
    const SdFilesystemBootInspection& boot,
    const SdSectorReadRequest& request);
SdSectorReadStatus authorizeSdFat32RootDirectorySectorRead(
    const SdSector0Inspection& sector0,
    const SdFilesystemBootInspection& boot,
    std::uint8_t sectorOffset,
    const SdSectorReadRequest& request);

struct SdFat32DirectoryInspection final {
    std::uint32_t crc32c = 0;
    std::uint8_t entriesExamined = 0;
    std::uint8_t activeEntries = 0;
    std::uint8_t deletedEntries = 0;
    std::uint8_t longNameEntries = 0;
    std::uint8_t volumeLabelEntries = 0;
    std::uint8_t directoryEntries = 0;
    std::uint8_t fileEntries = 0;
    std::uint8_t invalidEntries = 0;
    bool endMarkerSeen = false;
};

SdFat32DirectoryInspection inspectSdFat32DirectoryMetadata(
    const std::array<std::uint8_t, 512>& sector);
bool formatSdFat32DirectoryMetadataJson(
    const SdFat32DirectoryInspection& inspection,
    char* output, std::size_t capacity);

struct SdFat32DirectoryAggregate final {
    std::uint32_t crc32c = 0;
    std::uint8_t sectorsInspected = 0;
    std::uint16_t entriesExamined = 0;
    std::uint16_t activeEntries = 0;
    std::uint16_t deletedEntries = 0;
    std::uint16_t longNameEntries = 0;
    std::uint16_t volumeLabelEntries = 0;
    std::uint16_t directoryEntries = 0;
    std::uint16_t fileEntries = 0;
    std::uint16_t invalidEntries = 0;
    bool endMarkerSeen = false;
};

bool appendSdFat32DirectoryMetadata(
    const std::array<std::uint8_t, 512>& sector,
    SdFat32DirectoryAggregate* aggregate);
bool formatSdFat32DirectoryAggregateJson(
    const SdFat32DirectoryAggregate& aggregate,
    char* output, std::size_t capacity);

bool calculateSdFat32FsInfoLba(
    const SdSector0Inspection& sector0,
    const SdFilesystemBootInspection& boot,
    std::uint32_t* fsInfoLba);
SdSectorReadStatus authorizeSdFat32FsInfoRead(
    const SdSector0Inspection& sector0,
    const SdFilesystemBootInspection& boot,
    const SdSectorReadRequest& request);

struct SdFat32FsInfoInspection final {
    std::uint32_t crc32c = 0;
    std::uint32_t dataClusters = 0;
    std::uint32_t freeClusters = 0;
    std::uint32_t nextFreeCluster = 0;
    bool signaturesValid = false;
    bool freeCountKnown = false;
    bool nextFreeKnown = false;
    bool hintsValid = false;
};

SdFat32FsInfoInspection inspectSdFat32FsInfo(
    const std::array<std::uint8_t, 512>& sector,
    const SdFilesystemBootInspection& boot);
bool formatSdFat32FsInfoJson(
    const SdFat32FsInfoInspection& inspection,
    char* output, std::size_t capacity);

bool calculateSdFat32FirstFatLba(
    const SdSector0Inspection& sector0,
    const SdFilesystemBootInspection& boot,
    std::uint32_t* firstFatLba);
SdSectorReadStatus authorizeSdFat32FirstFatSectorRead(
    const SdSector0Inspection& sector0,
    const SdFilesystemBootInspection& boot,
    const SdSectorReadRequest& request);

enum class SdFat32EntryKind : std::uint8_t {
    Free,
    Data,
    Reserved,
    Bad,
    EndOfChain,
    OutOfRange,
};

const char* sdFat32EntryKindName(SdFat32EntryKind kind);

struct SdFat32ReservedInspection final {
    std::uint32_t crc32c = 0;
    std::uint32_t fat0 = 0;
    std::uint32_t fat1 = 0;
    std::uint32_t rootEntry = 0;
    std::uint8_t mediaDescriptor = 0;
    SdFat32EntryKind rootEntryKind = SdFat32EntryKind::OutOfRange;
    bool fat0Valid = false;
    bool fat1ReservedBitsValid = false;
    bool cleanShutdown = false;
    bool noHardError = false;
    bool rootEntryValid = false;
    bool rootChainContinues = false;
    bool structureValid = false;
};

SdFat32ReservedInspection inspectSdFat32ReservedAndRootEntries(
    const std::array<std::uint8_t, 512>& sector,
    const SdFilesystemBootInspection& boot);
bool formatSdFat32ReservedInspectionJson(
    const SdFat32ReservedInspection& inspection,
    char* output, std::size_t capacity);

struct SdFat32FsInfoCrossCheck final {
    bool available = false;
    bool freeHintCompatible = false;
    bool nextFreeHintCompatible = false;
    bool compatible = false;
};

SdFat32FsInfoCrossCheck crossCheckSdFat32FsInfoWithReservedEntries(
    const SdFat32FsInfoInspection& fsInfo,
    const SdFat32ReservedInspection& fat,
    const SdFilesystemBootInspection& boot);

}  // namespace leshy1::storage
