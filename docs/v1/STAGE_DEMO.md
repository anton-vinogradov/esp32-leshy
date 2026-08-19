# ESP32-Leshy 1.x — intermediate Stage Demo protocol

*Read in: **English** · [Русский](STAGE_DEMO.ru.md)*

Status: **mandatory delivery gate for S2…S8**.

Testing does not wait for a complete firmware image. Every vertical slice receives
host tests and applicable HIL immediately, and stages S2…S8 close only through a
reproducible Stage Demo on real hardware. Percentage complete and isolated unit tests
do not replace a demo.

## Common demo packet

Every `DEMO-S*` retains:

1. firmware version, commit/worktree identity, board/profile, and dependency lock;
2. a Home-originated happy path, error/degraded path, and Back/cancel path;
3. automated serial/action trace and real-TFT captures of key states;
4. applicable host/unit/integration results and firmware size/RAM budgets;
5. HIL boot/input/resource-cleanup and affected physical-module results;
6. known limitations without claiming “done” while the gate remains open;
7. `CAP-* → PR/NFR-* → WF-* → evidence` links in traceability/STATUS.

An operator is required only for physical observations that cannot be acquired from
the board or instruments automatically. Routine menu navigation and TFT evidence use
UI automation.

## Demos by stage

| ID | Demonstrated result | Minimum end-to-end path | What it proves |
|---|---|---|---|
| DEMO-S2 | Independent platform and UX/UI baseline | boot → capability Home → Self-Test Quick → Diagnostics/disabled reason → report → Back | clean target, real probe, common Actions, base visual system, user-visible automation, zero leaked leases |
| DEMO-S3 | First persistent Survey Session | Start passive Wi-Fi → List → Detail → Stop → reboot → Library → export | first real product workflow and atomic persistent storage |
| DEMO-S4 | Cross-radio passive Session | multiple compatible receivers → timeline/radar → degradation → reopen/export | common Observation model, scheduler/duty cycle, and ≥45-minute/≥8-cycle passive stability inside a one-hour release budget |
| DEMO-S5 | Stock-hardware completeness | Full/Guided preflight → probe every present module → observe/capture → Library → inspect/export; approved replay separately | hardware parity, optional/degraded behavior, honest N/A/blocked results, and recovery/power safety |
| DEMO-S6 | Targets, compare, and companion | baseline Session → repeat visit → diff/Target evidence → local companion export | primary product differentiation and one Action/schema boundary |
| DEMO-S7 | Safe Lab and SDK | saved Capture → Lab confirm → bounded TX → timeout/panic; sample extension | feature-complete 1.0, physical stop, and extensibility without policy bypass |
| DEMO-S8 | Release candidate | exact candidate → complete Self-Test plan → mixed field workflow → interrupted update/write → rollback/recovery | same on-device/release checks, independent oracle, release-complete binary, provenance, endurance, and recovery |

`DEMO-S2` is accepted by `E-BUILD-060`/`E-AUTO-022`/`E-HIL-082`/`E-GATE-002`.
Exact committed candidate 0.58 completed 29 public Action/query steps and matched nine
separately recorded real-TFT goldens with zero mismatches; Quick passed 8/8, safe
outputs stayed inactive, and the final resource lease was zero. This is an S2 stage
gate, not a release: Full capability coverage remains blocked until S3…S7 register
their checks.

S3 progress `E-AUTO-023`/`E-HIL-083` reuses that exact 0.58 candidate and proves the
real passive product path through live List→Detail→Back, generation 65→66 commit,
cold read-only reopen, Library, and JSON export. Five TFT states are visually
reviewed and final ownership is zero. Normal-path evidence has since advanced through
0.60/0.62, and exact 0.68
`E-AUTO-032`/`E-HIL-092` closes the missing-source real-TFT path without starting the
source or store, writing bytes, changing the prior 68/25 Library, leaking a lease, or
allowing a hidden Select retry. It is still deliberately not `DEMO-S3`: independently
recorded final demo goldens and the reproducible gate run remain open. Exact 0.69
`E-AUTO-033`/`E-HIL-093` accepts normal/remount LittleFS throughput, and exact 0.70
`E-AUTO-034`/`E-HIL-094` accepts all six software-reset boundaries with one-write
inactive-OTA1 restoration. Controlled physical power-cut is a named `DEMO-S4` gate.

`DEMO-S3` is now accepted by `E-AUTO-035`/`E-HIL-095`/`E-GATE-003`. A separate
non-gate recording run froze five manually reviewed TFT goldens before the distinct
gate run. Exact 0.70 then advanced generation 69→70 with 29/29 passive observations,
zero drops, cold read-only reopen and valid Library export; all five comparisons have
zero unmasked mismatch, heap is invariant, and final ownership is zero. S3 is closed
and S4 is active; this does not promote a release or waive any `DEMO-S4` gate.

S4 progress through exact 0.75 now covers selectable/durable real Wi-Fi/BLE and
compatible runtime degradation. `E-AUTO-040`/`E-HIL-100` safely injects BLE
unavailability, continues two real Wi-Fi cycles and 28 observations, commits
generation 77→78, cold-reopens eight ordered windows including the exact unavailable
interval, and ends with zero drops/overflow and lease 0. This is a slice checkpoint,
not `DEMO-S4`. Exact 0.76 then accepts the common read-only Observation browser:
All/Wi-Fi/BLE filters, List/Detail, bounded RSSI history and an RF-off frozen snapshot
cover 45 observations, generation 80→81, nine exact TFT states, cold recovery and
zero drops/overflow. Exact 0.77 then accepts immutable Capture provenance and the
47-row canonical observation CSV. Exact 0.78 accepts a deliberately separate bounded
Wi-Fi packet Capture: 16 retained real frames, parsed radiotap PCAP, aggregate-only
repository evidence, RAM scrub and final lease 0. Exact 0.79 then accepts explicit
privacy-confirmed atomic persistence, generation 82→83, cold read-only Library reopen
and a byte-exact PCAP without a second payload buffer. Exact 0.80 then registers the
completed platform/S3/S4 checks in Self-Test. Exact 0.81 advances it to plan v4: 16
checks pass, three absent assemblies are N/A, the declared nRF24 #1/#2 and CC1101
identity check passes under exact read-only wire bounds, and only total future
coverage remains blocked. Useful passive receiver workflows, active Full/Guided
execution, controlled physical power-cut and ≥45-minute/≥8-cycle multi-source stability
remain mandatory.

Exact 0.82 accepts the first of those useful shield workflows: an explicit
Survey→RF spectrum→2.4 GHz/nRF24 path draws a volatile 83-channel activity map,
supports a measured pause/resume, completes 21 dual-receiver sweeps with exact
receive-only wire accounting, leaves heap/storage invariant and returns Home with
lease 0. The retained contract does not claim calibrated power or instrumented
physical RF silence. Active Full/Guided execution, controlled physical power-cut and
endurance still keep `DEMO-S4` open.

Exact 0.83 accepts the second useful shield workflow: Survey→RF spectrum→Sub-GHz/
CC1101 exposes 315/433/868/915 MHz plans, samples one of 64 bins per main-loop turn
and redraws only after a sweep. The board run completes every band, holds exactly at
351 samples during a 400 ms pause, resumes and stops cleanly after 354 samples with
zero TX/PATABLE/FIFO/storage side effects, invariant heap/storage and final lease 0.
Its RSSI and frequency scale are not calibrated and physical RF silence is not
instrumented. Active Full/Guided execution, controlled physical power-cut and
endurance still keep `DEMO-S4` open.

Exact 0.84 accepts the first active Full/Guided execution slice. Plan v5 leaves
Quick read-only at 8/8, then actively performs one complete dual-nRF24 receive sweep
and one 64-bin CC1101 433 MHz receive sweep. Full returns 18 pass, zero fail, one
honest future-coverage blocker and three N/A; all TX/storage counters stay zero,
storage generation remains 83, 11 TFT states pass review and final lease is zero.
The initial runner equation mismatch is retained fail closed. Remaining
Survey/Library/Capture execution, controlled physical power-cut and the one-hour-budget
endurance gate still keep `DEMO-S4` open.

Exact 0.85 accepts the next Full/Guided slice. Plan v6 runs the RF phase first,
releases it, then crosses a separate cancellable boundary into a read-only persisted
artifact audit: exact-CID recovery of generation 83, Library JSON and capture
metadata, staged CSV, and a machine-parsed 16-record/2,773 B PCAP. Full returns 21
pass, zero fail, one honest future-coverage blocker and three N/A; storage writes and
TX events remain zero, 12 TFT states pass review and final lease is zero. The first
telemetry-truncation failure is retained fail closed beside the corrected run.
Fresh disposable Survey/Capture creation, controlled physical power-cut and the
≥45-minute/≥8-cycle cross-radio endurance gate still keep `DEMO-S4` open.

Exact 0.86 accepts the disposable Full/Guided slice. Plan v7 adds four checks that
create a three-observation Session only under the exact-CID scratch namespace,
commit it with three writes and durability barriers, recover/export it after a
read-only remount, then remove every exact scratch file. Product generation 83/0 is
unchanged, TX/product-write counters stay zero, 13 TFT states and final lease 0 pass.
The first no-timeline candidate is retained fail closed with zero writes; the fixed
candidate binds capture metadata to a finalized Wi-Fi timeline. Controlled physical
power-cut and the ≥45-minute/≥8-cycle endurance gate inside one hour are now the two
remaining `DEMO-S4` gates.

Exact 0.87 then closes the heap-budget defect observed in the 0.86 evidence. Final
facts now rebuild Quick, a native below-floor case fails, and one shared serial
workspace recovers 4,608 B static RAM. The same physical plan-v7 run passes at a
133,884 B minimum against the 131,072 B floor with unchanged functional/cleanup
evidence. This closes the heap issue, not either remaining `DEMO-S4` gate.

Exact 0.88 accepts calibrated XPT2046 touch as a second non-blocking input path over
the same Navigator and finger-sized rows. Exact 0.89 then closes the release-endurance
gate: 8/8 complete Wi-Fi+BLE product cycles over 2,799.845 s advance generation
86→94, forward 367 observations through 16 cold boots, preserve heap and exact CID,
record zero drops/timeouts, and finish each cycle with no owner or lease. Radio and
SD lifecycles do not overlap. Controlled physical power-cut recovery is now the only
remaining `DEMO-S4` gate; the stage itself is not yet complete.

Exact 0.90 then accepts the final product-first menu hierarchy without changing the
gate: Survey/Capture/Library are direct working entries, planned Targets/Lab fail
closed, and Settings/Self-Test/Diagnostics/About live under Device. Eight real TFT
states prove key/touch traversal and final zero ownership. Controlled physical
power-cut recovery remains the only `DEMO-S4` gate.

## Test cadence within a stage

- **On change:** fast host/static tests and related negative cases.
- **At slice completion:** build, automated board smoke, TFT/action evidence, and
  resource cleanup.
- **Before the gate:** complete `DEMO-S*`, current-capability regression matrix, and
  open risk/budget review.
- **S8:** two consecutive RCs pass the same release packet without redefining the
  criteria after seeing the result.

A Stage Demo is not a marketing video: it passes only when commands, logs, binary
hash, and expected observations make the result reproducible.
