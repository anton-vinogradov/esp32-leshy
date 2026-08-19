# ESP32-Leshy 1.x — автоматический предрелизный HIL

*Читать на: [English](PRE_RELEASE_HIL.md) · **Русский***

Статус документа: **принятый операционный контракт ADR-005; implementation v0.5**.

Цель — автоматически доказать, что конкретный неизменяемый release candidate
работает на реальном ESP32-DIV, показывает ожидаемые экраны и завершает сценарии без
утечек ресурсов. Прошивка предоставляет наблюдаемые факты; решение `pass/fail`
принимает независимый host-runner и проверяет release pipeline.

## Рекомендуемый контур

```text
commit / release candidate
  ↓
CI один раз собирает binary + map + manifest + SHA-256
  ↓
неизменяемый candidate artifact
  ↓
HIL-станция прошивает именно этот SHA на реальную плату
  ↓
cold boot → обычные Actions → реальные TFT captures → cleanup
  ↓
детерминированный evidence archive
  ↓
GitHub OIDC/Sigstore подписывает candidate и evidence без постоянного private key
  ↓
release gate проверяет suite, board, результаты и тот же SHA
  ↓
публикуются те же байты; повторная сборка запрещена
```

Это hybrid host-orchestrated design: небольшая безопасная evidence boundary входит в
прошивку, а сценарии, expected values, golden images, сравнение и release policy
остаются снаружи.

## Текущая команда connected-candidate

Обычный локальный checkpoint требует только clean committed candidate и один
ESP32-DIV, подключённый по USB. Это foreground-команда, а не macOS service,
daemon или постоянно зарегистрированная HIL-станция:

```sh
./tools/verify_connected_candidate.sh
```

Если найден ровно один `/dev/cu.usbmodem*`, port выбирается автоматически.
Явный `--port` остаётся для fail-closed разрешения неоднозначности. Команда по
порядку выполняет:

1. все host tests и source guards;
2. bilingual documentation/link/schema checks;
3. exact product build и фиксацию candidate hashes;
4. ровно одну прошивку этого candidate;
5. versioned physical workflow через public Actions;
6. screenshots настоящего TFT GRAM и machine-readable metrics;
7. independent verifier над run directory.

Реализованный workflow 0.93 не требует нажатий физических клавиш. Оператор только
подключает плату и запускает команду. Dirty tracked tree, неоднозначный port,
любое несовпадение identity/hash/CID, failed action, отсутствующий screen, изменение
heap/storage, drop, утёкшая lease или unsafe counter дают fail closed. Run output хранится в
`work/outputs/`. Принятые run/provenance/source/frame artifacts и их полный hash
index копируются в `tests/hil/evidence/` и регистрируются в host suite.
Repository policy намеренно исключает тяжёлые исторические `.bin`/`.elf`/`.map`
bytes: полный local gate перехеширует присутствующие bytes, а GitHub `quality`
перехеширует каждый Git-retained artifact, проверяет declared opaque hashes и
повторяет текущий source/claim contract в явном режиме `tracked`. Ни один режим
не заявляет проверку bytes, к которым у него нет доступа.

Эта local command доказывает candidate checkpoint, но не приписывает себе будущий
signed-release gate S8. GitHub OIDC/Sigstore signing и публикация тех же immutable
bytes остаются pipeline work, а controlled power-cut или destructive fixtures — отдельным
явно authorized HIL.

## Часть прошивки

Release candidate предоставляет по локальному USB стабильные versioned schemas:

- build/profile/reset identity и монотонный boot counter;
- capability inventory и resource ownership;
- обычные typed Actions, идущие тем же путём, что физические клавиши;
- публичное UI state без screen-specific setters;
- tiled readback реального TFT GRAM с revision и byte count;
- bounded metrics, queue/drop/storage/error counters и safe-output state;
- начало/завершение тестовой сессии только как маркировку evidence, без скрытого
  перехода приложения в нужный state.

Прошивка не содержит ожидаемый screenshot hash и не объявляет собственное поведение
успешным. Она сообщает факты. Runner обязан прийти к экрану через Home/Actions,
проверить state, pixels и cleanup независимо.

Обычно в release binary разрешены только read-only evidence, обычные пользовательские
Actions и безопасные штатные операции. Единственное узкое исключение — versioned
watchdog recovery diagnostic с exact confirmation: `safety.watchdog-test confirm`
разрешён только для armed supervisor на idle Home, без owner/lease и при уже
неактивных controllable output pads. Он не активирует GPIO/RF, не пишет storage и не
обходит permissions, а только прекращает feed watchdog main loop, чтобы проверить
recovery exact release bytes. Произвольные fault injection, GPIO/RF commands, raw
memory и обход permissions остаются запрещены. Разрушительные storage/power-cut/
radio HIL по-прежнему требуют отдельной diagnostic image или внешнего оборудования.

Приложение `Home → Устройство →` [Self-Test](SELF_TEST.ru.md) — пользовательский клиент того же
versioned check registry. Quick выбирает bounded read-only subset; Full/Guided после
явного preflight выбирает все применимые checks. Host runner вызывает те же check IDs
на exact release bytes, при разрешении добавляет fixtures/endurance и остаётся
независимым release oracle. Boot-time Quick detour и второго release-only определения
здоровья устройства нет.

Обязательное safety-поведение и hardware limits описаны в
[`SAFETY_SUPERVISOR.ru.md`](SAFETY_SUPERVISOR.ru.md). Connected safety runner:

```bash
python tools/run_1x_safety_watchdog_hil.py \
  --port /dev/cu.usbmodem2101 \
  --firmware firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.bin \
  --expected-version 0.103.0-safety-supervisor \
  --expected-cid FE343253440000002000000055019CB7 \
  --source-commit <full-commit-id> \
  --output work/outputs/safety-watchdog-0.103-<commit> --flash
```

Он требует настоящий panic Task-WDT reset, matching app identity, inactive pads,
защёлкнутый Safe Mode после второго reset, пропуск product recovery, двухшаговый
clear через публичный UI, неизменные catalog/CID, final Home и lease zero.

## Часть host-runner

Suite хранится как versioned declarative manifest. Каждый scenario задаёт:

- required board/profile/capabilities и допустимые degraded states;
- preconditions и явные разрешения на media/radio/storage;
- cold/warm boot policy и максимальные времена;
- последовательность public Actions или пользовательских commands;
- assertions для page/state/owner/leases/counters;
- точки TFT capture и выбранный visual comparator;
- error/cancel/Back path;
- финальные invariants: owner `none`, lease mask `0`, безопасные outputs, отсутствие
  неожиданного reset, bounded heap/drop/error delta.

Runner останавливается fail-closed при несовпадении candidate SHA, firmware-reported
version/build ID, board profile, suite schema или обязательной capability. Retry
разрешён только для заранее классифицированной transient signature и сохраняется в
evidence; общий «повторить до зелёного» запрещён.

## Проверка screenshots

Для каждого кадра сохраняются raw RGB565, PNG, UI state, revision и SHA-256.

Сравнение имеет три режима:

1. **Exact:** byte-identical RGB565 для полностью deterministic screens.
2. **Region-aware:** exact/threshold comparison по именованным регионам; dynamic
   time/RSSI/counter regions имеют явные masks и отдельные semantic assertions.
3. **External camera:** небольшой обязательный RC subset для panel/backlight/
   orientation и грубых физических дефектов отображения, которые GRAM readback
   принципиально не видит.

Глобальный permissive pixel threshold запрещён: он может скрыть пропавший critical
text или selection. Обновление golden требует просматриваемого image diff, причины и
version bump suite; runner не перезаписывает baseline автоматически.

### Контракт external-camera subset

Camera lane является частью одной foreground release-процедуры, а не постоянно
работающей macOS-службой. Она снимает физическую панель в тех же четырёх устойчивых
состояниях, для которых product runner уже сохранил GRAM: `setup`, `running`,
`committed`, `export`. Один station manifest фиксирует:

- `station_id` и точный platform `camera_id`;
- неизменный размер camera frame;
- калиброванный четырёхугольник видимой панели в порядке TL/TR/BR/BL;
- относительные пути к camera PNG и соответствующему GRAM PNG;
- пороги контраста, корреляции и преимущества правильной ориентации.

`verify_1x_camera_subset.py` выпрямляет область панели, приводит camera и GRAM к
одной bounded luminance grid и сравнивает ожидаемую ориентацию со всеми поворотами
0/90/180/270. Blank/underexposed frame, неверный размер, слабая корреляция,
поворот, отсутствующий/escaping path или ослабление нижней release policy завершаются
fail-closed. Result содержит SHA-256 manifest и каждого camera/GRAM PNG, фактические
метрики и причины отказа; повторная проверка этих связей внутри attested bundle не
позволяет заменить файл после optical verification.

Встроенный macOS provider использует AVFoundation строго как one-shot command:

```sh
python3 tools/capture_macos_camera.py list
python3 tools/capture_macos_camera.py capture \
  --device-id '<exact platform camera id>' --output camera/setup.png
python3 tools/verify_1x_camera_subset.py \
  --manifest camera-manifest.json --output camera-result.json
```

Provider компилируется во временный каталог, снимает один PNG и завершается; ничего
не устанавливает и не слушает в фоне. Контракт verifier не зависит от macOS или
конкретной модели камеры, поэтому provider можно заменить другим one-shot capture,
сохранив тот же PNG/manifest boundary.

Синтетическая positive/negative matrix уже входит в host tests. Camera lane станет
обязательной частью stable-1.x promotion только после подключения реальной камеры,
фиксации bench calibration и проверки порогов на board-01. До этого она не создаёт
фиктивный gate: measurement 0.45 остаётся заведомо non-publishable.

## Evidence bundle и GitHub attestation

Один прогон создаёт самодостаточный каталог:

```text
run.json                 suite/device/candidate/result summary
candidate-manifest.json  binary/map/partition hashes and budgets
serial.ndjson            unmodified device records
scenarios/*.json         actions, assertions, timings, cleanup
frames/*.rgb565          source display-controller bytes
frames/*.png             reviewable screenshots
frames/*.diff.png        visual failures or reviewed baseline changes
camera/*.png             external views of the same four product states
camera-manifest.json     station/camera/calibration and paired frame paths
camera-result.json       hashes, optical metrics, orientation and pass/fail
artifacts.sha256         hash of every retained file
runner-result.json       unsigned local result; не является release trust
```

Runner result содержит candidate SHA-256, firmware-reported build ID, suite revision,
board/profile ID, pass/fail и bundle hash. После локальной проверки каталог
детерминированно упаковывается в `hil-evidence.tar.gz`. GitHub Actions подписывает
candidate и этот архив через `actions/attest@v4`: job получает короткоживущую OIDC-
идентичность, а Sigstore связывает подпись с repository, commit, workflow и
protected environment. Постоянного private key, PEM-файла или GitHub secret с ключом
в этом контуре нет.

`runner-result.json` сам по себе никогда не делает bundle release-eligible. Gate
доверяет только успешной `gh attestation verify` для обоих exact artifacts и затем
повторно проверяет внутренние hashes/session/candidate bindings.

## Release gate

Предлагаются три частоты:

| Gate | Когда | Минимум |
|---|---|---|
| `device-smoke` | каждый merge/доступная станция | flash, cold boot, Self-Test Quick, Home/Diagnostics/Back, product Survey→commit→Library→export, TFT, resources, safe outputs |
| `device-regression` | nightly/изменение firmware | non-destructive plan Self-Test Full/Guided, все доступные workflows, EN/RU golden matrix, repeated navigation, storage read/reopen |
| `release-candidate` | перед публикацией | тот же полный применимый Self-Test plan плюс независимый host verdict, Stage Demo, install/update/rollback, reboot paths, destructive HIL attestations, budgets и обязательный camera subset |

GitHub-hosted CI собирает candidate и host tests, затем GitHub-attests exact binary.
Физический прогон выполняет выделенный self-hosted runner из protected environment
`hil-production`: он сначала проверяет provenance candidate, затем прошивает его и
возвращает evidence. Promotion job принимает только обе GitHub attestations от
`.github/workflows/prerelease-hil.yml` на `main`, проверяет suite/board matrix и
прикладывает тот же binary; rebuild между HIL и публикацией запрещён.

## Безопасность и приватность

- transport локальный USB, без network listener;
- normal Actions не обходят confirmations/permissions/resource leases;
- screenshot/export считается потенциально чувствительным artifact и sanitizes
  logs согласно scenario policy;
- unknown media никогда не становится тестовым автоматически;
- destructive scenarios требуют отдельный suite, explicit device/media identity и
  физически выделенный стенд;
- public PR никогда не направляется на HIL runner; environment разрешает только
  `main`, а одноразовый runner регистрируется только для этого repository после
  явного локального `check`;
- timeout/runner crash обязан вернуть power/resources в safe state либо пометить
  станцию quarantined до operator recovery.

## Альтернативы

| Вариант | Плюсы | Минусы | Роль |
|---|---|---|---|
| Device-only self-verdict | работает без host, простой factory launch | firmware проверяла бы сама себя; code/flash overhead; слабый trust candidate/golden | отвергнут как release authority; UI остаётся клиентом shared checks |
| Отдельная test firmware | можно включить опасную instrumentation | тестируются не exact release bytes; возможен test-only behavior | destructive fault injection |
| Только camera/button/power robot | максимальный black-box реализм | дороже, медленнее, сложнее диагностировать | небольшой RC subset и physical qualities |
| Только emulator/host screenshots | быстрый и дешёвый CI | не проверяет TFT, GPIO, buses, timing и реальную сборку | ранний feedback, не release gate |
| Hybrid host + firmware evidence boundary | exact candidate, реальные pixels/state, гибкие suites и строгий gate | нужен HIL station и versioned protocol | **рекомендуемый основной контур** |

## Последовательность реализации

1. Объединить текущие boot/UI/capture/metrics scripts в один runner с manifest и
   единым serial connection.
2. Зафиксировать минимальный `device-smoke` для board-01 и deterministic golden
   Home/Diagnostics/Back.
3. Добавить firmware build identity/test-session envelope и evidence bundle index.
4. Поднять self-hosted HIL station, immutable candidate download и keyless GitHub
   Artifact Attestations; текущий release workflow до реального прогона не блокировать
   фиктивным gate.
5. Перевести публикацию 1.x на build-once/test/promote-same-bytes.
6. Добавить relay power-cycle, camera и измерительные приборы по мере доступности.

## Однократная настройка GitHub

До первого запуска `.github/workflows/prerelease-hil.yml` нужны:

1. Environment `hil-production` с deployment branch только `main`, без required
   reviewer. Явным разрешением доступа к подключённой плате служит сам локальный
   запуск `release_1x.py check`; дополнительный click-approval ломал бы однокомандный
   контракт, не добавляя независимого reviewer в single-maintainer repository.
2. Авторизованный `gh` CLI с правами dispatch workflow, чтения attestations/artifacts
   и временной регистрации repository runner; Python 3 и USB access к плате.
3. Python dependencies физического job ставятся из
   `tools/requirements-hil.txt` в изолированный job venv.

Runner заранее не устанавливается. `tools/release_1x.py` скачивает pinned official
macOS arm64 archive в `~/Library/Caches/esp32-leshy/actions-runner`, проверяет его
SHA-256, а credentials/config/work directory создаёт заново во временной директории.
После cloud build script регистрирует runner с `--ephemeral`, labels
`leshy-hil`,`esp32-div-v2` и уникальной `leshy-request-<id>` только этого workflow
run: он не может случайно забрать другой queued job, принимает ровно один свой job,
deregisters и завершается. Постоянного listener, macOS service или `launchd` unit нет.

Signing secrets, PEM files и public-key provisioning не нужны. Serial path
определяется локально при единственном подключённом устройстве либо задаётся через
`--port` и передаётся только этому manual run; GitHub variable для него не требуется.

## Операторский release-контракт

При подключённой board-01 полный gate запускается одной командой из чистого `main`,
совпадающего с `origin/main`:

```sh
./tools/release_1x.py check 1.0.0
```

Команда проверяет зашитую версию и serial port, dispatches uniquely named workflow,
ждёт успешную cloud-сборку, поднимает одноразовый runner, прошивает exact candidate,
выполняет device-smoke и ждёт promotion-proof. Для stable `1.x.y` при успехе она
печатает `RELEASE READY` и точную следующую команду:

```sh
./tools/release_1x.py publish <successful-run-id>
```

Prerelease/measurement version может проверить весь контур, но получает только
`VALIDATION PASSED — NON-PUBLISHABLE VERSION`; `publish` её отвергает.

`publish` принимает только успешный manual run на `main` со stable version `1.x.y`,
повторно скачивает candidate/evidence, проверяет GitHub attestations каждого файла,
внутреннюю привязку bundle к `firmware.bin` и совпадение текущего HEAD с tested
commit. Только после этого создаются tag и GitHub Release с теми же exact bytes —
rebuild отсутствует. Исторический `.github/workflows/release.yml` ограничен `v0.*` и
не перехватывает 1.x tag.

GitHub Actions run, retained artifacts и Sigstore attestations — каноническое
evidence. Локальная квитанция `release-checks/<run-id>.json` gitignored и нужна лишь
как удобный указатель; её потеря не меняет release eligibility. При ошибке workflow
отменяется, runner process/registration очищаются, `RELEASE READY` не появляется.

## Текущее implementation evidence

Version v0.6 реализует первые пять пунктов, on-demand lifecycle, exact-byte promotion
и combined product/generic lane. И прежний generic-only, и текущий combined GitHub
workflow прошли end to end:

- `tools/run_1x_prerelease_hil.py` загружает declarative suite, по явному `--flash`
  прошивает exact candidate через esptool с verify, делает cold reset, держит один
  passive USB session для Actions/captures и формирует bundle;
- `tests/hil/device-smoke.v1.json` revision 6 задаёт отдельный bounded frontend
  physical keypad, fail-closed product admission,
  Home→Diagnostics→Back и
  product Survey Setup→Running→Detail→Stop & Commit→Library→Detail→Export→Home,
  boot ≤2 s, board/profile, heap ≥128 KiB, owner/lease cleanup и GPIO2 LOW;
- bounded query steps позволяют проверить typed serial artifact внутри того же HIL
  session; action/query ambiguity и небезопасные commands fail closed, а частичный
  `--scenario` run никогда не становится gate-eligible;
- generic UI regression и product-media recovery используют явные непересекающиеся
  states устройства. `storage.product.unenroll confirm` удаляет только CID из NVS и
  не обращается к SD перед deterministic `device-smoke`; после него
  `storage.product.enroll disposable-read-only <CID32>` может вернуть enrollment
  только после exact-CID read-only catalog admission с zero SD writes. Version 0.44
  прошла обе половины на board-01 и сохраняет machine-checked product-boot artifact;
  теперь этим переходом владеет `run_1x_release_hil.py`, который восстанавливает
  enrollment даже после ошибки generic lane;
- `tools/run_1x_product_survey_hil.py` — service-free lane для enrolled media. Когда
  device и exact product card подключены, одна команда при необходимости прошивает
  exact candidate, делает pre/post cold boot, требует exact-CID read-only recovery,
  подтверждает Start до identity/scan/mount work, затем polling переводит persistent
  worker в Running. Lane требует live source/lease/backend state, доказывает рост scan
  и observation counters при открытом Detail, применяет budgets callbacks Start/Stop
  и Detail/Back, допускает запись только после bounded cached-FSInfo и
  непротиворечивого passive accounting, останавливает source до commit ровно следующей
  generation, снимает TFT Setup/Running/Detail/Committed/Export, проверяет persistent
  Library export и заканчивает lease 0. При exception всё равно создаётся terminal
  evidence и выполняется best-effort cleanup owned state. Runner публикует собственный
  source SHA-256 во время выполнения; retained worker run 0.59 и exact bytes runner
  независимо machine-checked через `check_product_survey_worker_acceptance.py`, а
  retained regression 0.60 добавляет source invariant, что terminal `Idle` выставляется
  только после UI cleanup/commit, и проверяется
  `check_product_survey_terminal_ack_acceptance.py`;
- `tools/run_1x_product_survey_cancel_hil.py` — dedicated negative lane active scan.
  Он ждёт, пока firmware покажет physically active passive scan, отправляет Back,
  требует snapshot этого active state в cancellation request, применяет budgets
  acknowledgement 150 ms и callback 10 ms, после cold reboot доказывает отсутствие
  изменений generation/observations и заканчивает с закрытыми source/backend, zero
  writes и lease 0. `check_product_survey_active_cancel_acceptance.py` пересчитывает
  retained failed input-probe incident 0.61 и exact passing bundle 0.62; 0.62 также
  публикует bounded attempts/retries boot probe PCF8574;
- `tools/run_1x_product_survey_missing_source_hil.py` — dedicated negative lane exact
  source. Он arm one-shot fault только из idle Home без runtime owner, входит в Product
  Survey через public Actions и требует localized terminal TFT state после cleanup и
  release lease. Lane доказывает, что source start и store open не выполнялись,
  создано zero bytes/observations, Select не делает скрытый retry, Back возвращает
  Home, а cold read-only recovery сохраняет прежнюю generation. Exact candidate 0.68,
  bytes runner, hashes framebuffer, CID, invariant heap, zero writes и прежняя Library
  68/25 независимо перепроверяются
  `check_product_survey_missing_source_acceptance.py`
  (`E-AUTO-032`/`E-HIL-092`/`E-SURVEY-007`);
- `tools/run_1x_runtime_degradation_hil.py` — exact runtime-source negative lane.
  Он arm one-shot BLE-unavailable result только из idle Home без доступа к
  hardware/storage, запускает public dual-source Survey и требует перехода active
  mask в Wi-Fi-only при продолжении не менее двух real Wi-Fi cycles. Затем lane
  commits, cold-reopens и экспортирует точное unavailable window до возврата Home с
  lease 0. Retained exact run 0.75, пять TFT captures, hashes source/candidate,
  timeline durations, CID и invariant heap независимо проверяет
  `check_runtime_degradation_acceptance.py`
  (`E-AUTO-040`/`E-HIL-100`/`E-SURVEY-013`);
- `tools/run_1x_observation_browser_hil.py` — exact lane общего browser. Он наблюдает
  admitted post-flash boot до любого независимого reset, ждёт один полный real
  Wi-Fi+BLE cycle, переводит focus на Filter для остановки RF и финализации стабильного
  snapshot, затем проходит Все/Wi-Fi/BLE List/Detail и RSSI history. Lane сохраняет
  Session без повторного scan, cold-reopens/экспортирует те же данные и требует final
  lease 0. Exact 0.76 source/candidate/runner, девять TFT captures, filter counts,
  timeline equality, CID, heap и cleanup независимо проверяет
  `check_observation_browser_acceptance.py`
  (`E-AUTO-041`/`E-HIL-101`/`E-SURVEY-014`);
- `tools/run_1x_capture_export_hil.py` — exact lane Capture/export. Он сохраняет
  admitted post-flash boot, создаёт одну real Wi-Fi+BLE Session, commits и cold-reopens
  schema v3, затем проверяет immutable build/receive provenance и потоково принимает
  raw canonical CSV между typed begin/end markers. Проверяются каждые sequence,
  timestamp, source, tuning, RSSI и hex-encoded identity/label row; PCAP обязан вернуть
  `unavailable_no_frame_payload`, пока raw frames не существуют. Exact 0.77
  source/candidate, CSV на 47 rows, десять TFT captures, CID, heap и cleanup независимо
  проверяет `check_capture_export_acceptance.py`
  (`E-AUTO-042`/`E-HIL-102`/`E-SURVEY-015`);
- `tools/run_1x_wifi_frame_capture_hil.py` — exact lane bounded packet Capture. Он
  flash-ит exact candidate, сохраняет admitted read-only product recovery, проходит
  Capture Setup→Running→manual Stop→PCAP→Back и разбирает каждое global/record/radiotap
  поле streamed PCAP. Lane требует RAM bound 16×256 B, учтённый overflow, zero
  invalid/connect/raw-TX/storage calls, пять exact TFT states, payload scrub и final
  lease 0. Passing repository evidence намеренно не сохраняет raw 802.11 или PCAP
  bytes, только hashes и неидентифицирующие counts/tuning/RSSI ranges. Exact 0.78
  независимо проверяет `check_wifi_frame_capture_acceptance.py`
  (`E-AUTO-043`/`E-HIL-103`/`E-CAPTURE-001`);
- `tools/run_1x_persistent_wifi_capture_hil.py` — exact lane persistent Capture. Он
  проходит Capture→Stop→Save→privacy confirm, требует один atomic generation advance
  на exact enrolled CID, scrub-ит live RAM, делает cold reboot, открывает Library
  read-only и требует byte-for-byte равенство её streamed PCAP и live PCAP. Lane также
  связывает heap invariance, zero recovery writes, девять TFT states и final lease 0.
  Raw 802.11 bytes/PCAP остаются только на enrolled SD; retained evidence содержит
  hashes и aggregate metadata. Exact 0.79 независимо проверяет
  `check_persistent_wifi_capture_acceptance.py`
  (`E-AUTO-044`/`E-HIL-104`/`E-CAPTURE-002`);
- `tools/run_1x_self_test_coverage_hil.py` — текущий exact non-destructive lane plan
  v4. Он flash-ит exact candidate, связывает ELF/CID и continuity admitted storage,
  проводит Quick плюс Full/Guided через все пять common UI states и требует ordered
  registry S3/S4 плюс подтверждённый пользователем read-only probe RF shield. Exact
  0.81 проходит 16 checks, отмечает отсутствующие GPS/PN532/IR как три N/A и сохраняет
  только честный blocker total coverage. Дополнительно требуются две plausible nRF24
  identities, CC1101 PARTNUM 0/VERSION 0x14, exact bounds reads/bytes 8/2/20, zero
  CE-high/strobe/TX events, GPIO21 high, cleanup RadioSpi, десять TFT captures и final
  lease 0. `check_shield_receiver_self_test_acceptance.py` rehashes retained bundle
  (`E-AUTO-046`/`E-HIL-106`/`E-SELFTEST-003`/`E-RADIO-001`). Historical exact 0.80
  остаётся independently reproducible: `check_self_test_coverage_acceptance.py`
  получает его runner plan v3 из pinned runner commit;
- `tools/run_1x_full_guided_rf_hil.py` — текущий combined lane plan v7, несмотря на
  историческое имя. Он flash-ит exact bytes, проводит Quick плюс Full/Guided через
  RF, persisted-artifact и disposable-storage phases, снимает 13 TFT states и
  требует exact CID, три isolated writes/504 B, read-only remount/export, typed
  scratch cleanup, unchanged product generation, zero TX/product writes и final
  lease 0. Exact 0.86 и его сохранённый первый fail-closed attempt без timeline
  независимо проверяются `check_full_guided_disposable_acceptance.py`
  (`E-AUTO-051`/`E-HIL-111`/`E-SELFTEST-006`/`E-STORAGE-027`);
- `tools/run_1x_littlefs_parity_hil.py` — fail-closed lane disposable flash. Он
  выбирает только inactive OTA1 `app1`, требует два совпадающих полных чтения и
  firmware-side hash match до format, делает 32 commits common SessionStore плюс
  read-only remount recovery, затем восстанавливает и хеширует OTA1 и partition table
  до cold product-Library check. Passing evidence никогда не сохраняет private
  backup. Exact 0.69 и retained run независимо проверяет
  `check_littlefs_parity_acceptance.py` (`E-AUTO-033`/`E-HIL-093`/
  `E-STORAGE-024`); reset-boundary и physical power-cut lanes остаются отдельными;
- `tools/run_1x_ui_typography_hil.py` — service-free exact-TFT lane typography. Он
  требует уже flashed candidate, проверяет identity запущенного app и hashes candidate
  artifacts, нормализует Home/language/persisted Self-Test mode и снимает 18 EN/RU
  framebuffers через public Actions/queries. Набор включает persistent Library detail,
  Quick result, Full preflight, все пять guided common states и честный blocked result,
  затем возвращает pixel-identical русский Home. Обязательны Quick 8/8, Full 9/10 с
  одним declared blocker, zero side effects/input errors/drops, LOW buzzer, invariant
  heap и final lease 0. Exact 0.63 и собственные final bytes runner независимо
  проверяет `check_ui_typography_acceptance.py`
  (`E-AUTO-027`/`E-HIL-087`/`E-UX-008`);
- `tools/run_1x_release_hil.py` — release-facing foreground orchestrator. Он сначала
  запускает product, получает exact CID только из admitted enrollment, безопасно
  удаляет лишь enrollment в NVS, прошивает и запускает generic `device-smoke`
  revision 6, выполняет exact-CID read-only re-enrollment и доказывает финальный
  enrolled boot в Home с owner none/lease 0; `verify_1x_release_hil_bundle.py`
  независимо проверяет оба дочерних bundle и каждый state boundary до GitHub attestation;
- golden bootstrap создаёт только отсутствующие compressed RGB565 и отказывается
  перезаписывать существующие; обычный run требует exact Home/Back и masked-exact
  Diagnostics с одной явной dynamic region;
- `tools/verify_1x_prerelease_bundle.py` пересчитывает каждый artifact, сверяет exact
  candidate, suite/version, полный ESP app ELF SHA-256 и local-result binding;
  unsigned local result отвергается по умолчанию и может быть только
  development-verified явным флагом внутри уже GitHub-verified archive;
- `tools/esp_app_identity.py` независимо читает 32-byte ELF digest из app descriptor,
  а firmware публикует тот же digest из descriptor запущенного образа в cold boot и
  `metrics`; runner не начинает release-eligible result при любом несовпадении;
- host tests намеренно ломают manifest, app descriptor, unmasked pixel, artifact,
  candidate hash и build identity;
- runner создаёт random 128-bit run ID; firmware принимает `hil.begin` только при
  exact running app identity, запрещает nested session и завершает только тот же ID.
  Manifest, begin/end, run и local result обязаны совпасть;

Текущая прямая команда product lane:

```bash
python tools/run_1x_product_survey_hil.py \
  --port /dev/cu.usbmodem2101 \
  --firmware firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.bin \
  --expected-version 0.62.0-input-probe-resilience-measure \
  --output /tmp/leshy-product-survey-hil --flash
```

Dedicated regression отмены active scan:

```bash
python tools/run_1x_product_survey_cancel_hil.py \
  --port /dev/cu.usbmodem2101 \
  --firmware firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.bin \
  --expected-version 0.62.0-input-probe-resilience-measure \
  --expected-cid FE343253440000002000000055019CB7 \
  --output /tmp/leshy-product-survey-cancel-hil --flash
```

Dedicated regression terminal state при missing source:

```bash
python tools/run_1x_product_survey_missing_source_hil.py \
  --port /dev/cu.usbmodem2101 \
  --firmware firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.bin \
  --expected-version 0.68.0-missing-source-tft-measure \
  --expected-cid FE343253440000002000000055019CB7 \
  --output /tmp/leshy-product-survey-missing-source-hil --flash
```

Exact regression typography после build и flash того же candidate:

```bash
python tools/run_1x_ui_typography_hil.py \
  --port /dev/cu.usbmodem2101 \
  --expected-version 0.63.0-roboto-condensed-ui-measure \
  --expected-app-elf-sha256 3171e472c40c49484922c9c1b0ca82b60f2a3b71deedeaf8008604d8751eb01a \
  --firmware firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.bin \
  --factory firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.factory.bin \
  --map firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.map \
  --output /tmp/leshy-ui-typography-hil
```

- без `--expected-cid` CID определяется только из admitted enrollment с совпадающими
  expected/observed 32-byte fingerprints; явное значение остаётся для jobs с
  выделенной media;
- candidate сначала копируется в `candidate/firmware.bin` внутри нового bundle,
  повторно хешируется и только затем прошивается; verifier по умолчанию использует
  эту indexed copy, поэтому evidence не зависит от mutable build path;
- `tools/package_1x_prerelease_bundle.py` создаёт deterministic `tar.gz`, а
  `.github/workflows/prerelease-hil.yml` собирает candidate один раз, GitHub-attests
  его, запускает combined physical HIL в `hil-production`, attests evidence archive и
  в отдельном promotion job повторно проверяет оба provenance records, обе HIL lane,
  восстановление state и same bytes;
- ad-hoc Ed25519 signing удалён из production design: ни runner, ни verifier не
  принимают локальную подпись за release trust;
- `tools/release_1x.py check` автоматически выполняет preflight→dispatch→cloud
  build→ephemeral one-job runner→physical HIL→promotion-proof и сохраняет только
  disposable локальную квитанцию; `publish` повторно доказывает provenance/same bytes
  и создаёт 1.x Release без rebuild. Host tests покрывают SemVer/run identity, exact
  artifact set, serial selection и unsafe archive rejection.

Foreground endurance lane компонует ту же exact product command и не создаёт
resident agent или macOS service:

```bash
python tools/run_1x_product_endurance_hil.py \
  --port /dev/cu.usbmodem2101 \
  --firmware firmware/leshy1/.pio/build/esp32-div-v2-clean/firmware.bin \
  --expected-version EXACT_CANDIDATE_VERSION \
  --output /tmp/leshy-product-endurance-hil \
  --duration-seconds 2700 --minimum-cycles 8 --maximum-cycles 12 \
  --interval-seconds 300 --flash --release-endurance
```

Он прошивает только cycle 1, а в следующих проверяет continuity candidate/app/CID.
После каждого child сохраняются aggregate run и SHA-256 index. Каждый цикл обязан
продвинуть ровно одну generation, сохранить scan/pipeline drops равными нулю,
выполнить два read-only recovery boots, удержать четыре GRAM captures, не изменить
первый heap tuple и закончить на Home без owner/lease. Heartbeat каждые 30 секунд
делает одноразовый foreground process наблюдаемым. `--release-endurance` отклоняется,
если не заданы verified flash, configured duration 2 700…3 600 секунд и минимум
восемь cycles. Он также fail closed, если measured elapsed превышает часовой
операционный budget. Короткий development run даже при pass остаётся
`gate_eligible=false`. Обычный release gate ожидаемо занимает около 47–50 минут;
двухцикловый regression имеет execution budget десять минут.

Release cycles сохраняют ровно `setup`, `paused`, `committed` и `export`: `paused` —
стабильное RF-off состояние browser после одного Wi-Fi и одного BLE scan. Firmware
собирает observations в RAM, полностью останавливает оба radio adapter, повторно
идентифицирует exact CID и только затем открывает SD для atomic commit, поэтому
release evidence fail closed при пересечении lifecycles radio и storage.

`E-HIL-059` — первый сохранённый smoke runner: три цикла, шесть cold boots,
generation 12→15, 51/51 observations, zero drops/heap drift и final lease 0. Он
намеренно не считается endurance evidence и предшествует текущей policy
≥45 минут/≥8 циклов; physical power-cut и external-camera subset также остаются
отдельными gates.

Первая попытка release-endurance 0.46 сохранена как `E-HIL-060`, а не отброшена:
она положительно выполнила reset-separated boot retry, а затем fail-closed поймала
отдельный raw-identity transient на Product Start. Узкий retry 0.47 исправил этот
вход, но `E-HIL-061` обнаружил lower boot-recovery call, который не вернулся.
Поэтому final 0.48 связывает RTC retry state с exact app, повторяет Product Start
только до filesystem access и окружает enrolled boot recovery independent-core
watchdog 4 s. Watchdog не пишет log и не запускает shutdown handlers: он сохраняет
только RTC state и вызывает `esp_restart_noos`. `E-HIL-063` детерминированно
инъецирует timeout и read-only восстанавливает generation 27 с zero SD writes;
`E-HIL-064` затем продвигает 27→30 с 45/45 observations, zero drops и invariant
heap. Retained incident/regression artifact проверяет
`check_product_recovery_acceptance.py`; по действовавшей тогда policy это всё ещё был
короткий local result, а не release gate 8 h.

Следующая release-попытка 0.48 сохранена как `E-HIL-065`: cycle 1 исчерпал все три
Product Start identity attempts с пустым CID, затем проявил host `TypeError`
summarizer на намеренно неполной записи failed child. Aggregate checkpoint
восстановлен как failed. Runner теперь проверяет отсутствующие retry/timeout metrics
без exception и сохраняет любой неожиданный orchestration exception в terminal
checkpoint.

`E-HIL-066` сравнивает по 32 isolated identification-only runs на каждой частоте. На
той же board/card 400 kHz дали 13/32 valid и серию из семи failures, а 100 kHz —
24/32 и maximum streak два. Все attempts были read-only, очищали bus и возвращали
ownership в zero. Поэтому candidate 0.49 использует 100 kHz и допускает максимум
восемь cleaned raw-only Product Start attempts, включая parse rejection с пустым
CID, до любого filesystem call. Затем `E-HIL-067/068` проходят exact product cycle
и three-cycle regression 35→38 с 46/46 forwarded, zero drops, invariant heap и final
lease 0. Retained artifact проверяется
`check_product_start_resilience_acceptance.py`; действовавший тогда gate 8 h/32
cycles оставался открыт.

Затем release lane 0.49 завершил шесть cycles (generation 38→44, 96/96 forwarded,
zero drops и invariant heap), но cycle 7 после 5 719,273 s исчерпал отдельный boot
budget из трёх attempts (`E-HIL-069`). Безопасный немедленный probe получил exact
CID в 6/8 attempts, доказав, что media сохранилась, а failure был transient.
Предложенный R1 poll 64 byte отклонён по результату read-only experiment 32+32
`E-HIL-070`: он не улучшил valid reads относительно сохранённого limit 16 byte.
Candidate 0.50 вместо этого выравнивает narrow reset-separated boot policy с
существующим budget Product Start восемь attempts. Exact three-cycle regression
`E-HIL-071` продвигает 44→47 с 39/39 forwarded, двумя natural boot retries, zero
drops/heap drift и lease 0. Retained artifact проверяет
`check_product_boot_resilience_acceptance.py`; свежий run по действовавшей тогда
policy 8 h/32 cycles всё ещё был обязателен.

Этот свежий lane 0.50 сохранён как failed `E-HIL-072`: cycle 1 продвинул 47→48 с
16/16 forwarded и clean final lease, но cycle 2 после двух clean boot retry records
завис за третьим ROM app entry. Scheduler-based watchdog 4 s не выполнил reset;
безопасные DTR/RTS и loader probes не получили serial data. Final cleanup/lease/write
state неизвестен и поэтому fail closed. Candidate 0.51 добавляет panic-enabled
hardware Task WDT tier, IRAM hook которого сохраняет только armed exact-app timeout.
После physical power recovery `E-HIL-073` прошивает/verifies exact candidate,
наблюдает Task WDT на `loopTask`, reset reason 6 и read-only recovery attempt 2 с
`timeout_restarts=1`, zero writes, complete cleanup и lease 0. Затем `E-HIL-074`
продвигает 48→51 с 37/37 forwarded, шестью cold boots, zero drops/heap drift и final
lease 0. Retained failure и успешный fix проверяет
`check_product_hardware_watchdog_acceptance.py`; на тот момент до promotion оставался
только новый полный результат по policy 8 h/32 cycles.

Local combined run `E-HIL-055` прошёл на exact candidate 0.45: product run
`408bad8f085d7012fbc85fa57bdd363d` committed generation 4→5 с 20 passive Wi-Fi
observations, generic run `9c81c9f3d0f9cb0bdb69ebc8d002e8ce` прошёл все десять
goldens revision 6, а read-only re-enrollment и финальный cold boot восстановили
generation 5/20 с zero SD writes и lease 0. Independent verifier принял все 64 файла;
deterministic archive — `760fad19…6abad`. Этот standalone archive остаётся local
evidence; каноническое release trust даёт следующий GitHub-native run.

GitHub-native combined run
[`31987498533`](https://github.com/anton-vinogradov/esp32-leshy/actions/runs/31987498533)
на commit `b878b95` прошёл build/physical/promotion за 2:32/1:39/0:30. GitHub-attested
app `05865dc1…18d1a9` и evidence archive `fcc1e5fe…5992` прошли provenance и inner
same-byte verification. Product run `7476ff6b2c0d96a5332e01079302662d` committed
generation 5→6 с 16/16 passive observations; generic run
`a15e136702f65bb29cb811e74d29c330` прошёл десять goldens; финальный read-only
re-enrollment восстановил 6/16 с zero SD writes и lease 0. Ephemeral runner удалил
credentials и registration, число repository runners вернулось к нулю, а measurement
version корректно получила `VALIDATION PASSED — NON-PUBLISHABLE VERSION` без Release.

Первый bootstrap run `31975374875` fail-closed остановился до runner registration и
flash на безопасной внутренней symlink official archive; workflow был отменён,
registered runners осталось 0. После разрешения только archive-internal links и
negative escape test повторный run
[`31975573475`](https://github.com/anton-vinogradov/esp32-leshy/actions/runs/31975573475)
на commit `97e7145` прошёл полностью: cloud build/attestation 2:26, physical HIL 59 с,
promotion-proof 31 с. Exact app `ef08797c…9d63a`, factory
`87457cc7…280af`, ELF `e2d5b32c…edb94` и evidence archive
`d395d913…162d` GitHub-attested. Board ready 502,053 ms; Actions 85,164/95,840 ms;
Home/Diagnostics/Back дали 0 mismatched pixels; final owner none/lease 0, heap
238 728/233 332 B free/min, GPIO2 LOW. Session ID
`abbcd74e55aa5c05cfbb4f11a6492902` совпал во всех boundaries. Ephemeral runner
удалил credentials/registration и завершился; repository runners после run — 0.
Measurement version намеренно non-publishable.

Финальный hardened run
[`31976152593`](https://github.com/anton-vinogradov/esp32-leshy/actions/runs/31976152593)
на commit `714ac83` повторил весь контур с exact pinned Node.js 24 Actions без
compatibility fallback: cloud build/attestation 2:30, physical HIL 56 с,
promotion-proof 28 с. Exact app `16ab071a…7799a`, factory `05013e92…f3f9`, ELF
`70ee2b5d…da1`, map `e2761e95…56f1` и evidence archive `1799719f…5bd` прошли
attestation/same-byte verification. Run ID
`1585357a5c3b4f5bf70dec0e3b5fe317`; ready 501,840 ms, Actions 85,126/95,192 ms,
три TFT comparison дали zero mismatch, final owner `none`/lease `0`, heap
total/free/min 281 392/238 728/233 332 B, GPIO2 LOW. Runner удалил credentials и
registration, repository runners осталось 0; команда корректно завершилась
`VALIDATION PASSED — NON-PUBLISHABLE VERSION`, release не создавался.

Board-01 дважды получила app candidate SHA-256
`e95d7ede560943744f9b981bf2063b6f31077b600198bc8fa6a528c77e04441b`.
Первый run создал отсутствующие golden после визуального review; второй заново
прошил те же bytes и прошёл cold boot→Home→Diagnostics→Back с 0 mismatched pixels,
ready marker 501,72 ms, action acknowledgements 84,204/95,963 ms, финальными
owner `none`/lease `0`, heap free/min 238 832/233 436 B и GPIO2 LOW. Runner result
`passed=true`, `gate_eligible=true`; bundle verifier даёт
`development_verified=true`, но `release_eligible=false`, потому что этот исторический
run выполнялся вне GitHub attestation workflow. `run.json` SHA-256:
`16136f08…780f17`.

Следующий candidate `0.36.0-prerelease-build-identity-measure` добавил независимую
runtime identity. App SHA-256 `47bd62ad…66cecd5` содержит ELF SHA-256
`2e5dfcc2…274e6`; runner извлёк его до flash, а cold boot и повторный `metrics`
сообщили тот же полный digest. Исправленный physical run `c` прошёл ready за
505,962 ms, Actions за 85,338/94,918 ms и три visual comparisons с zero mismatch;
`run.json` `d011e052…60dbf8`, artifact index `c021993e…4f318`. Два предыдущих
прогона намеренно остались failed evidence: первый обнаружил сокращённый runtime
digest, второй — отказ bounded formatter печатать oversized boot record. Они
подтверждают fail-closed поведение, но не засчитываются как gate pass.

Candidate `0.37.0-prerelease-test-session-measure` завершил test-session envelope.
Self-contained physical run `b` прошил bundled app SHA-256 `25f1bacb…cd83c6` с ELF
SHA-256 `0c5277bb…ef7ed8`. ID `803dd8cfbd28657240fd64af50019588`
совпал в manifest, device begin/end, run и attestation; session active true→false,
UI revision 0→2. Ready занял 502,245 ms, Actions 84,116/95,379 ms, три TFT
comparisons дали zero mismatch. `run.json` `8466fe45…d76948`, artifact index
`2f3cb367…4be3e7`; verifier прошёл без внешнего candidate argument.

Candidate `0.38.0-product-survey-workflow-measure` расширил `device-smoke` до
revision 2. Локальный full-suite run `ddf0203694d3011788f1762cec64ff11`
прошил exact app `9240cccc…c3e370`, достиг ready за 502,731 ms, выполнил 17 Actions
и проверил idempotent Stop (`changed=false`). Десять real-TFT comparisons дали zero
mismatch; serial export сохранил generation 2, три observations, zero drops и
`simulated=true`/`persistent=false`/`radio_touched=false`. Final owner `none`, lease
`0`, heap total/free/min 281 360/238 696/233 300 B, GPIO2 LOW; `run.json`
`af5d493f…c2a7`, artifact index `c73f08d1…6376d`. Это local development evidence;
GitHub-native attestation revision 2 ещё не запускалась.

Candidate `0.39.0-product-survey-pipeline-measure` добавил в тот же сценарий
реальный bounded software FIFO между simulated source и Survey. Suite revision 3
требует переход pipeline ready→drained→committed, counters received/forwarded 3/3,
depth 0, high-water 3, drop 0 и batch trigger none→stop. Full run
`dc64d3b8d0438567a737f9a97d1cf078` прошил exact app `3f3b487b…d3fb19`, достиг
ready за 502,915 ms и выполнил 17 Actions максимум за 98,594 ms; десять TFT frames
совпали с reviewed goldens без единого pixel mismatch. Final owner/lease `none`/`0`,
heap total/free/min 281 272/238 608/233 212 B, GPIO2 LOW; `run.json`
`9716a080…074a8f`, index `27da0a1c…cd2b6`. Это local development evidence;
GitHub-native revision-3 attestation ещё не запускалась.

Candidate `0.40.0-product-admission-policy-measure` поднял suite до revision 4 без
изменения экранов/goldens. Новый bounded query до любого hardware I/O требует
`explicit_start_required`, store `missing_media`, точный `/leshy/sessions/v1`,
combined resources 14, passive/persistent true, simulated fallback false и
hardware/radio/mount/write false. Full run `51a294577b902dd2bd1ed53908e86597`
прошил exact app `83cac871…4d25844`/ELF `dadad5b7…503713`, достиг ready за
507,234 ms и сохранил 17 Actions максимум 99,066 ms, десять zero-mismatch TFT
comparisons, final owner/lease `none`/`0`, heap total/free/min
281 272/238 608/233 212 B и GPIO2 LOW. `run.json` `6361d40e…deafaa`, index
`e3796ec3…9608f1`; verifier подтверждает unsigned local development evidence, но
не release eligibility. Реальный product RF/SD lifecycle этот run намеренно не
запускал.

Candidate `0.41.0-keypad-frontend-measure` поднял suite до revision 5 после physical
регрессии responsiveness, которая показала, что serial Actions не проверяют frontend
PCF8574. Candidate делает sampling/debounce в отдельной задаче и ставит stable
transitions в очередь независимо от синхронной TFT redraw. Run
`490608019ef55ae5c230ed1254a82fad` прошил exact app
`03dc165c…70c05c5`/ELF `21f31ab2…ae8958`, достиг ready за 503,916 ms, измерил
maximum keypad sample gap 5 ms при 930 valid/0 erroneous reads и zero queue drops,
сохранил десять zero-mismatch TFT comparisons. Final owner/lease `none`/`0`, heap
total/free/min 281 184/233 556/228 160 B, GPIO2 LOW. `run.json`
`ab29096a…b97ee`, index `3b3a3ccb…a0f8ce`. Этот automatic run подтверждает
deployed frontend/task/queue contract, но намеренно не может создать physical switch
edges; UI-HIL-A8 остаётся отдельным guided pre-release artifact.

Guided edge test затем поймал два дефекта, недоступных serial-only suite. На 0.41
хаотичный run поймал 43 presses/43 releases без I2C error, но потерял 46 queued
press/release transitions. На 0.42 press-only queueing и state batching всё ещё
доставили лишь 27 из 48 пойманных presses и потеряли 21: per-action diagnostic output
и очередь 16 оставались в consumer path. Оба automatic runs были зелёными, поэтому
это явное negative evidence `E-HIL-050/051`.

Candidate `0.43.0-keypad-burst-buffer-measure` поднял suite до revision 6, использует
ordered press-only queue 64, применяет накопившиеся actions до одной TFT redraw и
публикует одну diagnostic record на batch. Automatic run
`d28fac6bd45fc9713d7e5e1f114af86c` прошил exact app
`cf0adf5a…befbab0`/ELF `8114a78b…eec75e`, достиг ready за 503,657 ms, сохранил
десять zero-mismatch frames, final owner/lease `none`/`0`, heap total/free/min
281 176/233 140/227 744 B, GPIO2 LOW. `run.json` `1990446e…9e1e46`, index
`742ee472…2d557`. Bound physical artifact UI-HIL-A8 затем зафиксировал ровно десять
каждой кнопки, 50 presses, 50 releases, 50 public UI dispatches/revisions, maximum
sample gap 5 ms, high-water 6/64 и нули I2C errors, ambiguity, residual depth/drops.
SHA-256 сохранённого physical artifact: `c7b8af2e…7523dbdc`.

Историческая копия этого real bundle была подписана временным Ed25519 key и получила
`release_eligible=true`, после чего temp key и copy уничтожены. Эксперимент
`E-AUTO-003` доказал механику, но product decision от 2026-08-17 отверг постоянный
station key; соответствующий production code path удалён. `hil-production` ограничен
ровно branch `main`, а GitHub workflow path закрыт evidence выше. Открыты
queue/quarantine и расширение release-candidate suite.

Низкоуровневая GitHub-native проверка для диагностики:

```sh
gh attestation verify <artifact> \
  --repo anton-vinogradov/esp32-leshy \
  --signer-workflow anton-vinogradov/esp32-leshy/.github/workflows/prerelease-hil.yml \
  --source-ref refs/heads/main \
  --source-digest <commit-sha>
```

Candidate и evidence archive хранятся как GitHub Actions artifacts конкретного run;
attestations — в GitHub/Sigstore. После promotion те же exact bytes и evidence должны
быть приложены к GitHub Release. Секретного signing key хранить негде и не требуется.

Принятие ADR-005 разрешает поэтапную реализацию этого контура. Release workflow 0.x
ограничен собственными `v0.*` tags; наличие контракта или незапущенного runner само
по себе не считается закрытым release gate.

Product decision от 17 августа 2026 года остановил 0.51 lane после 12 полностью
зелёных циклов/11 330,816 s, чтобы перейти S1→S2. `E-HIL-075` сохраняет aggregate и
все child hashes, generation 51→63, 144/144 observations, 24 cold boots, 48 TFT
captures, invariant heap и zero drops/retries/timeouts. Runner остаётся честно
`interrupted`/`gate_eligible=false`: это принятое engineering evidence текущего
slice, а не release promotion. 18 августа 2026 года критерий заменён NFR-004:
≥45 минут и ≥8 полных циклов при configured и measured elapsed не более одного часа
на готовом exact cross-radio passive candidate. Прежний run 8 h остаётся только
необязательной extended qualification после крупных storage/runtime/radio changes и
никогда не блокирует обычный release.

Exact 0.89 — первый принятый результат по этой policy. `E-HIL-114` сохраняет exact
source/binaries, восемь child runs и 32 TFT captures в indexed bundle из 160 файлов.
Run длится 2 799,845 s, продвигает generation 86→94, передаёт 111 Wi-Fi плюс 256 BLE
observations через 16 cold boots, сохраняет heap точно 231 772/166 812/147 460 B,
фиксирует zero drops/timeouts и завершает каждый цикл с owner/lease `none`/`0`.
Independent verifier `E-AUTO-054` заново выводит каждый claim. Это закрывает release
endurance; controlled physical power cut остаётся отдельным gate S4.

Exact 0.90 добавляет product-menu lane до любой последующей release promotion.
Runner проходит каждый домен Home, отклоняет disabled Цели/Лабораторию, открывает
вложенные пункты Устройства обычными Actions и общей touch row, сохраняет восемь
TFT states, проверяет non-interactive chrome и заканчивает Home с zero ownership.
Retained bundle `E-HIL-115` содержит exact bytes firmware/factory/ELF/runner и
первый runner-only failure ожидания revision; `E-AUTO-055` независимо проверяет все
hashes, source contracts, screenshots и final cleanup. Это принимает IA, но не
оставшийся gate controlled physical power cut.

Exact 0.101 закрывает этот gate S4 без always-on workstation service.
`tools/run_1x_sd_power_cut_matrix.py` запускается только при подключённом устройстве
для проверки candidate. Он связывает version, source commit, firmware/app hash,
exact CID и USB serial/VID/PID, сохраняет checkpoint каждой из шести boundaries и
отказывается продолжать без реального disconnect, отсутствия USB endpoint минимум
три секунды, той же identity после reconnect и read-only recovery с `POWERON`.
`E-HIL-126` фиксирует шесть blackout 5,216…6,589 s, generations 1/1/1/1/1/2, zero
recovery writes/syncs, полный cleanup и lease 0. Предыдущий exact candidate
regression проходит 17 TFT states и сохраняет product 95/0. `E-AUTO-066` проверяет
retained summary и exact source/tool hashes. Вместе с endurance exact 0.89
`E-GATE-005` закрывает `DEMO-S4`; S5 активен. Это stage evidence, а не signed
promotion release candidate.
