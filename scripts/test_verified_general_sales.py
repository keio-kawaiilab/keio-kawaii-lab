import json
import unittest
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from performance_entities import build_public_events
from verified_general_sales import apply_verified_general_sales, REGISTRY
from promoter_general_sale_guard import parse_known_performance, extract_general_sale, merge
from fix_missing_application_start_ui import _patch_static_ticket_option

class GeneralSalesTest(unittest.TestCase):
    def setUp(self):
        self.observations = json.loads(REGISTRY.read_text())['observations']
        self.raw = [dict(id=r['id']+'-show',group=r['group'],eventDate=r['eventDate'],startTime=r['startTime'],title=r['titleContains'],eventScope='kawaii-lab',ticketType='現在受付なし',venue='東京都 Zepp Shinjuku(TOKYO)' if r['group']=='SWEET STEADY' else '東京都 有明アリーナ') for r in self.observations]

    def test_five_offers_preserve_performance_count_and_survive_rebuild(self):
        public, _ = build_public_events(self.raw)
        before = len(public)
        apply_verified_general_sales(public, self.observations)
        self.assertEqual(len(public), before)
        once = deepcopy(public)
        apply_verified_general_sales(public, self.observations)
        self.assertEqual(once, public)
        for row in self.observations:
            matches = [e for e in public if e.get('group') == row['group'] and e.get('eventDate') == row['eventDate'] and e.get('startTime') == row['startTime']]
            self.assertEqual(len(matches), 1)
            offer = next(o for o in matches[0]['offers'] if o.get('sourceRowId') == row['id'])
            self.assertEqual(offer['applyStart'], '2026-09-12T10:00')
            self.assertEqual(offer['applyEnd'], row['offer']['applyEnd'])

    def test_newer_pia_observation_is_not_overwritten(self):
        public, _ = build_public_events(self.raw)
        apply_verified_general_sales(public, self.observations)
        event = next(e for e in public if e.get('group') == 'SWEET STEADY' and e.get('startTime') == '14:00' and e.get('eventDate') == '2026-09-21')
        offer = event['offers'][-1]
        offer.update(applicationStatus='open', sourceObservedAt='2026-09-15T10:00:00+09:00')
        apply_verified_general_sales(public, self.observations)
        self.assertEqual(offer['applicationStatus'], 'open')

    def test_regular_promoter_show_and_sale_section(self):
        public, _ = build_public_events(self.raw)
        html = '<nav>一般発売</nav>' + '<p>navigation</p>' * 100 + '''
        <h3>SWEET STEADY</h3><p>お花見会 第一回</p><p>2026年9月21日</p>
        <a href="../venue/detail.php?id=1">Zepp Shinjuku (TOKYO)</a>
        <p>OPEN 13:00 START 14:00</p><h4>発売情報</h4><p>一般発売 9/12(土)10:00〜</p>
        <h4>券種・料金</h4><p>優先 FC限定 8,000円</p><h4>関連公演</h4><p>CUTIE STREET 2026年9月29日 START 18:00</p>'''
        show = parse_known_performance(html, public, date(2026,9,14))
        self.assertEqual(show['startTime'], '14:00')
        sale = extract_general_sale(BeautifulSoup(html, 'html.parser'), show['eventDate'], 'https://www.red-hot.ne.jp/')
        self.assertEqual(sale['applyStart'], '2026-09-12T10:00')
        self.assertIsNone(parse_known_performance(html.replace('START 14:00','START 15:00'), public, date(2026,9,14)))

    def test_promoter_merge_keeps_daytime_and_evening_sales_separate(self):
        rows = [dict(id=t,group='SWEET STEADY',eventDate='2026-09-21',startTime=t,ticketType='一般発売') for t in ['14:00','17:30']]
        payload={'events': []}
        self.assertEqual(merge(payload, rows), (2,0))
        self.assertEqual(len(payload['events']), 2)

    def test_sold_out_static_sale_is_hidden(self):
        block='<div class="ticket-option" data-sale-status="sold_out"><span class="ticket-copy"><b>一般発売</b><small>2026/9/12 10:00〜</small></span><a class="ticket-link" href="https://t.pia.jp/">申込先 →</a></div>'
        html=_patch_static_ticket_option(block, datetime(2026,9,14,tzinfo=ZoneInfo('Asia/Tokyo')))
        self.assertEqual(html, '')

    def test_expired_static_offer_is_hidden_but_future_offer_remains(self):
        template='<div class="ticket-option"><span class="ticket-copy"><b>FC先行</b><small>{}</small></span><a class="ticket-link" href="https://example.com/">申込先 →</a></div>'
        now=datetime(2026,9,14,tzinfo=ZoneInfo('Asia/Tokyo'))
        self.assertEqual(_patch_static_ticket_option(template.format('2026/7/23 12:00〜2026/7/26 23:59'),now),'')
        self.assertIn('受付予定',_patch_static_ticket_option(template.format('2026/9/15 12:00〜2026/9/20 23:59'),now))

if __name__ == '__main__': unittest.main()
