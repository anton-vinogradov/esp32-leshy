# ESP32-Leshy 1.x

Читать на: [English](README.md) · **Русский**

ESP32-Leshy 1.x — переработанная с нуля прошивка для беспроводного мультитула
[ESP32-DIV](https://github.com/CiferTech/ESP32-DIV).

<!-- LESHY-ROADMAP:START -->
## Статус разработки и роадмап

> **Сейчас: S6 — Продуктовые отличия: Targets, compare и companion**
>
> Закрыто этапов: 5 из 9.

Этот срез главной страницы генерируется из документации-точки-истины 1.x; CI отклоняет рассинхрон.

- **Текущая фаза:** `S6.5 — local USB/Web companion над общими Actions и schemas`.
- **Проверенный checkpoint:** exact `0.196.2-companion-post-web-shared-scratch` на firmware source `7272d237ebb65e4b700ad8c64a32b48fc779ad75` физически принят для boundary **device-only Local Web → Targets → offline USB** в `E-BUILD-153`/`E-AUTO-125`/`E-HIL-183`/`E-COMPANION-007`. Одна exact-прошивка запускает и останавливает SoftAP самого DIV при zero associated stations, явно оставляет network core ESP-IDF process-lifetime, повторно открывает 16 read-only Targets и 7 comparison items, byte-for-byte воспроизводит принятый offline snapshot 11 521 byte и восстанавливает Survey worker в Home/none/lease 0. State codec 24 808 byte и admission scratch 11 272 byte переиспользуют один существующий static union, добавляя zero static RAM. Host network tools не запускаются, активный Wi-Fi Mac не затрагивается.
- **Следующий gate:** один раз прошить exact `1.0.0-dev.208` на original board-01, затем потребовать успешный boot catalog admission exact CID, один непрерывный реальный цикл Survey Wi-Fi+BLE, сохранение после bounded teardown NimBLE, перезагрузку, повторное открытие результата и финал Home/none/lease 0. Активный Wi-Fi ноутбука и Cardputer по-прежнему запрещено затрагивать. Physical HTTP parity остаётся отложенной до отдельного idle adapter или внешнего client, а physical gate S5 — отложенным, но не отменённым, до приезда replacement DIV и прохождения его read-only profile.

### Фазы текущего этапа

| Фаза | Результат / exit gate | Статус |
|---|---|---|
| S6.1 | Фундамент Target: стабильные Target ID, точные radio identities, изменяемые name/tags/notes/favorite и неизменяемые ссылки на source evidence; всё bounded и host-verified | ✅ готово |
| S6.2 | Объяснимая correlation предлагает связи с features/confidence; accept/reject и обратимые merge/split никогда не уничтожают source evidence | ✅ готово |
| S6.3 | Baseline/diff сравнивает две Session и классифицирует новые, исчезнувшие и изменившиеся Targets; каждый вывод открывает своё evidence | ✅ готово |
| S6.4 | On-device workflows Targets и Compare сначала показывают полезный результат, сохраняют стабильную навигацию и полноэкранные detail views | ✅ готово |
| S6.5 | Local companion USB/Web использует те же Actions и versioned schemas с ограниченными connectivity и secrets | 🟡 в работе |
| S6.6 | Интегральный DEMO-S6: записать и сравнить две survey, открыть каждый вывод на устройстве или локально и offline-export; перед принятием S6 вернуться к отложенному physical predecessor gate S5 и закрыть его | ⬜ дальше |

### Пользовательские возможности

| Возможность | Этап поставки | Статус |
|---|---|---|
| Home с версией прошивки, финальным task-first меню и страницами на всю полезную площадь | S2 | ✅ готово |
| Навигация пятью клавишами и touch, стабильный выбор, EN/RU UI и доступные общие компоненты | S2 | ✅ готово |
| Настройки устройства: язык, яркость, тема, питание/sleep и status LED каждой антенны | S2 + S5.5 | ✅ готово |
| Сервисный хаб: Быстрая/Полная самопроверка, Диагностика, recovery state и О системе | S2 + S5.6 | ✅ готово |
| Выбираемый пассивный multi-radio Обзор, долговечная timeline и переиспользуемые Сессии | S3 + S6.6 | 🟡 в работе |
| Сети Wi-Fi рядом: стабильный список, SSID/security/channel/vendor, раскрытие hidden name и live-радар | S4 | ✅ готово |
| Устройства Wi-Fi: пассивные клиенты, vendor/type/model/generation, directed SSID и live-радар | S4 | ✅ готово |
| Каналы Wi-Fi 1–13: текущая и средняя загрузка, границы каналов и объяснимая рекомендация свободного | S4 | ✅ готово |
| Ограниченная запись пакетов Wi-Fi, privacy-confirm, сохранение PCAP, cold reopen и экспорт | S4 | ✅ готово |
| Устройства Bluetooth рядом: strongest-first список, company/service identity и live-радар | S4 | ✅ готово |
| Спектр 2,4 ГГц nRF24 со всех приёмников и receiver-paced однопиксельный водопад | S5.3 | 🔴 заблокировано |
| Поиск сигнала nRF24 2,4 ГГц с калибровкой фона, точной частотой и ближайшим каналом Wi-Fi | S5.3 | 🔴 заблокировано |
| Спектр Sub-GHz и receiver-paced однопиксельные водопады 315/433/868/915 МГц | S5.4 | 🔴 заблокировано |
| Калиброванный поиск частоты Sub-GHz и bounded OOK/FSK приём, сохранение, cold reopen и экспорт | S5.4 | 🔴 заблокировано |
| Приём ИК, декодирование NEC, сохранение, cold reopen в Библиотеке и экспорт CSV | S5.2 | ✅ готово |
| Библиотека Сессий и Захватов с offline reopen и видимым статусом целостности | S4 + S5 | ✅ готово |
| Экспорт CSV/PCAP/offline snapshot с точным provenance исходного evidence | S4–S6.5 | ✅ готово |
| Цели: стабильная identity, избранное/name/tags/notes и переход к immutable evidence | S6.1 + S6.4 | ✅ готово |
| Объяснимая cross-radio correlation с review, accept/reject и обратимыми merge/split | S6.2 + S6.4 | ✅ готово |
| Сравнение baseline: новые, исчезнувшие и изменившиеся Цели с evidence каждого вывода | S6.3 + S6.4 | ✅ готово |
| Scoped local USB companion: просмотр/поиск Сессий, Целей и сравнений и offline export | S6.5 | 🟡 в работе |
| Scoped Web companion на самом устройстве над теми же read-only schemas и Actions | S6.5 | 🟡 в работе |
| Авторизованная Лаборатория: bounded TX/replay, видимый TX, immutable source capture и panic stop | S7 | ⬜ дальше |
| Permissioned extensions и optional hardware profiles GPS/NFC | S7 | ⬜ дальше |
| Устройство → Обновление: signed stable/beta OTA, rollback и recovery | S8 | ⬜ дальше |
| Browser install и зашифрованные backup/restore настроек и пользовательских данных | S8 | ⬜ дальше |
| Автоматические скриншоты реального устройства, delta/full HIL и часовая release qualification | S8 | ⬜ дальше |

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
