# ESP32-Leshy 1.x — UX-01: карта экранов и Actions

*Read in: [English](UX_SCREEN_MAP.md) · **Русский***

Статус: **low-fidelity baseline S1**. Пиксели, typography и palette фиксируются в
S2 на реальном TFT; эта карта уже задаёт структуру задач и поведение Back/Stop.

## Глобальная оболочка

Текущий `UX-S01 Home` содержит семь реализованных пользовательских задач. Последний
пункт `Устройство` содержит настройки, проверки и информацию о системе:

```text
Wi-Fi          найти сети рядом
Bluetooth      найти устройства рядом
2.4 ГГц        увидеть эфир / найти сигнал
Sub-GHz        увидеть эфир / записать сигнал
Захват         записать Wi-Fi или ИК
Библиотека     открыть сохранённые записи
Устройство
  Настройки
  Самопроверка (Quick / Full-Guided)
  Диагностика
  О системе
```

На каждом экране остаются видимыми: название контекста, честная сводка активных
приёмных/передающих антенн, назначение доступных кнопок и путь Back. Состояние
хранилища показывается только когда оно меняет текущий результат или действие и не
занимает глобальный header. Status bar не рисует battery или power state без
достоверной capability. Touch, physical buttons и diagnostic automation создают
одни и те же typed Actions.

Каждый живой список радиообъектов упорядочен по убыванию принятого сигнала:
текущий самый сильный RSSI находится сверху, более слабые записи идут ниже. При
равном RSSI сохраняется прежний взаимный порядок, а refresh привязывает selection
к той же identity, поэтому пересортировка не подменяет объект под курсором. Для
интерактивного live list порядок по убыванию сигнала действует до начала navigation.
Первый Navigate/Open фиксирует видимый порядок identity до выхода из задачи: текущие
значения сигнала продолжают обновляться на месте, но строки и объект под курсором не
прыгают. Повторный вход создаёт новый strongest-first snapshot и добавляет новые
обнаруженные объекты.

Площадь экрана расходуется только на пользовательскую пользу. Неинтерактивный факт
в одну строку занимает одну компактную строку. Крупная row допустима для touch target
и содержит как название задачи, так и полезный результат или пояснение. Просторная
область result/detail должна добавлять полезный контекст или читаемую визуализацию,
а не декоративную пустую рамку. На штатных пользовательских экранах не показываются
внутренние счётчики samples, frames или redraw. Поэтому detail радиообъекта сочетает
компактные identity и channel/mode с общей качественной и числовой шкалой сигнала.

## Дерево навигации

```text
UX-S01 Home
├─ Обзор
│  ├─ UX-S02 New Survey: sources, storage, duty-cycle preview
│  ├─ UX-S03 Running Survey: summary ↔ timeline ↔ list
│  │  └─ UX-S04 Observation Detail → Target / Radar / Capture
│  ├─ UX-S05 Stop & Commit Result → Session Detail / Export / Home
│  ├─ UX-S29 Защита эфира: находки → объяснение → exact evidence
│  └─ UX-S31 Field Survey: sources / GPS / revisit / local export
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
│  ├─ UX-S14 Capture Result: raw metadata / derived decode / Save / Export / Lab
│  ├─ UX-S30 Захват Wi-Fi-аутентификации
│  │  ├─ Выполняется: remaining time / candidate frames / retained/drop accounting
│  │  └─ Результат → Действия → Устройство → Доказательства → Детали
│  │     └─ Повторить: снова запустить тот же bounded capture
│  └─ UX-S32 BLE Inspector: raw packets / explicit connected GATT
├─ Лаборатория
│  ├─ UX-S18 Scope & Safety Context
│  ├─ UX-S19 Saved Capture + TX Parameters
│  ├─ UX-S20 Explicit Confirmation
│  ├─ UX-S21 Running TX: frequency, power, deadline, permanent Stop
│  ├─ UX-S22 Result / Fault / Source Capture
│  ├─ UX-S35 Automation / HID: package, permissions, target, preview
│  └─ UX-S36 Wireless Recipes: admitted Wi-Fi / BLE / nRF fixtures
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
   ├─ О системе → UX-S27 Version / Profile / Update / Rollback / Recovery
   ├─ Блокировка → UX-S33 Setup / Unlock / Recovery / Protected Scope
   └─ Serial Console → UX-S34 UART Preview / Running / Save Result

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
| Обзор | CAP-009…CAP-017, CAP-042, CAP-048, CAP-050 | Observation/finding→Target/Capture/Radar/evidence; stopped Session/Field Survey→Library/export |
| Цели | CAP-018…CAP-022, CAP-044 | Evidence→Observation/Capture; Target→Compare/Radar |
| Захват | CAP-023, CAP-024, CAP-026…CAP-031, CAP-042, CAP-043, CAP-051 | Result→Library/Export/Lab; GATT требует explicit connected mode |
| Захват Wi-Fi-аутентификации | CAP-049 | volatile Результат→Действия→Устройство→Доказательства→Детали; Повторить перезапускает capture; persistence/export не подключён, `exportEligibility` равен `NotEvaluated` |
| Лаборатория | CAP-032…CAP-037, CAP-054, CAP-055 | принимает только reviewed source/package/recipe; Result возвращает source/audit evidence |
| Библиотека | CAP-025…CAP-031, CAP-038, CAP-043, CAP-047 | item→Compare/Export/Lab; import никогда не обходит parser |
| Устройство | CAP-001…CAP-008, CAP-045…CAP-047, CAP-052, CAP-053 | Diagnostics объясняет недоступность до входа; Lock не блокирует Stop/recovery; Serial владеет одним explicit UART lease |
| Устройство → Настройки | PR-011, NFR-010 | переключение EN/RU; немедленное применение и persistent selection |
| Устройство → Самопроверка | применимые CAP-001…CAP-055, PR-009 | Quick/Full выполняют те же versioned checks, что release HIL; report→Diagnostics/remedy/export |

Exact host/build dev.247 связывает UX-S30 с одним стабильным controller path. В
terminal result `inconclusive` имеет приоритет над evidence Full, PMKID и Partial;
peers без valid message mask не участвуют в навигации. Up/Down меняют selection
только внутри текущего уровня, Right/OK двигают внутрь, Left/Back возвращают ровно на
уровень, Повторить запускает тот же bounded receive-only capture. Result явно
сообщает volatile/RAM-only/not saved. Он не предлагает Save или Export: product
persistence не подключён, standard artifact serializer не существует, export
eligibility остаётся `NotEvaluated`. Live/tone/selection updates перерисовывают только
изменённый content, а не весь экран. Эта карта остаётся host/build до physical
проверки TFT/navigation delta exact dev.247 на оригинальном DIV после USB repower.

## Acceptance UX-01

- Каждая `CAP-001…CAP-055` имеет один primary owner и измеримый путь
  entry → success/error/cancel → Back.
- WF-01 использует Home→Устройство→Самопроверка/Диагностика; WF-02 — UX-S02…S05; WF-03 — UX-S15…S17;
  WF-04 — UX-S06…S10; WF-05 — UX-S18…S22; WF-06 — UX-S29…S32;
  WF-07 — UX-S33/S34; WF-08 — UX-S35/S36 плюс UX-S18…S22.
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
2.4 ГГц открывает «Обзор эфира» / «Найти сигнал»; Sub-GHz — chooser диапазонов CC; Устройство
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
Четырнадцать exact TFT states принимают это refinement как `E-BUILD-096`/
`E-AUTO-060`/`E-HIL-120`/`E-UX-019`.

Exact `0.96.0-compact-ui-waterfall` также не меняет дерево экранов или normalized
input map. Вместо этого compact-ится общий shell: identity Home занимает одну строку,
вложенные titles переносятся в header 26 px, а четыре content row 216×60 заполняют
viewport от y=32 с inset 12 px. RF leaves сохраняют Спектр и Водопад как соседние
views, но существующий ring на 112 строк теперь движется по fixed cadence 26 785 мкс,
не зависящему от sweep duration приёмника. Четырнадцать exact EN/RU states
Home/menu/RF и host timings 2,905…2,927 s на nRF24 и всех четырёх CC bands принимают
результат (`E-BUILD-097`/`E-AUTO-061`/`E-HIL-121`/`E-UX-020`/`E-RADIO-007`).

Exact `0.111.0-ble-nearby` заменяет Bluetooth entry path exact 0.93:
Home→Bluetooth теперь сразу запускает «Устройства рядом» вместо технической
single-source строки Start. Live list владеет четырьмя touch row 216×60; Up/Down
выбирают, Right или OK открывает detail, Left возвращает. List показывает advertised
name (или явный fallback без имени), RSSI, suffix адреса и signal bars; detail — полный
адрес и пассивность. Duplicate timestamp-only observations ничего не рисуют,
изменившиеся данные перерисовывают только content rows, а background discovery
никогда не перерисовывает открытый detail. Пять exact TFT states и physical pixel
comparisons принимают этот немерцающий контракт (`E-BUILD-111`/`E-AUTO-075`/
`E-HIL-135`/`E-UX-030`).

Exact `0.122.2-ble-device-intelligence` заменяет этот намеренно краткий baseline без
новой страницы. Первая строка каждой из четырёх row показывает лучшее доступное
имя/type, вторая — отличающийся полезный vendor, state или RSSI fact; повторяющиеся
подписи подавляются. Открытие row сохраняет ту же identity и показывает компактный
passive passport над единственной встроенной signal card. Продолжающийся discovery
перерисовывает только эту card: name, address, vendor и advertisement facts остаются
pixel-identical, меняются current dBm, meter, volatile range и trend. Принятые frames
240×320 меняют 111 list-content/zero chrome pixels и 3 234 radar/zero
static-or-chrome pixels (`E-BUILD-122`/`E-AUTO-086`/`E-HIL-146`/`E-UX-041`).

Exact `0.123.0-nrf24-signal-finder` заменяет один implicit live view пункта 2.4 ГГц
двумя outcome rows: **Обзор эфира** (Спектр/Водопад) и **Найти сигнал**
(пульт/метка/датчик). Сначала Finder просит оставить источник выключенным на два
окна изучения фона, затем — включить и поднести его к антеннам. Экран сохраняет
status `RX N1+2+3`, чёрный полноширинный plot отклика 2 402…2 484 МГц и действие
**Заново**; при обнаружении prompt заменяется точными МГц и ближайшим каналом Wi-Fi.
В live search перерисовываются только result при смене state и bars графика. Восемь
exact TFT states и comparison двух frames принимают zero changes в header, legend,
axis и footer (`E-BUILD-123`/`E-AUTO-087`/`E-HIL-147`/`E-UX-042`).

Exact `0.124.1-cc1101-frequency-finder` даёт Sub-GHz три явных row:
**Обзор эфира**, **Найти частоту** и **Захват RAW**. Сначала Finder просит оставить
источник выключенным на три ambient sweep, затем — включить и поднести к антеннам.
Экран сохраняет `RX CC`, чёрный полноширинный plot 275…950 МГц с частотной осью и
действие **Заново**. Найденный результат заменяет prompt точными кГц и подсказкой
ближайшего стандартного диапазона; штатный run не показывает sweep/bin/counter
telemetry. Search перерисовывает только изменившиеся result и graph regions. Fresh
и независимый ambient run принимают 1 455 graph и zero static changed pixels
(`E-BUILD-124`/`E-AUTO-088`/`E-HIL-148`/`E-UX-043`).

Exact `0.113.0-dense-details` применяет правило расходования площади к трём
реализованным detail radio objects, не меняя navigation. Bluetooth Device, Wi-Fi
Network и Wi-Fi Device компактно показывают identity/channel-or-mode над одной
общей signal card с качественной оценкой, числом dBm и шкалой от слабого к сильному.
Штатные sample/frame counters удалены. Один fresh flash и два same-hash reuse run
сохраняют 17 TFT states; все три открытых detail остаются pixel-identical при
background reception (`E-BUILD-113`/`E-AUTO-077`/`E-HIL-137`/`E-UX-032`).

Exact `0.114.0-stable-network-nav` конкретизирует это правило live list для
Wi-Fi→«Сети рядом». До взаимодействия текущий RSSI задаёт порядок по убыванию.
Первое Up/Down/Open фиксирует видимую последовательность BSSID; RSSI и channel
продолжают обновляться на месте, но cursor, identity строк и выбранная сеть не
прыгают. Сети, впервые найденные после фиксации, появляются при повторном входе в
задачу. Fresh physical run выполняет восемь actions и ещё два scan на 23
зафиксированных строках без изменения selection, visible size, BSSID-order hash или
selected-BSSID hash (`E-BUILD-114`/`E-AUTO-078`/`E-HIL-138`/`E-UX-033`).

Exact `0.115.0-wifi-device-intelligence` превращает Wi-Fi→«Устройства» в
трёхуровневый пользовательский flow: strongest-first live list → стабильный паспорт
устройства → live signal radar. Primary label строки предпочитает пассивно
объявленные WPS device name/model/maker, затем embedded IEEE OUI maker, затем MAC.
Паспорт использует весь viewport для типа MAC, maker, model, поколения/channel Wi-Fi,
directed SSID, BSSID, длительности/state наблюдения и явной пометки passive evidence;
недоступные факты показываются как unknown, а не угадываются. Right или OK ведёт
вперёд, Left возвращает. Первое взаимодействие фиксирует identity строк, а radar
закрепляет приём на канале выбранного устройства и обновляет только RSSI state/range
card. Восемь exact TFT states проверяют zero static-chrome repaint и pixel-stable
паспорт при background traffic (`E-BUILD-115`/`E-AUTO-079`/`E-HIL-139`/`E-UX-034`).

Exact `0.116.0-wifi-channel-average` уточняет Wi-Fi→«Каналы», не добавляя нового
экрана. Полная ось 1…13 остаётся на чёрном графике. Для каждого канала узкий цветной
столбец последнего dwell накладывается на более широкий серый столбец среднего за
текущий вход; серый образец и подпись `СРЕД` объясняют кодировку.
`СВОБОДНЕЕ` сравнивает средние 1/6/11, поэтому один короткий всплеск сам по себе не
переворачивает рекомендацию. Перерисовывается только изменившийся столбец или
рекомендация. Четыре exact TFT states доказывают видимые серые средние и zero changes
за пределами live regions (`E-BUILD-116`/`E-AUTO-080`/`E-HIL-140`/`E-UX-035`).

Более поздний exact `0.120.0-wifi-channel-choice` делает рекомендацию понятной и согласованной с
графиком. Кандидатами становятся все измеренные подписи 1…13; побеждает минимальное
видимое серое среднее, а давление соседних каналов разрешает только равенство.
Голубым подсвечивается единственный выбранный номер. Удалены постоянные голубые
подписи 1/6/11 и английский текст `BEST 1/6/11`. Exact board evidence рекомендует и
подсвечивает канал 13 после второго и третьего полного sweep
(`E-BUILD-120`/`E-AUTO-084`/`E-HIL-144`/`E-UX-039`).

Саморевью exact `0.121.0-wifi-channel-neutral-bars` удаляет и legacy-зелёный tint
низкой загрузки, который всё ещё применялся только к 1/6/11. Текущие столбцы всех
каналов используют одну palette по измеренной загрузке; голубой остаётся только у
фактически рекомендованной подписи оси. Fresh physical evidence меняет только live
region и сохраняет static chrome exact (`E-BUILD-121`/`E-AUTO-085`/
`E-HIL-145`/`E-UX-040`).

Exact `0.117.0-wifi-device-live-detail` сворачивает исторический трёхуровневый flow
Wi-Fi→«Устройства» в strongest-first list → встроенную живую информацию. Right или
OK сразу открывает выбранную identity и фиксирует её канал; верхняя область
identity/MAC/passive evidence остаётся стабильной, а ниже обновляются только
generation/channel, network или состояние наблюдения, signal meter, range и trend.
Left снимает фиксацию и возвращает прямо к списку. Шесть physical TFT states
доказывают 2 120 changed pixels live-области и zero identity/chrome changes
(`E-BUILD-117`/`E-AUTO-081`/`E-HIL-141`/`E-UX-036`).

Exact `0.118.0-wifi-network-intelligence` заставляет «Сети рядом» отвечать «что это
за сеть?», а не показывать scan telemetry. Detail использует viewport для SSID/BSSID
и вендора, защиты/шифров, channel/frequency/width/PHY, WPS/FTM/RX antenna и
country/channel limits, когда они объявлены. Отсутствующие факты честно остаются
unknown. Hidden SSID подписан `Скрытая`; пассивный приём продолжает слушать, а более
поздний beacon или probe response того же BSSID заменяет имя на месте, не сдвигая
курсор. Следующая пустая запись не может стереть уже известное имя или более полные
факты. Прошивка не отправляет directed probe. Static passport перерисовывается
только при обогащении, обычный live refresh ограничен строкой RSSI. Шесть physical
TFT states доказывают zero changed pixels вне этой строки, native suite — монотонный
merge hidden→known (`E-BUILD-118`/`E-AUTO-082`/`E-HIL-142`/`E-UX-037`).

Exact `0.119.0-wifi-network-live-radar` сохраняет этот паспорт и использует оставшийся
нижний viewport для live-сигнала выбранного BSSID. Одна компактная карточка показывает
качественное состояние, числовой dBm, шкалу, минимум/максимум с момента входа и
последний trend; отдельного route и технического sample counter нет. Passive scan
продолжает обходить все каналы, сохраняя полезность списка и hidden-name enrichment.
При видимом изменении сигнала перерисовывается только карточка; identity, facts, header
и footer не мерцают. Шесть physical TFT states доказывают 86 changed pixels внутри
карточки и zero outside/chrome pixels (`E-BUILD-119`/`E-AUTO-083`/`E-HIL-143`/
`E-UX-038`).
