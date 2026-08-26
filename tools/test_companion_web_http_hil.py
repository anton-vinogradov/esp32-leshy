#!/usr/bin/env python3
"""Host tests for the local-Web physical HTTP gate helpers."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from companion_web_http_hil import (  # noqa: E402
    MacWifiGuard,
    derive_local_credentials,
    parse_mac,
)


class FakeNetworkSetup:
    def __init__(self, power: bool = True, ssid: str | None = "Home",
                 redact_ssid: bool = False) -> None:
        self.power = power
        self.ssid = ssid
        self.home_ssid = ssid
        self.redact_ssid = redact_ssid
        self.preferred = {ssid} if ssid is not None else set()
        self.commands: list[list[str]] = []
        self.fail_join = False
        self.address = "10.88.88.60" if power and ssid else None
        self.router = "10.88.88.1" if power and ssid else None
        self.subnet = "255.255.255.0" if power and ssid else None

    def _select_network(self, ssid: str | None) -> None:
        self.ssid = ssid
        if ssid is None:
            self.address = self.router = self.subnet = None
        elif ssid.startswith("Leshy-"):
            self.address = "192.168.4.2"
            self.router = "192.168.4.1"
            self.subnet = "255.255.255.0"
        else:
            self.address = "10.88.88.60"
            self.router = "10.88.88.1"
            self.subnet = "255.255.255.0"

    def __call__(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        self.commands.append(arguments)
        if arguments[0] == "/usr/sbin/ipconfig":
            operation = arguments[1]
            if operation == "getifaddr":
                value = self.address
            elif operation == "getoption" and arguments[3] == "router":
                value = self.router
            elif (operation == "getoption" and
                  arguments[3] == "subnet_mask"):
                value = self.subnet
            else:
                value = None
            return subprocess.CompletedProcess(
                arguments, 0 if value else 1,
                f"{value}\n" if value else "", "")
        operation = arguments[1]
        if operation == "-getnetworkserviceenabled":
            output = "Enabled\n"
        elif operation == "-getairportpower":
            output = f"Wi-Fi Power ({arguments[2]}): {'On' if self.power else 'Off'}\n"
        elif operation == "-getairportnetwork":
            output = (f"Current Wi-Fi Network: {self.ssid}\n"
                      if self.ssid and not self.redact_ssid
                      else "You are not associated with an AirPort network.\n")
        elif operation == "-listpreferredwirelessnetworks":
            entries = "".join(f"\t{name}\n" for name in sorted(self.preferred))
            output = f"Preferred networks on {arguments[2]}:\n{entries}"
        elif operation == "-setairportpower":
            self.power = arguments[3] == "on"
            if not self.power:
                self._select_network(None)
            elif self.home_ssid is not None:
                self._select_network(self.home_ssid)
            output = ""
        elif operation == "-setairportnetwork":
            if self.fail_join:
                return subprocess.CompletedProcess(arguments, 1, "", "no")
            self.power = True
            self._select_network(arguments[3])
            self.preferred.add(arguments[3])
            output = ""
        elif operation == "-removepreferredwirelessnetwork":
            self.preferred.discard(arguments[3])
            if self.ssid == arguments[3]:
                self._select_network(None)
            output = ""
        else:
            return subprocess.CompletedProcess(arguments, 1, "", "unknown")
        return subprocess.CompletedProcess(arguments, 0, output, "")


class CompanionWebHttpHilTests(unittest.TestCase):
    def test_credentials_match_firmware_vector(self) -> None:
        entropy = bytes(range(16))
        ssid, password = derive_local_credentials(
            "1c:db:d4:87:90:d5", entropy)
        self.assertEqual("Leshy-8790D5", ssid)
        self.assertEqual("2qzq5Rh3Txd9", password)
        self.assertEqual(
            (ssid, password), derive_local_credentials(
                "1C:DB:D4:87:90:D5", entropy))

    def test_mac_and_entropy_are_exact(self) -> None:
        self.assertEqual(
            bytes.fromhex("1cdbd48790d5"), parse_mac("1c:db:d4:87:90:d5"))
        for value in ("", "1c:db", "1c-db-d4-87-90-d5", "zz:00:00:00:00:00"):
            with self.assertRaises(ValueError, msg=value):
                parse_mac(value)
        with self.assertRaises(ValueError):
            derive_local_credentials("1c:db:d4:87:90:d5", bytes(16))

    def test_connected_network_is_restored_without_user_password(self) -> None:
        fake = FakeNetworkSetup()
        guard = MacWifiGuard("en0", "Wi-Fi", fake, wait_seconds=0.01)
        snapshot = guard.capture()
        guard.connect("Leshy-8790D5", "temporary123")
        guard.restore()
        self.assertEqual("Home", fake.ssid)
        self.assertNotIn("Leshy-8790D5", fake.preferred)
        self.assertTrue(guard.restored)
        restore = [command for command in fake.commands
                   if command[1] == "-setairportnetwork"][-1]
        self.assertEqual(
            ["/usr/sbin/networksetup", "-setairportnetwork", "en0", "Home"],
            restore)
        self.assertEqual("Home", snapshot.ssid)

    def test_redacted_connected_network_uses_dhcp_fingerprint(self) -> None:
        fake = FakeNetworkSetup(redact_ssid=True)
        guard = MacWifiGuard("en0", "Wi-Fi", fake, wait_seconds=0.01)
        snapshot = guard.capture()
        self.assertIsNone(snapshot.ssid)
        self.assertTrue(snapshot.associated)
        self.assertEqual("10.88.88.60", snapshot.ipv4_address)
        guard.connect("Leshy-8790D5", "temporary123")
        self.assertEqual("192.168.4.2", fake.address)
        guard.restore()
        self.assertEqual("Home", fake.ssid)
        self.assertEqual("10.88.88.60", fake.address)
        self.assertNotIn("Leshy-8790D5", fake.preferred)
        self.assertTrue(guard.restored)

    def test_powered_off_state_is_restored(self) -> None:
        fake = FakeNetworkSetup(power=False, ssid=None)
        guard = MacWifiGuard("en0", "Wi-Fi", fake, wait_seconds=0.01)
        guard.capture()
        guard.connect("Leshy-8790D5", "temporary123")
        guard.restore()
        self.assertFalse(fake.power)
        self.assertNotIn("Leshy-8790D5", fake.preferred)
        self.assertTrue(guard.restored)

    def test_powered_on_disconnected_state_is_restored(self) -> None:
        fake = FakeNetworkSetup(power=True, ssid=None)
        guard = MacWifiGuard("en0", "Wi-Fi", fake, wait_seconds=0.01)
        snapshot = guard.capture()
        self.assertIsNone(snapshot.ssid)
        guard.connect("Leshy-8790D5", "temporary123")
        guard.restore()
        self.assertTrue(fake.power)
        self.assertIsNone(fake.ssid)
        self.assertNotIn("Leshy-8790D5", fake.preferred)
        self.assertTrue(guard.restored)

    def test_existing_preferred_hil_name_fails_before_mutation(self) -> None:
        fake = FakeNetworkSetup()
        fake.preferred.add("Leshy-8790D5")
        guard = MacWifiGuard("en0", "Wi-Fi", fake, wait_seconds=0.01)
        guard.capture()
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            guard.connect("Leshy-8790D5", "temporary123")
        guard.restore()
        self.assertEqual("Home", fake.ssid)
        self.assertIn("Leshy-8790D5", fake.preferred)
        self.assertTrue(guard.restored)

    def test_failure_does_not_disclose_transient_password(self) -> None:
        fake = FakeNetworkSetup()
        fake.fail_join = True
        guard = MacWifiGuard("en0", "Wi-Fi", fake, wait_seconds=0.01)
        guard.capture()
        with self.assertRaises(RuntimeError) as raised:
            guard.connect("Leshy-8790D5", "temporary123")
        self.assertNotIn("temporary123", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
