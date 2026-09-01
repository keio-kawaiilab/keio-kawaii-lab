import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import import_odpt_timetables as importer


class ImportOdptTimetablesTests(unittest.TestCase):
    def test_compact_entity_keeps_route_fields(self):
        compact = importer.compact_entity({
            "owl:sameAs": "odpt.Station:Test.A",
            "odpt:connectingRailway": ["odpt.Railway:Test.B"],
            "odpt:connectingStation": ["odpt.Station:Test.B"],
            "odpt:color": "#123456",
            "ignored": "value",
        })
        self.assertEqual(compact["odpt:color"], "#123456")
        self.assertIn("odpt:connectingRailway", compact)
        self.assertNotIn("ignored", compact)

    def test_topology_is_published_without_timetables(self):
        target = {
            "test": {
                "label": "テスト鉄道",
                "aliases": ["Test"],
                "fallback": "odpt.Operator:Test",
                "license": "test",
            }
        }
        station = {
            "owl:sameAs": "odpt.Station:Test.A",
            "odpt:operator": "odpt.Operator:Test",
            "odpt:railway": "odpt.Railway:Test.Main",
            "odpt:stationTitle": {"ja": "A"},
        }
        railway = {
            "owl:sameAs": "odpt.Railway:Test.Main",
            "odpt:operator": "odpt.Operator:Test",
            "odpt:railwayTitle": {"ja": "本線"},
            "odpt:stationOrder": [{"odpt:index": 1, "odpt:station": station["owl:sameAs"]}],
        }

        def fake_get(_session, rdf_type, _key, _operator=None):
            return {
                "odpt:Station": [station],
                "odpt:Railway": [railway],
                "odpt:TrainType": [],
                "odpt:RailDirection": [],
                "odpt:StationTimetable": [],
                "odpt:TrainTimetable": [],
            }.get(rdf_type, [])

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", {"ODPT_API_KEY": "secret"}, clear=True), patch.object(importer, "OUT_ROOT", Path(temp_dir)), patch.object(importer, "TARGETS", target), patch.object(importer, "discover_operators", return_value=({"test": "odpt.Operator:Test"}, [])), patch.object(importer, "api_get", side_effect=fake_get):
            self.assertEqual(importer.main(), 0)
            manifest = json.loads((Path(temp_dir) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["operators"]["test"]["status"], "ok")
            self.assertEqual(manifest["operators"]["test"]["timetableStatus"], "not-available")
            self.assertTrue((Path(temp_dir) / "test" / "entities.json").exists())


if __name__ == "__main__":
    unittest.main()
