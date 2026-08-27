# ESP32-Leshy 1.x

Читать на: [English](README.md) · **Русский**

ESP32-Leshy 1.x — переработанная с нуля прошивка для беспроводного мультитула
[ESP32-DIV](https://github.com/CiferTech/ESP32-DIV).

<!-- LESHY-ROADMAP:START -->
## Статус разработки и роадмап

> **Сейчас: S6 — Продуктовые отличия: Targets, compare и companion**
>
> Закрыто этапов: 5 из 9.

Этот срез главной страницы генерируется из документации-точки-истины 1.x; CI отклоняет рассинхрон. Checklist полный для принятого baseline из 47 capabilities; девять candidates конкурентного паритета ждут явного решения о scope в [пофункциональном аудите](docs/v1/COMPETITIVE_ANALYSIS.ru.md#пофункциональный-аудит-паритета).

- **Текущая фаза:** `S6.5 — local USB/Web companion над общими Actions и schemas`.
- **Проверенный checkpoint:** exact `1.0.0-dev.209` на firmware source `e04d98dd3c5e5d494c615e12f2897dc3207272a9` теперь физически проходит **integrated device/offline path DEMO-S6** в `E-AUTO-132`/`E-HIL-189`/`E-DEMO-006`. Уже принятые no-flash Survey образуют contiguous generations 164/165 с 52/49 observations; исправленный harness открывает все пять реальных conclusions сравнения и их exact evidence, экспортирует ту же пару в canonical offline USB snapshot 11 882 byte с двумя Sessions, 16 Targets и пятью comparisons и завершает Home/none/lease 0 с safety armed. Дополнительной flash, DUT TX, storage write, serial discovery, доступа к Cardputer, SoftAP, host-network command или изменения активного Wi-Fi Mac нет.
- **Следующий gate:** закрыть physical HTTP payload parity через отдельный idle adapter или внешний client без затрагивания активного Wi-Fi Mac. Integrated device/offline path S6.6 принят, но final acceptance S6 всё ещё ждёт это proof S6.5 и отложенный physical predecessor gate S5 после приезда replacement DIV и прохождения его read-only profile.

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
- ⬜ **S7 — Безопасная Lab и расширяемость** · дальше
- ⬜ **S8 — Release hardening и 1.0.0** · дальше

[живой статус и ближайший evidence gate](docs/v1/STATUS.ru.md) · [результаты и exit gates этапов](docs/v1/DELIVERY_PLAN.ru.md) · [полная карта функциональности](docs/v1/DELIVERY_PLAN.ru.md#карта-функциональности-продукта)
<!-- LESHY-ROADMAP:END -->

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
