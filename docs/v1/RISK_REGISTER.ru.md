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
| R-001 | ESP32 module/PSRAM variants различаются между партиями v2 | M | H | required profile ограничен N16/no-PSRAM; mismatch — `fault`, а не динамическое расширение бюджета | boards; HW-T01 на второй плате + assembly IDs | open |
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
| R-015 | Одна плата и отсутствие continuity/logic/RF/power instruments создают ложную уверенность | H | H | evidence маркируется partial; unknown остаётся unknown; hardware scope ограничивается | hardware QA; вторая плата и named HW-T evidence | accepted constraint |
| R-016 | Изменение schema или Action API ломает stored evidence/companion clients | M | H | version every boundary, forward migrate или clear reject, immutable source data | services/SDK; schema/Action ADRs + migration contract tests | open |
| R-017 | EN/RU или color-only UI скрывает safety/error meaning или обрезает control | M | M | один string catalog/build, snapshot fixtures, standard-button coverage, no color-only state | UI/product; WF snapshots + NFR-010 matrix | open |
| R-018 | Fatal fault main loop/worker оставляет software-controlled outputs активными или тихо перезагружается в то же unsafe operation | M | critical | permanent panic Task WDT main loop; IRAM quiesce GPIO2/14/15/47; exact-app torn-write-resistant RTC latch; no automatic clear; Safe Mode блокирует product workers и normal Actions | safety/platform; exact 0.103 `E-AUTO-068`/`E-HIL-128`/`E-SAFETY-001` принимает настоящий main-loop watchdog, retained latch при software reset, inactive pads и TFT path explicit clear; worker heartbeats и independent physical-stop HIL остаются closure work | reduced/open |

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
- Storage fault injection и восьмичасовой passive endurance закрывают
  R-006…R-008/010.

### S5–S8

- Per-module HIL и measured power combinations закрывают либо навсегда ограничивают
  hardware risks.
- Active action не выпускается до independent physical stop evidence для R-009.
- Signed update, rollback, recovery, import fuzzing, privacy и EN/RU accessibility
  matrices входят в release gates.

## Триггеры review

Реестр пересматривается при новой board batch/profile, изменении dependency или
partition/schema, предложении active capability, провале power/bus/storage test либо
изменении requirement/stage gate. `STATUS` обновляется только когда факт меняет
текущий progress, evidence или blocker.
