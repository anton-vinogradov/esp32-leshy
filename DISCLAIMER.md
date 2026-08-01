# ⚖️ Disclaimer & Responsible Use

*Read this in: **English** · [Русский](DISCLAIMER.ru.md)*

> **TL;DR — never do any of this to anything that isn't yours.**

ESP32-Leshy is an **educational, security-research** firmware. It exists so people can learn how wireless systems work and test **their own** gear. Wireless "attacks" only make sense as a learning tool when the target is yours.

## The one rule

**Use it only on equipment you own, or that you have explicit written permission to test.**

That means: **never** run these tools against a neighbor's Wi-Fi, someone else's phone, a stranger's alarm, gate, key fob or car, a shop's tags, an office network, or any device or radio that is not yours. No exceptions. Not "just to see if it works." Not "just once." Not "they'll never know."

Doing so is, in most countries, a **crime** — unauthorized access to a computer system, illegal interception of communications, and/or causing unlawful radio interference — with real fines and jail time. It's also simply a rotten thing to do to another person.

## Per-feature terms

- **Wi-Fi capture (handshake / PMKID), Evil Twin, captive portal, deauth:** only on **your own** network and clients, or a lab you're authorized to test. Capturing or cracking a network you don't own is illegal.
- **"Jamming" / RF interference:** radiating a jammer over the air is **illegal in nearly every country even against your own devices** — interference spills into shared spectrum and can't be contained to "your" device. Any such capability is **shielded-lab-only and OFF by default**. Sending targeted deauth to *your own* network to test resilience is the legitimate alternative.
- **Sub-GHz receive / record / classify:** listening and logging is generally legal. **Replaying** a signal is only OK for **your own** devices (your own gate, your own remote). **Never** replay someone else's alarm, security system, gate or car — it's illegal, and rolling-code systems won't replay anyway.
- **RFID / NFC:** read, dump or emulate **your own** cards only. Cloning access cards you don't own is illegal.
- **BLE spam / spoofing / trickster features:** demos on your own devices only. Bombarding other people's phones is harassment.
- **Wardriving / scanning:** passively logging public beacons is generally legal; be mindful of local privacy law before storing or publishing.

## No warranty, no liability

This software is provided "as is", without warranty of any kind (see [LICENSE](LICENSE)). **You alone** are responsible for how you use it and for obeying the laws of your country. The authors and contributors accept **no liability** for any damage or legal consequence resulting from use or misuse.

If you're not sure whether something is legal where you live — **assume it isn't, and don't.**
