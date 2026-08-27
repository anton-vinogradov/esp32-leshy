# ESP32-Leshy 1.x — product review каталога 1.0

*Read in: [English](CAPABILITY_REVIEW.md) · **Русский***

Дата: 17 августа 2026 года. Результат: **product scope coherent; catalog baseline
reviewed; PRD technical baseline принят `E-GATE-001`**.

Дополнение по competitor features: **27 августа 2026 года**.

## Входы и правила проверки

Review сопоставляет [Vision](VISION.ru.md), J-01…J-06 и PR/NFR из
[PRD](PRODUCT_REQUIREMENTS.ru.md), WF-01…WF-05, hardware envelope, delivery stages и
явные исключения с каждой строкой [каталога](CAPABILITY_CATALOG.ru.md).

Возможность сохраняется в 1.0, только если у неё есть разрешённый user outcome,
primary owner в IA, requirement, stage, error/cancel path и проверяемый result. Пункт
меню 0.x/конкурента сам по себе не является основанием. Conditional hardware не
исчезает из scope, но обязано fail closed при отсутствии assembly/evidence.

## Найденные и закрытые пробелы

| Finding | Почему общих строк было недостаточно | Исправление baseline |
|---|---|---|
| CRV-01 Wi-Fi capture | scan и общий PCAP export не обещали реальный packet/channel workflow, важный для parity и evidence | CAP-042 + PR-015: passive bounded monitor/Capture, PCAP, drops, no hidden TX |
| CRV-02 Screenshot | Vision называл screenshots, но каталог не давал user Action, provenance и Library path | CAP-043 + PR-015: real-TFT screenshot как evidence artifact |
| CRV-03 Offline enrichment | Target обещал identities, но не version/provenance локальных OUI/BLE/protocol data | CAP-044 + PR-019: raw facts всегда доступны, database только обогащает |
| CRV-04 Feedback hardware | Settings упоминал sound, но не было владельца GPIO2/WS2812, quiet mode или safe idle | CAP-045 + PR-016: единый service, idle LOW, bounded cues, non-color fallback |
| CRV-05 Connectivity/secrets | OTA/companion требовали сеть, но setup, offline degradation и secret boundary не были user capability | CAP-046 + PR-017: scoped Wi-Fi/USB, no secret export, Survey/Library offline |
| CRV-06 Data maintenance | update recovery не равен backup/restore пользовательских данных и factory reset | CAP-047 + PR-018: preview/checksum/cancel/recovery и immutable raw protection |

## Проверка пересечений

- CAP-009/023/042 не дублируются: Session — контекст, Capture — immutable artifact,
  Wi-Fi monitor — конкретный passive producer.
- CAP-026/027 не дублируются: первая строка задаёт форматы, вторая — безопасные
  import/export transports и parsers.
- CAP-029…031 и CAP-034…036 разделяют capture/read от Lab replay/write; это
  обязательная safety boundary, а не два меню одной функции.
- CAP-007 и CAP-047 разделяют firmware recovery и user-data maintenance.
- CAP-017/044 разделяют измеренную локализацию и справочное enrichment; database не
  влияет на RSSI evidence.

## Coverage outcome

| Проверка | Результат |
|---|---|
| Jobs | J-01…J-06 имеют capabilities и WF owner |
| Requirements | PR-001…PR-019 и NFR-001…NFR-010 присутствуют в stage/traceability; PRD принят как baseline 1.0, verification остаётся поэтапной |
| Information architecture | Все CAP-001…CAP-047 имеют primary owner в UX-S01 six-task Home |
| Error/cancel behavior | UX-02 задаёт unavailable/loading/degraded/error/confirm/success и cleanup для каждого screen family |
| Hardware conditionals | RF shield, GPS, PN532, sound HW-T09 не превращаются в unconditional availability |
| Safety | Passive Capture отделён от Lab; любой TX имеет scope/confirm/deadline/Stop/Panic |
| Explicit exclusions | Cloud/default telemetry, executable marketplace, broad boards и attack-count parity остаются после 1.0 |

## Verdict

Product review принимает CAP-001…CAP-047 как полную рабочую границу 1.0. Новая
крупная возможность после этого review требует отдельного `J/PR/CAP`, risk impact и
stage proposal; формулировки и acceptance могут уточняться без скрытого расширения
scope.

Более поздний [пофункциональный аудит конкурентов](COMPETITIVE_ANALYSIS.ru.md#пофункциональный-аудит-паритета)
нашёл девять полезных или стратегически значимых семейств (`CF-001…CF-009`), которые
baseline оставляет неявными или не содержит. Поэтому «полная рабочая граница»
означает полноту для согласованных 17 августа jobs/requirements, **но не** полный
competitor-feature parity. Ни один candidate не повышается скрытно до `CAP-*`:
принятие требует той же product/safety traceability, что и любое изменение scope.
Сознательно disruptive функции и функции для отсутствующего железа остаются
explicit non-goals, а не скрытыми пропусками.

Scope review вместе с constrained hardware/resource evidence закрывает S1 через
`E-GATE-001`. Это не объявляет возможности реализованными или verified: такие статусы
дают только соответствующие S2…S8 evidence и gates.
