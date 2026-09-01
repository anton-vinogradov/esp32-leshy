#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
ADVISOR = ROOT / "firmware/leshy1/src/apps/wifi/WifiSecurityAdvisor.cpp"


def require(text: str, needle: str, source: Path) -> None:
    if needle not in text:
        raise SystemExit(f"missing contract marker in {source}: {needle}")


def main() -> None:
    entry = ENTRY.read_text(encoding="utf-8")
    advisor = ADVISOR.read_text(encoding="utf-8")
    require(entry, "assessWifiSecurity(wifiNetworkDetail.wifiNetwork)", ENTRY)
    require(entry, "assessment.passwordCheckAvailable", ENTRY)
    require(advisor, "pmfKnown", ADVISOR)
    require(advisor, "WifiSecurityNextStep::NoPasswordCheck", ADVISOR)
    forbidden = ("esp_wifi_connect", "WiFi.begin", "set_promiscuous", "rawTx")
    for marker in forbidden:
        if marker in advisor:
            raise SystemExit(f"advisor must remain interpretation-only: {marker}")
    print("wifi_security_advisor_contract: PASS")


if __name__ == "__main__":
    main()
