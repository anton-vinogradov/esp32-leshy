# ESP32-Leshy 1.x — UX-01: карта экранов и Actions

*Read in: [English](UX_SCREEN_MAP.md) · **Русский***

Статус: **low-fidelity baseline S1**. Пиксели, typography и palette фиксируются в
S2 на реальном TFT; эта карта уже задаёт структуру задач и поведение Back/Stop.

## Глобальная оболочка

`UX-S01 Home` содержит шесть задач, а не список радиомодулей, а последним пунктом —
всегда доступный utility Self-Test:

```text
Обзор       Цели        Захват
Лаборатория Библиотека  Устройство
SELF-TEST   (QUICK / FULL-GUIDED)
```

На каждом экране остаются видимыми: название контекста, состояние storage/power,
активная Session или TX, назначение доступных кнопок и путь Back. Status bar не
рисует battery percentage без достоверной capability. Touch, physical buttons и
diagnostic automation создают одни и те же typed Actions.

## Дерево навигации

```text
UX-S01 Home
├─ Обзор
│  ├─ UX-S02 New Survey: sources, storage, duty-cycle preview
│  ├─ UX-S03 Running Survey: summary ↔ timeline ↔ list
│  │  └─ UX-S04 Observation Detail → Target / Radar / Capture
│  └─ UX-S05 Stop & Commit Result → Session Detail / Export / Home
├─ Цели
│  ├─ UX-S06 Target List: search, filter, sort
│  └─ UX-S07 Target Detail
│     ├─ UX-S08 Name / Tags / Notes / Identities / Merge-Split
│     ├─ UX-S09 Baseline & Compare
│     └─ UX-S10 Radar / Localize
├─ Захват
│  ├─ UX-S11 Capture Source: Wi-Fi packets / Sub-GHz / IR / NFC / Screenshot
│  ├─ UX-S12 Capture Setup: source, bounds, destination
│  ├─ UX-S13 Capture Running: progress, drops, explicit Stop
│  └─ UX-S14 Capture Result: raw metadata / derived decode / Save / Export / Lab
├─ Лаборатория
│  ├─ UX-S18 Scope & Safety Context
│  ├─ UX-S19 Saved Capture + TX Parameters
│  ├─ UX-S20 Explicit Confirmation
│  ├─ UX-S21 Running TX: frequency, power, deadline, permanent Stop
│  └─ UX-S22 Result / Fault / Source Capture
├─ Библиотека
│  ├─ UX-S15 Sessions / Captures / Exports / Screenshots
│  ├─ UX-S16 Item Detail: integrity, provenance, source/derived data
│  └─ UX-S17 Import / Export / Compare / Open in Lab
├─ Устройство
   ├─ UX-S23 Device Dashboard
   ├─ UX-S24 Diagnostics / Capability / Module Detail / Report
   ├─ UX-S25 Language / Display / Input / Feedback / Connectivity
   ├─ UX-S26 Storage / Backup-Restore / Factory Reset
   └─ UX-S27 Install / Update / Rollback / Recovery / About
└─ Self-Test → test context UX-S24
   ├─ Quick: bounded read-only automatic plan
   └─ Full / Guided: scoped preflight → applicable checks → report

UX-S28 Global dialog layer: unavailable reason, progress, confirm, error, panic.
```

Deep links открывают существующий экран с переданным ID, а не вторую реализацию:
Observation→Target, Target→Capture, Capture→Lab и Library→Compare используют те же
controllers и Actions, что вход из Home.

## Typed Actions и physical mapping

| Action | Семантика | Кнопки / touch |
|---|---|---|
| `Navigate` | переместить focus/selection без side effect | Up/Down; tap focus |
| `Open` | открыть выбранный item/detail | Right или Select согласно видимой footer label; tap item |
| `Back` | закрыть верхний view/dialog и восстановить selection | Left; видимая Back area |
| `Context` | показать вторичные действия текущей сущности | Right при явной label; touch context button |
| `Start` | запустить уже просмотренный passive/configured workflow | Select на labelled Start |
| `Stop` | остановить текущую Session/Capture/TX, затем показать результат | Select/Left согласно постоянной Stop label |
| `Confirm` | выполнить явно показанную bounded mutation/TX/update/reset | Select только на отдельном confirm screen; touch Confirm |
| `Cancel` | отказаться без commit и освободить workers/leases | Left/Back; touch Cancel |
| `Save` | атомарно сохранить новый result/derived metadata | labelled Select; touch Save |
| `Export` | создать versioned artifact после preview target/format | Context→Export или labelled action |
| `Panic` | немедленно прекратить любой TX до обработки navigation | любой Back/Left во время TX; long Back — глобальный fallback |

Жест или serial-only команда не являются единственным способом выполнить core
action. В активном TX `Back` никогда не открывает confirm и сначала физически
останавливает передачу. После stop обычный Back возвращает по стеку.

## Владение возможностями

| Раздел | Primary capabilities | Важные переходы |
|---|---|---|
| Обзор | CAP-009…CAP-017, CAP-042 | Observation→Target/Capture/Radar; stopped Session→Library |
| Цели | CAP-018…CAP-022, CAP-044 | Evidence→Observation/Capture; Target→Compare/Radar |
| Захват | CAP-023, CAP-024, CAP-026…CAP-031, CAP-042, CAP-043 | Result→Library/Export/Lab |
| Лаборатория | CAP-032…CAP-037 | принимает только saved immutable Capture; Result возвращает source link |
| Библиотека | CAP-025…CAP-031, CAP-038, CAP-043, CAP-047 | item→Compare/Export/Lab; import никогда не обходит parser |
| Устройство | CAP-001…CAP-008, CAP-045…CAP-047 | Diagnostics объясняет недоступность до входа в task |
| Self-Test | применимые CAP-001…CAP-047, PR-009 | Quick/Full выполняют те же versioned checks, что release HIL; report→Diagnostics/remedy/export |

## Acceptance UX-01

- Каждая `CAP-001…CAP-047` имеет один primary owner и измеримый путь
  entry → success/error/cancel → Back.
- WF-01 использует Home→Self-Test/UX-S23/S24; WF-02 — UX-S02…S05; WF-03 — UX-S15…S17;
  WF-04 — UX-S06…S10; WF-05 — UX-S18…S22.
- Start основной задачи достигается не глубже четырёх переходов от Home; текущий
  receiver остаётся filter/parameter, а не верхним уровнем IA.
- Back восстанавливает selection и не выполняет скрытый Stop, кроме safety-first TX
  rule; Stop Session/Capture остаётся отдельным явным Action.
- Empty, unavailable, degraded и fault состояния ведут к Diagnostics или исправлению,
  а не в неработающий экран.
