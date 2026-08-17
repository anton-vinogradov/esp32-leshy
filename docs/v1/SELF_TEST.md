# ESP32-Leshy 1.x — on-device Self-Test

*Read in: **English** · [Русский](SELF_TEST.ru.md)*

Status: **accepted product/UX contract; S2 Quick and guided UI-state slices
physically accepted; Full/Guided capability coverage grows through S3…S8**.

Self-Test is an explicit application at the bottom of Home. It is never an automatic
boot detour. The same test engine serves a device owner, a guided field check, and
the release HIL station; the invoker and available fixtures change, not the meaning
of a check.

## Menu and modes

```text
Home
└─ SELF-TEST
   ├─ QUICK
   └─ FULL / GUIDED
```

| Mode | Purpose | Default side effects | Completion |
|---|---|---|---|
| `QUICK` | Answer “is this device basically healthy now?” | read-only; radios and user data remain untouched; buzzer stays LOW | bounded automatic checks and an exportable report |
| `FULL / GUIDED` | Exercise every applicable firmware workflow and installed device function | preflight lists writes, sound, radio, required media/fixtures, and estimated time; unsafe or unavailable checks do not start | automatic steps plus only unavoidable prompts such as pressing physical keys or confirming audible/visual output |

Quick does not run on boot. Boot only exposes the facts needed by the engine and
keeps the normal interactive-time budget.

## One engine, two independent judges

Every check is a versioned Action with a stable ID, declared resources, timeout,
safety class, required fixture, cleanup rule, and result schema. The on-device app
renders progress and stores the report. The release script invokes those same
Actions through the machine interface, but independently verifies candidate hashes,
protocol ordering, framebuffer images, counters, leases, and retained artifacts.
Device self-report alone cannot promote a release.

Result states are `pass`, `fail`, `not_applicable`, `blocked`, `skipped`, and
`inconclusive`. A module absent from the selected HardwareProfile is
`not_applicable`, not a false failure. A declared module that cannot be proved is
`fail` or `inconclusive`, never silently passed.

## Check families

| Family | Quick | Full / Guided and release extension |
|---|---|---|
| build/runtime | version, app identity, reset reason, heap, crash/watchdog record | restart recovery, leak/latency loops, endurance owned by the current Stage Demo |
| display/UI | TFT init plus deterministic framebuffer CRC | color/geometry/text patterns, screenshot comparison, every required UI state and Back path |
| input | frontend/task/queue health and idle raw value | prompt for every physical key; release fixture may use an actuator, while injected Actions separately test firmware navigation |
| feedback | GPIO2 configured LOW and quiet-mode state | bounded audible prompt when enabled; release fixture may add electrical/acoustic observation |
| storage | media/profile identity and read-only recovery | bounded scratch write/verify/recovery only after explicit preflight; user data remains outside the scratch namespace |
| radios | declared capability, driver/policy/lease readiness, no hidden start | passive receive workflows; active output only in an authorized instrumented Lab fixture with deadline and physical stop evidence |
| optional assemblies | profile declaration and conflict checks | applicable GPS/PN532/shield checks; absent assemblies report `not_applicable` |
| product workflows | controller/schema prerequisites | automated Home-originated Survey/Library/export and other stage-complete paths with final cleanup |

“All functionality” means every function applicable to the selected board/assembly
profile is exercised or produces an honest non-pass result. It never means probing
an ambiguous pin, transmitting without authorization, formatting arbitrary media,
or treating missing external instrumentation as success.

## Report contract

The report includes test-plan/schema version, firmware and app hashes, board/profile,
mode/invoker, start/end reason, per-check result/evidence/duration, operator prompts,
resource ownership before/during/after, heap and drop counters, side effects,
framebuffer/artifact hashes, and final cleanup. Secrets, raw nearby identifiers, and
unselected user data are excluded.

Back cancels at the next safe boundary, stops workers first, and publishes a partial
report. A run passes only if every required applicable check passes, no unexpected
side effect occurs, and final ownership is zero.

## Delivery and release use

- **S2:** bottom-of-Home entry, mode/preflight/result UI, Quick platform checks, and
  machine-readable report skeleton.
- **S3…S7:** each completed capability registers its Full/Guided check and its Stage
  Demo invokes the same Action.
- **S5:** all stock-hardware profile checks have physical evidence or an explicit
  conditional disposition.
- **S8:** the release script flashes exact bytes, runs the complete applicable plan,
  validates screenshots/report/artifact hashes independently, and only then permits
  promotion. Endurance and external power/RF fixtures remain separate plan steps but
  are indexed by the same report.

## Current S2 implementation

Candidate `0.53.0-self-test-quick-measure` established the final Home entry, mode
menu, Full preflight, result screens, eight stable Quick check IDs, and
`leshy.self_test.report.v1`. On board-01 it passed all eight Quick checks read-only
in 60 µs with zero radio/storage/buzzer side effects and final owner/lease
`none`/`0` (`E-HIL-077`). Its first physical attempt also exposed a loop-task stack
panic from a 3 KiB local diagnostic buffer; that failure is retained and the fixed
shared bounded workspace passed regression.

Candidate `0.57.0-ui-state-evidence-measure` advances the shared plan to version 2.
Full/Guided now walks the user or release driver through explicit dialog/confirm,
unavailable, degraded, error, and running cards after preflight. Nine actual TFT
frames and their Action/state traces are retained and machine-checked. The run passes
the eight Quick checks plus `full.ui.common_states`, then deliberately returns
blocked on `full.capability.coverage`: 9/10 pass, 0 fail, 1 blocked, with zero
radio/storage/buzzer side effects and final owner/lease `none`/`0`
(`E-HIL-081`/`E-UX-007`). This is the correct current result: incomplete S3…S7
capability checks cannot be promoted by the device or host.

## Acceptance

1. `SELF-TEST` is reachable by normal buttons as the last Home item; no serial-only
   action is required.
2. Quick is read-only, bounded, cancellable, emits no TX, and leaves zero leases.
3. Full shows scope before side effects, supports all applicable capability checks,
   and records `not_applicable/blocked` honestly.
4. User and release invocations execute the same versioned checks.
5. The host independently rejects wrong bytes, missing checks, stale/mixed reports,
   screenshot mismatch, unexpected side effects, or incomplete cleanup.
