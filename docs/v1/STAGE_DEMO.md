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
| DEMO-S4 | Cross-radio passive Session | multiple compatible receivers → timeline/radar → degradation → reopen/export | common Observation model, scheduler/duty cycle, and 8-hour passive stability |
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

S4 progress through exact 0.74 now covers selectable and durable real Wi-Fi/BLE:
`E-AUTO-039`/`E-HIL-099` serializes one scan per source, records 6+34 observations,
commits generation 76→77, cold-reopens six ordered dual-source windows and ends with
zero drops/overflow and lease 0. This is a slice checkpoint, not `DEMO-S4`: injected
degradation, controlled physical power-cut and 8-hour multi-source stability remain
mandatory.

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
