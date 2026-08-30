#!/usr/bin/env python3
"""Adversarial host tests for the top-level menu HIL smoke."""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

import run_1x_top_level_menu_smoke_hil as runner


def ui_state(case: runner.MenuCase, **overrides: Any) -> dict[str, Any]:
    state = case.expected()
    state.update(overrides)
    return state


def passing_result() -> dict[str, Any]:
    menus = []
    for case in runner.MENU_CASES:
        home = {
            "page": "home", "selected_id": case.item_id,
            "runtime_owner": "none", "lease_mask": 0,
        }
        menus.append({
            "id": case.item_id, "index": case.index,
            "passed": True, "failures": [],
            "effective_dwell_seconds": case.minimum_dwell_seconds,
            "dwell_samples": [
                ui_state(case, host_dwell_offset_ms=0.0),
                ui_state(
                    case,
                    host_dwell_offset_ms=
                        case.minimum_dwell_seconds * 1000.0),
            ],
            "home_settled": home,
        })
    return {
        "schema": runner.RUN_SCHEMA,
        "candidate": {"verified": True},
        "policy": {
            "board_id": runner.BOARD_ID, "exact_port": runner.BOARD_PORT,
            "top_level_only": True, "nested_actions_selected": 0,
            "dangerous_tx_started": False,
            "mac_wifi_or_ble_controlled": False,
            "manual_button_presses": 0,
            "product_storage_writes_measured": False,
            "isolated_device_lock_fixture": True,
            "pin_or_digest_retained": False,
            "product_lock_namespace_written_or_erased": False,
        },
        "menus": menus,
        "device_lock_fixture": {
            "begin": {
                "status": "begun", "active": True,
                "product_namespace_written_or_erased": False,
            },
            "unlocked": {
                "status": "unlocked", "protected_access": True,
                "persistence_fixture_active": True,
            },
            "cleanup": {
                "status": "cleaned", "active": False,
                "product_restored": True,
                "product_namespace_written_or_erased": False,
            },
            "product_before": {
                "status": "unconfigured", "credential_generation": 0,
                "failed_attempts": 0,
            },
            "product_after": {
                "status": "unconfigured", "credential_generation": 0,
                "failed_attempts": 0,
            },
        },
        "cleanup_after": {"complete": True},
        "safe_outputs": {
            "buzzer_inactive": True, "nrf_ce_inactive": True,
            "software_quiesce_complete": True,
        },
        "input": {"status": "ready", "read_errors": 0, "queue_drops": 0},
        "recovery_before": {"generation": 12, "observations": 34},
        "recovery_after": {
            "generation": 12, "observations": 34,
            "physical_write_calls": 0,
        },
        "boot_recovery_continuity": True,
        "hil_session": {
            "begin": {"active": True}, "end": {"active": False},
        },
        "post_hil_end": {
            "hil": {"active": False},
            "ui": {"page": "home", "runtime_owner": "none",
                   "lease_mask": 0},
        },
        "catalog_boundary": {
            "page": "home", "selection": runner.MENU_CASES[-1].index,
            "selected_id": runner.MENU_CASES[-1].item_id,
            "changed": False, "runtime_owner": "none", "lease_mask": 0,
        },
    }


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class MenuStateContractTests(unittest.TestCase):
    def test_exact_state_passes(self) -> None:
        for case in runner.MENU_CASES:
            self.assertEqual([], runner.state_failures(
                case, ui_state(case), case.item_id))

    def test_immediate_bounce_is_rejected(self) -> None:
        case = runner.MENU_CASES[1]
        failures = runner.state_failures(case, ui_state(
            case, page="home", parent_page="home", runtime_owner="none",
            lease_mask=0), "ble")
        self.assertTrue(any("bounce" in failure for failure in failures))
        self.assertTrue(any("runtime/lease disappeared" in failure
                            for failure in failures))

    def test_wrong_page_owner_and_lease_are_each_rejected(self) -> None:
        case = runner.MENU_CASES[1]
        for field, value in (
                ("page", "capture"), ("runtime_owner", "wifi"),
                ("lease_mask", 1)):
            with self.subTest(field=field):
                self.assertTrue(runner.state_failures(
                    case, ui_state(case, **{field: value}), "ble"))

    def test_wrong_selection_and_disabled_item_are_rejected(self) -> None:
        case = runner.MENU_CASES[4]
        self.assertTrue(runner.state_failures(
            case, ui_state(case, selected_id="ble"), "capture"))
        self.assertTrue(runner.state_failures(
            case, ui_state(case, selected_enabled=False), "capture"))

    def test_safety_latch_is_rejected(self) -> None:
        case = runner.MENU_CASES[0]
        self.assertTrue(runner.state_failures(
            case, ui_state(case, safety_latched=True), "wifi"))


class DwellTests(unittest.TestCase):
    def test_terminal_boundary_is_sampled(self) -> None:
        case = runner.MENU_CASES[1]
        clock = FakeClock()
        calls = 0

        def query(_device: object) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return ui_state(case)

        samples, failures = runner.collect_stable_dwell(
            object(), case, ui_state(case), 0.5, 0.2,
            query_state=query, monotonic=clock.monotonic, sleep=clock.sleep)
        self.assertEqual([], failures)
        self.assertGreaterEqual(len(samples), 4)
        self.assertGreaterEqual(samples[-1]["host_dwell_offset_ms"], 500.0)
        self.assertEqual(len(samples) - 1, calls)

    def test_delayed_ble_bounce_is_rejected(self) -> None:
        case = runner.MENU_CASES[1]
        clock = FakeClock()

        def query(_device: object) -> dict[str, Any]:
            if clock.now < 0.4:
                return ui_state(case)
            return ui_state(
                case, page="home", parent_page="home",
                runtime_owner="none", lease_mask=0)

        samples, failures = runner.collect_stable_dwell(
            object(), case, ui_state(case), 0.6, 0.2,
            query_state=query, monotonic=clock.monotonic, sleep=clock.sleep)
        self.assertGreaterEqual(len(samples), 4)
        self.assertTrue(any("bounce" in failure for failure in failures))

    def test_ble_effective_dwell_cannot_be_configured_below_minimum(self) -> None:
        ble = runner.MENU_CASES[1]
        self.assertEqual(runner.BLE_MINIMUM_DWELL_SECONDS,
                         runner.effective_dwell_seconds(ble, 0.5))
        self.assertGreaterEqual(
            runner.effective_dwell_seconds(ble, runner.DEFAULT_DWELL_SECONDS),
            15.0)
        self.assertEqual(15.0, runner.effective_dwell_seconds(ble, 12.0))
        self.assertEqual(16.0, runner.effective_dwell_seconds(ble, 16.0))

    def test_ble_bounce_near_full_lifecycle_boundary_is_rejected(self) -> None:
        case = runner.MENU_CASES[1]
        clock = FakeClock()

        def query(_device: object) -> dict[str, Any]:
            if clock.now < 14.9:
                return ui_state(case)
            return ui_state(
                case, page="home", parent_page="home",
                runtime_owner="none", lease_mask=0)

        samples, failures = runner.collect_stable_dwell(
            object(), case, ui_state(case), 15.0, 1.0,
            query_state=query, monotonic=clock.monotonic, sleep=clock.sleep)
        self.assertGreaterEqual(samples[-1]["host_dwell_offset_ms"], 15000.0)
        self.assertTrue(any("bounce" in failure for failure in failures))

    def test_invalid_dwell_parameters_are_rejected(self) -> None:
        case = runner.MENU_CASES[0]
        for dwell, sample in ((0.0, 0.1), (1.0, 0.0)):
            with self.subTest(dwell=dwell, sample=sample):
                with self.assertRaises(ValueError):
                    runner.collect_stable_dwell(
                        object(), case, ui_state(case), dwell, sample)


class RetainedContractTests(unittest.TestCase):
    def test_complete_evidence_passes(self) -> None:
        self.assertEqual([], runner.result_contract_failures(passing_result()))

    def test_missing_menu_is_rejected(self) -> None:
        result = passing_result()
        result["menus"].pop(1)
        self.assertTrue(runner.result_contract_failures(result))

    def test_reordered_menu_is_rejected(self) -> None:
        result = passing_result()
        result["menus"][0], result["menus"][1] = (
            result["menus"][1], result["menus"][0])
        self.assertTrue(runner.result_contract_failures(result))

    def test_one_sample_false_pass_is_rejected(self) -> None:
        result = passing_result()
        result["menus"][1]["dwell_samples"] = [
            result["menus"][1]["dwell_samples"][0]]
        failures = runner.result_contract_failures(result)
        self.assertTrue(any("bounded dwell unproven" in failure
                            for failure in failures))

    def test_ble_retained_dwell_below_minimum_is_rejected(self) -> None:
        result = passing_result()
        result["menus"][1]["effective_dwell_seconds"] = 1.25
        result["menus"][1]["dwell_samples"][-1][
            "host_dwell_offset_ms"] = 1250.0
        failures = runner.result_contract_failures(result)
        self.assertTrue(any("effective dwell below case minimum" in failure
                            for failure in failures))

    def test_mutated_retained_dwell_is_revalidated(self) -> None:
        result = passing_result()
        result["menus"][1]["dwell_samples"][1].update({
            "page": "home", "runtime_owner": "none", "lease_mask": 0,
        })
        self.assertTrue(runner.result_contract_failures(result))

    def test_dirty_home_is_rejected(self) -> None:
        result = passing_result()
        result["menus"][3]["home_settled"]["lease_mask"] = 9
        self.assertTrue(runner.result_contract_failures(result))

    def test_incomplete_terminal_cleanup_is_rejected(self) -> None:
        result = passing_result()
        result["cleanup_after"]["complete"] = False
        self.assertTrue(runner.result_contract_failures(result))

    def test_unsafe_outputs_are_rejected(self) -> None:
        for field in ("buzzer_inactive", "nrf_ce_inactive",
                      "software_quiesce_complete"):
            with self.subTest(field=field):
                result = passing_result()
                result["safe_outputs"][field] = False
                self.assertTrue(runner.result_contract_failures(result))

    def test_active_hil_or_leaked_final_lease_is_rejected(self) -> None:
        result = passing_result()
        result["post_hil_end"]["hil"]["active"] = True
        self.assertTrue(runner.result_contract_failures(result))

    def test_unverified_candidate_or_unsafe_policy_is_rejected(self) -> None:
        result = passing_result()
        result["candidate"]["verified"] = False
        self.assertTrue(runner.result_contract_failures(result))
        result = passing_result()
        result["policy"]["nested_actions_selected"] = 1
        self.assertTrue(runner.result_contract_failures(result))

    def test_input_drop_or_boot_recovery_mutation_is_rejected(self) -> None:
        result = passing_result()
        result["input"]["queue_drops"] = 1
        self.assertTrue(runner.result_contract_failures(result))
        result = passing_result()
        result["recovery_after"]["generation"] = 13
        result["boot_recovery_continuity"] = False
        self.assertTrue(runner.result_contract_failures(result))

    def test_physical_write_counter_is_not_misrepresented_as_global_proof(self) -> None:
        result = passing_result()
        result["recovery_after"]["physical_write_calls"] = 7
        self.assertEqual([], runner.result_contract_failures(result))
        self.assertIs(False,
                      result["policy"]["product_storage_writes_measured"])

    def test_hil_session_boundaries_are_required(self) -> None:
        result = passing_result()
        result["hil_session"]["begin"]["active"] = False
        self.assertTrue(runner.result_contract_failures(result))
        result = passing_result()
        result["hil_session"]["end"]["active"] = True
        self.assertTrue(runner.result_contract_failures(result))
        result = passing_result()
        result["post_hil_end"]["ui"]["lease_mask"] = 15
        self.assertTrue(runner.result_contract_failures(result))

    def test_record_marked_failed_cannot_pass_contract(self) -> None:
        result = passing_result()
        result["menus"][2]["passed"] = False
        self.assertTrue(runner.result_contract_failures(result))

    def test_unproven_catalog_boundary_is_rejected(self) -> None:
        result = passing_result()
        result["catalog_boundary"]["changed"] = True
        result["catalog_boundary"]["selection"] = 8
        self.assertTrue(runner.result_contract_failures(result))


class StaticSafetyPolicyTests(unittest.TestCase):
    def test_catalog_covers_all_nine_current_home_entries(self) -> None:
        self.assertEqual(
            ["wifi", "ble", "spectrum24", "subghz", "capture",
             "targets", "library", "lab", "device"],
            [case.item_id for case in runner.MENU_CASES])
        self.assertEqual(list(range(9)),
                         [case.index for case in runner.MENU_CASES])

    def test_clone_and_cardputer_ports_are_not_admitted_by_policy(self) -> None:
        self.assertEqual("/dev/cu.usbmodem2101", runner.BOARD_PORT)
        self.assertNotEqual(runner.BOARD_PORT, runner.FORBIDDEN_FIXTURE_PORT)

    def test_policy_contains_no_nested_or_transmit_action(self) -> None:
        source = Path(runner.__file__).read_text(encoding="utf-8")
        self.assertNotIn('action(device, "select")', source)
        self.assertNotIn('ui.key select', source)
        self.assertNotIn('WiFi.begin', source)
        self.assertNotIn('BLEDevice', source)
        self.assertNotIn('subprocess', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
