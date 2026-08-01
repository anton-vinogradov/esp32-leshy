# ⚖️ Disclaimer & responsible use

*Read this in: **English** · [Русский](DISCLAIMER.ru.md)*

> **In short — never do any of this to anything that isn't yours.**

## Your own equipment only

ESP32-Leshy is an **educational security-research** firmware. Use it **only** on networks, devices and radios you **own**, or that you have **explicit written permission** to test.

**Never** point these tools at anything that isn't yours: not a neighbor's Wi-Fi, not someone else's phone, not a stranger's alarm, gate, key fob or car. No exceptions, no "just to see if it works", no "just once", no "they won't find out".

## Laws differ from country to country

What is legal in one country is a crime in another. The rules on network access, signal interception and radio transmission **differ everywhere and change over time**. It is **your responsibility to find out and obey the laws of your own jurisdiction** — do not assume, verify; consult a lawyer if needed.

If you are unsure whether something is legal where you are, **treat it as illegal and do not do it until you have confirmed otherwise.**

## Responsibility is yours alone

All responsibility for use rests **solely with the end user — and no one else**. The authors and contributors **accept no liability** whatsoever: not for damage, not for the legal consequences of use or misuse. The software is provided **"as is", without any warranty** (see [LICENSE](LICENSE)).

## What is in the firmware now

Everything in the current build is **passive or defensive**:

- **Wi-Fi and BLE scan** — listens to what is already broadcast openly.
- **Hidden name reveal** — reads a network name from management frames that already carry it in cleartext. Receive only, nothing is transmitted.
- **Deauth monitor** — counts other people's deauth frames to warn you about an attack. Receive only.

## Offensive tools — later, and behind a lock

Some future features are **active** (for example, deauthing *your own* network to test its resilience, and jamming for a bench setup). These will live in a **separate, locked section**: each time, access will require confirming that the equipment is **yours** and that you are **complying with the law**. Off by default.

**About jamming.** Radiating a jammer over the air is **illegal almost everywhere — even against your own devices**: interference cannot be contained to "yours", it spills into shared spectrum and harms neighbours, emergency services, everyone. So that capability is **shielded-bench / own-equipment only** and behind the lock.

## Other people's privacy

Even passive observation can touch someone's privacy. Do not collect data about other people's devices, do not track people, and do not publish other people's MAC addresses or network names.

---

By continuing to use this firmware you confirm: you will use it **only on your own equipment**, you have **checked the laws of your own country yourself**, and you take **all responsibility**.
