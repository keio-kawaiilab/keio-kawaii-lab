import unittest

import update_playguide_events as playguides


class PlayguideEventTests(unittest.TestCase):
    def test_jsonld_discovers_hidden_eplus_performance(self):
        html = '''<script type="application/ld+json">{
          "@type":"Event",
          "url":"https://eplus.jp/sf/detail/3923750001-P0030013P021001",
          "startDate":"2026-12-01T18:30",
          "location":{"@type":"Place","name":"大分・iichikoグランシアタ"}
        }</script>'''
        rows = playguides.jsonld_performances(html)
        self.assertEqual("2026-12-01", rows[0]["day"])
        self.assertEqual("18:30", rows[0]["startTime"])
        self.assertIn("iichiko", rows[0]["venue"])

    def test_iso_window_accepts_japanese_weekday(self):
        start, end = playguides.iso_window(
            "受付期間:2026/8/21(金)12:00～2026/8/31(月)23:59"
        )
        self.assertEqual(start, "2026-08-21T12:00")
        self.assertEqual(end, "2026-08-31T23:59")

    def test_event_record_keeps_provider_and_performance_time(self):
        event = playguides.event_record(
            provider="eplus",
            group="CANDY TUNE",
            title="CANDY TUNE",
            ticket_type="2次プレオーダー受付",
            apply_start="2026-08-21T12:00",
            apply_end="2026-08-31T23:59",
            event_date="2026-10-08",
            venue="仙台サンプラザホール",
            url="https://eplus.jp/sf/detail/example",
            open_time="17:30",
            start_time="18:30",
        )
        self.assertEqual(event["ticketProvider"], "eplus")
        self.assertEqual(event["openTime"], "17:30")
        self.assertEqual(event["startTime"], "18:30")
        self.assertTrue(event["applicationWindowVerified"])

    def test_dedupe_never_collapses_different_providers(self):
        common = dict(
            group="CANDY TUNE",
            title="CANDY TUNE",
            ticket_type="先行",
            apply_start="2026-08-20T12:00",
            apply_end="2026-08-31T23:59",
            event_date="2026-10-08",
            venue="仙台サンプラザホール",
        )
        events = [
            playguides.event_record(provider="lawson", url="https://l-tike.com/order/?gLcode=1", **common),
            playguides.event_record(provider="eplus", url="https://eplus.jp/sf/detail/1", **common),
        ]
        self.assertEqual(len(playguides.dedupe(events)), 2)


if __name__ == "__main__":
    unittest.main()
