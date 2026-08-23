import unittest

import resolve_source_priority as r


class SourcePriorityTests(unittest.TestCase):
    def base(self, **overrides):
        event = {
            "group": "CUTIE STREET",
            "title": "CUTIE STREET 梅田みゆ 生誕祭 2026",
            "ticketType": "一般発売",
            "eventDate": "2026-09-14",
            "venue": "SGCホール有明",
            "url": "https://cutiestreet.asobisystem.com/news/detail/example",
            "sourceType": "auto",
        }
        event.update(overrides)
        return event

    def test_pia_beats_official_for_same_general_sale(self):
        official = self.base(applyStart="2026-08-20T10:00", applyEnd="2026-09-13T23:59")
        pia = self.base(
            sourceType="pia",
            url="https://t.pia.jp/pia/event/event.do?eventCd=example",
            applyStart="2026-08-22T10:00",
            applyEnd="2026-09-13T23:59",
        )
        out = r.resolve([official, pia])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["primarySource"], "pia")
        self.assertEqual(out[0]["applyStart"], "2026-08-22T10:00")
        self.assertEqual(len(out[0]["urls"]), 2)

    def test_fc_and_pia_playguide_are_both_kept(self):
        official_fc = self.base(ticketType="FC先行")
        pia = self.base(
            ticketType="プレリザーブ",
            sourceType="pia",
            url="https://t.pia.jp/pia/event/event.do?eventCd=example",
        )
        out = r.resolve([official_fc, pia])
        self.assertEqual(len(out), 2)

    def test_upgrade_and_pia_general_are_both_kept(self):
        official_upgrade = self.base(ticketType="アップグレード抽選")
        pia = self.base(
            ticketType="一般発売",
            sourceType="pia",
            url="https://t.pia.jp/pia/event/event.do?eventCd=example",
        )
        out = r.resolve([official_upgrade, pia])
        self.assertEqual(len(out), 2)

    def test_sukisuki_beats_official_for_online_benefit(self):
        official = self.base(
            group="CANDY TUNE",
            title="CANDY TUNE オンライン特典会",
            ticketType="オンライン特典会",
            eventDate="2026-08-24",
            eventCategory="online-benefit",
        )
        suki = self.base(
            group="CANDY TUNE",
            title="CANDY TUNE オンライン特典会",
            ticketType="オンライン特典会・抽選販売",
            eventDate="2026-08-24",
            eventCategory="online-benefit",
            sourceType="sukisuki",
            url="https://sukisuki-shop.com/goods/example",
            applyEnd="2026-08-23T23:59",
        )
        out = r.resolve([official, suki])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["primarySource"], "sukisuki")
        self.assertEqual(out[0]["applyEnd"], "2026-08-23T23:59")

    def test_pia_subset_is_not_merged_into_whole_tour(self):
        official = self.base(
            title="CUTIE STREET JAPAN ARENA TOUR 2026 -AUTUMN-",
            ticketType="プレイガイド先行",
            eventDate="2026-09-23",
            eventDates=["2026-09-23", "2026-09-29", "2026-09-30"],
            schedule=[
                {"date": "2026-09-23", "venue": "横浜アリーナ"},
                {"date": "2026-09-29", "venue": "有明アリーナ"},
                {"date": "2026-09-30", "venue": "有明アリーナ"},
            ],
        )
        pia_subset = self.base(
            title="CUTIE STREET JAPAN ARENA TOUR 2026 -AUTUMN-",
            ticketType="プレリザーブ",
            sourceType="pia",
            eventDate="2026-09-29",
            eventDates=["2026-09-29", "2026-09-30"],
            schedule=[
                {"date": "2026-09-29", "venue": "有明アリーナ"},
                {"date": "2026-09-30", "venue": "有明アリーナ"},
            ],
            url="https://t.pia.jp/pia/event/event.do?eventCd=example",
        )
        out = r.resolve([official, pia_subset])
        self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
