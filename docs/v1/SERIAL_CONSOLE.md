# Serial Console and shared Actions CLI

*Read in: **English** · [Русский](SERIAL_CONSOLE.ru.md)*

- **Capability:** CAP-053
- **Requirements:** PR-012, PR-017, PR-024, PR-025; NFR-002, NFR-003, NFR-006
- **Workflow:** WF-07, especially WF-07-A3/A4
- **Architecture:** [ADR-002](adr/ADR-002-resource-policy.md),
  [ADR-004](adr/ADR-004-action-boundary.md)
- **State:** host/build foundation at `1.0.0-dev.284`; product UI, hardware adapter
  and physical HIL remain open

## User outcome

The owner can monitor or bridge a selected, owned 3.3 V UART target without turning
Leshy into an arbitrary GPIO shell. Before anything owns pins, the device shows the
target, named wiring profile, voltage assumption, baud, framing, mode, permissions,
finite duration and every resource conflict. Back, timeout, failure and panic close
the port, scrub the unsaved buffer and release all ownership.

The same typed Action is used by the on-device flow and the local Actions CLI. A
transport may narrow permissions, but never widen the current unlocked device
session. No transcript is stored unless the user performs a separate explicit Save;
saved transcripts will use Device Lock protected storage.

## Safe hardware boundary

The first supported target profile is named `mux56-3v3`:

| Property | Contract |
|---|---|
| ESP receive | GPIO5, external target TX → ESP RX |
| ESP transmit | GPIO6, ESP TX → external target RX; Bridge only |
| Logic | 3.3 V UART only; it is not RS-232/RS-485 and is not 5 V tolerant |
| Availability | explicit external-UART assembly profile only |
| Conflicts | unavailable while the RF shield, GPS or PN532 owns/is declared on GPIO5/6 |

The stock `stock-rf-no-gps-no-pn532` assembly has the RF shield attached: GPIO5 is
CC1101 CSN and GPIO6 is GDO0. Serial Console must therefore explain `mux_conflict`
and remain unavailable on that assembled profile. Firmware does not accept numeric
RX/TX pin fields and does not offer raw GPIO read/write as a fallback. A later board
profile may add another *named and physically reviewed* wiring profile; it may not
weaken this rule.

## Modes and permissions

| Mode | Data direction | Required permissions | Confirmation |
|---|---|---|---|
| Monitor | target → Leshy only | `device.control`, `serial.monitor` | fresh target/config confirmation |
| Bridge | target ↔ Leshy | Monitor permissions plus `serial.write` | fresh target/config/write confirmation |

Both modes are `ActiveConfirmed` because even receive-only pin ownership changes a
shared mux. Baud is one of 1200/2400/4800/9600/19200/38400/57600/115200; framing is
8N1/8E1/8O1/8N2; a run lasts 1 second to 5 minutes. Target IDs are explicit bounded
ASCII tokens (1…32 bytes), not ambient labels. ResourceBroker atomically owns both
`Console` and `Mux56`; a partial lease is never visible.

## Shared Action contract

The stable first Action is `serial.console.start` v1 with request/result schema 1.
Dispatcher admission order is:

1. descriptor and schema bounds;
2. authenticated device session;
3. complete permissions;
4. declared capability;
5. fresh confirmation;
6. atomic `Console+Mux56` lease;
7. hardware adapter start.

Failure before step 7 has no hardware side effect. A failed adapter start releases
the acquired lease. Completion, cancel, timeout and endpoint failure are terminal and
release both resources. A second invocation returns `busy` without mutating the
already-running invocation.

The strict allocation-free CLI accepts only these shapes:

```text
action.preview serial.console.start profile=mux56-3v3 target=<id> baud=<baud> framing=<8N1|8E1|8O1|8N2> mode=<monitor|bridge> duration_ms=<ms>
action.run serial.console.start profile=mux56-3v3 target=<id> baud=<baud> framing=<8N1|8E1|8O1|8N2> mode=<monitor|bridge> duration_ms=<ms> confirm=yes
action.status serial.console.start
action.cancel serial.console.start
```

Unknown/duplicate/missing fields, raw pin numbers, unsupported Actions, ambiguous
whitespace, oversized lines and `run` without `confirm=yes` fail closed.

## Delivery slices

1. `done` — typed dispatcher, strict CLI parser, named profile preflight, separate
   monitor/write permissions, atomic leases, timeout/cancel/error cleanup, native
   contract tests and production build (`dev.284`).
2. `next` — bounded Arduino UART adapter and volatile ring, Device → Serial Console
   preview/running/result screens, Device Lock admission and shared CLI execution.
3. `planned` — physical receive-only loop fixture, then explicitly permissioned
   bridge fixture; Back/error/timeout/watchdog HIL, zero leaked leases and no saved
   transcript.
4. `planned` — explicit encrypted Save, cold reopen/export and release HIL matrix.

`dev.284` is not a physical UART claim: it deliberately performs no pin change,
device flash, serial bridge, storage write, radio operation or network operation.
