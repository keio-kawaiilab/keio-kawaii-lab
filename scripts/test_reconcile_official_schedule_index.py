import unittest

from reconcile_official_schedule_index import reconcile


class ReconcileOfficialScheduleIndexTests(unittest.TestCase):
    def test_joint_free_live_projects_group_specific_official_links_for_line(self):
        day = "2026-11-06"
        official = {
            "CANDY TUNE": "https://candytune.asobisystem.com/news/detail/93706",
            "SWEET STEADY": "https://sweetsteady.asobisystem.com/news/detail/93708",
            "MORE STAR": "https://morestar.asobisystem.com/news/detail/93710",
        }
        cutie = "https://cutiestreet.asobisystem.com/live_information/detail/46742"
        data = {"events": [{
            "id": "joint", "group": "KAWAII LAB.合同",
            "participants": ["CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR"],
            "title": "KAWAII LAB. ファンクラブ限定フリーライブ",
            "eventDate": day, "eventScope": "kawaii-lab",
            "url": "https://kawaiilab.asobisystem.com/news/detail/93695",
            "urls": [cutie, *official.values()],
        }]}
        index = {"entries": [{
            "group": "CUTIE STREET", "date": day, "category": "LIVE",
            "title": data["events"][0]["title"], "url": cutie,
            "eventScope": "kawaii-lab", "representedBy": "joint",
        }]}
        first = reconcile(data, index)
        self.assertEqual(3, first["projectedJointParticipantCount"])
        self.assertEqual(
            {"CUTIE STREET", *official.keys()},
            {row["group"] for row in index["entries"]},
        )
        self.assertTrue(all(
            row["url"] == official[row["group"]]
            for row in index["entries"] if row["group"] in official
        ))
        second = reconcile(data, index)
        self.assertEqual(0, second["projectedJointParticipantCount"])
        self.assertEqual(4, len(index["entries"]))

    def test_joint_projection_never_invents_official_group_urls(self):
        data = {"events": [{
            "id": "joint", "group": "KAWAII LAB.合同",
            "participants": ["CANDY TUNE", "CUTIE STREET"],
            "eventDate": "2026-11-06", "eventScope": "kawaii-lab",
            "url": "https://cutiestreet.asobisystem.com/live_information/detail/46742",
        }]}
        entry = {
            "group": "CUTIE STREET", "date": "2026-11-06",
            "category": "LIVE", "eventScope": "kawaii-lab",
            "url": data["events"][0]["url"], "representedBy": "joint",
        }
        index = {"entries": [entry]}
        self.assertEqual(0, reconcile(data, index)["projectedJointParticipantCount"])
        self.assertEqual([entry], index["entries"])

    def test_reconnects_same_official_event_after_richer_row_changes_id(self):
        official_url = "https://sweetsteady.asobisystem.com/live_information/detail/43898"
        data = {
            "events": [{
                "id": "rich-special-id",
                "group": "SWEET STEADY",
                "eventDate": "2026-09-06",
                "url": "https://sweetsteady.asobisystem.com/news/detail/88152",
                "urls": [official_url],
                "officialScheduleUrl": official_url,
            }]
        }
        index = {
            "entries": [{
                "group": "SWEET STEADY",
                "date": "2026-09-06",
                "url": official_url,
                "representedBy": "old-core-id",
            }]
        }

        report = reconcile(data, index)

        self.assertEqual(index["entries"][0]["representedBy"], "rich-special-id")
        self.assertEqual(report["reassignedCount"], 1)
        self.assertEqual(report["hydratedCount"], 0)
        self.assertEqual(report["ambiguousCount"], 0)
        self.assertEqual(report["unresolvedCount"], 0)

    def test_hydrates_missing_official_url_on_existing_represented_event(self):
        official_url = "https://candytune.asobisystem.com/live_information/detail/44452"
        data = {
            "events": [{
                "id": "special-a91f4fd0f80a1f20",
                "group": "CANDY TUNE",
                "eventDate": "2026-09-01",
                "title": "4th single リリースイベント",
                "eventScope": "kawaii-lab",
                "url": "https://candytune.asobisystem.com/news/detail/other",
            }]
        }
        index = {
            "entries": [{
                "group": "CANDY TUNE",
                "date": "2026-09-01",
                "title": "4th single リリースイベント",
                "eventScope": "kawaii-lab",
                "url": official_url,
                "representedBy": "special-a91f4fd0f80a1f20",
            }]
        }

        report = reconcile(data, index)

        self.assertEqual(data["events"][0]["officialScheduleUrl"], official_url)
        self.assertEqual(report["hydratedCount"], 1)
        self.assertEqual(report["unresolvedCount"], 0)

    def test_does_not_hydrate_when_scope_disagrees(self):
        official_url = "https://example.com/live/1"
        data = {"events": [{
            "id": "one",
            "group": "SWEET STEADY",
            "eventDate": "2026-09-06",
            "eventScope": "external",
        }]}
        index = {"entries": [{
            "group": "SWEET STEADY",
            "date": "2026-09-06",
            "eventScope": "kawaii-lab",
            "url": official_url,
            "representedBy": "one",
        }]}

        report = reconcile(data, index)

        self.assertNotIn("officialScheduleUrl", data["events"][0])
        self.assertEqual(report["hydratedCount"], 0)
        self.assertEqual(report["unresolvedCount"], 1)

    def test_does_not_guess_when_two_final_events_match(self):
        official_url = "https://example.com/live/1"
        base = {
            "group": "SWEET STEADY",
            "eventDate": "2026-09-06",
            "url": official_url,
        }
        data = {"events": [{**base, "id": "one"}, {**base, "id": "two"}]}
        index = {"entries": [{
            "group": "SWEET STEADY",
            "date": "2026-09-06",
            "url": official_url,
            "representedBy": "missing",
        }]}

        report = reconcile(data, index)

        self.assertEqual(index["entries"][0]["representedBy"], "missing")
        self.assertEqual(report["reassignedCount"], 0)
        self.assertEqual(report["ambiguousCount"], 1)

    def test_leaves_missing_row_for_fail_closed_audit(self):
        index = {"entries": [{
            "group": "SWEET STEADY",
            "date": "2026-09-06",
            "url": "https://example.com/live/missing",
            "representedBy": "missing",
        }]}

        report = reconcile({"events": []}, index)

        self.assertEqual(index["entries"][0]["representedBy"], "missing")
        self.assertEqual(report["unresolvedCount"], 1)


if __name__ == "__main__":
    unittest.main()