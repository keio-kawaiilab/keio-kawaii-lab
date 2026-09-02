import unittest
from datetime import datetime

import prepare_release_candidate as prep


class PrepareReleaseCandidateTests(unittest.TestCase):
    NOW = datetime.fromisoformat("2026-08-27T19:00:00+09:00")

    def test_dedupes_same_id_and_keeps_richer_row(self):
        thin = {"id": "same", "group": "X", "title": "A", "eventDate": "2026-09-01", "sourceType": "derived"}
        rich = {
            "id": "same", "group": "X", "title": "A", "eventDate": "2026-09-01",
            "sourceType": "official-special", "venue": "Hall", "url": "https://example.com/a",
        }
        rows, removed = prep.dedupe_ids([thin, rich])
        self.assertEqual(removed, 1)
        self.assertEqual(rows[0]["sourceType"], "official-special")

    def test_schedule_only_special_is_normalized_from_official_news(self):
        event = {
            "id": "x", "group": "CANDY TUNE", "title": "大特典会", "eventCategory": "large-benefit",
            "ticketType": "現在受付なし", "applicationStatus": "none", "eventDate": "2026-09-05",
            "url": "https://candytune.asobisystem.com/news/detail/99999",
            "sourceType": "derived",
        }
        normalized, changed = prep.normalize_special(event)
        self.assertTrue(changed)
        self.assertEqual(normalized["sourceType"], "official-special")
        self.assertEqual(normalized["specialDetailsStatus"], "awaiting-details")
        self.assertEqual(normalized["applicationDisplayMode"], "schedule-only")

    def test_expired_playguide_row_is_not_retained(self):
        event = {
            "group": "CANDY TUNE", "title": "Tour", "ticketType": "抽選 プレリク",
            "ticketProvider": "eplus", "applicationStatus": "open",
            "applyEnd": "2026-08-25T23:59", "eventDate": "2026-10-01",
            "url": "https://eplus.jp/sf/detail/1",
        }
        self.assertFalse(prep.should_retain_previous(event, self.NOW.date()))

    def test_future_no_reception_row_is_retained_even_with_playguide_url(self):
        event = {
            "group": "SWEET STEADY", "title": "Festival", "ticketType": "現在受付なし",
            "applicationStatus": "none", "eventDate": "2026-10-04",
            "url": "https://eplus.jp/sf/detail/1",
        }
        self.assertTrue(prep.should_retain_previous(event, self.NOW.date()))

    def test_missing_future_official_row_is_retained_stale(self):
        old = {
            "id": "old1", "group": "SWEET STEADY", "title": "Festival",
            "ticketType": "現在受付なし", "applicationStatus": "none",
            "eventDate": "2026-10-04", "sourceType": "official-schedule",
            "url": "https://sweetsteady.asobisystem.com/live_information/detail/123",
        }
        prepared, report = prep.prepare({"events": [old]}, {"events": []}, self.NOW)
        self.assertEqual(report["retainedPreviousRows"], 1)
        self.assertTrue(prepared["events"][0]["sourceStale"])

    def test_different_ticket_providers_are_never_semantically_collapsed(self):
        base = {
            "group": "CANDY TUNE", "title": "CANDY TUNE", "ticketType": "抽選 プレリク",
            "applicationStatus": "open", "applyStart": "2026-08-21T12:00",
            "applyEnd": "2026-08-31T23:59", "eventDate": "2026-10-08",
        }
        lawson = dict(base, ticketProvider="lawson", url="https://l-tike.com/order/?gLcode=1")
        eplus = dict(base, ticketProvider="eplus", url="https://eplus.jp/sf/detail/1")
        self.assertNotEqual(prep.semantic_key(lawson), prep.semantic_key(eplus))

    def test_active_lawson_rows_survive_eplus_only_candidate(self):
        old = {
            "id": "lawson-old", "group": "CANDY TUNE", "title": "CANDY TUNE",
            "ticketType": "抽選 プレリク", "ticketProvider": "lawson", "applicationStatus": "open",
            "applyStart": "2026-08-21T12:00", "applyEnd": "2026-08-31T23:59",
            "eventDate": "2026-10-08", "url": "https://l-tike.com/order/?gLcode=1",
        }
        current = {
            "id": "eplus-current", "group": "CANDY TUNE", "title": "CANDY TUNE",
            "ticketType": "抽選 プレリク", "ticketProvider": "eplus", "applicationStatus": "open",
            "applyStart": "2026-08-21T12:00", "applyEnd": "2026-08-31T23:59",
            "eventDate": "2026-10-08", "url": "https://eplus.jp/sf/detail/1",
        }
        prepared, report = prep.prepare({"events": [old]}, {"events": [current]}, self.NOW)
        self.assertEqual(report["retainedPreviousRows"], 1)
        self.assertEqual({row.get("ticketProvider") for row in prepared["events"]}, {"lawson", "eplus"})

    def test_stale_joint_special_is_removed_after_every_group_gets_its_own_row(self):
        title = "CANDY TUNE／SWEET STEADY 発売記念大特典会"
        shared = {
            "eventCategory": "large-benefit",
            "title": title,
            "eventTitle": title,
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "eventDate": "2026-09-22",
            "venue": "東京流通センター 第二展示場Fホール",
            "startTime": "10:00",
            "sourceType": "official-special",
            "primarySource": "official",
            "specialDetailsStatus": "awaiting-details",
            "applicationDisplayMode": "schedule-only",
            "eventScope": "kawaii-lab",
        }
        stale_joint = {
            **shared,
            "id": "joint-old",
            "group": "KAWAII LAB.合同",
            "participants": ["CANDY TUNE", "SWEET STEADY"],
            "sourceStale": True,
            "url": "https://candytune.asobisystem.com/news/detail/1",
        }
        candy = {
            **shared,
            "id": "candy-current",
            "group": "CANDY TUNE",
            "url": "https://candytune.asobisystem.com/news/detail/1",
        }
        sweet = {
            **shared,
            "id": "sweet-current",
            "group": "SWEET STEADY",
            "url": "https://sweetsteady.asobisystem.com/news/detail/2",
        }

        prepared, report = prep.prepare(
            {"events": [stale_joint, candy, sweet]},
            {"events": [stale_joint, candy, sweet]},
            self.NOW,
        )

        groups = {row.get("group") for row in prepared["events"]}
        self.assertEqual({"CANDY TUNE", "SWEET STEADY"}, groups)
        self.assertNotIn("KAWAII LAB.合同", groups)
        self.assertGreaterEqual(report["supersededStaleJointRowsRemoved"], 1)

    def test_joint_special_stays_until_all_participant_rows_are_present(self):
        base = {
            "eventCategory": "large-benefit",
            "title": "合同大特典会",
            "eventDate": "2026-09-22",
            "venue": "東京流通センター",
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "sourceType": "official-special",
            "specialDetailsStatus": "awaiting-details",
            "applicationDisplayMode": "schedule-only",
            "eventScope": "kawaii-lab",
        }
        joint = {
            **base,
            "id": "joint",
            "group": "KAWAII LAB.合同",
            "participants": ["CANDY TUNE", "SWEET STEADY"],
            "sourceStale": True,
            "url": "https://candytune.asobisystem.com/news/detail/1",
        }
        candy = {
            **base,
            "id": "candy",
            "group": "CANDY TUNE",
            "url": "https://candytune.asobisystem.com/news/detail/1",
        }

        kept, dropped = prep.drop_superseded_stale_joint_specials([joint, candy])

        self.assertEqual([], dropped)
        self.assertIn("KAWAII LAB.合同", {row.get("group") for row in kept})

    def test_retained_singleton_official_x_row_is_folded_into_series(self):
        shared = "https://x.com/MORE_STAR_/status/2093324279639392675"
        title = "『サマーゴー！！/WITH KAWAII論』発売記念リリースイベント"
        aggregate = {
            "id": "aggregate",
            "group": "MORE STAR",
            "title": title,
            "eventTitle": title,
            "displayTitle": title,
            "eventCategory": "release-event",
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "eventDate": "2027-01-03",
            "eventEndDate": "2027-02-04",
            "eventDates": ["2027-01-03", "2027-02-04"],
            "eventCount": 2,
            "schedule": [
                {"date": "2027-01-03", "venue": "テラスモール松戸"},
                {"date": "2027-02-04", "venue": "animate hall BLACK"},
            ],
            "venue": "複数会場（全2公演）",
            "url": shared,
            "urls": [shared],
            "sourceType": "derived",
            "sourceChannel": "official-x",
            "primarySource": "official",
        }
        previous_singleton = {
            "id": "singleton",
            "group": "MORE STAR",
            "title": title,
            "eventTitle": title,
            "displayTitle": title,
            "eventCategory": "release-event",
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "eventDate": "2027-02-05",
            "venue": "テラスモール松戸",
            "url": shared,
            "urls": [shared],
            "sourceType": "official-social",
            "sourceChannel": "official-x",
            "primarySource": "official",
        }

        prepared, report = prep.prepare(
            {"events": [aggregate, previous_singleton]},
            {"events": [aggregate]},
            self.NOW,
        )

        self.assertEqual(1, len(prepared["events"]))
        merged = prepared["events"][0]
        # Canonical public entities intentionally get a deterministic `special-*`
        # ID. Identity is the real event, not whichever source row happened to be
        # selected as the representative during this refresh.
        self.assertEqual("special-event", merged["entityType"])
        self.assertTrue(str(merged["id"]).startswith("special-"))
        self.assertEqual("2027-02-05", merged["eventEndDate"])
        self.assertIn("2027-02-05", merged["eventDates"])
        self.assertEqual("official-social", merged["sourceType"])
        self.assertEqual("official-x", merged["sourceChannel"])
        self.assertEqual("official", merged["primarySource"])
        self.assertEqual("awaiting-details", merged["specialDetailsStatus"])
        self.assertEqual("schedule-only", merged["applicationDisplayMode"])
        self.assertEqual(1, report["officialXRowsCollapsed"])
        self.assertEqual(0, report["physicalEventInvariant"]["remainingDuplicateCount"])

    def test_observation_clock_only_does_not_advance_public_updated_at(self):
        previous = {
            "updatedAt": "2026-08-27T18:00:00+09:00",
            "events": [{
                "id": "same",
                "group": "CANDY TUNE",
                "title": "Tour",
                "eventDate": "2026-10-01",
                "sourceObservedAt": "2026-08-27T18:00:00+09:00",
            }],
        }
        candidate = {
            "events": [{
                "id": "same",
                "group": "CANDY TUNE",
                "title": "Tour",
                "eventDate": "2026-10-01",
                "sourceObservedAt": "2026-08-27T19:00:00+09:00",
            }],
        }
        prepared, report = prep.prepare(previous, candidate, self.NOW)
        self.assertFalse(report["eventPayloadChanged"])
        self.assertEqual("2026-08-27T18:00:00+09:00", prepared["updatedAt"])
        self.assertEqual("2026-08-27T19:00:00+09:00", prepared["checkedAt"])

    def test_real_event_change_advances_public_updated_at(self):
        previous = {
            "updatedAt": "2026-08-27T18:00:00+09:00",
            "events": [{
                "id": "same",
                "group": "CANDY TUNE",
                "title": "Tour",
                "eventDate": "2026-10-01",
                "venue": "Old Hall",
            }],
        }
        candidate = {
            "events": [{
                "id": "same",
                "group": "CANDY TUNE",
                "title": "Tour",
                "eventDate": "2026-10-01",
                "venue": "New Hall",
            }],
        }
        prepared, report = prep.prepare(previous, candidate, self.NOW)
        self.assertTrue(report["eventPayloadChanged"])
        self.assertEqual("2026-08-27T19:00:00+09:00", prepared["updatedAt"])
        self.assertEqual("2026-08-27T19:00:00+09:00", prepared["checkedAt"])


if __name__ == "__main__":
    unittest.main()
