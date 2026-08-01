# ⚖️ Disclaimer & Responsible Use

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

---
---

# ⚖️ Дисклеймер и ответственное использование

> **Коротко — никогда не делайте ничего из этого не со своим.**

ESP32-Leshy — **образовательная** прошивка для **исследования безопасности**. Она нужна, чтобы разбираться, как устроены беспроводные системы, и тестировать **своё** оборудование. Беспроводные «атаки» имеют смысл как учебный инструмент только тогда, когда цель — ваша собственная.

## Единственное правило

**Используйте только на оборудовании, которое вам принадлежит или на тест которого есть явное письменное разрешение.**

Это значит: **никогда** не направляйте эти инструменты на Wi-Fi соседа, чужой телефон, чью-то сигнализацию, ворота, брелок или машину, магазинные метки, офисную сеть — на любое устройство или радио, которое не ваше. Без исключений. Не «просто проверить, работает ли». Не «всего один раз». Не «они же не узнают».

В большинстве стран это **преступление** — неправомерный доступ к компьютерной системе, незаконный перехват сообщений и/или создание радиопомех — с реальными штрафами и сроком. И это просто подлость по отношению к другому человеку.

## Условия по каждой фиче

- **Перехват Wi-Fi (handshake / PMKID), Evil Twin, captive-portal, deauth:** только на **своей** сети и своих клиентах или на стенде, который вам разрешено тестировать. Перехват/взлом чужой сети незаконен.
- **«Глушение» / радиопомехи:** излучать глушилку в эфир **незаконно почти везде даже против своих устройств** — помеха уходит в общий спектр и не удерживается внутри «своего». Любая такая функция — **только для экранированного стенда и ВЫКЛЮЧЕНА по умолчанию**. Легитимная альтернатива — прицельный deauth в *свою* сеть для проверки устойчивости.
- **Sub-GHz приём / запись / классификация:** слушать и логировать обычно легально. **Воспроизводить** сигнал можно только для **своих** устройств (свои ворота, свой пульт). **Никогда** не воспроизводите чужую сигнализацию, охранную систему, ворота или машину — это незаконно, а против rolling-code всё равно не сработает.
- **RFID / NFC:** читать, дампить и эмулировать только **свои** карты. Клонирование чужих карт доступа незаконно.
- **BLE-спам / подмена / трикстер-фичи:** только демонстрации на своих устройствах. Заваливать всплывашками чужие телефоны — это домогательство.
- **Wardriving / сканирование:** пассивно логировать публичные маяки обычно легально; при хранении/публикации учитывайте местные законы о приватности.

## Без гарантий и ответственности

ПО поставляется «как есть», без каких-либо гарантий (см. [LICENSE](LICENSE)). **Только вы** отвечаете за то, как это используете, и за соблюдение законов своей страны. Авторы и контрибьюторы **ответственности не несут** за любой ущерб или юридические последствия использования либо злоупотребления.

Сомневаетесь, законно ли это у вас, — **считайте, что нет, и не делайте.**
