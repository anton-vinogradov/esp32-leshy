#!/usr/bin/env python3
"""Disposable Device Lock admission for automated protected-UI HIL."""

from __future__ import annotations

import secrets
from typing import Any

from capture_1x_ui import PassiveSerial
from run_1x_device_lock_hil import device_lock_page, home_device
from run_1x_device_lock_persistence_hil import (
    begin_hil,
    end_hil,
    enter_pin,
    ephemeral_pin,
    fixture_command,
    fixture_failures,
    state_failures,
    wait_lock_state,
    wipe_pin,
)
from run_1x_product_survey_hil import action


class TemporaryDeviceLockHil:
    """Unlock protected UI without reading or mutating product credentials."""

    def __init__(self, device: PassiveSerial, app_identity: str) -> None:
        self.device = device
        self.app_identity = app_identity
        self.run_id = secrets.token_hex(16)
        self.pin = ephemeral_pin()
        self.sessions: list[dict[str, Any]] = []
        self.begin_report: dict[str, Any] = {}
        self.configured_report: dict[str, Any] = {}
        self.cleanup_report: dict[str, Any] = {}
        self.hil_started = False
        self.hil_ended = False
        self.fixture_started = False
        self.cleanup_proven = False
        self.pin_wiped = False

    def rebind(self, device: PassiveSerial) -> None:
        """Use a safely reopened serial transport for fail-closed cleanup."""
        self.device = device

    def start(self) -> dict[str, Any]:
        self.sessions.append(
            begin_hil(self.device, self.run_id, self.app_identity))
        self.hil_started = True
        # Set this before the mutating command: a lost response must still
        # trigger cleanup instead of assuming the fixture never became active.
        self.fixture_started = True
        self.begin_report = fixture_command(self.device, "begin")
        failures = fixture_failures(
            self.begin_report, "fixture_begin", status="begun",
            operation="begin", active=True, selected=True, cleaned=True,
            product_restored=False)
        if failures:
            raise RuntimeError("; ".join(failures))

        home_device(self.device)
        device_lock_page(self.device)
        action(self.device, "right")
        enter_pin(self.device, self.pin)
        enter_pin(self.device, self.pin)
        self.configured_report = wait_lock_state(
            self.device,
            lambda state: state.get("status") == "unlocked",
            "temporary HIL credential enrollment")
        failures = state_failures(
            self.configured_report, "fixture_configured",
            status="unlocked", failure="none", failed_attempts=0,
            generation=1, protected=True, fixture_active=True)
        if failures:
            raise RuntimeError("; ".join(failures))
        return home_device(self.device)

    def close(self) -> None:
        failures: list[str] = []
        try:
            if self.fixture_started and not self.cleanup_proven:
                self.cleanup_report = fixture_command(self.device, "cleanup")
                # A firmware reset invalidates the RAM-only authenticated HIL
                # session before the runner can prove fixture restoration.
                # Reacquire a session only for cleanup; boot has already
                # restored the product namespace and the idempotent cleanup
                # command proves the isolated namespace is empty.
                if self.cleanup_report.get("status") == "hil_session_required":
                    self.sessions.append(
                        begin_hil(self.device, self.run_id, self.app_identity))
                    self.hil_started = True
                    self.hil_ended = False
                    self.cleanup_report = fixture_command(
                        self.device, "cleanup")
                failures.extend(fixture_failures(
                    self.cleanup_report, "fixture_cleanup", status="cleaned",
                    operation="cleanup", active=False, selected=False,
                    cleaned=True, product_restored=True))
                self.cleanup_proven = not failures
            # Keep the authenticated HIL session alive if fixture cleanup did
            # not prove restoration; the caller can safely rebind and retry.
            if (not self.fixture_started or self.cleanup_proven) and \
                    self.hil_started and not self.hil_ended:
                self.sessions.append(end_hil(self.device, self.run_id))
                self.hil_ended = True
        finally:
            if not self.pin_wiped:
                wipe_pin(self.pin)
                self.pin_wiped = True
        if failures:
            raise RuntimeError("; ".join(failures))

    def evidence(self) -> dict[str, Any]:
        return {
            "active_at_end": self.cleanup_report.get("active"),
            "begun": self.begin_report.get("status") == "begun",
            "cleanup_proven": self.cleanup_proven,
            "configured": self.configured_report.get("status") == "unlocked",
            "hil_ended": self.hil_ended,
            "isolated_namespace": True,
            "pin_editor_replies_retained": False,
            "pin_length": 6,
            "pin_or_digest_retained": False,
            "product_namespace_written_or_erased": False,
            "sessions": self.sessions,
            "temporary_credential": True,
            "whole_nvs_read_or_copied": False,
        }
