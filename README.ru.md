# ESP32-Leshy 1.x

Читать на: [English](README.md) · **Русский**

ESP32-Leshy 1.x — переработанная с нуля прошивка для беспроводного мультитула
[ESP32-DIV](https://github.com/CiferTech/ESP32-DIV).

<!-- LESHY-ROADMAP:START -->
## Статус разработки и роадмап

> **Сейчас: S6 — Продуктовые отличия: Targets, compare и companion**
>
> Закрыто этапов: 5 из 9.

Этот срез главной страницы генерируется из документации-точки-истины 1.x; CI отклоняет рассинхрон. Checklist полный для принятого baseline из 55 capabilities; аудит принял восемь additions и явно отложил Peer Link до версии после 1.0 в [пофункциональном аудите](docs/v1/COMPETITIVE_ANALYSIS.ru.md#пофункциональный-аудит-паритета).

- **Текущая фаза:** `S6.5 — local USB/Web companion над общими Actions и schemas`.
- **Проверенный checkpoint:** `E-BUILD-193`/`E-AUTO-168`/`E-HIL-206`/`E-STORAGE-034`/`E-SURVEY-018`/`E-UX-063`/`RB-M204` закрывают inherited terminal gate Product Survey на уже прошитом exact image `1.0.0-dev.276`. Один automatic pass Wi-Fi+BLE учитывает 20+31=51 observations, forward-ит 51 и теряет zero, commits SD generation 175→176, затем cold reset принимает exact 176/51 read-only на attempt 1 с exact CID, zero physical writes и invariant heap 148 124/74 828 B. Library снова открывает `field-visit-live`, все cleanup boundaries завершаются Home/none/lease 0. Raw runner остался fail-closed только потому, что final host oracle всё ещё ожидал старое имя `product-passive-live`; retained checker разрешает ровно эту одну ошибку и exact SHA старого runner, повторно проверяет все terminal conditions исправленным oracle и отвергает любое другое расхождение.
- **Следующий gate:** начать следующую незаблокированную принятую возможность CAP-052 Device Lock с host/build foundation для local PIN setup, bounded retry/recovery и cleanup Stop/panic/update/factory reset, который нельзя обойти. Located/timed export CAP-050 всё ещё требует отдельно принадлежащего non-conflicting GPS profile; physical HTTP parity — dedicated client, который не затрагивает active Wi-Fi Mac или Cardputer; deferred S5 RF carrier gate остаётся заблокирован replacement hardware.

### Фазы текущего этапа

| Фаза | Результат / exit gate | Статус |
|---|---|---|
| S6.1 | Фундамент Target: стабильные Target ID, точные radio identities, изменяемые name/tags/notes/favorite и неизменяемые ссылки на source evidence; всё bounded и host-verified | ✅ готово |
| S6.2 | Объяснимая correlation предлагает связи с features/confidence; accept/reject и обратимые merge/split никогда не уничтожают source evidence | ✅ готово |
| S6.3 | Baseline/diff сравнивает две Session и классифицирует новые, исчезнувшие и изменившиеся Targets; каждый вывод открывает своё evidence | ✅ готово |
| S6.4 | On-device workflows Targets и Compare сначала показывают полезный результат, сохраняют стабильную навигацию и полноэкранные detail views | ✅ готово |
| S6.5 | Local companion USB/Web использует те же Actions и versioned schemas с ограниченными connectivity и secrets | 🟡 в работе |
| S6.6 | Integrated device/offline path DEMO-S6 физически принят; завершение фазы ждёт отложенный physical predecessor gate S5 перед acceptance S6 | 🔴 заблокировано |

### Пользовательские возможности по очереди реализации

| Возможность | Этап поставки | Статус |
|---|---|---|
| Boot probe определяет профиль платы, main/RF assembly и доступность каждой capability с evidence | S2 + S5 | 🟡 в работе |
| Capability-driven Home показывает только доступные задачи и до запуска объясняет disabled/conflicted/fault | S2 | ✅ готово |
| Устройство → Самопроверка/Диагностика безопасно проверяет применимое железо без TX и экспортирует отчёт | S2 + S5 | ✅ готово |
| TFT, пять клавиш и touch используют единые Actions, калибровку, стабильный выбор и доступный Back | S2 | ✅ готово |
| Локально сохраняемые EN/RU, яркость, тема, quiet/sound и поведение экрана | S2 + S5 | ✅ готово |
| Явные Start/Stop создают bounded multi-radio Survey Session с конфигурацией и provenance | S3 + S6.6 | ✅ готово |
| Пассивный Wi-Fi scan: сети, hidden-name enrichment, security/channel/vendor facts и нормализованные Observation | S3 + S4 | ✅ готово |
| Общие стабильные List/Detail/filter для Wi-Fi/BLE/других радио с полной полезной информацией | S3 + S4 | ✅ готово |
| Immutable Capture хранит raw source, время, частоту/канал, RSSI, координаты и настройки приёма | S3 + S4 | ✅ готово |
| Session/Capture сохраняются атомарно и восстанавливаются после reset и controlled power loss | S3 + S5 | 🔴 заблокировано |
| Библиотека офлайн открывает Сессии/Захваты и поддерживает list/detail/search/filter и integrity state | S3 + S6 | ✅ готово |
| Экспорт JSON/CSV summary, PCAP и переносимых radio formats с точным provenance | S3 + S5 | 🟡 в работе |
| SD/LittleFS показывают identity, capacity, recovery, integrity и degraded behavior | S3 + S5 | ✅ готово |
| Пассивный BLE scan: strongest-first устройства, company/services facts и нормализованные Observation без active probe | S4 | ✅ готово |
| Три nRF24: RX-only spectrum, receiver-paced однопиксельный waterfall и калиброванный по фону поиск сигнала 2,4 ГГц | S4 + S5.3 | 🔴 заблокировано |
| CC1101: RX-only Sub-GHz spectrum/activity, однопиксельные waterfalls и поиск частоты/RSSI 315/433/868/915 МГц | S4 + S5.4 | 🔴 заблокировано |
| GPS добавляет fix, satellites, time и track к Session только для explicit compatible assembly | S4 + S5 | ⬜ дальше |
| Общая timeline показывает источники, duty cycle, временную недоступность, degradation и dropped events | S4 + S6.6 | ✅ готово |
| Radar/localize для сети или устройства: RSSI history, trend/range и честные пределы оценки близости | S4 + S6 | 🟡 в работе |
| Wi-Fi channel/packet monitor: текущая/средняя загрузка 1–13, объяснимый свободный канал и bounded PCAP с drop counters | S4 | ✅ готово |
| Видимые питание/заряд/reset reason, low-voltage safe-write и проверяемые sleep/resume | S5 | 🔴 заблокировано |
| Import/export через SD, USB и local companion использует versioned schemas и fail-closed parser | S5 + S6 | 🟡 в работе |
| ИК receive/decode сохраняет оригинал и производные данные, cold-reopen-ит их в Библиотеке и экспортирует CSV | S5.2 | ✅ готово |
| Sub-GHz RAW/OOK/FSK Capture сохраняет pulses, radio parameters и производные decode | S5.4 | 🔴 заблокировано |
| PN532 читает tag/NDEF info и versioned dump только при explicit non-conflicting assembly | S5 | 🔴 заблокировано |
| Пользователь сохраняет screenshot реального TFT с build/state/time provenance и открывает его в Library/export | S5 | ⬜ дальше |
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
| IR replay доступен только из выбранного immutable Capture после preview и явного подтверждения | S7 | ⬜ дальше |
| Sub-GHz replay/TX из immutable Capture проходит ResourceBroker, bounds, confirm, countdown и stop result | S7 | ⬜ дальше |
| NFC write/restore поддерживаемой собственной метки показывает preview, verify и исходный dump для восстановления | S7, conditional hardware | ⬜ дальше |
| Protocol Workbench сравнивает pulses/waveforms, аннотирует поля и сохраняет derived decode без изменения raw source | S7 | ⬜ дальше |
| Permissioned app descriptor до запуска объявляет capabilities, ресурсы, permissions, safety policy и строки UI | S7 | ⬜ дальше |
| Versioned decoder/profile packages имеют compatibility gate, integrity/signature и scoped storage | S7 + S8 | ⬜ дальше |
| SDK, sample extension и simulator trace kit не позволяют обойти ResourceBroker, permissions или Safety Supervisor | S7 | ⬜ дальше |
| Защита эфира пассивно обнаруживает/объясняет подозрительные Wi-Fi/BLE conditions и открывает exact evidence/uncertainty каждой находки | S7 | ✅ готово |
| Focused Wi-Fi authentication Capture показывает EAPOL/PMKID и complete/incomplete handshakes, затем экспортирует PCAP и `hc22000` | S7 | ✅ готово |
| Offline Field Survey объединяет Wi-Fi AP/station и BLE observations с optional GPS track, revisit comparison и WiGLE-compatible export | S7 | 🟡 в работе |
| BLE Inspector сохраняет raw compatible packets и входит в connected GATT только после explicit target/permission/lease confirmation | S7 | ✅ готово |
| Device Lock защищает secrets/evidence local PIN, bounded retry и tested recovery, не блокируя Stop/panic/recovery | S7 | 🟡 в работе |
| Устройство → Serial Console даёт bounded UART bridge и общий Actions CLI с explicit target/configuration/lease | S7 | ⬜ дальше |
| Permissioned signed Automation/HID имеет preview, ceilings, finite runtime, scoped target и passive-by-default BadUSB inspection | S7 | ⬜ дальше |
| Authorized wireless Lab поставляет только именованные отдельно принятые Wi-Fi/BLE/nRF fixture recipes с bounded power/channel/time и physical stop | S7 | ⬜ дальше |
| Browser install и Устройство → Обновление: signed stable/beta OTA, rollback и recovery image | S8 | ⬜ дальше |
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
| **Passive audit** | **BadUSB inspection (CF-008):** разбирает подписанный Automation/HID script и показывает target, permissions, действия и пределы без исполнения | ⬜ запланировано, S7 |
| **Safe Lab** | **Именованные wireless fixtures (CF-009):** отдельно принятые Wi-Fi/BLE/nRF-рецепты для собственного стенда с выбранными source/target, channel, power/rate, duration, lease и проверяемым Stop | ⬜ запланировано, S7; каждый recipe проходит отдельную safety-приёмку |
| **Safe Lab** | **Собственные сигналы и метки:** IR replay только из immutable Capture; NFC write/restore с preview, verify и recovery dump; Sub-GHz replay — только после доказанного физического Stop | ⬜ запланировано; NFC зависит от PN532, CC1101 TX сейчас заблокирован |
| **Active-confirmed** | **BLE Inspector, GATT (CF-004):** подключается только к явно выбранному устройству и перечисляет services/characteristics под отдельными permission и lease | ✅ exact `1.0.0-dev.276`: explicit permission и second confirmation, live bounded enumeration, cleanup wrong-peer/timeout/resource/disconnect-failure и positive recovery физически приняты с zero pair/read/write/subscribe operations |
| **Active-confirmed** | **Блокировка устройства (CF-006):** local PIN, bounded retry/recovery и защита secrets/evidence без блокировки Stop, panic и recovery | 🟡 следующий implementation gate, S7 |
| **Active-confirmed** | **Serial Console (CF-007):** bounded UART monitor/bridge для выбранного внешнего устройства и общий Actions CLI без обхода policy/leases | ⬜ запланировано, S7; произвольный raw GPIO не входит в продукт |
| **Active-confirmed** | **Automation/HID execution (CF-008):** выполняет только подписанный permissioned script после preview цели, действий, ceilings и конечной длительности | ⬜ запланировано, S7 |

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
