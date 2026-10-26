import unittest
from datetime import date

import install_performance_public_view as public_view


class CurrentTicketOfferGuardTests(unittest.TestCase):
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
