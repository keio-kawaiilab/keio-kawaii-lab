#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import dedupe_keisei_official_timetables as subject


def trip(number: str, minute: int) -> list:
    return [0, 0, number, [[0, minute, minute], [1, minute + 2, minute + 2]]]


def test_exact_duplicates_removed_only() -> None:
    duplicate = trip("501T", 336)
    different_time = trip("501T", 337)
    different_number = trip("503T", 336)
    payload = {
        "version": 1,
        "railway": "odpt.Railway:Keisei.Oshiage",
        "stations": ["a", "b"],
        "calendars": ["weekday"],
        "trainTypes": ["普通"],
        "trips": [duplicate, json.loads(json.dumps(duplicate)), different_time, different_number],
    }
    normalized, stats = subject.dedupe_payload(payload)
    assert stats["beforeTrips"] == 4
    assert stats["afterTrips"] == 3
    assert stats["removedTrips"] == 1
    assert normalized["trips"] == [duplicate, different_time, different_number]


def test_repeated_run_is_idempotent() -> None:
    duplicate = trip("501T", 336)
    payload = {"trips": [duplicate, json.loads(json.dumps(duplicate))]}
    first, first_stats = subject.dedupe_payload(payload)
    second, second_stats = subject.dedupe_payload(first)
    assert first_stats["removedTrips"] == 1
    assert second_stats["removedTrips"] == 0
    assert first["trips"] == second["trips"]


def test_run_updates_index_report_and_manifest() -> None:
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        root = base / "keisei"
        (root / "timetables").mkdir(parents=True)
        timetable = root / "timetables" / "official-oshiage.json"
        duplicate = trip("501T", 336)
        timetable.write_text(json.dumps({"trips": [duplicate, duplicate]}), encoding="utf-8")
        index = root / "timetable-index.json"
        index.write_text(json.dumps({"lines": {"oshiage": {"file": "timetables/official-oshiage.json", "trips": 2, "connections": 2}}}), encoding="utf-8")
        report = root / "official-conversion-report.json"
        report.write_text(json.dumps({"lines": {"oshiage": {"trips": 2, "connections": 2}}}), encoding="utf-8")
        manifest = base / "manifest.json"
        manifest.write_text(json.dumps({"operators": {"keisei": {"timetableConnections": 2, "departures": 2}}, "notes": []}), encoding="utf-8")

        summary = subject.run(root, index, report, manifest)
        assert summary["removedTrips"] == 1
        assert summary["afterTrips"] == 1
        assert summary["connections"] == 1
        saved_index = json.loads(index.read_text(encoding="utf-8"))
        assert saved_index["lines"]["oshiage"]["trips"] == 1
        saved_report = json.loads(report.read_text(encoding="utf-8"))
        assert saved_report["duplicateCompactTripsRemoved"] == 1
        assert saved_report["deduplicationPolicy"]["trainNumberAloneMayMerge"] is False
        saved_manifest = json.loads(manifest.read_text(encoding="utf-8"))
        assert saved_manifest["operators"]["keisei"]["deduplicatedCompactTrips"] == 1


def main() -> int:
    test_exact_duplicates_removed_only()
    test_repeated_run_is_idempotent()
    test_run_updates_index_report_and_manifest()
    print("Keisei compact timetable dedupe tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
