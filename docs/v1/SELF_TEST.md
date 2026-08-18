# ESP32-Leshy 1.x — on-device Self-Test

*Read in: **English** · [Русский](SELF_TEST.ru.md)*

Status: **accepted product/UX contract; S2 Quick/guided UI, completed S3/S4
registration, the conditional RF-shield identity check, and the first active
receive-only RF execution are physically accepted; remaining Full/Guided workflow
execution continues through S4…S8**.

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

## Accepted S2 implementation

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

Exact committed candidate `0.58.0-stage-demo-s2-measure` accepts this platform slice
through `E-AUTO-022`/`E-HIL-082`/`E-GATE-002`. Self-Test still does not run at boot:
it remains the final Home item. The device exposes Quick and Full/Guided through the
normal five-key Action path, and `ui.state` publishes the current
`self_test_visual_state` so a release driver can verify the same semantic state that
the user sees. DEMO-S2 passes 29 steps, nine TFT comparisons, Quick 8/8, and zero
final leases; Full capability coverage remains honestly blocked until S3…S7.

## Accepted S3/S4 registration checkpoint

Exact candidate `0.80.0-self-test-coverage` advances the shared report to plan
version 3. It retains the eight read-only Quick checks and registers seven more
passing checks for common UI states, persistent Survey, passive BLE, passive Wi-Fi
Capture, enrolled storage, cold Library recovery, and persistent raw Capture. The
actual no-extension assembly reports GPS, PN532, and IR as `not_applicable`; it does
not convert missing hardware into failures or false passes. The two remaining checks,
`full.s4.shield.receivers` and `full.capability.coverage`, remain `blocked`.

On board-01 the independent host accepted the exact 15 pass / 0 fail / 2 blocked /
3 N/A ordered report, ten real TFT states, exact firmware/ELF/CID, unchanged storage
generation 83, zero radio-TX/storage-write/buzzer side effects, healthy input, and
final owner/lease `none`/`0` (`E-AUTO-045`/`E-HIL-105`/`E-SELFTEST-002`). This proves
honest registration and readiness/persistence checks; it deliberately does not yet
claim that Full/Guided actively executes every product workflow.

## Accepted RF-shield identity checkpoint

Exact candidate `0.81.0-shield-receiver-probe` advances the shared report to plan
version 4. Only after the user confirms the Full/Guided preflight, the foreground
Self-Test owner acquires `RadioSpi` and runs a bounded identity probe. nRF24 slots 1
and 2 each expose four registers while CE remains LOW; slot 3 is never selected and
GPIO21 must remain HIGH. CC1101 exposes only PARTNUM and VERSION status registers.
Any profile conflict, busy lease, floating/partial identity, side-effect counter or
cleanup failure fails closed. Nothing probes these receivers at boot.

Board-01 detects both nRF24 receivers and CC1101 PARTNUM 0/VERSION 0x14 in exactly
8 nRF register reads, 2 CC status reads and 20 SPI bytes. CE-high events, CC command
strobes and radio-TX commands are zero; storage remains generation 83 with zero
observations, and final owner/lease returns to `none`/`0`. Full is therefore 16 pass /
0 fail / 1 blocked / 3 N/A: `full.s4.shield.receivers` passes and only future total
capability coverage remains blocked (`E-AUTO-046`/`E-HIL-106`/`E-SELFTEST-003`/
`E-RADIO-001`). This proves bounded read-only identity, not physical RF silence,
passive activity reception or spectrum capture; those need their own workflows and,
for physical silence, unavailable RF instrumentation.

## Accepted active receive-only RF checkpoint

Exact candidate `0.84.0-full-guided-rf` advances the shared report to plan version 5
and adds `full.s4.spectrum.nrf24.receive` plus
`full.s4.spectrum.cc1101.receive`. After the five semantic UI cards, Full/Guided
shows a cancellable active screen for 500 ms, acquires `RadioSpi`, performs one
complete 83-channel receive sweep across the two declared nRF24 receivers, then one
64-bin CC1101 receive sweep in the 433 MHz plan. The work is cooperative and Back
cleans both adapters before release. Quick remains unchanged and read-only; Full is
now honestly `read_only:false` because it configures receivers, even though no
transmit or storage-write path is representable.

On board-01 Quick passes 8/8 and Full returns 18 pass / 0 fail / 1 blocked / 3 N/A.
Exact nRF24 accounting is 93 reads, 95 writes, 376 SPI bytes and 83 verified RX CE
windows. CC1101 accounts 2,060 reads, 208 writes, 4,730 SPI bytes and 1 reset / 64 RX /
129 idle strobes. TX-mode, payload, TX-strobe, PATABLE, FIFO, rejected-command and
storage-write counters are all zero; generation remains 83, eleven real TFT states
pass review, and final owner/lease is `none`/`0`
(`E-BUILD-085`/`E-AUTO-049`/`E-HIL-109`/`E-SELFTEST-004`/`E-RADIO-004`).

The first exact HIL attempt is retained as a fail-closed runner-model failure: it
expected an extra idle strobe per CC1101 bin. Source and observed wire accounting
show the implemented `SIDLE → tune → SRX → read → SIDLE` sequence, so the independent
equation was corrected and the same firmware bytes passed. This checkpoint proves
software-instrumented receive-only execution, not physical RF silence. Total
capability coverage and active Survey/Library/Capture execution remain blocked/open.

## Accepted read-only persisted-artifact checkpoint

Exact candidate `0.85.0-full-guided-artifacts` advances Full/Guided to plan version 6
with `full.s4.storage.recovery.audit`, `full.s4.library.export.audit`, and
`full.s4.capture.pcap.audit`. After the receive checks release `RadioSpi`, a separate
500 ms cancellable data screen re-identifies the enrolled SD card, mounts it with the
driver's read-only guarantee, and reopens the latest atomic Session. JSON metadata is
formatted in the bounded shared workspace; CSV advances one record per main-loop turn;
persisted raw Wi-Fi frames, when present, are streamed as radiotap PCAP into a discard
sink that counts bytes/records and FNV-1a without retaining payload. The Library view
and all Storage/RadioSpi ownership are restored before the final report.

Board-01 passes 21 checks with zero failures, one future capability blocker and three
profile N/A results. Exact CID and generation/observation continuity are
`FE34…9CB7` and 83/0→83/0. The audit produces 432-byte JSON, 880-byte capture metadata,
94-byte zero-row CSV and a 16-frame/2,773-byte PCAP digest; storage-write, blocked-write
and radio-TX counters remain zero. If the latest valid Session has no persisted frame
payload, the PCAP artifact check is honestly N/A rather than fabricated pass.

The first physical attempt is retained fail closed because the expanded `ui.state`
exceeded the old 4,096-byte diagnostics buffer. The single bounded workspace was
raised to 4,608 bytes, host limits were updated, and the corrected exact candidate
passed all 12 visually reviewed TFT states and final lease 0
(`E-BUILD-086`/`E-AUTO-050`/`E-HIL-110`/`E-SELFTEST-005`/`E-STORAGE-026`/
`E-CAPTURE-003`). This does not create a fresh Survey/Capture or modify user data.

## Accepted disposable write/remount/export checkpoint

Plan v7 creates a test Session only in an exact disposable namespace after the user
explicitly starts Full/Guided: exact enrolled CID, bounded run ID, and a dedicated
cleanup permit resolve only `/leshy-hil/<run-id>`. Cleanup first scans the entire
directory without mutation and accepts only bounded SessionStore names
(`head-a.bin`, `head-b.bin`, and exact eight-digit manifest/segment files); a nested
directory, unknown file, malformed generation or more than eight entries fails
closed before deletion. General remove, rename and recursive-delete APIs remain
forbidden.

Exact `0.86.0-full-guided-disposable` registers four checks for commit, read-only
remount, Library export and cleanup. Board-01 writes generation 1 with three fixture
observations through exactly three writes/504 bytes and three file plus three
directory syncs. Read-only remount recovers the same generation and exports JSON,
metadata and three CSV rows; cleanup removes the three exact files and scratch
directory. Product generation/observations remain 83/0 with zero product writes,
and final Home owns no resources.

The first physical candidate is retained fail closed: capture metadata selected
Wi-Fi but the fixture omitted its mandatory matching finalized timeline, so encoding
stopped before the first storage write. Cleanup still removed the empty scratch and
preserved product data. The corrected exact candidate adds one Wi-Fi timeline window
accounting for all three observations and passes 13 TFT states
(`E-BUILD-087`/`E-AUTO-051`/`E-HIL-111`/`E-SELFTEST-006`/`E-STORAGE-027`). This proves
the isolated disposable path, not controlled physical power-cut or endurance.

Exact `0.87.0-full-guided-heap-budget` corrects two related constraints exposed by
that run. The final Full/Guided snapshot now rebuilds Quick before emitting the
ordered report, so a heap minimum that crosses the floor during active work becomes
an actual failure. The serial diagnostics/storage commands share one bounded
5,120-byte workspace, recovering 4,608 B of static RAM. Native below-floor injection
fails; board-01 passes at 133,884/131,072 B minimum/floor with the same 25/0/1/3
functional result and exact cleanup (`E-BUILD-088`/`E-AUTO-052`/`E-HIL-112`/
`E-SELFTEST-007`).

## Accepted touch-input checkpoint

Exact `0.88.0-touch-input` advances the report to plan version 8 and adds the
read-only `quick.input.touch` check. It verifies that the physical frontend is
initialized, calibration is ready and the public touch dispatcher is present; it
does not synthesize a pass from coordinates or run interactive calibration during
boot. Quick now passes 9/9 with zero RF, storage or buzzer side effects.

The HIL separately requires one real panel tap before synthetic geometry coverage.
On board-01 point `(76,91)` opens Diagnostics exactly once using the CRC-valid
calibration `[533,2996,531,3117,6]`. The rejected threshold-350 attempt and its zero
touch events are retained; threshold 80 passes against idle raw pressure 3…14.
Header/footer and touch Back are rejected, four TFT states are retained, heap is
unchanged and final lease is zero (`E-BUILD-089`/`E-AUTO-053`/`E-HIL-113`/
`E-SELFTEST-008`). Full/Guided plan-v7 workflow semantics remain accepted by exact
0.87; they were not rerun or silently promoted by this focused corrective.

## Acceptance

1. `SELF-TEST` is reachable by normal buttons as the last Home item; no serial-only
   action is required.
2. Quick is read-only, bounded, cancellable, emits no TX, and leaves zero leases.
3. Full shows scope before side effects, supports all applicable capability checks,
   and records `not_applicable/blocked` honestly.
4. User and release invocations execute the same versioned checks.
5. The host independently rejects wrong bytes, missing checks, stale/mixed reports,
   screenshot mismatch, unexpected side effects, or incomplete cleanup.
