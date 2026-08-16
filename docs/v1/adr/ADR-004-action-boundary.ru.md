# ADR-004 — единая typed Action boundary

*Читать на: [English](ADR-004-action-boundary.md) · **Русский***

- **Статус:** accepted
- **Дата:** 2026-08-16
- **Requirements:** PR-002, PR-009, PR-012, PR-013; NFR-002, NFR-003, NFR-006
- **Risks:** R-008, R-009, R-014, R-016
- **Этап:** решение S1; основа dispatcher в S2

## Контекст

В 0.x UI и serial paths могут дублировать teardown и вызывать feature code по-разному.
1.x требует одинаковые operation semantics для device UI, tests, local CLI и
companion без direct driver access или расширенных permissions транспорта.

## Решение

1. Typed `Action` — единственная product-level точка входа operation. Descriptor
   содержит stable ID/version, request/result/event schemas, required capabilities/
   resources, safety class, permissions, timeout/deadline и cancel semantics.
2. UI, CLI, companion, automation и tests посылают один request единому Action
   dispatcher. Views отображают state/events и не вызывают driver/service teardown.
3. Порядок dispatcher: decode/bounds → authenticate transport при необходимости →
   permission/policy → capability → atomic resources → start. Failure до start не
   имеет hardware side effect и возвращает stable structured reason.
4. Invocation имеет ID, owner, bounded event queue, progress и idempotent cancel.
   Completion terminal; retry — новый invocation без explicit idempotency key.
5. Permissions local companion не шире device session. Transport schemas — versioned
   adapters Action schema, а не ещё один API.
6. Active Actions дополнительно требуют Lab context, SafetyPolicy approval, explicit
   confirmation, finite TX deadline, visible stop и physical-stop path ADR-002.
7. Audit records содержат action ID, policy result, timing, terminal reason и
   redacted parameters; credentials/captured payload исключены по умолчанию.

## Альтернативы

- **Раздельные UI/Web/serial handlers:** rejected из-за drift behavior/cleanup.
- **Driver APIs через RPC:** rejected — обход capability/resource/safety/data contracts.
- **Untyped command string:** rejected по bounds, versioning и testability.

## Последствия

Dispatcher становится узкой SDK boundary и integration-test seam. View change требует
Action только при изменении domain state, не для local navigation. Transport/auth
могут развиваться без изменения operation semantics. Stable Action IDs становятся
compatibility commitments с schema tests и superseding ADR.

## Проверка

- contract tests воспроизводят одни fixtures через UI adapter, CLI и companion;
- permission/capability/resource failures дают ноль driver starts;
- cancellation, Back, timeout, worker error и duplicate terminal events не оставляют
  workers/resources и проходят NFR-002/003;
- fuzz/bounds tests покрывают каждый transport decoder;
- active Actions проходят WF-05 и independent physical-stop HIL.
