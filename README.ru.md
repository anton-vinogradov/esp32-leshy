# ESP32-Leshy 1.x

Читать на: [English](README.md) · **Русский**

ESP32-Leshy 1.x — переработанная с нуля прошивка для беспроводного мультитула
[ESP32-DIV](https://github.com/CiferTech/ESP32-DIV).

<!-- LESHY-ROADMAP:START -->
## Статус разработки и роадмап

> **Сейчас: S6 — Продуктовые отличия: Targets, compare и companion**
>
> Закрыто этапов: 5 из 9.
>
> Пользовательские функции: **23/62 готовы** · 14 в работе · 6 заблокированы · 19 запланированы.

Этот срез главной страницы генерируется из документации-точки-истины 1.x; CI отклоняет рассинхрон. Checklist полный для принятого baseline из 62 capabilities, знаменатель зафиксирован. Повторный аудит конкурентов и product decision от 1 сентября завершены: все ценные принятые outcomes входят в знаменатель, а отложенные integrations и три жёсткие продуктовые границы явно перечислены в [пофункциональном аудите](docs/v1/COMPETITIVE_ANALYSIS.ru.md#пофункциональный-аудит-паритета).

- **Текущая фаза:** `S6.5 — local USB/Web companion над общими Actions и schemas`.
- **Режим поставки:** `functional-first`: пользовательские вертикальные срезы идут перед дополнительной невидимой инфраструктурой; для каждого среза запускается затронутый delta-HIL, а широкая matrix — на границе блока/этапа, RC, cross-cutting change или cadence.
- **Проверенный checkpoint:** `E-BUILD-227`/`E-AUTO-203`/`E-HIL-228`/`E-UX-082`/`RB-M239` принимают exact physical `1.0.0-dev.351` на original board-01. Receive-only IR Protocol Workbench рисует сохранённый physical NEC-вектор из 67 импульсов на реальном TFT 240×320; два перехода меняют только 492/426 pixels в строках cursor/facts, zero pixels снаружи и zero full frames. Storage остаётся generation 8/54 observations с zero writes, radio/TX не затронуты, cleanup заканчивается Home/none/lease 0. Exact dev.302 остаётся periodic full anchor.
- **Следующий gate:** `FF-3` остаётся активным. Первый receive-only IR slice waveform/facts/pulse cursor теперь принят по source, build и physical TFT на dev.351. Следующие deltas добавляют annotations immutable source, сравнение двух Captures и отдельно сохранённый derived decode без изменения raw Captures. RF TX запрещён.

### Functional-first очередь поставки

| Приоритет | Пользовательский срез | Состояние |
|---|---|---|
| FF-0 | Физическая ревью-сборка: пройти все доступные passive top-level workflows, сохранить stable screens/navigation и записать только пользовательские findings | ✅ готово |
| FF-1 | Radar Wi-Fi/BLE и Targets плюс согласованный cross-radio interaction review `FUNC-17` | ✅ готово |
| FF-2 | Поставить `FUNC-43` screenshot устройства → Library → export с provenance build/state/time | ✅ готово |
| FF-3 | Завершить `FUNC-37` Protocol Workbench над immutable Captures; receive-only IR slice waveform/facts/cursor физически принят, annotations/compare/derived decode остаются | 🟡 в работе |
| FF-4 | Завершить `FUNC-38` local USB/Web browse, search, compare и export, не делая сеть зависимостью устройства | ⬜ в очереди |
| FF-5 | Поставить `FUNC-34` IR replay из одного выбранного immutable Capture с preview, confirmation и доказанным Stop/timeout | ⬜ в очереди |
| FF-6 | Вернуться к classification/execution signed packages `FUNC-54`, затем к отдельно допускаемым действиям Safe Lab; Automation/HID остаётся zero-output до активации этой строки | ⏸️ безопасно заморожен |

### Фазы текущего этапа

| Фаза | Результат / exit gate | Статус |
|---|---|---|
| S6.1 | Фундамент Target: стабильные Target ID, точные radio identities, изменяемые name/tags/notes/favorite и неизменяемые ссылки на source evidence; всё bounded и host-verified | ✅ готово |
| S6.2 | Объяснимая correlation предлагает связи с features/confidence; accept/reject и обратимые merge/split никогда не уничтожают source evidence | ✅ готово |
| S6.3 | Baseline/diff сравнивает две Session и классифицирует новые, исчезнувшие и изменившиеся Targets; каждый вывод открывает своё evidence | ✅ готово |
| S6.4 | On-device workflows Targets и Compare сначала показывают полезный результат, сохраняют стабильную навигацию и полноэкранные detail views | ✅ готово |
| S6.5 | Functional-first product train ревьюит и завершает пользовательские вертикальные срезы, пока local companion USB/Web развивается над общими Actions и versioned schemas | 🟡 в работе |
| S6.6 | Integrated device/offline path DEMO-S6 физически принят; завершение фазы ждёт отложенный physical predecessor gate S5 перед acceptance S6 | 🔴 заблокировано |

### Полный каталог пользовательских возможностей

| Возможность | Этап поставки | Статус |
|---|---|---|
| Boot probe определяет профиль платы, main/RF assembly и доступность каждой capability с evidence | S2 + S5 | 🟡 в работе |
| Capability-driven Home показывает только доступные задачи и до запуска объясняет disabled/conflicted/fault | S2 | ✅ готово |
| Устройство → Самопроверка/Диагностика безопасно проверяет применимое железо без TX и экспортирует отчёт | S2 + S5 | ✅ готово |
| TFT, пять клавиш и touch используют единые Actions, калибровку, стабильный выбор и доступный Back | S2 | ✅ готово |
| Сохраняемые EN/RU, brightness/theme/sound, font scale/contrast/reduced motion/input repeat, favorite/hidden apps, shortcuts и startup app | S2 + S5 + S7 | 🟡 в работе |
| Явные Start/Stop создают bounded multi-radio Survey Session с конфигурацией и provenance | S3 + S6.6 | ✅ готово |
| Пассивный Wi-Fi scan: сети, hidden-name enrichment, security/channel/vendor facts и нормализованные Observation | S3 + S4 | ✅ готово |
| Общие стабильные List/Detail/filter для Wi-Fi/BLE/других радио с полной полезной информацией | S3 + S4 | ✅ готово |
| Immutable Capture хранит raw source, время, частоту/канал, RSSI, координаты и настройки приёма | S3 + S4 | ✅ готово |
| Session/Capture сохраняются атомарно и восстанавливаются после reset и controlled power loss | S3 + S5 | 🔴 заблокировано |
| Библиотека офлайн открывает Сессии/Захваты с list/detail/search/filter, integrity state и восстанавливаемой Корзиной/Отменой | S3 + S6 + S7 | 🟡 в работе |
| Экспорт JSON/CSV summary, PCAP и переносимых radio formats с точным provenance | S3 + S5 | 🟡 в работе |
| SD/LittleFS показывают identity, capacity, recovery, integrity и degraded behavior | S3 + S5 | ✅ готово |
| Пассивный BLE scan: strongest-first устройства, company/services facts и нормализованные Observation без active probe | S4 | ✅ готово |
| Три nRF24: RX-only spectrum, receiver-paced однопиксельный waterfall и калиброванный по фону поиск сигнала 2,4 ГГц | S4 + S5.3 | 🔴 заблокировано |
| CC1101: RX-only Sub-GHz spectrum/activity, однопиксельные waterfalls и поиск частоты/RSSI 315/433/868/915 МГц | S4 + S5.4 | 🔴 заблокировано |
| GPS добавляет fix, satellites, time и track к Session только для explicit compatible assembly | S4 + S5 | ⬜ дальше |
| Общая timeline показывает источники, duty cycle, временную недоступность, degradation и dropped events | S4 + S6.6 | ✅ готово |
| Radar/localize для сети или устройства: RSSI history, trend/range и честные пределы оценки близости | S4 + S6 | ✅ готово |
| Wi-Fi channel/packet monitor: текущая/средняя загрузка 1–13, объяснимый свободный канал и bounded PCAP с drop counters | S4 | ✅ готово |
| Видимые питание/заряд/reset reason, low-voltage safe-write и проверяемые sleep/resume | S5 | 🔴 заблокировано |
| Import/export через SD, USB и local companion использует versioned schemas и fail-closed parser | S5 + S6 | 🟡 в работе |
| ИК receive/decode сохраняет оригинал и производные данные, cold-reopen-ит их в Библиотеке и экспортирует CSV | S5.2 | ✅ готово |
| Sub-GHz RAW/OOK/FSK Capture сохраняет pulses/parameters/decodes и экспортирует Flipper-compatible `.sub` из declared decoder inventory | S5.4 + S7 | 🔴 заблокировано |
| PN532 читает tag/NDEF info и versioned dump только при explicit non-conflicting assembly | S5 | 🔴 заблокировано |
| Пользователь сохраняет screenshot реального TFT с build/state/time provenance и открывает его в Library/export | S5 | ✅ готово |
| Единый feedback service владеет status LED антенн и buzzer: default 2/255, quiet mode, bounded tones и доступные без цвета cues | S5 + S6 | ✅ готово |
| Локальные логи, crash journal и экспортируемый diagnostic bundle без облака | S6 + S8 | 🟡 в работе |
| Цель хранит стабильные identities, историю Observation и ссылки на immutable source evidence | S6.1 + S6.4 | ✅ готово |
| Имя, теги, заметки и избранное Цели редактируются bounded и переживают cold reopen | S6.1 + S6.4 | ✅ готово |
| Explainable correlation показывает признаки/confidence; review, accept/reject и merge/split обратимы | S6.2 + S6.4 | ✅ готово |
| Baseline/diff Сессий показывает новые, исчезнувшие и изменившиеся Цели | S6.3 + S6.4 | ✅ готово |
| Каждый вывод compare/correlation открывает точное исходное evidence | S6.3 + S6.4 | ✅ готово |
| Scoped local USB/Web companion просматривает, ищет, сравнивает и экспортирует через общие Actions/schemas | S6.5 | 🟡 в работе |
| Offline OUI/BLE company/services/protocol profiles обогащают факты с version/provenance, не подменяя raw evidence | S6 | ✅ готово |
| Scoped Wi-Fi/USB setup изолирует secrets, не экспортирует их и не делает сеть условием Survey/Library | S6 + S8 | 🟡 в работе |
| Отдельная Лаборатория показывает разрешённый scope, source, frequency, power, duration и постоянно видимый TX state | S7 | ⬜ дальше |
| Назад, timeout, panic, fault или потеря control/telemetry физически прекращает каждый TX path | S7 | ⬜ дальше |
| IR replay использует selected immutable Capture или ready signed multi-button/favorite remote/TV profile после preview и confirmation | S7 | ⬜ дальше |
| Sub-GHz replay/TX из immutable Capture проходит ResourceBroker, bounds, confirm, countdown и stop result | S7 | ⬜ дальше |
| NFC write/restore поддерживаемой собственной метки показывает preview, verify и исходный dump для восстановления | S7, conditional hardware | ⬜ дальше |
| Protocol Workbench сравнивает pulses/waveforms, аннотирует поля и сохраняет derived decode без изменения raw source | S7 | 🟡 в работе |
| Permissioned app descriptor до запуска объявляет capabilities, ресурсы, permissions, safety policy и строки UI | S7 | ⬜ дальше |
| Versioned decoder/profile packages имеют compatibility gate, integrity/signature и scoped storage | S7 + S8 | ⬜ дальше |
| SDK, sample extension и simulator trace kit не позволяют обойти ResourceBroker, permissions или Safety Supervisor | S7 | ⬜ дальше |
| Named profiles/sensitivity Защиты эфира объясняют Wi-Fi/BLE/nRF/Sub-GHz conditions, WPA3/PMF/SAE и jamming indicators с exact evidence/uncertainty | S7 | 🟡 в работе |
| Focused Wi-Fi authentication Capture показывает EAPOL/PMKID и complete/incomplete handshakes, затем экспортирует PCAP и `hc22000` | S7 | ✅ готово |
| Offline Field Survey объединяет Wi-Fi AP/station и BLE с optional GPS track/satellite diagnostics/POI/notes, revisit comparison и WiGLE export | S7 | 🟡 в работе |
| BLE Inspector сохраняет raw compatible packets и входит в connected GATT только после explicit target/permission/lease confirmation | S7 | ✅ готово |
| Device Lock защищает secrets/evidence с PIN/recovery и продолжает admitted Capture под private lock overlay без блокировки Stop | S7 | 🟡 в работе |
| Устройство → Serial Console даёт bounded UART bridge и общий Actions CLI с explicit target/configuration/lease | S7 | 🟡 в работе |
| Permissioned signed Automation/HID имеет preview, ceilings, finite runtime, scoped target и passive-by-default BadUSB inspection | S7 | 🟡 в работе |
| Owned Lab поставляет named Wi-Fi/BLE/nRF/IR recipes для targeted handshake assist, identity/iBeacon, MouseJack, robustness и IR-camera fixtures с containment и Stop | S7 | ⬜ дальше |
| nRF24 ESB Workbench захватывает/декодирует совместимые packets и пассивно обнаруживает MouseJack; injection — отдельный owned-fixture recipe | S7 | ⬜ дальше |
| Read-only Live Companion потоково отдаёт Wi-Fi/BLE evidence в USB Wireshark/extcap и зеркалирует TFT без изменения host network | S7 | ⬜ дальше |
| Conditional Advanced NFC/EMV даёт NDEF/ISO14443-4 emulation, erase, recovery собственной метки и redacted protocol diagnostics | S7, conditional PN532 | ⬜ дальше |
| Privacy Identity рандомизирует STA/AP Leshy и даёт ephemeral provenance-labeled synthetic lab identities из owned Captures | S7 | ⬜ дальше |
| Conditional USB Host Inspector перечисляет device/class interfaces и bounded signed keyboard/HID behavior после VBUS/OTG qualification | S7, conditional hardware | ⬜ дальше |
| Owned Evidence Verification проверяет свои Wi-Fi/NFC/Sub-GHz/fixed-code Captures с budget, pause/stop/checkpoint и provenance | S7 | ⬜ дальше |
| Owned Network Lab даёт read-only LAN inventory и bounded captive-portal/ARP/DHCP/MITM robustness tests на selected isolated fixture | S7 | ⬜ дальше |
| Browser/SD install и Устройство → Обновление: signed stable/beta OTA/SD package, rollback и recovery image | S8 | ⬜ дальше |
| Versioned backup/restore и factory reset показывают scope/preview/checksum и не перезаписывают raw Capture без confirm | S8 | ⬜ дальше |

### Роадмап

- ✅ **S0 — Governance и граница поколений** · готово
- ✅ **S1 — Evidence baseline: пользователи, конкуренты и железо** · готово
- ✅ **S2 — Чистая платформа 1.x** · готово
- ✅ **S3 — Первый вертикальный срез: Survey Session** · готово
- ✅ **S4 — Cross-radio passive platform** · готово
- 🔴 **S5 — Полнота железа ESP32-DIV** · заблокировано
- 🟡 **S6 — Продуктовые отличия: Targets, compare и companion** · в работе
- ⬜ **S7 — Конкурентная полнота, безопасная Lab и расширяемость** · дальше
- ⬜ **S8 — Release hardening и 1.0.0** · дальше

[живой статус и ближайший evidence gate](docs/v1/STATUS.ru.md) · [результаты и exit gates этапов](docs/v1/DELIVERY_PLAN.ru.md) · [полная карта функциональности](docs/v1/DELIVERY_PLAN.ru.md#карта-функциональности-продукта)
<!-- LESHY-ROADMAP:END -->

## Аудит безопасности и разрешённая Лаборатория

Leshy не прячет security-возможности за общим словом «мультитул». Ниже — принятый
пользовательский результат, граница его применения и честный текущий статус. Полный
scope и происхождение требований закреплены в [пофункциональном аудите
конкурентов](docs/v1/COMPETITIVE_ANALYSIS.ru.md#пофункциональный-аудит-паритета),
[требованиях продукта](docs/v1/PRODUCT_REQUIREMENTS.ru.md) и [живом
статусе](docs/v1/STATUS.ru.md).

| Режим | Что получает пользователь | Статус 1.x |
|---|---|---|
| **Passive audit** | **Защита эфира (CF-001):** RX-only предупреждения о disconnect bursts, конфликтующем twin/PineAP-like поведении, подозрительных BLE tracker/skimmer/drone identifiers и длительном росте шума; каждая находка открывает исходное evidence и uncertainty | ✅ физически принято в exact `1.0.0-dev.242`; DEMO-S7 остаётся открыт для остальных capabilities S7 |
| **Passive audit** | **Захват Wi-Fi-аутентификации (CF-002):** различает EAPOL/PMKID и complete/incomplete handshake, сохраняет focused Capture и экспортирует PCAP/`hc22000` | ✅ физически принято в exact `1.0.0-dev.255`: проходят явный atomic Save, cold recovery exact CID, radiotap PCAP из двух frame и одна canonical запись `WPA*02` без сохранения private/raw evidence |
| **Passive audit** | **Полевой обзор (CF-003):** Wi-Fi AP/station и BLE с deduplication, сравнением повторного визита, optional GPS track и локальным WiGLE-compatible экспортом | 🟡 в работе, S7: exact dev.263 физически принимает recovery first/revisit и bounded native плюс честный untimed/unlocated WiGLE export; live station capture и optional trusted GPS/UTC остаются открыты |
| **Passive audit** | **BLE Inspector, приём (CF-004):** сохраняет совместимые raw advertising records с provenance; это не обещание произвольного BLE link-layer sniffing | ✅ физически принято в exact `1.0.0-dev.270`: «RAW пакеты» selected device, bounded capture/freeze, incremental TFT и versioned local export проходят с clean receive-only teardown |
| **Passive audit** | **BadUSB inspection (CF-008):** разбирает подписанный Automation/HID script и показывает target, permissions, действия и пределы без исполнения | 🟡 exact physical dev.303 принимает malformed/unsigned packages, а dev.308 — real public-only enrollment/cold restore/revocation при zero output и complete cleanup; классификация signed package trusted/unknown/invalid следующая, execution отключён |
| **Safe Lab** | **Именованные wireless fixtures (CF-009):** отдельно принятые Wi-Fi/BLE/nRF-рецепты для собственного стенда с выбранными source/target, channel, power/rate, duration, lease и проверяемым Stop | ⬜ запланировано, S7; каждый recipe проходит отдельную safety-приёмку |
| **Safe Lab** | **Собственные сигналы и метки:** IR replay только из immutable Capture; NFC write/restore с preview, verify и recovery dump; Sub-GHz replay — только после доказанного физического Stop | ⬜ запланировано; NFC зависит от PN532, CC1101 TX сейчас заблокирован |
| **Active-confirmed** | **BLE Inspector, GATT (CF-004):** подключается только к явно выбранному устройству и перечисляет services/characteristics под отдельными permission и lease | ✅ exact `1.0.0-dev.276`: explicit permission и second confirmation, live bounded enumeration, cleanup wrong-peer/timeout/resource/disconnect-failure и positive recovery физически приняты с zero pair/read/write/subscribe operations |
| **Active-confirmed** | **Блокировка устройства (CF-006):** local PIN, bounded retry/recovery, optional non-destructive отключение PIN и защита secrets/evidence без блокировки Stop, panic и recovery | ✅ exact dev.331 физически принимает отдельно подтверждённое отключение PIN и exact-CID protected cold reopen без потери данных поверх encrypted storage dev.283 и recovery/admission dev.281; CAP-052 завершён, S7 |
| **Active-confirmed** | **Serial Console (CF-007):** bounded UART monitor/bridge для выбранного внешнего устройства и общий Actions CLI без обхода policy/leases | 🟡 exact dev.285 принимает product UI/CLI и fail-closed path stock RF-shield; positive UART traffic ещё требует проверенного no-RF fixture; произвольный raw GPIO не входит в продукт |
| **Active-confirmed** | **Automation/HID execution (CF-008):** выполняет только подписанный permissioned script после preview цели, действий, ceilings и конечной длительности | ⬜ запланировано, S7; принятый passive dev.308 намеренно всё ещё не имеет HID/Action output path |

**Аппаратная и safety-граница:** переносимый baseline — 16 MB flash и 0 используемой
PSRAM; RF shield, GPS и PN532 всегда определяются probe/profile, а не названием платы.
Три nRF допускают аппаратное снятие `CE`, но ESP32-DIV не умеет независимо
reset/power-gate CC1101, поэтому его TX/replay запрещён до отдельного physical-stop
evidence. Для штатной сборки доказана RF-эффективность CC1101 на 433 МГц; программная
настройка 315/868/915 МГц сама по себе её не доказывает. Подробности:
[аппаратный envelope](docs/v1/HARDWARE_ENVELOPE.ru.md) и [Safety
Supervisor](docs/v1/SAFETY_SUPERVISOR.ru.md).

**Явно вне 1.0:** `CF-005 Peer Link` между двумя DIV отложен после 1.0. Jamming,
неизбирательные flood/spam, crash, credential harvesting и disruptive clone не
являются целями Leshy. Состав сверялся только с официальными первичными источниками:
[ESP32-DIV](https://github.com/CiferTech/ESP32-DIV),
[GhostESP](https://github.com/GhostESP-Revival/GhostESP),
[Bruce](https://github.com/brucedevices/firmware),
[ESP32 Marauder](https://github.com/justcallmekoko/ESP32Marauder) и
[Flipper Zero](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/applications/ReadMe.md).

Выпущенная 0.x остаётся замороженной PoC-линейкой; пользовательский бинарник 1.x
пока не выпускался.

## Линейки версий

- **0.x — архивный PoC:** существующая menu-прошивка, список функций, заметки по
  железу и руководство разработчика сохранены в [архиве 0.x](docs/archive/v0.x/README.ru.md).
  [Веб-установщик](https://anton-vinogradov.github.io/esp32-leshy/) пока прошивает эту
  линейку.
- **1.x — активный редизайн:** продуктовый анализ, архитектура и новое ядро приложений
  с capabilities/resources находятся в разделе [docs/v1](docs/v1/README.ru.md).

Уже существующие checkpoints редизайна по `0.207` включительно сохраняют свои
неизменяемые evidence names. Следующая source-bearing сборка — `1.0.0-dev.208`,
phase-complete candidates имеют вид `1.0.0-rc.N`, а первый stable релиз редизайна —
`1.0.0`.

## Что строит 1.x

Leshy становится полевым инструментом с законченным сценарием:

> обнаружить → идентифицировать → локализовать → записать → сравнить → безопасно
> воспроизвести на своём стенде → сохранить и экспортировать результат.

Продукт строится вокруг Обзора, Целей, Захвата, Лаборатории, Библиотеки и Устройства,
а не постоянно растущего списка разрозненных радиоэкранов. Wi-Fi, BLE, NRF24, CC1101,
IR, NFC, GPS и хранилище становятся общими возможностями этих сценариев.

## С чего читать

- [Индекс документации](docs/README.ru.md)
- [Текущий статус](docs/v1/STATUS.ru.md)
- [Правила документации](docs/v1/GOVERNANCE.ru.md)
- [Этапы достижения 1.0.0](docs/v1/DELIVERY_PLAN.ru.md)
- [Трассировка целей](docs/v1/TRACEABILITY.ru.md)
- [Продуктовая концепция](docs/v1/VISION.ru.md)
- [Конкурентный анализ](docs/v1/COMPETITIVE_ANALYSIS.ru.md)
- [Требования продукта](docs/v1/PRODUCT_REQUIREMENTS.ru.md)
- [Аппаратные возможности и конфликты](docs/v1/HARDWARE_ENVELOPE.ru.md)
- [Целевая архитектура](docs/v1/ARCHITECTURE.ru.md)
- [Архив документации 0.x](docs/archive/v0.x/README.ru.md)

## Разработка

Документация определяет scope и gates 1.x. Текущее состояние кода, прототипов и
проверок фиксируется только в [STATUS](docs/v1/STATUS.ru.md). Роадмап на главной
генерируется из этого статуса и delivery plan, поэтому README не становится второй
конкурирующей точкой истины.

```bash
python3 tools/readme_roadmap.py --write
python3 tools/check_docs.py
tools/test.sh
tools/build.sh
```

## Ответственное использование

Используйте Leshy только со своим оборудованием или там, где есть явное письменное
разрешение. Наблюдение — режим по умолчанию. Передача и replay находятся в отдельной
Лаборатории с видимым состоянием, ограниченным временем и мгновенной остановкой.
Полные условия: [DISCLAIMER.ru.md](DISCLAIMER.ru.md).

## Лицензия и благодарности

[MIT](LICENSE). Железо и оригинальная прошивка —
[CiferTech](https://github.com/CiferTech/ESP32-DIV). Leshy — независимый неофициальный проект.
