# ADR-006: source-bound bounded-signal fixture

*Read in: **English** · [Русский](ADR-006-bounded-signal-fixture.ru.md)*

- status: `accepted`
- date: 2026-08-23
- requirements: PR-009, PR-014, NFR-001, NFR-002, NFR-005, NFR-006
- risks: R-018
- stage: S5

## Context

Passive receiver checks prove that product paths are safe and alive, but cannot prove
that a known physical signal is found, captured and attributed correctly. A second
ESP32-DIV can provide that signal. Turning it into a general transmitter would add
unnecessary capability, regulatory ambiguity and a failure mode in which a test leaves
an output active.

## Decision

Use a separate, test-only `leshy_fixture` image with a deliberately non-general
command surface:

1. It boots with all controlled outputs inactive and every nRF24 powered down.
2. The host must bind a random one-use session to the exact fixture image hash and
   efuse-derived fixture ID; admission expires after five seconds.
3. Only source-reviewed fixed vectors exist. There is no arbitrary payload, frequency,
   duration, replay, Wi-Fi, BLE, storage or product-side transmitter command.
4. The first RF vector uses one nRF24 module, channel 42 / 2,442 MHz, chip minimum
   power setting −18 dBm and a two-second continuous unmodulated carrier. Its hard
   software ceiling is 2.5 seconds.
5. Completion, timeout, mismatch, parser failure, explicit stop, panic and Task-WDT
   drop CE and power the radio down. The runner accepts the result only after reading
   those terminal facts back.
6. The candidate product remains RX-only and listens on every detected antenna. The
   fixture permission does not create product TX authority and does not generalize to
   Sub-GHz.

## Alternatives

- ambient-only receiver evidence;
- arbitrary test transmitter commands;
- a product diagnostic TX mode;
- external calibrated RF equipment only.

Ambient evidence misses positive detection; arbitrary/product TX broadens risk. Lab
equipment remains the correct tool for calibrated RF claims but is not required for
this binary functional checkpoint.

## Consequences

- Board-02 is a bounded signal source, not a second product candidate while the
  fixture image is installed.
- Software bounds reduce exposure but are not an independent rail kill, RF shield or
  calibrated power measurement.
- Evidence may claim exact register settings and successful physical detection only;
  it may not claim radiated power, sensitivity, distance or RF silence.
- Each new vector or band requires an explicit reviewed contract and tests.

## Verification

- native tests reject wrong session/vector, repeat and duration overflow;
- a source guard rejects general transmit paths and contract drift;
- fixture build and scenario runner are pinned to exact committed source and images;
- two-board HIL proves ambient `not found` → bounded fixture active → exact channel 42
  found on the product's three receivers → both boards inactive and product lease 0;
- intentional identity, state, duration or cleanup mismatch fails closed.
