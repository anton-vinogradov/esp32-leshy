# ADR-002 — capability and resource policy

*Read in: **English** · [Русский](ADR-002-resource-policy.ru.md)*

- **Status:** accepted
- **Date:** 2026-08-16
- **Requirements:** PR-001, PR-002, PR-009, PR-013, PR-014; NFR-002, NFR-006
- **Risks:** R-003, R-004, R-005, R-008, R-009
- **Stage:** S1 decision; kernel invariant from S2

## Context

ESP32-DIV has physical pin conflicts and devices sharing SPI, UART, and GPIO domains.
A capability bit cannot express evidence, conflict, ownership, cancellation, or
physical TX state. Library `begin()`/`end()` ordering is not a coexistence policy.

## Decision

1. `HardwareInventory` stores `declared`, `detected`, `available`, `conflicted`,
   `fault`, or `unknown` plus evidence/reason. Only `available` can start an Action.
2. `ResourceBroker` is the single ownership authority. Acquisition of a complete
   resource set is atomic and allocation-free; partial acquisition never escapes.
3. Resources include physical domains and logical devices. The broad domain lease
   is acquired before its device lease. S2 serializes broker mutation in the kernel.
4. Shared buses are exclusive operation leases by default. Transaction sharing is
   introduced only through a bus service after HW-T03/HW-T05/RB-07 evidence.
5. Each operation has an owner and cancel path. AppRuntime releases all owner leases
   after failed start, Back/cancel, stop, worker failure, and teardown.
6. TX leases additionally have a finite deadline and registered idempotent hardware
   stop. Panic/expiry invokes hardware stop before ownership release or UI teardown.
7. Ambiguous assembly/pin state fails closed. Code never probes contested output
   modes to discover which device may be attached.

## Alternatives

- **Per-driver mutexes:** rejected; they cannot atomically cover several domains.
- **Capability bitmask only:** retained only as a derived compatibility view, never
  as evidence or authorization.
- **Automatic preemption:** rejected for normal actions; explicit panic/expiry is the
  only safety preemption path in the initial policy.

## Consequences

Some theoretically concurrent features remain unavailable until measured. This is
intentional. Drivers become simpler, conflicts are explainable before start, and
cleanup has one enforceable owner. The current feasibility broker demonstrates
atomic acquisition but is not the S2 implementation.

## Verification

- exhaustive/property tests for atomic acquire/release/conflict reporting;
- failed start/cancel/Back/worker-crash tests end with no owner leaks;
- simulated and HIL contested-profile tests perform no output probe;
- shared-bus HIL meets RB-07 before concurrency is enabled;
- every TX stop cause passes WF-05 and an independent physical trace.
