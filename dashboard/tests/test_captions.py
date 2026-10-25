"""Captions copied for a post (dashboard.videos): hashtags move to the tag list."""

import unittest

from dashboard import videos


class StripHashtags(unittest.TestCase):
    def test_tacked_on_tags_go_and_a_word_in_the_sentence_stays(self):
        self.assertEqual(videos.strip_hashtags("Gravity flipped? #fyp #whatif"), "Gravity flipped?")
        self.assertEqual(videos.strip_hashtags("What if #gravity doubled"), "What if gravity doubled")
        self.assertEqual(videos.strip_hashtags("What if gravity doubled #fyp"), "What if gravity doubled fyp")
        self.assertEqual(videos.strip_hashtags("Hello. #fyp"), "Hello.")
        self.assertEqual(videos.strip_hashtags("#fyp #whatif"), "")

    def test_glued_hashtags_leave_the_caption(self):
        self.assertEqual(videos.strip_hashtags("Hello #fyp#whatif"), "Hello")
        self.assertEqual(videos.strip_hashtags("See #fyp#whatif now"), "See now")
        self.assertNotIn("#", videos.strip_hashtags("See #fyp#whatif now"))

    def test_a_post_does_not_keep_a_broken_glued_tag_in_the_line(self):
        text = videos.post_text("tiktok", "Hello #fyp#whatif", "#physics")
        self.assertTrue(text.startswith("Hello #"))
        self.assertNotIn("fyp#", text)
        self.assertIn("#fyp", text)
        self.assertIn("#whatif", text)
