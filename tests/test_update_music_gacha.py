"""Offline regression tests: no network access or YouTube credentials required."""
import copy
import unittest
from scripts.update_music_gacha import build_updates, parse_mv_title


class ParseMVTitle(unittest.TestCase):
    def test_official_video_formats(self):
        cases = [
            ("【MV】FRUITS ZIPPER『新曲！』", "FRUITS ZIPPER", ("FRUITS ZIPPER", "新曲！")),
            ("【MV】SWEET STEADY『SWEET STEP』", "KAWAII LAB.", ("SWEET STEADY", "SWEET STEP")),
            ("【MV】MORE STAR『WITH KAWAII論』", "MORE STAR", ("MORE STAR", "WITH KAWAII論")),
            ("【MV】CUTIE STREET『でぃすこみゅーたんと！』", "CUTIE STREET", ("CUTIE STREET", "でぃすこみゅーたんと！")),
            ("【MV】KAWAII LAB.『CHU CHU CHU研究中！』", "KAWAII LAB.", ("TEAM KAWAII LAB.", "CHU CHU CHU研究中！")),
            ("CANDY TUNE - アイドル (Official Music Video)", "CANDY TUNE", ("CANDY TUNE", "アイドル")),
        ]
        for title, channel, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(parse_mv_title(title, channel), expected)

    def test_excluded_clips_and_unidentifiable_group(self):
        cases = [
            ("【MV】FRUITS ZIPPER『新曲』メイキング", "FRUITS ZIPPER"),
            ("【MV】CUTIE STREET『新曲』Dance Practice", "CUTIE STREET"),
            ("【MV】CUTIE STREET『新曲』Teaser", "CUTIE STREET"),
            ("【MV】CUTIE STREET『新曲』Live ver.", "CUTIE STREET"),
            ("【MV】CUTIE STREET『新曲』Korean ver.", "CUTIE STREET"),
            ("CUTIE STREET 新曲のみ公開", "CUTIE STREET"),
            ("【MV】FRUITS ZIPPER『新曲』", "CUTIE STREET"),
            ("【MV】『新曲』", "KAWAII LAB."),
            ("【MV】CANDY TUNE × MORE STAR『合同曲』", "KAWAII LAB."),
        ]
        for title, channel in cases:
            with self.subTest(title=title):
                self.assertIsNone(parse_mv_title(title, channel))


class CatalogUpdate(unittest.TestCase):
    def setUp(self):
        self.data = {
            "metadata": {"count": 1, "countsByGroup": {"FRUITS ZIPPER": 1}},
            "songs": [{"id": "kwl-mv-074", "group": "FRUITS ZIPPER",
                       "title": "旧曲", "youtubeId": "aA1-2345_67", "videoType": "MV"}],
        }

    def test_deduplication_and_counter(self):
        videos = {"FRUITS ZIPPER": [
            {"id": "aA1-2345_67", "title": "【MV】FRUITS ZIPPER『旧曲』"},
            {"id": "bB1-2345_67", "title": "【MV】FRUITS ZIPPER『旧 曲』"},
            {"id": "cC1-2345_67", "title": "【MV】FRUITS ZIPPER『新曲』"},
            {"id": "dD1-2345_67", "title": "【MV】FRUITS ZIPPER『新曲』"},
        ]}
        result, added, ignored = build_updates(copy.deepcopy(self.data), videos)
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["id"], "kwl-mv-075")
        self.assertEqual(result["metadata"]["count"], 2)
        self.assertEqual(result["metadata"]["countsByGroup"]["FRUITS ZIPPER"], 2)
        self.assertEqual(ignored, [])

    def test_no_update_does_not_rewrite_json(self):
        old = copy.deepcopy(self.data)
        result, added, ignored = build_updates(copy.deepcopy(old), {})
        self.assertEqual(result, old)
        self.assertEqual(added, [])
        self.assertEqual(ignored, [])

    def test_ambiguous_mv_is_review_only(self):
        videos = {"MORE STAR": [{"id": "eE1-2345_67", "title": "【MV】謎の新作"}]}
        result, added, ignored = build_updates(copy.deepcopy(self.data), videos)
        self.assertEqual(len(added), 0)
        self.assertEqual(len(ignored), 1)
        self.assertEqual(result["metadata"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
