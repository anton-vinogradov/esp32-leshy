<p align="center">
  <img src="docs/leshy.svg" alt="ESP32-Leshy — a Leshy and a rider broadcasting Wi-Fi" width="820">
</p>

# ESP32-Leshy

*Read this in: **English** · [Русский](README.ru.md)*

**A friendlier, more playful alternative firmware for [ESP32-DIV](https://github.com/cifertech/ESP32-DIV) hardware.**

> Same great hardware — nicer to use, and a lot more fun. 😈

> 🛑 **Only your own equipment.** ESP32-Leshy is an **educational security-research** project. Use it **only** on networks, devices and radios you **own** or are **explicitly authorized in writing** to test. **Never** point these tools at anything that isn't yours — not a neighbor's Wi-Fi, not someone else's phone, not a stranger's alarm or car. Full terms: **[DISCLAIMER.md](DISCLAIMER.md)**.

> ⚠️ **Status: early WIP.** The project just started. Right now this repo is the plan, a skeleton, and the first working modules; code lands module by module. Watch/star to follow along.

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

Targets the **ESP32-DIV v2** platform (details in [docs/hardware.md](docs/hardware.md)):

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

## Features

Working today (tested on real ESP32-DIV hardware unless noted):

- **Wi-Fi scanner** — nearby APs with SSID, channel, RSSI and encryption.
- **Wi-Fi deauth detector** — passive and defensive: watches the air and alerts on deauth/disassoc bursts. Receive-only, fully legal.
- **BLE scanner + tracker detector** — lists nearby BLE devices and flags known trackers (Apple Find My / Tile / Samsung SmartTag).
- **Signal Finder** — a "hot / cold" RSSI direction finder that homes in on a chosen Wi-Fi AP as you walk toward it.
- **Polite Portal** — a captive portal with **no credential logging**: it asks the operator of a nearby AP to lower its Wi-Fi power, verifies the drop via beacon RSSI, and shuts itself down.
- **Bilingual UI (EN / RU)** with an in-app language switch.

The firmware is early WIP — this list is only what actually runs; more lands module by module.

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
- **Banner art (public domain):** ["Leshy", 1906](https://commons.wikimedia.org/wiki/File:Leshy_(1906).jpg) (from the journal *Leshy*) and Ivan Bilibin's ["Red Rider"](https://commons.wikimedia.org/wiki/File:Ivan_Bilibin_-_red-rider-illustration-for-the-fairy-tale-vasilisa-the-beautiful-1899.jpg) (*Vasilisa the Beautiful*, c. 1900) — both in the public domain, via Wikimedia Commons. The Wi-Fi motif was added for this project.
- ESP32-Leshy is an **independent, unofficial** firmware. Not affiliated with or endorsed by CiferTech.
