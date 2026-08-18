# ESP32-Leshy 1.x — встроенный Self-Test

*Читать на: [English](SELF_TEST.md) · **Русский***

Статус: **принят product/UX contract; Quick/guided UI S2, registration завершённых
capabilities S3/S4, conditional identity check RF shield и первый active receive-only
RF execution физически приняты; остальные workflows Full/Guided продолжаются через
S4…S8**.

Self-Test — отдельное приложение в самом низу Home. Оно никогда не перехватывает
обычную загрузку. Один test engine используется владельцем устройства, полным
guided-прогоном и release HIL station; меняются invoker и доступные fixtures, но не
смысл проверки.

## Меню и режимы

```text
Home
└─ SELF-TEST
   ├─ QUICK
   └─ FULL / GUIDED
```

| Режим | Цель | Side effects по умолчанию | Завершение |
|---|---|---|---|
| `QUICK` | Ответить «устройство в целом исправно прямо сейчас?» | read-only; radios и пользовательские данные не затрагиваются; buzzer остаётся LOW | bounded автоматические проверки и экспортируемый отчёт |
| `FULL / GUIDED` | Проверить каждую применимую функцию прошивки и установленного устройства | preflight перечисляет записи, звук, radio, нужные media/fixtures и оценку времени; unsafe/unavailable проверки не стартуют | автоматические шаги и только неизбежные prompts: нажать физические кнопки или подтвердить звук/изображение |

Quick не запускается при boot. Загрузка только публикует факты для engine и сохраняет
обычный budget выхода в интерактивный экран.

## Один engine, два независимых судьи

Каждая проверка — versioned Action со стабильным ID, declared resources, timeout,
safety class, required fixture, cleanup rule и result schema. On-device app показывает
progress и сохраняет report. Release script вызывает те же Actions через machine
interface, но независимо проверяет candidate hashes, protocol ordering, framebuffer,
counters, leases и retained artifacts. Самоотчёта устройства недостаточно для
promotion релиза.

Результаты: `pass`, `fail`, `not_applicable`, `blocked`, `skipped` и `inconclusive`.
Модуль, отсутствующий в выбранном HardwareProfile, получает `not_applicable`, а не
ложный fail. Declared-модуль без доказательства получает `fail` или `inconclusive`,
но никогда не молчаливый pass.

## Семейства проверок

| Семейство | Quick | Full / Guided и release extension |
|---|---|---|
| build/runtime | версия, app identity, reset reason, heap, crash/watchdog record | restart recovery, leak/latency loops и endurance текущего Stage Demo |
| display/UI | TFT init и deterministic framebuffer CRC | color/geometry/text patterns, screenshot comparison, все обязательные UI states и Back paths |
| input | здоровье frontend/task/queue и idle raw value | prompt для каждой физической кнопки; release fixture может использовать actuator, а injected Actions отдельно проверяют navigation прошивки |
| feedback | GPIO2 configured LOW и quiet-mode state | bounded audible prompt при разрешении; release fixture может добавить electrical/acoustic observation |
| storage | media/profile identity и read-only recovery | bounded scratch write/verify/recovery только после явного preflight; user data не попадает в scratch namespace |
| radios | declared capability, driver/policy/lease readiness и отсутствие hidden start | passive receive workflows; active output только в authorized instrumented Lab fixture с deadline и physical-stop evidence |
| optional assemblies | profile declaration и conflict checks | применимые GPS/PN532/shield checks; отсутствующие assemblies дают `not_applicable` |
| product workflows | controller/schema prerequisites | автоматические Home-originated Survey/Library/export и другие stage-complete paths с final cleanup |

«Вся функциональность» означает: каждая применимая к выбранному board/assembly profile
функция выполняется или честно получает non-pass результат. Это не разрешает пробовать
неоднозначный pin, передавать без authorization, форматировать произвольный носитель
или считать отсутствие внешнего инструмента успехом.

## Контракт отчёта

Report содержит test-plan/schema version, firmware/app hashes, board/profile,
mode/invoker, start/end reason, result/evidence/duration каждой проверки, operator
prompts, ownership до/во время/после, heap/drop counters, side effects,
framebuffer/artifact hashes и final cleanup. Secrets, raw nearby identifiers и
невыбранные user data исключаются.

Back отменяет прогон на ближайшей safe boundary, сначала останавливает workers и
публикует partial report. Pass возможен, только если каждая required applicable
проверка прошла, неожиданных side effects нет, а final ownership равен zero.

## Реализация и использование в релизе

- **S2:** последний пункт Home, UI mode/preflight/result, Quick platform checks и
  skeleton машиночитаемого report.
- **S3…S7:** каждая завершённая capability регистрирует Full/Guided check, а её Stage
  Demo вызывает тот же Action.
- **S5:** все checks штатного hardware profile имеют physical evidence или явный
  conditional disposition.
- **S8:** release script прошивает exact bytes, выполняет полный применимый plan,
  независимо проверяет screenshots/report/artifact hashes и только затем разрешает
  promotion. Endurance и внешние power/RF fixtures остаются отдельными plan steps,
  но индексируются тем же report.

## Принятая реализация S2

Candidate `0.53.0-self-test-quick-measure` заложил последний пункт Home, menu
режимов, Full preflight, result screens, восемь стабильных Quick check IDs и
`leshy.self_test.report.v1`. На board-01 он прошёл все восемь Quick checks read-only
за 60 µs с zero radio/storage/buzzer side effects и final owner/lease `none`/`0`
(`E-HIL-077`). Первый physical attempt также обнаружил loop-task stack panic из-за
локального diagnostic buffer 3 KiB; failure сохранён, а исправленный shared bounded
workspace прошёл regression.

Candidate `0.57.0-ui-state-evidence-measure` переводит общий plan на version 2.
После preflight Full/Guided проводит пользователя или release driver через явные
карточки dialog/confirm, unavailable, degraded, error и running. Девять actual TFT
frames и их Action/state traces сохранены и machine-checked. Run проходит восемь
Quick checks плюс `full.ui.common_states`, затем намеренно возвращает blocked на
`full.capability.coverage`: 9/10 pass, 0 fail, 1 blocked, с zero
radio/storage/buzzer side effects и final owner/lease `none`/`0`
(`E-HIL-081`/`E-UX-007`). Это правильный текущий результат: незавершённые capability
checks S3…S7 не могут быть promoted ни device, ни host.

Exact committed candidate `0.58.0-stage-demo-s2-measure` принимает этот platform
slice через `E-AUTO-022`/`E-HIL-082`/`E-GATE-002`. Self-Test по-прежнему не
запускается при boot: он остаётся последним пунктом Home. Device открывает Quick и
Full/Guided через штатный five-key Action path, а `ui.state` публикует текущий
`self_test_visual_state`, чтобы release driver проверял то же semantic state, которое
видит пользователь. DEMO-S2 проходит 29 steps, девять TFT comparisons, Quick 8/8 и
zero final leases; полный capability coverage честно остаётся blocked до S3…S7.

## Принятый registration checkpoint S3/S4

Exact candidate `0.80.0-self-test-coverage` переводит общий report на plan version 3.
Он сохраняет восемь read-only Quick checks и регистрирует ещё семь passing checks:
common UI states, persistent Survey, passive BLE, passive Wi-Fi Capture, enrolled
storage, cold Library recovery и persistent raw Capture. Фактическая no-extension
assembly отмечает GPS, PN532 и IR как `not_applicable`, не превращая отсутствующее
hardware в failure или false pass. Два оставшихся checks —
`full.s4.shield.receivers` и `full.capability.coverage` — остаются `blocked`.

На board-01 independent host принял exact ordered report 15 pass / 0 fail / 2 blocked /
3 N/A, десять real TFT states, exact firmware/ELF/CID, неизменную storage generation
83, zero radio-TX/storage-write/buzzer side effects, healthy input и final owner/lease
`none`/`0` (`E-AUTO-045`/`E-HIL-105`/`E-SELFTEST-002`). Это доказывает honest
registration и readiness/persistence checks, но намеренно ещё не утверждает, что
Full/Guided активно выполняет каждую product workflow.

## Принятый identity checkpoint RF shield

Exact candidate `0.81.0-shield-receiver-probe` переводит общий report на plan version
4. Только после подтверждения preflight пользователем foreground owner Self-Test
получает `RadioSpi` и выполняет bounded identity probe. Слоты nRF24 1 и 2 читают по
четыре регистра при постоянно LOW CE; slot 3 никогда не выбирается, GPIO21 обязан
оставаться HIGH. У CC1101 читаются только status-регистры PARTNUM и VERSION. Любой
profile conflict, busy lease, floating/partial identity, side-effect counter или
ошибка cleanup приводит к fail closed. При boot эти приёмники не пробуются.

Board-01 обнаруживает оба nRF24 и CC1101 PARTNUM 0/VERSION 0x14 ровно за 8 nRF
register reads, 2 CC status reads и 20 SPI bytes. CE-high events, CC command strobes
и radio-TX commands равны нулю; storage остаётся generation 83 с zero observations,
final owner/lease возвращается к `none`/`0`. Поэтому Full даёт 16 pass / 0 fail /
1 blocked / 3 N/A: `full.s4.shield.receivers` проходит, blocked остаётся только future
total capability coverage (`E-AUTO-046`/`E-HIL-106`/`E-SELFTEST-003`/
`E-RADIO-001`). Это доказывает bounded read-only identity, но не physical RF silence,
passive activity reception или spectrum capture; для них нужны отдельные workflows,
а для physical silence — недоступный сейчас RF instrument.

## Принятый active receive-only RF checkpoint

Exact candidate `0.84.0-full-guided-rf` переводит общий report на plan version 5 и
добавляет `full.s4.spectrum.nrf24.receive` и
`full.s4.spectrum.cc1101.receive`. После пяти semantic UI cards Full/Guided на 500 ms
показывает cancellable active screen, получает `RadioSpi`, выполняет один полный
receive sweep 83 каналов на двух declared nRF24, затем один receive sweep CC1101 по
64 bins в plan 433 МГц. Работа cooperative, Back очищает оба adapter до release.
Quick остаётся неизменным read-only; Full теперь честно `read_only:false`, потому что
настраивает приёмники, хотя в нём не представимы transmit или storage-write paths.

На board-01 Quick проходит 8/8, Full возвращает 18 pass / 0 fail / 1 blocked / 3 N/A.
Exact accounting nRF24: 93 reads, 95 writes, 376 SPI bytes и 83 verified RX CE windows.
CC1101: 2 060 reads, 208 writes, 4 730 SPI bytes и 1 reset / 64 RX / 129 idle strobes.
Все counters TX-mode, payload, TX-strobe, PATABLE, FIFO, rejected-command и
storage-write равны нулю; generation остаётся 83, одиннадцать real TFT states проходят
review, final owner/lease — `none`/`0`
(`E-BUILD-085`/`E-AUTO-049`/`E-HIL-109`/`E-SELFTEST-004`/`E-RADIO-004`).

Первый exact HIL attempt сохранён как fail-closed failure модели runner: она ожидала
лишний idle strobe на каждый bin CC1101. Source и observed wire accounting показывают
реальную последовательность `SIDLE → tune → SRX → read → SIDLE`; independent equation
исправлен, те же bytes прошивки прошли. Checkpoint доказывает software-instrumented
receive-only execution, но не physical RF silence. Total capability coverage и active
Survey/Library/Capture execution остаются blocked/open.

## Принятый read-only checkpoint сохранённого artifact

Exact candidate `0.85.0-full-guided-artifacts` переводит Full/Guided на plan version 6
с `full.s4.storage.recovery.audit`, `full.s4.library.export.audit` и
`full.s4.capture.pcap.audit`. После release `RadioSpi` receive-проверками отдельный
cancellable data screen на 500 ms повторно идентифицирует enrolled SD card, монтирует
её с read-only guarantee драйвера и открывает последнюю atomic Session. JSON metadata
форматируется в общем bounded workspace; CSV продвигается по одной записи за проход
main loop; persisted raw Wi-Fi frames при наличии потоково формируются как radiotap
PCAP в discard sink, считающий bytes/records и FNV-1a без удержания payload. Library
view и всё ownership Storage/RadioSpi восстанавливаются до итогового report.

Board-01 проходит 21 check с zero failures, одним future capability blocker и тремя
profile N/A. Exact CID и continuity generation/observations равны `FE34…9CB7` и
83/0→83/0. Audit создаёт JSON 432 bytes, capture metadata 880 bytes, zero-row CSV
94 bytes и digest PCAP 16 кадров/2 773 bytes; counters storage-write, blocked-write и
radio-TX остаются нулевыми. Если в latest valid Session нет persisted frame payload,
PCAP artifact check честно становится N/A, а не выдуманным pass.

Первый physical attempt сохранён fail closed: расширенный `ui.state` превысил прежний
diagnostics buffer 4 096 bytes. Единственный bounded workspace увеличен до 4 608 bytes,
host limits обновлены, исправленный exact candidate прошёл все 12 визуально проверенных
TFT states и final lease 0 (`E-BUILD-086`/`E-AUTO-050`/`E-HIL-110`/
`E-SELFTEST-005`/`E-STORAGE-026`/`E-CAPTURE-003`). Это не создаёт fresh Survey/Capture
и не меняет user data.

## Принятый checkpoint disposable write/remount/export

Plan v7 создаёт test Session только в exact disposable namespace после явного
запуска Full/Guided пользователем: exact enrolled CID, bounded run ID и отдельный
cleanup permit разрешают только `/leshy-hil/<run-id>`. До любой мутации cleanup полностью сканирует
каталог и принимает только bounded имена SessionStore (`head-a.bin`, `head-b.bin` и
точные восьмизначные manifest/segment files); nested directory, неизвестный файл,
malformed generation или больше восьми entries приводит к fail closed до удаления.
Общие remove, rename и recursive-delete API остаются запрещены.

Exact `0.86.0-full-guided-disposable` регистрирует четыре checks: commit, read-only
remount, Library export и cleanup. Board-01 записывает generation 1 с тремя fixture
observations ровно через три writes/504 bytes и три file плюс три directory syncs.
Read-only remount восстанавливает ту же generation и экспортирует JSON, metadata и
три CSV rows; cleanup удаляет три exact files и scratch directory. Product
generation/observations остаются 83/0 с zero product writes, final Home не владеет
ресурсами.

Первый physical candidate сохранён fail closed: capture metadata выбирала Wi-Fi, но
fixture не имела обязательной matching finalized timeline, поэтому encoding
остановился до первой storage write. Cleanup всё равно удалил пустой scratch и
сохранил product data. Исправленный exact candidate добавляет одно Wi-Fi timeline
window, учитывающее все три observations, и проходит 13 TFT states
(`E-BUILD-087`/`E-AUTO-051`/`E-HIL-111`/`E-SELFTEST-006`/`E-STORAGE-027`). Это
доказывает изолированный disposable path, но не controlled physical power-cut или
endurance.

## Приёмка

1. `SELF-TEST` доступен штатными кнопками последним пунктом Home; serial-only Action
   не требуется.
2. Quick — read-only, bounded, cancellable, без TX и с zero final leases.
3. Full показывает scope до side effects, покрывает все применимые capability checks
   и честно фиксирует `not_applicable/blocked`.
4. User и release invocations выполняют одни versioned checks.
5. Host независимо отклоняет wrong bytes, missing checks, stale/mixed report,
   screenshot mismatch, unexpected side effects или incomplete cleanup.
