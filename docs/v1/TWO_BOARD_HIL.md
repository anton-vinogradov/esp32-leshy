# Two-board HIL and declarative scenarios

*Read in: **English** · [Русский](TWO_BOARD_HIL.ru.md)*

Status: **accepted S5 verification architecture; board-02 is purchased but not yet
connected or profiled**.

## Roles

| Role | Firmware | Authority |
|---|---|---|
| `candidate` / board-01 | exact product candidate | device under test; production code remains passive/RX-only unless a product capability explicitly authorizes otherwise |
| `fixture` / board-02 | separate bounded HIL fixture image | creates a known stimulus only after a source-bound host session arms one named operation |
| host | `run_hil_scenario.py` | identifies roles, flashes authorized images, sequences Actions/commands, captures TFT GRAM, checks side effects and retains evidence |

The fixture is not a second copy of the product blindly transmitting. Its firmware
and permissions are separate so a test-only transmitter cannot leak into a product
build.

## Declarative execution

Scenarios use `leshy.hil.scenario.v1`. A scenario declares device roles, public UI
Actions, diagnostic queries, quiet timing windows, screenshots, exact expectations,
numeric checks, final invariants and honest limitations. The common runner supports
one or two serial devices and produces `leshy.hil.scenario_run.v1`; the common
evidence tool binds the scenario, runner and exact candidate commits, hashes the
firmware/app/factory/map, indexes every retained artifact, and independently checks
CID, storage, heap, input, safe outputs, cleanup and final lease.

The first accepted migration is
`tests/hil/scenarios/infrared-passive-no-signal.json`: exact 0.104 runs 19 declared
steps, takes seven TFT captures and proves the physical GPIO21 receive/no-signal path
without a fixture.

## Fixture safety contract

The future board-02 image must satisfy all of these rules:

- boot with every RF/IR output inactive and never auto-arm;
- accept only a named, bounded, source-bound test vector and expire its session;
- require exact fixture identity and firmware hash before stimulus;
- expose start/stop counters, duration and final inactive-pad evidence;
- stop on timeout, serial loss, candidate failure, watchdog or explicit panic;
- allow IR first; Sub-GHz/2.4 GHz transmission additionally requires an accepted
  band/region plan and appropriate physical attenuation or separation;
- never carry user replay data into repository evidence.

Release signing remains a GitHub-controlled process; no permanent signing key is
stored on the host or either fixture. Local HIL uses hashes and exact commits, then
the GitHub release workflow signs only bytes that passed the release gate.

## Bring-up boundary for board-02

When connected, board-02 receives a read-only identity/profile pass before any
fixture firmware or output test. We retain its USB identity, board profile, flash and
shield inventory, then create the role registry used by the common runner. Until
that happens all two-board positive-signal claims remain false.

The first positive scenario will be IR NEC: board-01 enters the timing-critical
receive window, board-02 emits one fixed bounded NEC vector, board-01 must decode,
explicitly save, cold-reopen in Library and export byte-exact CSV. The same pattern
then applies to Sub-GHz with the additional regulatory controls above.
