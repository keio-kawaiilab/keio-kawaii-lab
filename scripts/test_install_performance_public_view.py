import unittest
from datetime import date

import install_performance_public_view as public_view


class CurrentTicketOfferGuardTests(unittest.TestCase):
    def test_performance_offer_is_rendered_exactly_once(self):
        event = {
            "id": "performance", "entityType": "performance", "group": "FRUITS ZIPPER",
            "eventTitle": "Test Live", "eventDate": "2099-11-08", "venue": "Test Hall",
            "offers": [{
                "ticketType": "FC先行", "ticketProvider": "official",
                "applyStart": "2099-10-01T12:00", "applyEnd": "2099-11-07T23:59",
                "url": "https://example.com/ticket",
            }],
        }
        card = public_view._build_public_card(event)
        self.assertEqual(1, card.count('class="ticket-options"'))
        self.assertEqual(1, card.count("FC先行"))

    def test_performance_without_offer_gets_one_empty_state(self):
        event = {
            "id": "performance", "entityType": "performance", "group": "FRUITS ZIPPER",
            "eventTitle": "Test Live", "eventDate": "2099-11-08", "venue": "Test Hall",
            "offers": [],
        }
        card = public_view._build_public_card(event)
        self.assertEqual(1, card.count('class="no-ticket"'))

    def test_requires_offer_through_event_day(self):
        event = {"eventDate": "2026-10-08"}
        self.assertTrue(public_view._requires_current_ticket_offer(event, date(2026, 10, 8)))

    def test_does_not_require_offer_after_event_day(self):
        event = {"eventDate": "2026-10-08"}
        self.assertFalse(public_view._requires_current_ticket_offer(event, date(2026, 10, 9)))

    def test_warning_scope_is_stable_for_replacement(self):
        self.assertEqual(
            "CANDY TUNE tour render verification",
            public_view.TOUR_RENDER_WARNING_SCOPE,
        )


if __name__ == "__main__":
    unittest.main()
