# Two-board HIL and declarative scenarios

*Read in: **English** · [Русский](TWO_BOARD_HIL.ru.md)*

Status: **accepted physical S5 IR checkpoint; bounded nRF24 positive path implemented
and awaiting its exact two-board run**.

## Roles and trust boundary

| Role | Firmware | Authority |
|---|---|---|
| `candidate` / board-01 | exact product candidate | device under test; product radio paths remain RX-only and have no replay/TX authority |
| `fixture` / board-02 | separate `leshy_fixture` image | emits one admitted fixed NEC or minimum-power/time-bounded nRF24 vector |
| host | signal-specific wrapper → `run_hil_scenario.py` | binds physical roles, exact commits/images/IDs, sequences the scenario, captures TFT/data and fails closed |

Fixture sources live outside the product project. Source guards reject fixture code
inside `firmware/leshy1`. The fixture build contains no Wi-Fi, BLE, SD, arbitrary
payload/replay or product-side transmitter path. SPI exists only for the reviewed
fixed nRF24 register vector in [ADR-006](adr/ADR-006-bounded-signal-fixture.md).

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

The existing one-board no-signal evidence for exact 0.104 remains accepted. Exact
0.129 now also passes the physical positive scenario and is retained as
[machine-checked evidence](../../tests/hil/evidence/board-01-infrared-nec-0.129.json).

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

The `0.2.2-bounded-signals` source retains the NEC contract and adds exactly one RF
vector, `nrf24-ch42-min-2s`. It uses populated module slot 2 (CSN48/CE47), nRF
channel 42 / 2,442 MHz,
`RF_SETUP=0x90` (continuous carrier + PLL lock + chip minimum −18 dBm setting) and a
two-second duration with a 2.5-second hard ceiling. Boot, completion, stop, panic,
parser failure and Task-WDT hold all three CE pads inactive and put the addressed
radio into power-down. There is no payload command or arbitrary channel, power or
duration. This proves configured settings and functional reception only—not
radiated power, sensitivity, range, calibrated frequency or instrumented RF silence.

## Implemented nRF24 positive scenario

`tests/hil/scenarios/nrf24-carrier-positive.json`:

1. opens `Home → 2.4 GHz → Find signal` through public Actions;
2. proves an ambient calibrated `not found` result while all three product nRF24
   modules are active and RX-only;
3. admits board-02 for the fixed channel-42 carrier and requires the product to find
   2,442 MHz / nearest Wi-Fi channel 7 above its existing response threshold;
4. captures ambient, found and final TFT states;
5. requires automatic fixture completion/power-down, stops the receiver and returns
   the product to Home/lease 0 with zero TX/storage side effects.

The scenario is gate-eligible only after the physical result is retained. Until then
it is an implemented test contract, not accepted RF evidence.

The first physical attempt with fixture `0.2.0` failed safe before emission and
exposed a real wrong-slot error: preserved 0.x hardware code identifies slots 2/3 as
populated and slot 1 as unpopulated/PN532-reserved. Corrected slot-2 fixture `0.2.1`
also rejected start before CE HIGH, therefore that finding was not the complete root
cause. Both records retain zero emission/duration, inactive/powered-down fixture and
product Home/lease 0: [0.2.0](../../tests/hil/evidence/board-01-nrf24-fixture-0.2.0-failed.json),
[0.2.1](../../tests/hil/evidence/board-01-nrf24-fixture-0.2.1-failed.json).
Fixture `0.2.2` adds exact CE-low/PWR_DOWN STATUS, CONFIG, RF_CH and RF_SETUP read-back
telemetry. Its [physical short regression](../../tests/hil/evidence/board-01-nrf24-fixture-0.2.2-failed.json)
retained `0/0/0/0` and `channel_readback_mismatch` on board-02 slot 2 with zero
emissions and safe cleanup. The next diagnostic inventories every slot and both legacy
SPI data-pin orientations while CE remains LOW. The non-gate regression must pass
before the full scenario may be retried.

Fixture `0.2.3` implemented that inventory. Its retained physical response reports
primary STATUS/CONFIG/RF_CH/RF_SETUP arrays all zero, swapped arrays all `0xFF`, masks
`0/0` and `ce_high_events=0` across board-02. The run remains failed-safe because the
new response omitted generic fixture fields `session_id` and `nrf_powered_down`.
Source-bound fixture `0.2.4` fixes that protocol and passes the two-step diagnostic.
CC1101 on the same bus also returns invalid identity `status/part/version = 0/0/0`
on the documented orientation and no-ready/`0xFF` on the swapped orientation. With
all three nRF identities still zero/`0xFF`, no CE-high event, no emission and clean
terminal states on both boards, the evidence supports an electrically unavailable
whole detachable RF shield rather than an nRF-only fault. Photos subsequently prove
a real 2×10 socket/header connection, not pogo contacts. A full powered-off
disassembly/reassembly did not change the identities; RF emission remains
unauthorized:
[0.2.3 inventory](../../tests/hil/evidence/board-02-nrf24-inventory-0.2.3-failed.json),
[0.2.4 shared-shield identity](../../tests/hil/evidence/board-02-rf-shield-inventory-0.2.4.json).

The independent same-image cross-check removes the principal diagnostic-firmware
ambiguity. Exact product `0.81.0` and firmware hash `2d0bc0cf…8379` previously detect
two nRF identities `14/8/2/15` and CC1101 version `20` on board-01. Freshly flashed on
board-02, that identical image completes the same bounded eight nRF plus two CC reads
but returns zero for both nRF identities and CC1101 version. The run performs zero
TX commands and CE-high events, leaves the buzzer inactive, and ends Home/lease 0.
This supports a board-02 shared rail/SPI/connector or undocumented clone-pinout fault
rather than fixture-specific code. The exact same `0.81.0` image remains on board-02
and a no-flash rerun after reassembly reproduces zero identities with the same bounded
8+2 reads, zero TX/CE-high events and Home/lease-0 cleanup. Upstream v2 schematics,
BOM and source confirm that Leshy uses the exact stock pinout and that all four
receivers share direct 3.3 V and SPI. Comparative measurements then found approximately
4.35/3.2 V on working board-01 and 4.7/3.3 V on board-02. Exact 0.130 sampled shared
MISO/GPIO13 32 times under each internal pull and issued only four CE-low nRF NOPs:
board-01 was HIGH 32/32 with STATUS `0x0E`, while board-02 was LOW 0/32 with STATUS
`0x00` both before and after a powered-off reseat. Rail absence and a casual connector
contact are no longer supported. Powered-off MISO-to-ground resistance is 23 kΩ on
board-02 versus 32 kΩ on board-01, rejecting a hard passive short. The next safe
evidence is the same exact pull characterization on isolated board-02 main hardware:
following both pulls assigns the powered clamp to the RF carrier; LOW under both pulls
assigns it to main-board routing or ESP GPIO13.
Do not cross-swap shields or emit before localization:
[same-image cross-check](../../tests/hil/evidence/board-02-shield-receiver-crosscheck-0.81.json),
[variant/reassembly evidence](../../tests/hil/evidence/board-02-hardware-variant-20260823.json),
[MISO characterization](../../tests/hil/evidence/board-02-rf-bus-characterization-0.130.json).

Official stock v1.6 was used once as bounded manual corroboration after retaining a
full clone flash backup: internal Wi-Fi and BLE worked while the external 2.4 GHz
scanner remained blank. It did not provide a machine-readable receiver identity and
was replaced by exact Leshy 0.130. Stock remains inadmissible for automated diagnostic
or fixture work because its source contains maximum-power nRF24 constant-carrier paths,
the observed modules have external PA/LNA devices and radiated power is unmeasured.

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
  --output work/outputs/ir-nec-positive-0.129 \
  --profile-fixture-read-only \
  --declare-standard-v2-no-extensions \
  --declare-antennas-attached
```

The corresponding bounded nRF24 run uses the same admission and cleanup path:

```sh
tools/run_nrf24_two_board_hil.py \
  --candidate-port /dev/cu.CANDIDATE \
  --fixture-port /dev/cu.FIXTURE \
  --expected-cid FE343253440000002000000055019CB7 \
  --output work/outputs/nrf24-carrier-positive-0.129 \
  --fixture-profile work/fixture-profile.json
```

An already accepted profile can instead be passed with `--fixture-profile`. Exact
already-flashed bytes can be reused only through the explicit
`--reuse-exact-candidate-flash` and `--reuse-exact-fixture-flash` options; normal
operation flashes both exact images. The raw passing run is subsequently admitted
to tracked evidence by `hil_evidence.py`, which independently verifies fixture
profile/source/image identity and terminal inactive outputs.

## Current evidence boundary

Source commit `149e4ef37a650953b7335885c118824ed632fa16` binds exact product 0.129,
fixture 0.1.0, the runner and scenario. Board-02 profile proves fixture ID
`00009070690D15E0`, ESP32-S3/16 MB, the explicitly declared standard v2 assembly and
zero profiling writes. The passing run reuses exact already-flashed image hashes,
performs one 68.424 ms fixed NEC emission, captures/decodes 67 pulses on board-01,
advances catalog generation 97→98 after explicit Save, cold-reopens the item and
compares live/Library CSV byte-for-byte. Both boards finish inactive and product
owner/lease is `none`/`0`.

This closes the declared IR positive boundary only. ADR-006 authorizes the single
bounded nRF24 vector in committed fixture source, but no physical nRF24 claim is
accepted until its exact two-board evidence passes and is retained. Sub-GHz fixture
transmission remains unauthorized pending a separate region/band and vector contract.
