import unittest
from datetime import date

from update_official_schedule import (
    OfficialRow, build_event, collapse_missing, enrich_existing, event_key,
    parse_detail, parse_schedule_list, propagate_ticket_scopes,
)


class OfficialScheduleTests(unittest.TestCase):
    def test_list_parses_only_live_and_event(self):
        html = '''<a href="/live_information/detail/1"><span class="block--date__month">09</span><span class="block--date__date">20</span><p class="category">EVENT</p><p class="tit">IDOL RUNWAY COLLECTION</p></a>
        <a href="/live_information/detail/2"><span class="block--date__month">09</span><span class="block--date__date">21</span><p class="category">TV</p><p class="tit">TV番組</p></a>'''
        rows = parse_schedule_list(html, "CANDY TUNE", "https://example.com", 2026, 9, date(2026, 8, 24))
        self.assertEqual(1, len(rows))
        self.assertEqual("external", rows[0].event_scope)

    def test_detail_parses_venue_and_times(self):
        html = '''<div class="block--title"><p class="tit">生誕祭</p></div><ul class="block--liveinfo">
        <li><p class="item-tit">公演日</p><p class="item-detail">2026.10.01</p></li>
        <li><p class="item-tit">開催場所・会場</p><p class="item-detail">東京都 Veats Shibuya</p></li></ul>
        <div>OPEN 17:30 / START 19:00</div>'''
        row = parse_detail(html)
        self.assertEqual("東京都 Veats Shibuya", row["venue"])
        self.assertEqual("17:30", row["openTime"])
        self.assertEqual("19:00", row["startTime"])

    def test_shared_external_rows_collapse(self):
        rows = [
            OfficialRow("CANDY TUNE", "2026-09-21", "LIVE", "ROCK IN JAPAN FESTIVAL 2026", "a", "external"),
            OfficialRow("CUTIE STREET", "2026-09-21", "LIVE", "ROCK IN JAPAN FESTIVAL 2026", "b", "external"),
        ]
        self.assertEqual(1, len(collapse_missing(rows)))
        self.assertEqual(event_key(rows[0].title), event_key(rows[1].title))

    def test_same_festival_listing_is_one_calendar_event(self):
        rows = [
            OfficialRow("FRUITS ZIPPER", "2026-09-19", "EVENT", "東京ガールズコレクション 2026", "a", "external"),
            OfficialRow("FRUITS ZIPPER", "2026-09-19", "EVENT", "東京ガールズコレクション 2026（櫻井・鎮西）", "b", "external"),
            OfficialRow("SWEET STEADY", "2026-09-19", "EVENT", "TGC 2026", "c", "external"),
        ]
        self.assertEqual(1, len(collapse_missing(rows)))

    def test_ticket_row_inherits_official_performance_scope(self):
        event = {
            "group": "CANDY TUNE", "eventDate": "2026-12-01", "title": "CANDY TUNE",
            "sourceType": "eplus", "eventScope": "external",
        }
        row = OfficialRow(
            "CANDY TUNE", "2026-12-01", "LIVE", "CANDY TUNE JAPAN TOUR 2026",
            "https://example.com/official", "kawaii-lab",
        )
        self.assertEqual(1, propagate_ticket_scopes([event], [row]))
        self.assertEqual("kawaii-lab", event["eventScope"])

    def test_schedule_only_large_benefit_is_never_rendered_as_a_live(self):
        row = OfficialRow(
            "FRUITS ZIPPER", "2026-09-06", "EVENT",
            "FRUITS ZIPPER 5thシングルCD発売記念イベント 大特典会@ベルサール汐留",
            "https://example.com/official", "kawaii-lab",
        )
        event = build_event([row], {"venue": "東京都 ベルサール汐留"})
        self.assertEqual("large-benefit", event["eventCategory"])
        self.assertEqual("awaiting-details", event["specialDetailsStatus"])

    def test_existing_schedule_special_gets_category(self):
        event = {"sourceType": "official-schedule", "title": "大特典会", "url": "https://example.com/old"}
        row = OfficialRow(
            "SWEET STEADY", "2026-09-06", "EVENT", "SWEET STEADY 大特典会",
            "https://example.com/official", "kawaii-lab",
        )
        enrich_existing(event, row, {})
        self.assertEqual("large-benefit", event["eventCategory"])
        self.assertEqual("schedule-only", event["applicationDisplayMode"])


if __name__ == "__main__":
    unittest.main()
