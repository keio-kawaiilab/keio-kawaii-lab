import unittest

from schedule_scope import EXTERNAL, HOSTED, infer_event_scope


class ScheduleScopeTests(unittest.TestCase):
    def test_hosted_events(self):
        for title in (
            "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            "CUTIE STREET 梅田みゆ 生誕祭 2026",
            "KAWAII LAB. Christmas SESSION 2026",
            "KAWAII LAB. COLLECTION produced by TGC",
            "5thシングルCD発売記念イベント 大特典会",
        ):
            self.assertEqual(HOSTED, infer_event_scope({"title": title}), title)

    def test_external_appearances(self):
        for title in (
            "ROCK IN JAPAN FESTIVAL 2026",
            "第43回 マイナビ 東京ガールズコレクション 2026",
            "第4回 IDOL RUNWAY COLLECTION 2026",
            "HIROSHIMA CONTI-NeW FeS 2026",
        ):
            self.assertEqual(EXTERNAL, infer_event_scope({"title": title}), title)

    def test_unknown_is_fail_closed_external(self):
        self.assertEqual(EXTERNAL, infer_event_scope({"title": "VERSE BY VERSE #1"}))

    def test_group_named_live_is_hosted(self):
        self.assertEqual(HOSTED, infer_event_scope({"group": "CUTIE STREET", "title": "CUTIE STREET Live in Korea 2027 WINTER"}))

    def test_explicit_scope_wins(self):
        self.assertEqual(HOSTED, infer_event_scope({"title": "FEST", "eventScope": HOSTED}))


if __name__ == "__main__":
    unittest.main()
