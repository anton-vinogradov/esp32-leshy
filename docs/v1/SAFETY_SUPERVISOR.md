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
- A complete loss of power also removes RTC retention and therefore acts as physical
  intervention; this software-only board cannot preserve the latch without power.

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

## Output contract

| Output/domain | ISR action | Boot/Safe Mode evidence | Current guarantee |
|---|---|---|---|
| buzzer GPIO2 | direct LOW | pad reads LOW | software-controlled sound path inactive |
| nRF CE GPIO14/15/47 | direct LOW | all pads read LOW | all declared nRF transmit enables inactive |
| CC1101 | no scheduler/SPI call in ISR | current firmware has no TX path; boot re-establishes receive/idle adapters only after clear | no independent hard stop; future TX is forbidden without hardware/physical-stop evidence |
| SD/product data | no ISR filesystem work | Safe Mode skips catalog/mount workers; catalog is re-opened read-only only after explicit clear/restart | no safety-trip write or implicit recovery mutation |
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

## Accepted Product Survey Wi-Fi worker deadline checkpoint

Version `0.133.0-worker-deadline-supervision` adds the first supervised worker
boundary without changing the retained-record layout. The real Core-0 Product Survey
task arms a 6 s deadline only after admission and scanner preparation complete. It
heartbeats around the UI start gate, every blocking Wi-Fi/BLE scan and the bounded
inter-scan wait, then disarms only after scanner/filesystem cleanup.

The main loop evaluates that independent state before normal worker events. Expiry
requests both scanners to cancel, releases the foreground application lease, holds
software-controlled outputs inactive and latches `worker_deadline` in the same
exact-app RTC record used by the main-loop watchdog. The test-only command
`safety.worker-deadline-test confirm` merely arms a one-shot 8 s delay; a normal
public Survey Start must activate the real worker.

Exact board-01 HIL now accepts the first bounded slice on the public **Wi-Fi →
Nearby Networks** path. The real Product Survey worker arms once and heartbeats
twice; the 8 s injected stall trips once at age 6,001 ms against the 6,000 ms
deadline. Cancel/cleanup completes, owner/lease becomes `none`/`0`, buzzer and nRF
CE remain inactive, and the retained `worker_deadline` latch survives a reason-3
software restart. Safe Mode advances through `latched` → `clear_pending` only after
the first public Right/OK Action, clears and restarts only after the second, and
returns Home with exact CID, catalog 98/0 and zero physical storage writes unchanged.
Three 240×320 TFT states and exact source/image/runner/transcript hashes are bound in
the [machine-checked artifact](../../tests/hil/evidence/board-01-worker-deadline-0.133.json).

This checkpoint deliberately does not claim physical BLE-worker coverage or the
admission/scanner-preparation interval: the current deadline arms only after that
preparation completes. A stale-menu pre-gate run entered the BLE path and was
rejected rather than reused as evidence. BLE needs its own source-appropriate
deadline/heartbeat proof before the Product Survey boundary is considered complete.

## Open safety work

- extend the accepted Wi-Fi Product Survey slice to BLE, the pre-admission/preparation
  interval, every other long-lived worker and any future transmit lease;
- route driver invariant, brownout/thermal, and storage safe-shutdown faults into the
  same reasoned latch only after trustworthy sensors exist;
- add an external rail/PA kill or load switch and a CC1101 reset/power gate for any
  future active-radio profile;
- measure GPIO reset/pull behavior and physical RF stop with independent equipment;
- include the destructive watchdog check in Full/Guided Self-Test and the final S8
  release manifest while keeping Quick read-only.
