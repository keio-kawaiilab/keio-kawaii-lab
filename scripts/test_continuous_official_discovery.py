import unittest
from datetime import date
from unittest.mock import patch

import audit_discovery_publication as publication
import continuous_official_discovery as discovery
import update_live_events_v2 as retention
from performance_entities import build_public_events
from sanitize_live_events import sanitize_payload
from resolve_source_priority import resolve


class ContinuousDiscoveryTests(unittest.TestCase):
    def test_homepage_article_survives_one_broken_news_page(self):
        retention.FEED_FAILURES.clear()
        def fetch(url, headers):
            if "page=3" in url:
                raise RuntimeError("temporary failure")
            if url.endswith("/"):
                return '<a href="/news/detail/new">New tour announced</a>'
            return "<html></html>"
        with patch.object(retention, "_fetch_news_page", side_effect=fetch):
            session = discovery.requests.Session()
            found = retention.deep_candidate_links(session, "CANDY TUNE", "https://candytune.asobisystem.com")
        self.assertEqual([item.url for item in found], ["https://candytune.asobisystem.com/news/detail/new"])
        self.assertEqual(len(retention.FEED_FAILURES["CANDY TUNE"]), 1)

    def test_future_article_and_publication_missing_url_are_revisited(self):
        base = "https://candytune.asobisystem.com/news/detail/"
        existing = {
            "events": [{"group": "CANDY TUNE", "eventDate": "2099-10-01", "url": base + "old"}],
            "pendingReview": [{"group": "CANDY TUNE", "url": base + "stale-pending"}],
            "failures": [{"group": "CANDY TUNE", "url": base + "stale-failure"}],
            "officialDiscoveryState": {
                "observations": [
                    {"group": "CANDY TUNE", "url": base + "retry", "status": "publication-missing"},
                    {"group": "CANDY TUNE", "url": base + "stale-observation", "status": "pending"},
                ]
            },
        }
        found = discovery.revisit_candidates(existing, date(2099, 9, 1))
        self.assertEqual(set(found), {base + "old", base + "retry"})

    def test_new_general_sale_flows_from_article_into_public_offer(self):
        candidate = discovery.parser.Candidate("CANDY TUNE", "CANDY TUNE 新ツアー", "https://candytune.asobisystem.com/news/detail/new")
        text = "2099.09.01\n日程：2099年10月1日\n会場：Test Hall\nOPEN 17:00 START 18:00\n一般発売：2099年9月10日10:00〜"
        rows = discovery.general_sale_rows(candidate, text, {"events": []})
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["applyEnd"])
        payload = retention.build_payload({"events": [], "anotherCollectorDiagnostics": {"ok": True}},
                                          {row["id"]: row for row in rows}, [], [], date(2099, 9, 1))
        self.assertTrue(payload["anotherCollectorDiagnostics"]["ok"])
        payload = sanitize_payload(payload, today=date(2099, 9, 15))
        payload["events"] = resolve(payload["events"])
        public, _ = build_public_events(payload["events"])
        report = publication.audit({"observations": [{"expectedOffers": rows}]}, {"publicEvents": public})
        self.assertEqual(report["representedOffers"], 1)
        self.assertEqual(report["missingOffers"], [])
        self.assertEqual(publication.audit({"observations": [{"expectedOffers": rows}]}, {"publicEvents": []})["missingOffers"], rows)

    def test_existing_show_gets_later_sale_from_same_old_article(self):
        candidate = discovery.parser.Candidate("MORE STAR", "MORE STAR Live", "https://morestar.asobisystem.com/news/detail/old")
        existing = {"events": [{"group": "MORE STAR", "eventDate": "2099-11-01", "startTime": "18:00", "url": candidate.url}]}
        rows = discovery.general_sale_rows(candidate, "2099.09.01\n一般販売\n2099年10月1日10:00〜\nSOLD OUT", existing)
        self.assertEqual(rows[0]["eventDate"], "2099-11-01")
        self.assertEqual(rows[0]["applicationStatus"], "sold_out")
        self.assertIsNone(rows[0]["applyEnd"])

    def test_offline_feeds_still_revisit_old_article_and_keep_new_sale(self):
        url = "https://morestar.asobisystem.com/news/detail/old"
        existing = {"events": [{"id": "show", "group": "MORE STAR", "eventDate": "2099-11-01", "url": url}]}
        seen = []
        def read(candidate, payload, headers):
            seen.append(candidate.url)
            rows = discovery.general_sale_rows(candidate, "2099.09.01\n一般発売：2099年10月1日10:00〜", payload)
            return rows, None, "parsed"
        with patch.object(retention, "deep_candidate_links", side_effect=RuntimeError("offline")), patch.object(discovery, "read_candidate", side_effect=read):
            fresh, pending, failures, counts, observations = discovery.collect(discovery.requests.Session(), existing)
        self.assertEqual(seen, [url])
        self.assertEqual(len(fresh), 1)
        self.assertEqual(len(failures), 6)
        out = retention.build_payload(existing, fresh, pending, failures, date(2099, 9, 1))
        public, _ = build_public_events(out["events"])
        self.assertEqual(publication.audit({"observations": observations}, {"publicEvents": public})["representedOffers"], 1)

    def test_ticket_article_without_performance_date_links_to_one_known_future_show(self):
        candidate = discovery.parser.Candidate(
            "CUTIE STREET",
            "『CUTIE STREET テストメンバー 生誕祭 2099』公演 リセールサービスのお知らせ",
            "https://cutiestreet.asobisystem.com/news/detail/resale",
        )
        existing = {"events": [{
            "id": "show",
            "group": "CUTIE STREET",
            "eventTitle": "CUTIE STREET テストメンバー 生誕祭 2099",
            "eventDate": "2099-11-09",
            "venue": "SGCホール有明",
            "startTime": "19:00",
            "ticketType": "現在受付なし",
        }]}
        review = {"applyStart": "2099-11-01T10:00", "applyEnd": "2099-11-05T23:59"}
        row = discovery.fallback_row_from_review(candidate, candidate.title, "リセール", review, existing)
        self.assertIsNotNone(row)
        self.assertEqual(row["eventDate"], "2099-11-09")
        self.assertEqual(row["ticketType"], "リセール")
        self.assertEqual(row["applyStart"], "2099-11-01T10:00")
        self.assertEqual(row["applyEnd"], "2099-11-05T23:59")

    def test_ticket_article_without_date_stays_pending_when_show_match_is_ambiguous(self):
        candidate = discovery.parser.Candidate(
            "CUTIE STREET",
            "CUTIE STREET 同名公演 リセールサービスのお知らせ",
            "https://cutiestreet.asobisystem.com/news/detail/resale",
        )
        existing = {"events": [
            {"group": "CUTIE STREET", "eventTitle": "CUTIE STREET 同名公演", "eventDate": "2099-11-09"},
            {"group": "CUTIE STREET", "eventTitle": "CUTIE STREET 同名公演", "eventDate": "2099-11-10"},
        ]}
        review = {"applyStart": "2099-11-01T10:00", "applyEnd": "2099-11-05T23:59"}
        self.assertIsNone(discovery.fallback_row_from_review(candidate, candidate.title, "リセール", review, existing))

    def test_central_fc_article_uses_existing_joint_event_url(self):
        url = "https://kawaiilab.asobisystem.com/news/detail/87217"
        existing = {"events": [
            {"group": "KAWAII LAB. SOUTH", "eventTitle": "Joint show", "eventDate": "2099-10-12", "url": url},
            {"group": "KAWAII LAB.合同", "participants": ["FRUITS ZIPPER", "CANDY TUNE"],
             "eventTitle": "Joint show", "eventDate": "2099-10-12", "url": url},
        ]}
        self.assertEqual(discovery.infer_central_group("Joint show FC先行", "受付開始", url, existing), "KAWAII LAB.合同")

    def test_expired_review_is_not_current_pending(self):
        self.assertTrue(discovery.review_is_expired(
            {"applyStart": "2026-01-01T10:00", "applyEnd": "2026-01-03T23:59"},
            date(2026, 9, 18),
        ))
        self.assertFalse(discovery.review_is_expired(
            {"applyStart": "2026-09-18T10:00", "applyEnd": "2026-09-20T23:59"},
            date(2026, 9, 18),
        ))

    def test_fallback_prefers_exact_existing_url_over_title_variation(self):
        url = "https://cutiestreet.asobisystem.com/live_information/detail/99999"
        candidate = discovery.parser.Candidate("CUTIE STREET", "Completely different ticket headline", url)
        existing = {"events": [{
            "group": "CUTIE STREET", "eventTitle": "Known Future Show", "eventDate": "2099-11-09",
            "venue": "Test Hall", "url": url,
        }]}
        review = {"applyStart": "2099-11-01T10:00", "applyEnd": "2099-11-05T23:59"}
        row = discovery.fallback_row_from_review(candidate, candidate.title, "FC先行", review, existing)
        self.assertIsNotNone(row)
        self.assertEqual(row["eventDate"], "2099-11-09")

    def test_unlabeled_fc_window_after_heading_is_extracted(self):
        text = "<KAWAII LAB. OFFICIAL FANCLUB 有料会員先行受付＞\n2026年9月18日(金)12:00〜2026年9月24日(木)23:59\nお申込みはこちら"
        self.assertEqual(
            discovery.unlabeled_ticket_window(text, 2026),
            ("2026-09-18T12:00", "2026-09-24T23:59"),
        )

    def test_performance_date_is_not_misread_as_general_sale_start(self):
        candidate = discovery.parser.Candidate("MORE STAR", "Live", "https://morestar.asobisystem.com/news/detail/new")
        self.assertEqual(discovery.general_sale_rows(candidate, "一般販売の詳細は後日\n公演日：2099年10月1日18:00", {}), [])

    def test_tour_resale_windows_are_not_cross_joined_to_all_dates(self):
        candidate = discovery.parser.Candidate("MORE STAR", "Live リセール", "https://morestar.asobisystem.com/news/detail/new")
        text = "2099.09.01\n公演日：2099年10月1日\nリセール：2099年9月28日10:00〜9月30日23:59\n公演日：2099年11月1日\nリセール：2099年10月28日10:00〜10月31日23:59"
        self.assertEqual(discovery.general_sale_rows(candidate, text, {}), [])

    def test_new_sale_with_time_enriches_existing_schedule_without_duplicate_show(self):
        existing = {"events": [{"id": "schedule", "group": "MORE STAR", "eventTitle": "MORE STAR New Live", "title": "MORE STAR New Live", "eventDate": "2099-10-01", "venue": "Test Hall", "ticketType": "現在受付なし", "sourceType": "official-schedule", "url": "https://morestar.asobisystem.com/live_information/detail/1"}]}
        row = {"id": "new-sale", "group": "MORE STAR", "title": "MORE STAR New Live 一般発売", "eventDate": "2099-10-01", "startTime": "18:00", "venue": "Test Hall", "ticketType": "一般発売", "applyStart": "2099-09-01T10:00", "url": "https://morestar.asobisystem.com/news/detail/new", "sourceType": "auto"}
        result = retention.build_payload(existing, {row["id"]: row}, [], [], date(2099, 9, 1))
        public, _ = build_public_events(result["events"])
        self.assertEqual(len(public), 1)
        self.assertEqual(public[0]["startTime"], "18:00")
        self.assertEqual(len(public[0]["offers"]), 1)


if __name__ == "__main__":
    unittest.main()
