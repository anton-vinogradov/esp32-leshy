# ESP32-Leshy 1.x — storage atomicity HIL

*Read in: **English** · [Русский](STORAGE_HIL.ru.md)*

Document status: **binding safety/verification protocol; host logic, real-file
fixture, guarded physical FAT commit/remount, per-generation and batched 32-sample
SD throughput, real-source queue/persistence, and the six-boundary software-reset
matrix are implemented; product UI, power-cut, and LittleFS parity remain open**.

This protocol verifies ADR-003 without risking an unknown SD card or retained flash
data. The ordinary diagnostic image never formats or writes storage during boot or
capability detection.

## Implemented logical contract

The allocation-free `storage/AtomicHead` contract defines a 24-byte, big-endian
head record:

| Field | Bytes | Rule |
|---|---:|---|
| magic | 4 | `LSHH` |
| schema | 2 | version 1; unsupported versions fail closed |
| flags | 2 | zero in v1 |
| generation | 4 | serial-number comparison with wrap support |
| manifest length | 4 | must match the referenced manifest |
| manifest CRC32C | 4 | must match manifest evidence |
| head CRC32C | 4 | covers the preceding 20 bytes |

Recovery validates both heads and their manifests, then chooses the highest valid
generation. An equal generation with different manifest identity or an exactly
half-range generation delta is a `conflict`, not a guessed winner. No valid head is
`none`; both results require explicit recovery UI.

Commit order is fixed: write payloads → sync payloads → write manifest → sync
manifest → write the older head slot → sync head. Only the last successful sync
publishes the new generation.

Host tests inject failure at every boundary. All six incomplete commits select the
previous generation; the complete path selects the new generation. Bounds, the
standard CRC32C vector, every one-bit head corruption, missing/mismatched manifests,
split-brain, and generation rollover are also covered.

`storage/SessionCodec` now supplies the bounded payload contract behind that head.
Schema 1 uses a canonical CBOR manifest and canonical CBOR observations framed by
big-endian length and CRC32C. A 24-byte `LSHS` segment footer authenticates schema,
flags, record count, body length, and body/footer CRC32C. Fixed limits are 256 bytes
per manifest, 128 bytes per record, 12,288 bytes per segment, and 64 observations.
The decoder rejects future schemas, non-canonical/malformed/trailing data, invalid
timelines, bounds violations, and checksum mismatch. Host tests mutate every
manifest bit, truncate the segment at every byte, and mutate one bit in every segment
byte. The exact golden Session reopens and emits deterministic bounded JSON.

Board-01 `0.10.0-session-codec-measure` repeats encode → head selection → reopen →
JSON after explicit Stop and reports `storage_written=false` and
`radio_touched=false`. This confirms the same allocation-free codec on target but is
not filesystem, reset, or power-cut evidence.

The guarded host filesystem fixture then performs the commit against actual files in
an isolated `mkdtemp` directory. It requires the same exact-fingerprint,
explicit-disposable, bounded `StorageGuard` permit; syncs both files and their parent
directory; reopens the selected generation; verifies prior bytes; and removes the
fixture. Six injected write/sync failures recover generation 1, while a complete
commit recovers generation 2. This is real file/`fsync` evidence, but the failures are
modeled return/crash images rather than ESP reset or power cut.

The common `SessionStore` now owns this layout and orchestration with fixed buffers:
automatic generation/older-slot selection, uint32 rollover, commit, full manifest and
segment validation, reopen, and corrupt-new fallback. It distinguishes a truly empty
store from corrupt/ambiguous heads; only empty may initialize, while ambiguity writes
nothing. The POSIX fixture recovers through this same contract.

A second matrix kills the writer process with `SIGKILL` after each real operation.
Recovery in the surviving process selects generation 1 before head publication and
generation 2 after a complete head write. The latter is valid even before head
`fsync`: payload and manifest are already durable, and a complete head may survive.
All six outcomes reopen three observations and keep prior bytes unchanged.

Board-01 `0.11.0-session-store-measure` runs the same common `SessionStore` through a
bounded, explicitly non-persistent two-generation RAM adapter. It automatically
publishes generation 1/A then 2/B, reopens generation 2, flips one byte in its segment,
classifies it as `invalid_payload`, and falls back to generation 1. Both reopen three
observations. The adapter models six file and six directory sync calls while reporting
`physical_storage_written=false` and `radio_touched=false`. This closes target
orchestration/fallback evidence, not persistence.

Board-01 `0.12.0-library-offline-measure` adds a bounded Library List/Detail controller
over that reopened metadata. The first image was rejected after a stack canary exposed
a full `SurveySession` temporary in `reopenSession`; decode now resets and fills
caller-owned bounded storage directly. The corrected image shows generation,
integrity, and explicit volatile/RF-off provenance while holding only the UI lease.

Board-01 `0.13.0-library-export-measure` adds an explicit Detail→Export Ready action.
Only that state emits the bounded deterministic `leshy.library.export.v1` serial
artifact; Home returns `not_requested`. The artifact retains generation, integrity,
simulated/persistent state, storage backend, transport, RF state, and Session summary.
It is transport evidence, not a persisted file.

Board-01 `0.14.0-storage-discovery-measure` introduces the typed
`ReadOnlyMediaAdapter` boundary. The board implementation samples GPIO38 without
reconfiguring it and reports level 0, but HW-U06 makes that level non-authoritative.
Therefore status remains `unknown`: mount, filesystem, fingerprint, capacity, and
free-space claims are absent, writes are disabled, and `StorageGuard` remains required.
Host validation forbids present/absent claims from non-authoritative detect and
requires complete read-only metadata before a result can become `detected`.

Board-01 `0.15.0-mount-policy-measure` adds the gate before driver execution. A mount
attempt requires explicit selection, a proven read-only driver, format disabled, and
exclusive Storage+RadioSpi ownership. The installed Arduino `SDFS::begin` exposes no
read-only option and the class exposes raw writes, so the board reports actual
`explicit_target_required` and hypothetical `driver_not_read_only`. It executes no
SPI or mount operation.

Board-01 `0.16.0-sd-ro-protocol-measure` adds a dedicated identification-only plan
outside SDFS: CMD0, CMD8, CMD55/ACMD41, CMD58, CMD10, and CMD9 with bounded init.
Host tests explicitly reject write/program/erase/lock/general commands and any plan
drift. The board reports the valid plan with execution disabled; no SD command runs.

Board-01 `0.17.0-sd-parser-measure` adds the bounded response parser. It validates
R1 state, CMD8 echo, initialization count, OCR, CID/CSD CRC16, identity sanity, CSD
v2 structure, and capacity. Host tests reject every one-bit mutation in the 16-byte
CID and CSD. The board parses a synthetic transcript while reporting zero commands
and no physical SPI, write, or radio activity.

Board-01 `0.18.0-sd-transport-measure` adds the executable state machine over a
strict deterministic fake. It completes eleven exchanges for the three-attempt
golden case. Host injection rejects failure at every exchange, stops a never-ready
card after 100 attempts/202 exchanges, and refuses physical transports before their
first call. No physical adapter exists or runs in this slice.

Board-01 `0.19.0-sd-wire-measure` adds allocation-free wire framing without a bus
adapter. CMD0/CMD8 match their known CRC7 packets; R1 and data-token polling are
bounded, R3/R7 trailing values are exact, and CID/CSD wire CRC16 is required. Host
fixtures reject invalid arguments, mutating commands, timeout, unexpected token,
truncation, and checksum mismatch. The board reports zero commands and execution
disabled.

Board-01 `0.20.0-sd-physical-id-measure` adds the guarded 400 kHz physical adapter.
The exact confirmation command acquires Storage+RadioSpi, keeps NRF CE LOW and other
known chip selects HIGH, requires GPIO21 to stay HIGH, then executes identification
only. Three runs return identical CID/CSD and 62,534,975,488-byte capacity; cold/warm
initialization takes 8/2/2 attempts. Every run completes cleanup and releases mask
12→0. Discovery remains unmounted/unknown and no data block, filesystem, write,
format, or radio command executes.

Board-01 `0.21.0-sd-sector0-measure` adds one separately guarded CMD17 after valid
physical identity. Authorization accepts only LBA0/count 1 for a selected high-
capacity read-only target while Storage+RadioSpi is held without conflict. The
physical run reads exactly one block, validates wire CRC16 `5391`, and reports a
valid MBR partition type `0x0C` at LBA 2,048 for 122,136,512 sectors plus LBA0
CRC32C `1784529910`. The raw block is not retained, and cleanup again returns 12→0.

Board-01 `0.22.0-sd-boot-inspect-measure` adds one more metadata permit whose LBA
must equal the first partition LBA from that valid MBR. Exactly two total blocks
(LBA0 and boot) confirm FAT32 geometry: 512 B/sector, 64 sectors/cluster, 14,906
sectors/FAT, root cluster 2, and 122,136,512 total sectors. Boot CRC32C/wire CRC16
are `3945425518`/`9849`. Raw sectors are not retained; mount/filesystem APIs,
directory/file reads, writes, format, and radio TX remain disabled. The next sector
would contain directory entries and therefore crosses from geometry into potential
user-data evidence.

The operator approved `counts_hash_only` for that boundary. Board-01
`0.23.0-sd-root-metadata-measure` derives root LBA 32,768 from the validated FAT32
geometry and authorizes exactly one block. Its first-sector report contains only a
CRC32C and aggregate slot classes: 16 active, including 8 LFN, 2 directory, 5 file,
and 1 volume-label entries. Host privacy fixtures place identifiable short/LFN names
in raw bytes and prove formatted evidence contains none. The board zeroes the reused
512-byte directory buffer immediately after aggregation.

Board-01 `0.24.0-sd-root-cluster-measure` extends the same policy through sequential
sectors bounded by the declared 64-sector cluster. It finds the directory end marker
in sector two and stops: 29 examined slots, 26 active, 2 deleted, 12 LFN, 6
directory, 7 file, 1 volume-label, and zero invalid. Aggregate CRC32C is
`1849301523`. Four total blocks include LBA0, boot, and the two directory sectors;
the FAT chain is not touched. Every raw directory buffer is zeroed, and no name or
file data is retained.

Board-01 `0.25.0-sd-fsinfo-measure` then reads only the FAT32 FSInfo sector declared
at reserved-sector offset 1 (absolute LBA 2,049). Lead/structure/trailing signatures
and bounds are valid. It reports technical hints of 1,907,095 free clusters out of
1,907,903 data clusters and next-free cluster 888, with CRC32C `1661032487` and wire
CRC16 `49708`. These are hints, not a full FAT allocation proof. The buffer is
zeroed; no names, directory entries, FAT entries, or file data are read. Refactoring
the mutually exclusive probes onto one shared workspace reduces static RAM from
95,620 B in 0.24 to 90,004 B while preserving the same safety boundary.

Reserved-entry semantics follow the
[Microsoft FAT32 Specification 1.03 (`fatgen103.doc`)](https://www.microsoft.com/en-au/download/details.aspx?id=53426).
Board-01 `0.27.0-sd-fat-reserved-measure` adds exactly one first-FAT sector to
fresh LBA0/boot/FSInfo evidence and parses FAT[0], FAT[1], and FAT[2] only. First FAT
LBA 2,956 is derived from reserved offset 908. FAT[0] `0x0FFFFFF8` matches boot media
`0xF8`; FAT[1] `0x0FFFFFFF` reports clean shutdown/no hard error; FAT[2]
`0x0FFFFFFF` ends root cluster 2. FSInfo free 1,907,095/1,907,903 and next-free 888
are compatible with this minimum allocation evidence. This is not a full recount:
the parser does not follow a chain after FAT[2], even if the entry points to another
cluster. FSInfo and FAT buffers are zeroed; names, directory/file data, VFS, mounts,
and writes remain absent.

`StorageGuard` now implements the physical-fixture authorization boundary. It issues
a bounded permit only after exact fingerprint match, explicit disposable selection,
a safe new run ID/namespace, consistent capacity, non-zero byte limit, and reserved
free space. Negative host tests cover every refusal reason.

Board-01 `0.28.0-sd-session-store-measure` is the first guarded writable physical
slice. The explicit command includes the exact CID and a fresh run ID, acquires
Storage+RadioSpi, mounts SDFS with formatting disabled, and confines the common
`SessionStore` to `/leshy-hil/s1-session-store-20260816-d`. Generations 1/A and 2/B
commit with six file and six directory syncs; a real unmount/remount followed by a
read-only reopen returns generation 2 and three synthetic observations. Logical bytes
written are 440 within a 65,536-byte permit. Repeating the same command refuses the
existing scratch path and writes zero bytes. No existing path is deleted, no user
names or file payload are read, and no radio TX command occurs.

FatFs `f_sync` behind Arduino `File::flush` is the adapter's file/directory durability
boundary. This successful normal remount is not evidence for reset at each commit
boundary or loss of power. The run also exposed and fixed an oversized loop-stack
recovery temporary and incorrect nested-directory verification before successful
Session writes.

## Physical fixture safety

A physical run may use only one of these explicitly selected targets:

- a disposable SD card whose capacity/CID fingerprint has been recorded for this
  run; or
- a dedicated disposable LittleFS image/partition created for HIL, never the current
  product/legacy data partition.

Read-only discovery comes first. A target with an unexpected fingerprint, existing
scratch namespace, mount error, insufficient space, or filesystem inconsistency is
refused. All writes are bounded to `/leshy-hil/<run-id>/`; format, partition-table
changes, and writes outside that namespace are forbidden. Cleanup occurs only after
evidence hashes are retained; here cleanup means unmount and resource/GPIO recovery,
not deletion of the evidence namespace.

Logical reset injection (`esp_restart`) can exercise reopen/recovery but does not
replace real power-cut evidence. Closing PR-005/RB-06 requires a controlled supply or
power switch that cuts power independently at every persisted boundary.

## Implemented and physically exercised software-reset harness

Version `0.30.0-sd-session-reset-measure` adds a diagnostic
`SessionStoreBoundaryIo` wrapper around the unchanged common commit path. It counts
only a successfully completed logical operation. A write boundary fires after the
underlying `writeFile` succeeds; a sync boundary fires only after both `syncFile` and
the adapter's directory barrier succeed. Host tests stop after each of the six
boundaries and recover an allowed generation while preserving generation-1 bytes.

| Number | Boundary | Allowed recovery after software reset |
|---:|---|---|
| 1 | payload write | generation 1 |
| 2 | payload file + directory sync | generation 1 |
| 3 | manifest write | generation 1 |
| 4 | manifest file + directory sync | generation 1 |
| 5 | older-head write | generation 1 or 2; a complete unsynced head may survive |
| 6 | head file + directory sync | generation 2 |

The write-side command requires exact CID, a unique run ID, a new scratch namespace,
64 KiB bound, and Storage+RadioSpi ownership. It fully commits generation 1, records
its manifest/segment sizes and CRC32C, then calls `esp_restart` immediately after the
selected boundary of generation 2:

```text
storage.sd.session-store reset disposable-write <CID32> <run-id> <1..6>
```

After boot, a separate command again proves exact CID and the existing namespace,
opens `SessionStoreIo` read-only, writes/syncs zero bytes, checks the software-reset
reason, validates the allowed recovered generation and three observations, compares
the prior manifest/segment bytes with their deterministic CRC32C, then unmounts and
releases resources:

```text
storage.sd.session-store recover disposable-read-only <CID32> <run-id> <1..6>
```

`tools/run_1x_sd_reset_matrix.py` sequences six unique namespaces, checkpoints every
completed boundary, and refuses to run without `--execute-reset-matrix`. Recovery
has at most three attempts with exponential backoff. A retry is permitted only for
the observed fail-closed readiness signature: fingerprint not matched,
`missing_media`, zero writes/syncs, and complete cleanup. Integrity, CID, namespace,
or recovery-oracle failures stop immediately.

Board-01 with exact SD CID `FE343253440000002000000055019CB7` passed all six
physical `esp_restart` boundaries. Recovered generations were `1/1/1/1/1/2`; each
reopen returned three observations, preserved the generation-1 155-byte segment and
41-byte manifest CRC32C, wrote/synced zero bytes, returned `FR_OK`, and released
resources 12→0. Boundary 4 first produced transient immediate `missing_media`; a
zero-write read-only retry recovered generation 1, and the final read-only audit of
all six namespaces passed. This closes ST-HIL-A04/A06 for this one board/card
software-reset combination, not physical power-cut or endurance.

Version `0.31.0-sd-session-ram-review` then removed a redundant 4,672-byte physical
recovery `SurveySession` and reused `SessionStoreWorkspace::validationSession`, which
the common recovery path already owns and uses serially. Static RAM fell from 99,932
to 95,260 B. A new exact-CID boundary-6 run reached `sync_head`, recovered required
generation 2 with unchanged prior hashes and zero recovery writes/syncs, and completed
cleanup on its first attempt. This is E-BUILD-033/E-HIL-036 regression evidence for
the shared workspace; it does not repeat the full six-boundary matrix.

Version `0.33.0-sd-session-batch-throughput-measure` adds a fixed 64-observation FIFO
and publication policy: 2,048 encoded B, 5 s maximum latency, capacity, explicit Stop,
or safe shutdown. Host tests cover FIFO wrap-around, drop/high-water and scrub
counters, every trigger/precedence, and overflow-safe rate math. With measured Wi-Fi
p99 546 B/s, safety factor 4, and prior commit p99 591,651 us, the minimum batch is
1,293 B; the selected 2,048 B target exceeds that bound.

A physical exact-CID run in new namespace
`/leshy-hil/s1-batch-throughput-20260816-a` committed 32 generations of 64
observations and a 4,609 B encoded segment. All 32 commits and 96+96 barriers
completed, and generation 32 with 64 observations reopened before and after remount.
Encoded payload service rate was 9,068 B/s against the RB-06 requirement of 2,184
B/s: a pass with 4.15x margin. No formatting, deletion, existing-path overwrite, or
radio TX occurred; resources returned 12→0. This closes the performance part of the
batching design, while the synthetic fixture does not yet prove the real passive
Wi-Fi→queue→SessionStore path.

Version `0.34.0-wifi-passive-persist-measure` then acquires one atomic
EspRf+Storage+RadioSpi lease and joins the physical passive scanner to this FIFO/policy
and guarded FAT SessionStore. An exact-CID run completed four scans, accepted 29
observations with FIFO high-water 9/64 and zero drops, then committed generation 1
with a 1,334 B segment in 192,729 us at the 5 s latency trigger. Recovery before
unmount and after real remount/read-only reopen returned all 29 observations.
Effective encoded payload rate was 6,921 B/s, passing RB-06 by 3.17x; cleanup returned
the combined resource mask 14→0. Identifiers were not emitted in evidence and were
intentionally retained only inside the new isolated scratch Session. This is the
technical end-to-end path; product Start/Running/Stop, reboot Library, and export do
not yet use it.

Version `0.35.0-persistent-library-admission-measure` stops restoring the simulated
RAM Library after a successful path. New exact-CID namespace
`/leshy-hil/s3-wifi-library-20260816-a` accepted 52 observations from four scans at
FIFO high-water 18/64 and zero drops; the size trigger committed generation 1 with
a 2,499 B segment in 192,867 us. Recovery after real remount returned all 52, and
the 12,957 B/s effective rate passes RB-06 by 5.93x. The validated Session is copied
into the caller-owned Library workspace and receives runtime capability
`library.persistent_session` without declaring generic SD availability. The actual
TFT path Home→List→Detail→Export shows READY, `PERSISTENT SESSION | REAL`,
generation 1/valid, and `PERSISTED YES`; the serial artifact carries
`persistent=true`, `simulated=false`, Wi-Fi 52. Back releases the Storage+UI lease
5→0. This is current-boot admission after an explicit command: safe boot
mount/catalog/recovery is not implemented, so reboot still starts with simulated
Library.

Version 0.40 adds product-level authorization above the proven technical path. Boot
catalog access permits only the exact enrolled fingerprint, an existing
`/leshy/sessions/v1`, a guaranteed read-only non-writable driver, and lease 12.
Initialize/commit require explicit selection, a writable driver, byte budget, and
the same resources; format is forbidden. The combined Survey gate requires a
passive plan and lease 14 and never falls back to simulated/RAM. This is host plus
non-I/O board policy evidence, not a mount or write to the product namespace.

## Acceptance

| ID | Required result |
|---|---|
| ST-HIL-A01 | Read-only discovery records media kind, capacity, filesystem, stable fingerprint, and free space |
| ST-HIL-A02 | The run refuses media unless its disposable fingerprint and scratch namespace are explicitly selected |
| ST-HIL-A03 | Every operation is confined to a new bounded `/leshy-hil/<run-id>/` namespace |
| ST-HIL-A04 | Reset injection at all six boundaries always recovers either the prior valid generation or the fully synced new one |
| ST-HIL-A05 | Torn head, bad CRC, missing manifest, and manifest mismatch never become current |
| ST-HIL-A06 | Previously committed payload hashes are unchanged after every recovery |
| ST-HIL-A07 | SD and LittleFS are measured separately; throughput reports sample size, p50/p95/p99, sync latency, and free-space delta |
| ST-HIL-A08 | Physical power-cut repeats the boundary matrix before PR-005/RB-06 can be verified |

The offline Library/reopen, bounded export, non-mounting discovery, mount policy, SD
identity/geometry/technical-metadata paths, guarded FAT `SessionStore` commit plus
remount/reopen, a 32-commit p50/p95/p99 throughput distribution, and the host/static
reset harness plus physical six-boundary matrix are implemented. The fixed queue and
batched publication cadence are now host-tested, and E-HIL-038 delivers 9,068 encoded
B/s against the 2,184 B/s RB-06 target. The next safe work is to implement a board
adapter lifecycle satisfying read-only boot recovery and explicit bounded commit
policy, then connect the proven path to product Setup/Running/Stop & Commit and persistent Library
catalog/recovery. Export of this recovered Session in the current boot is already
confirmed by E-HIL-040. The readiness retry also awaits a natural transient. Physical power-cut
still needs a controller.
LittleFS is not touched until a dedicated disposable partition/image is proven; the
current flash filesystem may contain legacy/product data.
