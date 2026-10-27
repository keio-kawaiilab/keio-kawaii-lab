import unittest
from datetime import date

import update_official_birthday_news as news
import update_official_x_birthday_events as birthday


class OfficialBirthdayNewsTests(unittest.TestCase):
    def test_upgrade_notice_is_left_to_continuous_official_collector(self):
        payload = {"events": [{
            "id": "schedule-placeholder",
            "group": "CUTIE STREET",
            "title": "CUTIE STREET 佐野愛花 生誕祭 2026",
            "eventDate": "2026-11-26",
            "openTime": "17:30",
            "startTime": "17:30",
            "ticketType": "現在受付なし",
            "sourceType": "official-schedule",
        }]}
        text = (
            "CUTIE STREET 佐野愛花 生誕祭 2026 アップグレード抽選受付\n"
            "年会費コース会員対象\n"
            "受付期間：2026年10月26日 12:00〜2026年10月29日 23:59\n"
        )
        rows = news.article_events(
            payload,
            "CUTIE STREET",
            "https://cutiestreet.asobisystem.com/news/detail/93573",
            text,
            date(2026, 10, 26),
        )
        self.assertEqual(rows, [])

    def test_event_announcement_with_later_upgrade_notes_is_collected(self):
        article_url = "https://sweetsteady.asobisystem.com/news/detail/94087"
        text = (
            "2027年1月7日(木) SWEET STEADY 奥田彩友 BIRTHDAY LIVE 2027 開催決定！FC先行受付開始！\n"
            "日程：2027年1月7日(木)\n"
            "会場：SGCホール有明\n"
            "時間：開場17:30 / 開演19:00\n"
            "＜アップグレードにつきまして＞\n"
            "後日、座席のアップグレードを実施いたします。\n"
            "SWEET STEADY OFFICIAL FANCLUB 有料会員先行受付\n"
            "受付期間：2026年10月27日 20:00〜2026年11月4日 23:59\n"
        )
        rows = news.article_events(
            {"events": []},
            "SWEET STEADY",
            article_url,
            text,
            date(2026, 10, 27),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["eventDate"], "2027-01-07")
        self.assertEqual(rows[0]["openTime"], "17:30")
        self.assertEqual(rows[0]["startTime"], "19:00")
        self.assertEqual(rows[0]["applyStart"], "2026-10-27T20:00")
        self.assertEqual(rows[0]["applyEnd"], "2026-11-04T23:59")
        self.assertEqual(rows[0]["applicationWindowSource"], article_url)
        self.assertEqual(rows[0]["deadlineSource"], article_url)
        self.assertEqual(rows[0]["url"], article_url)

    def test_official_article_times_enrich_existing_schedule_placeholder(self):
        article_url = "https://sweetsteady.asobisystem.com/news/detail/94087"
        payload = {"events": [{
            "id": "okuda-stable",
            "group": "SWEET STEADY",
            "title": "SWEET STEADY 奥田彩友 BIRTHDAY LIVE 2027",
            "eventTitle": "SWEET STEADY 奥田彩友 BIRTHDAY LIVE 2027",
            "eventDate": "2027-01-07",
            "venue": "SGCホール有明",
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "applyStart": None,
            "applyEnd": None,
            "sourceType": "official-schedule",
            "primarySource": "official",
        }]}
        text = (
            "2027年1月7日(木) SWEET STEADY 奥田彩友 BIRTHDAY LIVE 2027\n"
            "時間：開場17:30 / 開演19:00\n"
            "会場：SGCホール有明\n"
            "SWEET STEADY OFFICIAL FANCLUB会員先行\n"
            "受付期間：2026年10月27日 20:00〜2026年11月4日 23:59\n"
        )

        rows = news.article_events(
            payload, "SWEET STEADY", article_url, text, date(2026, 10, 27)
        )
        self.assertEqual(rows[0]["openTime"], "17:30")
        self.assertEqual(rows[0]["startTime"], "19:00")

        merged = birthday.merge_birthday_events(payload, rows)
        event = next(row for row in merged["events"] if row.get("id") == "okuda-stable")
        self.assertEqual(event["openTime"], "17:30")
        self.assertEqual(event["startTime"], "19:00")
        self.assertEqual(event["applyStart"], "2026-10-27T20:00")
        self.assertEqual(event["applyEnd"], "2026-11-04T23:59")

        # Reproduce the persisted state from the earlier collector version:
        # the reception is already present, but OPEN/START are still missing.
        event.pop("openTime")
        event.pop("startTime")
        retry_payload = {"events": [event]}
        retry_rows = news.article_events(
            retry_payload, "SWEET STEADY", article_url, text, date(2026, 10, 27)
        )
        retried = birthday.merge_birthday_events(retry_payload, retry_rows)
        self.assertEqual(len(retried["events"]), 1)
        self.assertEqual(retried["events"][0]["id"], "okuda-stable")
        self.assertEqual(retried["events"][0]["openTime"], "17:30")
        self.assertEqual(retried["events"][0]["startTime"], "19:00")

    def test_shoji_official_news_enriches_promoter_row_in_place(self):
        payload = {"events": [{
            "id": "shoji-stable",
            "group": "SWEET STEADY",
            "title": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
            "eventTitle": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
            "eventCategory": "solo-live",
            "eventDate": "2026-10-26",
            "venue": "SGC HALL ARIAKE",
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "applyStart": None,
            "applyEnd": None,
            "url": "https://red-hot.ne.jp/play/detail.php?pid=example",
            "urls": ["https://red-hot.ne.jp/play/detail.php?pid=example"],
            "sourceType": "promoter",
            "primarySource": "official",
            "sourceCandidates": ["promoter"],
        }]}
        article_url = "https://sweetsteady.asobisystem.com/news/detail/99999"
        text = (
            "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026\n"
            "FC先行受付\n"
            "受付期間：2026年8月31日 19:00〜2026年9月8日 23:59\n"
        )
        rows = news.article_events(payload, "SWEET STEADY", article_url, text, date(2026, 9, 1))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "shoji-stable")
        self.assertEqual(rows[0]["eventDate"], "2026-10-26")
        self.assertEqual(rows[0]["applyEnd"], "2026-09-08T23:59")
        self.assertEqual(rows[0]["url"], article_url)

        merged = birthday.merge_birthday_events(payload, rows)
        shoji = [e for e in merged["events"] if e.get("id") == "shoji-stable"]
        self.assertEqual(len(shoji), 1)
        self.assertNotEqual(shoji[0]["ticketType"], "現在受付なし")
        self.assertEqual(shoji[0]["applicationStatus"], "open")
        self.assertEqual(shoji[0]["eventDate"], "2026-10-26")
        self.assertEqual(shoji[0]["url"], article_url)
        self.assertEqual(shoji[0]["applyEnd"], "2026-09-08T23:59")

    def test_cutie_three_people_keep_current_2026_schedule_dates_and_deadlines(self):
        people = [
            ("furusawa", "古澤里紗", "2026-11-09", "2026-09-09T23:59"),
            ("itakura", "板倉可奈", "2026-11-11", "2026-09-09T23:59"),
            ("sano", "佐野愛花", "2026-11-26", "2026-09-10T23:59"),
        ]
        payload = {"events": [
            {
                "id": event_id,
                "group": "CUTIE STREET",
                "title": f"CUTIE STREET {person} 生誕祭 2026",
                "eventTitle": f"CUTIE STREET {person} 生誕祭 2026",
                "eventCategory": "solo-live",
                "eventDate": event_date,
                "ticketType": "現在受付なし",
                "applicationStatus": "none",
                "applyStart": None,
                "applyEnd": None,
                "url": f"https://red-hot.ne.jp/play/detail.php?pid={event_id}",
                "sourceType": "promoter",
                "primarySource": "official",
                "sourceCandidates": ["promoter"],
            }
            for event_id, person, event_date, _deadline in people
        ]}

        for event_id, person, event_date, deadline in people:
            article_url = f"https://cutiestreet.asobisystem.com/news/detail/{event_id}"
            text = (
                f"CUTIE STREET {person} 生誕祭 2026\n"
                "CUTIE STREET FC会員年会費コース限定先行受付\n"
                f"受付期間：2026年8月31日 20:00〜{deadline[:4]}年{int(deadline[5:7])}月{int(deadline[8:10])}日 23:59\n"
            )
            rows = news.article_events(payload, "CUTIE STREET", article_url, text, date(2026, 9, 1))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["id"], event_id)
            self.assertEqual(rows[0]["eventDate"], event_date)
            self.assertEqual(rows[0]["url"], article_url)
            self.assertEqual(rows[0]["applyEnd"], deadline)
            self.assertEqual(rows[0]["applicationStatus"], "open")

            merged = birthday.merge_birthday_events(payload, rows)
            by_id = {event["id"]: event for event in merged["events"]}
            self.assertEqual(by_id[event_id]["eventDate"], event_date)
            self.assertNotEqual(by_id[event_id]["ticketType"], "現在受付なし")
            self.assertEqual(by_id[event_id]["applicationStatus"], "open")
            self.assertEqual(by_id[event_id]["url"], article_url)
            self.assertEqual(by_id[event_id]["applyEnd"], deadline)


    def test_listing_title_wins_over_stale_body_year_for_same_birthday_day(self):
        article_url = "https://sweetsteady.asobisystem.com/news/detail/94087"
        listing_title = (
            "2027年1月7日(木)「SWEET STEADY 奥田彩友 BIRTHDAY LIVE 2027」"
            "開催決定！SWEET STEADY OFFICIAL FANCLUB会員先行開始！"
        )
        text = (
            f"{listing_title}\n"
            "日程：2026年1月7日(木) 時間：開場17:30 / 開演19:00\n"
            "会場：SGCホール有明\n"
            "SWEET STEADY OFFICIAL FANCLUB会員先行\n"
            "受付期間：2026年10月27日 20:00〜2026年11月4日 23:59\n"
        )

        canonical = news.canonical_birthday_event_text(listing_title, text)
        self.assertNotIn("日程：2026年1月7日", canonical)
        self.assertIn("日程：2027年1月7日", canonical)
        self.assertIn("開場17:30 / 開演19:00", canonical)
        self.assertIn("受付期間：2026年10月27日", canonical)

        rows = news.article_events(
            {"events": []},
            "SWEET STEADY",
            article_url,
            canonical,
            date(2026, 10, 27),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["eventDate"], "2027-01-07")
        self.assertEqual(rows[0]["openTime"], "17:30")
        self.assertEqual(rows[0]["startTime"], "19:00")
        self.assertEqual(rows[0]["applyStart"], "2026-10-27T20:00")
        self.assertEqual(rows[0]["applyEnd"], "2026-11-04T23:59")
        self.assertEqual(rows[0]["url"], article_url)


    def test_multiple_page_ranges_use_the_unique_scoped_fc_reception(self):
        article_url = "https://sweetsteady.asobisystem.com/news/detail/94087"
        text = (
            "2026.10.27\n"
            "2027年1月7日(木) SWEET STEADY 奥田彩友 BIRTHDAY LIVE 2027\n"
            "SWEET STEADY OFFICIAL FANCLUB会員先行\n"
            "受付期間\n"
            "2026年10月27日 20:00〜2026年11月4日 23:59\n"
            "関連公演\n"
            "2027年1月30日 17:00〜2027年1月31日 16:00\n"
        )
        details = news.ticket_details_from_official_article(
            text, article_url, date(2026, 10, 27)
        )
        self.assertEqual(details["ticketType"], "FC先行")
        self.assertEqual(details["applyStart"], "2026-10-27T20:00")
        self.assertEqual(details["applyEnd"], "2026-11-04T23:59")
        self.assertTrue(details["applicationWindowVerified"])
        self.assertEqual(details["applicationWindowSource"], article_url)


if __name__ == "__main__":
    unittest.main()
