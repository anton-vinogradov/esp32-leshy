#!/usr/bin/env python3
"""Pure admission policy shared by screenshot/Library HIL and host tests."""

from __future__ import annotations

from typing import Any


def owner_protected_access_admitted(state: dict[str, Any]) -> bool:
    """Accept only owner-authorized product states with no lock worker running."""
    return (
        state.get("status") in {"unlocked", "disabled"}
        and state.get("protected_access") is True
        and state.get("worker_active") is False
    )
