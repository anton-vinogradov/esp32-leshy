# ADR-003 — schema Session/Capture и atomic storage

*Читать на: [English](ADR-003-storage-schema.md) · **Русский***

- **Статус:** accepted
- **Дата:** 2026-08-16
- **Requirements:** PR-003, PR-005…PR-008, PR-012; NFR-007…NFR-009
- **Risks:** R-006, R-010, R-014, R-016
- **Этап:** решение S1; минимальная реализация в S3

## Контекст

Sessions должны переживать cancel и power loss на SD/FAT и LittleFS. Captured source
data остаются проверяемыми после изменения decoder/schema. JSON подходит для
interchange, но слишком велик для canonical no-PSRAM write path; filesystem rename
сам по себе не является переносимой power-loss transaction.

## Решение

1. Canonical metadata/records используют deterministic versioned CBOR. Observation
   streams состоят из append-only framed records с bounded length и CRC32C; decoder
   проверяет оба до allocation и parse payload fields.
2. Capture payload bytes — immutable files с local UUID и content checksum. Decode,
   edit, annotate, merge или export создаёт metadata/derived data и не перезаписывает
   source payload.
3. Session пишет bounded segments. Segment committed только после проверки footer,
   record count и checksum. Incomplete tail при recovery quarantined/ignored; старые
   segments остаются referenced и unchanged.
4. Logical commit point — dual head (`A`/`B`) с generation, manifest checksum и CRC.
   Update пишет/sync новые payload/segments и manifest, затем записывает более старый
   head slot. Boot выбирает максимальное valid generation. Rename можно использовать
   для cleanup temp, но это не единственное доказательство commit.
5. Каждый object имеет schema kind/version. Supported versions мигрируют вперёд в
   новые derived records или отклоняются понятно; original bytes неизменны.
6. SD предпочтительна по capacity; LittleFS — supported fallback с тем же logical
   contract и отдельными measured limits. JSON/CSV/PCAP и radio-specific files —
   import/export, не canonical database.
7. Limits record/segment/capture/nesting/allocation задаются compile-time/profile и
   проверяются до работы. Session metadata/summary export по умолчанию без secrets.

## Альтернативы

- **Один mutable JSON на Session:** rejected из-за write amplification, RAM, recovery.
- **SQLite:** rejected для S3 по footprint/complexity; только после measured benefit.
- **Только rename atomicity:** rejected — FAT/LittleFS различаются при power cut.
- **Raw structs:** rejected из-за ABI, endianness и migration fragility.

## Последствия

Recovery/migration явны и host-testable. Space reclamation требует отдельного bounded
garbage collector, не удаляющего данные, referenced любым valid head. Exact CBOR
field registry и segment size — implementation artifacts внутри ADR/measurements.

## Проверка

- golden canonical encodings и forward-version rejection/migration tests;
- fuzz/bounds corpus для frames, CBOR, heads и manifests;
- power/cancel injection на каждой write/sync/head boundary для SD/LittleFS;
- recovery выбирает один valid generation и сохраняет старые source hashes;
- throughput проходит RB-06 и acceptance WF-02/03.
