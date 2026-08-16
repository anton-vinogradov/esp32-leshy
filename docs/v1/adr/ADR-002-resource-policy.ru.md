# ADR-002 — policy capabilities и resources

*Читать на: [English](ADR-002-resource-policy.md) · **Русский***

- **Статус:** accepted
- **Дата:** 2026-08-16
- **Requirements:** PR-001, PR-002, PR-009, PR-013, PR-014; NFR-002, NFR-006
- **Risks:** R-003, R-004, R-005, R-008, R-009
- **Этап:** решение S1; kernel invariant с S2

## Контекст

ESP32-DIV имеет физические pin conflicts и устройства с общими SPI/UART/GPIO
domains. Capability bit не выражает evidence, conflict, ownership, cancellation или
physical TX state. Порядок library `begin()`/`end()` не является coexistence policy.

## Решение

1. `HardwareInventory` хранит `declared`, `detected`, `available`, `conflicted`,
   `fault` или `unknown` плюс evidence/reason. Action запускается только для
   `available`.
2. `ResourceBroker` — единственный ownership authority. Полный resource set
   получается атомарно и без allocations; partial acquisition наружу не выходит.
3. Resources включают physical domains и logical devices. Broad domain lease
   берётся до device lease. В S2 mutation broker сериализуется kernel-ом.
4. Shared buses по умолчанию дают exclusive operation lease. Transaction sharing
   появляется только через bus service после evidence HW-T03/HW-T05/RB-07.
5. У каждой operation есть owner и cancel path. AppRuntime освобождает все leases
   owner после failed start, Back/cancel, stop, worker failure и teardown.
6. TX lease дополнительно имеет finite deadline и registered idempotent hardware
   stop. Panic/expiry вызывает hardware stop до release ownership или teardown UI.
7. Ambiguous assembly/pin state fail-closed. Код не пробует contested output modes
   для определения подключённого устройства.

## Альтернативы

- **Per-driver mutexes:** rejected — не покрывают несколько domains атомарно.
- **Только capability bitmask:** остаётся лишь derived compatibility view, не
  evidence и не authorization.
- **Automatic preemption:** rejected для обычных actions; в initial policy только
  explicit panic/expiry является safety preemption.

## Последствия

Теоретически concurrent features могут оставаться unavailable до measurements. Это
намеренно. Drivers проще, conflict объясняется до start, cleanup имеет одного owner.
Текущий feasibility broker показывает atomic acquisition, но не является S2 code.

## Проверка

- exhaustive/property tests atomic acquire/release/conflict reporting;
- failed start/cancel/Back/worker-crash оставляют ноль owner leaks;
- simulated/HIL contested profiles не выполняют output probe;
- shared-bus HIL проходит RB-07 до включения concurrency;
- каждая причина TX stop проходит WF-05 и independent physical trace.
