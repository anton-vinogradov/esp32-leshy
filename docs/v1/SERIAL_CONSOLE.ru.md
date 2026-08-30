# Serial Console и общий Actions CLI

*Читать на: [English](SERIAL_CONSOLE.md) · **Русский***

- **Capability:** CAP-053
- **Requirements:** PR-012, PR-017, PR-024, PR-025; NFR-002, NFR-003, NFR-006
- **Workflow:** WF-07, особенно WF-07-A3/A4
- **Architecture:** [ADR-002](adr/ADR-002-resource-policy.ru.md),
  [ADR-004](adr/ADR-004-action-boundary.ru.md)
- **Состояние:** host/build foundation в `1.0.0-dev.284`; product UI, hardware
  adapter и physical HIL ещё открыты

## Результат для пользователя

Владелец может слушать или двусторонне подключить выбранное собственное UART-
устройство 3,3 В, не превращая Лешего в shell произвольных GPIO. До владения pins
устройство показывает target, именованный wiring profile, voltage assumption, baud,
framing, mode, permissions, конечную duration и все resource conflicts. Back,
timeout, failure и panic закрывают port, стирают unsaved buffer и освобождают всё
владение.

On-device flow и локальный Actions CLI используют одну typed Action. Transport может
только сузить permissions текущей unlocked device session, но не расширить их.
Transcript не сохраняется без отдельного явного Save; сохранённый transcript будет
использовать protected storage Device Lock.

## Безопасная аппаратная граница

Первый поддерживаемый target profile называется `mux56-3v3`:

| Свойство | Контракт |
|---|---|
| Приём ESP | GPIO5, TX внешнего target → RX ESP |
| Передача ESP | GPIO6, TX ESP → RX внешнего target; только Bridge |
| Logic | только UART 3,3 В; это не RS-232/RS-485, tolerance 5 В отсутствует |
| Доступность | только explicit assembly profile external UART |
| Конфликты | недоступен, пока RF shield, GPS или PN532 объявлен/владеет GPIO5/6 |

В штатной сборке `stock-rf-no-gps-no-pn532` установлен RF shield: GPIO5 — CC1101
CSN, GPIO6 — GDO0. Поэтому Serial Console на собранном профиле обязан объяснить
`mux_conflict` и остаться недоступным. Firmware не принимает числовые поля RX/TX и
не предлагает raw GPIO read/write как fallback. Следующий board profile может
добавить другой *именованный и физически проверенный* wiring profile, но не ослабить
это правило.

## Режимы и permissions

| Режим | Направление | Обязательные permissions | Подтверждение |
|---|---|---|---|
| Monitor | только target → Леший | `device.control`, `serial.monitor` | fresh confirmation target/config |
| Bridge | target ↔ Леший | permissions Monitor плюс `serial.write` | fresh confirmation target/config/write |

Оба режима имеют класс `ActiveConfirmed`: даже receive-only владение pins меняет
shared mux. Baud — один из 1200/2400/4800/9600/19200/38400/57600/115200; framing —
8N1/8E1/8O1/8N2; run длится от 1 секунды до 5 минут. Target ID — явный bounded ASCII
token 1…32 bytes, не ambient label. ResourceBroker атомарно владеет `Console` и
`Mux56`; частичный lease никогда не виден.

## Контракт общей Action

Первая stable Action — `serial.console.start` v1, schemas request/result 1. Порядок
admission dispatcher:

1. bounds descriptor/schema;
2. authenticated device session;
3. полные permissions;
4. declared capability;
5. fresh confirmation;
6. atomic lease `Console+Mux56`;
7. старт hardware adapter.

Failure до шага 7 не имеет hardware side effect. Failed start adapter освобождает
полученный lease. Completion, cancel, timeout и endpoint failure terminal и
освобождают оба resource. Вторая invocation возвращает `busy`, не меняя state уже
работающей invocation.

Строгий allocation-free CLI принимает только формы:

```text
action.preview serial.console.start profile=mux56-3v3 target=<id> baud=<baud> framing=<8N1|8E1|8O1|8N2> mode=<monitor|bridge> duration_ms=<ms>
action.run serial.console.start profile=mux56-3v3 target=<id> baud=<baud> framing=<8N1|8E1|8O1|8N2> mode=<monitor|bridge> duration_ms=<ms> confirm=yes
action.status serial.console.start
action.cancel serial.console.start
```

Unknown/duplicate/missing fields, raw pin numbers, unsupported Actions, ambiguous
whitespace, oversized lines и `run` без `confirm=yes` fail closed.

## Этапы поставки

1. `done` — typed dispatcher, strict CLI parser, preflight именованного profile,
   отдельные permissions monitor/write, atomic leases, cleanup timeout/cancel/error,
   native contract tests и production build (`dev.284`).
2. `next` — bounded Arduino UART adapter и volatile ring, экраны Устройство → Serial
   Console preview/running/result, admission Device Lock и выполнение общего CLI.
3. `planned` — physical receive-only loop fixture, затем explicit permissioned bridge
   fixture; HIL Back/error/timeout/watchdog, zero leaked leases и no saved transcript.
4. `planned` — explicit encrypted Save, cold reopen/export и release HIL matrix.

`dev.284` не является physical UART claim: он намеренно не меняет pins, не прошивает
device, не запускает serial bridge, storage write, radio или network operation.
