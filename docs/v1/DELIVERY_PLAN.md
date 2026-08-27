# ESP32-Leshy 1.x — stages to 1.0.0

*Read in: **English** · [Русский](DELIVERY_PLAN.ru.md)*

This document defines stable stage boundaries. Current state, evidence, and next
actions live only in [STATUS.md](STATUS.md). A stage closes on a verifiable outcome,
not on code volume; every technical stage after S1 leaves a working vertical slice.

## Stage map

```text
S0 Governance and version boundary
 └─ S1 Evidence and constraints
     └─ S2 Clean 1.x platform
         └─ S3 First Survey Session
             └─ S4 Cross-radio passive platform
                 └─ S5 Complete ESP32-DIV hardware
                     └─ S6 Targets, comparison, and companion
                         └─ S7 Competitive completeness, Safe Lab, and extensibility
                             └─ S8 Reliability, RC, and 1.0.0
```

| Stage | Candidate artifact | Primary outcome |
|---|---|---|
| S0–S1 | no user release | the right problem and real constraints are frozen |
| S2 | `1.0.0-alpha.1` | an independent target boots and diagnoses the board |
| S3 | `1.0.0-alpha.2` | the first persisted end-to-end Survey Session |
| S4 | `1.0.0-alpha.3` | one passive multi-radio session |
| S5 | `1.0.0-alpha.4` | baseline workflows for standard ESP32-DIV hardware |
| S6 | `1.0.0-beta.1` | Leshy's main product differentiators |
| S7 | `1.0.0-beta.2` | accepted competitor completeness, safe active work, and an extension contract |
| S8 | `1.0.0-rc.*` → `1.0.0` | evidenced field reliability |

A version tag labels an artifact; it never closes a gate by itself.

## Cross-cutting control points

Three documents protect stage outcomes without creating extra stages:

- the [capability catalog](CAPABILITY_CATALOG.md) freezes complete 1.0 scope in S1;
- the [UX/UI baseline](UX_UI_BASELINE.md) agrees product UX in S1 and the real-TFT
  visual/interaction system in S2;
- the [Stage Demo](STAGE_DEMO.md) closes every S2…S8 stage through a reproducible
  end-to-end run on hardware.

S7 means **feature-complete**: every accepted P0/P1 and applicable conditional
`CAP-*` is implemented. S8 means **release-complete**: the same capabilities pass
the release matrix, endurance, and recovery; S8 does not add major feature scope.

## Product functionality map

This is the readable top-level index of the complete planned 1.0 product. The
[capability catalog](CAPABILITY_CATALOG.md) remains the normative, testable inventory
of all 55 `CAP-*` items; this map groups them by user outcome and assigns every group
to the stage that must deliver it. Live completion status belongs in
[STATUS.md](STATUS.md).

| Product area | Planned user-visible functionality | Owning stage |
|---|---|---|
| Device foundation and UX | reliable boot and board profiles; unified five-key navigation; consistent EN/RU visual system and feedback; safe resource arbitration; Diagnostics; on-device Quick plus extensible Full/Guided Self-Test | S2, then extended through S8 |
| Survey and evidence library | explicit passive Survey Start/Stop; normalized observations; List/Detail; atomic Session storage; offline Library; cold reopen; JSON and recorded-trace export | S3 |
| Passive multi-radio observation and packet Capture | selectable Wi-Fi/BLE; compatible nRF24/CC1101 spectrum contracts; GPS context; common timeline, filters, RSSI views and capture metadata; dedicated bounded Wi-Fi frame Capture; PCAP plus CSV/JSON; visible degradation/duty; privacy-aware persistence; power-cut recovery and multi-source endurance | S4 |
| Complete standard ESP32-DIV hardware | IR capture/decode/library and authorized replay; PN532 tag/NDEF/dump and authorized write/restore; GPS fix/track/time; resilient SD/LittleFS browse/import/export; calibration, power, sleep/resume and low-voltage safety | S5 |
| Targets, comparison and local companion | target identities/history/correlation, tags and notes; reversible merge/split; session/capture baseline and diff; localization and GPS map; offline search; local Web/USB companion over the same Actions and schemas | S6 |
| Competitive completeness, device security, Safe Lab and extensions | Airspace Guard; focused Wi-Fi authentication Capture; offline Field Survey; BLE raw/GATT Inspector; Device Lock; bounded Serial Console/Actions CLI; permissioned signed automation and scoped HID; explicit legal/safety context; individually admitted Wi-Fi/BLE/nRF recipes; controlled TX/write paths, indication, timeout and panic stop; permissioned app descriptors/scoped storage; signed/versioned decoders; protocol workbench; SDK, sample extension and simulator traces | S7 |
| Trust, recovery and distribution | stable/beta signed OTA, rollback and recovery; one release/on-device Self-Test plan; automated HIL, screenshots, endurance, fault injection and fuzzing; crash bundle; backup/restore; reproducible binaries, provenance, compatibility and support policy | S8 |

Screenshots, accessibility, privacy, resource budgets, data integrity and fail-closed
cleanup are cross-cutting acceptance properties: they are exercised in every owning
stage rather than postponed to S8.

## S0 — Governance and generation boundary

**Goal:** prevent the 0.x PoC and the new product from becoming one ambiguous line.

Outputs: archived and frozen 0.x docs; canonical documentation hierarchy and conflict
rules; IDs for jobs, requirements, stages, and ADRs; one status document, delivery
plan, and traceability map; a web installer explicitly labeled 0.x.

**Exit gate:** a new contributor can unambiguously find current scope, active stage,
and its exit conditions; no active checklist competes with `STATUS`; internal links
pass validation.

## S1 — Evidence baseline: users, competitors, and hardware

**Goal:** prove the product fits real ESP32-DIV constraints before freezing an
implementation.

Outputs: power/GPIO/bus/memory/mode-conflict map; capability matrix; reference
workflows with happy/error/cancel flows; measured flash/RAM/storage/startup/power
budgets; risk register; accepted 1.0.0 PRD baseline; evidence-based selection of the
first Survey source; ADR candidates for toolchain, storage, and resource policy;
reviewed `CAP-*` catalog and explicit exclusions; accepted information architecture,
common Actions, mandatory UX states, and S2…S8 Stage Demo protocol.

**Exit gate:** every P0 maps to a capability, constraint, architecture owner, and test
type; no unknown pin/resource conflicts remain; the first slice fits measured
budgets; the scope catalog and S1 UX direction are accepted.

## S2 — Clean 1.x platform

**Goal:** create the minimum independent firmware needed to build safe workflows
without linking the 0.x monolith.

Outputs: separate target and layered source tree; pinned toolchain; BoardProfile,
HardwareProbe, and Diagnostics; Navigator and unified input; AppRuntime, capability
registry, and atomic ResourceBroker; basic display/storage/logging/crash/time services;
a real-TFT EN/RU visual/interaction baseline; a bottom-of-Home Self-Test app with
Quick platform checks and a versioned report skeleton; host CI and minimum
boot/input/probe HIL.

**Exit gate:** a clean build boots without the 0.x menu, reports the actual board,
survives 1,000 open/back cycles without lost leases or heap growth, tolerates missing
hardware, and passes reproducible host/HIL checks.
`DEMO-S2` and UX-01…UX-07 must also pass the common Stage Demo protocol.
Quick Self-Test must be button-accessible, read-only, bounded, cancellable, and leave
zero ownership; the Full/Guided registry grows with each later stage.

## S3 — First vertical slice: Survey Session

**Goal:** prove the full product and architecture path using one passive source.

Outputs: Start/Stop Survey Actions; normalized Observations from one driver; shared
List/Detail with correct back/cancel/error states; atomic Session storage; offline
reopen after reboot; JSON summary export; a recorded trace for host integration.

**Exit gate:** all nine PRD slice criteria have evidence; software-reset interruption
preserves committed Session data; UI, CLI/test harness use identical Action semantics.
Controlled physical power removal is measured with the multi-source workload in S4.

Closed by exact 0.70 `E-AUTO-035`/`E-HIL-095`/`E-GATE-003`: a distinct run matches
five independently recorded TFT goldens, commits generation 69→70 with 29/29 passive
observations, cold-reopens/exports it and returns Home with zero leases.

## S4 — Cross-radio passive platform

**Goal:** turn the single-source slice into a shared passive observation system.

Outputs: Wi-Fi/BLE scan, NRF24/CC1101 spectrum, and GPS driver contracts; scheduler
for compatible and exclusive resources with visible duty cycle; common timeline,
filters, views, and metadata; PCAP plus CSV/JSON exports; bounded queues and
instrumentation; a release endurance test of at least 45 minutes/eight complete
cycles within a one-hour operational budget.
Every completed passive source also registers its applicable Full/Guided Self-Test
check instead of creating a release-only diagnostic path.

**Exit gate:** one Session safely joins available passive sources, explains resource
unavailability, survives reboot/export and controlled physical power-cut, and has no
heap growth or data corruption. This extends the S3 baseline accepted by
`E-HIL-095`/`E-GATE-003`.

Closed by exact 0.89 endurance plus exact 0.101
`E-AUTO-066`/`E-HIL-126`/`E-STORAGE-028`/`E-GATE-005`: eight cross-radio cycles run
for 2,799.845 s, and the common SessionStore then recovers read-only across all six
real power-cut boundaries with unchanged product data and zero final leases.

## S5 — Complete ESP32-DIV hardware

**Goal:** give every standard module a complete useful workflow and reach meaningful
0.x/original parity without porting their menu structure.

Outputs: IR capture/decode/library and policy-approved replay; PN532 probe, tag/NDEF,
versioned dump, and authorized write/restore; GPS diagnostics and track/time; resilient
SD/LittleFS library and import/export; calibration, power/sleep/resume, and low-voltage
safe writes; passive smoke/error tests for every module.

**Exit gate:** `PR-014` is verified; missing optional hardware cannot break boot or
neighboring workflows; every module completes probe → observe/capture → library →
inspect/export.

## S6 — Product differentiation: Targets, comparison, companion

**Goal:** outperform isolated tools through connected data and analysis.

Outputs: Target history/identities/tags/notes and evidence-based correlation;
reversible merge/split; session and capture baseline/diff; localization, timeline, and
GPS track; local Web/USB companion using the same Actions/schemas; offline search and
export without an account.

**Exit gate:** a user records and compares two surveys, identifies new/disappeared/
changed Targets, and opens the source evidence for every conclusion on-device or in
the local companion.

## S7 — Competitive completeness, Safe Lab, and extensibility

**Goal:** deliver the accepted competitor-review outcomes, protect sensitive local
data, and enable controlled research/automation of owned equipment without bypassing
platform guarantees.

Outputs: evidence-backed Airspace Guard; focused authentication Capture; offline
Field Survey and BLE Inspector; Device Lock and bounded Serial Console/Actions CLI;
permissioned signed automation and scoped HID; Lab context, regulatory policy, TX
indication/deadline/panic stop; named individually admitted Wi-Fi/BLE/nRF recipes;
application descriptors, permissions, and scoped storage; signed/versioned decoder
packages; protocol workbench; sample app/decoder, SDK docs, and simulator trace kit.

**Exit gate:** an external developer builds a sample extension without kernel changes;
extensions cannot bypass leases/permissions; HIL proves physical stop for every
shipped TX path on timeout, Back, panic, and fault; the 1.0 catalog is
feature-complete across all 55 accepted capabilities and passes `DEMO-S7`.

## S8 — Release hardening and 1.0.0

**Goal:** turn beta into a device trusted with a field day and its data.

Outputs: signed stable/beta OTA, rollback, and recovery; full HIL matrix; fuzzing;
crash journal and diagnostic bundle; performance/storage/power budget evidence;
complete schemas, threat model, compatibility/support policy; reproducible binary
hashes and provenance; one complete Self-Test plan shared by on-device Full/Guided
and the independently verified release runner.

**Exit gate:** two consecutive RCs have no open P0/P1; a mixed workload covers at
least 45 minutes/eight cycles and finishes within one hour with no freeze, leak,
drops, or corruption; interrupted update/write recovery succeeds; every P0
requirement is `verified`; `DEMO-S8` passes without adding new feature scope.

## After 1.0.0

Authenticated DIV-to-DIV Peer Link, additional board profiles, extension catalogs,
languages, and analytics require a new 1.x requirement/stage proposal and cannot
retroactively weaken the 1.0.0 gates.
