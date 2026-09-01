#!/usr/bin/env python3
"""Host checks for the local-only companion Web preview."""

from __future__ import annotations

import unittest

import preview_companion_web as preview


class CompanionWebPreviewTests(unittest.TestCase):
    def test_embedded_assets_are_served_from_production_source(self) -> None:
        self.assertIn(b'<script src="/app.js">', preview.INDEX)
        self.assertIn(b"leshy.companion.request.v1", preview.APP)
        self.assertNotIn(b"http://", preview.INDEX + preview.APP)
        self.assertNotIn(b"https://", preview.INDEX + preview.APP)

    def test_demo_contract_covers_every_page_and_mutation(self) -> None:
        connect = preview.response({"kind": "connect", "request_id": "c"})
        self.assertEqual("ok", connect["status"])
        sessions = preview.response(
            {"kind": "session.list", "request_id": "s"})
        self.assertEqual(2, len(sessions["items"]))
        targets = preview.response(
            {"kind": "target.list", "request_id": "t"})
        self.assertEqual(2, len(targets["items"]))
        detail = preview.response({
            "kind": "target.detail", "request_id": "d",
            "target_id": targets["items"][0]["target_id"],
            "section": "identities",
        })
        self.assertTrue(detail["items"])
        compare = preview.response(
            {"kind": "target.compare", "request_id": "x"})
        self.assertEqual({"added", "changed"},
                         {item["class"] for item in compare["items"]})
        previewed = preview.response({
            "kind": "target.mutation.preview", "request_id": "m",
            "target_id": targets["items"][0]["target_id"],
        })
        self.assertEqual("preview-1", previewed["mutation_id"])
        saved = preview.response({
            "kind": "target.mutation.status", "request_id": "m",
        })
        self.assertEqual("saved", saved["state"])


if __name__ == "__main__":
    unittest.main()
