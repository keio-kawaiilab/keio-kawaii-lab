import unittest
from datetime import date
from unittest.mock import patch

import requests

import update_live_events_v2 as v2


class OfficialHeadlineDiscoveryTests(unittest.TestCase):
    def test_old_live_notice_without_ticket_keyword_is_not_skipped(self):
        base = "https://fruitszipper.asobisystem.com"
        def fake_fetch(url, headers):
            if "page=3" in url:
                return (
                    '<a href="/news/detail/500">FRUITS ZIPPER 単独ライブ開催決定</a>'
                    '<a href="/news/detail/501">新衣装の写真を公開</a>'
                )
            return "<html></html>"

        v2.FEED_FAILURES.clear()
        with patch.object(v2, "_fetch_news_page", side_effect=fake_fetch):
            found = v2.deep_candidate_links(requests.Session(), "FRUITS ZIPPER", base)
        self.assertEqual(["https://fruitszipper.asobisystem.com/news/detail/500"], [row.url for row in found])

    def test_image_only_official_notice_uses_image_alt(self):
        base = "https://morestar.asobisystem.com"
        def fake_fetch(url, headers):
            if "page=3" in url:
                return '<a href="/news/detail/600"><img alt="MORE STAR LIVE 開催決定" src="/notice.png"></a>'
            return "<html></html>"

        v2.FEED_FAILURES.clear()
        with patch.object(v2, "_fetch_news_page", side_effect=fake_fetch):
            found = v2.deep_candidate_links(requests.Session(), "MORE STAR", base)
        self.assertEqual(["https://morestar.asobisystem.com/news/detail/600"], [row.url for row in found])


class RetentionPolicyTests(unittest.TestCase):
    def test_archived_fresh_reception_does_not_erase_future_performance(self):
        row = {"id": "same", "sourceType": "auto", "group": "MORE STAR", "title": "MORE STAR LIVE", "eventDate": "2099-10-01", "applyEnd": "2099-08-01T23:59", "url": "https://morestar.asobisystem.com/news/detail/1"}
        result = v2.build_payload({"events": [row]}, {"same": dict(row)}, [], [], date(2099, 9, 1))
        self.assertEqual([event["id"] for event in result["events"]], ["same"])

    def test_future_show_survives_old_application_deadline(self):
        event = {
            "eventDate": "2026-12-12",
            "applyEnd": "2026-08-30T23:59",
        }
        self.assertTrue(v2.should_show(event, date(2026, 11, 30)))

    def test_show_is_visible_on_the_day_and_hidden_after(self):
        event = {"eventDate": "2026-08-31"}
        self.assertTrue(v2.should_show(event, date(2026, 8, 31)))
        self.assertFalse(v2.should_show(event, date(2026, 9, 1)))

    def test_consecutive_event_uses_final_date(self):
        event = {
            "eventDate": "2026-12-12",
            "eventEndDate": "2026-12-13",
        }
        self.assertTrue(v2.should_show(event, date(2026, 12, 13)))
        self.assertFalse(v2.should_show(event, date(2026, 12, 14)))

    def test_old_article_future_event_is_retained(self):
        existing = {
            "events": [{
                "id": "old-future",
                "sourceType": "auto",
                "eventDate": "2027-05-01",
                "applyEnd": "2026-08-01T23:59",
                "url": "https://example.test/old",
            }]
        }
        payload = v2.build_payload(existing, {}, [], [], date(2026, 8, 23))
        self.assertEqual([e["id"] for e in payload["events"]], ["old-future"])

    def test_past_existing_event_is_removed(self):
        existing = {
            "events": [{
                "id": "past",
                "sourceType": "auto",
                "eventDate": "2026-08-22",
                "url": "https://example.test/past",
            }]
        }
        payload = v2.build_payload(existing, {}, [], [], date(2026, 8, 23))
        self.assertEqual(payload["events"], [])

    def test_reparsed_article_replaces_old_row_when_time_enrichment_changes_id(self):
        source = "https://example.test/news/detail/1"
        old = {
            "id": "old-id", "sourceType": "auto", "group": "FRUITS ZIPPER",
            "eventDate": "2099-01-19", "startTime": None,
            "applyStart": "2098-10-19T20:00", "ticketType": "チケット受付", "url": source,
        }
        fresh = {
            **old, "id": "new-id", "startTime": "18:00",
            "url": "https://w.pia.jp/t/example/", "urls": ["https://w.pia.jp/t/example/", source],
        }
        payload = v2.build_payload({"events": [old]}, {"new-id": fresh}, [], [], date(2098, 10, 20))
        self.assertEqual([row["id"] for row in payload["events"]], ["new-id"])


if __name__ == "__main__":
    unittest.main()
