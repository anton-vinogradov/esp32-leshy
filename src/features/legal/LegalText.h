#pragma once

// The full legal / responsible-use notice, shown on screen — the same terms as
// DISCLAIMER.md, in both languages. Kept as an array of paragraphs so the screen
// can wrap and scroll it. Blank strings are paragraph spacers; a line starting
// with '#' is a heading.
struct LegalDoc { const char* const* p; int n; };

static const char* const LEGAL_RU[] = {
    "# ТОЛЬКО СВОЁ ОБОРУДОВАНИЕ",
    "ESP32-Leshy — образовательный проект по исследованию безопасности. Применяй его ТОЛЬКО к сетям, устройствам и радио, которые принадлежат тебе, или на тест которых у тебя есть явное письменное разрешение.",
    "",
    "НИКОГДА не направляй эти инструменты на чужое: ни на Wi-Fi соседа, ни на чужой телефон, ни на чью-то сигнализацию, ворота или машину. Без исключений, без «я же просто проверить», без «всего один раз».",
    "",
    "# ЭТО ЗАКОН, А НЕ ПОЖЕЛАНИЕ",
    "Атаковать, перехватывать или создавать помехи устройствам и сетям, которые тебе не принадлежат, без разрешения — преступление в большинстве стран: неправомерный доступ, незаконный перехват, создание радиопомех.",
    "",
    "Отвечать будешь ты, а не авторы прошивки. Авторы ответственности не несут.",
    "",
    "# ЧТО ДЕЛАЕТ ЭТА ПРОШИВКА",
    "Всё, что здесь есть, — пассивное или защитное:",
    "",
    "Скан Wi-Fi и BLE — слушает то, что и так открыто вещается в эфир. Легально.",
    "",
    "Раскрытие скрытых имён — читает имя сети из служебных кадров, где оно и так идёт открытым текстом. Только приём, ничего не отправляется.",
    "",
    "Детектор атак — считает чужие deauth-кадры, чтобы предупредить тебя об атаке. Только приём.",
    "",
    "Здесь НЕТ атак: ни deauth, ни глушения, ни подбора паролей, ни расшифровки чужого трафика.",
    "",
    "# ПРО ГЛУШЕНИЕ",
    "Излучать глушилку в эфир незаконно почти везде, даже против своих устройств: помеху нельзя удержать внутри «своего» — она уходит в общий спектр и мешает соседям, экстренным службам, всем.",
    "",
    "# ПРИВАТНОСТЬ ДРУГИХ ЛЮДЕЙ",
    "Даже пассивное наблюдение может задевать чужую приватность. Не собирай данные о чужих устройствах, не веди слежку за людьми и не публикуй чужие MAC-адреса и имена сетей.",
    "",
    "# ЕСЛИ СОМНЕВАЕШЬСЯ",
    "Не уверен, твоё это устройство или нет — считай, что чужое, и не трогай. Спроси разрешение письменно.",
    "",
    "Продолжая, ты подтверждаешь: применяешь прошивку только к своему оборудованию и берёшь ответственность на себя.",
};

static const char* const LEGAL_EN[] = {
    "# YOUR OWN EQUIPMENT ONLY",
    "ESP32-Leshy is an educational security-research project. Use it ONLY on networks, devices and radios you own, or that you have explicit written permission to test.",
    "",
    "NEVER point these tools at anything that isn't yours: not a neighbor's Wi-Fi, not someone else's phone, not a stranger's alarm, gate or car. No exceptions, no 'just testing', no 'just once'.",
    "",
    "# THIS IS LAW, NOT ADVICE",
    "Attacking, intercepting or disrupting devices and networks you do not own, without authorization, is a crime in most countries: unauthorized access, illegal interception, causing radio interference.",
    "",
    "You are responsible, not the authors. The authors accept no liability.",
    "",
    "# WHAT THIS FIRMWARE DOES",
    "Everything here is passive or defensive:",
    "",
    "Wi-Fi and BLE scan - listens to what is already broadcast openly. Legal.",
    "",
    "Hidden name reveal - reads a network name from management frames that already carry it in cleartext. Receive only, nothing is transmitted.",
    "",
    "Deauth monitor - counts other people's deauth frames to warn you about an attack. Receive only.",
    "",
    "There are NO attacks here: no deauth, no jamming, no password cracking, no decryption of other people's traffic.",
    "",
    "# ABOUT JAMMING",
    "Radiating a jammer over the air is illegal almost everywhere, even against your own devices: interference cannot be contained to 'yours' - it spills into shared spectrum and hurts neighbours, emergency services, everyone.",
    "",
    "# OTHER PEOPLE'S PRIVACY",
    "Even passive observation can touch someone's privacy. Do not collect data about other people's devices, do not track people, and do not publish other people's MAC addresses or network names.",
    "",
    "# WHEN IN DOUBT",
    "If you are not sure whether a device is yours, treat it as someone else's and leave it alone. Ask for written permission.",
    "",
    "By continuing you confirm: you will use this firmware only on your own equipment, and you take responsibility.",
};

static const LegalDoc LEGAL_DOC_RU = { LEGAL_RU, (int)(sizeof(LEGAL_RU) / sizeof(LEGAL_RU[0])) };
static const LegalDoc LEGAL_DOC_EN = { LEGAL_EN, (int)(sizeof(LEGAL_EN) / sizeof(LEGAL_EN[0])) };
