# ESP32-Leshy 1.x — risk register

*Read in: **English** · [Русский](RISK_REGISTER.ru.md)*

Document status: **active S1 register**. `STATUS` owns current stage state; this file
owns durable risks, controls, triggers, and closure evidence.

## Rating and handling

- Likelihood and impact are `low`, `medium`, or `high`; the labels prioritize work
  and are not fake numeric probabilities.
- Treatment is `avoid`, `reduce`, `constrain`, `transfer`, or `accept`.
- A risk remains `open` until its closure evidence exists. A documented fallback can
  constrain product scope without proving the underlying hardware safe.
- A new fact that invalidates an accepted requirement or stage gate reopens that
  decision through `GOVERNANCE` rather than silently changing implementation.

## Register

| ID | Risk / trigger | L | I | Treatment and current control | Owner / closure evidence | State |
|---|---|---|---|---|---|---|
| R-001 | ESP32 module/PSRAM variants differ across v2 batches; observed board-02 substitutes N16R8 whose Octal pins collide with the display | H | H | portable profile keeps PSRAM disabled and classifies N16R8 separately; ROM-reported memory never expands budgets | boards; exact assembly IDs plus a pin-compatible display/PSRAM proof if such a profile exists | reduced/open |
| R-002 | Legacy `TFT_RST=0` drives BOOT while schematic ties TFT reset to RESET/EN | M | H | avoid GPIO0 output/reset probing; clean profile keeps reset external | boards/display; HW-T02 continuity/logic evidence | open |
| R-003 | SD/NRF/CC/PN532 shared SPI transactions corrupt storage or wedge a receiver | H | H | exclusive `spi_radio` operation leases; no transparent sharing until traced endurance | kernel/drivers/storage; HW-T03/HW-T05 + RB-07 | open |
| R-004 | GPIO5/6, GPIO14/21, or GPIO2 multiplexing causes contention, TX, sound, or false battery data | H | H | explicit assembly profile; GPIO2 is held OUTPUT LOW until a bounded sound service and is never ADC-sampled; other contested output probes are forbidden | boards/drivers; buzzer boot/runtime state + audible observation, HW-T07…HW-T09 | reduced/open |
| R-005 | Receiver/backlight/SD current peaks cause brownout, heat, or data loss | M | H | unmeasured combinations disabled by RB-08; Wi-Fi-first slice avoids shield concurrency | boards/power; HW-T10 rail/thermal matrix | open |
| R-006 | Power loss or cancellation corrupts a Session/Capture or an older committed record | M | H | append-only/immutable source model; atomic-storage ADR and fault matrix required | storage; WF-02-A4, WF-03-A3, PR-005 | open |
| R-007 | No-PSRAM heap pressure, fragmentation, or unbounded queues fail long Survey runs | H | H | RB-03/04, bounded queues/pools, high-water/drop counters, no monotonic heap decline | kernel/services; size gate + one-hour-budget release endurance; optional extended qualification after major runtime changes | open |
| R-008 | UI or driver blocks a core, Back is late, or a worker/lease survives navigation | M | H | one Navigator event path; ≤10 ms callbacks; cancel token; atomic ResourceBroker release | kernel/UI; WF acceptance traces, NFR-002/003/006 | reduced/open |
| R-009 | An active action starts outside Lab policy or does not physically stop | M | critical | no shipped TX without finite lease, visible state, independent stop HIL and region policy | safety/kernel/drivers; WF-05-A1…A5 + physical detector trace | open |
| R-010 | Malformed capture/import/schema input crashes or exhausts the device | H | H | length/bounds before allocation, version rejection, fuzz corpus, immutable originals | parsers/storage; WF-03-A4, NFR-007…009 | open |
| R-011 | Update/signing/rollback failure bricks a device or installs an untrusted build | M | H | two bootable slots, signed manifest/image, recovery path retained and HIL-tested | update/platform; PR-010 rollback/recovery matrix | open |
| R-012 | Framework/library drift or an abandoned dependency blocks reproducible builds | M | H | pin toolchain and direct dependencies; framework behind platform adapters; CI builds from clean cache | platform; toolchain ADR + clean reproducibility job | open |
| R-013 | Feature-count competition recreates the 0.x monolith and delays the Survey outcome | H | H | every change maps to J/PR/WF and current stage; menu parity is not a requirement | product/architecture; traceability review at every gate | reduced/open |
| R-014 | Credentials, precise location, MACs, or captured payload leak through logs/exports | M | H | redact diagnostic/export defaults; explicit data selection; private recovery backup never committed | services/security; report/export scans and permission tests | open |
| R-015 | Missing continuity/logic/RF/power instruments create false confidence even with two boards | H | H | label evidence partial; board-02 RF stays `fault`; unknown stays unknown; no cross-swap/emission before rail/pinout admission | hardware QA; comparative continuity/rail plus named HW-T evidence | accepted constraint |
| R-016 | Schema or Action API changes make stored evidence or companion clients incompatible | M | H | version every boundary, forward migrate or reject clearly, immutable source data | services/SDK; schema/Action ADRs + migration contract tests | open |
| R-017 | EN/RU or color-only UI hides safety/error meaning or truncates critical controls | M | M | one string catalog/build, snapshot fixtures, standard-button coverage, no color-only state | UI/product; WF snapshots + NFR-010 matrix | open |
| R-018 | A fatal loop/worker fault leaves software-controlled outputs active or silently reboots into the same unsafe operation | M | critical | permanent panic Task WDT on the main loop; IRAM GPIO2/14/15/47 quiesce; exact-app torn-write-resistant RTC latch; no automatic clear; Safe Mode blocks product workers and normal Actions | safety/platform; exact 0.103 `E-AUTO-068`/`E-HIL-128`/`E-SAFETY-001` accepts the real main-loop watchdog, retained software-reset latch, inactive pads and explicit-clear TFT path; worker heartbeats and independent physical-stop HIL remain closure work | reduced/open |
| R-019 | Clone/DNP assemblies preserve the enclosure and menu but change module population, shared-radio wiring or RF front ends; board-02 has valid idle rails and its assembled RF carrier clamps shared MISO LOW, while upstream issue #102 independently reports the same all-radio failure shape from interboard faults | H | H | exact assembly profiles; compare BOM/photo/ROM; safe read-only identity and pull characterization before any TX; 23/32 kΩ powered-off comparison rejects a hard short; exact 0.131 changes GPIO13 LOW→HIGH when the carrier is removed; exact 0.132 proves all four CSNs HIGH while reassembled MISO is LOW with zero bus/TX activity; antenna appearance alone authorizes no solder change; board-02 remains RF-fault/no-cross-swap | boards/RF; return/replace carrier/device or physically isolate module MISO/power; require repaired plausible same-image identity before bounded regression | reduced/open |
| R-020 | Defensive detector or channel/auth analysis presents a false conclusion as a threat or proof | M | H | every conclusion exposes detector/version/threshold/confidence/uncertainty and exact evidence; insufficient fixtures remain inconclusive; no automatic response. Exact dev.210 pins these rules for the first Wi-Fi disconnect-burst detector and excludes driver/TX dependencies; dev.211 validates reports, freezes evidence-strength order and preserves a visible incomplete-evidence flag through drilldown | analytics/product; `E-BUILD-159…160`/`E-AUTO-133…134` are partial control; WF-06-A1/A2 live golden + negative corpora, TFT evidence drilldown and physical cleanup still close the risk | reduced/open |
| R-021 | Authentication frames, precise tracks, lock state/recovery data, or automation transcripts leak sensitive information or lock out the owner | M | H | encrypted/scoped storage, redacted defaults, explicit export selection, bounded retries and tested owner recovery; safe cleanup/recovery never requires unlock | security/storage; PR-021/022/024 privacy, recovery and export matrix | open |
| R-022 | Connected BLE, UART, CLI, USB/BLE HID or scripts broaden the active interface and bypass target consent, leases, or policy | H | critical | explicit mode/target/permission preview, separate finite leases, least privilege, no raw GPIO, passive inspection default, audit and deterministic disconnect/cleanup | security/runtime; WF-06-A4, WF-07-A3/A4, WF-08-A1/A2 | open |
| R-023 | A script or wireless recipe runs away, exceeds resource/TX bounds, or smuggles a forbidden disruptive action | M | critical | signed/versioned packages, per-recipe review, resource/time ceilings, SafetySupervisor, watchdog, panic/expiry physical stop and forbidden-class rejection | safety/extensions; WF-08-A1/A3/A4 + independent physical HIL | open |

`critical` is reserved for a safety failure whose prevention takes priority over
feature delivery; it is intentionally stronger than `high`.

## Stage controls

### S1 exit

- R-001…R-005 and R-015 are measured or constrained in the Hardware Envelope and
  Resource Budgets; no unresolved pin conflict is labelled available.
- Binding ADRs exist for toolchain, resource policy, storage schema/atomicity, and
  Action boundary.
- Each P0 maps to an owner and negative/positive evidence type.

### S2–S4

- CI enforces pinned builds and RB-02…RB-05.
- Resource/Action negative tests cover failed start, Back, cancel, expiry, and worker
  crash.
- Storage fault injection and the bounded passive endurance gate (at least 45 minutes
  and 8 cycles, completed within one hour) close R-006…R-008/010.

### S5–S8

- Per-module HIL and measured power combinations close or permanently constrain the
  hardware risks.
- No active action ships until R-009 has independent physical stop evidence.
- Signed update, rollback, recovery, import fuzzing, privacy, and EN/RU accessibility
  matrices are release gates.
- S7 cannot close while R-020…R-023 lack negative corpora, privacy/recovery evidence,
  permission/lease tests, and independent stop evidence for every active interface.

## Review triggers

Review this register when a new board batch/profile appears, a dependency or
partition/schema changes, an active capability is proposed, a power/bus/storage test
fails, or a requirement/stage gate changes. Update `STATUS` only when the fact changes
current progress, evidence, or a blocker.
