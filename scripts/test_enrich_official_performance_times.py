import unittest

import enrich_official_performance_times as enrich


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, html):
        self.html = html

    def get(self, url, timeout=20):
        return FakeResponse(self.html)


class OfficialPerformanceTimeTests(unittest.TestCase):
    def test_enriches_grouped_schedule_rows_from_official_article(self):
        url = "https://candytune.asobisystem.com/news/detail/82537"
        payload = {
            "events": [{
                "id": "tour",
                "group": "CANDY TUNE",
                "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
                "url": url,
                "schedule": [
                    {"date": "2026-08-29", "venue": "戸田市文化会館"},
                    {"date": "2026-09-04", "venue": "カルッツかわさき"},
                ],
            }]
        }
        html = """
            <div>2026.06.06</div>
            <div>日程：2026年8月29日（土）</div>
            <div>時間：OPEN 16:00 / START 17:00</div>
            <div>会場：埼玉県 戸田市文化会館</div>
            <div>日程：2026年9月4日（金）</div>
            <div>時間：OPEN 17:30 / START 18:30</div>
            <div>会場：神奈川県 カルッツかわさき</div>
        """
        result, diagnostics = enrich.enrich_payload(payload, FakeSession(html))
        rows = result["events"][0]["schedule"]
        self.assertEqual((rows[0]["openTime"], rows[0]["startTime"]), ("16:00", "17:00"))
        self.assertEqual((rows[1]["openTime"], rows[1]["startTime"]), ("17:30", "18:30"))
        self.assertEqual(diagnostics["changedEvents"], 1)

    def test_enriches_single_performance(self):
        url = "https://sweetsteady.asobisystem.com/news/detail/1"
        payload = {"events": [{"eventDate": "2027-03-04", "url": url}]}
        html = "<div>日程：2027年3月4日（木）</div><div>開場 17:00 / 開演 18:30</div><div>会場：日本武道館</div>"
        result, _ = enrich.enrich_payload(payload, FakeSession(html))
        self.assertEqual(result["events"][0]["openTime"], "17:00")
        self.assertEqual(result["events"][0]["startTime"], "18:30")


if __name__ == "__main__":
    unittest.main()
