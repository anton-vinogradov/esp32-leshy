# ADR-004 — one typed Action boundary

*Read in: **English** · [Русский](ADR-004-action-boundary.ru.md)*

- **Status:** accepted
- **Date:** 2026-08-16
- **Requirements:** PR-002, PR-009, PR-012, PR-013; NFR-002, NFR-003, NFR-006
- **Risks:** R-008, R-009, R-014, R-016
- **Stage:** S1 decision; dispatcher foundation in S2

## Context

0.x UI and serial paths can duplicate teardown and call feature code differently.
1.x needs the same operation semantics for device UI, tests, local CLI, and companion
without giving a remote transport direct driver access or wider permissions.

## Decision

1. A typed `Action` is the only product-level operation entry point. Its descriptor
   has stable ID/version, request/result/event schemas, required capabilities and
   resources, safety class, permissions, timeout/deadline, and cancel semantics.
2. UI, CLI, companion, automation, and tests submit the same request to one Action
   dispatcher. Views render state/events and never call a driver or service teardown.
3. Dispatcher order is: decode/bounds → authenticate transport where applicable →
   permission/policy → capability → atomic resources → start. A failure before start
   has no hardware side effect and returns a stable structured reason.
4. Each invocation has an ID, owner, bounded event queue, progress, and idempotent
   cancel. Completion is terminal; retry is a new invocation unless an Action
   explicitly defines an idempotency key.
5. Local companion permissions are never broader than the device session. Transport
   schemas are versioned adapters around the Action schema; they are not another API.
6. Active Actions additionally require Lab context, SafetyPolicy approval, explicit
   confirmation, finite TX deadline, visible stop, and ADR-002 physical-stop path.
7. Audit records contain action ID, policy result, timing, terminal reason, and
   redacted parameters; credentials and captured payload are excluded by default.

## Alternatives

- **Separate UI/Web/serial handlers:** rejected because behavior and cleanup drift.
- **Expose driver APIs through RPC:** rejected because it bypasses capability,
  resource, safety, and data contracts.
- **One untyped command string:** rejected for bounds, versioning, and testability.

## Consequences

The dispatcher is a narrow SDK boundary and a natural integration-test seam. Simple
view changes may require explicit Actions only when they mutate domain state, not for
local navigation. Transport/auth details can evolve without changing operation
semantics. Stable Action IDs become compatibility commitments governed by schema
tests and superseding ADRs.

## Verification

- contract tests replay identical fixtures through UI adapter, CLI, and companion;
- permission/capability/resource failures produce zero driver starts;
- cancellation, Back, timeout, worker error, and duplicate terminal events leak no
  workers/resources and meet NFR-002/003;
- fuzz/bounds tests cover every transport decoder;
- active Actions pass WF-05 and independent physical-stop HIL.
