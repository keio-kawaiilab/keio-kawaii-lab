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

    def test_exact_window_on_enriched_matching_event_is_already_represented(self):
        url = "https://morestar.asobisystem.com/live_information/detail/46447"
        candidate = discovery.parser.Candidate("MORE STAR", "MORE STAR 大特典", url)
        existing = {"events": [
            {
                "group": "MORE STAR", "eventDate": "2099-11-03",
                "ticketType": "現在受付なし", "url": url,
            },
            {
                "group": "MORE STAR", "eventDate": "2099-11-03",
                "urls": [url],
                "offers": [{
                    "ticketType": "対象商品予約",
                    "applyStart": "2099-10-23T21:00",
                    "applyEnd": "2099-10-27T23:59",
                }],
            },
        ]}
        review = {"applyStart": "2099-10-23T21:00", "applyEnd": "2099-10-27T23:59"}
        self.assertTrue(discovery.review_is_already_represented(candidate, review, existing))

    def test_exact_multi_performance_upgrade_notice_is_already_represented(self):
        url = "https://sweetsteady.asobisystem.com/news/detail/93491"
        candidate = discovery.parser.Candidate(
            "SWEET STEADY",
            "SWEET STEADY JAPAN TOUR アップグレード抽選受付のお知らせ",
            url,
        )
        existing = {"events": [{
            "group": "SWEET STEADY",
            "eventDate": "2099-11-13",
            "ticketType": "アップグレード抽選",
            "applyStart": "2099-10-23T18:00",
            "applyEnd": "2099-10-26T23:59",
            "url": "https://sweetsteady.asobisystem.com/feature/tour",
            "urls": ["https://sweetsteady.asobisystem.com/feature/tour", url],
        }]}
        self.assertTrue(discovery.source_notice_is_already_represented(
            candidate, candidate.title, existing,
        ))

    def test_exact_notice_url_does_not_hide_a_different_ticket_family(self):
        url = "https://sweetsteady.asobisystem.com/news/detail/upgrade"
        candidate = discovery.parser.Candidate(
            "SWEET STEADY", "アップグレード抽選受付のお知らせ", url,
        )
        existing = {"events": [{
            "group": "SWEET STEADY",
            "eventDate": "2099-11-13",
            "ticketType": "FC先行",
            "applyStart": "2099-10-01T12:00",
            "applyEnd": "2099-10-05T23:59",
            "urls": [url],
        }]}
        self.assertFalse(discovery.source_notice_is_already_represented(
            candidate, candidate.title, existing,
        ))

    def test_represented_notice_clears_review_when_parser_also_returns_rows(self):
        url = "https://sweetsteady.asobisystem.com/news/detail/93491"
        candidate = discovery.parser.Candidate(
            "SWEET STEADY",
            "SWEET STEADY JAPAN TOUR アップグレード抽選受付のお知らせ",
            url,
        )
        existing = {"events": [{
            "group": "SWEET STEADY",
            "eventDate": "2099-11-13",
            "ticketType": "アップグレード抽選",
            "applyStart": "2099-10-23T18:00",
            "applyEnd": "2099-10-26T23:59",
            "urls": [url],
        }]}

        class DummyResponse:
            text = (
                "<div class='section--detail'><h1>SWEET STEADY JAPAN TOUR "
                "アップグレード抽選受付のお知らせ</h1><p>チケット受付</p></div>"
            )
            def raise_for_status(self):
                return None

        class DummySession:
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def get(self, *args, **kwargs): return DummyResponse()

        parsed = [{
            "eventDate": "2099-11-13",
            "ticketType": "FC先行",
            "applyStart": "2099-09-01T12:00",
            "applyEnd": "2099-09-05T23:59",
        }]
        review = {"reason": "additional dates unresolved"}
        with patch.object(discovery.requests, "Session", return_value=DummySession()), \
             patch.object(discovery.parser, "parse_candidate", return_value=(parsed, review)):
            rows, pending, status = discovery.read_candidate(candidate, existing, {})

        self.assertEqual(1, len(rows))
        self.assertIsNone(pending)
        self.assertEqual("parsed", status)

    def test_represented_notice_clears_review_synthesized_after_empty_parse(self):
        url = "https://sweetsteady.asobisystem.com/news/detail/93491"
        candidate = discovery.parser.Candidate(
            "SWEET STEADY",
            "SWEET STEADY JAPAN TOUR アップグレード抽選受付のお知らせ",
            url,
        )
        existing = {"events": [{
            "group": "SWEET STEADY",
            "eventDate": "2099-11-13",
            "ticketType": "アップグレード抽選",
            "applyStart": "2099-10-23T18:00",
            "applyEnd": "2099-10-26T23:59",
            "urls": [url],
        }]}

        class DummyResponse:
            text = (
                "<div class='section--detail'><h1>SWEET STEADY JAPAN TOUR "
                "アップグレード抽選受付のお知らせ</h1><p>チケット受付</p></div>"
            )
            def raise_for_status(self):
                return None

        class DummySession:
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def get(self, *args, **kwargs): return DummyResponse()

        window = ("2099-10-23T18:00", "2099-10-26T23:59")
        with patch.object(discovery.requests, "Session", return_value=DummySession()), \
             patch.object(discovery.parser, "parse_candidate", return_value=([], None)), \
             patch.object(discovery, "unlabeled_ticket_window", return_value=window):
            rows, pending, status = discovery.read_candidate(candidate, existing, {})

        self.assertEqual([], rows)
        self.assertIsNone(pending)
        self.assertEqual("represented", status)

    def test_represented_notice_skips_generic_final_fallback_review(self):
        url = "https://sweetsteady.asobisystem.com/news/detail/93491"
        candidate = discovery.parser.Candidate(
            "SWEET STEADY",
            "SWEET STEADY JAPAN TOUR アップグレード抽選受付のお知らせ",
            url,
        )
        existing = {"events": [{
            "group": "SWEET STEADY",
            "eventDate": "2099-11-13",
            "ticketType": "アップグレード抽選",
            "applyStart": "2099-10-23T18:00",
            "applyEnd": "2099-10-26T23:59",
            "urls": [url],
        }]}

        class DummyResponse:
            text = (
                "<div class='section--detail'><h1>SWEET STEADY JAPAN TOUR "
                "アップグレード抽選受付のお知らせ</h1><p>チケット受付</p></div>"
            )
            def raise_for_status(self):
                return None

        class DummySession:
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def get(self, *args, **kwargs): return DummyResponse()

        with patch.object(discovery.requests, "Session", return_value=DummySession()), \
             patch.object(discovery.parser, "parse_candidate", return_value=([], None)), \
             patch.object(discovery, "unlabeled_ticket_window", return_value=None), \
             patch.object(discovery, "standalone_ticket_window", return_value=None):
            rows, pending, status = discovery.read_candidate(candidate, existing, {})

        self.assertEqual([], rows)
        self.assertIsNone(pending)
        self.assertEqual("represented", status)

    def test_different_window_on_matching_event_is_not_already_represented(self):
        url = "https://morestar.asobisystem.com/live_information/detail/46447"
        candidate = discovery.parser.Candidate("MORE STAR", "MORE STAR 大特典", url)
        existing = {"events": [{
            "group": "MORE STAR", "eventDate": "2099-11-03", "urls": [url],
            "offers": [{
                "applyStart": "2099-10-23T21:00",
                "applyEnd": "2099-10-27T23:59",
            }],
        }]}
        review = {"applyStart": "2099-10-24T21:00", "applyEnd": "2099-10-27T23:59"}
        self.assertFalse(discovery.review_is_already_represented(candidate, review, existing))

    def test_central_fc_article_uses_existing_joint_event_url(self):
        url = "https://kawaiilab.asobisystem.com/news/detail/87217"
        existing = {"events": [
            {"group": "KAWAII LAB. SOUTH", "eventTitle": "Joint show", "eventDate": "2099-10-12", "url": url},
            {"group": "KAWAII LAB.合同", "participants": ["FRUITS ZIPPER", "CANDY TUNE"],
             "eventTitle": "Joint show", "eventDate": "2099-10-12", "url": url},
        ]}
        self.assertEqual(discovery.infer_central_group("Joint show FC先行", "受付開始", url, existing), "KAWAII LAB.合同")

    def test_standalone_resale_range_is_extracted(self):
        text = (
            "リセールサービスのお知らせ\n"
            "申込方法をご確認ください\n"
            "2026年5月22日(金)10:00〜2026年5月27日(水)23:59まで\n"
        )
        self.assertEqual(
            discovery.standalone_ticket_window(text, 2026),
            ("2026-05-22T10:00", "2026-05-27T23:59"),
        )

    def test_end_only_expired_ticket_window_leaves_current_pending_queue(self):
        text = "2026.02.17\n受付期間：～2026年3月2日(月)23:59まで"
        self.assertTrue(
            discovery.end_only_ticket_window_is_expired(text, date(2026, 9, 28))
        )
        future = "2026.09.27\n受付期間：～2026年10月2日(金)23:59まで"
        self.assertFalse(
            discovery.end_only_ticket_window_is_expired(future, date(2026, 9, 28))
        )

    def test_ambiguous_central_article_with_expired_window_is_past(self):
        candidate = discovery.parser.Candidate(
            "KAWAII LAB. FC",
            "KAWAII LAB. SESSION vol.17 / vol.18 チケットぴあ特別先行（抽選）実施決定！",
            "https://kawaiilab.asobisystem.com/news/detail/old",
        )

        class DummyResponse:
            text = (
                "<div class='section--detail'><h1>KAWAII LAB. SESSION vol.17 / vol.18 "
                "チケットぴあ特別先行（抽選）実施決定！</h1>"
                "<p>受付期間：2025年11月28日(金)12:00〜2025年12月3日(水)23:59</p></div>"
            )
            def raise_for_status(self):
                return None

        class DummySession:
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def get(self, *args, **kwargs): return DummyResponse()

        with patch.object(discovery.requests, "Session", return_value=DummySession()):
            rows, review, status = discovery.read_candidate(candidate, {"events": []}, {})
        self.assertEqual([], rows)
        self.assertIsNone(review)
        self.assertEqual("past", status)

    def test_system_maintenance_article_is_irrelevant_even_if_body_mentions_ticket(self):
        candidate = discovery.parser.Candidate(
            "CANDY TUNE",
            "［重要］システムメンテナンスのお知らせ",
            "https://candytune.asobisystem.com/news/detail/maintenance",
        )

        class DummyResponse:
            text = (
                "<div class='section--detail'><h1>［重要］システムメンテナンスのお知らせ</h1>"
                "<p>メンテナンス中はチケットページをご利用いただけません。</p></div>"
            )
            def raise_for_status(self):
                return None

        class DummySession:
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def get(self, *args, **kwargs): return DummyResponse()

        with patch.object(discovery.requests, "Session", return_value=DummySession()):
            rows, review, status = discovery.read_candidate(candidate, {"events": []}, {})
        self.assertEqual([], rows)
        self.assertIsNone(review)
        self.assertEqual("irrelevant", status)

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

    def test_non_sale_fc_notice_is_irrelevant(self):
        candidate = discovery.parser.Candidate(
            "KAWAII LAB. FC",
            "KAWAII LAB. STORE デジタル整理券導入のお知らせ",
            "https://kawaiilab.asobisystem.com/news/detail/notice",
        )
        class DummyResponse:
            text = "<div class='section--detail'><h1>KAWAII LAB. STORE デジタル整理券導入のお知らせ</h1><p>チケットに関する注意事項</p></div>"
            def raise_for_status(self):
                return None
        class DummySession:
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def get(self, *args, **kwargs): return DummyResponse()
        with patch.object(discovery.requests, "Session", return_value=DummySession()):
            rows, review, status = discovery.read_candidate(candidate, {"events": []}, {})
        self.assertEqual(rows, [])
        self.assertIsNone(review)
        self.assertEqual(status, "irrelevant")

    def test_unlabeled_official_fc_window_publishes_both_parts_and_common_venue(self):
        candidate = discovery.parser.Candidate(
            "SWEET STEADY", "2026年11月15日「SWEET STEADYのSWEETEST STORY」開催決定！FC先行受付！",
            "https://sweetsteady.asobisystem.com/news/detail/92529",
        )
        html = """
        <div class="section--detail"><h1>2026年11月15日「SWEET STEADYのSWEETEST STORY」開催決定！FC先行受付！</h1>
        <p>2026.10.13</p>
        <p>FC先行受付が10月15日(木)10:00からスタート！</p>
        <p>〖SWEET STEADYのSWEETEST STORY 第1部〗</p>
        <p>日程：2026年11月15日(日)</p>
        <p>時間：開場 14:00 開演 15:00</p>
        <p>〖SWEET STEADYのSWEETEST STORY 第2部〗</p>
        <p>日程：2026年11月15日(日)</p>
        <p>時間：開場 17:00 開演 18:00</p>
        <p>会場：お台場特設会場（フジテレビ湾岸スタジオ）</p>
        <p>＜SWEET STEADY OFFICIAL FANCLUB 有料会員先行受付＞</p>
        <p>2026年10月15日(木)10:00〜2026年10月18日(日)23:59</p>
        <a href="https://w.pia.jp/t/first/">第1部お申込みはこちら</a>
        <a href="https://w.pia.jp/t/second/">第2部お申込みはこちら</a></div>"""
        class Response:
            text = html
            def raise_for_status(self): pass
        class Session:
            headers = {}
            def __enter__(self): return self
            def __exit__(self,*args): return None
            def get(self,*args,**kwargs): return Response()
        with patch.object(discovery.requests, "Session", return_value=Session()):
            rows, pending, status=discovery.read_candidate(candidate, {"events":[]}, {})
        self.assertEqual("parsed",status,(pending,rows))
        self.assertIsNone(pending)
        self.assertEqual(2,len(rows))
        self.assertEqual({"15:00","18:00"}, {row["startTime"] for row in rows})
        self.assertEqual(1,len({row["venue"] for row in rows}))
        self.assertEqual({"2026-10-15T10:00"}, {row["applyStart"] for row in rows})
        self.assertEqual({"2026-10-18T23:59"}, {row["applyEnd"] for row in rows})
        self.assertEqual({candidate.url}, {row["url"] for row in rows})
        self.assertEqual(2,len({row["id"] for row in rows}))
        public, _ = build_public_events(rows)
        self.assertEqual(2, len(public))
        self.assertEqual({"15:00","18:00"}, {event["startTime"] for event in public})
        self.assertTrue(all(event["eventScope"] == "external" for event in public))
        self.assertTrue(all("FC先行" in event["ticketType"] for event in public))

    def test_new_official_show_announcement_without_any_ticket_words_is_imported(self):
        candidate = discovery.parser.Candidate(
            "SWEET STEADY", "2026.10.25 SWEET STEADY 新ライブ開催決定！",
            "https://sweetsteady.asobisystem.com/news/detail/newshow",
        )
        html = """
        <div class="section--detail"><h1>SWEET STEADY 新ライブ開催決定！</h1>
        <p>2026.10.25</p><p>日程：2026年12月21日(月)</p>
        <p>会場：Zepp Haneda</p><p>時間：開場 17:00 開演 18:00</p></div>"""
        class Response:
            text = html
            def raise_for_status(self): pass
        class Session:
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def get(self, *args, **kwargs): return Response()
        with patch.object(discovery.requests, "Session", return_value=Session()):
            rows, review, status = discovery.read_candidate(candidate, {"events": []}, {})
        self.assertEqual("schedule-only", status)
        self.assertIsNone(review)
        self.assertEqual(1, len(rows))
        self.assertEqual("2026-12-21", rows[0]["eventDate"])
        self.assertEqual("Zepp Haneda", rows[0]["venue"])
        self.assertEqual("18:00", rows[0]["startTime"])
        self.assertEqual("現在受付なし", rows[0]["ticketType"])

    def test_new_show_without_confirmed_venue_is_kept_as_review_not_ignored(self):
        candidate = discovery.parser.Candidate(
            "MORE STAR", "2026.10.25 MORE STAR 単独ライブ開催決定！",
            "https://morestar.asobisystem.com/news/detail/newshow",
        )
        html = "<div class='section--detail'><h1>MORE STAR 単独ライブ開催決定！</h1><p>2026.10.25</p><p>日程：2026年12月23日</p></div>"
        class Response:
            text=html
            def raise_for_status(self): pass
        class Session:
            headers={}
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def get(self,*args,**kwargs): return Response()
        with patch.object(discovery.requests, "Session", return_value=Session()):
            rows, review, status = discovery.read_candidate(candidate, {"events":[]}, {})
        self.assertEqual("pending",status)
        self.assertEqual([],rows)
        self.assertEqual(candidate.url,review["url"])

    def test_real_format_official_fc_opening_without_deadline_is_published(self):
        candidate = discovery.parser.Candidate(
            "CANDY TUNE",
            "2026年11⽉6⽇(⾦)「KAWAII LAB. ファンクラブ限定フリーライブ」開催決定！FC先行受付開始！",
            "https://candytune.asobisystem.com/news/detail/93706",
        )
        article = """
        <div class="section--detail">
        <h1>2026年11⽉6⽇(⾦)「KAWAII LAB. ファンクラブ限定フリーライブ」開催決定！FC先行受付開始！</h1>
        <p>2026.10.24</p>
        <p>CANDY TUNE OFFICIAL FANCLUB有料会員様限定のチケット先行受付が10月24日(土)12:00よりスタート！</p>
        <p>日程：2026年11⽉6⽇(⾦)</p>
        <p>会場：東京ガーデンシアター</p>
        <p>時間：開場 16:30 開演 18:00</p>
        <p>出演者：CANDY TUNE / SWEET STEADY / CUTIE STREET / MORE STAR</p>
        </div>"""
        class Response:
            text = article
            def raise_for_status(self): pass
        class Session:
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def get(self, *_args, **_kwargs): return Response()
        with patch.object(discovery.requests, "Session", return_value=Session()):
            rows, pending, status = discovery.read_candidate(candidate, {"events": []}, {})
        self.assertEqual("parsed", status, (pending, rows))
        self.assertIsNone(pending)
        self.assertEqual(1, len(rows))
        self.assertEqual("2026-11-06", rows[0]["eventDate"])
        self.assertEqual("東京ガーデンシアター", rows[0]["venue"])
        self.assertEqual("18:00", rows[0]["startTime"])
        self.assertEqual("2026-10-24T12:00", rows[0]["applyStart"])
        self.assertIsNone(rows[0]["applyEnd"])
        self.assertEqual("CANDY TUNE FC先行", rows[0]["ticketType"])
        self.assertEqual(candidate.url, rows[0]["url"])

    def test_start_only_extractor_rejects_unsourced_opening_and_multiple_windows(self):
        candidate = discovery.parser.Candidate("MORE STAR", "FC先行受付", "https://morestar.asobisystem.com/news/detail/example")
        common = "2026.10.24\\n日程：2026年11月6日\\n会場：東京ガーデンシアター\\n開演 18:00\\n"
        self.assertEqual([], discovery.confirmed_start_only_rows(candidate, candidate.title, common+"受付期間未定", {"events":[]}))
        text = common+"チケット先行受付が10月24日(土)12:00からスタート！\\nチケット先行受付が10月25日(日)12:00からスタート！"
        self.assertEqual([], discovery.confirmed_start_only_rows(candidate, candidate.title, text, {"events":[]}))

    def test_actual_multi_day_joint_fc_article_parses_official_ticket_and_times(self):
        title = "2026.10.12 「KAWAII LAB. 5th ANNIVERSARY TOUR」開催決定！FC先行開始！"
        candidate = discovery.parser.Candidate(
            "KAWAII LAB. FC", title,
            "https://kawaiilab.asobisystem.com/news/detail/92410",
        )
        body = """
        <div class="section--detail">
        <h1>2026.10.12 「KAWAII LAB. 5th ANNIVERSARY TOUR」開催決定！FC先行開始！</h1>
        <p>2026.10.12</p>
        <p>日程：2027年1月30日(土)</p><p>時間：OPEN 15:00 / START 17:00</p>
        <p>会場：宮城県 宮城セキスイハイムスーパーアリーナ</p>
        <p>日程：2027年1月31日(日)</p><p>時間：OPEN 14:00 / START 16:00</p>
        <p>会場：宮城県 宮城セキスイハイムスーパーアリーナ</p>
        <p>出演：FRUITS ZIPPER / CANDY TUNE / SWEET STEADY / CUTIE STREET / MORE STAR</p>
        <p>＜KAWAII LAB. OFFICIAL FANCLUB 有料会員先行受付＞</p>
        <p>受付期間：2026年10月12日(月)18:30～2026年10月18日(日)23:59</p>
        <a href="https://w.pia.jp/t/kawaii-lab-fifth/">お申込みはこちら</a>
        </div>"""
        class DummyResponse:
            text = body
            def raise_for_status(self): pass
        class DummySession:
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def get(self, *args, **kwargs): return DummyResponse()
        existing = {"events": [{
            "group": "KAWAII LAB.合同", "eventDate": "2027-01-30",
            "title": "KAWAII LAB. 5th ANNIVERSARY TOUR",
            "venue": "宮城セキスイハイムスーパーアリーナ",
            "ticketType": "現在受付なし",
        }]}
        with patch.object(discovery.requests, "Session", return_value=DummySession()):
            rows, review, status = discovery.read_candidate(candidate, existing, {})
        self.assertEqual("parsed", status, (rows, review, status))
        self.assertIsNone(review)
        self.assertEqual({"2027-01-30", "2027-01-31"}, {r["eventDate"] for r in rows})
        self.assertEqual({"KAWAII LAB.合同"}, {r["group"] for r in rows})
        self.assertEqual({("15:00", "17:00"), ("14:00", "16:00")},
                         {(r["openTime"], r["startTime"]) for r in rows})
        self.assertEqual({"2026-10-12T18:30"}, {r["applyStart"] for r in rows})
        self.assertEqual({"2026-10-18T23:59"}, {r["applyEnd"] for r in rows})

    def test_news_publication_date_does_not_hide_future_joint_tour(self):
        title = "2026.10.12 「KAWAII LAB. 5th ANNIVERSARY TOUR」開催決定！FC先行開始！"
        official_body = (
            "2026.10.12\n"
            "2027年1月30日(土) OPEN 15:00 START 17:00\n"
            "2027年1月31日(日) OPEN 14:00 START 16:00\n"
            "FRUITS ZIPPER / CANDY TUNE / SWEET STEADY / CUTIE STREET / MORE STAR\n"
            "受付期間：2026年10月12日18:30～2026年10月18日23:59"
        )
        self.assertFalse(discovery.title_is_past_event(title, official_body, date(2026, 10, 25)))
        existing = {"events": [{
            "id": "joint-tour",
            "group": "KAWAII LAB.合同",
            "eventDate": "2027-01-30",
            "eventTitle": "KAWAII LAB. 5th ANNIVERSARY TOUR",
            "venue": "宮城セキスイハイムスーパーアリーナ",
        }]}
        group = discovery.infer_central_group(
            title, official_body, "https://kawaiilab.asobisystem.com/news/detail/92410", existing
        )
        self.assertEqual("KAWAII LAB.合同", group)

    def test_explicitly_dated_past_ticket_title_is_historical(self):
        self.assertTrue(discovery.title_is_past_event(
            "7/11(土) KAWAII LAB. SESSION 当日券販売のお知らせ",
            "2026.07.11",
            date(2026, 9, 18),
        ))
        self.assertFalse(discovery.title_is_past_event(
            "2026年10月26日(月) SWEET STEADY BIRTHDAY LIVE FC先行受付開始！",
            "2026.09.18",
            date(2026, 9, 18),
        ))

    def test_dated_birthday_fc_article_links_to_existing_performance(self):
        candidate = discovery.parser.Candidate(
            "SWEET STEADY",
            "2026年10月26日(月)「SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026」開催決定！FC先行受付開始！",
            "https://kawaiilab.asobisystem.com/news/detail/90038",
        )
        existing = {"events": [{
            "group": "SWEET STEADY",
            "eventTitle": "SWEET STEADY 庄司なぎさ BIRTHDAY LIVE 2026",
            "eventDate": "2026-10-26",
            "venue": "Test Hall",
            "url": "https://sweetsteady.asobisystem.com/news/detail/88494",
        }]}
        review = {"applyStart": "2026-09-18T12:00", "applyEnd": "2026-09-24T23:59"}
        row = discovery.fallback_row_from_review(candidate, candidate.title, "2026.09.18", review, existing)
        self.assertIsNotNone(row)
        self.assertEqual(row["eventDate"], "2026-10-26")
        self.assertEqual(row["applyStart"], "2026-09-18T12:00")
        self.assertEqual(row["applyEnd"], "2026-09-24T23:59")

    def test_unlabeled_fc_window_after_heading_is_extracted(self):
        text = "<KAWAII LAB. OFFICIAL FANCLUB 有料会員先行受付＞\n2026年9月18日(金)12:00〜2026年9月24日(木)23:59\nお申込みはこちら"
        self.assertEqual(
            discovery.unlabeled_ticket_window(text, 2026),
            ("2026-09-18T12:00", "2026-09-24T23:59"),
        )

    def test_performance_date_is_not_misread_as_general_sale_start(self):
        candidate = discovery.parser.Candidate("MORE STAR", "Live", "https://morestar.asobisystem.com/news/detail/new")
        self.assertEqual(discovery.general_sale_rows(candidate, "一般販売の詳細は後日\n公演日：2099年10月1日18:00", {}), [])

    def test_tour_resale_rows_are_paired_per_performance(self):
        candidate = discovery.parser.Candidate(
            "FRUITS ZIPPER",
            "FRUITS ZIPPER JAPAN TOUR 2099 リセールサービスのお知らせ",
            "https://fruitszipper.asobisystem.com/news/detail/resale",
        )
        text = (
            "2099.08.31\n"
            "2099/9/3(木) よこすか芸術劇場\n"
            "〖リセール受付・購入期間〗9/1(火)10:00〜9/2(水)23:59\n"
            "2099/9/21(月) 三重県文化会館\n"
            "〖リセール受付・購入期間〗9/19(土)10:00〜9/20(日)23:59\n"
        )
        rows = discovery.paired_resale_rows(candidate, text)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {(row["eventDate"], row["applyStart"], row["applyEnd"]) for row in rows},
            {
                ("2099-09-03", "2099-09-01T10:00", "2099-09-02T23:59"),
                ("2099-09-21", "2099-09-19T10:00", "2099-09-20T23:59"),
            },
        )

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
