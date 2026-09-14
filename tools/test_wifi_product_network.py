#!/usr/bin/env python3
"""Host regressions for ordinary-product two-board verification."""
import unittest
import json
import struct
import tempfile
from pathlib import Path
from unittest.mock import patch
from check_wifi_test_network_contract import ROOT, check
import run_wifi_product_network_hil as runner

class ProductNetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = ROOT / "firmware/leshy1/src/platform/arduino"
        cls.adapter = (base / "BoardWifiTestNetwork.cpp").read_text()
        cls.entry = (base / "ArduinoEntry.cpp").read_text()
    def test_normal_contract(self):
        self.assertEqual(check(self.adapter, self.entry), [])
    def test_unapproved_wifi_rejected(self):
        for change in (self.adapter + "\nvoid bad(){ esp_wifi_connect(); }",
                       self.adapter.replace("init.nvs_enable = 0", "init.nvs_enable = 1"),
                       self.adapter.replace("LESHY-TEST-%02X%02X", "some-other-network"),
                       self.adapter + "\nvoid bad(){ esp_netif_init(); }"):
            with self.subTest(change=change[-30:]): self.assertTrue(check(change, self.entry))
    def test_missing_guard_rejected(self):
        for marker in ("safetySupervisor.armed()", "resourceBroker.acquire",
                       "wifiTestNetwork.due(millis())", "digitalRead(0) == LOW",
                       "wifiTestTextCache.changed"):
            with self.subTest(marker=marker):
                self.assertTrue(check(self.adapter, self.entry.replace(marker, "removed")))
    def test_exact_board(self):
        with patch.object(runner, "serial_metadata", return_value={"serial_number":"11:22:33:44:55:66"}):
            runner.exact_port("/dev/example", "112233445566")
            with self.assertRaises(RuntimeError): runner.exact_port("/dev/example", "000000000000")
    def test_pixel_oracle(self):
        before = bytes(240 * 320 * 2)
        after = bytearray(before)
        after[(240 * 241 + 15) * 2] = 1
        self.assertEqual(runner.countdown_diff(before, after),
                         {"dynamic_pixels":1, "static_pixels":0})
        after[0] = 1
        self.assertEqual(runner.countdown_diff(before, after)["static_pixels"], 1)
        with self.assertRaises(RuntimeError): runner.countdown_diff(b"", b"")
    def test_bssid_hash(self):
        self.assertEqual(runner.bssid_hash("000000000000"), 2138539933)
    def test_timed_capture_never_retries_into_another_scene(self):
        source = Path(runner.__file__).read_text()
        self.assertIn("capture(device, frames, name, maximum_attempts=1)", source)
    def test_credential_not_logged_or_cached(self):
        for entry in (
            self.entry.replace("wifiTestTextCache.publish(4, credentialState",
                               "wifiTestTextCache.publish(4, credential"),
            self.entry.replace("secret[i] = 0", "secret[i] = 1"),
            self.entry.replace("void emitWifiTestNetworkState(Stream& reply) {",
                "void emitWifiTestNetworkState(Stream& reply) { reply.println(boardWifiTestNetwork.displayPassword());"),
        ):
            with self.subTest(): self.assertTrue(check(self.adapter, entry))
    def test_console_blocker_requires_actual_failure_shape(self):
        from retain_wifi_product_boot_blocker import retain_console_timeout
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            image = bytearray(288); image[0] = 0xe9
            struct.pack_into('<I', image, 32, 0xabcd5432)
            image[176:208] = bytes([1])*32
            (folder/'firmware.bin').write_bytes(image)
            deploy = folder/'deploy.log'
            deploy.write_text('Wrote 288 bytes\nHash of data verified.\n'
                'TimeoutError: timed out synchronizing the firmware console\n')
            for filename in ('source-one-reset.log','source-post-deploy-probe.log'):
                (folder/filename).write_bytes(b'')
            def record(filename, value):
                (folder/filename).write_text(json.dumps(value, separators=(',',':'))+'\n')
            record('receiver-post-deploy-probe.log', dict(schema='leshy.ui.v1',
                page='home', lease_mask=0, safety_latched=False))
            record('source-boot.log', dict(schema='leshy.storage.product_boot_retry.v1',
                cleanup_complete=True, blocked_write_attempts=0, completed_attempts=1))
            result = retain_console_timeout(folder, deploy)
            self.assertFalse(result['application_runtime_verified'])
            self.assertFalse(result['two_board_acceptance'])
            self.assertEqual(result['observed_sd_retry_attempts'], [1])
            (folder/'source-one-reset.log').write_bytes(b'new evidence')
            with self.assertRaises(ValueError): retain_console_timeout(folder, deploy)
            (folder/'source-one-reset.log').write_bytes(b'')
            deploy.write_text('write never completed')
            with self.assertRaises(ValueError): retain_console_timeout(folder, deploy)

if __name__ == "__main__": unittest.main()
