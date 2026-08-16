# ESP32-Leshy 1.x — clean measurement target

*Читать на: [English](README.md) · **Русский***

Это первое независимое build tree 1.x. Оно служит bootstrap и resource measurement
target S1/S2, а не пользовательской прошивкой или закрытым этапом.

- не компилирует sources 0.x;
- фиксирует toolchain ADR-001 и профиль 16 MiB/no-PSRAM;
- инициализирует только display/backlight и read-only PCF8574 input; не запускает
  radio, storage, buzzer, IR или contested GPIO;
- выдаёт bounded NDJSON boot/resource evidence через native USB и UART0;
- реализует fixed-capacity multi-state HardwareInventory contract;
- направляет физические и диагностические клавиши в один `UiController` и выдаёт
  tiled TFT GRAM capture для воспроизводимого PNG evidence;
- компилирует dual-head atomicity contract и fail-closed disposable-media guard;
  boot оставляет mount/format/write выключенными, а один explicit exact-CID HIL
  command запускает общий `SessionStore` только в fresh bounded path disposable card;
- строит home menu из `HardwareInventory`: Diagnostics доступен, а Survey/Library
  disabled с причиной, пока их capabilities не стали available;
- запускает enabled entries через clean-tree `AppRuntime` и атомарно освобождает все
  foreground leases `ResourceBroker` по Back;
- определяет первую bounded модель Survey/Observation и passive-only Wi-Fi ingress
  contract; measurement image отрисовывает явно simulated golden workflow
  List/Detail/Stop, но не запускает и не трогает radio;
- кодирует stopped golden Session как deterministic CBOR + framed CRC32C segment,
  проверяет его через in-memory atomic head, открывает с выключенными radios и
  формирует bounded JSON summary; guarded HIL path дополнительно commits два
  generations в FAT, unmount/remount и read-only reopen newest generation;
- измеряет production-candidate ESP-IDF SDSPI/FatFs path на actual 4 MHz за
  32 commits, выдавая exact `FRESULT`, fixed timing p50/p95/p99, счётчики sync,
  allocation delta, heap и recovery generation 32 после real remount;
- реализует, но не запускает автоматически, six-boundary software-reset HIL
  path: exact-CID/new-namespace arm, `esp_restart` после выбранной успешной
  operation, затем exact-CID read-only recovery с prior-hash и zero-write checks;
  board-01 прошла все шесть boundaries с generations `1/1/1/1/1/2`, а runner теперь
  сохраняет checkpoint каждой boundary и ограничивает fail-closed media-readiness retry;
- использует общий caller-owned SessionStore validation/recovery workspace; 0.31
  удаляет redundant Session buffer 4 672 B, возвращает static RAM ниже RB-03 и
  проходит guarded physical boundary-6 regression;
- предоставляет explicit measurement-only passive Wi-Fi source в 0.32: NVS и
  credentials off, без active/connect/config/raw-TX API, с EspRf lease, scrubbed
  identifier-free aggregate evidence и fixed p50/p95/p99 encoded ingress rates;
- добавляет fixed FIFO 64 observations и policy 2 KiB/5 s/Stop/safe-shutdown в
  0.33; guarded 32×64 physical batch run даёт 9 068 encoded B/s против RB-06
  required 2 184 B/s и восстанавливает generation 32 после remount;
- соединяет real passive Wi-Fi→FIFO→guarded SessionStore в 0.34: 29 observations,
  high-water 9/64, zero drops, latency commit и read-only reopen после remount;
- принимает recovered physical Session в штатную Library в 0.35 без восстановления
  simulated fixture: Home/List/Detail/Export показывают persistent/real provenance,
  serial artifact содержит `persistent=true`, `simulated=false`; boot-time catalog
  остаётся отдельным следующим шагом;
- в 0.36 публикует полный ESP app ELF SHA-256 из descriptor реально запущенного
  образа; prerelease runner независимо извлекает digest из candidate и требует его
  exact equality в cold boot и повторном metrics record;
- в 0.37 принимает bounded `hil.begin/end` envelope: один 128-bit run ID и exact app
  identity связывают device execution с manifest/run/attestation без обхода UI,
  permissions или resource leases;
- использует временный dual-OTA/LittleFS layout под ADR-003/RB-02.

Сборка без прошивки:

```sh
tools/build_1x_measure.sh
```

Host contracts и isolation checks запускаются через `tools/test.sh`. Physical flash
является evidence operation и требует проверенный full backup с тем же restore path,
что `HIL_PROBE`.

Reset matrix runner требует отдельное deliberate acknowledgement и может
работать только с явно выбранной disposable card:

```sh
"$HOME/.platformio/penv/bin/python" tools/run_1x_sd_reset_matrix.py \
  --port /dev/cu.usbmodem2101 --cid <CID32> --run-prefix <new-prefix> \
  --output reset-matrix.json --execute-reset-matrix
```

Evidence и оставшийся scope поддерживаются в
[`docs/v1/STORAGE_HIL.ru.md`](../../docs/v1/STORAGE_HIL.ru.md).

Управление и захват probe UI без reset:

```sh
"$HOME/.platformio/penv/bin/python" tools/capture_1x_ui.py \
  --port /dev/cu.usbmodem2101 --keys down,down,select --output ui.png
```

Report разделяет runtime-, display-, input- и first-render-ready milestones. TFT
GRAM capture заменяет рутинные фотографии; для финального evidence NFR-001 всё ещё
нужны физическая проверка панели/яркости и внешний boot timing.
