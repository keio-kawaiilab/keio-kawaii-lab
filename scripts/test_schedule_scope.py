import unittest

from apply_event_scopes import dedupe_birthday_schedule_shadows
from schedule_scope import EXTERNAL, HOSTED, infer_event_scope, special_event_category


class ScheduleScopeTests(unittest.TestCase):
    def test_official_special_title_category(self):
        self.assertEqual("large-benefit", special_event_category("発売記念リリースイベント 大特典会"))
        self.assertEqual("release-event", special_event_category("CD発売記念リリースイベント"))

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

    def test_stale_birthday_schedule_shadow_is_removed_when_fc_row_exists(self):
        fc = {
            "id": "fc",
            "group": "CANDY TUNE",
            "title": "2026年10月1日(木) CANDY TUNE 小川奈々子 生誕祭 2026 FC会員先行",
            "eventTitle": "CANDY TUNE 小川奈々子 生誕祭 2026",
            "eventCategory": "solo-live",
            "ticketType": "KAWAII LAB. FC先行",
            "applicationStatus": "open",
            "applyStart": "2026-08-26T12:00",
            "applyEnd": "2026-08-31T23:59",
            "eventDate": "2026-10-01",
            "venue": "SGCホール有明",
            "startTime": "19:00",
            "url": "https://kawaiilab.asobisystem.com/news/detail/88104",
            "sourceType": "auto",
        }
        stale = {
            "id": "old",
            "group": "CANDY TUNE",
            "title": "CANDY TUNE 小川奈々子 生誕祭 2026",
            "eventCategory": "solo-live",
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "eventDate": "2026-10-01",
            "venue": "SGCホール有明",
            "startTime": "19:00",
            "url": "https://candytune.asobisystem.com/news/detail/86518",
            "officialScheduleUrl": "https://candytune.asobisystem.com/live_information/detail/43376",
            "sourceType": "derived",
            "sourceStale": True,
            "releaseRetentionReason": "missing-from-current-refresh",
        }
        rows, removed = dedupe_birthday_schedule_shadows([fc, stale])
        self.assertEqual(1, removed)
        self.assertEqual(1, len(rows))
        self.assertEqual("fc", rows[0]["id"])
        self.assertIn(stale["url"], rows[0]["urls"])
        self.assertEqual(stale["officialScheduleUrl"], rows[0]["officialScheduleUrl"])

    def test_current_schedule_only_birthday_is_kept_without_richer_row(self):
        event = {
            "id": "birthday",
            "group": "CUTIE STREET",
            "title": "CUTIE STREET 梅田みゆ 生誕祭 2026",
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "eventDate": "2026-09-14",
            "venue": "SGCホール有明",
            "sourceType": "official-schedule",
        }
        rows, removed = dedupe_birthday_schedule_shadows([event])
        self.assertEqual(0, removed)
        self.assertEqual([event], rows)

    def test_distinct_birthday_ticket_rounds_are_not_collapsed(self):
        base = {
            "group": "SWEET STEADY",
            "eventTitle": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
            "eventDate": "2026-10-26",
            "venue": "SGCホール有明",
            "startTime": "19:00",
            "applicationStatus": "open",
        }
        fc = dict(base, id="fc", ticketType="FC先行", applyEnd="2026-09-01T23:59")
        general = dict(base, id="general", ticketType="一般発売", applyEnd="2026-10-25T23:59")
        rows, removed = dedupe_birthday_schedule_shadows([fc, general])
        self.assertEqual(0, removed)
        self.assertEqual({"fc", "general"}, {row["id"] for row in rows})


if __name__ == "__main__":
    unittest.main()
