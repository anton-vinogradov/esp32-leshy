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
kernel/     SafetySupervisor · AppRuntime · Navigator · ResourceBroker · scheduler
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

The touch adapter loads a versioned calibration from NVS and can import the legacy
0.x `leshy/tcal` record without rewriting it. Its allocation-free frontend is
edge-triggered with a 35 ms release debounce. A shared geometry mapper accepts only
visible Home/choice rectangles and converts a hit into bounded selection movement
plus `Select`; header/footer never dispatch, and touch cannot synthesize Back.

### Safety supervisor

`SafetySupervisor` is a kernel boundary below apps, UI, drivers, and product
recovery. A panic-enabled Task WDT monitors every completed main-loop turn. Its IRAM
handler can only lower the known buzzer/nRF CE pads and publish an exact-app,
torn-write-resistant RTC record; it never logs, allocates, waits, or touches SPI.
The watchdog reset enters a latched Safe Mode that skips product workers and normal
Actions. A second reset preserves an already confirmed latch. Only an explicit
two-step user clear removes it and restarts. Worker heartbeats and physical rail/
radio shutdown remain separate open work. The binding contract is
[`SAFETY_SUPERVISOR.md`](SAFETY_SUPERVISOR.md).

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
lease 0. The following exact slice accepts injected unavailable/fault recovery.

Exact `0.75.0-runtime-degradation` closes that slice with a pure decision boundary
between driver results and product state. An unavailable or faulted source is removed
from the active mask and gets an explicit timeline state/reason; the Session continues
only while another compatible selected source remains. Later successful scans cannot
erase `running_degraded`. A diagnostic one-shot can substitute the next driver result
only while Home/idle and reports that it touched neither hardware nor storage. Exact
`E-HIL-100` injects BLE unavailability, then proves two real Wi-Fi cycles still reach
28 observations, persists eight windows including 3,625,744 us of BLE
`driver_unavailable`, cold-reopens/exports it with zero fault time, zero drops and
final lease 0.

Exact `0.76.0-observation-browser` adds a common allocation-free Survey browser over
the retained Observation records. All/Wi-Fi/BLE filters map visible rows back to the
same bounded session without copying records; List opens radio-neutral Detail and a
12-sample RSSI history. Moving focus to browsing requests a worker-owned snapshot:
the active RF source is stopped, the timeline is finalized, and the storage backend
remains owned until Save or Cancel. This prevents user dwell time from overflowing
the 64-observation Session while keeping the browser read-only. `E-HIL-101` proves one
complete real Wi-Fi+BLE cycle, 8+37 observations, exact filter counts, RF-off pause,
generation 80→81 commit, cold reopen/export, nine TFT captures, zero drops/overflow
and final lease 0.

Exact `0.77.0-capture-export` advances the atomic Session format to schema v3 while
keeping byte-compatible v1 and readable v2. A fixed CRC-covered Capture record is
written before observation and timeline records. It binds the producing app ELF,
selected source mask and exact passive Wi-Fi/BLE receive plans; location and raw-frame
payload absence are represented explicitly instead of inferred. Library exposes this
immutable provenance, retains the v2 JSON summary contract and streams canonical CRLF
CSV one bounded row at a time. Identity and label bytes are lower-case hex so export is
deterministic and binary-safe without a second Session-sized allocation. The current
scan drivers retain normalized observations, not raw 802.11/BLE frames, so PCAP returns
the typed `unavailable_no_frame_payload` result rather than fabricating packets.
`E-HIL-102` proves generation 81→82, 16+31 observations, exact metadata, a 47-row CSV,
cold recovery, ten TFT captures, invariant heap, zero drops/overflow and final lease 0.

Exact `0.78.0-wifi-frame-capture` adds the separate packet path instead of changing
the Observation model. `WifiFrameCapture` owns a fixed 16-frame store with a 256-byte
snap bound; the Arduino adapter enters STA promiscuous receive without NVS persistence,
application connect or raw TX and hops the explicit 2.4 GHz channel plan. Stop first
detaches the driver and releases Radio, then freezes the bounded frames for a streaming
PCAP 2.4 writer. Each record contains a 15-byte radiotap header with flags, channel and
RSSI followed by the captured 802.11 bytes; the writer allocates no second payload
buffer. Capture is volatile by default, performs no storage write, and Back zeroes the
store before releasing UI. `E-HIL-103` proves 34 reported/16 retained real frames,
4,096 B payload, 18 counted capacity drops, a parsed 16-record/4,616 B PCAP, five TFT
states, read-only prior Session, scrubbed RAM and final lease 0.

Exact `0.79.0-persistent-frame-capture` extends the same bounded source through one
atomic storage path. Session schema v4 adds a CRC-covered fixed `LWFC` frame block and
v2 Capture metadata while preserving decoding of v1–v3. Save is a separate user action
and requires an explicit raw-identity privacy confirmation. A background worker checks
the exact enrolled CID, acquires Storage+RadioSpi only for the commit, publishes one
new generation, reopens it fail closed, and returns ownership before UI acknowledges
success. `PersistedWifiFrameCaptureView` reads the existing 12 KiB SessionStore
workspace directly, so Library PCAP creates no second frame-payload buffer. Back
scrubs volatile capture RAM but does not delete an explicitly saved artifact.
`E-HIL-104` proves generation 82→83, 16 records/2,253 payload bytes, live/cold
2,773-byte PCAP equality, read-only recovery, invariant heap, nine TFT states and final
lease 0.

Exact `0.80.0-self-test-coverage` makes capability registration an explicit
architecture boundary rather than inferring health from menu availability. Boot
inventory facts are projected into plan-v3 `SelfTestFacts`; one deterministic engine
emits ordered checks for completed S3/S4 readiness and persistence, while optional
assembly declarations map to `not_applicable` and unfinished receiver contracts map
to `blocked`. The same report drives the TFT and independent HIL oracle, records zero
side effects, and keeps only the UI lease. `E-HIL-105` proves 15 pass/0 fail/2 blocked/
3 N/A and final lease 0.

Exact `0.81.0-shield-receiver-probe` adds a narrow hardware adapter below that pure
plan engine. It is called only from user-confirmed Full/Guided while the foreground
owner holds `RadioSpi`; boot and Quick never call it. The adapter keeps nRF CE LOW,
reads only four identity/config registers on slots 1/2, never selects slot 3/GPIO21,
and reads only CC1101 PARTNUM/VERSION status registers. The pure contract rejects
floating/partial identities, profile/resource conflicts, any CE-high/strobe/TX event
or incomplete cleanup. `E-HIL-106` binds the exact 8 nRF reads, 2 CC reads, 20 SPI
bytes, three detected receivers and final lease 0. This is an identity boundary, not
a passive observation pipeline or physical RF-silence measurement. Those workflows,
active Full/Guided execution, controlled physical power-cut and the ≥45-minute/
≥8-cycle endurance gate inside its one-hour operational budget
remain `DEMO-S4` work.

Exact `0.82.0-nrf24-spectrum` builds the first useful shield workflow above that
identity boundary without coupling UI rendering to SPI. A pure
`Nrf24SpectrumController` owns the 83-bin plan and pause/resume/stop state; the
Arduino adapter alone owns the dual-receiver register sequence, 200 us dwell and
safe cleanup. `SurveySourceController` only maps typed Actions and projects a
volatile snapshot into the localized live chart, whose updates are confined to the
chart region. `E-HIL-107` proves 21 complete 2,402…2,484 MHz sweeps, a stable paused
counter, exact receive-window accounting, zero TX/CC/storage side effects, invariant
heap/storage and final lease 0. RPD bins represent threshold activity, not calibrated
power; physical RF silence remains unmeasured.

Exact `0.83.0-cc1101-spectrum` applies the same separation to Sub-GHz RSSI without
copying the nRF wire model. Pure `Cc1101SpectrumController` owns four 64-bin band
plans and interaction state. `BoardCc1101PassiveSpectrum` performs only one bounded
sample per main-loop turn, whitelists reset/RX/idle strobes, waits at most 3,000 us
for RX ready, observes for 500 us and returns to IDLE; it exposes no TX, PATABLE or
FIFO operation. UI redraw occurs only after a completed sweep. `E-HIL-108` proves all
four bands, a stable 400 ms pause, exact wire accounting, zero TX/storage side
effects, invariant heap/storage and final lease 0. Values are uncalibrated RSSI and
physical RF silence remains unmeasured.

The accepted `0.99.0-wifi-spectrum-modes` display contract makes measurement
completion, not a wall-clock UI timer, the waterfall row clock. The active pure
controller exposes a monotonically increasing completed-sweep counter; the Arduino
layer consumes each new value once and stores the current complete spectrum as one
physical row in a fixed 240×224 eight-bit raster. A counter jump greater than one is
retained as a skipped-measurement failure, so the renderer cannot silently duplicate
a stale/partial snapshot to satisfy a visual speed target. The raster is the screen
resolution, not the receiver resolution: the 83 nRF bins and 64 CC bins map to
adjacent columns without interpolating invented measurements. Receiver capability
therefore determines the time axis. All detected nRF slots are selected by default;
the header reports the active receive set, while Signal and Traffic remain distinct
display metrics. Only the newest graph row is updated after initial chrome render.
`E-HIL-124` binds the source/candidate, six zero-skip full-history paths, 17 TFT
states, unchanged storage and final lease 0. This is still software receive-only
evidence, not calibrated RF or instrumented physical-silence evidence.

The accepted `0.100.0-spectrum-source-history` refinement separates physical
display resolution from retained receiver resolution without changing that timing
contract. Each of the 224 history rows now owns 83 bytes, the maximum real source
width, rather than 240 already-expanded display bytes. nRF stores all 83 bins and
CC stores its 64 bins plus a cleared tail; `intensity(row, column)` selects the
nearest real source bin only while the 240-pixel scanline is rendered. There is no
horizontal interpolation, averaging or extra measurement, and the physical result
remains one completed sweep per one-pixel row. This reduces the fixed history from
53,760 to 18,592 bytes and static RAM from 205,296 to 170,128 bytes. `E-HIL-125`
binds six zero-skip paths, maximum 611 us row rendering, all three nRF slots, zero
CC retries/recoveries, stabilized heap 211,580/146,472/127,120 B, unchanged storage
and final lease 0.

Exact `0.84.0-full-guided-rf` makes those two receiver contracts executable from
plan-v5 Full/Guided without making boot or Quick active. The orchestration shows a
500 ms cancellable boundary, acquires `RadioSpi` once, completes one bounded dual-
nRF24 sweep, then advances CC1101 by one bin per main-loop turn before releasing the
resource and producing the final report. Stable active-check IDs and
`leshy.self_test.active_rf.v1` separate device progress from the independent host
oracle. `E-HIL-109` proves Quick 8/8, Full 18 pass/0 fail/1 blocked/3 N/A, exact wire
accounting, zero TX/storage side effects, 11 real TFT states and final lease 0. The
first runner equation mismatch is retained fail closed. Physical RF silence and
active execution of the remaining Survey/Library/Capture workflows stay open.

Exact `0.85.0-full-guided-artifacts` advances Full/Guided to plan v6 while keeping
Quick read-only and keeping radio and storage ownership strictly sequential. After
the RF adapters have cleaned up and released `RadioSpi`, a separate 500 ms
cancellable data boundary acquires `Storage|RadioSpi`, re-identifies the enrolled
CID, mounts read-only and reuses the boot recovery path for the latest atomic
Session. Staged discard sinks then exercise Library JSON, capture metadata, one CSV
record per main-loop turn and, when persisted raw frames exist, streaming radiotap
PCAP without creating or replacing user data. Stable check IDs plus
`leshy.self_test.active_artifact.v1` expose recovery, exporter bytes/records/hash and
final cleanup to the independent oracle. `E-HIL-110` proves Quick 8/8 and Full 21
pass/0 fail/1 blocked/3 N/A, unchanged generation 83, a 16-record/2,773 B PCAP,
zero storage writes/TX events and final lease 0. The first run that truncated the
expanded `ui.state` is retained fail closed; the bounded diagnostics workspace was
then raised to 4,608 bytes and the exact corrected candidate was rerun. Creating a
fresh disposable Survey/Capture, controlled physical power-cut and endurance remain
open.

Exact `0.86.0-full-guided-disposable` advances this boundary to plan v7. After the
read-only artifact audit, separate short-lived `Storage|RadioSpi` leases identify the
same enrolled CID, authorize only `/leshy-hil/full-guided-v7`, commit a deterministic
three-observation Session with finalized capture timeline, release, read-only remount
and export it, then reacquire for typed exact cleanup. A final read-only product
recovery proves generation 83/0 unchanged. The failed no-timeline candidate and the
corrected pass are both retained; only the latter writes three files/504 bytes and
then removes them. Controlled physical power-cut and one-hour endurance remain open.

Exact `0.87.0-full-guided-heap-budget` closes a diagnostic truth/budget defect exposed
by 0.86. The 4,608-byte storage line and 5,120-byte diagnostic JSON buffer never run
concurrently on the single main-loop command path, so one 5,120-byte workspace now
serves both. Full/Guided also clears and rebuilds its ordered report from final facts;
an end-of-run heap drop can no longer retain the healthy preflight result. Native
below-floor injection fails, while board-01 passes at 133,884 B against 131,072 B.

Exact `0.101.0-power-cut-harness` closes the remaining S4 durability boundary with a
separate protocol, not a hidden boot behavior. `power-cut disposable-write` prepares
only a typed exact-CID scratch Session, reaches one of the same six SessionStore
boundaries, emits a flushed arm record and waits while feeding the watchdog. It does
not call `esp_restart`. The host proves a real USB disappearance for at least three
seconds, tracks the same serial/VID/PID across re-enumeration, and then issues a
separate `power-cut-recover disposable-read-only` command. Firmware accepts that path
only for `ESP_RST_POWERON`; recovery cannot write, format, list product names or read
product data. Board-01 completes all six boundaries as generations 1/1/1/1/1/2 with
unchanged prior CRCs, zero recovery writes/syncs and lease 0. The fixture reuses the
dedicated diagnostic Session workspace, so static RAM remains 170,128 B and product
generation 95/0 is unaffected. Combined with exact 0.89 endurance, this closes S4;
S5 now extends the same broker/storage/observation contracts to every stock module.

Exact `0.115.0-wifi-device-intelligence` keeps the Wi-Fi Devices path passive and
bounded while separating raw evidence, inferred facts and presentation. The
promiscuous adapter admits only client Probe Request, Association/Reassociation
Request and to-DS Data frames into the existing fixed queue. `WifiDeviceCatalog`
merges directed SSID, BSSID/state/channel, supported rates, HT/VHT/HE generation and
WPS device/manufacturer/model into 32 fixed records; later sparse frames cannot erase
richer earlier evidence. `WifiOuiDatabase` binary-searches a build-pinned official
IEEE MA-L snapshot of 39,984 fixed 32-byte records directly from flash. Multicast and
locally administered MACs bypass OUI attribution, and optional fields stay unknown
unless broadcast. `WifiDeviceNavigationOrder` snapshots MAC identity on first user
interaction. The passport is frozen presentation; the following radar pins the
receiver to the selected observed channel and redraws only live RSSI/range/trend
content. Neither screen sends probes, associates, decrypts or writes persistent
identity. Exact HIL binds the source/OUI provenance, eight TFT states, two stable
lifecycles, zero drops/writes/chrome repaint and final lease 0.

Exact `0.116.0-wifi-channel-average` keeps the Wi-Fi Channels aggregation bounded
and separates two time scales. Each completed 120 ms dwell publishes the existing
current lower-bound airtime permille and adds it to a per-channel 64-bit cumulative
sum with a bounded dwell count. The snapshot exposes the arithmetic mean; reset on
task entry clears both. `bestPrimaryChannel()` compares only means for 1/6/11.
Rendering uses a wide gray mean bar behind a narrow colored current bar and clears
only that bar's previous extent, so the axis, legend, header and footer do not flash.
Native tests deliberately make the instantaneous winner differ from the mean winner;
physical HIL waits for at least two samples per channel and verifies exact gray TFT
pixels, data-only redraw, two clean lifecycles and final lease 0.

Later exact `0.120.0-wifi-channel-choice` supersedes that last selection rule without
changing storage. `bestPrimaryChannel()` waits for the complete 13-bit measured mask,
then compares `averageBusyPermille` for channels 1…13. A strictly smaller mean always
wins. Only equal means invoke an allocation-free adjacent-pressure sum over ±3
channel centres with weights 3/2/1, approximating decreasing 20 MHz overlap. The
renderer repaints the previous/new axis label together with the bounded recommendation
region, so exactly one candidate is highlighted and no full-screen refresh is added.

Self-review exact `0.121.0-wifi-channel-neutral-bars` makes rendering obey the same
channel-neutral model. `wifiChannelBarTone()` accepts only `busyPermille`; warning
and danger thresholds are common to every channel and low load always uses the same
positive tone. A host guard rejects reintroduction of the former 1/6/11 branch.

Exact `0.122.2-ble-device-intelligence` keeps BLE discovery receive-only while
carrying bounded advertisement facts through the existing observation pipeline.
The adapter explicitly disables active scan, deduplicates controller results and
normalizes address/advertisement type, legacy/connectable/scannable flags, TX power,
appearance, company ID, known service mask/counts and bounded payload lengths.
`BleDeviceCatalog` monotonically merges sparse advertisements for 32 identities,
moves fixed signal statistics with its stable strongest-first sort and snapshots
identity order once the user interacts. A 128,384-byte flash asset supplies 4,012
Bluetooth SIG company records by binary search; it is not copied into heap.
The full detail draws stable facts once and incremental refresh is limited to its
radar rectangle. A scan cycle permits at most two attempts and retries only the
scanner-unavailable/scan-timeout classes; a second failure remains terminal and
cleanup releases every lease. Advertisement enrichment remains volatile and is not
encoded by the current Session schema. The focused HIL minimum heap of 9,760 B is
below RB-04, so this functional checkpoint does not supersede mixed-workload release
resource/endurance evidence.

Exact `0.117.0-wifi-device-live-detail` removes `DeviceRadar` as a separate UI and
runtime state. The Devices open action copies the selected fixed record, locks the
passive adapter to its observed channel and enters `DeviceDetail`; Left performs the
matching unlock before returning to the list. Full render draws stable identity once.
Catalog revisions call only `renderWifiDeviceDetailLiveData()`, whose bounded lower
rectangle contains observation state and the existing signal card/range/trend. The
HIL oracle separates identity, live and chrome pixels and accepts an unchanged frame
when a newly received packet leaves every displayed value unchanged.

Exact `0.118.0-wifi-network-intelligence` enriches the scan path without turning it
active. `BoardWifiPassiveScanner` still uses passive ESP-IDF scans with
`show_hidden=true`; it normalizes the returned auth/cipher, channel-width/secondary,
PHY, WPS/FTM, RX-antenna, country, BSS-color and VHT-center fields into fixed
`WifiNetworkFacts`. `WifiNetworkCatalog` remains bounded at 32 BSSIDs and merges
sparse records monotonically: an empty SSID may become known when a later beacon or
probe response carries the same BSSID, while an empty later record cannot erase that
name or earlier facts. Vendor lookup reuses the flash-resident IEEE MA-L table.
Navigation still snapshots BSSID identities, so enrichment changes content in place
rather than cursor position. The detail renderer compares static facts separately
from RSSI; routine updates touch only the signal line. No directed probe,
association, decryption or persistent identity write is introduced.

Exact `0.119.0-wifi-network-live-radar` adds an allocation-free
`WifiNetworkSignalStats` alongside every one of the catalog's 32 fixed BSSID slots.
Insertion sort moves observations and statistics together; an update increments a
saturating sample count and maintains minimum, maximum and latest RSSI delta. Sample
count alone does not advance the UI revision. A visible RSSI/range/trend change does,
and `renderSelectionDelta()` repaints only the selected network's bounded radar card.
The shared survey service therefore refreshes NetworkDetail but still freezes BLE
detail. HIL binds telemetry, exact BSSID facts and framebuffer pixels. The source
remains the ordinary all-channel passive ESP-IDF scan: no channel lock, active probe,
association, calibrated distance or persistent signal history is added.

## Data model

### Passive 2.4 GHz signal finder

Exact `0.123.0-nrf24-signal-finder` reuses the guarded
`BoardNrf24PassiveSpectrum` adapter and its all-detected-slot receive-only plan;
it does not add a second hardware driver or any TX operation. The allocation-free
`Nrf24SignalFinder` aggregates 48 complete 83-bin sweeps per window. Two calibration
windows retain the per-bin minimum as ambient floor. Search subtracts that floor
and the common mean delta, then applies a bounded two-count hold decay so a local
transient remains visible without turning a broad environmental change into a
false target. Detection starts at local rise eight.

The UI state is separate from the receiver lifetime: the direct `spectrum24` app
holds `UiForeground|RadioSpi` while its two-choice menu is open, starts the adapter
only inside Overview/Finder, and returns to the menu before final app release.
Finder draws static chrome once and updates result state plus changed graph columns
only. Read-only `hardware.nrf24.finder` exposes calibration, mapping, receiver mask,
side-effect counters and leases for HIL; none of those counters appears on the TFT.
The physical acceptance covers real ambient receive/search/restart/cleanup; a known
board-02 source remains required for physical found-state evidence.

### Passive Sub-GHz frequency finder

Exact `0.124.1-cc1101-frequency-finder` reuses the guarded receive-only CC1101
adapter and owns `UiForeground|RadioSpi` only while Overview/Finder/Capture needs
the radio. `Cc1101SignalFinder` scans a fixed 275,000…949,500 kHz plan in 250 kHz
steps: 1,099 signed baseline bins, 1,099 raw-rise bins and 1,099 held-response bins
are statically allocated. Three complete calibration sweeps form a per-bin median;
search removes common-wideband drift, rejects neighborhoods within 500 kHz of
26/40 MHz board-clock harmonics and requires a local 18 dB rise. The earlier
minimum-of-two calibration accepted non-repeatable ambient minima as peaks; both
failed 0.124.0 runs are retained and the fixed candidate rejects them twice.

The board adapter programs one bounded CC1101 receive observation at a time and
permits only reset/RX/idle strobes. The product renderer draws static header,
instructions, axis and footer once, then changes only result state and the 240-column
response projection. Read-only `hardware.cc1101.finder` exposes calibration sweeps,
frequency mapping, response, side effects and lease state for HIL. No TX, PATABLE,
FIFO or storage operation exists in the finder path. The accepted board-01 evidence
covers real ambient receive/search/restart/cleanup; a controlled board-02 source is
still required for physical found-state and any calibrated-accuracy claim.

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
