# ESP32-Leshy 1.x — software Safety Supervisor

*Read in: **English** · [Русский](SAFETY_SUPERVISOR.ru.md)*

Document status: **binding S5 software-safety contract**. Current implementation is
not a certified safety system and cannot replace missing power-cut, temperature,
voltage, or current-monitoring hardware.

## Purpose and boundary

The Safety Supervisor is a system-wide fail-closed layer below applications. It must
turn an observed fatal software fault into a bounded reset and a latched Safe Mode,
instead of silently rebooting into normal operation. It owns no product feature and
does not infer safety from a healthy UI.

The ESP32-DIV v2 board can provide a panic-enabled ESP32-S3 Task WDT and force the
known active-high buzzer plus all declared nRF CE pins LOW. It cannot, with the
confirmed wiring, disconnect the 3.3/5 V rails, independently reset or power-gate the
CC1101, measure cell/rail temperature, or prove that a dead MCU physically stopped a
radio. Those unavailable controls remain explicit `false` facts in diagnostics.

## State machine

```text
startup ── successful WDT/output checks ──> armed
   │                                          │
   └── unavailable/invariant fault ───────────┤
                                              ↓
                         fatal fault ──> latched Safe Mode
                                              │
                                      OK / Right once
                                              ↓
                                        clear pending
                                      │               │
                               Left cancels     OK / Right confirms
                                      │               │
                                      └── latched     ↓
                                                 clear RTC + restart
```

- There is no timeout or automatic clear from `latched`.
- A console clear requires the exact `safety.clear confirm` command.
- The normal UI uses the same Action path as physical keys: first OK/Right requests
  unlock, the second confirms; Left only cancels the pending clear.
- A later software/EN/USB reset does not clear an accepted exact fault record.
- A complete loss of power removes the RTC latch and therefore acts as physical
  intervention. The durable NVS incident journal survives power loss, but it is
  diagnostic history and cannot recreate or substitute for the live safety latch.

## Runtime watchdog sequence

1. Boot establishes buzzer LOW and nRF CE LOW before console/display startup.
2. The narrow SD boot-recovery watchdog runs under its existing separate arm flag.
3. After boot recovery, the main loop task is permanently subscribed to the
   panic-enabled 5 s Task WDT.
4. Every completed main-loop turn feeds that watchdog. An intentional test can stop
   feeding only when Home has no owner or lease.
5. The Task-WDT ISR first distinguishes the narrow SD recovery arm from the runtime
   arm. For a runtime trip it uses direct ESP32-S3 GPIO write-one-to-clear registers
   to lower GPIO2/14/15/47, then writes an exact-app retained record.
6. The retained record is published magic-last and contains value/complement pairs
   for app identity, reason, trip count, quiesce count, and latch confirmation. Torn
   or foreign-app records are rejected.
7. The panic path resets the MCU. A fresh runtime record is accepted only with a
   watchdog-class reset, then marked confirmed in task context. Later resets retain
   that confirmed Safe Mode; an unconfirmed stale record cannot create one.
8. Safe Mode skips product SD recovery, radio workers, capture workers, and normal
   Actions. It permits only diagnostics, TFT capture, evidence-session commands,
   the two-step UI clear, and the exact console clear.

## Durable incident journal

- The ISR performs no flash or filesystem work. It only quiesces outputs and
  publishes the bounded exact-app RTC record described above.
- On the first safe task-context boot, a valid watchdog-class RTC incident is
  written once to internal NVS and read back for verification. A sequence marker
  prevents later resets from duplicating the same incident.
- NVS is mandatory for the current device profile. Its verified record preserves
  reset reason, triggered CPU mask, firmware identity, page, stage and active Wi-Fi
  view even if the SD card is absent, unavailable, wrong, full or unwritable.
- Safe Mode never mounts or writes the card. Only after explicit two-step clear and
  normal exact-CID storage admission may the same retained incident be mirrored to
  `/leshy/diagnostics/v1/watchdog-%08lx.json`.
- The SD mirror is opportunistic and atomic: a temporary file is written, synced,
  closed, read back exactly, renamed, synced and verified. Failure leaves the NVS
  record intact and exposes a reasoned status; it never hides the original cause.
- The FatFS file and verification buffers share one nothrow heap workspace. An
  allocation failure reports `workspace_unavailable`; there is no unbounded retry.

## Output contract

| Output/domain | ISR action | Boot/Safe Mode evidence | Current guarantee |
|---|---|---|---|
| buzzer GPIO2 | direct LOW | pad reads LOW | software-controlled sound path inactive |
| nRF CE GPIO14/15/47 | direct LOW | all pads read LOW | all declared nRF transmit enables inactive |
| CC1101 | no scheduler/SPI call in ISR | current firmware has no TX path; boot re-establishes receive/idle adapters only after clear | no independent hard stop; future TX is forbidden without hardware/physical-stop evidence |
| SD/product data | no ISR filesystem work | Safe Mode skips catalog/mount workers; after explicit clear/restart normal exact-CID admission permits one atomic diagnostic mirror | no safety-trip write or implicit recovery mutation; NVS remains authoritative if SD is unavailable |
| power rails | none | `physical_rail_kill_available=false` | rails remain energized |
| thermal/voltage/current | none | availability remains false | no over-temperature/undervoltage claim |

The ISR never logs, flushes, allocates, takes a mutex, calls an Arduino adapter, or
performs SPI/filesystem cleanup. Task-context quiesce is idempotent, but the ISR path
does not depend on it.

## Observable schemas and automated HIL

- `safety.state` emits `leshy.safety.v1`: state/reason, arm/latch/clear status,
  watchdog timeout, retained counters, reset reason, safe pad state, owner/lease, and
  explicit hardware limitations.
- `hardware.safe-outputs` extends its compatible v1 record with all-nRF-CE and
  software-quiesce facts.
- `safety.watchdog-test confirm` is a bounded destructive diagnostic: it is accepted
  only from normal `armed` Home with no runtime owner/lease and inactive output pads,
  emits a flushed arm record, then deliberately stops feeding the main-loop WDT.
- `safety.restart-test confirm` is accepted only from a latched, quiescent Safe Mode;
  it emits a flushed proof record and performs a software reset without clearing the
  retained latch. It is an automated persistence diagnostic, not a user clear path.
- `tools/run_1x_safety_watchdog_hil.py` flashes one exact candidate, proves normal
  arm, causes the real Task-WDT reset, checks retained Safe Mode and inactive pads,
  performs an explicit output-quiesced software restart and requires the latch to
  remain, captures both Safe Mode TFT states, clears through the public Right/OK
  Action path, and proves exact CID/catalog continuity plus final Home lease zero.

The test is not a simulation and must retain the reset transcript. A missing reset,
invalid record, automatic recovery, writable storage activity, unexpected owner,
or unavailable final Home is a terminal failure.

Accepted board-01 checkpoint: exact `0.103.0-safety-supervisor`, source/runner commit
`2863090`, `E-BUILD-104`/`E-AUTO-068`/`E-HIL-128`/`E-SAFETY-001`. The real panic
Task-WDT reset occurred after 5,810.775 ms with reason 6; one retained trip/quiesce
survived a reason-3 software restart, three TFT states were captured, catalog 95/0
and exact CID remained unchanged, and explicit clear ended at Home with lease zero.
The [machine-checked artifact](../../tests/hil/evidence/board-01-safety-watchdog-0.103.json)
also binds all negative hardware claims below.

Exact physical `1.0.0-dev.376`, `E-BUILD-245`/`E-AUTO-224`/`E-HIL-241`/
`E-SAFETY-089`/`RB-M258`, accepts the durable-journal extension. The retained
rejected dev.375 run proves first-boot NVS persistence and restart deduplication,
then honestly retains its loopTask stack-canary failure in the SD path. Dev.376
moves the FatFS workspace off the loopTask stack (`writeSd` 4,496 → 384 B), records
one reset-reason-6 incident as sequence 2, defers SD in Safe Mode, preserves that
sequence without a second NVS write across restart, and atomically verifies one
mirror on the enrolled exact-CID card after explicit clear. The run ends at
Home/armed/none/lease 0. Both incident and correction are source-bound in the
[privacy-minimal machine-checked artifact](../../tests/hil/evidence/board-01-runtime-watchdog-journal-1.0.0-dev.376.json).

## Accepted calibrated Product Survey Wi-Fi+BLE worker deadline checkpoint

Version `0.133.0-worker-deadline-supervision` added the first supervised worker
boundary without changing the retained-record layout. Version
`0.134.0-ble-worker-deadline` calibrates the real Core-0 Product Survey deadline to
8 s. The BLE adapter publishes its exact two-attempt/one-retry worst-case duration:
6,100 ms for the current plan. A compile-time assertion requires the Product Survey
deadline to remain greater than that bound. The task still arms only after admission
and scanner preparation complete, heartbeats around the UI start gate, every
blocking Wi-Fi/BLE scan and the bounded inter-scan wait, and disarms only after
scanner/filesystem cleanup.

The main loop evaluates that independent state before normal worker events. Expiry
requests both scanners to cancel, releases the foreground application lease, holds
software-controlled outputs inactive and latches `worker_deadline` in the same
exact-app RTC record used by the main-loop watchdog. The test-only command
`safety.worker-deadline-test confirm` merely arms a one-shot 10 s delay; a normal
public Survey Start must activate the real worker.

Exact 0.133 board-01 HIL accepts the public **Wi-Fi → Nearby Networks** fault path.
Exact 0.134 now accepts the public **Bluetooth → Nearby Devices** normal and fault
paths. The normal lifecycle completes one BLE cycle/attempt, accepts 34/34
observations, records zero drops/transient retries and does not trip. It then cleans
up to owner/lease `none`/`0`. A second lifecycle arms the same worker, injects the
10 s stall and trips once at age 8,001 ms against the 8,000 ms deadline, for
cumulative arm/heartbeat/trip counts 2/8/1. Cancel/cleanup completes, buzzer and nRF
CE remain inactive, and the retained `worker_deadline` latch survives a reason-3
software restart. Safe Mode advances through `latched` → `clear_pending` only after
the first public Right/OK Action, clears and restarts only after the second, and
returns Home with exact CID, catalog 98/0 and zero physical storage writes unchanged.
Three 240×320 TFT states and exact source/image/runner/transcript hashes are bound in
the [machine-checked artifact](../../tests/hil/evidence/board-01-worker-deadline-0.134.json).

Exact `0.135.0-survey-preparation-deadline` adds a separate 8 s supervisor from the
public Start transition through card identity, read-only filesystem/store checks,
scanner startup and admission. Heartbeats bracket every bounded retry/wait and each
hardware boundary; the calibrated worker is armed only after preparation disarms.
The test-only `safety.worker-preparation-deadline-test confirm` injects one 10 s
delay before any preparation hardware operation. A normal BLE lifecycle first arms
preparation then the worker and accepts 30/30 observations in one attempt with zero
scan drops/retries. The injected lifecycle trips preparation at 8,001 ms, with
cumulative arm/heartbeat/trip 3/18/1, and preserves the same quiesce, retained latch,
two-action clear, exact CID/catalog and final Home/lease-zero contract. The exact
source/image/runner/transcripts and three TFT states are retained in the
[machine-checked artifact](../../tests/hil/evidence/board-01-worker-preparation-deadline-0.135.json).

This checkpoint does not cover other long-lived workers, future transmit leases,
full-power retained state or a physical rail/radio kill.

## Open safety work

- extend the accepted Product Survey slice to every other long-lived worker and any
  future transmit lease;
- route driver invariant, brownout/thermal, and storage safe-shutdown faults into the
  same reasoned latch only after trustworthy sensors exist;
- add an external rail/PA kill or load switch and a CC1101 reset/power gate for any
  future active-radio profile;
- measure GPIO reset/pull behavior and physical RF stop with independent equipment;
- include the destructive watchdog check in Full/Guided Self-Test and the final S8
  release manifest while keeping Quick read-only.
