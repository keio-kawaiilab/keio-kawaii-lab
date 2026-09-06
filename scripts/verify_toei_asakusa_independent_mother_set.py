#!/usr/bin/env python3
"""Fail-closed verifier for the independent Toei Asakusa mother set audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def verify(payload: dict) -> dict:
    errors: list[str] = []
    if payload.get("version") != 1:
        errors.append("version must be 1")
    if payload.get("kind") != "toei-asakusa-independent-mother-set-audit":
        errors.append("unexpected dataset kind")
    if payload.get("railway") != "odpt.Railway:Toei.Asakusa":
        errors.append("unexpected railway")
    if payload.get("timeBasis") != "train-timetable":
        errors.append("timeBasis must be train-timetable")

    expected = int(payload.get("expectedTripCount") or 0)
    actual = int(payload.get("actualTripCount") or 0)
    physical = int(payload.get("candidatePhysicalTrainCount") or 0)
    timetable_ids = int(payload.get("uniqueTimetableIdCount") or 0)
    calendar_train_ids = int(payload.get("uniqueCalendarTrainIdCount") or 0)
    connections = int(payload.get("connectionCount") or 0)
    expected_connections = int(payload.get("expectedConnectionCount") or 0)
    stop_count = int(payload.get("stopCount") or 0)
    if expected <= 0 or actual <= 0:
        errors.append("no Toei Asakusa trips audited")
    if actual != expected:
        errors.append(f"trip count mismatch: {actual}/{expected}")
    if physical != actual:
        errors.append("physical train count must equal timetable trip count before cross-operator reconciliation")
    if timetable_ids != actual:
        errors.append("timetable IDs are not unique for every trip")
    if calendar_train_ids != actual:
        errors.append("calendar+train IDs are not unique for every trip")
    if stop_count <= 0:
        errors.append("no stops audited")
    if expected_connections and connections != expected_connections:
        errors.append(f"connection count mismatch: {connections}/{expected_connections}")

    calendar_counts = payload.get("calendarCounts") or {}
    if len(calendar_counts) < 2:
        errors.append("weekday and Saturday/holiday calendars are not both represented")
    if sum(int(v) for v in calendar_counts.values()) != actual:
        errors.append("calendar counts do not sum to all trips")

    internal = int(payload.get("internalDestinationTrips") or 0)
    external = int(payload.get("externalDestinationTrips") or 0)
    if internal + external != actual:
        errors.append("destination partition mismatch")
    if external <= 0:
        errors.append("no external-destination trips found; through-service audit would be empty")

    policy = payload.get("identityPolicy") or {}
    required_true = (
        "motherSetComesFromToeiTrainTimetable",
        "allTimetableTripsRetained",
        "trainTimetableIdIsExactLocalIdentity",
    )
    required_false = (
        "keiseiMotherSetUsedToSelectTrips",
        "crossOperatorIdentityEstablished",
        "clockTimeMayEstablishCrossOperatorIdentity",
        "destinationMayEstablishCrossOperatorIdentity",
    )
    for key in required_true:
        if policy.get(key) is not True:
            errors.append(f"{key} must be true")
    for key in required_false:
        if policy.get(key) is not False:
            errors.append(f"{key} must be false")
    if policy.get("runtimeSameTrainPromotions") != 0:
        errors.append("runtimeSameTrainPromotions must remain zero")
    if payload.get("issues"):
        errors.append(f"audit has {len(payload['issues'])} issue(s)")

    if errors:
        raise RuntimeError("Toei Asakusa independent mother-set verification failed:\n- " + "\n- ".join(errors[:100]))
    return {
        "verified": True,
        "trips": actual,
        "connections": connections,
        "internalDestinationTrips": internal,
        "externalDestinationTrips": external,
        "calendarCounts": calendar_counts,
        "runtimeSameTrainPromotions": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.dataset.read_text(encoding="utf-8"))
    print(json.dumps(verify(payload), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
