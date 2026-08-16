# ADR-003 — Session/Capture schema and atomic storage

*Read in: **English** · [Русский](ADR-003-storage-schema.ru.md)*

- **Status:** accepted
- **Date:** 2026-08-16
- **Requirements:** PR-003, PR-005…PR-008, PR-012; NFR-007…NFR-009
- **Risks:** R-006, R-010, R-014, R-016
- **Stage:** S1 decision; minimum implementation in S3

## Context

Sessions must survive cancellation and power loss on both SD/FAT and LittleFS.
Captured source data must remain verifiable across decoder and schema changes. JSON
is suitable for interchange but too verbose for the canonical no-PSRAM write path;
filesystem rename alone is not a portable power-loss transaction.

## Decision

1. Canonical metadata and records use deterministic, versioned CBOR. Observation
   streams are append-only framed records with bounded length and CRC32C; a decoder
   validates both before allocating or parsing payload fields.
2. Capture payload bytes are immutable files identified by a local UUID and content
   checksum. Decode, edit, annotate, merge, or export creates metadata/derived data;
   it never overwrites the source payload.
3. A Session writes bounded segments. A segment is committed only after its footer,
   record count, and checksum validate. An incomplete tail is quarantined/ignored at
   recovery; earlier segments remain referenced and unchanged.
4. The logical commit point is a dual head (`A`/`B`) with generation, manifest
   checksum, and CRC. Update writes/syncs new payload/segments and a new manifest,
   then writes the older head slot. Boot selects the highest valid generation.
   Filesystem rename may optimize temporary cleanup but is not the sole commit proof.
5. Every object carries schema kind/version. Supported versions migrate forward into
   new derived records or fail clearly; the original bytes remain untouched.
6. SD is preferred for capacity; LittleFS is a supported fallback with the same
   logical contract and separate measured limits. JSON/CSV/PCAP and radio-specific
   files are imports/exports, never the canonical database.
7. Limits for record, segment, capture, nesting, and allocation are compile-time or
   profile configuration and are checked before work. No secret is included by
   default in Session metadata or summary export.

## Alternatives

- **One mutable JSON file per Session:** rejected for write amplification, RAM, and
  poor recovery.
- **SQLite:** rejected for S3 footprint/complexity; reconsider only with measured
  benefit inside RB budgets.
- **Rename-only atomicity:** rejected because FAT/LittleFS power-cut guarantees differ.
- **Raw structs:** rejected due to ABI, endianness, and migration fragility.

## Consequences

Recovery and migration are explicit and host-testable. Space reclamation needs a
separate bounded garbage collector that never removes data referenced by either
valid head. The exact CBOR field registry and segment size are implementation
artifacts governed by this ADR and measurements, not new architecture decisions.

## Verification

- golden canonical encodings and forward-version rejection/migration tests;
- fuzz/bounds corpus for frames, CBOR, heads, and manifests;
- power/cancel injection at every write/sync/head boundary on SD and LittleFS;
- recovery always selects one valid generation and preserves older source hashes;
- throughput meets RB-06 and WF-02/03 acceptance.
