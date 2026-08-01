# 🌲👺 ESP32-Leshy

**A friendlier, more playful alternative firmware for [ESP32-DIV](https://github.com/cifertech/ESP32-DIV) hardware.**

> Same great hardware — nicer to use, and a lot more fun. 😈

> 🛑 **Only your own equipment.** ESP32-Leshy is an **educational security-research** project. Use it **only** on networks, devices and radios you **own** or are **explicitly authorized in writing** to test. **Never** point these tools at anything that isn't yours — not a neighbor's Wi-Fi, not someone else's phone, not a stranger's alarm or car. Full terms: **[DISCLAIMER.md](DISCLAIMER.md)**.

> ⚠️ **Status: early WIP.** The project just started. Right now this repo is the plan and the skeleton; code lands module by module. Watch/star to follow along.

---

## What is this?

**ESP32-Leshy** is a from-scratch firmware that runs on the **ESP32-DIV** wireless multitool by [CiferTech](https://github.com/cifertech/ESP32-DIV) — the same ESP32-S3 board with its display, NRF24, CC1101, RFID/NFC, GPS and IR modules.

We love the hardware. We just want a firmware that is:

- **easier to live with** — snappy UI, buttons that don't double-fire, a keyboard that can actually type a full Wi-Fi password, no random reboots;
- **more fun** — a mischievous "trickster" toolkit built around spoofing, redirects and playful RF pranks;
- **cleaner inside** — modular code you can build and extend, instead of one giant sketch.

## Why "Leshy"?

The **Leshy** (Ле́ший) is a shapeshifting trickster spirit of the Slavic forest. He doesn't destroy — he *misleads*: he changes shape, mimics familiar voices, and **leads wanderers off the path**. That is exactly the vibe here: shapeshifting (spoofing), leading devices astray (redirects, evil-twin, captive portals), and playful mischief rather than brute-force destruction.

## Hardware

Targets the **ESP32-DIV v2** platform:

| Part | Role |
|------|------|
| ESP32-S3 | main MCU, built-in Wi-Fi + BLE |
| 2.8" TFT (ILI9341) + touch (XPT2046) | UI |
| 3× NRF24L01 | 2.4 GHz sweep / spectrum |
| CC1101 | Sub-GHz RX/replay |
| PN532 | RFID / NFC (13.56 MHz) |
| GPS (NEO-6M) | wardriving |
| IR TX/RX | remotes |
| microSD | logging (PCAP / CSV / profiles) |

You need the ESP32-DIV board (or a compatible DIY build) to run Leshy. We don't sell hardware — buy or build the [ESP32-DIV](https://github.com/cifertech/ESP32-DIV).

## Planned features

**🛠️ Quality of life (the "finally usable" bucket)**
- Responsive UI — radio scans never freeze input or drawing
- Solid button debounce (no more one-press-counts-as-two)
- On-screen keyboard with the **full** character set
- No spurious reboots / memory leaks (NimBLE, heap discipline, watchdog)
- Honest battery gauge (IP5306 over I²C), brightness control, screen sleep
- Export to SD: CSV / JSON / PCAP with timestamps
- Split SPI buses (touch / radio / SD) — fixes the classic "touch dies after RF" bug
- Bilingual UI (EN / RU) with an in-app language switch

**😈 Trickster toolkit (the fun bucket)**
- Evil-twin AP + captive portal (demo/lab)
- BLE notification spam (Apple/Android proximity pop-ups)
- Fake beacon / SSID flood
- "Lead astray" mode — playful redirects

**📡 Analysis & defense (the responsible bucket)**
- Wi-Fi deauth **detector** (passive, fully legal)
- 2.4 GHz activity waterfall (NRF24 RPD sweep)
- Wi-Fi sniffer + PCAP for Wireshark
- BLE scanner + tracker / skimmer / hidden-camera detectors
- GPS wardriving (WiGLE CSV)
- IR record / replay / universal remote

See [ROADMAP.md](ROADMAP.md) for the prioritized plan.

## ⚖️ Legal & responsible use

**This project is for education and for testing your OWN equipment. Nothing else.**

- ✅ **Do:** run it against **your own** Wi-Fi, your own devices, your own radios and cards — or a lab/network you have **explicit written permission** to test.
- 🛑 **Never do this to anything that isn't yours.** Not a neighbor's Wi-Fi. Not someone else's phone. Not a stranger's alarm, gate, or car. No exceptions, no "just testing," no "just once."

Attacking, intercepting, or disrupting devices and networks you don't own — **without authorization — is a crime** in most countries (unauthorized access, illegal interception, causing radio interference), on top of being a jerk move.

**About "jamming":** radiating a jammer *over the air* is **illegal in nearly every country even against your own devices**, because interference cannot be contained to "your" device — it spills into shared spectrum. Any interference/jamming capability here is **shielded-lab-only and off by default**. (Sending targeted deauth frames to *your own* network to test its resilience is a different, legitimate thing.)

You alone are responsible for what you do with this firmware. The authors accept **no liability**. See **[DISCLAIMER.md](DISCLAIMER.md)** for the full, per-feature terms.

## License

[MIT](LICENSE) — same spirit as the original ESP32-DIV.

## Credits

- **Hardware & original firmware:** [CiferTech — ESP32-DIV](https://github.com/cifertech/ESP32-DIV) (MIT). Huge thanks — none of this exists without their board.
- ESP32-Leshy is an **independent, unofficial** firmware. Not affiliated with or endorsed by CiferTech.

---
---

# 🌲👺 ESP32-Leshy (по-русски)

**Более удобная и весёлая альтернативная прошивка для железа [ESP32-DIV](https://github.com/cifertech/ESP32-DIV).**

> То же отличное железо — но пользоваться приятнее, и куда прикольнее. 😈

> 🛑 **Только своё оборудование.** ESP32-Leshy — **образовательный** проект по **исследованию безопасности**. Применяйте его **только** к сетям, устройствам и радио, которые вам **принадлежат** или на тест которых есть **явное письменное разрешение**. **Никогда** не направляйте эти инструменты на чужое — ни на Wi-Fi соседа, ни на чужой телефон, ни на чью-то сигнализацию или машину. Полные условия: **[DISCLAIMER.md](DISCLAIMER.md)**.

> ⚠️ **Статус: ранний WIP.** Проект только стартовал. Пока в репе план и каркас; код приезжает модуль за модулем. Ставь ⭐ и watch, чтобы следить.

## Что это?

**ESP32-Leshy** — прошивка, написанная с нуля под беспроводной мультитул **ESP32-DIV** от [CiferTech](https://github.com/cifertech/ESP32-DIV): та же плата на ESP32-S3 с дисплеем, NRF24, CC1101, RFID/NFC, GPS и ИК.

Железо — супер. Хочется прошивку, которая:

- **удобнее в быту** — отзывчивый UI, кнопки без двойных срабатываний, клавиатура, которой реально можно ввести полный пароль Wi-Fi, без случайных ребутов;
- **прикольнее** — набор «трикстера»-пакостника: подмена, редиректы и игривые RF-каверзы;
- **чище внутри** — модульный код, который легко собирать и расширять, а не один гигантский скетч.

## Почему «Leshy»?

**Леший** — дух-оборотень славянского леса. Он не разрушает, а **морочит**: меняет облик, аукается знакомым голосом и **уводит путников не туда**. Ровно наш настрой: оборотничество (спуфинг), увод устройств не туда (редиректы, evil-twin, captive-portal) и игривые каверзы вместо грубой силы.

## Железо

Целевая платформа — **ESP32-DIV v2** (ESP32-S3, TFT 2.8" + тач, 3× NRF24L01, CC1101, PN532, GPS NEO-6M, ИК, microSD). Чтобы запустить Leshy, нужна плата ESP32-DIV (или совместимая DIY-сборка). Железо мы не продаём — берите/собирайте [ESP32-DIV](https://github.com/cifertech/ESP32-DIV).

## Что планируется

- **🛠️ Удобство:** отзывчивый UI, нормальный дебаунс, клавиатура со всеми символами, без ребутов и утечек, честный индикатор батареи, яркость/сон экрана, экспорт CSV/JSON/PCAP, раздельные SPI-шины (лечит «залипание тача после RF»), **двуязычный интерфейс (EN/RU)** с переключателем.
- **😈 Пакости:** evil-twin + captive-portal (демо/лаба), BLE-спам всплывашек, фейковые beacon/SSID, режим «увести не туда».
- **📡 Анализ и защита:** **детектор** deauth (пассивный, легальный), водопад активности 2.4 ГГц, Wi-Fi-сниффер + PCAP, BLE-скан + детекторы трекеров/скиммеров/скрытых камер, wardriving (WiGLE CSV), ИК запись/повтор/универсальный пульт.

Подробный приоритизированный план — в [ROADMAP.md](ROADMAP.md).

## ⚖️ Ответственное использование

**Проект — для обучения и тестирования СВОЕГО оборудования. И ничего больше.**

- ✅ **Можно:** свой Wi-Fi, свои устройства, своё радио и свои карты — или стенд/сеть, на тест которых есть **явное письменное разрешение**.
- 🛑 **Никогда не делайте так не со своим.** Ни с Wi-Fi соседа. Ни с чужим телефоном. Ни с чьей-то сигнализацией, воротами или машиной. Без исключений, без «я же просто проверить», без «всего один раз».

Атаковать, перехватывать или создавать помехи устройствам и сетям, которые вам не принадлежат, **без разрешения — это преступление** в большинстве стран (неправомерный доступ, незаконный перехват, создание радиопомех) — и просто подлость.

**Про «глушение»:** излучать глушилку *в эфир* **незаконно почти везде даже против своих устройств**, потому что помеху нельзя удержать внутри «своего» — она уходит в общий спектр. Любая функция помех/глушения здесь — **только для экранированного стенда и выключена по умолчанию**. (Отправить прицельный deauth в *свою собственную* сеть, чтобы проверить её устойчивость, — это другое, легитимное дело.)

Ответственность за использование прошивки — целиком на вас. Авторы **ответственности не несут**. Полные условия по каждой фиче — в **[DISCLAIMER.md](DISCLAIMER.md)**.

## Лицензия и благодарности

Лицензия — [MIT](LICENSE), в духе оригинального ESP32-DIV.

Отдельное спасибо [CiferTech — ESP32-DIV](https://github.com/cifertech/ESP32-DIV) за железо и оригинальную прошивку (MIT). ESP32-Leshy — **независимая, неофициальная** прошивка, не связана с CiferTech.
