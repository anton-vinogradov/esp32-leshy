# ESP32-Leshy 1.x — реестр рисков

*Читать на: [English](RISK_REGISTER.md) · **Русский***

Статус документа: **активный реестр S1**. `STATUS` хранит текущее состояние этапа;
этот файл хранит устойчивые risks, controls, triggers и closure evidence.

## Оценка и обработка

- Likelihood и impact принимают `low`, `medium` или `high`; это приоритеты, а не
  вымышленные численные вероятности.
- Treatment: `avoid`, `reduce`, `constrain`, `transfer` или `accept`.
- Risk остаётся `open` до появления closure evidence. Документированный fallback
  может сузить product scope, но не доказывает безопасность неизвестного hardware.
- Новый факт, нарушающий accepted requirement или stage gate, пересматривается по
  `GOVERNANCE`, а не молча меняет implementation.

## Реестр

| ID | Risk / trigger | L | I | Treatment и текущий control | Owner / closure evidence | State |
|---|---|---|---|---|---|---|
| R-001 | ESP32 module/PSRAM variants различаются между партиями v2; observed board-02 заменяет N16 на N16R8, чьи Octal pins конфликтуют с display | H | H | portable profile держит PSRAM выключенной и классифицирует N16R8 отдельно; ROM-reported memory не расширяет budgets | boards; exact assembly IDs и pin-compatible display/PSRAM proof, если такой profile существует | reduced/open |
| R-002 | Legacy `TFT_RST=0` управляет BOOT, а schematic ведёт TFT reset к RESET/EN | M | H | GPIO0 не используется для output/reset probe; clean profile считает reset внешним | boards/display; HW-T02 continuity/logic evidence | open |
| R-003 | Общие SPI-транзакции SD/NRF/CC/PN532 портят storage или зависают receiver | H | H | эксклюзивные operation leases `spi_radio`; transparent sharing запрещён до traced endurance | kernel/drivers/storage; HW-T03/HW-T05 + RB-07 | open |
| R-004 | Мультиплексирование GPIO5/6, GPIO14/21 или GPIO2 вызывает contention, TX, звук или ложный battery result | H | H | explicit assembly profile; GPIO2 удерживается OUTPUT LOW до bounded sound service и не читается как ADC; остальные contested output probes запрещены | boards/drivers; buzzer boot/runtime state + audible observation, HW-T07…HW-T09 | reduced/open |
| R-005 | Пики receiver/backlight/SD вызывают brownout, перегрев или потерю данных | M | H | unmeasured combinations выключены по RB-08; Wi-Fi-first slice не требует shield concurrency | boards/power; HW-T10 rail/thermal matrix | open |
| R-006 | Power loss/cancel портит Session/Capture или старую committed запись | M | H | append-only/immutable source model; обязательны atomic-storage ADR и fault matrix | storage; WF-02-A4, WF-03-A3, PR-005 | open |
| R-007 | No-PSRAM heap pressure, fragmentation или unbounded queues ломают долгий Survey | H | H | RB-03/04, bounded queues/pools, high-water/drop counters, отсутствие monotonic heap decline | kernel/services; size gate + release endurance с часовым бюджетом; optional extended qualification после крупных runtime changes | open |
| R-008 | UI/driver блокирует core, Back запаздывает или worker/lease переживает navigation | M | H | единый Navigator event path; callbacks ≤10 мс; cancel token; atomic release ResourceBroker | kernel/UI; WF acceptance traces, NFR-002/003/006 | reduced/open |
| R-009 | Active action запускается вне Lab policy или физически не останавливается | M | critical | никакого shipped TX без finite lease, visible state, independent stop HIL и region policy | safety/kernel/drivers; WF-05-A1…A5 + physical detector trace | open |
| R-010 | Malformed capture/import/schema input перезагружает или исчерпывает device | H | H | length/bounds до allocation, version rejection, fuzz corpus, immutable originals | parsers/storage; WF-03-A4, NFR-007…009 | open |
| R-011 | Ошибка update/signing/rollback brick-ит device или ставит недоверенный build | M | H | два bootable slots, signed manifest/image, сохранённый recovery path и HIL | update/platform; PR-010 rollback/recovery matrix | open |
| R-012 | Drift framework/library или заброшенная dependency ломает reproducible builds | M | H | pinned toolchain/direct dependencies; framework за platform adapters; CI из clean cache | platform; toolchain ADR + clean reproducibility job | open |
| R-013 | Feature-count competition снова создаёт монолит 0.x и откладывает Survey outcome | H | H | каждое изменение связано с J/PR/WF и текущим stage; menu parity не requirement | product/architecture; traceability review на каждом gate | reduced/open |
| R-014 | Credentials, точная location, MAC или captured payload уходят в logs/exports | M | H | redacted defaults; explicit data selection; private recovery backup не коммитится | services/security; report/export scans and permission tests | open |
| R-015 | Отсутствие continuity/logic/RF/power instruments создаёт ложную уверенность даже при двух платах | H | H | evidence маркируется partial; RF board-02 остаётся `fault`; unknown остаётся unknown; cross-swap/emission запрещены до admission rail/pinout | hardware QA; comparative continuity/rail плюс named HW-T evidence | accepted constraint |
| R-016 | Изменение schema или Action API ломает stored evidence/companion clients | M | H | version every boundary, forward migrate или clear reject, immutable source data | services/SDK; schema/Action ADRs + migration contract tests | open |
| R-017 | EN/RU или color-only UI скрывает safety/error meaning или обрезает control | M | M | один string catalog/build, snapshot fixtures, standard-button coverage, no color-only state | UI/product; WF snapshots + NFR-010 matrix | open |
| R-018 | Fatal fault main loop/worker оставляет software-controlled outputs активными или тихо перезагружается в то же unsafe operation | M | critical | permanent panic Task WDT main loop; IRAM quiesce GPIO2/14/15/47; exact-app torn-write-resistant RTC latch; no automatic clear; Safe Mode блокирует product workers и normal Actions | safety/platform; exact 0.103 `E-AUTO-068`/`E-HIL-128`/`E-SAFETY-001` принимает настоящий main-loop watchdog, retained latch при software reset, inactive pads и TFT path explicit clear; worker heartbeats и independent physical-stop HIL остаются closure work | reduced/open |
| R-019 | Clone/DNP assembly сохраняет корпус и menu, но меняет module population, shared-radio wiring либо RF front ends; board-02 имеет valid idle rails, а её assembled RF carrier clamps shared MISO LOW; upstream issue #102 независимо сообщает ту же форму all-radio failure из-за interboard faults | H | H | exact assembly profiles; сравнение BOM/photo/ROM; safe read-only identity и pull characterization до любого TX; powered-off comparison 23/32 кОм отвергает hard short; exact 0.131 меняет GPIO13 LOW→HIGH при снятии carrier; exact 0.132 доказывает все четыре CSN HIGH, пока reassembled MISO LOW при zero bus/TX activity; вид antenna не разрешает изменения пайки; board-02 остаётся RF-fault/no-cross-swap | boards/RF; вернуть/заменить carrier/device либо физически изолировать MISO/power modules; потребовать repaired plausible same-image identity до bounded regression | reduced/open |
| R-020 | Defensive detector или channel/auth analysis показывает false conclusion как угрозу или proof | M | H | каждый вывод показывает detector/version/threshold/confidence/uncertainty и exact evidence; insufficient fixtures остаются inconclusive; automatic response отсутствует. Exact dev.210 фиксирует эти правила для первого Wi-Fi disconnect-burst detector и исключает dependencies driver/TX; dev.211 валидирует reports и замораживает evidence-strength order; dev.212 отвергает противоречивые status/counters/evidence bounds и даёт bounded текст EN/RU, поэтому цвет никогда не является единственным значением; dev.213 явно рисует empty input как capture-not-started; dev.214 добавляет bounded live passive Wi-Fi evidence, но observed/drop counters, zero coverage и incomplete cleanup fail closed; dev.215 добавляет второй SSID/security conflict indicator над complete evidence, называет его medium-confidence проверкой вместо proof evil twin и сохраняет оба exact BSSID/security/source reference; dev.216 делит один live buffer между reserved slots отключений и deduplicated exact identity profiles, включает detector только после полного cleanup и превращает malformed/oversized/capacity loss в incomplete evidence; dev.217 добавляет третий индикатор быстрой смены видимых имён одним BSSID, считает допустимый multi-SSID medium-confidence поводом для проверки, игнорирует повторы имён, fail closed для split/stale/malformed evidence, сохраняет exact references и не заявляет PineAP или атаку; dev.218 добавляет default-off BLE tracker-compatible presence по exact группам protocol/address-type/identity, трактует confidence как повторное presence, а не ownership или unwanted tracking и fail closed для ambiguous/incomplete evidence; dev.219 даёт finding отдельный owner-unknown copy EN/RU и details source-record/time/RSSI, независимо от Wi-Fi валидирует Bluetooth identity и zero-channel evidence; dev.220 сохраняет exact повторные BLE reports только для этого detector, разделяет raw/retained/lost accounting и fail closed при malformed, queue или capacity loss; dev.221 запускает BLE после complete Wi-Fi cleanup на существующем supervised worker, отвергает stale generations и требует exact accounting плюс cleanup до publication, а Back/safety/deadline и pre-start latch делают отмену fail closed; dev.222 добавляет bounded индикатор same-channel elevated noise над правдоподобными RX metadata ESP32-S3, всегда называет его Low-confidence возможной помехой с неизвестной причиной, никогда не идентифицирует источник и не доказывает глушение, а invalid/missing/lost metadata превращает в incomplete evidence; automatic response по-прежнему отсутствует | analytics/product; `E-BUILD-159…171`/`E-AUTO-133…145` — partial control; live golden + negative corpora WF-06-A1/A2 и consolidated physical TFT evidence drilldown/cleanup всё ещё закрывают risk | reduced/open |
| R-021 | Authentication frames, precise tracks, lock state/recovery data или automation transcripts раскрывают sensitive information либо блокируют owner | M | H | encrypted/scoped storage, redacted defaults, explicit export selection, bounded retries и tested owner recovery; safe cleanup/recovery не требует unlock | security/storage; PR-021/022/024 privacy, recovery и export matrix | open |
| R-022 | Connected BLE, UART, CLI, USB/BLE HID или scripts расширяют active interface и обходят target consent, leases либо policy | H | critical | explicit mode/target/permission preview, отдельные finite leases, least privilege, no raw GPIO, passive inspection default, audit и deterministic disconnect/cleanup | security/runtime; WF-06-A4, WF-07-A3/A4, WF-08-A1/A2 | open |
| R-023 | Script или wireless recipe выходит из bounds, превышает resource/TX limits либо прячет forbidden disruptive action | M | critical | signed/versioned packages, per-recipe review, resource/time ceilings, SafetySupervisor, watchdog, panic/expiry physical stop и forbidden-class rejection | safety/extensions; WF-08-A1/A3/A4 + independent physical HIL | open |
| R-024 | NFC/EMV, captive portal или evidence verification сохраняет реальный submitted credential/payment secret или найденный Wi-Fi candidate | M | critical | data-minimization schema NFR-011, redacted views и forbidden-field/log/screenshot/export guards; Wi-Fi plaintext остаётся на компьютерном companion, обратно приходит только несекретный weakness result; evidence inventory и persistence/export negative tests доказывают границу; versioned curated common/default corpus разрешён, identity-linked leaked credentials — нет | privacy/storage; PR-030/033/034 | open |
| R-025 | Bounded robustness/interference/network recipe затрагивает ambient или неверный target | M | critical | NFR-012 selected target, явный channel/frequency и power profile вплоть до полного qualified output, qualified isolated fixture/interlock, preview, deadline, physical Stop, RF/network containment oracle и fail-closed admission; requested power setting никогда не выдаётся за measured dBm | safety/Lab; PR-027/028/031/034 | open |
| R-026 | Signed package, developer mode, companion или USB host path обходит broker/watchdog/Stop | M | critical | единый brokered Actions path NFR-013, отсутствие raw hooks, permission negatives, watchdog injection и independent physical-stop HIL | kernel/security; PR-026/029/032 | open |
| R-027 | Conditional USB host, PN532, live companion или новый decoder превышает power/RAM/flash/bus budget либо расширяет support без evidence | H | H | capability probe, measured per-profile budgets, mutually exclusive leases, conditional UI, fixture-specific HIL и отсутствие availability claim без evidence | hardware/runtime; CAP-056…060 | open |

`critical` используется только для safety failure, предотвращение которого важнее
feature delivery; это намеренно сильнее `high`.

## Controls по этапам

### Gate S1

- R-001…R-005 и R-015 измерены либо ограничены в Hardware Envelope и Resource
  Budgets; ни один unresolved pin conflict не помечен available.
- Существуют binding ADR для toolchain, resource policy, storage schema/atomicity и
  Action boundary.
- Каждый P0 связан с owner и типом negative/positive evidence.

### S2–S4

- CI проверяет pinned builds и RB-02…RB-05.
- Resource/Action negative tests покрывают failed start, Back, cancel, expiry и
  worker crash.
- Storage fault injection и ограниченный passive endurance gate (не менее 45 минут
  и 8 циклов, с завершением в пределах одного часа) закрывают R-006…R-008/010.

### S5–S8

- Per-module HIL и measured power combinations закрывают либо навсегда ограничивают
  hardware risks.
- Active action не выпускается до independent physical stop evidence для R-009.
- Signed update, rollback, recovery, import fuzzing, privacy и EN/RU accessibility
  matrices входят в release gates.
- S7 не закрывается, пока R-020…R-027 не имеют negative corpora, privacy/recovery
  evidence, permission/lease tests и independent stop evidence для каждого active
  interface.

## Триггеры review

Реестр пересматривается при новой board batch/profile, изменении dependency или
partition/schema, предложении active capability, провале power/bus/storage test либо
изменении requirement/stage gate. `STATUS` обновляется только когда факт меняет
текущий progress, evidence или blocker.
