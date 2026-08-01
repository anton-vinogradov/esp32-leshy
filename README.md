# 🌲👺 ESP32-Leshy

**A friendlier, more playful alternative firmware for [ESP32-DIV](https://github.com/cifertech/ESP32-DIV) hardware.**

> Same great hardware — nicer to use, and a lot more fun. 😈

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

This is an **educational and security-research** tool. Use it **only** on devices and networks **you own or have explicit permission to test**.

Transmitting to disrupt others (Wi-Fi deauth, jamming, RF flooding) is **illegal in most countries**. Such features, where present, are meant for shielded lab environments and are **off by default**. You are solely responsible for how you use this firmware. The authors accept no liability.

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

- **🛠️ Удобство:** отзывчивый UI, нормальный дебаунс, клавиатура со всеми символами, без ребутов и утечек, честный индикатор батареи, яркость/сон экрана, экспорт CSV/JSON/PCAP, раздельные SPI-шины (лечит «залипание тача после RF»).
- **😈 Пакости:** evil-twin + captive-portal (демо/лаба), BLE-спам всплывашек, фейковые beacon/SSID, режим «увести не туда».
- **📡 Анализ и защита:** **детектор** deauth (пассивный, легальный), водопад активности 2.4 ГГц, Wi-Fi-сниффер + PCAP, BLE-скан + детекторы трекеров/скиммеров/скрытых камер, wardriving (WiGLE CSV), ИК запись/повтор/универсальный пульт.

Подробный приоритизированный план — в [ROADMAP.md](ROADMAP.md).

## ⚖️ Ответственное использование

Это **образовательный** инструмент для **исследований безопасности**. Применяйте его **только** к устройствам и сетям, которые вам **принадлежат или на тест которых есть явное разрешение**.

Передача с целью помешать другим (Wi-Fi deauth, глушение, RF-флуд) **незаконна в большинстве стран**. Такие функции, если они есть, предназначены для экранированного стенда и **выключены по умолчанию**. Ответственность за использование — полностью на вас.

## Лицензия и благодарности

Лицензия — [MIT](LICENSE), в духе оригинального ESP32-DIV.

Отдельное спасибо [CiferTech — ESP32-DIV](https://github.com/cifertech/ESP32-DIV) за железо и оригинальную прошивку (MIT). ESP32-Leshy — **независимая, неофициальная** прошивка, не связана с CiferTech.
