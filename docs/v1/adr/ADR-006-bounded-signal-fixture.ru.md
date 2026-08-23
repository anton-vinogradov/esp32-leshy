# ADR-006: source-bound fixture ограниченных сигналов

*Читать на: [English](ADR-006-bounded-signal-fixture.md) · **Русский***

- status: `accepted`
- date: 2026-08-23
- requirements: PR-009, PR-014, NFR-001, NFR-002, NFR-005, NFR-006
- risks: R-018
- stage: S5

## Контекст

Пассивные проверки приёмников доказывают безопасность и живость product paths, но не
доказывают обнаружение, capture и корректную атрибуцию известного физического
сигнала. Такой сигнал может дать второй ESP32-DIV. General-purpose transmitter
добавил бы ненужные полномочия, регуляторную неоднозначность и риск оставить output
активным после сбоя теста.

## Решение

Использовать отдельный test-only image `leshy_fixture` с намеренно узким интерфейсом:

1. Он загружается со всеми controlled outputs inactive и всеми nRF24 в power-down.
2. Host связывает случайную одноразовую session с exact hash image fixture и fixture
   ID из efuse; admission истекает через пять секунд.
3. Разрешены только проверенные fixed vectors. Нет произвольных payload, frequency,
   duration, replay, Wi-Fi, BLE, storage или product-side TX command.
4. Первый RF vector использует populated slot 2 shield (CSN48/CE47), канал 42 /
   2 442 МГц, минимальную настройку
   мощности чипа −18 dBm и двухсекундную непрерывную немодулированную несущую. Hard
   software ceiling — 2,5 секунды.
5. Completion, timeout, mismatch, parser failure, explicit stop, panic и Task-WDT
   опускают CE и переводят radio в power-down. Runner принимает результат только
   после чтения этих terminal facts.
6. Product candidate остаётся RX-only и слушает всеми обнаруженными антеннами.
   Полномочие fixture не создаёт product TX authority и не распространяется на
   Sub-GHz.

## Альтернативы

- только ambient receiver evidence;
- произвольные test transmitter commands;
- diagnostic TX mode внутри product;
- только внешнее calibrated RF equipment.

Ambient evidence не проверяет positive detection; arbitrary/product TX расширяет
риск. Лабораторные приборы остаются правильным средством для calibrated RF claims,
но не нужны для этого binary functional checkpoint.

## Последствия

- Пока установлен fixture image, board-02 — bounded signal source, а не второй
  product candidate.
- Software bounds уменьшают риск, но не являются независимым rail kill, RF shield
  или calibrated power measurement.
- Evidence может утверждать exact register settings и успешное physical detection,
  но не radiated power, sensitivity, distance или RF silence.
- Каждый новый vector или band требует отдельного явного контракта и tests.

## Проверка

- native tests отвергают wrong session/vector, repeat и duration overflow;
- source guard отвергает general transmit paths и drift контракта;
- fixture build и scenario runner связаны с exact committed source и images;
- two-board HIL доказывает ambient `not found` → bounded fixture active → exact channel
  42 найден product на трёх receivers → обе платы inactive и product lease 0;
- intentional identity, state, duration или cleanup mismatch приводит к fail closed.

Первый [physical attempt `0.2.0`](../../../tests/hil/evidence/board-01-nrf24-fixture-0.2.0-failed.json)
намеренно сохранён как negative evidence: он обращался
к unpopulated/PN532-reserved slot 1 и отверг carrier после register read-back. `0.2.1`
связал vector с populated slot 2 из сохранённой implementation 0.x, но его
[короткий regression](../../../tests/hil/evidence/board-01-nrf24-fixture-0.2.1-failed.json)
тоже отверг start до CE HIGH. Выбор slot был дефектом, но не полной root cause;
[`0.2.2`](../../../tests/hil/evidence/board-01-nrf24-fixture-0.2.2-failed.json)
добавляет exact powered-down register telemetry и локализует следующую границу до
некорректного полностью нулевого SPI read-back slot 2. Следующая диагностика обязана
инвентаризировать все slots и обе legacy-ориентации data pins при всех CE LOW до fix.
Сохранённый [`0.2.3 inventory`](../../../tests/hil/evidence/board-02-nrf24-inventory-0.2.3-failed.json)
не нашёл plausible nRF ни в одной orientation и не поднял CE. Пропуск fields generic
runner остаётся test failure; следующая диагностика добавляет identity CC1101 на
shared bus до классификации shield board-02.
