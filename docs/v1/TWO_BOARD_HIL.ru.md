# Двухплатный HIL и декларативные сценарии

*Читать на: [English](TWO_BOARD_HIL.md) · **Русский***

Статус: **принятая verification-архитектура S5; board-02 куплена, но ещё не
подключена и не профилирована**.

## Роли

| Роль | Прошивка | Полномочия |
|---|---|---|
| `candidate` / board-01 | exact product candidate | проверяемое устройство; production code остаётся passive/RX-only, если отдельная product capability явно не разрешает иное |
| `fixture` / board-02 | отдельный bounded HIL fixture image | создаёт известный stimulus только после source-bound host session для одной именованной операции |
| host | `run_hil_scenario.py` | определяет роли, прошивает разрешённые images, выполняет Actions/commands, снимает TFT GRAM, проверяет side effects и сохраняет evidence |

Fixture — не вторая копия продукта, которая бесконтрольно передаёт. Её firmware и
permissions отделены, чтобы test-only transmitter не мог попасть в product build.

## Декларативное выполнение

Сценарии используют `leshy.hil.scenario.v1`. Сценарий объявляет роли устройств,
публичные UI Actions, diagnostic queries, тихие интервалы времени, screenshots,
точные ожидания, числовые проверки, финальные invariants и честные ограничения.
Общий runner поддерживает один или два serial device и создаёт
`leshy.hil.scenario_run.v1`; общий evidence tool связывает commits сценария, runner
и exact candidate, хеширует firmware/app/factory/map, индексирует каждый сохранённый
artifact и независимо проверяет CID, storage, heap, input, safe outputs, cleanup и
final lease.

Первая принятая миграция —
`tests/hil/scenarios/infrared-passive-no-signal.json`: exact 0.104 выполняет 19
описанных шагов, снимает семь TFT states и доказывает physical receive/no-signal path
GPIO21 без fixture.

## Safety contract fixture

Будущий image board-02 обязан:

- загружаться со всеми RF/IR outputs inactive и никогда не взводиться автоматически;
- принимать только именованный bounded source-bound test vector и завершать session по timeout;
- требовать exact fixture identity и firmware hash до stimulus;
- публиковать counters start/stop, duration и evidence финальных inactive pads;
- останавливаться при timeout, потере serial, отказе candidate, watchdog или panic;
- сначала разрешать только IR; Sub-GHz/2.4 ГГц TX дополнительно требуют принятого
  band/region plan и подходящего attenuation или физического разнесения;
- никогда не сохранять пользовательские replay data в repository evidence.

Подпись релиза остаётся процессом под управлением GitHub: постоянный signing key не
хранится на host или fixture. Local HIL использует hashes и exact commits, после
чего GitHub release workflow подписывает только прошедшие gate bytes.

## Граница bring-up board-02

После подключения board-02 сначала проходит read-only identity/profile, до любой
fixture firmware или проверки output. Мы сохраняем USB identity, board profile,
flash и shield inventory, затем создаём role registry для общего runner. До этого
все двухплатные positive-signal claims остаются false.

Первый положительный сценарий — IR NEC: board-01 входит в timing-critical receive
window, board-02 выдаёт один фиксированный bounded NEC vector, board-01 должна его
декодировать, явно сохранить, cold-reopen в Library и экспортировать byte-exact CSV.
Затем тот же шаблон применяется к Sub-GHz с дополнительными regulatory controls.
