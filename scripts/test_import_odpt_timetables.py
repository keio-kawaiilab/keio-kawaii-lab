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

    def test_timetable_import_is_enabled_by_default_and_can_be_paused(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertTrue(importer.timetable_import_enabled())
        with patch.dict("os.environ", {"ODPT_IMPORT_TIMETABLES": "0"}, clear=True):
            self.assertFalse(importer.timetable_import_enabled())

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

    def test_compact_line_timetable_keeps_service_day_times_and_station_aliases(self):
        item = {
            "odpt:calendar": "odpt.Calendar:Weekday",
            "odpt:trainType": "odpt.TrainType:Test.Local",
            "odpt:trainNumber": "101",
            "odpt:trainTimetableObject": [
                {"odpt:departureStation": "station:a-old", "odpt:departureTime": "23:58"},
                {"odpt:arrivalStation": "station:b", "odpt:arrivalTime": "24:07"},
                {"odpt:departureStation": "station:b", "odpt:departureTime": "24:08"},
                {"odpt:arrivalStation": "station:c", "odpt:arrivalTime": "24:15"},
            ],
        }
        compact, connections = importer.compact_line_timetable(
            "railway:test", [item], {"station:a-old": "station:a"}
        )
        self.assertEqual(compact["stations"], ["station:a", "station:b", "station:c"])
        self.assertEqual(compact["calendars"], ["odpt.Calendar:Weekday"])
        self.assertEqual(compact["trips"][0][3][0], [0, None, 1438])
        self.assertEqual(compact["trips"][0][3][1], [1, 1447, 1448])
        self.assertEqual(connections, 2)

    def test_station_timetables_are_joined_into_trips(self):
        items = [
            {
                "odpt:railway": "railway:test",
                "odpt:station": "station:a-old",
                "odpt:railDirection": "direction:outbound",
                "odpt:calendar": "odpt.Calendar:Weekday",
                "odpt:stationTimetableObject": [{
                    "odpt:train": "train:101",
                    "odpt:trainType": "type:local",
                    "odpt:trainNumber": "101",
                    "odpt:departureTime": "23:58",
                }],
            },
            {
                "odpt:railway": "railway:test",
                "odpt:station": "station:b",
                "odpt:railDirection": "direction:outbound",
                "odpt:calendar": "odpt.Calendar:Weekday",
                "odpt:stationTimetableObject": [{
                    "odpt:train": "train:101",
                    "odpt:trainType": "type:local",
                    "odpt:trainNumber": "101",
                    "odpt:departureTime": "00:07",
                }],
            },
        ]
        lines = importer.compact_station_timetables(items, {"station:a-old": "station:a"})
        compact, connections, departures = lines["railway:test"]
        self.assertEqual(compact["timeBasis"], "station-departure")
        self.assertEqual(compact["stations"], ["station:a", "station:b"])
        self.assertEqual(compact["trips"][0][3], [[0, 1438, 1438], [1, 1447, 1447]])
        self.assertEqual(connections, 1)
        self.assertEqual(departures, 2)

    def test_station_timetable_without_train_ids_becomes_departure_board(self):
        items = [
            {
                "odpt:railway": "railway:test",
                "odpt:station": "station:a",
                "odpt:railDirection": "direction:ascending",
                "odpt:calendar": "odpt.Calendar:Weekday",
                "odpt:stationTimetableObject": [
                    {"odpt:trainType": "type:local", "odpt:departureTime": "08:01"},
                    {"odpt:trainType": "type:local", "odpt:departureTime": "08:11"},
                    {"odpt:trainType": "type:local", "odpt:departureTime": "08:21"},
                ],
            },
            {
                "odpt:railway": "railway:test",
                "odpt:station": "station:b",
                "odpt:railDirection": "direction:ascending",
                "odpt:calendar": "odpt.Calendar:Weekday",
                "odpt:stationTimetableObject": [
                    {"odpt:trainType": "type:local", "odpt:departureTime": "08:04"},
                    {"odpt:trainType": "type:local", "odpt:departureTime": "08:14"},
                    {"odpt:trainType": "type:local", "odpt:departureTime": "08:24"},
                ],
            },
        ]
        railway = {
            "owl:sameAs": "railway:test",
            "odpt:ascendingRailDirection": "direction:ascending",
            "odpt:descendingRailDirection": "direction:descending",
            "odpt:stationOrder": [
                {"odpt:index": 1, "odpt:station": "station:a"},
                {"odpt:index": 2, "odpt:station": "station:b"},
            ],
        }
        compact, connections, departures = importer.compact_station_timetables(
            items, {}, [railway]
        )["railway:test"]
        self.assertEqual(compact["timeBasis"], "station-departure-only")
        self.assertEqual(compact["order"], ["station:a", "station:b"])
        self.assertEqual(compact["boards"][0][3], [[481, 0, 0], [491, 0, 0], [501, 0, 0]])
        self.assertEqual(compact["edgeMinutes"], [[0, 1, 3, 3], [1, 0, 3, 3]])
        self.assertEqual(compact["typeDurations"], [[0, 1, 0, 0, 3, 3]])
        self.assertEqual(len(compact["inferredTrips"]), 3)
        self.assertEqual(compact["inferredConnections"], 3)
        self.assertEqual(connections, 0)
        self.assertEqual(departures, 6)

    def test_inferred_station_trips_keep_train_specific_waiting_time(self):
        station_times = {
            "station:a": ["08:00", "08:10", "08:20"],
            "station:b": ["08:03", "08:13", "08:23"],
            # The first local waits four extra minutes here; later trains do not.
            "station:c": ["08:10", "08:16", "08:26"],
            "station:d": ["08:13", "08:19", "08:29"],
        }
        items = []
        for station_id, times in station_times.items():
            items.append({
                "odpt:railway": "railway:test",
                "odpt:station": station_id,
                "odpt:railDirection": "direction:ascending",
                "odpt:calendar": "odpt.Calendar:Weekday",
                "odpt:stationTimetableObject": [{
                    "odpt:trainType": "type:local",
                    "odpt:destinationStation": ["station:d"],
                    "odpt:departureTime": departure,
                } for departure in times],
            })
        railway = {
            "owl:sameAs": "railway:test",
            "odpt:ascendingRailDirection": "direction:ascending",
            "odpt:descendingRailDirection": "direction:descending",
            "odpt:stationOrder": [
                {"odpt:index": index + 1, "odpt:station": station_id}
                for index, station_id in enumerate(station_times)
            ],
        }
        compact, connections, _departures = importer.compact_station_timetables(
            items, {}, [railway]
        )["railway:test"]
        first_trip = next(
            trip for trip in compact["inferredTrips"]
            if trip[5][0][2] == 8 * 60
        )
        self.assertEqual([stop[2] for stop in first_trip[5]], [480, 483, 490, 493])
        self.assertEqual(compact["inferredConnections"], 9)
        self.assertEqual(connections, 0, "inferred trips must remain labelled as estimates")

    def test_inferred_station_trip_keeps_an_arrival_only_terminal(self):
        items = [
            {
                "odpt:railway": "railway:test",
                "odpt:station": "station:a",
                "odpt:railDirection": "direction:ascending",
                "odpt:calendar": "odpt.Calendar:Weekday",
                "odpt:stationTimetableObject": [{
                    "odpt:trainType": "type:local",
                    "odpt:destinationStation": ["station:b"],
                    "odpt:departureTime": value,
                } for value in ["08:00", "08:10", "08:20"]],
            },
            {
                "odpt:railway": "railway:test",
                "odpt:station": "station:b",
                "odpt:railDirection": "direction:ascending",
                "odpt:calendar": "odpt.Calendar:Weekday",
                "odpt:stationTimetableObject": [{
                    "odpt:trainType": "type:local",
                    "odpt:arrivalTime": value,
                } for value in ["08:03", "08:13", "08:23"]],
            },
        ]
        railway = {
            "owl:sameAs": "railway:test",
            "odpt:ascendingRailDirection": "direction:ascending",
            "odpt:descendingRailDirection": "direction:descending",
            "odpt:stationOrder": [
                {"odpt:index": 1, "odpt:station": "station:a"},
                {"odpt:index": 2, "odpt:station": "station:b"},
            ],
        }
        compact, _connections, departures = importer.compact_station_timetables(
            items, {}, [railway]
        )["railway:test"]
        first_trip = next(trip for trip in compact["inferredTrips"] if trip[5][0][2] == 480)
        self.assertEqual(first_trip[5][1][1:], [483, None])
        self.assertEqual(departures, 3, "arrival-only rows must not become boardable departures")

    def test_inferred_station_trip_joins_a_mid_route_type_change(self):
        station_rows = {
            "station:a": ("type:express", ["08:00", "08:10", "08:20"]),
            "station:b": ("type:express", ["08:03", "08:13", "08:23"]),
            "station:c": ("type:local", ["08:10", "08:20", "08:30"]),
            "station:d": ("type:local", ["08:13", "08:23", "08:33"]),
        }
        items = [{
            "odpt:railway": "railway:test",
            "odpt:station": station_id,
            "odpt:railDirection": "direction:ascending",
            "odpt:calendar": "odpt.Calendar:Weekday",
            "odpt:stationTimetableObject": [{
                "odpt:trainType": train_type,
                "odpt:destinationStation": ["station:d"],
                "odpt:departureTime": departure,
            } for departure in times],
        } for station_id, (train_type, times) in station_rows.items()]
        for item in items:
            if item["odpt:station"] not in ("station:b", "station:c"):
                continue
            no_wait_times = ["08:05", "08:15", "08:25"] if item["odpt:station"] == "station:b" else ["08:08", "08:18", "08:28"]
            item["odpt:stationTimetableObject"].extend({
                "odpt:trainType": "type:no-wait",
                "odpt:destinationStation": ["station:elsewhere"],
                "odpt:departureTime": departure,
            } for departure in no_wait_times)
        railway = {
            "owl:sameAs": "railway:test",
            "odpt:ascendingRailDirection": "direction:ascending",
            "odpt:descendingRailDirection": "direction:descending",
            "odpt:stationOrder": [
                {"odpt:index": index + 1, "odpt:station": station_id}
                for index, station_id in enumerate(station_rows)
            ],
        }
        compact, _connections, _departures = importer.compact_station_timetables(
            items, {}, [railway]
        )["railway:test"]
        express_index = compact["trainTypes"].index("type:express")
        first_trip = next(
            trip for trip in compact["inferredTrips"]
            if trip[2] == express_index and trip[5][0][2] == 480
        )
        self.assertEqual([stop[2] for stop in first_trip[5]], [480, 483, 490, 493])
        self.assertEqual(first_trip[5][2][1], 486, "the extra four minutes must be platform dwell, not running time")

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

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", {"ODPT_API_KEY": "secret", "ODPT_IMPORT_TIMETABLES": "0"}, clear=True), patch.object(importer, "OUT_ROOT", Path(temp_dir)), patch.object(importer, "MANUAL_TOPOLOGY_PATH", Path(temp_dir) / "missing.json"), patch.object(importer, "TARGETS", target), patch.object(importer, "discover_operators", return_value=({"test": "odpt.Operator:Test"}, [])), patch.object(importer, "api_get", side_effect=fake_get):
            self.assertEqual(importer.main(), 0)
            manifest = json.loads((Path(temp_dir) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["operators"]["test"]["status"], "ok")
            self.assertEqual(manifest["operators"]["test"]["timetableStatus"], "not-requested")
            self.assertTrue((Path(temp_dir) / "test" / "entities.json").exists())


if __name__ == "__main__":
    unittest.main()
