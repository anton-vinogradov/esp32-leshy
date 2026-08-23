# Двухплатный HIL и декларативные сценарии

*Читать на: [English](TWO_BOARD_HIL.md) · **Русский***

Статус: **принятый physical IR checkpoint S5; exact 0.129 закрывает source-bound
двухплатную цепочку NEC receive, persistence, cold export и safe cleanup**.

## Роли и граница доверия

| Роль | Прошивка | Полномочия |
|---|---|---|
| `candidate` / board-01 | exact product candidate | проверяемое устройство; product IR path остаётся RX-only и не имеет replay/TX authority |
| `fixture` / board-02 | отдельный image `leshy_fixture` | выдаёт один fixed NEC vector только после exact host admission |
| host | `run_ir_two_board_hil.py` → `run_hil_scenario.py` | связывает physical roles, exact commits/images/ID, выполняет scenario, снимает TFT/CSV и fail-closed отвергает отклонения |

Исходники fixture находятся вне product project. Source guards запрещают fixture
code внутри `firmware/leshy1`, а fixture build не содержит Wi-Fi, BLE, RF-radio,
SPI, SD или user-replay path.

## Реализованный первый positive scenario

`tests/hil/scenarios/infrared-nec-positive.json` — первый полный двухплатный
scenario. Он:

1. открывает `Home → Захват → Инфракрасный` через public Actions;
2. допускает board-02 к одному source-bound emission `nec-10-34`;
3. требует exact NEC decode из 67 pulses (`address=0x10`, `command=0x34`);
4. сохраняет live pulse CSV, явно сохраняет capture и доказывает continuity ровно
   на одно поколение storage;
5. холодно перезагружает product, открывает Library, проверяет IR-specific metadata
   и экспортирует byte-identical CSV;
6. возвращает обе платы в доказанное inactive state, а board-01 — на Home/lease 0.

Существующее одноплатное no-signal evidence exact 0.104 остаётся принятым. Exact
0.129 теперь также проходит physical positive scenario и сохранён как
[machine-checked evidence](../../tests/hil/evidence/board-01-infrared-nec-0.129.json).

## Safety contract fixture

Реализованный image `0.1.0-ir-nec`:

- предварительно устанавливает LOW на buzzer GPIO2, IR TX GPIO14 и nRF CE GPIO15/47
  до перевода в output; GPIO21 остаётся input;
- получает 16-символьный fixture ID из efuse base MAC ESP32-S3 и связывает exact
  running app ELF identity;
- никогда не auto-arm; admission требует случайную 128-bit session, exact app hash
  и exact fixture ID и истекает через 5 s;
- разрешает ровно один fixed NEC code `0xCB34EF10` на 38 kHz с hard ceiling
  измеренной длительности 100 ms;
- публикует counters start/stop/panic/emission, duration и факты всех inactive pads;
- гасит outputs при boot, нормальном завершении, stop, panic, timeout, parser failure
  и в Task-WDT ISR.

NEC emitter намеренно allocation-free и blocking примерно на 68 ms. Serial panic не
может прервать уже разрешённый выполняющийся burst; burst не может повториться или
превысить 100 ms, а completion path сразу переводит все контролируемые outputs в
inactive. Эта software boundary не заменяет независимый physical rail kill или
oscilloscope/RF proof.

## Read-only admission board-02

До любой fixture flash `profile_hil_board.py` запускает ROM esptool с `--no-stub` и
только командами `chip-id`, `read-mac`, `flash-id`, `get-security-info`. Сохранённый
profile обязан доказать ESP32-S3, flash 16 MB, zero erase/write/stub operations,
exact port и canonical fixture ID. Оператор явно декларирует стандартную assembly
v2 без extension modules и подключённые антенны; отсутствующие факты не выводятся.

Runner отвергает одинаковые candidate/fixture ports, profile с другого текущего
fixture port, dirty/uncommitted source, несовпадающие images, ID, versions или
commits, неактивный fixture, второе emission, drift storage/heap/input, неполный
cleanup или ненулевой final product lease.

## Один command для physical run

При двух подключённых платах на разных serial ports clean committed tree собирает
оба image, создаёт read-only fixture profile, прошивает явно названные ports,
выполняет все шаги и сохраняет machine run в `work/outputs` одной командой:

```sh
tools/run_ir_two_board_hil.py \
  --candidate-port /dev/cu.CANDIDATE \
  --fixture-port /dev/cu.FIXTURE \
  --expected-cid FE343253440000002000000055019CB7 \
  --output work/outputs/ir-nec-positive-0.129 \
  --profile-fixture-read-only \
  --declare-standard-v2-no-extensions \
  --declare-antennas-attached
```

Ранее принятый profile можно передать через `--fixture-profile`. Уже прошитые exact
bytes разрешено переиспользовать только явными options
`--reuse-exact-candidate-flash` и `--reuse-exact-fixture-flash`; normal path прошивает
оба exact images. Затем raw passing run допускается в tracked evidence через
`hil_evidence.py`, независимо проверяющий profile/source/image fixture и terminal
inactive outputs.

## Текущая граница evidence

Source commit `149e4ef37a650953b7335885c118824ed632fa16` связывает exact product 0.129,
fixture 0.1.0, runner и scenario. Profile board-02 доказывает fixture ID
`00009070690D15E0`, ESP32-S3/16 MB, явно объявленную standard v2 assembly и zero
profiling writes. Зелёный run переиспользует exact hashes уже прошитых images,
выполняет одну fixed NEC emission 68,424 ms, принимает/декодирует 67 pulses на
board-01, продвигает catalog generation 97→98 после явного Save, cold-reopen-ит item
и побайтно сравнивает live/Library CSV. Обе платы заканчивают inactive, product
owner/lease — `none`/`0`.

Это закрывает только объявленную IR positive boundary. Fixture TX Sub-GHz и 2.4 ГГц
остаётся запрещён до отдельных контрактов region/band, minimum-power, separation и
vector; разрешение IR не распространяется на RF.
