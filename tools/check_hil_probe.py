#!/usr/bin/env python3
"""Fail closed when the S1 read-only probe grows an obvious transmit path."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "diagnostics" / "hil_probe" / "src" / "main.cpp"


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")
    errors: list[str] = []

    forbidden_tokens = {
        "WiFi.h": "ESP Wi-Fi must not start in the evidence image",
        "BLEDevice": "ESP BLE must not start in the evidence image",
        "RF24.h": "radio libraries with write/TX APIs are forbidden",
        "RadioLib": "radio libraries with write/TX APIs are forbidden",
        "0xA0": "NRF W_TX_PAYLOAD opcode is forbidden",
        "0xB0": "NRF W_TX_PAYLOAD_NO_ACK opcode is forbidden",
        "0xE3": "NRF REUSE_TX_PL opcode is forbidden",
        "0x31": "CC1101 SFSTXON command strobe is forbidden",
        "0x34": "CC1101 SRX command strobe is forbidden in identity probe",
        "0x35": "CC1101 STX command strobe is forbidden",
        "0x36": "CC1101 SIDLE command strobe is unnecessary in read-only probe",
        "0x3B": "CC1101 SFTX command strobe is forbidden",
    }
    for token, reason in forbidden_tokens.items():
        if token in text:
            errors.append(f"{reason}: found {token}")

    required_fragments = [
        'constexpr char kRfConfirmation[] = "rf-read shield-no-gps-no-pn532";',
        "constexpr uint8_t kNrfReadRegister = 0x00;",
        "constexpr uint8_t kCcReadPartNumber = 0xF0;",
        "constexpr uint8_t kCcReadVersion = 0xF1;",
        "for (int pin : kNrfCe) digitalWrite(pin, LOW);",
        "pinMode(kNrfCsn[2], INPUT);",
        "if (strcmp(command, kRfConfirmation) == 0)",
    ]
    for fragment in required_fragments:
        if fragment not in text:
            errors.append(f"missing safety invariant: {fragment}")

    if re.search(r"digitalWrite\s*\([^;\n]*kNrfCe[^;\n]*,\s*HIGH\s*\)", text):
        errors.append("NRF CE must never be driven HIGH")
    if "pinMode(kNrfCsn[2], OUTPUT)" in text:
        errors.append("NRF slot 3 CSN must remain input until HW-T08")

    if errors:
        print("HIL probe safety checks failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("HIL probe safety checks passed: no known TX path and guarded contested pins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
