# Two-board HIL and declarative scenarios

*Read in: **English** · [Русский](TWO_BOARD_HIL.ru.md)*

Status: **implemented and host-verified S5 foundation; board-02 is purchased but
has not yet been connected, read-only profiled or used for a physical run**.

## Roles and trust boundary

| Role | Firmware | Authority |
|---|---|---|
| `candidate` / board-01 | exact product candidate | device under test; the product IR path remains RX-only and has no replay/TX authority |
| `fixture` / board-02 | separate `leshy_fixture` image | emits one fixed NEC vector only after exact host admission |
| host | `run_ir_two_board_hil.py` → `run_hil_scenario.py` | binds physical roles, exact commits/images/IDs, sequences the scenario, captures TFT/CSV and fails closed |

Fixture sources live outside the product project. Source guards reject fixture code
inside `firmware/leshy1`, and the fixture build contains no Wi-Fi, BLE, RF-radio,
SPI, SD or user-replay path.

## Implemented first positive scenario

`tests/hil/scenarios/infrared-nec-positive.json` is the first complete two-board
scenario. It:

1. enters `Home → Capture → Infrared` using public Actions;
2. admits board-02 for one source-bound `nec-10-34` emission;
3. requires the exact 67-pulse NEC decode (`address=0x10`, `command=0x34`);
4. retains the live pulse CSV, explicitly saves the capture and proves one-generation
   storage continuity;
5. cold-reboots the product, reopens Library, checks IR-specific metadata and
   exports a byte-identical CSV;
6. returns both boards to a proven inactive state and board-01 to Home/lease 0.

The existing one-board no-signal evidence for exact 0.104 remains accepted. The new
positive scenario is gate-eligible by contract but has **not run physically**, so it
is not evidence yet.

## Fixture safety contract

The implemented `0.1.0-ir-nec` image:

- preloads buzzer GPIO2, IR TX GPIO14 and nRF CE GPIO15/47 LOW before making them
  outputs; GPIO21 stays input;
- derives its 16-character fixture ID from the ESP32-S3 efuse base MAC and binds the
  exact running app ELF identity;
- never auto-arms; admission requires a random 128-bit session, exact app hash and
  exact fixture ID and expires after 5 s;
- permits only fixed NEC code `0xCB34EF10` at 38 kHz, once per admission, with a hard
  measured-duration ceiling of 100 ms;
- publishes start/stop/panic/emission counters, duration and all inactive-pad facts;
- quiesces outputs on boot, normal completion, explicit stop, panic, timeout, parser
  failure and Task-WDT ISR.

The NEC emitter is deliberately allocation-free and blocking for approximately
68 ms. A serial panic cannot interrupt a burst already authorized and executing;
the burst cannot repeat or exceed 100 ms and its completion path immediately drives
all controlled outputs inactive. This software bound is not an independent physical
rail kill or oscilloscope/RF proof.

## Read-only board-02 admission

Before any fixture flash, `profile_hil_board.py` invokes ROM esptool with `--no-stub`
and only `chip-id`, `read-mac`, `flash-id` and `get-security-info`. The retained
profile must prove ESP32-S3, 16 MB flash, zero erase/write/stub operations, an exact
port and canonical fixture ID. The operator must explicitly declare a standard v2
assembly without extension modules and attached antennas; missing facts are not
inferred.

The runner rejects identical candidate/fixture ports, a profile captured from a
different current fixture port, dirty/uncommitted source, mismatched images, IDs,
versions or commits, a non-inactive fixture, any second emission, storage/heap/input
drift, incomplete cleanup or a nonzero final product lease.

## One-command physical run

With both boards connected under distinct serial ports, a clean committed tree can
build both images, create the read-only fixture profile, flash the explicitly named
ports, execute every step and retain the machine run under `work/outputs`:

```sh
tools/run_ir_two_board_hil.py \
  --candidate-port /dev/cu.CANDIDATE \
  --fixture-port /dev/cu.FIXTURE \
  --expected-cid FE343253440000002000000055019CB7 \
  --output work/outputs/ir-nec-positive-0.125 \
  --profile-fixture-read-only \
  --declare-standard-v2-no-extensions \
  --declare-antennas-attached
```

An already accepted profile can instead be passed with `--fixture-profile`. Exact
already-flashed bytes can be reused only through the explicit
`--reuse-exact-candidate-flash` and `--reuse-exact-fixture-flash` options; normal
operation flashes both exact images. The raw passing run is subsequently admitted
to tracked evidence by `hil_evidence.py`, which independently verifies fixture
profile/source/image identity and terminal inactive outputs.

## Current evidence boundary

Source commit `f1b3394a10848b4a7112f2b8777b0e46c0954019` and host tests establish the
software boundary. Product candidate `0.125.0-ir-fixture-foundation` builds at
233,288 B static RAM and 3,061,504 B linked flash. Fixture app image
`c95996e2…f520` is 322,624 B, with app identity `2786589a…557`, 22,724 B static RAM
and 322,215 B linked flash.

No board was flashed for this checkpoint. Board-02 profile, successful NEC decode,
persistence, cold Library export and final physical cleanup all remain open until
both devices are connected. Sub-GHz and 2.4 GHz fixture transmission remain
unauthorized pending separate regional/band, attenuation/separation and vector
contracts; the IR permission does not generalize to RF.
