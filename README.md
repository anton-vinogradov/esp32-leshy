<p align="center">
  <img src="docs/leshy.svg" alt="ESP32-Leshy — a Leshy and a rider broadcasting Wi-Fi" width="820">
</p>

# ESP32-Leshy

*Read this in: **English** · [Русский](README.ru.md)*

**A playful, trickster-themed alternative firmware for the [ESP32-DIV](https://github.com/cifertech/ESP32-DIV) multitool.**

> The same great hardware — with a mischievous streak. 😈

> 🛑 **Only your own equipment.** ESP32-Leshy is an **educational security-research** project. Use it **only** on networks, devices and radios you **own** or are **explicitly authorized in writing** to test. **Never** point these tools at anything that isn't yours — not a neighbor's Wi-Fi, not someone else's phone, not a stranger's alarm or car. Full terms: **[DISCLAIMER.md](DISCLAIMER.md)**.

> ⚠️ **Status: actively developed.** A working, menu-driven firmware with Wi-Fi and BLE tools already runs on real hardware; more features land regularly. Watch/star to follow along.

---

## What is this?

**ESP32-Leshy** is an independent, from-scratch firmware for the excellent **ESP32-DIV** wireless multitool by [CiferTech](https://github.com/cifertech/ESP32-DIV) — the same ESP32-S3 board with its display, NRF24, CC1101, RFID/NFC, GPS and IR modules.

CiferTech's **ESP32-DIV — both the board and its firmware — is a fantastic, generous open-source project**, and it's the whole reason this one can exist. ESP32-Leshy isn't a "better" replacement; it's a **different flavor** with its own personality:

- **a playful "trickster" theme** — a toolkit built around spoofing, redirects and good-natured RF mischief rather than brute force;
- **its own UI take** — a menu-driven interface with keypad + touch, on-screen Wi-Fi setup from your phone, and a bilingual EN/RU interface;
- **a modular codebase** — small, separate modules that are easy to build on and learn from.

If you enjoy ESP32-DIV, please **star and support the original first** — Leshy simply stands on its shoulders. 🙏

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

A working, menu-driven firmware — highlights, all passive / own-equipment:

- **Wi-Fi** — scan (signal, channel, security, ★your net, per-AP sparkline; **▶** = per-network options), live 2.4 GHz channel graphs, hidden-SSID reveal, deauth monitor.
- **BLE** — devices + tracker detector.
- **Connectivity** — join your Wi-Fi from your phone (no keyboard); **OTA update from GitHub releases** (SHA-256 + auto-rollback, auto-check on connect).
- Bilingual **EN / RU**, multi-level menu, keypad **and** touch.

📖 **Full feature list and menu map: [docs/features.md](docs/features.md).**  Coming: Sub-GHz recorder (CC1101), raw 2.4 GHz spectrum (NRF24).

## ⚖️ Legal & responsible use

**For education and testing your OWN equipment. Nothing else.**

- ✅ **Do:** run it against **your own** Wi-Fi, devices and radios — or a lab you have **explicit written permission** to test.
- 🛑 **Never** point it at anything that isn't yours. No exceptions, no "just testing", no "just once".
- 🌍 **Laws differ by country and change over time** — it's on **you** to check and obey your own jurisdiction's rules. Don't assume; verify. Unsure → treat it as illegal and don't.
- ⚖️ **All responsibility is yours alone.** The authors accept **no liability**. Software is "as is", no warranty.

The current build is passive/defensive only. Any future **offensive tools (incl. jamming) will live behind a lock** that requires confirming, every time, that the gear is yours and that you comply with the law.

📜 Read the full notice — the **same text the firmware shows on first boot** — in **[DISCLAIMER.md](DISCLAIMER.md)**.

## License

[MIT](LICENSE) — same spirit as the original ESP32-DIV.

## Credits

- **Hardware & original firmware:** [CiferTech — ESP32-DIV](https://github.com/cifertech/ESP32-DIV) (MIT). Huge thanks — none of this exists without their board.
- **Banner art (public domain):** ["Leshy", 1906](https://commons.wikimedia.org/wiki/File:Leshy_(1906).jpg) (from the journal *Leshy*) and Ivan Bilibin's ["Red Rider"](https://commons.wikimedia.org/wiki/File:Ivan_Bilibin_-_red-rider-illustration-for-the-fairy-tale-vasilisa-the-beautiful-1899.jpg) (*Vasilisa the Beautiful*, c. 1900) — both in the public domain, via Wikimedia Commons. The Wi-Fi motif was added for this project.
- ESP32-Leshy is an **independent, unofficial** firmware. Not affiliated with or endorsed by CiferTech.
