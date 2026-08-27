#!/usr/bin/env python3
"""Fail-closed host Wi-Fi and HTTP helpers for the local Web HIL gate."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


NETWORKSETUP = "/usr/sbin/networksetup"
IPCONFIG = "/usr/sbin/ipconfig"
CREDENTIAL_ALPHABET = (
    "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")


def parse_mac(value: str) -> bytes:
    fields = value.split(":")
    if len(fields) != 6 or any(len(field) != 2 for field in fields):
        raise ValueError("SoftAP MAC must contain six hexadecimal octets")
    try:
        parsed = bytes(int(field, 16) for field in fields)
    except ValueError as error:
        raise ValueError(
            "SoftAP MAC must contain six hexadecimal octets") from error
    return parsed


def derive_local_credentials(softap_mac: str, entropy: bytes) -> tuple[str, str]:
    mac = parse_mac(softap_mac)
    if len(entropy) != 16 or not any(entropy):
        raise ValueError("entropy must be exactly 16 non-zero bytes")
    accumulator = 0x6C657368
    password: list[str] = []
    for index, byte in enumerate(entropy):
        accumulator ^= byte << ((index & 3) * 8)
        accumulator = (
            accumulator * 1664525 + 1013904223 + mac[index % len(mac)]
        ) & 0xFFFFFFFF
        if index < 12:
            password.append(CREDENTIAL_ALPHABET[
                (accumulator ^ (accumulator >> 16)) %
                len(CREDENTIAL_ALPHABET)])
    return f"Leshy-{mac[3]:02X}{mac[4]:02X}{mac[5]:02X}", "".join(password)


@dataclass(frozen=True)
class WifiSnapshot:
    interface: str
    service: str
    power_on: bool
    ssid: str | None
    ipv4_address: str | None
    router: str | None
    subnet_mask: str | None

    @property
    def associated(self) -> bool:
        return self.ipv4_address is not None and self.router is not None


CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _default_command_runner(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment.update({"LC_ALL": "C", "LANG": "C"})
    return subprocess.run(
        arguments, check=False, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, env=environment)


class MacWifiGuard:
    """Snapshot, switch and restore one explicitly named macOS Wi-Fi link."""

    def __init__(self, interface: str, service: str,
                 runner: CommandRunner = _default_command_runner,
                 wait_seconds: float = 20.0) -> None:
        if not interface or not service:
            raise ValueError("explicit Wi-Fi interface and service are required")
        self.interface = interface
        self.service = service
        self._runner = runner
        self._wait_seconds = wait_seconds
        self.snapshot: WifiSnapshot | None = None
        self.restored = False
        self.restore_attempted = False
        self.association_attempts = 0
        self.dhcp_requests = 0
        self._mutation_attempted = False
        self._temporary_ssid: str | None = None

    def _run(self, arguments: list[str], operation: str,
             executable: str = NETWORKSETUP) -> str:
        result = self._runner([executable, *arguments])
        if result.returncode != 0:
            # Do not echo arguments: a transient connect command contains the
            # one-shot HIL passphrase.
            raise RuntimeError(f"networksetup {operation} failed")
        return result.stdout.strip()

    def _run_optional(self, arguments: list[str],
                      executable: str) -> str | None:
        result = self._runner([executable, *arguments])
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value if value else None

    def _power(self) -> bool:
        output = self._run(
            ["-getairportpower", self.interface], "read power")
        if output.endswith(": On"):
            return True
        if output.endswith(": Off"):
            return False
        raise RuntimeError("cannot unambiguously parse Wi-Fi power state")

    def _ssid(self) -> str | None:
        output = self._run(
            ["-getairportnetwork", self.interface], "read association")
        prefix = "Current Wi-Fi Network: "
        if output.startswith(prefix) and output[len(prefix):]:
            return output[len(prefix):]
        if "not associated" in output.lower():
            return None
        raise RuntimeError("cannot unambiguously parse Wi-Fi association")

    def _preferred_ssids(self) -> list[str]:
        output = self._run(
            ["-listpreferredwirelessnetworks", self.interface],
            "read preferred networks")
        lines = output.splitlines()
        if not lines or not lines[0].startswith("Preferred networks on "):
            raise RuntimeError(
                "cannot unambiguously parse preferred Wi-Fi networks")
        return [line.strip() for line in lines[1:] if line.strip()]

    def _link_fingerprint(self) -> tuple[str | None, str | None,
                                         str | None]:
        address = self._run_optional(
            ["getifaddr", self.interface], IPCONFIG)
        router = self._run_optional(
            ["getoption", self.interface, "router"], IPCONFIG)
        subnet = self._run_optional(
            ["getoption", self.interface, "subnet_mask"], IPCONFIG)
        return address, router, subnet

    def _request_dhcp_lease(self) -> None:
        result = self._runner([IPCONFIG, "set", self.interface, "DHCP"])
        if result.returncode != 0:
            raise RuntimeError("explicit HIL DHCP lease request failed")
        self.dhcp_requests += 1

    def capture(self) -> WifiSnapshot:
        enabled = self._run(
            ["-getnetworkserviceenabled", self.service],
            "read service state")
        if enabled != "Enabled":
            raise RuntimeError("explicit Wi-Fi service is not enabled")
        power_on = self._power()
        ssid = self._ssid() if power_on else None
        address, router, subnet = (
            self._link_fingerprint() if power_on else (None, None, None))
        self.snapshot = WifiSnapshot(
            self.interface, self.service, power_on, ssid,
            address, router, subnet)
        return self.snapshot

    def _wait_for(self, expected_ssid: str) -> None:
        deadline = time.monotonic() + self._wait_seconds
        while time.monotonic() < deadline:
            if self._ssid() == expected_ssid:
                return
            time.sleep(0.25)
        raise RuntimeError("Wi-Fi association did not reach the expected SSID")

    @staticmethod
    def _is_hil_fingerprint(
            observed: tuple[str | None, str | None, str | None]) -> bool:
        address, router, subnet = observed
        return (
            address is not None and address.startswith("192.168.4.") and
            address != "192.168.4.1" and
            router in (None, "192.168.4.1") and
            subnet == "255.255.255.0"
        )

    def _hil_failure(self, observed: tuple[str | None, str | None,
                                           str | None],
                     join_reported_failure: bool) -> RuntimeError:
        prior = None if self.snapshot is None else (
            self.snapshot.ipv4_address,
            self.snapshot.router,
            self.snapshot.subnet_mask,
        )
        if join_reported_failure:
            reason = "networksetup repeatedly reported join failure"
        elif observed == prior and prior != (None, None, None):
            reason = "prior network remained active after bounded retries"
        elif (observed[0] is not None and
              observed[0].startswith("192.168.4.")):
            reason = "the HIL subnet metadata was inconsistent"
        elif (observed[0] is not None and
              observed[0].startswith("169.254.")):
            reason = "only a link-local address was established"
        elif observed == (None, None, None):
            reason = "no IPv4 link was established"
        else:
            reason = "an unexpected network fingerprint was established"
        return RuntimeError(
            "Wi-Fi did not reach the bounded HIL subnet after "
            f"{self.association_attempts} attempts: {reason}")

    def _wait_for_fingerprint(self, snapshot: WifiSnapshot) -> None:
        deadline = time.monotonic() + self._wait_seconds
        expected = (
            snapshot.ipv4_address, snapshot.router, snapshot.subnet_mask)
        while time.monotonic() < deadline:
            if self._link_fingerprint() == expected:
                return
            time.sleep(0.25)
        raise RuntimeError(
            "Wi-Fi did not restore the prior anonymous link fingerprint")

    def _wait_for_disconnected(self) -> None:
        deadline = time.monotonic() + self._wait_seconds
        while time.monotonic() < deadline:
            if self._ssid() is None:
                return
            time.sleep(0.25)
        raise RuntimeError("Wi-Fi did not return to the disconnected state")

    def connect(self, ssid: str, passphrase: str) -> None:
        if self.snapshot is None:
            raise RuntimeError("Wi-Fi state must be captured before mutation")
        if not ssid or len(passphrase) < 8:
            raise ValueError("bounded HIL SSID and passphrase are required")
        if ssid in self._preferred_ssids():
            raise RuntimeError(
                "temporary HIL SSID already exists as a preferred network")
        self._temporary_ssid = ssid
        self._mutation_attempted = True
        if not self._power():
            self._run(
                ["-setairportpower", self.interface, "on"], "enable power")
        deadline = time.monotonic() + self._wait_seconds
        observed = self._link_fingerprint()
        join_reported_failure = False
        while time.monotonic() < deadline:
            self.association_attempts += 1
            join_output = self._run(
                ["-setairportnetwork", self.interface, ssid, passphrase],
                "join HIL network")
            this_join_reported_failure = (
                "fail" in join_output.lower() or
                "error" in join_output.lower())
            join_reported_failure = (
                join_reported_failure or this_join_reported_failure)
            if this_join_reported_failure:
                if time.monotonic() < deadline:
                    time.sleep(0.25)
                continue
            # networksetup can finish the 802.11 association without waking
            # IPConfiguration for the new link. Ask the existing DHCP-mode
            # service for a lease; never install a static HIL address.
            self._request_dhcp_lease()
            # networksetup may need a fresh scan after the AP starts. Retry
            # the join itself instead of merely polling a stale association.
            attempt_deadline = min(deadline, time.monotonic() + 4.0)
            while time.monotonic() < attempt_deadline:
                observed = self._link_fingerprint()
                if self._is_hil_fingerprint(observed):
                    return
                time.sleep(0.25)
            if time.monotonic() < deadline:
                time.sleep(0.25)
        raise self._hil_failure(observed, join_reported_failure)

    def _remove_temporary_profile(self) -> None:
        if self._temporary_ssid is None:
            return
        if self._temporary_ssid in self._preferred_ssids():
            self._run(
                ["-removepreferredwirelessnetwork", self.interface,
                 self._temporary_ssid],
                "remove HIL preferred network")
        if self._temporary_ssid in self._preferred_ssids():
            raise RuntimeError("temporary HIL preferred network survived removal")
        self._temporary_ssid = None

    def _matches_snapshot(self) -> bool:
        if self.snapshot is None or self._power() != self.snapshot.power_on:
            return False
        if not self.snapshot.power_on:
            return True
        if self.snapshot.ssid is not None:
            return self._ssid() == self.snapshot.ssid
        if self.snapshot.associated:
            return self._link_fingerprint() == (
                self.snapshot.ipv4_address,
                self.snapshot.router,
                self.snapshot.subnet_mask,
            )
        return self._ssid() is None and self._link_fingerprint() == (
            None, None, None)

    def restore(self) -> None:
        self.restore_attempted = True
        if self.snapshot is None:
            raise RuntimeError("no Wi-Fi snapshot exists to restore")
        if not self._mutation_attempted:
            if not self._matches_snapshot():
                raise RuntimeError("unchanged Wi-Fi state no longer matches snapshot")
            self.restored = True
            return
        self._remove_temporary_profile()
        if not self.snapshot.power_on:
            self._run(
                ["-setairportpower", self.interface, "off"],
                "restore power")
            if self._power():
                raise RuntimeError("Wi-Fi power restoration did not hold")
        elif self.snapshot.ssid is not None:
            # No password is supplied: macOS must use the pre-existing saved
            # network. The user's credential never enters the HIL process.
            self._run(
                ["-setairportnetwork", self.interface, self.snapshot.ssid],
                "restore saved network")
            self._wait_for(self.snapshot.ssid)
        elif self.snapshot.associated:
            # Some recent macOS builds redact the current SSID from
            # networksetup even while the link is active. Rejoin through the
            # existing saved-network policy, then prove the exact prior DHCP
            # fingerprint without ever reading or recording that SSID.
            self._run(
                ["-setairportpower", self.interface, "off"],
                "restore anonymous saved network")
            self._run(
                ["-setairportpower", self.interface, "on"],
                "restore anonymous saved network")
            self._wait_for_fingerprint(self.snapshot)
        else:
            # networksetup has no explicit disassociate verb. A bounded power
            # cycle is the only reversible operation that can restore the
            # observed on-but-disconnected state; fail if macOS auto-joins.
            self._run(
                ["-setairportpower", self.interface, "off"],
                "restore disconnected power cycle")
            self._run(
                ["-setairportpower", self.interface, "on"],
                "restore disconnected power cycle")
            self._wait_for_disconnected()
        self.restored = True


def _opener() -> urllib.request.OpenerDirector:
    # The device is a direct RFC1918 peer; ambient HTTP proxy variables must
    # never redirect a local HIL request elsewhere.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_get(url: str, timeout: float = 5.0) -> tuple[int, str, bytes]:
    request = urllib.request.Request(url, method="GET")
    with _opener().open(request, timeout=timeout) as response:
        return response.status, response.headers.get_content_type(), response.read()


def http_companion_request(
    url: str, payload: dict[str, Any], timeout: float = 5.0,
) -> tuple[int, str, dict[str, Any]]:
    encoded = json.dumps(payload, separators=(",", ":")).encode("ascii")
    request = urllib.request.Request(
        url, data=encoded, method="POST",
        headers={"Content-Type": "application/json"})
    with _opener().open(request, timeout=timeout) as response:
        body = json.loads(response.read())
        if not isinstance(body, dict):
            raise RuntimeError("companion HTTP response is not an object")
        return response.status, response.headers.get_content_type(), body
