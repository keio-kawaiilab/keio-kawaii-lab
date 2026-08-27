#!/usr/bin/env python3
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "ticket-flow.js").read_text(encoding="utf-8")
CSS = (ROOT / "ticket-flow.css").read_text(encoding="utf-8")
LOADER = (ROOT / "going-highlight-soften.js").read_text(encoding="utf-8")


class TicketFlowReleaseTests(unittest.TestCase):
    def test_existing_ticket_card_styles_are_not_overridden(self):
        forbidden = (
            ".ticket-options{",
            ".ticket-option{",
            ".provider{",
            ".ticket-copy{",
            ".ticket-link{",
            ".sale-state{",
        )
        for selector in forbidden:
            self.assertNotIn(selector, CSS, selector)

    def test_degraded_collection_does_not_hide_verified_rows(self):
        self.assertIn('collectionState()', JS)
        self.assertIn('一部の情報源を現在確認できていないため、履歴に抜けがある可能性があります。', JS)
        self.assertIn('Promise.all([historyRequest,healthRequest])', JS)
        self.assertNotIn('if(!freshHealth(health))return null', JS)

    def test_flow_uses_permanent_verified_history(self):
        self.assertIn('ticket-history.json', JS)
        self.assertIn('row.publishable!==true', JS)
        self.assertIn('row.flowEligible!==true', JS)
        self.assertIn('windowCompleteness', JS)
        self.assertIn('safeSourceUrl(row.sourceUrl)', JS)

    def test_every_normal_live_card_gets_an_additive_tab(self):
        self.assertIn('isNormalLiveCard(card)', JS)
        self.assertIn('card.classList.contains("release-card")', JS)
        self.assertIn('card.classList.contains("benefit-card")', JS)
        self.assertIn('card.classList.contains("online-card")', JS)
        self.assertNotIn('if(!rows.length)return', JS)
        self.assertIn('card.querySelector(".ticket-options")||card.querySelector(".no-ticket")', JS)
        self.assertIn('anchor.insertAdjacentHTML("afterend",flowHtml(safeRowsForCard(card)))', JS)
        self.assertIn('<details class="ticket-flow">', JS)

    def test_missing_history_is_explicit_not_invented(self):
        self.assertIn('販売がなかったことを意味するものではありません。', JS)
        self.assertIn('未発表・未確認の販売段階は予測していません。', JS)
        self.assertNotIn('FC先行 →', JS)
        self.assertNotIn('一般販売 →', JS)

    def test_ended_end_only_history_has_clean_period_text(self):
        self.assertIn('fmt(row.applyEnd)+" 受付終了"', JS)
        self.assertIn('"受付中・予定"', JS)
        self.assertIn('"受付状況未確認"', JS)

    def test_loader_is_isolated_to_schedule(self):
        self.assertIn('document.getElementById("calendar")', LOADER)
        self.assertIn('document.getElementById("cards")', LOADER)
        self.assertIn('ticket-flow.css', LOADER)
        self.assertIn('ticket-flow.js', LOADER)


if __name__ == "__main__":
    unittest.main()
