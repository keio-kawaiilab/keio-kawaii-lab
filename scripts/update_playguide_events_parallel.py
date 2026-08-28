#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

import update_playguide_events as playguides

JST = ZoneInfo("Asia/Tokyo")
USER_AGENT = "KeioKawaiiLabCalendarBot/1.7 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"
Collector = Callable[[object, str, date], list[dict]]
DEFAULT_TASKS: tuple[tuple[str, str, Collector], ...] = tuple(
    (provider, group, collector)
    for group in playguides.GROUPS
    for provider, collector in (("eplus", playguides.collect_eplus), ("lawson", playguides.collect_lawson))
)


def make_session():
    session = playguides.requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def collect_one(
    provider: str,
    group: str,
    collector: Collector,
    today: date,
    observed_at: str,
    session_factory=make_session,
) -> tuple[str, str, list[dict]]:
    session = session_factory()
    try:
        rows = collector(session, group, today)
    finally:
        close = getattr(session, "close", None)
        if callable(close):
            close()
    for row in rows:
        row["sourceObservedAt"] = observed_at
        row["sourceStale"] = False
        row.pop("sourceStaleSince", None)
    return provider, group, rows


def collect_parallel(
    today: date,
    observed_at: str,
    *,
    tasks: Iterable[tuple[str, str, Collector]] | None = None,
    max_workers: int = 10,
    session_factory=make_session,
) -> dict:
    ordered_tasks = tuple(tasks or DEFAULT_TASKS)
    workers = max(1, min(max_workers, len(ordered_tasks) or 1))
    started = time.monotonic()
    rows_by_source: dict[tuple[str, str], list[dict]] = {}
    failures: list[str] = []

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="playguide") as pool:
        futures = {
            pool.submit(collect_one, provider, group, collector, today, observed_at, session_factory): (provider, group)
            for provider, group, collector in ordered_tasks
        }
        for future in as_completed(futures):
            provider, group = futures[future]
            try:
                _, _, rows = future.result()
                rows_by_source[(provider, group)] = rows
            except Exception as exc:
                failures.append(f"{provider}/{group}: {type(exc).__name__}: {exc}")

    fresh: list[dict] = []
    fresh_counts: Counter[str] = Counter()
    refreshed: set[tuple[str, str]] = set()
    for provider, group, _collector in ordered_tasks:
        key = (provider, group)
        if key not in rows_by_source:
            continue
        rows = rows_by_source[key]
        fresh.extend(rows)
        fresh_counts[f"{provider}:{group}"] = len(rows)
        refreshed.add(key)

    return {
        "fresh": playguides.dedupe(fresh),
        "freshCounts": dict(sorted(fresh_counts.items())),
        "refreshed": refreshed,
        "failures": sorted(failures),
        "workerCount": workers,
        "durationSeconds": round(time.monotonic() - started, 3),
    }


def merge_collection(payload: dict, collection: dict, today: date, observed_at: str) -> dict:
    existing = [dict(item) for item in payload.get("events", []) if isinstance(item, dict)]
    fresh = list(collection["fresh"])
    refreshed: set[tuple[str, str]] = set(collection["refreshed"])
    fresh_identity = {playguides.identity(event) for event in fresh}

    retained: list[dict] = []
    still_active_missing: list[dict] = []
    expired_pruned = 0
    for event in existing:
        provider = str(event.get("ticketProvider") or event.get("sourceType") or "").lower()
        group = str(event.get("group") or "")
        if provider not in {"eplus", "lawson"}:
            retained.append(event)
            continue
        if (provider, group) not in refreshed:
            retained.append(event)
            continue
        if playguides.identity(event) in fresh_identity:
            continue
        if playguides.is_current_window(str(event.get("applyEnd") or ""), today):
            event["sourceStale"] = True
            event.setdefault("sourceStaleSince", observed_at)
            retained.append(event)
            still_active_missing.append({
                "provider": provider,
                "group": group,
                "eventDate": event.get("eventDate"),
                "ticketType": event.get("ticketType"),
                "applyEnd": event.get("applyEnd"),
                "url": event.get("url"),
            })
        else:
            expired_pruned += 1

    result = dict(payload)
    result["events"] = retained + fresh
    result["updatedAt"] = observed_at
    result["playguideFailures"] = list(collection["failures"])
    result["playguideDiagnostics"] = {
        "collectedAt": observed_at,
        "collectorMode": "parallel",
        "workerCount": collection["workerCount"],
        "durationSeconds": collection["durationSeconds"],
        "freshCounts": collection["freshCounts"],
        "refreshedSources": [f"{provider}:{group}" for provider, group in sorted(refreshed)],
        "failureCount": len(collection["failures"]),
        "failures": list(collection["failures"]),
        "stillActiveMissingCount": len(still_active_missing),
        "stillActiveMissing": still_active_missing,
        "expiredRowsPruned": expired_pruned,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh Lawson Ticket and eplus windows in parallel")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    payload = json.loads(playguides.DATA_PATH.read_text(encoding="utf-8"))
    now = datetime.now(JST)
    today = now.date()
    observed_at = now.isoformat(timespec="seconds")
    collection = collect_parallel(today, observed_at, max_workers=args.workers)

    if not collection["refreshed"]:
        raise SystemExit("All playguide sources failed: " + "; ".join(collection["failures"]))

    if collection["failures"]:
        print("Playguide source warnings: " + "; ".join(collection["failures"]), file=sys.stderr)

    if args.check:
        print(json.dumps({
            "status": "ok",
            "collectorMode": "parallel",
            "workerCount": collection["workerCount"],
            "durationSeconds": collection["durationSeconds"],
            "activeWindows": len(collection["fresh"]),
            "freshCounts": collection["freshCounts"],
            "refreshedSources": [f"{p}:{g}" for p, g in sorted(collection["refreshed"])],
            "failures": collection["failures"],
        }, ensure_ascii=False, indent=2))
        return 0

    result = merge_collection(payload, collection, today, observed_at)
    playguides.DATA_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["playguideDiagnostics"], ensure_ascii=False, indent=2))
    print(
        f"Refreshed playguides in parallel: {len(collection['fresh'])} active windows; "
        f"{result['playguideDiagnostics']['expiredRowsPruned']} ended rows pruned"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
