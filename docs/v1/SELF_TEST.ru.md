# ESP32-Leshy 1.x — встроенный Self-Test

*Читать на: [English](SELF_TEST.md) · **Русский***

Статус: **принят product/UX contract; Quick slice S2 физически принят;
coverage Full/Guided развивается через S3…S8**.

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

## Текущая реализация S2

Candidate `0.53.0-self-test-quick-measure` реализует последний пункт Home, menu
режимов, Full preflight, result screens, восемь стабильных Quick check IDs и
`leshy.self_test.report.v1`. На board-01 exact candidate прошёл все восемь Quick
checks read-only за 60 µs, с zero radio/storage/buzzer side effects, zero input
drops, minimum heap 188 872 B и final owner/lease `none`/`0` (`E-HIL-077`).

Full/Guided намеренно возвращает восемь pass и blocked
`full.capability.coverage`. Для S2 это правильный результат: незавершённые checks
S3…S7 не могут быть promoted ни device, ни host. Первый physical attempt также
обнаружил loop-task stack panic из-за локального diagnostic buffer 3 KiB; failure
сохранён, buffer перенесён в один bounded static workspace, а exact fixed candidate
прошёл полный regression.

## Приёмка

1. `SELF-TEST` доступен штатными кнопками последним пунктом Home; serial-only Action
   не требуется.
2. Quick — read-only, bounded, cancellable, без TX и с zero final leases.
3. Full показывает scope до side effects, покрывает все применимые capability checks
   и честно фиксирует `not_applicable/blocked`.
4. User и release invocations выполняют одни versioned checks.
5. Host независимо отклоняет wrong bytes, missing checks, stale/mixed report,
   screenshot mismatch, unexpected side effects или incomplete cleanup.
