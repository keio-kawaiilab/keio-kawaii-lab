#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone

from audit_schedule_release_grouped import audit_grouped, repair_local_errors

NOW = datetime(2026, 8, 27, 4, 0, tzinfo=timezone.utc)
SOURCE = "https://x.com/MORE_STAR_/status/2092567739969966299"


def event(event_id: str, day: str, title: str, group: str = "MORE STAR") -> dict:
    return {
        "id": event_id,
        "group": group,
        "eventScope": "kawaii-lab",
        "title": title,
        "eventTitle": title,
        "ticketType": "現在受付なし",
        "applicationStatus": "none",
        "eventDate": day,
        "venue": "公演会場",
        "url": SOURCE,
        "urls": [SOURCE],
        "sourceType": "official-social",
        "primarySource": "official",
    }


def payload(events: list[dict]) -> dict:
    return {"updatedAt": "2026-08-27T13:00:00+09:00", "events": events}


class GroupedReleaseAuditTests(unittest.TestCase):
    def test_unchanged_shared_announcement_dates_do_not_false_fail(self):
        rows = [
            event("5th", "2026-09-24", "MORE STAR 単独ライブ 5th STAR"),
            event("6th", "2026-10-21", "MORE STAR 単独ライブ 6th STAR"),
            event("7th", "2026-11-12", "MORE STAR 単独ライブ 7th STAR"),
        ]
        errors, warnings, report = audit_grouped(payload(rows), payload(copy.deepcopy(rows)), NOW)
        self.assertEqual([], errors)
        self.assertFalse(any("performance dates added" in item for item in warnings))
        self.assertIn("url:" + SOURCE, report["sharedSourceDateSetsReconciled"])

    def test_new_date_on_same_multi_event_x_post_keeps_existing_dates_safe(self):
        title = "『サマーゴー！！/WITH KAWAII論』発売記念リリースイベント"
        old_rows = [
            event("feb3", "2027-02-03", title),
            event("feb4", "2027-02-04", title),
        ]
        new_rows = [
            copy.deepcopy(old_rows[0]),
            copy.deepcopy(old_rows[1]),
            event("feb5", "2027-02-05", title),
        ]
        errors, warnings, report = audit_grouped(payload(old_rows), payload(new_rows), NOW)
        self.assertEqual([], errors)
        self.assertFalse(any("2027-02-04" in item and "disappeared" in item for item in errors))
        self.assertTrue(any("2027-02-05" in item and "performance dates added" in item for item in warnings))
        self.assertIn("url:" + SOURCE, report["officialXSharedSourceKeysReconciled"])

    def test_single_event_x_date_change_still_blocks_strict_audit(self):
        title = "MORE STAR リリースイベント"
        old_rows = [event("old", "2027-02-04", title)]
        new_rows = [event("new", "2027-02-03", title)]
        errors, _, report = audit_grouped(payload(old_rows), payload(new_rows), NOW)
        self.assertTrue(any("disappeared" in item for item in errors))
        self.assertEqual("blocked", report["status"])

    def test_real_missing_date_still_blocks_strict_audit(self):
        old_rows = [
            event("5th", "2026-09-24", "MORE STAR 単独ライブ 5th STAR"),
            event("6th", "2026-10-21", "MORE STAR 単独ライブ 6th STAR"),
            event("7th", "2026-11-12", "MORE STAR 単独ライブ 7th STAR"),
        ]
        new_rows = [copy.deepcopy(old_rows[0]), copy.deepcopy(old_rows[1])]
        errors, _, report = audit_grouped(payload(old_rows), payload(new_rows), NOW)
        self.assertTrue(any("disappeared" in item for item in errors))
        self.assertEqual("blocked", report["status"])

    def test_other_group_cannot_mask_a_missing_date(self):
        old_rows = [
            event("more-a", "2026-09-24", "MORE STAR LIVE A"),
            event("more-b", "2026-10-21", "MORE STAR LIVE B"),
            event("other", "2026-10-21", "CANDY TUNE LIVE", group="CANDY TUNE"),
        ]
        new_rows = [copy.deepcopy(old_rows[0]), copy.deepcopy(old_rows[2])]
        errors, _, _ = audit_grouped(payload(old_rows), payload(new_rows), NOW)
        self.assertTrue(any("disappeared" in item for item in errors))

    def test_release_repair_restores_bad_source_but_keeps_unrelated_fresh_event(self):
        title = "MORE STAR リリースイベント"
        old = event("old", "2027-02-04", title)
        changed = event("new", "2027-02-03", title)
        unrelated = event("fresh", "2026-12-20", "新しい別公演")
        other_source = "https://morestar.asobisystem.com/live_information/detail/99999"
        unrelated["url"] = other_source
        unrelated["urls"] = [other_source]
        unrelated["sourceType"] = "official"

        repaired, errors, _, report, actions = repair_local_errors(
            payload([old]), payload([changed, unrelated]), NOW
        )

        ids = {row["id"] for row in repaired["events"]}
        self.assertEqual([], errors)
        self.assertIn("old", ids)
        self.assertIn("fresh", ids)
        self.assertNotIn("new", ids)
        self.assertGreaterEqual(len(actions), 1)
        self.assertEqual("ok", report["status"])

    def test_release_repair_withholds_bad_brand_new_row_only(self):
        stable = event("stable", "2026-09-24", "既存公演")
        bad = event("bad-new", "2026-10-01", "新規だが壊れた公演")
        bad["eventScope"] = ""
        other_source = "https://morestar.asobisystem.com/live_information/detail/88888"
        bad["url"] = other_source
        bad["urls"] = [other_source]
        bad["sourceType"] = "official"

        repaired, errors, _, _, actions = repair_local_errors(
            payload([stable]), payload([copy.deepcopy(stable), bad]), NOW
        )

        ids = {row["id"] for row in repaired["events"]}
        self.assertEqual([], errors)
        self.assertEqual({"stable"}, ids)
        self.assertGreaterEqual(len(actions), 1)

    def test_release_repair_downgrades_unchanged_legacy_special_row(self):
        title = "『サマーゴー！！/WITH KAWAII論』発売記念リリースイベント"
        legacy = event("legacy-special", "2026-09-10", title)
        legacy["eventCategory"] = "release-event"
        legacy["url"] = ""
        legacy["urls"] = []
        legacy["sourceType"] = "legacy-import"
        legacy["primarySource"] = "legacy"

        fresh = event("fresh", "2026-12-20", "新しい別公演")
        fresh_source = "https://morestar.asobisystem.com/live_information/detail/77777"
        fresh["url"] = fresh_source
        fresh["urls"] = [fresh_source]
        fresh["sourceType"] = "official"

        previous = payload([legacy])
        candidate = payload([copy.deepcopy(legacy), fresh])
        repaired, errors, warnings, report, actions = repair_local_errors(previous, candidate, NOW)

        ids = {row["id"] for row in repaired["events"]}
        self.assertEqual([], errors)
        self.assertEqual({"legacy-special", "fresh"}, ids)
        self.assertEqual([], actions)
        self.assertEqual("ok", report["status"])
        self.assertGreater(report.get("legacyProtectedErrorCount", 0), 0)
        self.assertTrue(any("protected unchanged last-good row" in item for item in warnings))

    def test_release_repair_keeps_global_integrity_failure_blocking(self):
        stable = event("stable", "2026-09-24", "既存公演")
        previous = payload([stable])
        candidate = payload([copy.deepcopy(stable)])
        candidate["updatedAt"] = "not-a-date"

        _, errors, _, report, actions = repair_local_errors(previous, candidate, NOW)

        self.assertTrue(any("candidate updatedAt is invalid" in item for item in errors))
        self.assertEqual([], actions)
        self.assertEqual("blocked", report["status"])


if __name__ == "__main__":
    unittest.main()
