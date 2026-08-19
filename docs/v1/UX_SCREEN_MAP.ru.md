# ESP32-Leshy 1.x — UX-01: карта экранов и Actions

*Read in: [English](UX_SCREEN_MAP.md) · **Русский***

Статус: **low-fidelity baseline S1**. Пиксели, typography и palette фиксируются в
S2 на реальном TFT; эта карта уже задаёт структуру задач и поведение Back/Stop.

## Глобальная оболочка

`UX-S01 Home` содержит шесть продуктовых доменов, а не список радиомодулей или
служебных функций. Последний домен `Устройство` содержит настройки, проверки и
информацию о системе:

```text
Обзор
Захват
Библиотека
Цели          (planned до S6)
Лаборатория   (planned до S7)
Устройство
  Настройки
  Самопроверка (Quick / Full-Guided)
  Диагностика
  О системе
```

На каждом экране остаются видимыми: название контекста, честное состояние
storage/receiver, назначение доступных кнопок и путь Back. Exact 0.91 использует
`SD OK`/`SD !`/`SD --` и `RF RX`/`RF --`; status bar не рисует battery percentage
без достоверной capability. Touch, physical buttons и diagnostic automation создают
одни и те же typed Actions.

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
└─ Устройство
   ├─ Настройки → UX-S25 Language / Display / Input / Feedback / Connectivity
   ├─ Самопроверка → test context UX-S24
   │  ├─ Quick: bounded read-only automatic plan
   │  └─ Full / Guided: scoped preflight → applicable checks → report
   ├─ Диагностика → UX-S24 Capability / Module Detail / Report
   └─ О системе → UX-S27 Version / Profile / Update / Rollback / Recovery

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
| `Back` | закрыть верхний view/dialog и восстановить selection | физическая Left; touch target или footer-кнопка Back отсутствуют |
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
| Устройство → Настройки | PR-011, NFR-010 | переключение EN/RU; немедленное применение и persistent selection |
| Устройство → Самопроверка | применимые CAP-001…CAP-047, PR-009 | Quick/Full выполняют те же versioned checks, что release HIL; report→Diagnostics/remedy/export |

## Acceptance UX-01

- Каждая `CAP-001…CAP-047` имеет один primary owner и измеримый путь
  entry → success/error/cancel → Back.
- WF-01 использует Home→Устройство→Самопроверка/Диагностика; WF-02 — UX-S02…S05; WF-03 — UX-S15…S17;
  WF-04 — UX-S06…S10; WF-05 — UX-S18…S22.
- Start основной задачи достигается не глубже четырёх переходов от Home. Receiver
  может быть прямой top-level задачей, если именно это нужно пользователю;
  выбор band/source остаётся его параметром.
- Back восстанавливает selection и не выполняет скрытый Stop, кроме safety-first TX
  rule; Stop Session/Capture остаётся отдельным явным Action.
- Empty, unavailable, degraded и fault состояния ведут к Diagnostics или исправлению,
  а не в неработающий экран.

Exact `0.90.0-product-menu` реализует эту верхнеуровневую карту на board-01.
Восемь retained TFT states и machine checker связывают Home, Устройство,
Самопроверку, Диагностику и О системе, включая disabled будущие домены, вход по
touch row, non-interactive chrome, восстановление parent клавишей Left и final zero
ownership (`E-BUILD-091`/`E-AUTO-055`/`E-HIL-115`/`E-UX-014`).

Exact `0.91.0-clean-status` уточняет shell, не меняя эту карту: visible raw-input
diagnostics удалены, одновременно помещаются четыре Home row, а exact real-TFT
evidence доказывает idle `RF --` и active receive `RF RX` с final zero ownership
(`E-BUILD-092`/`E-AUTO-056`/`E-HIL-116`/`E-UX-015`).

Exact `0.92.0-spectrum-views` уточняет два RF leaf: каждый даёт Спектр и Водопад,
CC1101 получает chooser четырёх диапазонов; brand `LESHY` остаётся только на Home,
а вложенный header показывает навигационный контекст. Live viewport занимает полные
240 px ширины и 216 px высоты над key legend. Exact HIL связывает все четыре CC bands,
накопленную историю, pause/resume и final zero ownership
(`E-BUILD-093`/`E-AUTO-057`/`E-HIL-117`/`E-UX-016`/`E-RADIO-005`).

Exact `0.93.0-product-menu` заменяет executable-часть Home 0.90, не отменяя
карту capabilities 1.0. Текущий Home содержит только реализованные задачи
в таком порядке: Wi-Fi, Bluetooth, 2.4 ГГц, Sub-GHz, Захват, Библиотека,
Устройство. Будущие Цели и Лаборатория остаются в этом документе и roadmap,
пока не станут полезными. Wi-Fi и Bluetooth открывают свою single-source строку Start;
2.4 ГГц сразу открывает live nRF24; Sub-GHz — chooser диапазонов CC; Устройство
остаётся последним и владеет всеми service pages. Одна connected-candidate команда
сохраняет 13 реальных TFT states и независимо проверяет каждый пункт,
наполненные водопады, final Home и zero ownership без ручных нажатий
(`E-BUILD-094`/`E-AUTO-058`/`E-HIL-118`/`E-UX-017`/`E-RADIO-006`).

Exact `0.94.0-home-identity` не меняет дерево экранов. Он локализует brand,
существующий только на корне, как `LESHY`/`Леший`, показывает SemVer core сборки
на Home и убирает brand из текста «О системе». Вложенные headers остаются
навигационным контекстом. Physical candidate gate добавляет английский Home к
русскому product route и восстанавливает русский перед final cleanup. Четырнадцать
retained TFT states и exact source/candidate bindings принимают результат
(`E-BUILD-095`/`E-AUTO-059`/`E-HIL-119`/`E-UX-018`).

Candidate `0.95.0-inline-key-hints` не меняет дерево экранов или input map. Меняется
только общая легенда физических клавиш: прежние двухэтажные cells «клавиша над
подписью» становятся одной строкой Roboto Condensed Medium 12 в смешанном регистре:
`◀ Назад` выровнено влево, `▲▼ Выбор` центрировано, contextual action и `OK▶`
выровнены вправо. Footer остаётся non-interactive; touch entry по-прежнему принадлежит
enabled content rows.
