# ESP32-Leshy 1.x — UX-01: карта экранов и Actions

*Read in: [English](UX_SCREEN_MAP.md) · **Русский***

Статус: **реализованная task-first карта 1.x**. Exact physical `1.0.0-dev.328`
принимает иерархию Home и прямой controlled-вход в «Лабораторию» на реальном TFT.
Host/build `1.0.0-dev.329` дополнительно реализует ранний путь Screenshot→защищённая
Библиотека→USB, а host/build `1.0.0-dev.333` добавляет первый receive-only IR
Protocol Workbench за Библиотекой. Их connected physical gates остаются открытыми.
Карта задаёт структуру задач, семантику цветов и поведение Back/Stop.

## Глобальная оболочка

Текущий `UX-S01 Home` — один плоский список из девяти пунктов, упорядоченный в пять
смысловых групп без дополнительных страниц и нажатий. Названия описывают желаемый
результат пользователя, а не внутреннюю подсистему:

```text
Рядом
  WI-FI РЯДОМ        найти сети и Wi-Fi-устройства
  BLUETOOTH РЯДОМ    найти Bluetooth-устройства
Эфир
  ЭФИР 2.4 ГГЦ      увидеть активность / найти сигнал
  ЭФИР SUB-GHZ       увидеть активность / найти сигнал
Доказательства
  ЗАПИСАТЬ           записать Wi-Fi, Sub-GHz или ИК
  МОИ ЦЕЛИ           открыть именованные/связанные объекты и Radar
  СОХРАНЕННОЕ        открыть sessions, captures и exports
Контролируемое
  ЛАБОРАТОРИЯ        прямой advanced-вход; красные label/hint, жёлтый focus
Сервис
  УСТРОЙСТВО         последний приглушённый пункт
  Настройки
  Самопроверка (Quick / Full-Guided)
  Диагностика
  О системе
```

Красный цвет `ЛАБОРАТОРИИ` означает «контролируемая функция — сначала проверить»;
само открытие пункта не означает передачу. Сейчас entry остаётся read-only
Inspector. Любое будущее active action сохраняет собственные preview, explicit
confirmation, interlock, deadline и постоянный Stop. Selection остаётся общим
жёлтым геометрическим focus, поэтому уровень предупреждения и состояние навигации
никогда не кодируются одним цветом.

Screenshot намеренно доступен до входа пользователя в глубокую функцию: выбор
`Снимок` внутри «Захвата» включает один global shot и возвращает Home. Пользователь
открывает нужный экран и сохраняет его exact текущие pixels физическим Select или
touch target `СНИМОК` в header. `ГОТОВО`/`ОШИБКА` — временная обратная связь, а не
ещё одна modal page. Сохранённый item появляется как `Снимок` в Библиотеке с generation,
integrity и provenance build/UI/time; export выбирается из этого же item. Поэтому
Home остаётся task-focused без отдельной постоянной screenshot-only строки.

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

Дерево ниже описывает иерархию capabilities. Исполняемый Home сохраняет стабильный
плоский порядок выше для доступа в одно нажатие; названия групп — смысловая
документация, а не дополнительные экраны. Deep links могут открыть
`Target / Radar / Capture / Lab` из результата, сохраняя тот же typed Action и
safety admission path.

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
│  │  └─ Screenshot: включить → Home → нужный экран → Select/СНИМОК → защищённая Библиотека
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
│  │  └─ Анализ IR → UX-S37 Protocol Workbench: immutable waveform / pulse cursor
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
| Захват Wi-Fi-аутентификации | CAP-049 | Результат→Действия→Устройство→Доказательства→Детали; production Actions — Детали/Сохранить/Повторить, Save требует явного подтверждения и атомарно сохраняет evidence schema 8, а экспорт PCAP и `hc22000` только с полезным evidence повторно открывает exact stored generation |
| Owned Lab | CAP-032…CAP-037, CAP-054…CAP-062 | принимает только reviewed source/package/recipe и qualified fixture; Result возвращает source/audit evidence |
| Библиотека | CAP-025…CAP-031, CAP-038, CAP-043, CAP-047 | item→Compare/Export/Lab; import никогда не обходит parser |
| Устройство | CAP-001…CAP-008, CAP-045…CAP-047, CAP-052, CAP-053 | Diagnostics объясняет недоступность до входа; Lock не блокирует Stop/recovery; Serial владеет одним explicit UART lease |
| Устройство → Настройки | PR-011, NFR-010 | переключение EN/RU; немедленное применение и persistent selection |
| Устройство → Самопроверка | применимые CAP-001…CAP-062, PR-009 | Quick/Full выполняют те же versioned checks, что release HIL; report→Diagnostics/remedy/export |

## Baseline UX-S31 «Полевой обзор»

Пользователь запускает эту задачу ради трёх ответов: что находится здесь, что
появилось или исчезло после прошлого визита и как забрать результат. Поэтому product
workflow имеет три компактных уровня:

1. **Настройка** показывает receive sources `Wi-Fi AP + устройства` и `Bluetooth`,
   выбранный baseline повторного прохода или `Первый визит`, готовность хранилища и
   location как `GPS готов`, `GPS отсутствует` или `Ожидание координат`. У штатного
   ESP32-DIV нет authoritative GPS, поэтому `GPS отсутствует` — нормальное честное
   состояние, которое не блокирует локальный обзор.
2. **Выполняется** использует всю content area для времени, общего числа unique,
   Новых, Уже видели и самых сильных недавних объектов. Переключение открывает общий
   strongest-first список AP/станций/BLE; после начала navigation порядок identity
   фиксируется, а signal обновляется на месте. Implementation counters, totals redraw
   и пустые декоративные рамки отсутствуют. Stop остаётся явным, Back отменяет через
   общий bounded cleanup path.
3. **Результат** начинает с `Новые / Уже видели / Исчезли`, затем показывает totals
   AP/станций/BLE. Actions: Сохранить, Детали сравнения, Экспорт native record и
   Экспорт WiGLE. Потеря capacity/source создаёт явный incomplete result и запрещает
   claims comparison. WiGLE получает статус `готов к загрузке` только с trusted UTC
   и location; иначе это честный локальный export с пустыми полями. Wi-Fi stations
   остаются в native result, хотя WiGLE 1.6 не имеет row type для station.

Exact host/build dev.256 принимает только bounded catalog, comparison и serializer
строк за этим screen contract. Wiring product state, routing persistence/export,
live station capture, optional adapter GPS и physical pixels остаются открыты.

Exact host/build dev.257 принимает первый product slice: пункт меню Wi-Fi объясняет
comparison Wi-Fi+Bluetooth, Setup заменяет не относящийся к визиту переход в RF spectrum
на явный выбор `Предыдущий визит` / `Первый визит`, все доступные receivers выбраны по
умолчанию, а automatic baseline может стать только exact complete запись
`field-visit-live`. Result показывает unique либо Новые/Снова/Не найдено и totals
Wi-Fi/BLE; incomplete input выводит `Результат неполный` и не публикует comparison.
Для Running в этом slice остаётся существующий strongest-first browser observations.
Более богатые live Новые/Снова, station capture и optional adapter GPS остаются
открыты.

Exact physical dev.263 принимает presentation и route export результата. Right/OK
на stopped complete Field Survey открывает Library «Экспорт готов» без
повторного radio ownership. Экран сообщает, что native CSV готов, а WiGLE не имеет
GPS/UTC, вместо ложного claims upload readiness; USB назван transfer path. Меняется
только content «Экспорт готов», exact pixels сохранены. Payload native и WiGLE
парсятся автоматикой в memory и не пишутся в host evidence.

Exact physical dev.248 принимает исходную иерархию результата UX-S30 на оригинальном
DIV. Exact host/build dev.249 расширяет production Actions до Детали, Сохранить и
Повторить. Save сначала открывает явное подтверждение, затем показывает Сохранение и
terminal state Сохранено/Ошибка; он атомарно коммитит authentication provenance
schema 8 и принимает Сохранено только после exact-generation reopen, повторного
анализа и validation artifact. Valid stored capture остаётся экспортируемым как PCAP,
даже если полезного authentication material нет; canonical `hc22000` становится
готовым только для valid PMKID или replay-consistent пары M1→M2. Results synthetic HIL
остаются volatile и не могут предлагать Save или Export. В terminal result
`inconclusive` имеет приоритет над evidence Full, PMKID и Partial; peers без valid
message mask не участвуют в навигации. Up/Down меняют selection только внутри текущего
уровня, Right/OK двигают внутрь, Left/Back возвращают ровно на уровень, Повторить
запускает тот же bounded receive-only capture. Live/tone/selection updates
перерисовывают только изменённый content, а не весь экран. Title перерисовывается
только при видимой смене tone/color; одинаковые title list/detail остаются
нетронутыми, footer меняется только при изменении видимых hints. Extension
Save/reopen/export dev.249 всё ещё требует physical acceptance TFT, SD и полезного
evidence; dev.248 остаётся physical baseline.

## UX-S37 receive-only IR Protocol Workbench

Пользователь открывает один сохранённый IR Capture, чтобы сразу ответить на три
вопроса: какую форму приняли, из каких timing families она состоит и какой exact
pulse сейчас изучается. Поэтому detail Библиотеки сохраняет **Анализ** и **Экспорт**
отдельными actions; анализ не подменяет и не изменяет evidence/export workflow.

При входе один раз рисуются static chrome, summary protocol/pulse/base, уведомление
immutable source, waveform на всю ширину, centers timing families и source
fingerprint. Up/Down перемещают pulse cursor и заменяют только bounded cursor strip
плюс одну atomic row с index, logical Mark/Space, microseconds и normalized units.
Active-low electrical level штатного demodulator переводится в полезный logical
envelope; bytes raw source не меняются. Reopen допускается только для exact выбранного
persisted generation. Unavailable или stale input fail closed вместо анализа другой
Session из памяти.

Host/build dev.333 реализует этот первый read-only IR slice с fixed workspace 1 KiB
и без heap allocation, TX, replay, output API или radio lease. Physical review
TFT/navigation, comparison двух Captures, annotations полей и сохранение derived
decode остаются открытыми, поэтому FUNC-37 ещё не завершён.

## Acceptance UX-01

- Каждая `CAP-001…CAP-062` имеет один primary owner и измеримый путь
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
