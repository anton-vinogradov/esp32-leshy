# ESP32-Leshy 1.x — автоматический предрелизный HIL

*Читать на: [English](PRE_RELEASE_HIL.md) · **Русский***

Статус документа: **принятый операционный контракт ADR-005; implementation v0.4**.

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

В release binary разрешены только read-only evidence, обычные пользовательские
Actions и безопасные штатные операции. Fault injection, произвольные GPIO/RF
команды, raw memory и обход permissions туда не входят. Разрушительные storage/
power-cut/radio HIL выполняются отдельной diagnostic image или внешним оборудованием;
их evidence дополняет, но не заменяет smoke на точных release bytes.

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
   orientation/physical damage, которые GRAM readback принципиально не видит.

Глобальный permissive pixel threshold запрещён: он может скрыть пропавший critical
text или selection. Обновление golden требует просматриваемого image diff, причины и
version bump suite; runner не перезаписывает baseline автоматически.

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
| `device-smoke` | каждый merge/доступная станция | flash, cold boot, Home/Diagnostics/Back, product Survey→commit→Library→export, TFT, resources, safe outputs |
| `device-regression` | nightly/изменение firmware | все доступные non-destructive workflows, EN/RU golden matrix, repeated navigation, storage read/reopen |
| `release-candidate` | перед публикацией | полный применимый Stage Demo, install/update/rollback, reboot paths, destructive HIL attestations, budgets и обязательный camera subset |

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
| Полный self-test внутри firmware | работает без host, простой запуск на заводе | firmware проверяет само себя; code/flash overhead; трудно менять golden и release policy | только low-level POST/module checks |
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
и combined product/generic lane. Прежний generic-only GitHub workflow прошёл;
обновлённый combined workflow реализован и доказан локально, но ещё требует первого
GitHub OIDC-attested run:

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
  допускает запись только после bounded cached-FSInfo и непротиворечивого passive-scan
  accounting, commits ровно следующую generation, снимает TFT
  Setup/Running/Committed/Export, проверяет persistent Library export и заканчивает
  lease 0. Retained board run 0.45 machine-checked через
  `check_product_survey_acceptance.py`;
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
  --expected-version 0.45.0-product-survey-measure \
  --output /tmp/leshy-product-survey-hil --flash
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

Local combined run `E-HIL-055` прошёл на exact candidate 0.45: product run
`408bad8f085d7012fbc85fa57bdd363d` committed generation 4→5 с 20 passive Wi-Fi
observations, generic run `9c81c9f3d0f9cb0bdb69ebc8d002e8ce` прошёл все десять
goldens revision 6, а read-only re-enrollment и финальный cold boot восстановили
generation 5/20 с zero SD writes и lease 0. Independent verifier принял все 64 файла;
deterministic archive — `760fad19…6abad`. Результат не release-eligible, пока
обновлённый workflow не добавит GitHub Artifact Attestations.

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
