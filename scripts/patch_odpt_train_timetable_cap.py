from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing anchor in {path}: {old[:140]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Add a fail-closed complete TrainTimetable fetcher. ODPT Challenge responses
# can stop at 1000 rows, so a saturated railway query is partitioned by
# authoritative direction and, if necessary, calendar. We never silently
# accept a still-saturated partition.
anchor = '''def api_base_for(config: dict[str, Any]) -> str:
'''
helper = '''ODPT_RESULT_CAP = int(os.environ.get("ODPT_RESULT_CAP", "1000"))


def api_get_complete_train_timetables(
    session: requests.Session,
    key: str,
    operator: str,
    railway: dict[str, Any] | str,
    base_url: str = BASE_URL,
) -> list[dict[str, Any]]:
    """Fetch every TrainTimetable row for one railway without silent cap loss.

    The Challenge API can return exactly 1000 rows for a broad query even when
    more rows exist. A saturated railway query is therefore partitioned by the
    railway's published directions. If one direction is still saturated, it is
    partitioned again by the calendar values visible in that direction. Any
    still-saturated leaf fails closed instead of being mistaken for complete
    data.
    """
    railway_id = str(railway.get("owl:sameAs") or "") if isinstance(railway, dict) else str(railway or "")
    if not railway_id:
        return []
    base_params = {"odpt:railway": railway_id}
    first = api_get(session, "odpt:TrainTimetable", key, operator, base_url=base_url, extra_params=base_params)
    if len(first) < ODPT_RESULT_CAP:
        return first

    directions: list[str] = []
    if isinstance(railway, dict):
        for field in ("odpt:ascendingRailDirection", "odpt:descendingRailDirection"):
            value = str(railway.get(field) or "")
            if value and value not in directions:
                directions.append(value)
    for row in first:
        value = str(row.get("odpt:railDirection") or "")
        if value and value not in directions:
            directions.append(value)
    if not directions:
        raise RuntimeError(f"Saturated TrainTimetable query has no direction partition: {railway_id}")

    merged: dict[str, dict[str, Any]] = {}

    def add(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            row_id = str(row.get("owl:sameAs") or "")
            if row_id:
                merged[row_id] = row

    for direction in directions:
        direction_params = {**base_params, "odpt:railDirection": direction}
        rows = api_get(session, "odpt:TrainTimetable", key, operator, base_url=base_url, extra_params=direction_params)
        if len(rows) < ODPT_RESULT_CAP:
            add(rows)
            continue

        calendars: list[str] = []
        for row in rows:
            raw = row.get("odpt:calendar")
            values = raw if isinstance(raw, list) else [raw]
            for value in values:
                text = str(value or "")
                if text and text not in calendars:
                    calendars.append(text)
        # Standard railway service calendars are included as defensive probes
        # in case one calendar happens to be absent from the capped first page.
        for value in (
            "odpt.Calendar:Weekday",
            "odpt.Calendar:Saturday",
            "odpt.Calendar:Holiday",
            "odpt.Calendar:SaturdayHoliday",
        ):
            if value not in calendars:
                calendars.append(value)

        direction_merged: dict[str, dict[str, Any]] = {}
        successful_calendar_probe = False
        for calendar in calendars:
            calendar_rows = api_get(
                session,
                "odpt:TrainTimetable",
                key,
                operator,
                base_url=base_url,
                extra_params={**direction_params, "odpt:calendar": calendar},
            )
            if not calendar_rows:
                continue
            successful_calendar_probe = True
            if len(calendar_rows) >= ODPT_RESULT_CAP:
                raise RuntimeError(
                    f"TrainTimetable partition is still saturated after railway/direction/calendar split: "
                    f"{railway_id} / {direction} / {calendar}"
                )
            for row in calendar_rows:
                row_id = str(row.get("owl:sameAs") or "")
                if row_id:
                    direction_merged[row_id] = row
        if not successful_calendar_probe:
            raise RuntimeError(f"Could not split saturated TrainTimetable direction: {railway_id} / {direction}")
        merged.update(direction_merged)

    original_ids = {str(row.get("owl:sameAs") or "") for row in first if row.get("owl:sameAs")}
    if not original_ids.issubset(merged):
        missing = sorted(original_ids - set(merged))[:5]
        raise RuntimeError(f"Partitioned TrainTimetable fetch lost rows for {railway_id}: {missing}")
    if len(merged) <= len(first):
        raise RuntimeError(
            f"Saturated TrainTimetable query did not expand after partitioning: {railway_id} ({len(first)} rows)"
        )
    print(f"{railway_id}: expanded saturated TrainTimetable query {len(first)} -> {len(merged)}")
    return list(merged.values())


'''
replace_once("scripts/import_odpt_timetables.py", anchor, helper + anchor)

old_call = '''                    train_raw = api_get(
                        session,
                        "odpt:TrainTimetable",
                        key,
                        operator_uri,
                        base_url=base_url,
                        extra_params={"odpt:railway": railway_id},
                    )
'''
new_call = '''                    train_raw = api_get_complete_train_timetables(
                        session,
                        key,
                        operator_uri,
                        railway,
                        base_url=base_url,
                    )
'''
replace_once("scripts/import_odpt_timetables.py", old_call, new_call)

# Identity collection must use the same complete per-railway fetch rather than
# one operator-wide request that is also capped at 1000 rows.
replace_once(
    "scripts/collect_odpt_train_identity.py",
    "import requests\n",
    "import requests\n\nfrom import_odpt_timetables import api_get_complete_train_timetables\n",
)
old_identity_fetch = '''        rows = api_get(f"{base_url}/odpt:TrainTimetable", key, operator)
        kept = 0
        for item in rows:
'''
new_identity_fetch = '''        entities_path = ROOT / slug / "entities.json"
        try:
            entities = json.loads(entities_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            entities = {}
        railways = [row for row in entities.get("Railway") or [] if isinstance(row, dict) and row.get("owl:sameAs")]
        session = requests.Session()
        rows_by_id: dict[str, dict[str, Any]] = {}
        for railway in railways:
            railway_rows = api_get_complete_train_timetables(
                session,
                key,
                operator,
                railway,
                base_url=base_url,
            )
            for item in railway_rows:
                timetable_id = str(item.get("owl:sameAs") or "")
                if timetable_id:
                    rows_by_id[timetable_id] = item
        rows = list(rows_by_id.values())
        kept = 0
        for item in rows:
'''
replace_once("scripts/collect_odpt_train_identity.py", old_identity_fetch, new_identity_fetch)

# Add a regression test that simulates a capped railway response and proves
# the complete fetcher fans out by direction and returns the missing row.
test_path = Path("scripts/test_import_odpt_timetables.py")
test_text = test_path.read_text(encoding="utf-8")
test_anchor = '''    def test_compact_entity_keeps_route_fields(self):
'''
test_case = '''    def test_complete_train_timetable_fetch_splits_a_saturated_railway_by_direction(self):
        railway_id = "odpt.Railway:Test.Main"
        inbound = "odpt.RailDirection:Inbound"
        outbound = "odpt.RailDirection:Outbound"
        initial = [
            {"owl:sameAs": f"tt:initial:{index}", "odpt:operator": "odpt.Operator:Test", "odpt:railDirection": inbound if index < 500 else outbound}
            for index in range(1000)
        ]
        inbound_rows = [
            {"owl:sameAs": f"tt:in:{index}", "odpt:operator": "odpt.Operator:Test", "odpt:railDirection": inbound}
            for index in range(700)
        ]
        outbound_rows = [
            {"owl:sameAs": f"tt:out:{index}", "odpt:operator": "odpt.Operator:Test", "odpt:railDirection": outbound}
            for index in range(650)
        ]
        missing = {"owl:sameAs": "tt:out:missing", "odpt:operator": "odpt.Operator:Test", "odpt:railDirection": outbound}
        outbound_rows.append(missing)

        calls = []
        def fake_api_get(_session, rdf_type, _key, operator=None, base_url=None, extra_params=None):
            self.assertEqual(rdf_type, "odpt:TrainTimetable")
            self.assertEqual(operator, "odpt.Operator:Test")
            params = dict(extra_params or {})
            calls.append(params)
            direction = params.get("odpt:railDirection")
            if direction == inbound:
                return inbound_rows
            if direction == outbound:
                return outbound_rows
            return initial

        railway = {
            "owl:sameAs": railway_id,
            "odpt:ascendingRailDirection": inbound,
            "odpt:descendingRailDirection": outbound,
        }
        with patch.object(importer, "api_get", side_effect=fake_api_get):
            rows = importer.api_get_complete_train_timetables(
                object(), "secret", "odpt.Operator:Test", railway, base_url="https://example.test/api/v4"
            )
        ids = {row["owl:sameAs"] for row in rows}
        self.assertIn("tt:out:missing", ids)
        self.assertEqual(len(rows), 1351)
        self.assertTrue(any(call.get("odpt:railDirection") == inbound for call in calls))
        self.assertTrue(any(call.get("odpt:railDirection") == outbound for call in calls))

'''
if test_anchor not in test_text:
    raise SystemExit("test insertion anchor missing")
test_path.write_text(test_text.replace(test_anchor, test_case + test_anchor, 1), encoding="utf-8")
