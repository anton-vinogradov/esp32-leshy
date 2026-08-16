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
| DEMO-S2 | Independent platform and UX/UI baseline | boot → capability Home → Diagnostics → disabled reason → Back | clean target, real probe, common Actions, base visual system, zero leaked leases |
| DEMO-S3 | First persistent Survey Session | Start passive Wi-Fi → List → Detail → Stop → reboot → Library → export | first real product workflow and atomic persistent storage |
| DEMO-S4 | Cross-radio passive Session | multiple compatible receivers → timeline/radar → degradation → reopen/export | common Observation model, scheduler/duty cycle, and 8-hour passive stability |
| DEMO-S5 | Stock-hardware completeness | probe every present module → observe/capture → Library → inspect/export; approved replay separately | hardware parity, optional/degraded behavior, and recovery/power safety |
| DEMO-S6 | Targets, compare, and companion | baseline Session → repeat visit → diff/Target evidence → local companion export | primary product differentiation and one Action/schema boundary |
| DEMO-S7 | Safe Lab and SDK | saved Capture → Lab confirm → bounded TX → timeout/panic; sample extension | feature-complete 1.0, physical stop, and extensibility without policy bypass |
| DEMO-S8 | Release candidate | install/update → mixed field workflow → interrupted update/write → rollback/recovery | release-complete binary, provenance, endurance, and recovery |

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
