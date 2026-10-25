"""The publish check's reading of build/qa/review.md."""

import tempfile
import unittest
from pathlib import Path

from studio.publish_check import review_approved


class ReviewVerdict(unittest.TestCase):
    def verdict(self, text: str) -> bool:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.md"
            path.write_text(text, encoding="utf-8")
            return review_approved(path)

    def test_the_later_verdict_wins(self):
        self.assertTrue(self.verdict("APPROVED"))
        self.assertFalse(self.verdict("REJECTED: the duck clips the frame"))
        self.assertTrue(self.verdict("First pass REJECTED: clipping.\nFixed the mix.\nAPPROVED"))
        self.assertFalse(self.verdict("APPROVED\n\nActually REJECTED: the loop jumps"))

    def test_a_word_that_only_contains_approved_is_not_an_approval(self):
        self.assertFalse(self.verdict("DISAPPROVED"))
        self.assertFalse(self.verdict("UNAPPROVED"))
        self.assertFalse(self.verdict("NOT APPROVED"))
        self.assertFalse(self.verdict("The picture is fine but this is not approved."))
        self.assertFalse(self.verdict("APPROVED at first glance.\nNOT APPROVED: the loop jumps."))
        self.assertTrue(self.verdict("NOT APPROVED on the first pass.\nFixed.\nAPPROVED"))

    def test_a_missing_review_is_not_approved(self):
        self.assertFalse(review_approved(Path("/no/such/review.md")))
