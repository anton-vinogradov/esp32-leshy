# ESP32-Leshy 1.x — current status

*Read in: **English** · [Русский](STATUS.ru.md)*

Last updated: **17 August 2026**.

This is the only document containing live project state. Stable stage boundaries are
in [DELIVERY_PLAN.md](DELIVERY_PLAN.md); update rules are in
[GOVERNANCE.md](GOVERNANCE.md).

## Now

- **Active stage:** `S1 — Evidence baseline`.
- **Last completed stage:** `S0 — Governance and generation boundary`.
- **Repository baseline:** `c31565c` (`v0.9.1-3-gc31565c`) plus unreleased
  documentation and feasibility prototypes in the worktree.
- **Release state:** 0.x is a frozen PoC; no user-facing 1.x binary exists.
- **Current objective:** confirm ESP32-DIV constraints and promote the 1.0.0 PRD from
  draft to an accepted baseline.

## Stage state

| Stage | Status | Confirmed result | Remaining gate work |
|---|---|---|---|
| S0 | `done` | 0.x archive, governance, delivery plan, status, traceability, 0.x installer label | — |
| S1 | `active` | vision, competitive snapshot, draft PRD 0.2, product-reviewed `CAP-001…047`, UX-01/02 and Stage Demo contracts, workflows, constrained hardware unknowns, partial HIL/budgets, risk register, five ADRs, and a first automatic device-smoke with firmware-reported build identity | remaining physical/storage evidence and PRD baseline review |
| S2 | `planned` | capability-built home, unified input/TFT capture, atomic-head/media-guard contracts, guarded FAT evidence backend, and AppRuntime/ResourceBroker lease path exist | no production mount policy or complete product workflow |
| S3 | `planned` | bounded Survey/UI, deterministic codec, auto-publishing SessionStore, guarded FAT persistence/reopen/throughput/software-reset recovery, generation fallback, and a real passive Wi-Fi→FIFO→persistent SessionStore/remount path run on board-01 with RB-06 margin; the recovered Session is admitted to ordinary Library and exported as persistent/real in the current boot | diagnostic path is not yet connected to product Start/Running/Stop or boot-time catalog/recovery; power-cut, endurance, and LittleFS parity remain; requires S2 gate |
| S4 | `planned` | target cross-radio model exists | requires S3 gate |
| S5 | `planned` | standard hardware scope is listed | requires S4 gate |
| S6 | `planned` | Targets/comparison/companion are conceptual | requires S5 gate |
| S7 | `planned` | Lab/SDK boundaries are conceptual | requires S6 gate |
| S8 | `planned` | release gates are defined | requires S7 gate |

## S1 completed work

- separated the 0.x and 1.x generations;
- reviewed original ESP32-DIV, GhostESP, Bruce, Marauder, Flipper Zero, and secondary
  references;
- defined `J-01…J-06`, `PR-001…PR-019`, and `NFR-001…NFR-010`;
- defined the first vertical outcome as a persisted Survey Session;
- created the bilingual [`HARDWARE_ENVELOPE`](HARDWARE_ENVELOPE.md) from v2
  schematic/BOM, original firmware, and vendor datasheets;
- defined physical resource domains, safe probe order, `HW-T01…HW-T11`, and open
  questions `HW-U01…HW-U10`;
- refined PR-001/003/014 and architecture for the detachable RF shield, external
  GPS/PN532 assemblies, and a multi-state capability inventory.
- created an isolated non-transmitting diagnostic image and operator protocol for
  HW-T01/T04/T06/T07/T11; NRF #3 fails closed as `unknown` until HW-T08.
- board-01 confirms ESP32-S3 rev 0.2, 16 MB Quad flash, and no PSRAM; read-only I²C
  responds at `0x20`/`0x75`, and CP2102 backup/upload/console works;
- retained a private hash-identified 16 MB pre-flash backup and unedited raw HIL logs.
- after operator confirmation, read NRF #1/#2 and CC1101 identities without TX
  opcodes; NRF #3 remains `unknown`, and physical RF silence is not yet measured.
- specified `WF-01…WF-05` reference workflows covering J-01…J-06, each with explicit
  happy/error/cancel paths, measurable acceptance IDs, and planned evidence.
- created the resource-budget ledger with measured flash/heap evidence, no-PSRAM and
  OTA guardrails, and explicit storage/power/shared-bus unknowns.
- created risk register R-001…R-017 with controls, closure owners, stage gates, and
  an explicit critical physical-stop risk for any active action.
- decomposed complete user-facing 1.0 scope into `CAP-001…CAP-047`; UX is controlled
  through S1 direction and the S2 real-TFT `UX-01…UX-08` baseline, while every
  S2…S8 stage closes through a reproducible `DEMO-S*`, not by waiting for final firmware.
- product review closed six hidden scope gaps: Wi-Fi packet/PCAP Capture, screenshot
  evidence, offline enrichment, safe feedback service, scoped connectivity, and data
  backup/restore; the catalog is accepted as the complete working 1.0 boundary.
- UX-01 fixed the six-task Home, 28 screen contexts, typed Actions, and physical
  Back/Panic mapping; UX-02 defines unavailable/loading/running/degraded/error/
  confirm/success plus cleanup for every WF-01…WF-05 screen family.
- accepted ADR-001…ADR-005 for the pinned clean toolchain, fail-closed resource
  policy, atomic versioned storage, one typed Action boundary, and hybrid
  pre-release HIL.
- assigned binding fail-closed dispositions to HW-U01…HW-U10; each physical unknown
  now has a safe 1.x default and named closure evidence.
- built and ran the independent no-legacy 1.x target on board-01; display, five
  active-low keypad inputs, and sub-second interactive-ready milestone are measured;
- added one physical/diagnostic UI action path and actual tiled TFT GRAM capture;
  board-01 is intentionally left on the 1.x diagnostic target while its hash-identified
  full 0.x backup remains available.
- implemented the ADR-003 dual-head wire/recovery contract and injected failure at
  every commit boundary without writing unknown physical media.
- implemented exact-fingerprint disposable-media authorization with bounded scratch
  namespace/size and negative tests; board diagnostics remain read-only.
- replaced the static probe menu with an `AppCatalog` projected from capability
  states; unavailable Survey/Library explain themselves before launch.
- integrated the clean target with `AppRuntime` and an all-or-none `ResourceBroker`;
  board-01 completed 1,000 launch/Back cycles with zero leaked leases, unchanged heap,
  and p99 Back/release acknowledgement below 99 ms.
- added the first bounded SurveySession/Observation model and passive-only Wi-Fi
  ingress contract; the measurement image statically forbids Wi-Fi APIs and keeps the
  radio untouched until physical no-TX evidence is possible.
- added a three-observation golden Wi-Fi trace through the first List/Detail
  controller; Back preserves the running Session and explicit Stop is idempotent.
- rendered that golden workflow on board-01 with unambiguous `SIMULATED / RF OFF`
  state; actual TFT traces prove Back preserves the Session and explicit Stop precedes
  Home/lease release.
- implemented the bounded schema-1 Session codec: canonical CBOR manifest/records,
  per-record and segment CRC32C, footer validation, offline reopen, and deterministic
  JSON summary; exhaustive corruption/truncation tests fail closed.
- ran the stopped golden Session through encode → AtomicHead selection → reopen →
  JSON on board-01; all three observations survived, radio/storage remained untouched,
  and Home release returned to zero leases.
- ran the same commit contract on real temporary host files behind a valid
  `StorageGuard` permit: seven isolated scenarios used file/directory `fsync`; all six
  injected failures reopened generation 1, the complete commit reopened generation 2,
  and prior bytes remained unchanged.
- extracted a bounded hardware-independent `SessionStore`: it owns fixed paths,
  codec workspace, automatic generation/older-head publication, rollover, full
  payload validation, and fallback; empty initializes, while corrupt/ambiguous heads
  fail closed without writes.
- killed a commit child with real `SIGKILL` after each of six boundaries and recovered
  in the parent from files only; each result was either the prior generation or a
  fully materialized new one, reopened three observations, and preserved prior bytes.
- ran common `SessionStore` on board-01 through a bounded two-generation RAM adapter:
  automatic 1/A→2/B publication, reopen generation 2, deliberate new-segment
  corruption, `invalid_payload` classification, and fallback to generation 1 all pass.
- added a bounded offline Library controller over reopened Session metadata; board-01
  completes List→Detail→Back→Home while explicitly displaying
  `SIMULATED RAM | VOLATILE | RF OFF`, using only a UI lease.
- rejected the first Library board build after its stack canary exposed a full
  `SurveySession` temporary in the reopen path; decoding now uses caller-owned
  bounded storage, and the corrected image passes host tests and HIL.
- added an explicit Detail→Export Ready action and bounded deterministic Library JSON
  artifact; board-01 exposes it only after confirmation, retains provenance, and
  fails closed with `not_requested` after returning Home.
- added a typed read-only media-adapter/discovery boundary; board-01 samples GPIO38
  without reconfiguration but keeps SD `unknown`, because an unverified polarity may
  not claim card presence or absence. No mount or write occurs.
- added a mount-authorization gate requiring explicit target selection, a proven
  read-only driver, format disabled, and exclusive Storage+RadioSpi ownership; the
  stock Arduino SDFS path is rejected as `driver_not_read_only` without execution.
- added a fixed identification-only SD protocol plan outside SDFS: bounded
  CMD0/8/55/ACMD41/58/10/9, CID/CSD reads only, with mutating commands and board
  execution statically rejected.
- added a bounded SD transcript parser with response/echo/OCR/CID/CSD/capacity
  validation; 256 one-bit CID/CSD faults fail closed and the board runs only a
  synthetic no-SPI fixture.
- added an executable identification state machine over a deterministic fake
  transport; every exchange failure, the 100-attempt timeout, sequence drift, and
  physical-transport invocation fail closed before any hardware I/O.
- added allocation-free SD SPI wire framing: known CRC7 command frames, bounded R1
  and data-token polling, exact R3/R7 reads, and CRC16 validation; the board exposes
  the contract with zero commands and physical execution disabled.
- identified one explicitly selected disposable microSD through guarded 400 kHz
  physical SPI in three read-only runs; CID/CSD/capacity were stable, every cleanup
  released Storage+RadioSpi, and no mount, data-block read, write, or radio command ran.
- read exactly LBA0 through one bounded CMD17 and retained only its fingerprint plus
  valid MBR geometry: FAT32-LBA partition type `0x0C`, first LBA 2,048, and
  122,136,512 sectors; the raw sector was not retained.
- read exactly the partition boot sector derived from that validated MBR and confirmed
  coherent FAT32 geometry, including 512-byte sectors, 64 sectors/cluster, root
  cluster 2, and a total matching the partition; no mount, directory, or file read ran.
- applied the explicitly approved `counts_hash_only` privacy policy to one derived
  FAT32 root-directory sector; retained only entry-type counts and CRC32C, then
  zeroed the raw buffer without retaining names or reading file data.
- extended the same policy sequentially across the bounded root cluster; the second
  sector contained the end marker, producing a complete 26-entry metadata inventory
  for this card state without reading a FAT chain, names, or file content.
- read exactly the boot-declared FAT32 FSInfo sector and validated all three
  signatures plus bounded free/next hints; retained only technical counts/CRC32C,
  zeroed the buffer, and reduced static RAM through one shared SD evidence workspace.
- one additional exact first-FAT-sector cross-check reads FAT[0…2] only: media
  `0xF8` matches, the volume is clean/no-error, and root cluster 2 is EOC; FSInfo
  hints are compatible, no FAT chain/name/file data is read, and both buffers are zeroed.
- added a guarded Arduino FAT backend for the common `SessionStore`; one exact-CID,
  disposable-card run created only a new bounded scratch namespace, committed
  generations 1/A and 2/B with six file and six directory syncs, then survived a
  real unmount/remount and read-only reopen with generation 2/three observations.
- repeated the same command against the now-existing run ID: `StorageGuard` refused
  it as `scratch_already_exists` with zero logical bytes written and no deletion;
  reset injection, power-cut, and LittleFS parity were open at that evidence point.
- replaced the intermittent Arduino SD sector transport with guarded ESP-IDF SDSPI;
  one 32-commit exact-CID run completed 96 file and 96 directory barriers, reported
  p50/p95/p99 405,729/571,276/591,651 us, and recovered generation 32 before and
  after remount; an exact retry refused the existing namespace with zero writes.
- implemented the six-boundary logical-reset harness:
  a host-tested `SessionStoreIo` wrapper stops only after a successful write or
  durability boundary; board arm/recovery commands require exact CID, unique bounded
  namespaces, software-reset reason, read-only reopen, allowed generation, and
  unchanged prior payload hashes. The matrix runner refuses to start without an
  explicit `--execute-reset-matrix` acknowledgement.
- passed all six software-reset boundaries on board-01/disposable SD: boundaries
  1…4 recovered generation 1, boundary 5 recovered allowed generation 1, and fully
  synced boundary 6 recovered generation 2; every read-only recovery preserved the
  prior hashes and wrote/synced zero bytes. Boundary 4 exposed one transient immediate
  SD re-identification failure; a bounded read-only retry and the final six-namespace
  audit passed.
- closed the 1,628 B RB-03 static-RAM overage without weakening the guardrail:
  map review removed one redundant 4,672 B physical-recovery `SurveySession`, reused
  the existing caller-owned validation workspace, and measured 95,260 B static RAM;
  a new exact-CID boundary-6 run recovered generation 2 with zero recovery writes.
- measured the first physical source through an explicit passive-only Wi-Fi adapter:
  32/32 scans accepted 414 normalized Observations with zero drop/reject and p99
  encoded ingress 546 B/s; heap returned to baseline and RF/storage leases cleaned up.
  Physical no-TX remains unverified without an RF instrument.
- compared that source with SD under RB-06: required storage is 2,184 B/s, while the
  current fsync-every-generation workload provides 536 B/s. The next storage design
  must use bounded queueing and batching without weakening atomic publication.
- a fixed 64-observation FIFO and 2 KiB/5 s/Stop/safe-shutdown publication policy are
  host-tested; the physical 64-observation workload delivers 9,068 encoded B/s,
  4.15x RB-06, and reopens generation 32 after 32 commits/remount without changing
  the atomic dual-head contract.
- real passive Wi-Fi, the fixed FIFO, batch policy, and guarded SessionStore are joined
  in one board run: 29 observations from four scans persist with zero drops, the
  latency trigger publishes generation 1, and remount/read-only reopen returns all
  29; effective payload rate 6,921 B/s passes RB-06 by 3.17x and the combined lease
  returns 14→0.
- the next board run admits the recovered generation to ordinary Library instead of
  restoring the simulated fixture: 52 observations, FIFO high-water 18/64, zero
  drops, and 12,957 encoded B/s; Home/List/Detail/Export show READY,
  PERSISTENT/REAL, generation 1/valid, and PERSISTED YES, while the serial artifact
  carries `persistent=true`, `simulated=false`; Back returns lease mask 5→0.
- ADR-005 is accepted and the first manifest-driven pre-release device smoke is
  implemented: the runner flashed the exact app candidate twice and, after a
  separate golden bootstrap, passed cold boot→Home→Diagnostics→Back with actual TFT
  RGB565 comparisons, zero pixel mismatch, owner/lease `none`/`0`, heap above
  128 KiB, and GPIO2 LOW; an independent verifier binds bundle/candidate hashes and
  rejects an unsigned local result as standalone release evidence by default.
- candidate 0.36 adds the full firmware-reported ESP app ELF SHA-256; the runner
  independently extracts the same digest from the candidate app descriptor before
  flashing and requires exact equality in both cold-boot and repeated metrics
  records. Two intermediate runs failed closed on a truncated runtime digest and an
  undersized bounded JSON envelope; the corrected physical run passed with all
  three identity bindings equal.
- candidate 0.37 adds an allocation-free HIL session envelope: one random 128-bit
  run ID binds the candidate manifest, firmware begin/end, run, and local result;
  firmware rejects nested, malformed, or identity-mismatched sessions. The runner
  first retains the candidate in the bundle and flashes that immutable copy, so the
  verifier can recheck self-contained evidence without an external build path.
- A historical OpenSSL Ed25519 prototype returned `release_eligible=true` for a copy
  of a physical bundle, but the 2026-08-17 product decision rejected a persistent
  station key. Production trust moved to keyless GitHub OIDC/Sigstore attestations
  of candidate and evidence archive; the local signing path has been removed.
- found the author's upstream evidence for the false GPIO2 buzzer and verified 0.x
  LOW fix; clean 1.x now establishes OUTPUT LOW before console/display through a
  dedicated BoardSafeOutputs adapter, forbids direct app/driver control, and emits
  boot/runtime diagnostic state.

## S1 priority queue

Unavailable boards or instruments limit physical evidence but do not pause the next
safe documentation/prototype item.

1. Complete partial `HW-T01/T04/T07`: module marking, second v2 board, exact
   power-manager marking, and separate GPS/PN532 assemblies only when available.
2. Run manual `HW-T02/T03/T05/T08/T09/T10`; run `HW-T06` only after GPS/PN532 absence
   is confirmed and an RF detector/logic analyzer is attached.
3. Productize the proven source→queue→store→Library/export path: Survey
   Setup/Running/Stop & Commit, visible progress/drop/storage states, and boot-time
   catalog/recovery of the same persistent Session. Exercise reset-readiness retry on the next
   natural transient. LittleFS still needs a separately proven disposable image;
   physical power-cut needs a controller.
4. Measure power/shared-bus/no-TX stability when instruments are available.
5. Update PRD and traceability from measurements, then review the S1 gate.

## Evidence on the current baseline

| ID | Check | Result | Limitation |
|---|---|---|---|
| E-DOC-001 | All local Markdown links | pass, 2026-08-16 | navigation only |
| E-DOC-002 | `docs/manifest.json` via `jq` | pass, 2026-08-16 | installer still flashes 0.x |
| E-TEST-001 | `tools/test.sh` | pass, 2026-08-16 | host contracts; physical storage/power failures require HIL |
| E-BUILD-001 | `tools/build.sh`, ESP32-S3 | pass: RAM 98,748 B (30.1%), flash 1,995,896 B (59.7%) | 0.x + prototype build, not a 1.x target |
| E-HW-DESIGN-001 | v2 main/shield schematic + BOM + original pin map + vendor datasheets | hardware envelope created, 2026-08-16 | design evidence; does not replace `HW-T01…HW-T11` |
| E-BUILD-002 | `tools/build_hil_probe.sh`, probe 0.1.1 | pass: RAM 23,872 B (7.3%), flash 354,548 B (10.6%); board-01 flash hash verified | evidence tool, not the 1.x product target |
| E-TEST-002 | HIL probe logic tests + static no-TX guard | pass, 2026-08-16 | only an HW-T06 detector trace proves physical silence |
| E-HIL-001 | board-01 HW-T01 runtime | partial: ESP32-S3 rev 0.2, 16 MB Quad flash, 0 PSRAM | no module photo or second board |
| E-HIL-002 | board-01 HW-T04 read-only I²C | partial/pass: `0x20`, `0x75`, zero writes | exact IP5306 variant unresolved |
| E-HIL-003 | board-01 HW-T07 GPS RX-only for 10 s | inconclusive: zero bytes/NMEA | GPS absence unproven; PN532 not run |
| E-HIL-004 | board-01 HW-T11 | pass: both USB paths, reset, download, console, full hash-verified 16 MB restore, and operator-confirmed original 0.x UI | CP2102 460800 unstable; verified ceiling 230400 |
| E-HIL-005 | board-01 guarded HW-T06 | partial: NRF #1/#2 detected; CC PARTNUM `0x00`, VERSION `0x14`; zero CE-high/TX commands | operator has no logic/RF detector; NRF #3 gated by HW-T08 |
| E-BUDGET-001 | `RESOURCE_BUDGETS` build + board-01 ledger | partial: physical flash/PSRAM, slots, clean/probe/legacy/interactive sizes, runtime heap, interactive-ready, upload/recovery | product-home boot, storage, power, and shared-bus measurements remain open |
| E-RISK-001 | `RISK_REGISTER` review | R-001…R-017 have treatment, owner, closure evidence, and gate controls | risks remain open until their named evidence exists |
| E-ADR-001 | ADR-001…ADR-004 + traceability review | accepted: toolchain, resource policy, storage schema/atomicity, Action boundary | implementation and verification begin in their named S2+ gates |
| E-BUILD-003 | `tools/build_1x_measure.sh`, clean target 0.1.0-measure | pass: RAM 22,576 B (6.9%), flash 320,952 B (7.7% of 4 MiB app slot); no dependencies/legacy sources | bootstrap only; no display/input/storage/source |
| E-HIL-006 | clean target on board-01/native USB | profile match; runtime-ready 7,224 µs; heap total/free/min 389,680/349,660/344,512 B; full 0.x restore hash-verified | runtime milestone is not interactive UI boot evidence |
| E-BUILD-004 | `0.2.0-interactive-measure` | pass: RAM 24,460 B, flash 391,719 B; app/factory 392,128/457,664 B | probe screen only; no storage/source |
| E-HIL-007 | interactive target on board-01 | display visible; PCF8574 detected; idle `0xFF` plus five distinct active-low inputs; interactive-ready 0.363 s; heap free/min 343,420/338,272 B | semantic key labels inherit the known v2 map; no final product UI |
| E-BUILD-005 | `0.3.0-ui-automation-measure` | pass: RAM 26,388 B, flash 394,843 B; app/factory 395,248/460,784 B; all host/isolation checks pass | diagnostic shell, not user firmware |
| E-HIL-008 | board-01 UI action/capture trace | serial and physical input share `UiController`; stateful navigation captured 240×320/153,600 B TFT GRAM; post-capture revision matched; passive serial reconnect preserved state without reset | verifies transport/probe pages, not workflow UI or physical brightness |
| E-STORAGE-001 | ADR-003 `AtomicHead` host fault matrix | pass: fixed 24 B encoding; CRC32C/bounds; 192 one-bit corruptions; missing/mismatched manifest; conflict/rollover; failures at six write/sync boundaries keep the prior generation | no filesystem backend, throughput, reset, or physical power-cut evidence yet |
| E-BUILD-006 | `0.4.0-storage-contract-measure` | pass: RAM 26,388 B, flash 395,115 B; app/factory 395,520/461,056 B | atomic head is host-tested; no filesystem backend |
| E-HIL-009 | board-01 storage contract report + UI capture | pass: head 24 B/schema 1/six boundaries/`write_enabled=false`; interactive-ready 0.369 s; TFT/post-state revision agree | read-only; does not verify media, throughput, reset, or power-cut |
| E-STORAGE-002 | `StorageGuard` negative matrix | pass: exact fingerprint + explicit disposable + safe new run namespace + bounded size/reserve required; every invalid condition refuses permit | policy only; no media was mounted or written |
| E-BUILD-007 | `0.5.0-storage-guard-measure` | pass: RAM 26,388 B, flash 395,627 B; app/factory 396,032/461,568 B | no filesystem backend |
| E-HIL-010 | board-01 guard policy + UI capture | pass: scratch `/leshy-hil/`, exact/disposable/refuse-existing; mount/format/write false; interactive-ready 0.369 s | read-only policy evidence |
| E-CAPABILITY-001 | `AppCatalog` + dynamic `UiController` host tests | pass: available projection, disabled reasons, blocked launch, enabled launch/Back | three S2 entries only; no product workflow |
| E-BUILD-008 | `0.6.0-capability-home-measure` | pass: RAM 26,436 B, flash 396,243 B; app/factory 396,640/462,176 B | measurement target |
| E-HIL-011 | board-01 capability-home scenarios | pass: Diagnostics ready/open/back; Survey/Library disabled with reasons; actual TFT + revision traces; interactive-ready 0.373 s | does not verify full apps or external cold-boot timing |
| E-RUNTIME-001 | `AppRuntime` + `ResourceBroker` host tests | pass: all-or-none acquisition, busy/disabled/invalid rejection, idempotent launch, stop/release | single-threaded S2 slice; physical shared-bus arbitration remains open |
| E-BUILD-009 | `0.7.0-runtime-leases-measure` | pass: RAM 26,468 B, flash 396,887 B; app/factory 397,296/462,832 B | measurement target; Diagnostics is still a shell |
| E-HIL-012 | board-01 runtime leases + 1,000 open/Back cycles | pass: disabled app obtains no lease; Diagnostics start/stop owns/releases display; zero leaked leases or heap change; Back/release p99/max 98.801/99.345 ms | host acknowledgement timing, not external cold-boot or RF/storage bus evidence |
| E-SURVEY-001 | SurveySession/Observation/Wi-Fi/controller tests | pass: passive-only validation, normalization/bounds, monotonic sequence, idempotent stop, 64-entry capacity/overflow, and golden List→Detail→Back trace | simulated contract only; no Wi-Fi driver, rendered product UI, or persisted Session |
| E-BUILD-010 | `0.8.0-survey-contract-measure` | pass: RAM 26,468 B, flash 397,571 B; app/factory 397,968/463,504 B; clean-target guard forbids Wi-Fi API | no running source or rendered Survey workflow |
| E-HIL-013 | board-01 no-RF Survey contract | pass: current hash flashed; passive-only/plan valid; active probe, directed SSID, driver start, and radio touch false; capacity 64; Home TFT/state captured | contract evidence only; physical RF silence still requires a detector |
| E-BUILD-011 | `0.9.0-survey-golden-ui-measure` | pass: RAM 31,156 B, flash 405,223 B; app/factory 405,632/471,168 B | in-memory golden data; no hardware source/storage |
| E-HIL-014 | board-01 golden Survey UI | pass: simulated Home→List→Detail→Back keeps running/lease; explicit Stop then Home releases owner/lease; final TFT review clean | no persistence/reopen/export and no physical RF evidence |
| E-STORAGE-003 | `SessionCodec` host golden/fault matrix | pass: canonical schema-1 CBOR; framed records + footer CRC32C; exact 41/155 B golden manifest/segment; reopen + deterministic JSON; every manifest bit, every segment truncation, and one bit in every segment byte rejected | no filesystem backend or physical media |
| E-BUILD-012 | `0.10.0-session-codec-measure` | pass: RAM 48,628 B, flash 416,175 B; app/factory 416,576/482,112 B | bounded in-memory codec workspace; no filesystem backend |
| E-HIL-015 | board-01 Session codec round-trip | pass: explicit Stop → encode → head select → reopen 3 observations → JSON; storage/radio false; final Home owner none/lease 0; heap total/free/min 362,088/319,252/314,104 B | in-memory self-check, not persistence/reset/power-cut evidence |
| E-STORAGE-004 | guarded host real-filesystem commit fixture | pass: valid exact-fingerprint/1 MiB permit; seven isolated real-file scenarios; 30 file + 16 directory fsync calls; six failures recover generation 1, complete recovers generation 2; both reopen 3 observations; prior bytes unchanged; fixture cleaned | modeled call failures, not process kill, ESP reset, removable media, or power cut |
| E-STORAGE-005 | bounded `SessionStore` + host `SIGKILL` recovery | pass: automatic empty→generation 1/A→generation 2/B, uint32 rollover, corrupt-new fallback, corrupt-store refusal; six children killed after distinct boundaries; recovery from files returns generation 1 before head and generation 2 after head, always reopens 3 observations and preserves prior bytes | process death on host, not kernel crash, ESP reset, removable media, or power cut |
| E-BUILD-013 | `0.11.0-session-store-measure` | pass: RAM 74,148 B, flash 458,847 B; app/factory 459,248/524,784 B | two maximum-size RAM generations are diagnostic-only; no persistent backend |
| E-HIL-016 | board-01 bounded RAM SessionStore | pass: stopped Session auto-commits 1/A→2/B; generation 2 reopens 3 observations; corrupt-new `invalid_payload` falls back to generation 1/3 observations; six file + six directory sync calls modeled; radio/physical storage false; Home owner none/lease 0 | RAM-backed target orchestration, not persistence/reset/power-cut evidence |
| E-LIBRARY-001 | bounded offline Library controller host tests | pass: stopped/valid admission, running/invalid/duplicate rejection, four-entry capacity, List→Detail→Back, provenance; reopen decodes into caller-owned workspace | RAM/simulated data only; no export transport or physical persistence |
| E-BUILD-014 | `0.12.0-library-offline-measure` | pass: RAM 79,132 B, flash 465,563 B; app/factory 465,968/531,504 B | bounded RAM Library; no persistent backend |
| E-HIL-017 | board-01 offline Library workflow | pass: Home→List→Detail→Back→Home; generation 1/3 observations/valid; volatile and RF-off provenance visible; only UI lease held; `radio_touched=false`; heap total/free/min 331,584/288,748/283,600 B | simulated RAM fixture, not persistence/reset/power-cut evidence |
| E-EXPORT-001 | bounded Library export host tests | pass: explicit Export Ready transition, exact deterministic JSON, provenance, short-buffer and missing-Session refusal, three-level Back | serial NDJSON only; no file or companion delivery |
| E-BUILD-015 | `0.13.0-library-export-measure` | pass: RAM 79,772 B, flash 467,247 B; app/factory 467,648/533,184 B | export is bounded serial output, not persistence |
| E-HIL-018 | board-01 explicit Library export | pass: Detail→Right→Export Ready; TFT shows JSON/serial/not persisted/RF off; valid artifact includes generation/integrity/session; Export→Detail→List→Home releases UI lease; command on Home returns `not_requested`; heap total/free/min 330,944/288,108/282,960 B | no physical media or companion transport |
| E-STORAGE-006 | read-only media-adapter/discovery contract tests | pass: non-authoritative detect cannot claim present/absent; detected requires RO mount/filesystem/fingerprint/capacity; invalid metadata/mount state/write-enabled fail closed; bounded JSON | no SD protocol or filesystem operation |
| E-BUILD-016 | `0.14.0-storage-discovery-measure` | pass: RAM 80,588 B, flash 469,199 B; app/factory 469,600/535,136 B | GPIO sample + contract only; no mount |
| E-HIL-019 | board-01 SD discovery | pass: GPIO38 sampled level 0 without reconfiguration; validation valid but status remains `unknown`, detect non-authoritative; mount false, fingerprint/filesystem/capacity unknown, write false, guard required; Home owner none/lease 0; heap total/free/min 330,128/287,292/282,144 B | does not prove polarity, card presence, FAT, CID, shared SPI, or persistence |
| E-STORAGE-007 | read-only mount authorization tests | pass: invalid discovery/slot/repeat/selection/driver/format/resources/conflict all refuse; only complete request permits; required mask Storage+RadioSpi | authorization only; no SD command or mount |
| E-BUILD-017 | `0.15.0-mount-policy-measure` | pass: RAM 80,588 B, flash 470,215 B; app/factory 470,624/536,160 B | policy report only; no driver execution |
| E-HIL-020 | board-01 mount policy | pass: actual `explicit_target_required`; hypothetical selection `driver_not_read_only`; Arduino SDFS RO guarantee false; required/owned resources 12/0; format/mount/execution/write false; Home lease 0; heap total/free/min 330,128/287,292/282,144 B | stock driver rejected; no SD/SPI/filesystem evidence |
| E-STORAGE-008 | SD identification-plan tests | pass: exact CMD0/8/55/41/58/10/9 order, init bound 1…100; eleven mutating command classes rejected; sequence drift and execution-enabled reject; invalid plan cannot format evidence | plan only; no response parser or SPI transport |
| E-BUILD-018 | `0.16.0-sd-ro-protocol-measure` | pass: RAM 81,100 B, flash 471,099 B; app/factory 471,504/537,040 B | protocol contract only; execution disabled |
| E-HIL-021 | board-01 SD RO protocol report | pass: identification-only plan valid; CID/CSD true, data reads/write/erase/format false; max init 100; execution false; mount permit and disposable card required; Home lease 0; heap total/free/min 329,616/286,780/281,632 B | no SD command, response, CID/CSD, or bus evidence |
| E-STORAGE-009 | SD transcript parser fault matrix | pass: response/echo/init/OCR/CID/CSD/CSD-v2/capacity validation; CRC16 check vector; all 256 one-bit CID/CSD mutations rejected | synthetic transcript only; no command transport or physical SPI |
| E-BUILD-019 | `0.17.0-sd-parser-measure` | pass: RAM 81,804 B, flash 472,987 B; app/factory 473,392/538,928 B | parser fixture only; physical SPI false and commands 0 |
| E-HIL-022 | board-01 SD parser fixture | pass: 16 MiB synthetic high-capacity identity, init 3, CID/CSD CRC valid; fake transport, commands 0, physical SPI/write/radio false; Home lease 0; heap total/free/min 328,912/286,076/280,928 B | transcript interpretation, not physical identity or framing |
| E-STORAGE-010 | fake SD transport state-machine tests | pass: exact command/argument sequence, 11 exchange-boundary failures, 100-attempt/202-exchange timeout, sequence violation, invalid plan zero calls, physical transport zero calls | deterministic fake only; no bus acquisition or SPI framing |
| E-BUILD-020 | `0.18.0-sd-transport-measure` | pass: RAM 82,316 B, flash 474,959 B; app/factory 475,360/540,896 B | fake transport only; physical adapter rejected |
| E-HIL-023 | board-01 fake SD transport | pass: 11/11 exchanges, init 3, parsed 16 MiB; fake transport, physical SPI/write/radio false; Home owner none/lease 0; heap total/free/min 328,400/285,564/280,416 B | state-machine execution, not physical SD/SPI/no-TX evidence |
| E-STORAGE-011 | SD SPI wire-codec tests | pass: known CMD0/CMD8 CRC7 frames; exact allowed arguments; eleven mutating classes refused; R1 1…16 and data token 1…8 bounds; timeout/invalid/truncated/CRC16 faults rejected | byte fixtures only; no CS, clocks, bus, or physical transport |
| E-BUILD-021 | `0.19.0-sd-wire-measure` | pass: RAM 82,828 B, flash 476,051 B; app/factory 476,448/541,984 B | wire contract only; execution disabled, commands 0 |
| E-HIL-024 | board-01 SD wire report | pass: known CMD0/CMD8 frames, CRC7/CRC16 and poll bounds; execution/physical SPI/commands/write/radio false; Home owner none/lease 0; heap total/free/min 327,888/285,052/279,904 B | framing contract, not physical SD identity/shared-bus/no-TX evidence |
| E-STORAGE-012 | physical SD permit/adapter safety tests | pass: physical transport receives zero calls without selection, identification-only contract, exact Storage+RadioSpi ownership, and no conflict; GPIO is confined to one checked adapter with no filesystem/write APIs | software/static evidence cannot prove RF silence or electrical timing |
| E-BUILD-022 | `0.20.0-sd-physical-id-measure` | pass: RAM 84,300 B, flash 479,659 B; app/factory 480,064/545,600 B | guarded physical identification only |
| E-HIL-025 | board-01 physical SD identity | pass: three read-only 400 kHz runs return stable CID `FE343253440000002000000055019CB7`, CSD and 62,534,975,488 B capacity; cold/warm init 8/2/2; resource 12→0, GPIO21 stable HIGH, cleanup complete; no mount/data block/write/radio command; Home lease 0; heap total/free/min 326,416/283,944/278,668 B | one disposable card/board; no logic/RF trace, filesystem, data-block, radio recovery, endurance, or persistence evidence |
| E-STORAGE-013 | bounded CMD17/LBA0 authorization, wire, and parser tests | pass: only high-capacity LBA0/count 1 with exact selection/read-only/Storage+RadioSpi ownership is permitted; 512-byte CRC16, truncation/corruption, MBR/GPT/FAT/exFAT hints, and partition bounds are covered | parser retains structural metadata/CRC32C only; no filesystem traversal |
| E-BUILD-023 | `0.21.0-sd-sector0-measure` | pass: RAM 86,764 B, flash 483,319 B; app/factory 483,728/549,264 B | guarded single-sector metadata read only |
| E-HIL-026 | board-01 physical SD LBA0 | pass: exactly one CMD17 reads valid MBR with partition type `0x0C`, first LBA 2,048, length 122,136,512 sectors; CRC32C 1,784,529,910 and wire CRC16 5,391; resource 12→0, cleanup complete; raw sector/mount/filesystem API/write/radio false; heap total/free/min 323,952/281,480/276,204 B | partition map only; no boot sector, FAT, directory, allocation, or file evidence |
| E-STORAGE-014 | partition-boot authorization and bounded FAT/exFAT parser tests | pass: boot LBA must equal the first partition LBA from valid LBA0; exact count 1, signature, capacity, FAT32/exFAT geometry, label sanitization, and invalid forms are covered | metadata parser only; no mount, FAT traversal, directory, or file read |
| E-BUILD-024 | `0.22.0-sd-boot-inspect-measure` | pass: RAM 90,340 B, flash 487,071 B; app/factory 487,472/553,008 B | exactly LBA0 plus its derived boot-sector metadata |
| E-HIL-027 | board-01 physical FAT32 boot sector | pass: two metadata blocks confirm FAT32, 512 B/sector, 64 sectors/cluster, 14,906 sectors/FAT, root cluster 2, and 122,136,512 total sectors; boot CRC32C/wire CRC16 3,945,425,518/9,849; resource 12→0, cleanup complete; raw sectors/mount/filesystem API/write/radio false; Home lease 0; heap total/free/min 320,376/277,904/272,628 B | one card/board; directory entries, allocation chains, files, instrumented RF silence, radio recovery, endurance, and persistence remain open |
| E-STORAGE-015 | root-directory LBA permit and metadata-only privacy tests | pass: only count 1 at the FAT32 root LBA derived from valid MBR/boot geometry is permitted; overflow/bounds/resource faults reject; fixtures containing short/LFN names emit counts/CRC32C only and no names | one-sector parser temporarily sees raw bytes in RAM, then the board buffer is zeroed; no persistence or content semantics |
| E-BUILD-025 | `0.23.0-sd-root-metadata-measure` | pass: RAM 95,620 B, flash 492,119 B; app/factory 492,528/558,064 B | one root-directory sector under `counts_hash_only` policy |
| E-HIL-028 | board-01 physical root-directory sector | pass: derived LBA 32,768; exactly three total blocks; first root sector has 16 active slots (8 LFN, 2 directory, 5 file, 1 volume label), CRC32C/wire CRC16 1,846,458,358/834; no names/end marker retained, buffer zeroed, resource 12→0, cleanup complete; mount/filesystem API/file data/write/radio false; heap total/free/min 315,096/272,516/267,208 B | one sector only; end marker absent, so inventory is incomplete at this evidence point |
| E-STORAGE-016 | bounded sequential root-cluster authorization/aggregation tests | pass: every offset must be sequential and inside sectors/cluster; aggregate CRC32C/counts stop on the first end marker, reject append-after-end, and never format names | first cluster only; FAT-chain traversal deliberately disabled |
| E-BUILD-026 | `0.24.0-sd-root-cluster-measure` | pass: RAM 95,620 B, flash 492,743 B; app/factory 493,152/558,688 B | bounded metadata-only root-cluster scan |
| E-HIL-029 | board-01 physical FAT32 root cluster | pass: two of max 64 root sectors reach end marker; 29 slots examined, 26 active/2 deleted, with 12 LFN, 6 directory, 7 file, 1 volume-label, 0 invalid; aggregate CRC32C 1,849,301,523; four total blocks, resource 12→0, cleanup complete; names/raw/file data/mount/filesystem API/write/radio false; Home lease 0; heap total/free/min 315,096/272,516/267,208 B | complete root metadata for this card state only; file/FAT chains, free space, instrumented RF silence, radio recovery, endurance, and persistence remain open |
| E-STORAGE-017 | boot-declared FAT32 FSInfo permit/parser tests | pass: only exact partition LBA + nonzero in-reserved FSInfo offset/count 1 is permitted; lead/structure/trail signatures, unknown hints, cluster bounds, CRC32C, and malformed forms are covered | FSInfo values are hints; no FAT allocation scan or VFS |
| E-BUILD-027 | `0.25.0-sd-fsinfo-measure` | pass: RAM 90,004 B, flash 493,799 B; app/factory 494,208/559,744 B | shared SD evidence workspace plus one technical FSInfo sector |
| E-HIL-030 | board-01 physical FAT32 FSInfo | pass: declared sector 1/LBA 2,049 has valid signatures and hints: 1,907,095 free of 1,907,903 data clusters, next-free 888, CRC32C/wire CRC16 1,661,032,487/49,708; exactly three blocks, buffer zeroed, resource 12→0, cleanup complete; names/file data/mount/filesystem API/write/radio false; Home lease 0; heap total/free/min 320,712/278,132/272,824 B | one card state; hints not cross-checked against FAT, no instrumented RF silence, radio recovery, endurance, or persistence evidence |
| E-DOC-003 | product-reviewed paired scope/UX/demo contracts | pass: `CAP-001…047`, `PR-001…019`, `UX-01…08`, `UX-S01…S28`, `CRV-01…06`, and `DEMO-S2…S8` match EN/RU; links/status discipline pass `check_docs.py` | PRD remains draft until the full technical baseline gate; visual baseline UX-03…07 is created in S2 |
| E-BUZZER-001 | upstream issue #117 + 0.x commit `04fd290` + clean-target static/host checks | pass: GPIO2 is active HIGH and verified fix is boot hold LOW; apps/drivers cannot call `pinMode/digitalWrite/tone/ledc` for the buzzer directly | software evidence; ADC/electrical coupling remains HW-T09 |
| E-BUILD-028 | `0.26.0-buzzer-safe-measure` | pass: RAM 90,004 B, flash 494,507 B; factory 560,448 B, SHA-256 `50d4510f…c7158f9` | measurement image; sound service intentionally absent |
| E-HIL-031 | board-01 buzzer-safe boot/runtime + TFT | pass: GPIO2 configured OUTPUT LOW before console/display; boot and 4/4 final runtime samples across 90 s report `buzzer_inactive=true`; interactive ready 393,871 µs, Home capture clean, lease 0 | pad-level software evidence without microphone/scope; physical silence needs audible observation and long endurance remains S4/S8 |
| E-STORAGE-018 | exact first-FAT-sector permit and FAT[0…2]/FSInfo cross-check parser tests | pass: only the first FAT LBA derived from valid MBR/boot geometry and count 1 is permitted; media descriptor, FAT[1] clean/error polarity, root free/data/self/reserved/bad/EOC/out-of-range, and incompatible FSInfo hints are covered | root cluster must be 2 for this bounded slice; no chain is followed |
| E-BUILD-029 | `0.27.0-sd-fat-reserved-measure` | pass: RAM 90,004 B, flash 500,007 B; app/factory 500,416/565,952 B, SHA-256 `a934e5c2…70e27524` | one additional FAT sector; parser is limited to three entries |
| E-HIL-032 | board-01 physical FAT32 reserved/root cross-check | pass: 4/4 blocks; first FAT LBA 2,956; FAT[0] media `0xF8` valid, FAT[1] clean/no-hard-error, FAT[2] root EOC; FSInfo free/next hints compatible; buffers zeroed, resource 12→0, cleanup complete; names/file data/chain/mount/write/radio false; Home lease 0, GPIO2 LOW; heap total/free/min 320,712/278,240/272,964 B | minimum three-entry check for this card state only, not a full allocation recount/VFS/persistence; no instrumented RF silence |
| E-STORAGE-019 | guarded Arduino FAT `SessionStoreIo` adapter and clean-target checks | pass: boot never mounts/writes; physical invocation requires exact CID, explicit disposable selection, new bounded run ID, 64 KiB permit, Storage+RadioSpi lease, format false, path confinement, verified directory creation, file/directory sync, and refuse-existing semantics | FatFs `f_sync` is the adapter durability boundary; host/static evidence alone is not reset or power-cut proof |
| E-BUILD-030 | `0.28.0-sd-session-store-measure` | pass: RAM 94,996 B, flash 572,655 B; app/factory 573,056/638,592 B, factory SHA-256 `d6808679…ac726ca7` | measurement image contains an explicit guarded writable HIL command, not a product auto-mount policy |
| E-HIL-033 | board-01 guarded physical FAT SessionStore | pass: exact-CID permit; new `/leshy-hil/s1-session-store-20260816-d`; generations 1/A and 2/B commit in 165,474/184,572 us with 6 file + 6 directory syncs; real unmount/remount/read-only reopen returns generation 2/3 observations; 440 logical B within 65,536 B limit; resource 12→0, cleanup complete, no format/delete/user-name/user-data read/radio TX; exact retry refuses existing scratch and writes 0 B; Home lease 0, GPIO2 LOW; heap total/free/min 315,720/272,648/237,716 B | one normal-remount card run, not reset-boundary, throughput distribution, power-cut, endurance, user-workflow, or LittleFS evidence |
| E-STORAGE-020 | guarded direct-FatFs `SessionStoreIo`, ESP-IDF SDSPI transport, timing summary, and clean-target checks | pass: caller-owned FatFs workspace exposes exact open/write/sync/close `FRESULT`; format is false; SPI2 is exclusive; 32 samples use a 4 MiB physical guard and fixed nearest-rank p50/p95/p99; stack allocation and opaque Arduino sector failures were removed | implementation/static evidence; power-cut, endurance, source-rate comparison, and LittleFS parity remain physical work |
| E-BUILD-031 | `0.29.0-sd-session-throughput-measure` | pass: RAM 99,932 B, flash 615,159 B; app/factory 615,568/681,104 B, factory SHA-256 `fe30f079…b1d649` | static RAM exceeded temporary RB-03 by 1,628 B; the review is closed by E-BUILD-033; explicit writable HIL image, not product auto-mount |
| E-HIL-034 | board-01 guarded SD SessionStore throughput | pass: ESP-IDF SDSPI at actual 4 MHz; exact CID; new `/leshy-hil/s1-throughput-20260816-n`; 32/32 commits, 96+96 barriers, min/p50/p95/p99/max 166,348/405,729/571,276/591,651/591,651 us; generation 32 and 3 observations recover before and after remount; 7,040 logical B, 2,195,456 B physical delta inside 4 MiB guard; exact retry writes 0 B; resources 12→0, Home lease 0, GPIO2 LOW; heap total/free/min 309,504/266,460/233,464 B | one card/run and SessionStore workload; this run injected no reset, while E-HIL-035 later covers software reset; no power-cut/endurance, source-rate comparison, product workflow, shared-bus cycling, or LittleFS evidence |
| E-STORAGE-021 | six-boundary `SessionStoreBoundaryIo`, exact existing-scratch read permit, guarded board arm/recovery commands, and matrix runner | pass: host tests stop after each successful payload/manifest/head write or sync boundary; write arm requires exact CID/new run ID/64 KiB guard; recovery requires exact CID/existing namespace and exposes zero-write read-only IO, software-reset reason, allowed generation, prior manifest/segment sizes+CRC32C, cleanup, and exact `FRESULT`; the host runner requires `--execute-reset-matrix`, checkpoints each completed boundary, and retries at most three times only for the exact zero-write `missing_media` readiness signature; follow-up read-only policy audit passed all six namespaces on their first attempt | implementation plus E-HIL-035 physical reset evidence; retry branch awaits a natural transient exercise; `esp_restart` is not power-cut evidence |
| E-BUILD-032 | `0.30.0-sd-session-reset-measure` | pass: RAM 99,932 B, flash 626,155 B; app/factory 626,560/692,096 B, factory SHA-256 `8b15ae09…77fa83b` | +10,996 B linked flash and zero static-RAM delta vs 0.29; guarded reset commands are diagnostic, not product recovery policy |
| E-HIL-035 | board-01 guarded six-boundary SD software-reset matrix | pass: exact CID and six new `/leshy-hil/s1-reset-20260816-r-b1…b6` namespaces; recovered generations 1/1/1/1/1/2 satisfy the boundary oracle; all reopen 3 observations and preserve segment 155 B/CRC32C 1,782,718,116 plus manifest 41 B/CRC32C 1,687,843,120; every recovery writes/syncs 0 B, returns `FR_OK`, resources 12→0, cleanup complete; postflight Home lease 0, GPIO2 LOW, heap total/free/min 309,504/266,676/233,656 B; hardened-runner read-only audit SHA-256 `7806a327…157f4` repeats all six on the first attempt | one card/board/software-reset matrix; boundary 4 originally needed one read-only retry after transient immediate `missing_media`; retry branch is host-tested but not naturally re-exercised; no physical power-cut, endurance, LittleFS, source-rate, or shared-bus evidence |
| E-BUILD-033 | `0.31.0-sd-session-ram-review` | pass: RAM 95,260 B, flash 621,479 B; app/factory 621,888/687,424 B, factory SHA-256 `2f6999cf…2774d3` | map-driven removal of one redundant 4,672 B `SurveySession`; 3,044 B static-RAM headroom below RB-03, no guardrail change |
| E-HIL-036 | board-01 shared recovery workspace + guarded boundary 6 | pass: exact 0.31 preflight heap total/free/min 314,176/271,704/266,428 B; new `/leshy-hil/s1-ram-review-20260816-a-b6` reaches `sync_head`, software-reset recovery selects required generation 2/3 observations, preserves prior hashes, writes/syncs 0 B, returns `FR_OK`, resources 12→0, cleanup complete on first attempt; postflight Home lease 0 and GPIO2 LOW; evidence SHA-256 `d42044a7…282a3` | one board/card/boundary; transient HIL minimum 238,460 B is not the RB-03 interactive-boot value; no endurance, source, LittleFS, or power-cut evidence |
| E-SURVEY-002 | explicit passive Wi-Fi board adapter, ingress rate summary, privacy scrubbing, and safety guard | pass: host tests cover bounded nearest-rank rates and Session reset scrubbing; static checks require passive scan/null filters/RAM config/NVS off and forbid active scan/connect/set-config/raw-TX/AP/promiscuous APIs outside the adapter; command requires `passive-only` and EspRf ownership | software path has zero application TX APIs, but physical no-TX cannot be verified without RF instrumentation |
| E-BUILD-034 | `0.32.0-wifi-passive-ingress-measure` | pass: RAM 113,600 B, flash 1,016,688 B; app/factory 1,017,088/1,082,624 B, factory SHA-256 `5795c798…2c868` | Wi-Fi source slice adds 18,340 B static RAM and 395,209 B linked flash vs 0.31; combined S3 diagnostic image exceeds RB-03 and is assessed under RB-04 |
| E-HIL-037 | board-01 passive Wi-Fi ingress and RB-06 comparison | pass: 32/32 passive scans over 54,419,229 us report/read 414/414 AP records, accept/reject/drop 414/0/0, encode 20,268 B; min/p50/p95/p99/max 214/370/504/546/546 B/s; heap before/after/min 244,664/244,664/186,376 B; resources 2→0, cleanup complete, Home unchanged, GPIO2 LOW, storage writes 0, identifiers emitted/retained false; evidence SHA-256 `c81da232…31422c` | RB-06 requires 2,184 B/s, current SD workload 536 B/s and therefore fails margin by ~4.1×; one environment, no instrumented RF no-TX, product queue/workflow, 8 h endurance, BLE/NRF/CC ingress, or concurrent storage evidence |
| E-STORAGE-022 | fixed `ObservationQueue`, batch policy, and rate-bound tests | pass: host tests cover capacity 64, FIFO wrap-around, drop/high-water/push/pop counters, scrubbing reset, 2,048 B/5 s/capacity/Stop/safe-shutdown policy, trigger precedence, and overflow-safe minimum batch; measured inputs produce a 1,293 B minimum | implementation contract; real source→queue→store integration remains the next slice |
| E-BUILD-035 | `0.33.0-sd-session-batch-throughput-measure` | pass: RAM 114,200 B, flash 1,018,192 B; app/factory 1,018,592/1,084,128 B, factory SHA-256 `27fbd7e1…3739e1` | +600 B static RAM and +1,504 B linked flash vs the combined 0.32 image; assessed under RB-04 |
| E-HIL-038 | board-01 guarded batched SessionStore throughput | pass: exact CID/new `/leshy-hil/s1-batch-throughput-20260816-a`; 32/32 commits of 64 observations/4,609 B, 96+96 barriers; min/p50/p95/p99/max 201,234/518,527/652,362/664,421/664,421 us; generation 32/64 observations recover before and after remount; encoded payload 9,068 B/s vs required 2,184 B/s, target passes by 4.15x; 149,568 logical B; `FR_OK`, resources 12→0, cleanup complete, GPIO2 LOW, fixture restored; evidence SHA-256 `372d2d34…135f4` | synthetic fixed batch proves the storage service rate but not concurrent/real Wi-Fi queue, product workflow, power-cut, LittleFS, or endurance evidence |
| E-SURVEY-003 | guarded passive Wi-Fi→FIFO→SessionStore integration path | pass: the exact-CID command acquires a combined EspRf+Storage+RadioSpi lease, the passive scanner writes normalized observations only to a fixed FIFO, policy selects size/latency/capacity/Stop boundary, and a stopped snapshot commits atomically and reopens after remount; output exposes counts/rates only while identifiers remain in isolated scratch | diagnostic command, not product UI; physical no-TX is not instrumented |
| E-BUILD-036 | `0.34.0-wifi-passive-persist-measure` | pass: RAM 119,656 B, flash 1,027,804 B; app/factory 1,028,208/1,093,744 B, factory SHA-256 `308a9869…7c3818` | real fixed ring adds 4,672 B plus evidence buffer/code; combined S3 image is assessed under RB-04 |
| E-HIL-039 | board-01 real passive Wi-Fi→persistent SessionStore | pass: exact CID/new `/leshy-hil/s3-wifi-persist-20260816-a`; 4 scans read/accept/reject/drop 29/29/0/0; FIFO high-water 9/64, push/pop/drop 29/29/0; latency trigger; generation 1 with 29 observations/1,334 B commits in 192,729 us and reopens before/after remount; encoded payload 6,921 B/s vs required 2,184 B/s, pass by 3.17x; `FR_OK`, resources 14→0, cleanup complete, Home lease 0, GPIO2 LOW; evidence SHA-256 `1dcb2e44…6cd77f` | first real-source persistent technical path; product Start/Stop/Library/reboot/export, instrumented no-TX, power-cut, LittleFS, and endurance remain open |
| E-LIBRARY-002 | persistent Session admission contracts | pass: runtime capability `library.persistent_session` takes precedence over the simulated fixture and enables ordinary Library with a Storage lease; state/export provenance comes from the active entry instead of hardcoded RAM flags | boot-time media discovery/catalog is not implemented; the entry holds a caller-owned RAM copy of the already validated persistent Session |
| E-BUILD-037 | `0.35.0-persistent-library-admission-measure` | pass: RAM 120,264 B, flash 1,029,116 B; app/factory 1,029,520/1,095,056 B, factory SHA-256 `eb7a69a8…a967f9` | +608 B static RAM and +1,312 B linked flash vs 0.34; diagnostic admission follows an explicit HIL command, not boot policy |
| E-HIL-040 | board-01 current-boot persistent Library and export | pass: exact CID/new `/leshy-hil/s3-wifi-library-20260816-a`; 4 scans read/accept/drop 52/52/0, FIFO high-water 18/64, size trigger; generation 1/52 observations/2,499 B commits in 192,867 us and reopens after real remount; 12,957 B/s vs 2,184 B/s, pass by 5.93x; `fixture_restored=false`, persistent admission true; actual TFT Home→List→Detail→Export shows READY/PERSISTENT REAL/generation 1 valid/PERSISTED YES; serial export is `persistent=true`, `simulated=false`, Wi-Fi 52; Back releases lease 5→0, postflight heap total/free/min 281,496/237,420/147,692 B, GPIO2 LOW; run SHA-256 `cecbc574…f7f53b`, export `2e9c371f…655a3` | current-boot admission after an explicit diagnostic path; reboot starts from simulated Library until safe boot mount/catalog/recovery exists; product Start/Stop, instrumented no-TX, power-cut, LittleFS, and endurance remain open |
| E-AUTO-001 | ADR-005 pre-release runner/suite/bundle-verifier host tests | pass: manifest/action/assertion/mask bounds, missing-only golden bootstrap, overwrite refusal, exact/masked pixel mismatch, artifact/candidate tamper, and unsigned-default rejection are covered; full `tools/test.sh` passes | queue/quarantine, camera/power, and a live GitHub HIL run remain open |
| E-HIL-041 | board-01 automatic `device-smoke` | pass: exact app candidate SHA-256 `e95d7ede…04441b` flashed and verified twice; second run reaches ready in 501.72 ms, Home/Back exact and Diagnostics masked-exact have zero mismatched pixels; acknowledgements 84.204/95.963 ms, final owner none/lease 0, heap total/free/min 281,496/238,832/233,436 B, GPIO2 LOW; runner pass/gate-eligible; `run.json` SHA-256 `16136f08…780f17`, artifact index `9240caee…4ae75` | development bundle is local: verifier passes only with the explicit dev flag and default release check fails; exact release build identity, a GitHub attestation run, EN/RU matrix, power-cycle/camera, and CI publish gate remain open |
| E-BUILD-038 | `0.36.0-prerelease-build-identity-measure` | pass: RAM 120,328 B, flash 1,029,312 B; app/factory 1,029,712/1,095,248 B, app SHA-256 `47bd62ad…66cecd5`, factory `9aec9999…55da75` | +64 B static RAM and +196 B linked flash vs 0.35; bounded boot evidence adds full app ELF SHA-256 `2e5dfcc2…274e6` |
| E-AUTO-002 | ESP app identity parser, runner/verifier binding, and negative host tests | pass: parser validates image/app-descriptor magic and reads the full 32-byte ELF digest; malformed image and missing or mismatched firmware/candidate/run/manifest/local-result identity fail closed; full `tools/test.sh` passes | the test-session envelope was later closed by E-AUTO-004; live GitHub provenance remains E-AUTO-005 |
| E-HIL-042 | board-01 build-identity `device-smoke` | pass: exact app SHA-256 `47bd62ad…66cecd5` flashed with verify; candidate descriptor, cold boot, and repeated metrics agree on ELF SHA-256 `2e5dfcc2…274e6`; ready 505.962 ms, Actions 85.338/94.918 ms, all three visual comparisons have 0 mismatched pixels, final owner none/lease 0, heap total/free/min 281,432/238,768/233,372 B, GPIO2 LOW; `run.json` `d011e052…60dbf8`, artifact index `c021993e…4f318` | two preceding failed bundles retain fail-closed truncated-digest and bounded-envelope diagnostics; the successful result remains local development evidence, so GitHub provenance/promotion/camera remain open |
| E-AUTO-003 | historical canonical Ed25519 station-attestation prototype | experiment pass: an ephemeral-key host test signed a candidate/bundle copy and detected post-sign tampering | superseded 2026-08-17: persistent station key rejected and production code path removed; not release evidence |
| E-AUTO-004 | HIL session v2 and self-contained candidate host contracts | pass: a 128-bit lower-hex ID and full app identity are mandatory; nested begin, wrong end, stale/mixed session, and a rehashed mixed bundle are rejected; runner copies and verifies the candidate, flashes that copy, and indexes it inside the bundle; verifier needs no external candidate path | runner-crash quarantine/power relay and remote immutable artifact download remain station work |
| E-AUTO-005 | GitHub-native build-once/HIL/promotion trust workflow | implementation pass: deterministic evidence packaging is host-tested; `.github/workflows/prerelease-hil.yml` GitHub-attests exact candidate/factory/ELF/map files through OIDC, verifies provenance before flash, attests the evidence archive, and re-verifies every artifact/same bytes in promotion; `tools/release_1x.py check` performs clean-main/version/port preflight, dispatch, pinned-SHA runner bootstrap, a unique per-run label, one-job `--ephemeral` lifecycle, and cleanup without a macOS service; `publish` accepts only a successful stable 1.x run, rechecks attestations/inner bundle/current HEAD, and creates the Release without rebuilding; host negative tests pass | the live workflow has not run; the `hil-production` deployment-branch rule, first GitHub HIL/provenance proof, and queue/quarantine remain open |
| E-BUILD-039 | `0.37.0-prerelease-test-session-measure` | pass: RAM 120,368 B, flash 1,030,684 B; app/factory 1,031,088/1,096,624 B, app SHA-256 `25f1bacb…cd83c6`, factory `6fc9a66c…c41eca` | +40 B static RAM and +1,372 B linked flash vs 0.36; session state owns no hardware/resource lease and resets on reboot |
| E-HIL-043 | board-01 session-bound self-contained `device-smoke` | pass: bundled exact app SHA-256 `25f1bacb…cd83c6` flashed with verify; ELF SHA-256 `0c5277bb…ef7ed8`; run ID `803dd8cfbd28657240fd64af50019588` agrees across manifest/begin/end/run/legacy attestation, UI revision 0→2 and session active true→false; ready 502.245 ms, Actions 84.116/95.379 ms, all three visual mismatches 0, final owner none/lease 0, heap total/free/min 281,392/238,728/233,332 B, GPIO2 LOW; self-contained verifier passes; `run.json` `8466fe45…d76948`, index `2f3cb367…4be3e7` | retained run is local and predates GitHub-native E-AUTO-005; camera/power and the first CI promotion proof remain open |

## Known uncertainties and risks

- Board-01 provides partial evidence for `HW-T01/T04/T07/T11`; other physical tests
  have not run, and no composite HW-T test is fully closed yet.
- BOM says ESP32-S3-WROOM-1U-N16 (16 MB, no PSRAM), while the original build guide
  says OPI PSRAM; `HW-U01` remains physically open but is constrained to N16/no-PSRAM.
- Schematic TFT RESET and legacy `TFT_RST=0` conflict; GPIO0 is forbidden as display
  reset until `HW-T02`.
- Runtime/navigation prototypes in the worktree are integrated into 0.x; they do not
  satisfy S2 and must not dictate the clean target automatically.
- Probe-UI flash/RAM/heap figures are a 1.x platform lower bound, not an S3 Survey or
  final-release budget.
- The PRD remains `draft 0.2 after product review`; no P0 is accepted or verified
  until the full technical baseline gate.
- One board is available, but `HW-T01` requires a second v2 unit; continuity,
  logic/RF, storage, and power evidence is still missing.
- No microphone/scope evidence exists for the buzzer: exact boot/runtime pad state is
  proven, while absence of audible hum remains an operator observation and HW-T09.

## Blockers

S1 as a whole is not blocked. Full HIL needs a second board, multimeter, logic/RF
detector, and power measurement; unavailable instruments limit evidence but do not
stop budget, risk-register, or ADR work.
