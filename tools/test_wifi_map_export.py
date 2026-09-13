#!/usr/bin/env python3
"""Small host-only regression for the documentation exporter."""

import html
import unittest

from export_wifi_map import END, START, SRCDOC, updated_export


def fragment(body: str) -> str:
    return START + "\n" + body + "\n" + END


def wrapper(source: str) -> str:
    return '<iframe sandbox="allow-scripts" srcdoc="' + html.escape(
        "<html><body>" + source + "</body></html>", quote=True
    ) + '"></iframe>'


class ExportTests(unittest.TestCase):
    def test_roundtrip_and_idempotence(self):
        source = fragment('<div title="a & b">Скрытая сеть &lt;x&gt;</div>')
        result = updated_export(source, wrapper(fragment("old")))
        self.assertIn(source, html.unescape(SRCDOC.search(result)[1]))
        self.assertEqual(updated_export(source, result), result)
        self.assertTrue(result.startswith('<iframe sandbox="allow-scripts"'))

    def test_trailing_newline_is_stable(self):
        source = fragment("test")
        self.assertEqual(updated_export(source + "\n", wrapper(source)), wrapper(source))

    def test_missing_duplicate_reversed_or_outside_markers(self):
        for source in ("plain", START + START + END, END + START, fragment("x") + "extra"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                updated_export(source, wrapper(fragment("old")))

    def test_invalid_wrapper_fails_closed(self):
        source = fragment("test")
        for exported in ("plain", wrapper(source) * 2, wrapper("unmarked")):
            with self.subTest(exported=exported), self.assertRaises(ValueError):
                updated_export(source, exported)

    def test_budget_counts_utf8_bytes(self):
        with self.assertRaises(ValueError):
            updated_export(fragment("я" * 500_000), wrapper(fragment("old")))


if __name__ == "__main__":
    unittest.main()
