#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DATA_PATH = Path("data/live-events.json")
JST = ZoneInfo("Asia/Tokyo")


def main() -> int:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    diagnostics = payload.get("playguideDiagnostics")
    if not isinstance(diagnostics, dict):
        print("playguideDiagnostics is missing")
        return 2

    errors: list[str] = []
    collected_at = str(diagnostics.get("collectedAt") or "")
    try:
        stamp = datetime.fromisoformat(collected_at)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=JST)
        age = datetime.now(JST) - stamp.astimezone(JST)
        if age > timedelta(hours=2, minutes=30):
            errors.append(f"playguide diagnostics are stale by {age}")
    except ValueError:
        errors.append(f"invalid collectedAt: {collected_at!r}")

    failures = diagnostics.get("failures") if isinstance(diagnostics.get("failures"), list) else []
    missing = diagnostics.get("stillActiveMissing") if isinstance(diagnostics.get("stillActiveMissing"), list) else []
    refreshed = diagnostics.get("refreshedSources") if isinstance(diagnostics.get("refreshedSources"), list) else []

    # Ten source/group pairs should be attempted: eplus + Lawson for five groups.
    if len(refreshed) + len(failures) < 10:
        errors.append(f"only {len(refreshed) + len(failures)}/10 playguide source/group attempts are accounted for")
    if failures:
        errors.append(f"{len(failures)} playguide source/group request(s) failed")
    if missing:
        errors.append(
            f"{len(missing)} still-active reception(s) disappeared from a successfully refreshed playguide source"
        )

    report = {
        "status": "ok" if not errors else "blocked",
        "collectedAt": diagnostics.get("collectedAt"),
        "freshCounts": diagnostics.get("freshCounts") or {},
        "refreshedSources": refreshed,
        "failureCount": len(failures),
        "stillActiveMissingCount": len(missing),
        "expiredRowsPruned": diagnostics.get("expiredRowsPruned", 0),
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
