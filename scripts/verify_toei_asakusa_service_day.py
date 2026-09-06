#!/usr/bin/env python3
"""Fail-closed verifier for Toei Asakusa independent service-day audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def verify(payload: dict) -> dict:
    errors: list[str] = []
    if payload.get("version") != 2:
        errors.append("version must be 2")
    if payload.get("kind") != "toei-asakusa-independent-mother-set-service-day-audit":
        errors.append("unexpected dataset kind")
    if payload.get("railway") != "odpt.Railway:Toei.Asakusa":
        errors.append("unexpected railway")
    expected = int(payload.get("expectedTripCount") or 0)
    actual = int(payload.get("actualTripCount") or 0)
    if actual <= 0 or actual != expected:
        errors.append(f"trip count mismatch: {actual}/{expected}")
    if int(payload.get("uniqueTimetableIdCount") or 0) != actual:
        errors.append("not every trip has a unique timetable ID")
    if int(payload.get("uniqueCalendarTrainIdCount") or 0) != actual:
        errors.append("not every trip has a unique calendar+train ID")
    if int(payload.get("connectionCount") or 0) != int(payload.get("expectedConnectionCount") or 0):
        errors.append("connection count mismatch")
    if int(payload.get("unsafeTimeRegressionTripCount") or 0) != 0:
        errors.append("unsafe time regressions remain")
    if payload.get("unsafeTimeRegressionTrips"):
        errors.append("unsafe regression details are non-empty")

    raw_count = int(payload.get("rawNonMonotonicTripCount") or 0)
    wrap_count = int(payload.get("acceptedMidnightWrapTripCount") or 0)
    wrap_rows = payload.get("acceptedMidnightWrapTrips") or []
    if raw_count != wrap_count:
        errors.append(f"not every raw regression is a midnight wrap: {wrap_count}/{raw_count}")
    if wrap_count != len(wrap_rows):
        errors.append("midnight wrap detail count mismatch")
    for row in wrap_rows:
        wraps = row.get("wraps") or []
        if len(wraps) != 1:
            errors.append(f"trip has {len(wraps)} wraps: {row.get('timetableId')}")
            continue
        wrap = wraps[0]
        if int(wrap.get("from") or -1) < 23 * 60:
            errors.append(f"wrap starts before 23:00: {row.get('timetableId')}")
        if int(wrap.get("to") or 9999) > 2 * 60:
            errors.append(f"wrap ends after 02:00: {row.get('timetableId')}")
        first = row.get("firstServiceDayTime")
        last = row.get("lastServiceDayTime")
        if first is not None and last is not None and int(last) < int(first):
            errors.append(f"service-day chronology still regresses: {row.get('timetableId')}")

    policy = payload.get("identityPolicy") or {}
    required_true = (
        "motherSetComesFromToeiTrainTimetable",
        "allTimetableTripsRetained",
        "trainTimetableIdIsExactLocalIdentity",
        "rawTimesPreserved",
        "midnightWrapNormalizationForChronologyOnly",
        "only2300To0200WrapMayNormalize",
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
        raise RuntimeError("Toei Asakusa service-day verification failed:\n- " + "\n- ".join(errors[:100]))
    return {
        "verified": True,
        "trips": actual,
        "connections": int(payload.get("connectionCount") or 0),
        "midnightWrapTrips": wrap_count,
        "unsafeTimeRegressions": 0,
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
