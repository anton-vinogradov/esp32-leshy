# ESP32-Leshy 1.x target architecture

*Read in: **English** · [Русский](ARCHITECTURE.ru.md)*

Document status: draft architecture for the clean 1.x line. Firmware 0.x is frozen as a
separate PoC and a source of validated hardware knowledge. Version 1.x does not
depend on its `main.cpp`, menu tree, or global state. A low-level fragment may be
reused only after it is isolated behind a 1.x contract and tested independently.

Binding choices that refine this draft live in the
[accepted ADR index](adr/README.md). In a conflict, an accepted ADR takes precedence
over this general architecture text.

## Why change

At the audit baseline, `main.cpp` has 3,181 lines and owns navigation, global screen
state, rendering, driver lifecycle, radio coexistence, and serial QA. Lifecycle logic
is repeated across `launch()`, `back()`, serial commands, and the main `loop()`.

That makes features expensive and teardown unsafe. Physical pin conflicts are known
to individual drivers, not to the system, and most behavior is testable only on the
device. Existing non-blocking scans, OTA/rollback, and driver code remain useful as
evidence and implementation references. They are not linked into 1.x until they
satisfy a new driver contract and its tests.

## Layers

```text
apps/       Survey · Targets · Wi-Fi · BLE · Sub-GHz · IR · NFC · GPS · Lab
sdk/        Application · events · views · capture API · safety API
services/   observations · sessions · library · settings · OTA · diagnostics
kernel/     AppRuntime · Navigator · ResourceBroker · scheduler · event bus
drivers/    Wi-Fi/BLE · NRF24 · CC1101 · PN532 · GPS · IR · SD · display/input
boards/     pin map · electrical conflicts · build flags · capability probes
platform/   Arduino-ESP32 / FreeRTOS adapters
```

Dependencies point down. Drivers never open screens, apps never manipulate another
app's driver or global state, and services do not know about the TFT.

## Board profile and capabilities

The normative design-time source is
[`HARDWARE_ENVELOPE.md`](HARDWARE_ENVELOPE.md): evidence, the physical pin map,
assembly variants, safe probing, and unresolved facts. `BoardProfile.h` is a
versioned implementation of its accepted subset, not an independent source of facts.

`HardwareInventory` records `declared`, `detected`, `available`, `conflicted`,
`fault`, or `unknown` plus evidence and reason. It distinguishes the main board, the
detachable RF shield, removable media, and explicit external GPS/PN532 assemblies.
The app registry consumes only the compatible `available` projection.

Important v2 conflicts are explicit:

- TFT and touch share physical SPI GPIO 35/36/37 and require serialized transactions;
- NRF24, CC1101, and SD share radio SPI 12/13/11; PN532 reverses the data direction on 11/13;
- CC1101/PN532 and GPS overlap GPIO 5/6, so ambiguous auto-probing is forbidden;
- NRF24 slot 3 and IR overlap GPIO 21/14;
- GPIO2 couples the buzzer actuator and battery divider;
- the schematic connects TFT reset to RESET/EN while legacy flags use BOOT GPIO0;
- BOM module N16 has no PSRAM, while display GPIO35–37 conflict with Octal-PSRAM variants.

Detected hardware drives the app registry and menu. An unavailable app explains the
missing module in Diagnostics instead of failing after its screen opens.

The first broker domains are `spi_display`, `spi_radio`, `mux_5_6`,
`mux_nrf3_ir`, `gpio2_battery_buzzer`, `i2c_control`, `storage`, and `esp_rf`.
Radio SPI begins with exclusive operation leases; transaction-level sharing requires
HIL and endurance evidence. GPS/PN532 require explicit assembly profiles.

## Application runtime

Every app declares a stable ID, capabilities, exclusive resource domains, and one of
`Passive`, `Connected`, `Transmit`, or `Disruptive`. It implements `onStart`,
`onEvent`, `onTick`, and `onStop`.

`AppRuntime` validates capabilities, atomically acquires leases, and always releases
them after stop or failed start. `Navigator` owns the fixed-size screen stack and each
level's selection. Back becomes a system event instead of a branch repeated by screens.

Physical buttons, touch, and local diagnostic control produce the same normalized
Actions and enter that Navigator path. The diagnostic client reads actual TFT GRAM
and records state/revision evidence; it never owns a second navigation model. The
binding transport and acceptance rules are in
[`UI_AUTOMATION.md`](UI_AUTOMATION.md).

## Concurrency and memory

- Core 1 owns UI/navigation; callbacks should not block for more than 10 ms.
- Core 0 runs bounded radio/storage workers that publish immutable snapshots or events.
- ISRs only enqueue timestamped edges into preallocated queues.
- Long work has cancellation and progress; all queues are bounded and count drops.
- Steady state avoids repeated heap allocation; large buffers belong to reusable services.
- No mandatory path relies on PSRAM until `HW-U01` is resolved. Boot diagnostics
  records actual flash, partition table, package/revision, and PSRAM presence.

Source ingress never waits on filesystem durability barriers. Each receiver publishes
normalized Observations into a fixed-capacity ring owned by the Survey service; the
storage worker drains a bounded batch into the current segment and publishes a new
atomic head only on explicit stop, size/time threshold, or safe-shutdown request.
Queue depth, high-water mark, and drops are Session evidence. E-HIL-037 measures
passive Wi-Fi p99 at 546 encoded B/s and therefore sets the first RB-06 storage target
at 2,184 B/s. E-HIL-038's fixed batch delivers 9,068 B/s and E-HIL-039's real
Wi-Fi→FIFO→SessionStore path delivers 6,921 B/s with high-water 9/64 and zero drops.
E-HIL-040 repeats that path through ordinary Library/export at 12,957 B/s,
high-water 18/64, zero drops, recovered generation 1/52 observations, and
persistent/real provenance in List/Detail/Export. That result was a sequential
diagnostic command. Version 0.59 closes the product-worker integration gap: one
persistent Core-0 task owns source and storage work behind bounded event/observation
queues (8/64), while Core 1 owns and drains the `SurveyPipeline`. Start and Stop UI
callbacks only enqueue intent and return; the measured callbacks take 13/10 us.
The source remains active through List and Detail, and E-HIL-084 observes progress
from 14 observations/one scan to 27/two scans while Detail is open, with queue
high-water 10/64 and zero drops. Durability work starts only after the source has
stopped; boot-time catalog recovery remains a separate read-only path.

Self-review then found one terminal-state race: the worker exposed `Idle` immediately
after enqueueing Failed/Cancelled/Stopped, before Core 1 had consumed that terminal
event. Version 0.60 makes the UI the sole terminal acknowledger. The worker keeps its
non-idle control state until Core 1 completes cancellation cleanup or commit cleanup;
only then may a later Start be admitted. A static contract rejects worker-side `Idle`
transitions, and E-HIL-085 repeats the exact physical normal path through generation
67→68 with 25/25 forwarded, zero drops, read-only reboot/export, and final lease zero.
Version 0.62 makes the worker's blocking-scan interval observable and snapshots that
state when Back requests cancellation. E-HIL-086 waits for a real active passive scan,
then proves that the request reaches `cancelling`, closes source/backend, publishes no
generation, and cold-reopens the unchanged 68/25 Library with zero writes and leases.
The preceding 0.61 run is retained as failed because its second cold boot lost the
single PCF8574 read; boot now performs at most eight reads with 5 ms spacing and emits
attempt/retry accounting. Deliberate first-read injection is still additional evidence.

Product activation is a separate fail-closed boundary. `ProductStorePolicy` fixes
the only current product root at `/leshy/sessions/v1`: automatic catalog recovery
requires an already enrolled exact media fingerprint, an existing root, a guaranteed
read-only non-writable driver, and Storage+RadioSpi ownership. Initialization and
commit additionally require an explicit user selection, writable driver, and bounded
size/reserve. `ProductSurveyAdmission` then requires explicit Start, a validated
passive plan, a writable commit permit, and combined EspRf+Storage+RadioSpi ownership.
It never silently replaces a requested real/persistent Session with simulated/RAM.
The 0.44 board lifecycle persists only the exact 32-character CID in NVS, identifies
the card under lease 12, mounts FAT with formatting disabled, replaces diskio write
and trim callbacks with `RES_WRPRT`, opens only the fixed product root, stages the
latest valid generation into Library, then unmounts and releases all resources.
Recovery deliberately validates raw card capacity and does not call `f_getfree` or
filesystem-capacity queries: boot does not need free space, and scanning a large FAT
would make latency depend on media size. Enrollment is saved only after the same
read-only recovery succeeds; unenrollment removes only the NVS CID and never accesses
the SD. Initialization/commit remain explicit writable operations.

Version 0.45 first connected that admission to the interactive product Survey without
changing the un-enrolled simulated fixture. AppCatalog prefers
`survey.persistent_passive` only
after exact-media boot recovery and atomically requests UI+EspRf+Storage+RadioSpi
(lease 15). Explicit Start re-identifies the CID, mounts writable with formatting
disabled, uses only the cached FAT/FSInfo free-cluster hint, authorizes a 64 KiB commit
with a 1 MiB reserve, and routes the allocation-free workflow to the product store.
Version 0.59 replaces the original one-shot UI-loop scan with the persistent bounded
worker above. The credential-free Wi-Fi adapter performs passive scans only, supports
stopping an active scan, and never calls connect/configuration/raw-TX APIs. Stop first
requests worker/source shutdown and then publishes and reopens exactly the next
generation before replacing Library; every exit closes the store/mount and routes the
workflow back to RAM. Back from Running cancels without a commit and preserves the
prior Library. The normal Start→live List/Detail→Stop→commit→read-only reboot/export
path and final zero-lease cleanup are physically accepted in E-HIL-084. Version 0.60
additionally holds worker control ownership until UI terminal acknowledgement,
preventing a new Start from overtaking an older terminal event; E-HIL-085 confirms the
unchanged normal hardware path. E-HIL-086 now closes physical cancellation during an
active scan without commit or leak. Version 0.68 adds a one-shot release-test fault at
the real source boundary. E-HIL-092 proves that an unavailable passive source is shown
as a localized terminal TFT state only after cleanup and lease release: source start
and store open are both false, zero bytes and observations are created, Select cannot
silently retry, Back returns Home, and cold read-only recovery preserves generation
68 with 25 observations. At that evidence point physical power-cut, endurance,
LittleFS parity, and independent demo goldens remained open; the normal/remount
LittleFS slice is accepted by 0.69 below.

Version 0.69 adds a HIL-only LittleFS backend without changing the product partition
map. It accepts only inactive OTA1 `app1` at `0x410000`/4 MiB, proves the running and
boot applications are elsewhere and product `spiffs` is disjoint, then requires an
exact host-provided full-partition SHA-256 before format. The common `SessionStore`
uses a confined POSIX adapter under `/hil-lfs/leshy-hil/<run-id>`; file `fsync` is the
LittleFS metadata/directory durability barrier. E-HIL-093 proves 32 commits,
read-only remount recovery and throughput, while the host proves two-read backup,
exact OTA1/table restore and unchanged product Library. Version 0.70/E-HIL-094 then
closes all six LittleFS software-reset boundaries with typed read-only recovery and
one-write exact restore. `E-HIL-095`/`E-GATE-003` closes S3 on the same exact 0.70
candidate: generation 69→70, 29/29 observations, cold reopen/export and five
independent TFT matches. S4 is now active; physical power-cut and multi-source
endurance remain its explicit gates.

The first S4 user-facing slice is exact `0.71.0-survey-source-plan`
(`E-HIL-096`/`E-SURVEY-009`). An allocation-free `SurveySourceController` projects
boot inventory into a draft UX-S02 plan separately from driver execution: only
`available` sources can be selected, empty real plans cannot Start, and declared BLE
remains visible with an unavailable reason. Plan/Sources navigation uses the common
Actions and incremental renderer; leaving Setup releases the foreground lease. This
is the stable UI/domain seam for the next shared timeline and passive BLE work, not a
claim that the BLE driver or `DEMO-S4` is complete.

The exact `0.72.0-source-timeline-runtime` checkpoint adds the first shared radio
time model and connects it to the selected plan and real product worker.
`SourceTimeline` owns two fixed source slots and streams completed scheduled, active,
unavailable, and fault windows through a 16-entry FIFO. It retains per-source
64-bit accepted/drop counters and accumulated durations, reports duty cycle in
permille, rejects out-of-order transitions and invalid state/reason pairs, and leaves
the current state unchanged when the FIFO is full while incrementing an overflow
counter. Host contracts cover overlapping Wi-Fi/BLE windows, temporary BLE driver
unavailability, observation drops, terminal accounting, FIFO drain/retry, and
overflow-safe stop. Worker ScanStarted/Scan/terminal events now drive Wi-Fi windows,
every accepted or dropped observation updates the same monotonic ledger, and Running
UI shows the current Wi-Fi state and duty share. Exact `E-HIL-097` verifies two real
scan cycles, 34/34 accepted/forwarded observations, 4→5 completed windows, zero
drops/overflow, terminal close, generation 71→72, exact-CID cold recovery and final
lease 0. This accepts runtime integration and visibility only: schema-v1 persistence
still stores observations without timeline windows, so the FIFO is not yet drained
durably and a full queue remains an intentional fail-closed short-run bound.

Exact `0.73.0-source-timeline-persistence` closes that persistence boundary without
breaking existing sessions. SessionCodec schema v2 appends a CRC-bound timeline
record while schema v1 remains byte-for-byte readable. The product worker drains each
completed runtime window immediately into a bounded 16-window `SurveySession` ring,
with explicit total/evicted counts and per-source summaries; an incomplete or invalid
timeline prevents commit. Stop finalizes the timeline before generation 73→74 is
published. Cold Library reopen exports `leshy.session.summary.v2` and the retained
ordered `timeline_windows`, including source/state/reason, exact monotonic bounds and
accepted/drop counts. Exact `E-HIL-098` proves 21/21 observations, five windows,
zero FIFO backlog/overflow/drops, cold reopen and final lease 0. Schema-v2 controlled
power-cut and long multi-source endurance remain separate `DEMO-S4` gates.

Exact `0.74.0-passive-ble` adds the second real source without weakening those
boundaries. A bounded Arduino BLE scan streams each advertisement directly into the
common Observation pipeline and removes it from the library map immediately, so RF
density cannot grow an unbounded retained-device table. Wi-Fi and BLE scans remain
serialized by the product worker; a binary start gate makes the worker publish and
the UI task accept each timeline `ScanStarted` boundary before the driver can emit an
observation, preserving cross-queue monotonic ordering. SessionCodec v2 accepts BLE
observations with zero channel/frequency while retaining exact schema-v1 decode, and
the Library summary exports explicit per-source counts. Exact `E-HIL-099` proves one
real Wi-Fi plus one real BLE cycle, 6+34 observations, generation 76→77, six ordered
persisted/exported windows, zero drops/overflow, exact-CID cold recovery and final
lease 0. Injected unavailable/fault recovery remains the next S4 slice.

## Data model

Raw observation is separate from interpretation:

```text
Observation { session, time, location?, radio, frequency, RSSI, identity?, payload ref, annotations[] }
Target      { local id, identities[], first/last seen, tags, notes }
Capture     { immutable source blob, metadata, derived decodes[] }
Session     { device/build/calibration, start/end, track, observations[] }
```

Versioned CBOR metadata and immutable payloads live under `/leshy` on SD, with
LittleFS fallback. PCAP, CSV, JSON, and radio-specific formats are import/export
formats, not the internal source of truth.

## Safety and release integrity

TX apps require a Lab context with visible frequency, power, timeout, indication, and
immediate stop. A shared regulatory policy blocks disallowed bands. Firmware and its
manifest should be signed; SHA-256 verifies integrity but not origin. File and network
parsers are host-fuzzed, and credentials never enter session exports.

## 1.x implementation sequence

1. Freeze the board capability/conflict map and reference workflows.
2. Create an independent 1.x build target with the board profile, runtime, broker,
   and Navigator; treat the existing contract prototype as an experiment, not an
   extension of 0.x.
3. Bring up display, input, storage, and HardwareProbe without the legacy menu.
4. Build the first end-to-end Survey Session slice: one passive source → Observation
   → List/Detail → persisted Session → reopen.
5. Add receivers through new driver contracts and recorded traces; port only
   validated hardware operations, not 0.x screens or global state.
6. Grow Survey into cross-radio operation, then implement Targets and a reboot-backed Library catalog.

All new 1.x code must sit behind 1.x contracts, build independently from 0.x, and
have host/HIL verification. The 0.x archive is not changed to make new development
easier.
