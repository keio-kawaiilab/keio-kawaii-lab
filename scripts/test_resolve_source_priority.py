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

    def test_distinct_pia_lots_are_never_collapsed(self):
        first = self.base(
            group="CANDY TUNE",
            title="CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            ticketType="プレリザーブ",
            eventDate="2026-11-24",
            eventDates=["2026-11-24", "2026-11-26"],
            sourceType="pia",
            url="https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=AAA",
        )
        second = dict(first)
        second["url"] = "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=BBB"
        out = r.resolve([first, second])
        self.assertEqual(len(out), 2)
        self.assertEqual({r.pia_lots(x)[0] for x in out}, {"AAA", "BBB"})

    def test_fc_and_pia_playguide_are_both_kept(self):
        official_fc = self.base(ticketType="FC先行")
        pia = self.base(
            ticketType="プレリザーブ",
            sourceType="pia",
            url="https://t.pia.jp/pia/event/event.do?eventCd=example",
        )
        out = r.resolve([official_fc, pia])
        self.assertEqual(len(out), 2)

    def test_official_beats_pia_for_same_fc_sale(self):
        official_fc = self.base(
            ticketType="FC先行",
            applyStart="2026-08-01T12:00",
            applyEnd="2026-08-10T23:59",
        )
        pia_fc = self.base(
            ticketType="FC先行",
            sourceType="pia",
            url="https://t.pia.jp/pia/event/event.do?eventCd=example",
            applyStart="2026-08-02T12:00",
            applyEnd="2026-08-10T23:59",
        )
        out = r.resolve([pia_fc, official_fc])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["primarySource"], "official")
        self.assertEqual(out[0]["applyStart"], "2026-08-01T12:00")

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
            url="https://sukisuki-shop.com/goods/6500000004000",
            applyEnd="2026-08-23T23:59",
        )
        out = r.resolve([official, suki])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["primarySource"], "sukisuki")
        self.assertEqual(out[0]["applyEnd"], "2026-08-23T23:59")

    def test_sukisuki_lottery_and_late_first_come_are_both_kept(self):
        lottery = self.base(
            group="CANDY TUNE",
            title="CANDY TUNE オンライン特典会",
            ticketType="オンライン特典会・抽選販売",
            eventDate="2026-08-24",
            eventCategory="online-benefit",
            sourceType="sukisuki",
            url="https://sukisuki-shop.com/goods/6500000004000",
            applyStart="2026-08-20T18:00",
            applyEnd="2026-08-22T23:59",
        )
        first_come = dict(lottery)
        first_come.update({
            "ticketType": "オンライン特典会・先着販売",
            "url": "https://sukisuki-shop.com/goods/6500000004999",
            "applyStart": "2026-08-24T12:00",
            "applyEnd": "2026-08-24T17:00",
        })
        out = r.resolve([lottery, first_come])
        self.assertEqual(len(out), 2)
        self.assertEqual({x["ticketType"] for x in out}, {
            "オンライン特典会・抽選販売",
            "オンライン特典会・先着販売",
        })

    def test_distinct_sukisuki_goods_pages_are_never_collapsed(self):
        first = self.base(
            group="SWEET STEADY",
            title="SWEET STEADY オンライン特典会",
            ticketType="オンライン特典会・先着販売",
            eventDate="2026-08-24",
            eventCategory="online-benefit",
            sourceType="sukisuki",
            url="https://sukisuki-shop.com/goods/6500000005001",
        )
        second = dict(first)
        second["url"] = "https://sukisuki-shop.com/goods/6500000005002"
        out = r.resolve([first, second])
        self.assertEqual(len(out), 2)
        self.assertEqual({r.sukisuki_goods(x)[0] for x in out}, {"6500000005001", "6500000005002"})

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
