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
5. Два Sub-GHz vector используют только 433,920 МГц, минимальное проверенное значение
   PATABLE CC1101 `0x1D` (примерно −15 dBm), fixed packet mode 60 bytes и fixed
   payload. OOK выдаёт четыре packet с gap 4 ms, FSK — один packet с ограниченным
   числом edges. Чип возвращается в IDLE после каждого packet, общая измеренная
   emission не может превышать 250 ms, PATABLE очищается, FIFO сбрасывается. Команд
   произвольных frequency, power, payload, modulation, packet count или duration нет.
6. Completion, timeout, mismatch, parser failure, explicit stop, panic и Task-WDT
   опускают CE и переводят radio в power-down. Runner принимает результат только
   после чтения terminal facts. Уже допущенный CC1101 packet при Task-WDT аппаратно
   конечен и auto-idle; ISR запрещает следующие packets, а normal cleanup явно
   выполняет IDLE, очищает PA и TX FIFO.
7. Product candidate остаётся RX-only и слушает всеми обнаруженными антеннами.
   Полномочие fixture не создаёт product TX authority.

## Альтернативы

- только ambient receiver evidence;
- произвольные test transmitter commands;
- diagnostic TX mode внутри product;
- только внешнее calibrated RF equipment.

Ambient evidence не проверяет positive detection; arbitrary/product TX расширяет
риск. Лабораторные приборы остаются правильным средством для calibrated RF claims,
но не нужны для этого binary functional checkpoint.

## Последствия

- Отдельно profiled и электрически qualified собственная board — bounded signal
  source, а не второй product candidate, пока на ней установлен fixture image.
- Неисправный клон board-02 явно исключён: shared RF bus не даёт plausible receiver
  identity, поэтому ему нельзя выдавать никакой RF vector.
- Software bounds уменьшают риск, но не являются независимым rail kill, RF shield
  или calibrated power measurement.
- Evidence может утверждать exact register settings и успешное physical detection,
  но не radiated power, sensitivity, distance или RF silence.
- Каждый новый vector или band требует отдельного явного контракта и tests.

## Проверка

- native tests отвергают wrong session/vector, repeat и duration overflow;
- source guard отвергает general transmit paths и drift контракта;
- fixture build и scenario runner связаны с exact committed source и images;
- nRF two-board HIL доказывает ambient `not found` → bounded fixture active → exact
  channel 42 найден product на трёх receivers → обе платы inactive и product lease 0;
- отдельные OOK и FSK scenarios доказывают known signal 433,920 МГц → public
  receive-only Capture → explicit Save → cold Library reopen → byte-exact CSV при
  zero product TX и terminal telemetry fixture IDLE/PA-clear/FIFO-clear;
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
runner остаётся test failure. Source-bound `0.2.4` исправляет contract и проходит
диагностику, но identity CC1101 на shared bus тоже invalid: `0/0/0` на documented bus
и no-ready/`0xFF` на swapped bus. Сохранённый
[`0.2.4 evidence`](../../../tests/hil/evidence/board-02-rf-shield-inventory-0.2.4.json)
поэтому указывает на электрическую недоступность всего съёмного shield, не разрешает
RF emission и требует powered-off hardware diagnosis до bounded carrier regression.

Независимый [same-image cross-check `0.81.0`](../../../tests/hil/evidence/board-02-shield-receiver-crosscheck-0.81.json)
затем воспроизводит zero identities на board-02 тем же exact product image и driver,
которые ранее нашли все три приёмника на board-01. Bounded 8+2 SPI reads, zero
TX/CE-high events и terminal Home/lease 0 делают fixture-specific code маловероятным;
полная disassembly/reassembly connector 2×10 без питания и no-flash same-image rerun
теперь воспроизводят fault. Upstream v2 pin definitions совпадают с Leshy, а все
receiver используют прямые общие 3,3 В/SPI. Exact passive `0.130.0` затем
измеряет valid idle rails, держит все CE LOW, samples MISO под обоими pull и
тактирует только nRF NOP: board-01 показывает HIGH 32/32 с STATUS `0x0E`, а
board-02 остаётся LOW 0/32 с STATUS `0x00` до и после ещё одного reseat без
питания. Powered-off MISO→GND равно 23 кОм на board-02 против 32 кОм на
board-01, что отвергает hard passive short и оставляет powered/logic-dependent
clamp. До разрешения carrier start этим ADR обязательны та же exact
pull-characterization на isolated main hardware board-02, localization на RF carrier
или main board/ESP GPIO13 и последующая plausible same-image receiver identity.
Cross-swap shields и stock-firmware diagnosis не допускаются.

Fixture `0.3.0-subghz-safe` добавляет два проверенных CC1101 vector и их declarative
gate-eligible scenarios. Пока это только реализованный и build-checked contract: он
не отменяет admission по read-only profile и plausible identity и не делает
неисправный клон разрешённым source. Physical OOK/FSK claims остаются открыты до
прогона обоих exact scenarios на отдельной qualified board и независимой проверки
сохранённого evidence.
