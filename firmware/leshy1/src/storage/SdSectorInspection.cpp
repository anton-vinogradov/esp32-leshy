#include "SdSectorInspection.h"

#include <cstdio>
#include <cstring>
#include <limits>

#include "storage/AtomicHead.h"
#include "storage/SdIdentificationTransport.h"

namespace leshy1::storage {
namespace {

std::uint16_t get16(const std::uint8_t* value) {
    return static_cast<std::uint16_t>(value[0] |
                                      (static_cast<std::uint16_t>(value[1]) << 8U));
}

std::uint32_t get32(const std::uint8_t* value) {
    return static_cast<std::uint32_t>(value[0]) |
           (static_cast<std::uint32_t>(value[1]) << 8U) |
           (static_cast<std::uint32_t>(value[2]) << 16U) |
           (static_cast<std::uint32_t>(value[3]) << 24U);
}

bool powerOfTwo(std::uint8_t value) {
    return value != 0 && (value & static_cast<std::uint8_t>(value - 1U)) == 0;
}

bool validFatMediaDescriptor(std::uint8_t value) {
    return value == 0xF0U || value >= 0xF8U;
}

std::uint32_t fat32DataClusters(const SdFilesystemBootInspection& boot) {
    const std::uint64_t firstDataSector =
        static_cast<std::uint64_t>(boot.reservedSectors) +
        static_cast<std::uint64_t>(boot.fatCount) * boot.sectorsPerFat;
    if (boot.kind != SdFilesystemBootKind::Fat32 || !boot.geometryValid ||
        firstDataSector >= boot.totalSectors || boot.sectorsPerCluster == 0) {
        return 0;
    }
    return static_cast<std::uint32_t>(
        (boot.totalSectors - firstDataSector) / boot.sectorsPerCluster);
}

bool plausibleFatBoot(const std::array<std::uint8_t, 512>& sector) {
    const bool jump = sector[0] == 0xEB || sector[0] == 0xE9;
    const std::uint16_t bytesPerSector = get16(sector.data() + 11);
    return jump && (bytesPerSector == 512 || bytesPerSector == 1024 ||
                    bytesPerSector == 2048 || bytesPerSector == 4096) &&
           powerOfTwo(sector[13]) && get16(sector.data() + 14) != 0 &&
           (sector[16] == 1 || sector[16] == 2);
}

std::uint32_t extendCrc32c(std::uint32_t previous,
                           const std::uint8_t* data,
                           std::size_t size) {
    std::uint32_t crc = ~previous;
    for (std::size_t index = 0; index < size; ++index) {
        crc ^= data[index];
        for (std::uint8_t bit = 0; bit < 8; ++bit) {
            const std::uint32_t mask = 0U - (crc & 1U);
            crc = (crc >> 1U) ^ (0x82F63B78U & mask);
        }
    }
    return ~crc;
}

}  // namespace

const char* sdSectorReadStatusName(SdSectorReadStatus status) {
    switch (status) {
        case SdSectorReadStatus::Permitted: return "permitted";
        case SdSectorReadStatus::ExplicitTargetRequired:
            return "explicit_target_required";
        case SdSectorReadStatus::ReadOnlyRequired: return "read_only_required";
        case SdSectorReadStatus::HighCapacityRequired: return "high_capacity_required";
        case SdSectorReadStatus::CapacityInvalid: return "capacity_invalid";
        case SdSectorReadStatus::LbaForbidden: return "lba_forbidden";
        case SdSectorReadStatus::BlockCountInvalid: return "block_count_invalid";
        case SdSectorReadStatus::ResourcesMissing: return "resources_missing";
        case SdSectorReadStatus::ResourceConflict: return "resource_conflict";
    }
    return "read_only_required";
}

SdSectorReadStatus authorizeSdSector0Read(const SdSectorReadRequest& request) {
    if (!request.explicitlySelected) {
        return SdSectorReadStatus::ExplicitTargetRequired;
    }
    if (!request.readOnly) return SdSectorReadStatus::ReadOnlyRequired;
    if (!request.highCapacity) return SdSectorReadStatus::HighCapacityRequired;
    if (request.capacityBytes < 512 || (request.capacityBytes % 512U) != 0) {
        return SdSectorReadStatus::CapacityInvalid;
    }
    if (request.lba != 0) return SdSectorReadStatus::LbaForbidden;
    if (request.blockCount != 1) return SdSectorReadStatus::BlockCountInvalid;
    if ((request.ownedResources & kSdIdentificationResources) !=
        kSdIdentificationResources) {
        return SdSectorReadStatus::ResourcesMissing;
    }
    if (request.conflictingOwner) return SdSectorReadStatus::ResourceConflict;
    return SdSectorReadStatus::Permitted;
}

const char* sdSector0KindName(SdSector0Kind kind) {
    switch (kind) {
        case SdSector0Kind::InvalidSignature: return "invalid_signature";
        case SdSector0Kind::ProtectiveMbr: return "protective_mbr";
        case SdSector0Kind::PartitionedMbr: return "partitioned_mbr";
        case SdSector0Kind::ExfatBoot: return "exfat_boot";
        case SdSector0Kind::FatBoot: return "fat_boot";
        case SdSector0Kind::UnknownBoot: return "unknown_boot";
    }
    return "unknown_boot";
}

SdSector0Inspection inspectSdSector0(const std::array<std::uint8_t, 512>& sector,
                                    std::uint64_t capacityBytes) {
    SdSector0Inspection result;
    result.crc32c = crc32c(sector.data(), sector.size());
    result.signatureValid = sector[510] == 0x55 && sector[511] == 0xAA;
    if (!result.signatureValid) return result;

    const std::uint64_t capacitySectors = capacityBytes / 512U;
    bool protective = false;
    for (std::uint8_t index = 0; index < 4; ++index) {
        const std::uint8_t* entry = sector.data() + 446 + index * 16;
        const std::uint8_t boot = entry[0];
        const std::uint8_t type = entry[4];
        const std::uint32_t first = get32(entry + 8);
        const std::uint32_t count = get32(entry + 12);
        if (type == 0) continue;
        if ((boot != 0 && boot != 0x80) || count == 0 || first >= capacitySectors ||
            static_cast<std::uint64_t>(first) + count > capacitySectors) {
            continue;
        }
        if (result.partitionCount == 0) {
            result.firstPartitionType = type;
            result.firstPartitionLba = first;
            result.firstPartitionSectors = count;
        }
        ++result.partitionCount;
        if (type == 0xEE) protective = true;
    }
    if (protective) result.kind = SdSector0Kind::ProtectiveMbr;
    else if (result.partitionCount != 0) result.kind = SdSector0Kind::PartitionedMbr;
    else if (std::memcmp(sector.data() + 3, "EXFAT   ", 8) == 0) {
        result.kind = SdSector0Kind::ExfatBoot;
    } else if (plausibleFatBoot(sector)) {
        result.kind = SdSector0Kind::FatBoot;
    } else {
        result.kind = SdSector0Kind::UnknownBoot;
    }
    return result;
}

bool formatSdSector0Json(const SdSector0Inspection& inspection, char* output,
                         std::size_t capacity) {
    if (output == nullptr || capacity == 0) return false;
    const int written = std::snprintf(
        output, capacity,
        "{\"sector_kind\":\"%s\",\"signature_valid\":%s,"
        "\"sector_crc32c\":%lu,\"partition_count\":%u,"
        "\"first_partition_type\":%u,\"first_partition_lba\":%lu,"
        "\"first_partition_sectors\":%lu}",
        sdSector0KindName(inspection.kind),
        inspection.signatureValid ? "true" : "false",
        static_cast<unsigned long>(inspection.crc32c),
        static_cast<unsigned>(inspection.partitionCount),
        static_cast<unsigned>(inspection.firstPartitionType),
        static_cast<unsigned long>(inspection.firstPartitionLba),
        static_cast<unsigned long>(inspection.firstPartitionSectors));
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

SdSectorReadStatus authorizeSdPartitionBootRead(
    const SdSector0Inspection& sector0, const SdSectorReadRequest& request) {
    if (!request.explicitlySelected) {
        return SdSectorReadStatus::ExplicitTargetRequired;
    }
    if (!request.readOnly) return SdSectorReadStatus::ReadOnlyRequired;
    if (!request.highCapacity) return SdSectorReadStatus::HighCapacityRequired;
    if (request.capacityBytes < 512 || (request.capacityBytes % 512U) != 0) {
        return SdSectorReadStatus::CapacityInvalid;
    }
    if (sector0.kind != SdSector0Kind::PartitionedMbr ||
        sector0.partitionCount == 0 || sector0.firstPartitionLba == 0 ||
        request.lba != sector0.firstPartitionLba) {
        return SdSectorReadStatus::LbaForbidden;
    }
    if (request.blockCount != 1) return SdSectorReadStatus::BlockCountInvalid;
    if ((request.ownedResources & kSdIdentificationResources) !=
        kSdIdentificationResources) {
        return SdSectorReadStatus::ResourcesMissing;
    }
    if (request.conflictingOwner) return SdSectorReadStatus::ResourceConflict;
    return SdSectorReadStatus::Permitted;
}

const char* sdFilesystemBootKindName(SdFilesystemBootKind kind) {
    switch (kind) {
        case SdFilesystemBootKind::Invalid: return "invalid";
        case SdFilesystemBootKind::Fat12: return "fat12";
        case SdFilesystemBootKind::Fat16: return "fat16";
        case SdFilesystemBootKind::Fat32: return "fat32";
        case SdFilesystemBootKind::Exfat: return "exfat";
        case SdFilesystemBootKind::Unsupported: return "unsupported";
    }
    return "invalid";
}

SdFilesystemBootInspection inspectSdFilesystemBoot(
    const std::array<std::uint8_t, 512>& sector,
    std::uint32_t partitionSectors) {
    SdFilesystemBootInspection result;
    result.crc32c = crc32c(sector.data(), sector.size());
    result.signatureValid = sector[510] == 0x55 && sector[511] == 0xAA;
    if (!result.signatureValid || partitionSectors == 0) return result;

    if (std::memcmp(sector.data() + 3, "EXFAT   ", 8) == 0) {
        const std::uint8_t bytesShift = sector[108];
        const std::uint8_t clusterShift = sector[109];
        const std::uint32_t lowLength = get32(sector.data() + 72);
        const std::uint32_t highLength = get32(sector.data() + 76);
        if (bytesShift != 9 || clusterShift > 25 || highLength != 0 ||
            lowLength == 0 || lowLength > partitionSectors || sector[110] == 0) {
            result.kind = SdFilesystemBootKind::Invalid;
            return result;
        }
        result.kind = SdFilesystemBootKind::Exfat;
        result.bytesPerSector = 512;
        result.sectorsPerCluster = 1U << clusterShift;
        result.totalSectors = lowLength;
        result.sectorsPerFat = get32(sector.data() + 84);
        result.rootCluster = get32(sector.data() + 96);
        result.volumeSerial = get32(sector.data() + 100);
        result.geometryValid = result.sectorsPerFat != 0 && result.rootCluster >= 2;
        return result;
    }

    if (!plausibleFatBoot(sector)) {
        result.kind = SdFilesystemBootKind::Unsupported;
        return result;
    }
    result.bytesPerSector = get16(sector.data() + 11);
    result.sectorsPerCluster = sector[13];
    result.reservedSectors = get16(sector.data() + 14);
    result.fatCount = sector[16];
    result.mediaDescriptor = sector[21];
    const std::uint32_t total16 = get16(sector.data() + 19);
    result.totalSectors = total16 != 0 ? total16 : get32(sector.data() + 32);
    const std::uint32_t fat16 = get16(sector.data() + 22);
    const std::uint16_t rootEntries = get16(sector.data() + 17);
    if (rootEntries == 0 && fat16 == 0) {
        result.kind = SdFilesystemBootKind::Fat32;
        result.sectorsPerFat = get32(sector.data() + 36);
        result.rootCluster = get32(sector.data() + 44);
        result.fsInfoSector = get16(sector.data() + 48);
        result.backupBootSector = get16(sector.data() + 50);
        result.volumeSerial = get32(sector.data() + 67);
        std::memcpy(result.volumeLabel.data(), sector.data() + 71, 11);
    } else {
        result.kind = result.totalSectors < 65525U
                          ? SdFilesystemBootKind::Fat12
                          : SdFilesystemBootKind::Fat16;
        result.sectorsPerFat = fat16;
        result.volumeSerial = get32(sector.data() + 39);
        std::memcpy(result.volumeLabel.data(), sector.data() + 43, 11);
    }
    for (std::size_t index = 0; index < 11; ++index) {
        const unsigned char value =
            static_cast<unsigned char>(result.volumeLabel[index]);
        if (value < 0x20 || value > 0x7E) result.volumeLabel[index] = '?';
    }
    result.volumeLabel[11] = '\0';
    result.geometryValid = result.totalSectors != 0 &&
        result.totalSectors <= partitionSectors && result.sectorsPerFat != 0 &&
        result.reservedSectors != 0 && result.fatCount != 0;
    if (result.geometryValid && result.kind == SdFilesystemBootKind::Fat32) {
        const std::uint64_t dataStart =
            static_cast<std::uint64_t>(result.reservedSectors) +
            static_cast<std::uint64_t>(result.fatCount) * result.sectorsPerFat;
        const std::uint64_t rootOffset = dataStart +
            static_cast<std::uint64_t>(result.rootCluster - 2U) *
                result.sectorsPerCluster;
        result.geometryValid = result.rootCluster >= 2 &&
            rootOffset < result.totalSectors &&
            rootOffset + result.sectorsPerCluster <= result.totalSectors;
    }
    if (!result.geometryValid) result.kind = SdFilesystemBootKind::Invalid;
    return result;
}

bool formatSdFilesystemBootJson(const SdFilesystemBootInspection& inspection,
                                char* output, std::size_t capacity) {
    if (output == nullptr || capacity == 0) return false;
    const int written = std::snprintf(
        output, capacity,
        "{\"filesystem\":\"%s\",\"signature_valid\":%s,"
        "\"geometry_valid\":%s,\"boot_crc32c\":%lu,"
        "\"bytes_per_sector\":%u,\"sectors_per_cluster\":%lu,"
        "\"total_sectors\":%lu,\"sectors_per_fat\":%lu,"
        "\"root_cluster\":%lu,\"reserved_sectors\":%u,"
        "\"fat_count\":%u,\"media_descriptor\":%u,\"fsinfo_sector\":%u,"
        "\"backup_boot_sector\":%u,\"volume_serial\":%lu,"
        "\"volume_label\":\"%s\"}",
        sdFilesystemBootKindName(inspection.kind),
        inspection.signatureValid ? "true" : "false",
        inspection.geometryValid ? "true" : "false",
        static_cast<unsigned long>(inspection.crc32c),
        static_cast<unsigned>(inspection.bytesPerSector),
        static_cast<unsigned long>(inspection.sectorsPerCluster),
        static_cast<unsigned long>(inspection.totalSectors),
        static_cast<unsigned long>(inspection.sectorsPerFat),
        static_cast<unsigned long>(inspection.rootCluster),
        static_cast<unsigned>(inspection.reservedSectors),
        static_cast<unsigned>(inspection.fatCount),
        static_cast<unsigned>(inspection.mediaDescriptor),
        static_cast<unsigned>(inspection.fsInfoSector),
        static_cast<unsigned>(inspection.backupBootSector),
        static_cast<unsigned long>(inspection.volumeSerial),
        inspection.volumeLabel.data());
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

bool calculateSdFat32RootDirectoryLba(
    const SdSector0Inspection& sector0,
    const SdFilesystemBootInspection& boot,
    std::uint32_t* rootDirectoryLba) {
    if (rootDirectoryLba == nullptr ||
        sector0.kind != SdSector0Kind::PartitionedMbr ||
        sector0.partitionCount == 0 || sector0.firstPartitionLba == 0 ||
        sector0.firstPartitionSectors == 0 ||
        boot.kind != SdFilesystemBootKind::Fat32 || !boot.geometryValid ||
        boot.bytesPerSector != 512 || boot.rootCluster < 2 ||
        boot.sectorsPerCluster == 0 || boot.sectorsPerFat == 0 ||
        boot.reservedSectors == 0 || boot.fatCount == 0) {
        return false;
    }
    const std::uint64_t dataStart =
        static_cast<std::uint64_t>(boot.reservedSectors) +
        static_cast<std::uint64_t>(boot.fatCount) * boot.sectorsPerFat;
    const std::uint64_t relative = dataStart +
        static_cast<std::uint64_t>(boot.rootCluster - 2U) *
            boot.sectorsPerCluster;
    if (relative >= sector0.firstPartitionSectors ||
        relative >= boot.totalSectors ||
        relative + boot.sectorsPerCluster > sector0.firstPartitionSectors ||
        relative + boot.sectorsPerCluster > boot.totalSectors) {
        return false;
    }
    const std::uint64_t absolute = sector0.firstPartitionLba + relative;
    if (absolute > std::numeric_limits<std::uint32_t>::max()) return false;
    *rootDirectoryLba = static_cast<std::uint32_t>(absolute);
    return true;
}

SdSectorReadStatus authorizeSdFat32RootDirectoryRead(
    const SdSector0Inspection& sector0,
    const SdFilesystemBootInspection& boot,
    const SdSectorReadRequest& request) {
    return authorizeSdFat32RootDirectorySectorRead(
        sector0, boot, 0, request);
}

SdSectorReadStatus authorizeSdFat32RootDirectorySectorRead(
    const SdSector0Inspection& sector0,
    const SdFilesystemBootInspection& boot,
    std::uint8_t sectorOffset,
    const SdSectorReadRequest& request) {
    if (!request.explicitlySelected) {
        return SdSectorReadStatus::ExplicitTargetRequired;
    }
    if (!request.readOnly) return SdSectorReadStatus::ReadOnlyRequired;
    if (!request.highCapacity) return SdSectorReadStatus::HighCapacityRequired;
    if (request.capacityBytes < 512 || (request.capacityBytes % 512U) != 0) {
        return SdSectorReadStatus::CapacityInvalid;
    }
    std::uint32_t rootDirectoryLba = 0;
    if (!calculateSdFat32RootDirectoryLba(
            sector0, boot, &rootDirectoryLba) ||
        sectorOffset >= boot.sectorsPerCluster) {
        return SdSectorReadStatus::LbaForbidden;
    }
    const std::uint64_t expectedLba =
        static_cast<std::uint64_t>(rootDirectoryLba) + sectorOffset;
    if (expectedLba >= request.capacityBytes / 512U ||
        expectedLba > std::numeric_limits<std::uint32_t>::max() ||
        request.lba != expectedLba) {
        return SdSectorReadStatus::LbaForbidden;
    }
    if (request.blockCount != 1) return SdSectorReadStatus::BlockCountInvalid;
    if ((request.ownedResources & kSdIdentificationResources) !=
        kSdIdentificationResources) {
        return SdSectorReadStatus::ResourcesMissing;
    }
    if (request.conflictingOwner) return SdSectorReadStatus::ResourceConflict;
    return SdSectorReadStatus::Permitted;
}

SdFat32DirectoryInspection inspectSdFat32DirectoryMetadata(
    const std::array<std::uint8_t, 512>& sector) {
    SdFat32DirectoryInspection result;
    result.crc32c = crc32c(sector.data(), sector.size());
    for (std::size_t offset = 0; offset < sector.size(); offset += 32) {
        const std::uint8_t* entry = sector.data() + offset;
        ++result.entriesExamined;
        if (entry[0] == 0x00) {
            result.endMarkerSeen = true;
            break;
        }
        if (entry[0] == 0xE5) {
            ++result.deletedEntries;
            continue;
        }
        ++result.activeEntries;
        const std::uint8_t attributes = entry[11];
        if (attributes == 0x0F) {
            ++result.longNameEntries;
            const std::uint8_t ordinal = entry[0] & 0x1FU;
            if (ordinal == 0 || ordinal > 20 || entry[12] != 0 ||
                get16(entry + 26) != 0) {
                ++result.invalidEntries;
            }
            continue;
        }
        if ((attributes & 0xC0U) != 0 || (attributes & 0x18U) == 0x18U) {
            ++result.invalidEntries;
            continue;
        }
        if ((attributes & 0x08U) != 0) ++result.volumeLabelEntries;
        else if ((attributes & 0x10U) != 0) ++result.directoryEntries;
        else ++result.fileEntries;
    }
    return result;
}

bool formatSdFat32DirectoryMetadataJson(
    const SdFat32DirectoryInspection& inspection,
    char* output, std::size_t capacity) {
    if (output == nullptr || capacity == 0) return false;
    const int written = std::snprintf(
        output, capacity,
        "{\"privacy_policy\":\"counts_hash_only\","
        "\"sector_crc32c\":%lu,\"entries_examined\":%u,"
        "\"active_entries\":%u,\"deleted_entries\":%u,"
        "\"long_name_entries\":%u,\"volume_label_entries\":%u,"
        "\"directory_entries\":%u,\"file_entries\":%u,"
        "\"invalid_entries\":%u,\"end_marker_seen\":%s,"
        "\"names_retained\":false,\"raw_sector_retained\":false,"
        "\"file_data_read\":false}",
        static_cast<unsigned long>(inspection.crc32c),
        static_cast<unsigned>(inspection.entriesExamined),
        static_cast<unsigned>(inspection.activeEntries),
        static_cast<unsigned>(inspection.deletedEntries),
        static_cast<unsigned>(inspection.longNameEntries),
        static_cast<unsigned>(inspection.volumeLabelEntries),
        static_cast<unsigned>(inspection.directoryEntries),
        static_cast<unsigned>(inspection.fileEntries),
        static_cast<unsigned>(inspection.invalidEntries),
        inspection.endMarkerSeen ? "true" : "false");
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

bool appendSdFat32DirectoryMetadata(
    const std::array<std::uint8_t, 512>& sector,
    SdFat32DirectoryAggregate* aggregate) {
    if (aggregate == nullptr || aggregate->endMarkerSeen ||
        aggregate->sectorsInspected >= 128) {
        return false;
    }
    const SdFat32DirectoryInspection inspection =
        inspectSdFat32DirectoryMetadata(sector);
    aggregate->crc32c = extendCrc32c(
        aggregate->crc32c, sector.data(), sector.size());
    ++aggregate->sectorsInspected;
    aggregate->entriesExamined += inspection.entriesExamined;
    aggregate->activeEntries += inspection.activeEntries;
    aggregate->deletedEntries += inspection.deletedEntries;
    aggregate->longNameEntries += inspection.longNameEntries;
    aggregate->volumeLabelEntries += inspection.volumeLabelEntries;
    aggregate->directoryEntries += inspection.directoryEntries;
    aggregate->fileEntries += inspection.fileEntries;
    aggregate->invalidEntries += inspection.invalidEntries;
    aggregate->endMarkerSeen = inspection.endMarkerSeen;
    return true;
}

bool formatSdFat32DirectoryAggregateJson(
    const SdFat32DirectoryAggregate& aggregate,
    char* output, std::size_t capacity) {
    if (output == nullptr || capacity == 0) return false;
    const int written = std::snprintf(
        output, capacity,
        "{\"privacy_policy\":\"counts_hash_only\","
        "\"cluster_crc32c\":%lu,\"sectors_inspected\":%u,"
        "\"entries_examined\":%u,\"active_entries\":%u,"
        "\"deleted_entries\":%u,\"long_name_entries\":%u,"
        "\"volume_label_entries\":%u,\"directory_entries\":%u,"
        "\"file_entries\":%u,\"invalid_entries\":%u,"
        "\"end_marker_seen\":%s,\"names_retained\":false,"
        "\"raw_sectors_retained\":false,\"file_data_read\":false}",
        static_cast<unsigned long>(aggregate.crc32c),
        static_cast<unsigned>(aggregate.sectorsInspected),
        static_cast<unsigned>(aggregate.entriesExamined),
        static_cast<unsigned>(aggregate.activeEntries),
        static_cast<unsigned>(aggregate.deletedEntries),
        static_cast<unsigned>(aggregate.longNameEntries),
        static_cast<unsigned>(aggregate.volumeLabelEntries),
        static_cast<unsigned>(aggregate.directoryEntries),
        static_cast<unsigned>(aggregate.fileEntries),
        static_cast<unsigned>(aggregate.invalidEntries),
        aggregate.endMarkerSeen ? "true" : "false");
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

bool calculateSdFat32FsInfoLba(
    const SdSector0Inspection& sector0,
    const SdFilesystemBootInspection& boot,
    std::uint32_t* fsInfoLba) {
    if (fsInfoLba == nullptr ||
        sector0.kind != SdSector0Kind::PartitionedMbr ||
        sector0.partitionCount == 0 || sector0.firstPartitionLba == 0 ||
        boot.kind != SdFilesystemBootKind::Fat32 || !boot.geometryValid ||
        boot.fsInfoSector == 0 || boot.fsInfoSector == 0xFFFFU ||
        boot.fsInfoSector >= boot.reservedSectors ||
        boot.fsInfoSector >= sector0.firstPartitionSectors) {
        return false;
    }
    const std::uint64_t absolute =
        static_cast<std::uint64_t>(sector0.firstPartitionLba) +
        boot.fsInfoSector;
    if (absolute > std::numeric_limits<std::uint32_t>::max()) return false;
    *fsInfoLba = static_cast<std::uint32_t>(absolute);
    return true;
}

SdSectorReadStatus authorizeSdFat32FsInfoRead(
    const SdSector0Inspection& sector0,
    const SdFilesystemBootInspection& boot,
    const SdSectorReadRequest& request) {
    if (!request.explicitlySelected) {
        return SdSectorReadStatus::ExplicitTargetRequired;
    }
    if (!request.readOnly) return SdSectorReadStatus::ReadOnlyRequired;
    if (!request.highCapacity) return SdSectorReadStatus::HighCapacityRequired;
    if (request.capacityBytes < 512 || (request.capacityBytes % 512U) != 0) {
        return SdSectorReadStatus::CapacityInvalid;
    }
    std::uint32_t fsInfoLba = 0;
    if (!calculateSdFat32FsInfoLba(sector0, boot, &fsInfoLba) ||
        fsInfoLba >= request.capacityBytes / 512U ||
        request.lba != fsInfoLba) {
        return SdSectorReadStatus::LbaForbidden;
    }
    if (request.blockCount != 1) return SdSectorReadStatus::BlockCountInvalid;
    if ((request.ownedResources & kSdIdentificationResources) !=
        kSdIdentificationResources) {
        return SdSectorReadStatus::ResourcesMissing;
    }
    if (request.conflictingOwner) return SdSectorReadStatus::ResourceConflict;
    return SdSectorReadStatus::Permitted;
}

SdFat32FsInfoInspection inspectSdFat32FsInfo(
    const std::array<std::uint8_t, 512>& sector,
    const SdFilesystemBootInspection& boot) {
    SdFat32FsInfoInspection result;
    result.crc32c = crc32c(sector.data(), sector.size());
    if (boot.kind != SdFilesystemBootKind::Fat32 || !boot.geometryValid) {
        return result;
    }
    result.signaturesValid =
        get32(sector.data()) == 0x41615252U &&
        get32(sector.data() + 484) == 0x61417272U &&
        get32(sector.data() + 508) == 0xAA550000U;
    result.dataClusters = fat32DataClusters(boot);
    if (result.dataClusters == 0) return result;
    const std::uint32_t freeHint = get32(sector.data() + 488);
    const std::uint32_t nextHint = get32(sector.data() + 492);
    result.freeCountKnown = freeHint != 0xFFFFFFFFU;
    result.nextFreeKnown = nextHint != 0xFFFFFFFFU;
    if (result.freeCountKnown) result.freeClusters = freeHint;
    if (result.nextFreeKnown) result.nextFreeCluster = nextHint;
    const bool freeValid = !result.freeCountKnown ||
        result.freeClusters <= result.dataClusters;
    const bool nextValid = !result.nextFreeKnown ||
        (result.nextFreeCluster >= 2 &&
         static_cast<std::uint64_t>(result.nextFreeCluster) <
             static_cast<std::uint64_t>(result.dataClusters) + 2U);
    result.hintsValid = result.signaturesValid && result.dataClusters != 0 &&
        freeValid && nextValid;
    return result;
}

bool formatSdFat32FsInfoJson(
    const SdFat32FsInfoInspection& inspection,
    char* output, std::size_t capacity) {
    if (output == nullptr || capacity == 0) return false;
    const int written = std::snprintf(
        output, capacity,
        "{\"fsinfo_crc32c\":%lu,\"signatures_valid\":%s,"
        "\"hints_valid\":%s,\"data_clusters\":%lu,"
        "\"free_count_known\":%s,\"free_clusters\":%lu,"
        "\"next_free_known\":%s,\"next_free_cluster\":%lu,"
        "\"technical_metadata_only\":true,"
        "\"raw_sector_retained\":false,\"file_data_read\":false}",
        static_cast<unsigned long>(inspection.crc32c),
        inspection.signaturesValid ? "true" : "false",
        inspection.hintsValid ? "true" : "false",
        static_cast<unsigned long>(inspection.dataClusters),
        inspection.freeCountKnown ? "true" : "false",
        static_cast<unsigned long>(inspection.freeClusters),
        inspection.nextFreeKnown ? "true" : "false",
        static_cast<unsigned long>(inspection.nextFreeCluster));
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

bool calculateSdFat32FirstFatLba(
    const SdSector0Inspection& sector0,
    const SdFilesystemBootInspection& boot,
    std::uint32_t* firstFatLba) {
    if (firstFatLba == nullptr ||
        sector0.kind != SdSector0Kind::PartitionedMbr ||
        sector0.partitionCount == 0 || sector0.firstPartitionLba == 0 ||
        sector0.firstPartitionSectors == 0 ||
        boot.kind != SdFilesystemBootKind::Fat32 || !boot.geometryValid ||
        boot.bytesPerSector != 512 || boot.reservedSectors == 0 ||
        boot.sectorsPerFat == 0 || boot.fatCount == 0 ||
        boot.reservedSectors >= sector0.firstPartitionSectors ||
        boot.reservedSectors >= boot.totalSectors) {
        return false;
    }
    const std::uint64_t absolute =
        static_cast<std::uint64_t>(sector0.firstPartitionLba) +
        boot.reservedSectors;
    if (absolute > std::numeric_limits<std::uint32_t>::max()) return false;
    *firstFatLba = static_cast<std::uint32_t>(absolute);
    return true;
}

SdSectorReadStatus authorizeSdFat32FirstFatSectorRead(
    const SdSector0Inspection& sector0,
    const SdFilesystemBootInspection& boot,
    const SdSectorReadRequest& request) {
    if (!request.explicitlySelected) {
        return SdSectorReadStatus::ExplicitTargetRequired;
    }
    if (!request.readOnly) return SdSectorReadStatus::ReadOnlyRequired;
    if (!request.highCapacity) return SdSectorReadStatus::HighCapacityRequired;
    if (request.capacityBytes < 512 || (request.capacityBytes % 512U) != 0) {
        return SdSectorReadStatus::CapacityInvalid;
    }
    std::uint32_t firstFatLba = 0;
    if (!calculateSdFat32FirstFatLba(sector0, boot, &firstFatLba) ||
        firstFatLba >= request.capacityBytes / 512U ||
        request.lba != firstFatLba) {
        return SdSectorReadStatus::LbaForbidden;
    }
    if (request.blockCount != 1) return SdSectorReadStatus::BlockCountInvalid;
    if ((request.ownedResources & kSdIdentificationResources) !=
        kSdIdentificationResources) {
        return SdSectorReadStatus::ResourcesMissing;
    }
    if (request.conflictingOwner) return SdSectorReadStatus::ResourceConflict;
    return SdSectorReadStatus::Permitted;
}

const char* sdFat32EntryKindName(SdFat32EntryKind kind) {
    switch (kind) {
        case SdFat32EntryKind::Free: return "free";
        case SdFat32EntryKind::Data: return "data";
        case SdFat32EntryKind::Reserved: return "reserved";
        case SdFat32EntryKind::Bad: return "bad";
        case SdFat32EntryKind::EndOfChain: return "end_of_chain";
        case SdFat32EntryKind::OutOfRange: return "out_of_range";
    }
    return "out_of_range";
}

SdFat32ReservedInspection inspectSdFat32ReservedAndRootEntries(
    const std::array<std::uint8_t, 512>& sector,
    const SdFilesystemBootInspection& boot) {
    constexpr std::uint32_t kFat32Mask = 0x0FFFFFFFU;
    constexpr std::uint32_t kCleanShutdown = 0x08000000U;
    constexpr std::uint32_t kNoHardError = 0x04000000U;
    SdFat32ReservedInspection result;
    result.crc32c = crc32c(sector.data(), sector.size());
    result.fat0 = get32(sector.data()) & kFat32Mask;
    result.fat1 = get32(sector.data() + 4) & kFat32Mask;
    result.rootEntry = get32(sector.data() + 8) & kFat32Mask;
    result.mediaDescriptor = static_cast<std::uint8_t>(result.fat0);
    if (boot.kind != SdFilesystemBootKind::Fat32 || !boot.geometryValid ||
        boot.rootCluster != 2 || !validFatMediaDescriptor(boot.mediaDescriptor)) {
        return result;
    }
    result.fat0Valid = result.fat0 ==
        (0x0FFFFF00U | static_cast<std::uint32_t>(boot.mediaDescriptor));
    result.fat1ReservedBitsValid =
        (result.fat1 & 0x03FFFFFFU) == 0x03FFFFFFU;
    result.cleanShutdown = (result.fat1 & kCleanShutdown) != 0;
    result.noHardError = (result.fat1 & kNoHardError) != 0;

    const std::uint32_t dataClusters = fat32DataClusters(boot);
    const std::uint64_t maxCluster =
        static_cast<std::uint64_t>(dataClusters) + 1U;
    if (result.rootEntry == 0) {
        result.rootEntryKind = SdFat32EntryKind::Free;
    } else if (result.rootEntry >= 2 &&
               static_cast<std::uint64_t>(result.rootEntry) <= maxCluster) {
        result.rootEntryKind = SdFat32EntryKind::Data;
    } else if (result.rootEntry >= 0x0FFFFFF0U &&
               result.rootEntry <= 0x0FFFFFF6U) {
        result.rootEntryKind = SdFat32EntryKind::Reserved;
    } else if (result.rootEntry == 0x0FFFFFF7U) {
        result.rootEntryKind = SdFat32EntryKind::Bad;
    } else if (result.rootEntry >= 0x0FFFFFF8U) {
        result.rootEntryKind = SdFat32EntryKind::EndOfChain;
    } else {
        result.rootEntryKind = SdFat32EntryKind::OutOfRange;
    }
    result.rootChainContinues =
        result.rootEntryKind == SdFat32EntryKind::Data && result.rootEntry != 2;
    result.rootEntryValid = result.rootChainContinues ||
        result.rootEntryKind == SdFat32EntryKind::EndOfChain;
    result.structureValid = result.fat0Valid && result.fat1ReservedBitsValid &&
        result.rootEntryValid;
    return result;
}

bool formatSdFat32ReservedInspectionJson(
    const SdFat32ReservedInspection& inspection,
    char* output, std::size_t capacity) {
    if (output == nullptr || capacity == 0) return false;
    const int written = std::snprintf(
        output, capacity,
        "{\"fat_crc32c\":%lu,\"fat0\":%lu,\"fat1\":%lu,"
        "\"root_entry\":%lu,\"media_descriptor\":%u,"
        "\"fat0_valid\":%s,\"fat1_reserved_bits_valid\":%s,"
        "\"clean_shutdown\":%s,\"no_hard_error\":%s,"
        "\"root_entry_kind\":\"%s\",\"root_entry_valid\":%s,"
        "\"root_chain_continues\":%s,\"structure_valid\":%s,"
        "\"entries_inspected\":3,\"fat_chain_followed\":false,"
        "\"technical_metadata_only\":true,\"raw_sector_retained\":false,"
        "\"names_read\":false,\"file_data_read\":false}",
        static_cast<unsigned long>(inspection.crc32c),
        static_cast<unsigned long>(inspection.fat0),
        static_cast<unsigned long>(inspection.fat1),
        static_cast<unsigned long>(inspection.rootEntry),
        static_cast<unsigned>(inspection.mediaDescriptor),
        inspection.fat0Valid ? "true" : "false",
        inspection.fat1ReservedBitsValid ? "true" : "false",
        inspection.cleanShutdown ? "true" : "false",
        inspection.noHardError ? "true" : "false",
        sdFat32EntryKindName(inspection.rootEntryKind),
        inspection.rootEntryValid ? "true" : "false",
        inspection.rootChainContinues ? "true" : "false",
        inspection.structureValid ? "true" : "false");
    return written >= 0 && static_cast<std::size_t>(written) < capacity;
}

SdFat32FsInfoCrossCheck crossCheckSdFat32FsInfoWithReservedEntries(
    const SdFat32FsInfoInspection& fsInfo,
    const SdFat32ReservedInspection& fat,
    const SdFilesystemBootInspection& boot) {
    SdFat32FsInfoCrossCheck result;
    result.available = fsInfo.hintsValid && fat.structureValid &&
        boot.kind == SdFilesystemBootKind::Fat32 && boot.rootCluster == 2;
    if (!result.available) return result;
    const std::uint32_t knownAllocatedClusters =
        fat.rootChainContinues ? 2U : 1U;
    result.freeHintCompatible = !fsInfo.freeCountKnown ||
        (fsInfo.dataClusters >= knownAllocatedClusters &&
         fsInfo.freeClusters <=
             fsInfo.dataClusters - knownAllocatedClusters);
    result.nextFreeHintCompatible = !fsInfo.nextFreeKnown ||
        (fsInfo.nextFreeCluster != boot.rootCluster &&
         (!fat.rootChainContinues ||
          fsInfo.nextFreeCluster != fat.rootEntry));
    result.compatible = result.freeHintCompatible &&
        result.nextFreeHintCompatible;
    return result;
}

}  // namespace leshy1::storage
