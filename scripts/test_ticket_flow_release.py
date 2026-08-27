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

    def test_flow_is_fail_closed_on_collection_health(self):
        self.assertIn('health.safeForTicketFlowPublication!==true', JS)
        self.assertIn('health.status!=="healthy"', JS)
        self.assertIn('MAX_HEALTH_AGE_MS', JS)
        self.assertIn('ticket-collection-health.json', JS)

    def test_flow_uses_permanent_verified_history(self):
        self.assertIn('ticket-history.json', JS)
        self.assertIn('row.publishable!==true', JS)
        self.assertIn('row.flowEligible!==true', JS)
        self.assertIn('windowCompleteness', JS)

    def test_flow_is_additive_after_existing_ticket_area(self):
        self.assertIn('card.querySelector(".ticket-options")||card.querySelector(".no-ticket")', JS)
        self.assertIn('anchor.insertAdjacentHTML("afterend",flowHtml(rows))', JS)
        self.assertIn('<details class="ticket-flow">', JS)

    def test_unknown_future_is_never_invented(self):
        self.assertIn('この先の販売情報は未発表です。新しい受付が公式発表された場合だけ追加します。', JS)
        self.assertNotIn('FC先行 →', JS)
        self.assertNotIn('一般販売 →', JS)

    def test_loader_is_isolated_to_schedule(self):
        self.assertIn('document.getElementById("calendar")', LOADER)
        self.assertIn('document.getElementById("cards")', LOADER)
        self.assertIn('ticket-flow.css', LOADER)
        self.assertIn('ticket-flow.js', LOADER)


if __name__ == "__main__":
    unittest.main()
