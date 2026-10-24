import unittest
from datetime import date

from update_official_schedule import (
    OfficialRow, build_event, collapse_missing, enrich_existing, event_key, merge,
    match_existing, parse_detail, parse_schedule_list, propagate_ticket_scopes,
)


class DummyResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class DummySession:
    def get(self, _url, timeout=25):
        return DummyResponse('''
        <div class="block--title"><p class="tit">完全新規公演</p></div>
        <ul class="block--liveinfo">
          <li><p class="item-tit">公演日</p><p class="item-detail">2026.10.20</p></li>
          <li><p class="item-tit">開催場所・会場</p><p class="item-detail">東京都 新規ホール</p></li>
        </ul>
        <div>OPEN 17:00 / START 18:00</div>
        ''')


class OfficialScheduleTests(unittest.TestCase):
    def test_list_parses_only_live_and_event(self):
        html = '''<a href="/live_information/detail/1"><span class="block--date__month">09</span><span class="block--date__date">20</span><p class="category">EVENT</p><p class="tit">IDOL RUNWAY COLLECTION</p></a>
        <a href="/live_information/detail/2"><span class="block--date__month">09</span><span class="block--date__date">21</span><p class="category">TV</p><p class="tit">TV番組</p></a>'''
        rows = parse_schedule_list(html, "CANDY TUNE", "https://example.com", 2026, 9, date(2026, 8, 24))
        self.assertEqual(1, len(rows))
        self.assertEqual("external", rows[0].event_scope)

    def test_kawaiilab_fc_free_live_list_row_is_hosted_for_line(self):
        html = (
            '<a href="/live_information/detail/46742">'
            '<span class="block--date__month">11</span>'
            '<span class="block--date__date">06</span>'
            '<p class="category">LIVE</p>'
            '<p class="tit">KAWAII LAB. ファンクラブ限定フリーライブ</p>'
            '</a>'
        )
        rows = parse_schedule_list(
            html, "CUTIE STREET", "https://cutiestreet.asobisystem.com",
            2026, 11, date(2026, 10, 24),
        )
        self.assertEqual(1, len(rows))
        self.assertEqual("kawaii-lab", rows[0].event_scope)
        self.assertEqual("2026-11-06", rows[0].day)

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

    def test_external_schedule_row_joins_ticket_article_from_another_group(self):
        event = {
            "group": "FRUITS ZIPPER",
            "eventDate": "2027-01-19",
            "eventTitle": "2027/1/19・20開催「災害支援基金コンサート」詳細発表＆オフィシャル先行受付スタート！",
            "ticketType": "チケット受付",
            "eventScope": "external",
        }
        row = OfficialRow(
            "CANDY TUNE", "2027-01-19", "LIVE", "「災害支援基金コンサート」",
            "https://example.com/candy", "external",
        )
        matched = match_existing(row, [event])
        self.assertIs(event, matched)
        enrich_existing(matched, row, {})
        self.assertEqual("KAWAII LAB.合同", event["group"])
        self.assertEqual({"FRUITS ZIPPER", "CANDY TUNE"}, set(event["participants"]))

    def test_fifth_tour_listings_collapse_by_date_across_groups(self):
        titles = (
            "KAWAII LAB. 5th ANNIVERSARY TOUR@Kアリーナ横浜",
            "KAWAII LAB. 5th ANNIVERSARY TOUR @Kアリーナ横浜",
            "KAWAII LAB. 5th ANNIVERSARY TOUR 神奈川公演 DAY1",
        )
        groups = ("FRUITS ZIPPER", "CUTIE STREET", "MORE STAR")
        rows = [
            OfficialRow(group, "2027-02-13", "LIVE", title, f"https://example.com/{i}", "kawaii-lab")
            for i, (group, title) in enumerate(zip(groups, titles))
        ]
        collapsed = collapse_missing(rows)
        self.assertEqual(1, len(collapsed))
        combined = build_event(collapsed[0], {"venue": "神奈川県 Kアリーナ横浜"})
        self.assertEqual("KAWAII LAB.合同", combined["group"])
        self.assertEqual("kawaii-lab", combined["eventScope"])
        self.assertEqual(set(groups), set(combined["participants"]))

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

    def test_unmatched_official_schedule_row_is_automatically_added(self):
        row = OfficialRow(
            "CANDY TUNE",
            "2026-10-20",
            "LIVE",
            "完全新規公演",
            "https://example.com/live_information/detail/new",
            "kawaii-lab",
        )
        merged, diagnostics = merge({"events": []}, [row], DummySession())

        self.assertEqual(1, diagnostics["addedEvents"])
        self.assertEqual(1, len(merged["events"]))
        event = merged["events"][0]
        self.assertEqual("完全新規公演", event["title"])
        self.assertEqual("2026-10-20", event["eventDate"])
        self.assertEqual("東京都 新規ホール", event["venue"])
        self.assertEqual("17:00", event["openTime"])
        self.assertEqual("18:00", event["startTime"])
        self.assertEqual("official-schedule", event["sourceType"])


if __name__ == "__main__":
    unittest.main()
