import unittest

from audit_official_schedule_coverage import audit


class CoverageAuditTests(unittest.TestCase):
    def fixture(self):
        event = {
            "id": "event-1", "group": "CANDY TUNE", "title": "TOUR",
            "eventDate": "2026-09-04", "eventScope": "kawaii-lab",
            "url": "https://candytune.asobisystem.com/live_information/detail/1",
        }
        entry = {
            "group": "CANDY TUNE", "date": "2026-09-04", "title": "TOUR",
            "eventScope": "kawaii-lab", "url": event["url"], "representedBy": "event-1",
        }
        groups = {group: {"count": 1} for group in (
            "FRUITS ZIPPER", "CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR",
        )}
        return {"events": [event]}, {"groups": groups, "entries": [entry]}

    def test_complete_index_passes(self):
        data, index = self.fixture()
        self.assertEqual([], audit(data, index))

    def test_missing_representation_blocks(self):
        data, index = self.fixture()
        index["entries"][0]["representedBy"] = "missing"
        self.assertTrue(audit(data, index))

    def test_special_row_without_special_category_blocks(self):
        data, index = self.fixture()
        index["entries"][0]["title"] = "FRUITS ZIPPER 大特典会"
        self.assertTrue(any("wrong category" in value for value in audit(data, index)))


if __name__ == "__main__":
    unittest.main()
