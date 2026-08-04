#!/usr/bin/env python3
# Build the fixed-width, sorted lookup blobs the firmware binary-searches on LittleFS:
#   data/btco.bin  — Bluetooth SIG company IDs   : record = u16 code (LE) + char[30] name  (32 B)
#   data/oui.bin   — IEEE MA-L OUIs (24-bit)      : record = u8[3] oui (BE) + char[29] name (32 B)
# Sources are fetched once into /tmp. Both files are OPTIONAL at runtime — no file, no lookup.
import json, os, struct, sys, urllib.request

TMP = "/tmp"
OUT = os.path.join(os.path.dirname(__file__), "..", "data")
CO_URL  = "https://raw.githubusercontent.com/NordicSemiconductor/bluetooth-numbers-database/master/v1/company_ids.json"
OUI_URL = "https://www.wireshark.org/download/automated/data/manuf"
CO_NAME, OUI_NAME = 30, 29                      # name field widths → 32-byte records

def fetch(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    print(f"fetch {url}")
    urllib.request.urlretrieve(url, path)
    return path

# Strip trailing legal cruft so names fit the small screen ("Samsung Electronics
# Co.,ltd" -> "Samsung Electronics", "Apple, Inc." -> "Apple"). Suffixes carry a
# leading space/comma so short brands ("Cisco") are never truncated.
_SUFFIXES = [", inc.", ", inc", " inc.", " inc", ", ltd.", ", ltd", " ltd.", " ltd",
             " co.,ltd.", " co.,ltd", " co., ltd.", " co., ltd", " co.", " co", " corporation",
             " corp.", " corp", " technologies", " technology", " gmbh", " llc",
             " limited", " a/s", " ab", " ag", " b.v.", " s.a."]
def clean_name(s):
    s = " ".join(s.split())
    changed = True
    while changed:
        changed = False
        low = s.lower()
        for suf in _SUFFIXES:
            if low.endswith(suf) and len(s) - len(suf) >= 3:
                s = s[:len(s) - len(suf)].rstrip(" ,."); changed = True; break
    return s

def rec_name(s, width):
    b = clean_name(s).encode("ascii", "ignore")[:width]
    return b + b"\x00" * (width - len(b))

def build_companies():
    data = json.load(open(fetch(CO_URL, f"{TMP}/bt_companies.json")))
    rows = sorted(((int(d["code"]), d["name"]) for d in data), key=lambda r: r[0])
    with open(f"{OUT}/btco.bin", "wb") as f:
        for code, name in rows:
            if 0 <= code <= 0xFFFF:
                f.write(struct.pack("<H", code) + rec_name(name, CO_NAME))
    return len(rows), os.path.getsize(f"{OUT}/btco.bin")

def build_oui():
    rows = []
    for line in open(fetch(OUI_URL, f"{TMP}/manuf.txt"), encoding="utf-8", errors="ignore"):
        if line.startswith("#") or not line.strip():
            continue
        parts = line.rstrip("\n").split("\t")
        pref = parts[0].strip()
        if "/" in pref:                          # MA-M / MA-S (finer than 24-bit) — skip, we key on 3 bytes
            continue
        hx = pref.replace(":", "").replace("-", "")
        if len(hx) != 6:
            continue
        try:
            oui = bytes.fromhex(hx)
        except ValueError:
            continue
        name = (parts[2] if len(parts) >= 3 and parts[2].strip() else parts[1] if len(parts) >= 2 else "").strip()
        if not name:
            continue
        rows.append((oui, name))
    rows.sort(key=lambda r: r[0])
    with open(f"{OUT}/oui.bin", "wb") as f:
        for oui, name in rows:
            f.write(oui + rec_name(name, OUI_NAME))
    return len(rows), os.path.getsize(f"{OUT}/oui.bin")

os.makedirs(OUT, exist_ok=True)
nc, sc = build_companies()
no, so = build_oui()
print(f"btco.bin: {nc} companies, {sc} B ({sc/1024:.0f} KB)")
print(f"oui.bin : {no} OUIs, {so} B ({so/1024/1024:.2f} MB)")
print(f"total   : {(sc+so)/1024/1024:.2f} MB  (LittleFS partition = 1.5 MB)")
