#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone

from audit_schedule_release import audit

NOW = datetime(2026, 8, 23, 13, 30, tzinfo=timezone.utc)


def base_pia(**changes):
    event = {
        "id": "pia-1",
        "group": "CANDY TUNE",
        "title": "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
        "ticketType": "プレリザーブ",
        "applyStart": "2026-08-20T10:00",
        "applyEnd": "2026-08-25T23:59",
        "eventDate": "2026-11-10",
        "eventDates": ["2026-11-10", "2026-11-12"],
        "url": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=12345",
        "urls": ["https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=12345"],
        "sourceType": "pia",
        "primarySource": "pia",
        "applicationStatus": "open",
        "applicationWindowVerified": True,
        "deadlineVerified": True,
        "applicationDisplayMode": "band",
        "applicationWindowSource": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=12345",
        "deadlineSource": "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=12345",
    }
    event.update(changes)
    return event


def payload(events):
    return {"updatedAt": "2026-08-23T22:30:00+09:00", "events": events}


class AuditScheduleReleaseTests(unittest.TestCase):
    def test_unchanged_good_release_passes(self):
        old = payload([base_pia()])
        errors, warnings, report = audit(old, copy.deepcopy(old), NOW)
        self.assertEqual([], errors)
        self.assertEqual("ok", report["status"])

    def test_active_future_item_cannot_disappear(self):
        old = payload([base_pia()])
        errors, _, _ = audit(old, payload([]), NOW)
        self.assertTrue(any("disappeared" in error for error in errors))

    def test_deadline_moving_earlier_is_blocked(self):
        old = payload([base_pia()])
        new = payload([base_pia(applyEnd="2026-08-24T11:00")])
        errors, _, _ = audit(old, new, NOW)
        self.assertTrue(any("deadline moved earlier" in error for error in errors))

    def test_verified_deadline_extension_is_allowed(self):
        old = payload([base_pia()])
        new = payload([base_pia(applyEnd="2026-08-27T23:59")])
        errors, warnings, _ = audit(old, new, NOW)
        self.assertEqual([], errors)
        self.assertTrue(any("deadline extended" in warning for warning in warnings))

    def test_duplicate_pia_lot_is_blocked(self):
        first = base_pia(id="a")
        second = base_pia(id="b")
        errors, _, _ = audit(payload([]), payload([first, second]), NOW)
        self.assertTrue(any("duplicate Pia lot" in error for error in errors))

    def test_reversed_application_window_is_blocked(self):
        event = base_pia(applyStart="2026-08-26T10:00", applyEnd="2026-08-25T23:59")
        errors, _, _ = audit(payload([]), payload([event]), NOW)
        self.assertTrue(any("application window reversed" in error for error in errors))

    def test_pia_fc_or_upgrade_is_blocked(self):
        event = base_pia(ticketType="FC先行")
        errors, _, _ = audit(payload([]), payload([event]), NOW)
        self.assertTrue(any("FC/upgrade-only" in error for error in errors))

    def test_online_sale_requires_sukisuki_product_url(self):
        event = {
            "id": "online-1",
            "group": "CANDY TUNE",
            "title": "CANDY TUNE オンライン特典会",
            "ticketType": "オンライン特典会・先着販売",
            "applyStart": "2026-08-23T20:00",
            "applyEnd": "2026-08-24T12:00",
            "eventDate": "2026-08-24",
            "url": "https://example.com/not-sukisuki",
            "eventCategory": "online-benefit",
            "applicationStatus": "open",
        }
        errors, _, _ = audit(payload([]), payload([event]), NOW)
        self.assertTrue(any("no SUKISUKI product URL" in error for error in errors))

    def test_future_performance_date_cannot_silently_vanish(self):
        old = payload([base_pia(eventDates=["2026-11-10", "2026-11-12"])])
        new = payload([base_pia(eventDates=["2026-11-10"])])
        errors, _, _ = audit(old, new, NOW)
        self.assertTrue(any("performance dates disappeared" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
