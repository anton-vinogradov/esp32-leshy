# ESP32-Leshy 1.x — программный Safety Supervisor

*Читать на: [English](SAFETY_SUPERVISOR.md) · **Русский***

Статус документа: **обязательный software-safety contract S5**. Текущая реализация
не является сертифицированной системой безопасности и не заменяет отсутствующие
power-cut, temperature, voltage и current-monitoring hardware.

## Назначение и граница

Safety Supervisor — общесистемный fail-closed слой ниже приложений. Наблюдаемый
фатальный software fault должен приводить к bounded reset и защёлкнутому Safe Mode,
а не к тихой перезагрузке обратно в обычный режим. Supervisor не принадлежит ни
одной пользовательской функции и не выводит безопасность из работающего UI.

ESP32-DIV v2 позволяет использовать panic-enabled Task WDT ESP32-S3 и принудительно
опускать известный active-high buzzer и все объявленные nRF CE. Подтверждённая схема
не позволяет разорвать rails 3,3/5 В, независимо reset/power-gate CC1101, измерить
температуру cell/rail или доказать физическую остановку радио после смерти MCU.
Недоступные controls всегда остаются явными `false` в diagnostics.

## Машина состояний

```text
startup ── WDT и outputs исправны ──> armed
   │                                    │
   └── WDT/invariant fault ─────────────┤
                                        ↓
                       fatal fault ──> latched Safe Mode
                                        │
                                 OK / вправо один раз
                                        ↓
                                   clear pending
                                 │               │
                         влево отменяет   OK / вправо подтверждает
                                 │               │
                                 └── latched     ↓
                                            clear RTC + restart
```

- У `latched` нет timeout или автоматического снятия.
- Console clear требует точную команду `safety.clear confirm`.
- Обычный UI использует тот же Action path, что physical keys: первое OK/вправо
  запрашивает разблокировку, второе подтверждает; влево только отменяет pending.
- Последующий software/EN/USB reset не очищает принятую exact fault record.
- Полное снятие питания удаляет и RTC retention, поэтому является physical
  intervention; software-only плата не может сохранить latch без питания.

## Runtime watchdog

1. Boot устанавливает buzzer LOW и nRF CE LOW до console/display.
2. Узкий watchdog восстановления SD работает под отдельным существующим arm flag.
3. После boot recovery main loop task постоянно подписывается на panic-enabled
   Task WDT с timeout 5 с.
4. Каждый завершённый оборот main loop кормит watchdog. Намеренный тест может
   прекратить feed только на Home без owner/lease.
5. ISR Task WDT отличает arm восстановления SD от runtime arm. При runtime trip он
   прямыми write-one-to-clear регистрами ESP32-S3 опускает GPIO2/14/15/47 и затем
   пишет exact-app retained record.
6. Record публикуется magic-last и содержит value/complement для app identity,
   reason, trip count, quiesce count и latch confirmation. Torn и foreign-app records
   отклоняются.
7. Panic path перезагружает MCU. Свежая runtime record принимается только при
   watchdog-class reset, затем в task context отмечается confirmed. Последующие
   resets сохраняют этот Safe Mode; unconfirmed stale record его не создаёт.
8. Safe Mode пропускает product SD recovery, radio/capture workers и обычные
   Actions. Разрешены diagnostics, TFT capture, evidence-session commands,
   двухшаговый UI clear и exact console clear.

## Контракт outputs

| Output/domain | Действие ISR | Evidence при boot/Safe Mode | Текущая гарантия |
|---|---|---|---|
| buzzer GPIO2 | direct LOW | pad читается LOW | software sound path неактивен |
| nRF CE GPIO14/15/47 | direct LOW | все pads читаются LOW | все объявленные nRF transmit enable неактивны |
| CC1101 | ISR не вызывает scheduler/SPI | в текущем firmware нет TX path; boot возвращает receive/idle adapters только после clear | независимого hard stop нет; будущий TX запрещён без hardware/physical-stop evidence |
| SD/product data | ISR не трогает filesystem | Safe Mode не запускает catalog/mount workers; read-only reopen только после explicit clear/restart | safety trip ничего не пишет и не мутирует recovery |
| power rails | нет действия | `physical_rail_kill_available=false` | rails остаются под питанием |
| thermal/voltage/current | нет действия | availability остаётся false | нет claim over-temperature/undervoltage |

ISR не пишет log, не flush-ит, не выделяет память, не берёт mutex, не вызывает
Arduino adapter и не выполняет SPI/filesystem cleanup. Task-context quiesce
идемпотентен, но ISR от него не зависит.

## Наблюдаемые schemas и автоматический HIL

- `safety.state` выдаёт `leshy.safety.v1`: state/reason, arm/latch/clear, watchdog
  timeout, retained counters, reset reason, pads, owner/lease и явные hardware limits.
- `hardware.safe-outputs` совместимо расширен facts для всех nRF CE и software
  quiesce.
- `safety.watchdog-test confirm` — bounded destructive diagnostic. Он разрешён
  только из нормального `armed` Home без runtime owner/lease и при inactive pads,
  выдаёт flushed arm record и намеренно прекращает feed main-loop WDT.
- `safety.restart-test confirm` разрешён только из защёлкнутого и quiescent Safe
  Mode; он выдаёт flushed proof record и выполняет software reset, не очищая
  retained latch. Это автоматическая проверка persistence, а не пользовательский
  clear path.
- `tools/run_1x_safety_watchdog_hil.py` прошивает один exact candidate, проверяет
  normal arm, вызывает настоящий Task-WDT reset, проверяет retained Safe Mode и
  inactive pads, делает явный output-quiesced software restart и требует сохранения
  latch, снимает оба TFT state, очищает latch через публичный Right/OK Action path и
  доказывает continuity exact CID/catalog плюс final Home lease zero.

Это не simulation: reset transcript обязателен. Отсутствующий reset, invalid record,
automatic recovery, запись storage, неожиданный owner или недоступный final Home —
terminal failure.

## Открытая safety-работа

- добавить heartbeat/deadline supervision worker tasks и будущих transmit leases;
- направлять driver invariant, brownout/thermal и storage safe-shutdown faults в ту
  же reasoned latch только после появления надёжных sensors;
- для любого будущего active-radio profile добавить внешний rail/PA kill либо load
  switch и reset/power gate CC1101;
- измерить GPIO reset/pull и physical RF stop независимыми приборами;
- включить destructive watchdog check в Full/Guided Self-Test и final S8 release
  manifest, сохранив Quick read-only.
