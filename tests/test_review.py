import json
from pathlib import Path
import unittest

from review import render_case


class CaseReviewTest(unittest.TestCase):
    def test_render_persisted_case_and_escape_caller_text(self):
        record = json.loads((Path(__file__).resolve().parents[1] / "demo/case.json").read_text())
        record["transcript"][0]["caller"] = "<script>unsafe()</script>"
        page = render_case(record)
        self.assertIn("North Star Coffee", page)
        self.assertIn("$6.75 USD", page)
        self.assertIn("May 15, 2026", page)
        self.assertIn("Awaiting review", page)
        self.assertIn(f'/cases/{record["case_id"]}"', page)
        self.assertIn("&lt;script&gt;unsafe()", page)
        self.assertNotIn("<script>", page)
