import json
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from refresh_train_status import build_payload, event_area_ids, parse_trouble_routes


JST = ZoneInfo("Asia/Tokyo")


class RefreshTrainStatusTests(unittest.TestCase):
    def setUp(self):
        self.venues = [{
            "id": "arena",
            "name": "テストアリーナ",
            "aliases": ["東京都 テストアリーナ"],
            "prefecture": "東京都",
        }]
        self.events = [{
            "id": "event-1",
            "eventDate": "2026-08-24",
            "venue": "東京都 テストアリーナ",
        }]

    def test_only_today_event_regions_are_requested(self):
        self.assertEqual(event_area_ids(self.events, self.venues, "2026-08-24"), ["4"])
        self.assertEqual(event_area_ids(self.events, self.venues, "2026-08-25"), [])

    def test_yahoo_area_codes_for_western_japan(self):
        venues = [
            {"name": "九州会場", "prefecture": "福岡県"},
            {"name": "中国会場", "prefecture": "広島県"},
            {"name": "四国会場", "prefecture": "香川県"},
        ]
        events = [{"eventDate": "2026-08-24", "venue": venue["name"]} for venue in venues]
        self.assertEqual(event_area_ids(events, venues, "2026-08-24"), ["7", "8", "9"])

    def test_parses_minimal_trouble_route_fields(self):
        next_data = {
            "props": {"pageProps": {"troubleRails": [{"routeInfo": {"property": {
                "displayName": "横浜線",
                "companyName": "JR東日本",
                "pcUrl1": "https://transit.yahoo.co.jp/traininfo/detail/31/0/",
                "diainfo": [{"status": "運転状況", "updateDate": "2026-08-24 12:05:00", "message": "転載しない詳細"}],
            }}}]}},
        }
        page = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(next_data, ensure_ascii=False) + '</script>'
        self.assertEqual(parse_trouble_routes(page), [{
            "name": "横浜線",
            "company": "JR東日本",
            "status": "運転状況",
            "updatedAt": "2026-08-24 12:05:00",
            "url": "https://transit.yahoo.co.jp/traininfo/detail/31/0/",
        }])

    def test_no_event_means_no_external_request_and_empty_routes(self):
        def forbidden(_area):
            raise AssertionError("fetcher must not be called")

        payload = build_payload(
            "2026-08-25",
            datetime(2026, 8, 25, 9, 0, tzinfo=JST),
            self.events,
            self.venues,
            forbidden,
        )
        self.assertEqual(payload["routes"], [])


if __name__ == "__main__":
    unittest.main()
