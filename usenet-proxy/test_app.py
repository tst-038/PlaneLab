import unittest
from urllib.parse import parse_qs

from app import rewrite_query


class RewriteQueryTests(unittest.TestCase):
    def test_rewrites_episode_tvsearch(self):
        query, changed = rewrite_query(
            "t=tvsearch&q=Example+Show&season=12&ep=8&cat=5000%2C5020&apikey=secret"
        )
        values = parse_qs(query)

        self.assertTrue(changed)
        self.assertEqual(values["t"], ["search"])
        self.assertEqual(values["q"], ["Example Show"])
        self.assertEqual(values["apikey"], ["secret"])
        self.assertNotIn("cat", values)
        self.assertNotIn("season", values)
        self.assertNotIn("ep", values)

    def test_rewrites_season_tvsearch(self):
        query, changed = rewrite_query(
            "t=tvsearch&q=Example+Show&season=3&cat=5000"
        )

        self.assertTrue(changed)
        self.assertEqual(parse_qs(query)["q"], ["Example Show"])

    def test_leaves_caps_and_downloads_untouched(self):
        for query in ("t=caps&apikey=secret", "t=get&id=123&apikey=secret"):
            rewritten, changed = rewrite_query(query)
            self.assertFalse(changed)
            self.assertEqual(rewritten, query)

    def test_does_not_rewrite_id_only_search(self):
        query = "t=tvsearch&tvdbid=123&season=1"
        rewritten, changed = rewrite_query(query)
        self.assertFalse(changed)
        self.assertEqual(rewritten, query)


if __name__ == "__main__":
    unittest.main()
