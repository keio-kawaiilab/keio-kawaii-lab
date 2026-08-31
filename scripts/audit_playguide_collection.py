#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DATA_PATH = Path("data/live-events.json")
JST = ZoneInfo("Asia/Tokyo")


def audit_payload(payload: dict, now: datetime | None = None) -> tuple[dict, int]:
    diagnostics = payload.get("playguideDiagnostics")
    if not isinstance(diagnostics, dict):
        return {
            "status": "blocked",
            "warnings": [],
            "errors": ["playguideDiagnostics is missing"],
        }, 2

    errors: list[str] = []
    warnings: list[str] = []
    collected_at = str(diagnostics.get("collectedAt") or "")
    now = now or datetime.now(JST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=JST)
    try:
        stamp = datetime.fromisoformat(collected_at)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=JST)
        age = now.astimezone(JST) - stamp.astimezone(JST)
        if age > timedelta(hours=2, minutes=30):
            errors.append(f"playguide diagnostics are stale by {age}")
    except ValueError:
        errors.append(f"invalid collectedAt: {collected_at!r}")

    failures = diagnostics.get("failures") if isinstance(diagnostics.get("failures"), list) else []
    missing = diagnostics.get("stillActiveMissing") if isinstance(diagnostics.get("stillActiveMissing"), list) else []
    refreshed = diagnostics.get("refreshedSources") if isinstance(diagnostics.get("refreshedSources"), list) else []

    # Ten source/group pairs should be attempted: eplus + Lawson for five groups.
    # A failed request is not by itself a release blocker: the parallel collector
    # preserves the previous known-good rows for that exact provider/group pair.
    # This keeps unrelated schedule sources updating during a transient outage.
    accounted = len(refreshed) + len(failures)
    if accounted < 10:
        errors.append(f"only {accounted}/10 playguide source/group attempts are accounted for")
    if not refreshed:
        errors.append("all playguide source/group requests failed")
    elif failures:
        warnings.append(
            f"{len(failures)} playguide source/group request(s) failed; previous known-good rows were retained"
        )

    # A still-active row missing from a successfully refreshed source is already
    # kept by merge_collection() and marked sourceStale. Treat that as a guarded
    # warning rather than discarding *all* healthy provider updates. The later
    # integrated row-level audit still remains authoritative before publication.
    if missing:
        warnings.append(
            f"{len(missing)} still-active reception(s) disappeared from a refreshed source; guarded previous rows were retained as stale"
        )

    report = {
        "status": "ok" if not errors else "blocked",
        "collectedAt": diagnostics.get("collectedAt"),
        "freshCounts": diagnostics.get("freshCounts") or {},
        "refreshedSources": refreshed,
        "failureCount": len(failures),
        "stillActiveMissingCount": len(missing),
        "expiredRowsPruned": diagnostics.get("expiredRowsPruned", 0),
        "warnings": warnings,
        "errors": errors,
    }
    return report, 0 if not errors else 2


def main() -> int:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    report, code = audit_payload(payload)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
