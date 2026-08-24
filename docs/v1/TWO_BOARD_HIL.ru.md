# Двухплатный HIL и декларативные сценарии

*Читать на: [English](TWO_BOARD_HIL.md) · **Русский***

Статус: **принятый physical IR checkpoint S5; bounded positive path nRF24 реализован
и ожидает exact two-board run**.

## Роли и граница доверия

| Роль | Прошивка | Полномочия |
|---|---|---|
| `candidate` / board-01 | exact product candidate | проверяемое устройство; product radio paths остаются RX-only и не имеют replay/TX authority |
| `fixture` / board-02 | отдельный image `leshy_fixture` | выдаёт один admitted fixed NEC либо minimum-power/time-bounded nRF24 vector |
| host | signal-specific wrapper → `run_hil_scenario.py` | связывает physical roles, exact commits/images/ID, выполняет scenario, снимает TFT/data и fail-closed отвергает отклонения |

Исходники fixture находятся вне product project. Source guards запрещают fixture
code внутри `firmware/leshy1`. Fixture build не содержит Wi-Fi, BLE, SD,
произвольного payload/replay или product-side transmitter path. SPI существует
только для проверенного fixed nRF24 register vector из
[ADR-006](adr/ADR-006-bounded-signal-fixture.ru.md).

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

Source `0.2.2-bounded-signals` сохраняет NEC contract и добавляет ровно один RF
vector `nrf24-ch42-min-2s`. Он использует populated module slot 2 (CSN48/CE47), nRF
channel 42 / 2 442 МГц,
`RF_SETUP=0x90` (continuous carrier + PLL lock + минимальная настройка чипа −18 dBm)
и duration 2 секунды при hard ceiling 2,5 секунды. Boot, completion, stop, panic,
parser failure и Task-WDT удерживают CE всех трёх модулей inactive и переводят
адресованный radio в power-down. Payload command и произвольных channel, power или
duration нет. Это доказывает configured settings и functional reception, но не
radiated power, sensitivity, range, calibrated frequency или instrumented RF silence.

## Реализованный positive scenario nRF24

`tests/hil/scenarios/nrf24-carrier-positive.json`:

1. открывает `Home → 2.4 ГГц → Найти сигнал` через public Actions;
2. доказывает ambient calibrated `not found`, пока все три product nRF24 active и
   RX-only;
3. допускает board-02 к fixed channel-42 carrier и требует от product найти
   2 442 МГц / ближайший Wi-Fi channel 7 выше существующего response threshold;
4. снимает ambient, found и final TFT states;
5. требует automatic fixture completion/power-down, останавливает receiver и
   возвращает product на Home/lease 0 с zero TX/storage side effects.

Scenario становится gate-eligible только после сохранения physical результата. До
этого это реализованный test contract, а не принятое RF evidence.

Первый physical attempt с fixture `0.2.0` завершился fail-safe до emission и обнаружил
реальную ошибку slot: сохранённый hardware code 0.x указывает populated slots 2/3 и
unpopulated/PN532-reserved slot 1. Исправленный на slot 2 fixture `0.2.1` также
отверг start до CE HIGH, поэтому эта находка не была полной root cause. Оба record
сохранили zero emission/duration, fixture inactive/powered-down и product Home/lease
0: [0.2.0](../../tests/hil/evidence/board-01-nrf24-fixture-0.2.0-failed.json),
[0.2.1](../../tests/hil/evidence/board-01-nrf24-fixture-0.2.1-failed.json).
Fixture `0.2.2` добавляет exact CE-low/PWR_DOWN telemetry read-back STATUS, CONFIG,
RF_CH и RF_SETUP. Его [physical short regression](../../tests/hil/evidence/board-01-nrf24-fixture-0.2.2-failed.json)
сохранил `0/0/0/0` и `channel_readback_mismatch` на slot 2 board-02 при zero emissions
и safe cleanup. Следующая диагностика инвентаризирует каждый slot и обе legacy
ориентации SPI data pins, удерживая CE LOW. Non-gate regression обязан пройти до
повтора полного scenario.

Fixture `0.2.3` реализовал этот inventory. Сохранённый physical response показывает
полностью нулевые primary arrays STATUS/CONFIG/RF_CH/RF_SETUP, полностью `0xFF`
swapped arrays, masks `0/0` и `ce_high_events=0` на board-02. Run остаётся failed-safe,
потому что новый response не включил generic fixture fields `session_id` и
`nrf_powered_down`. Source-bound fixture `0.2.4` исправляет protocol и проходит
двухшаговую диагностику. CC1101 на той же bus также возвращает invalid identity
`status/part/version = 0/0/0` в documented orientation и no-ready/`0xFF` в swapped
orientation. При прежних zero/`0xFF` identity всех трёх nRF, отсутствии CE HIGH и
излучения и clean terminal states обеих плат evidence указывает на электрическую
недоступность всего съёмного RF-shield, а не только nRF. Фото затем подтвердили
настоящий connector socket/header 2×10, а не pogo contacts. Полная разборка и сборка
без питания не изменила identities; RF emission остаётся запрещённым:
[inventory 0.2.3](../../tests/hil/evidence/board-02-nrf24-inventory-0.2.3-failed.json),
[shared-shield identity 0.2.4](../../tests/hil/evidence/board-02-rf-shield-inventory-0.2.4.json).

Независимый same-image cross-check снимает основную неопределённость diagnostic
firmware. Exact product `0.81.0` с firmware hash `2d0bc0cf…8379` ранее находил на
board-01 две nRF identity `14/8/2/15` и CC1101 version `20`. Свежая прошивка того же
image на board-02 завершает те же bounded восемь nRF и два CC reads, но возвращает
нули для обеих nRF identity и CC1101 version. Run выполняет zero TX commands и
CE-high events, оставляет buzzer inactive и заканчивает Home/lease 0. Это поддерживает
fault общей rail/SPI/connector board-02 либо undocumented clone pinout, а не
fixture-specific code. Тот же exact image `0.81.0` остаётся на board-02; no-flash
rerun после reassembly снова получил zero identities с теми же bounded 8+2 reads,
zero TX/CE-high events и Home/lease-0 cleanup. Upstream v2 schematics, BOM и source
подтверждают точное совпадение pinout Leshy со stock и прямые общие 3,3 В/SPI для
всех четырёх receiver. Сравнительные измерения затем дали примерно 4,35/3,2 В на
рабочей board-01 и 4,7/3,3 В на board-02. Exact 0.130 sampled shared MISO/GPIO13 32
раза под каждым internal pull и выполнил только четыре CE-low nRF NOP: board-01 был
HIGH 32/32 со STATUS `0x0E`, board-02 — LOW 0/32 со STATUS `0x00` до и после reseat
без питания. Отсутствие rail и случайный плохой контакт больше не поддерживаются.
Powered-off MISO→GND равно 23 кОм на board-02 против 32 кОм на board-01,
что отвергает hard passive short. Exact 0.131 затем снимает detachable RF carrier и
читает тот же GPIO13 board-02 как HIGH 32/32 под обоими pull при zero SPI bytes и
zero receiver operations. Переход attached→isolated LOW→HIGH доказывает, что ESP
input наблюдает оба состояния, и локализует источник LOW на RF carrier или его стороне
connector. GPIO13 также обслуживает SD MISO main board, поэтому isolated HIGH под
обоими pull не является диагнозом повреждения main board. Exact diagnostic 0.132
снова подключает родной carrier board-02 и samples nRF CSN GPIO4/48/21 плюс CC1101
CSN GPIO5 HIGH 32/32 каждый, пока MISO остаётся LOW 0/32 под обоими pull. CE остаётся
LOW, SCK/MOSI получают zero transitions, выполняются zero receiver reads, strobes и TX
commands. Это отвергает случайно выбранный receiver и локализует оставшийся fault до
carrier module или shared-MISO net. Поскольку четыре modules делят direct power и
MISO, software selection не изолирует виновника; дальнейший module-by-module диагноз
требует физической изоляции MISO/power, либо carrier/device можно вернуть или заменить.
Разная population U.FL/external feed CC1101
не является evidence digital identity и не должна изменяться только по виду. Cross-swap
shields и emission запрещены до
локализации: [same-image cross-check](../../tests/hil/evidence/board-02-shield-receiver-crosscheck-0.81.json),
[variant/reassembly evidence](../../tests/hil/evidence/board-02-hardware-variant-20260823.json),
[assembled MISO characterization](../../tests/hil/evidence/board-02-rf-bus-characterization-0.130.json),
[isolated-main MISO characterization](../../tests/hil/evidence/board-02-isolated-main-miso-0.131.json),
[carrier-CSN characterization](../../tests/hil/evidence/board-02-rf-carrier-csn-0.132.json).

Official stock v1.6 один раз использован как bounded manual corroboration после
сохранения полного flash backup клона: internal Wi-Fi и BLE работали, внешний scanner
2,4 ГГц остался пустым. Stock не дал machine-readable receiver identity и был заменён
exact Leshy 0.130. Он остаётся недопустимым для automated diagnostic/fixture work:
source содержит maximum-power nRF24 constant-carrier paths, на observed modules есть
внешние PA/LNA, а radiated power не измерена.

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

Соответствующий bounded nRF24 run использует тот же admission и cleanup path:

```sh
tools/run_nrf24_two_board_hil.py \
  --candidate-port /dev/cu.CANDIDATE \
  --fixture-port /dev/cu.FIXTURE \
  --expected-cid FE343253440000002000000055019CB7 \
  --output work/outputs/nrf24-carrier-positive-0.129 \
  --fixture-profile work/fixture-profile.json
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

Это закрывает только объявленную IR positive boundary. ADR-006 разрешает единственный
bounded nRF24 vector в committed fixture source, но physical nRF24 claim не
принимается до зелёного и сохранённого exact two-board evidence. Fixture TX Sub-GHz
остаётся запрещён до отдельного region/band и vector contract.
