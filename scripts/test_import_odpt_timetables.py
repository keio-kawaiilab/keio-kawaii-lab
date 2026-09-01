import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import import_odpt_timetables as importer


class ImportOdptTimetablesTests(unittest.TestCase):
    def test_challenge_operators_use_the_challenge_api(self):
        self.assertEqual(
            importer.api_base_for({"license": "challenge-2026"}),
            importer.CHALLENGE_BASE_URL,
        )
        self.assertEqual(importer.api_base_for({"license": "basic"}), importer.BASE_URL)
        self.assertEqual(
            importer.api_key_for({"license": "challenge-2026"}, "standard", "challenge"),
            "challenge",
        )
        self.assertEqual(importer.api_key_for({"license": "basic"}, "standard", "challenge"), "standard")

    def test_jr_east_import_is_enabled_by_default_and_can_be_paused(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertTrue(importer.jr_east_import_enabled())
        with patch.dict("os.environ", {"ALLOW_JR_EAST_CHALLENGE_DATA": "0"}, clear=True):
            self.assertFalse(importer.jr_east_import_enabled())

    def test_operator_discovery_prefers_exact_railway_uri_over_substrings(self):
        operators = [
            {
                "owl:sameAs": "odpt.Operator:Toei",
                "odpt:operatorTitle": {"en": "Bureau of Transportation, Tokyo Metropolitan Government"},
            },
            {
                "owl:sameAs": "odpt.Operator:TokyoMetro",
                "odpt:operatorTitle": {"ja": "東京メトロ"},
            },
            {
                "owl:sameAs": "odpt.Operator:SeibuBus",
                "odpt:operatorTitle": {"en": "Seibu Bus"},
            },
        ]
        with patch.object(importer, "api_get", return_value=operators):
            found, _rows = importer.discover_operators(object(), "secret")
        self.assertEqual(found["tokyo-metro"], "odpt.Operator:TokyoMetro")
        self.assertEqual(found["toei"], "odpt.Operator:Toei")
        self.assertEqual(found["seibu"], "odpt.Operator:Seibu")

    def test_api_get_filters_an_unscoped_response_by_operator(self):
        class Response:
            status_code = 200
            headers = {}

            def raise_for_status(self):
                return None

            def json(self):
                return [
                    {"owl:sameAs": "station:a", "odpt:operator": "odpt.Operator:A"},
                    {"owl:sameAs": "station:b", "odpt:operator": "odpt.Operator:B"},
                ]

        class Session:
            def get(self, *_args, **_kwargs):
                return Response()

        with patch.object(importer, "MIN_REQUEST_INTERVAL", 0):
            rows = importer.api_get(Session(), "odpt:Station", "secret", "odpt.Operator:A")
        self.assertEqual([row["owl:sameAs"] for row in rows], ["station:a"])

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

    def test_manual_topology_adds_all_stations_and_station_order(self):
        topology = {
            "lines": [{"name": "本線", "stations": ["A", "B", "C"], "color": "#123456"}],
            "stationMetadata": {"B": {"connectingStation": ["station:other"]}},
        }
        merged = importer.merge_manual_topology(
            "test", "odpt.Operator:Test", {"Station": [], "Railway": []}, topology
        )
        self.assertEqual(len(merged["Station"]), 3)
        self.assertEqual(len(merged["Railway"][0]["odpt:stationOrder"]), 3)
        station_b = next(item for item in merged["Station"] if item["dc:title"] == "B")
        self.assertEqual(station_b["odpt:connectingStation"], ["station:other"])

    def test_reviewed_topology_contains_complete_keio_keisei_and_minatomirai_lines(self):
        topology = importer.load_manual_topology()
        keio = importer.merge_manual_topology(
            "keio", "odpt.Operator:Keio", {"Station": [], "Railway": []}, topology["keio"]
        )
        keisei = importer.merge_manual_topology(
            "keisei", "odpt.Operator:Keisei", {"Station": [], "Railway": []}, topology["keisei"]
        )
        minatomirai = importer.merge_manual_topology(
            "yokohama-minatomirai",
            "manual.Operator:YokohamaMinatomirai",
            {"Station": [], "Railway": []},
            topology["yokohama-minatomirai"],
        )
        self.assertEqual(len(keio["Railway"]), 7)
        self.assertEqual(len(keio["Station"]), 69)
        self.assertEqual(
            sum(len(line["odpt:stationOrder"]) - 1 for line in keio["Railway"]), 69
        )
        self.assertTrue(all(len(line["odpt:stationOrder"]) >= 2 for line in keio["Railway"]))
        self.assertEqual(len(keisei["Railway"]), 8)
        self.assertGreaterEqual(len(keisei["Station"]), 80)
        self.assertTrue(all(len(line["odpt:stationOrder"]) >= 2 for line in keisei["Railway"]))
        self.assertEqual(len(minatomirai["Station"]), 6)
        self.assertEqual(len(minatomirai["Railway"][0]["odpt:stationOrder"]), 6)

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
        station_b = {
            "owl:sameAs": "odpt.Station:Test.B",
            "odpt:operator": "odpt.Operator:Test",
            "odpt:railway": "odpt.Railway:Test.Main",
            "odpt:stationTitle": {"ja": "B"},
        }
        railway = {
            "owl:sameAs": "odpt.Railway:Test.Main",
            "odpt:operator": "odpt.Operator:Test",
            "odpt:railwayTitle": {"ja": "本線"},
            "odpt:stationOrder": [
                {"odpt:index": 1, "odpt:station": station["owl:sameAs"]},
                {"odpt:index": 2, "odpt:station": station_b["owl:sameAs"]},
            ],
        }

        def fake_get(_session, rdf_type, _key, _operator=None, base_url=importer.BASE_URL):
            return {
                "odpt:Station": [station, station_b],
                "odpt:Railway": [railway],
                "odpt:TrainType": [],
                "odpt:RailDirection": [],
                "odpt:StationTimetable": [],
                "odpt:TrainTimetable": [],
            }.get(rdf_type, [])

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", {"ODPT_API_KEY": "secret"}, clear=True), patch.object(importer, "OUT_ROOT", Path(temp_dir)), patch.object(importer, "MANUAL_TOPOLOGY_PATH", Path(temp_dir) / "missing.json"), patch.object(importer, "TARGETS", target), patch.object(importer, "discover_operators", return_value=({"test": "odpt.Operator:Test"}, [])), patch.object(importer, "api_get", side_effect=fake_get):
            self.assertEqual(importer.main(), 0)
            manifest = json.loads((Path(temp_dir) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["operators"]["test"]["status"], "ok")
            self.assertEqual(manifest["operators"]["test"]["timetableStatus"], "not-requested")
            self.assertTrue((Path(temp_dir) / "test" / "entities.json").exists())


if __name__ == "__main__":
    unittest.main()
