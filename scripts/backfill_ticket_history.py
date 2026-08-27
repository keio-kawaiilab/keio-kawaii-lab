#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

BACKFILL_PATH = Path("data/ticket-history-backfill-sources.json")
HISTORY_PATH = Path("data/ticket-history.json")
REGISTRY_PATH = Path("data/ticket-source-registry.json")
JST = ZoneInfo("Asia/Tokyo")


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def clean(value: object) -> str:
    return str(value or "").strip()


def source_key_for_url(url: str, registry: dict) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    rules = registry.get("hostRules") or {}
    if host in rules:
        return str(rules[host])
    for known_host, key in rules.items():
        if host.endswith("." + str(known_host).lower()):
            return str(key)
    return None


def validate(backfill: dict, registry: dict) -> list[str]:
    errors: list[str] = []
    sources = registry.get("sources") or {}
    seen_keys: set[str] = set()

    for index, series in enumerate(backfill.get("series") or []):
        if not isinstance(series, dict):
            errors.append(f"series[{index}] is not an object")
            continue
        key = clean(series.get("key"))
        if not key:
            errors.append(f"series[{index}] missing key")
        elif key in seen_keys:
            errors.append(f"duplicate series key: {key}")
        seen_keys.add(key)

        for field in ("group", "eventTitle", "sourceKey", "sourceUrl"):
            if not clean(series.get(field)):
                errors.append(f"{key or index}: missing {field}")

        source_key = clean(series.get("sourceKey"))
        source_url = clean(series.get("sourceUrl"))
        source_config = sources.get(source_key) if source_key else None
        if not isinstance(source_config, dict) or source_config.get("publishPolicy") != "direct":
            errors.append(f"{key or index}: sourceKey {source_key!r} is not a direct source")
        mapped = source_key_for_url(source_url, registry) if source_url else None
        if mapped != source_key:
            errors.append(f"{key or index}: sourceUrl maps to {mapped!r}, not {source_key!r}")

        events = [x for x in series.get("events") or [] if isinstance(x, dict)]
        event_dates = {clean(x.get("date")) for x in events if clean(x.get("date"))}
        if not events:
            errors.append(f"{key or index}: no events")
        if len(event_dates) != len(events):
            errors.append(f"{key or index}: duplicate or missing event dates")

        phases = [x for x in series.get("phases") or [] if isinstance(x, dict)]
        if not phases:
            errors.append(f"{key or index}: no phases")
        for p_index, phase in enumerate(phases):
            label = f"{key or index}/phase[{p_index}]"
            if not clean(phase.get("ticketType")):
                errors.append(f"{label}: missing ticketType")
            if not clean(phase.get("applyEnd")):
                errors.append(f"{label}: missing applyEnd")
            dates = phase.get("dates")
            if dates is not None:
                unknown = {clean(x) for x in dates} - event_dates
                if unknown:
                    errors.append(f"{label}: unknown target dates {sorted(unknown)}")
    return errors


def semantic_key(item: dict) -> tuple[str, ...]:
    return (
        clean(item.get("group")),
        clean(item.get("eventDate")),
        clean(item.get("ticketType")),
        clean(item.get("applyStart")),
        clean(item.get("applyEnd")),
        clean(item.get("ticketProvider")),
    )


def entry_id(series_key: str, event_date: str, phase: dict) -> str:
    raw = "\x1f".join(
        (
            "curated-backfill-v1",
            series_key,
            event_date,
            clean(phase.get("ticketType")),
            clean(phase.get("applyStart")),
            clean(phase.get("applyEnd")),
            clean(phase.get("ticketProvider")),
        )
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def make_entry(series: dict, event: dict, phase: dict, now: str) -> dict:
    start = phase.get("applyStart")
    end = phase.get("applyEnd")
    return {
        "id": entry_id(clean(series.get("key")), clean(event.get("date")), phase),
        "group": series.get("group"),
        "participants": [],
        "eventTitle": series.get("eventTitle"),
        "eventDate": event.get("date"),
        "venue": event.get("venue"),
        "ticketType": phase.get("ticketType"),
        "ticketProvider": phase.get("ticketProvider") or "official",
        "saleFamily": phase.get("saleFamily"),
        "applyStart": start,
        "applyEnd": end,
        "resultDate": phase.get("resultDate"),
        "paymentEnd": phase.get("paymentEnd"),
        "sourceKey": series.get("sourceKey"),
        "sourceLabel": series.get("sourceLabel") or series.get("sourceKey"),
        "sourceUrl": series.get("sourceUrl"),
        "sourcePublishedAt": phase.get("sourcePublishedAt"),
        "verificationLevel": "curated-direct-official",
        "windowCompleteness": "full" if start and end else "end-only" if end else "start-only",
        "publishable": bool(end),
        "flowEligible": True,
        "eventCategory": None,
        "curatedBackfill": True,
        "backfillSeriesKey": series.get("key"),
        "firstSeenAt": now,
        "lastSeenAt": now,
        "observedWindows": [
            {
                "applyStart": start,
                "applyEnd": end,
                "resultDate": phase.get("resultDate"),
                "paymentEnd": phase.get("paymentEnd"),
            }
        ],
    }


def apply_backfill(backfill: dict, history: dict, now: str) -> tuple[dict, dict]:
    entries = [dict(x) for x in history.get("entries") or [] if isinstance(x, dict) and x.get("id")]
    known_semantic = {semantic_key(x) for x in entries}
    known_ids = {clean(x.get("id")) for x in entries}
    added = 0
    skipped_existing = 0
    by_series: dict[str, int] = {}

    for series in backfill.get("series") or []:
        series_key = clean(series.get("key"))
        events = [x for x in series.get("events") or [] if isinstance(x, dict)]
        event_by_date = {clean(x.get("date")): x for x in events}
        for phase in series.get("phases") or []:
            targets = [clean(x) for x in phase.get("dates") or event_by_date.keys()]
            for day in targets:
                event = event_by_date.get(day)
                if not event:
                    continue
                incoming = make_entry(series, event, phase, now)
                signature = semantic_key(incoming)
                if signature in known_semantic or incoming["id"] in known_ids:
                    skipped_existing += 1
                    continue
                entries.append(incoming)
                known_semantic.add(signature)
                known_ids.add(incoming["id"])
                added += 1
                by_series[series_key] = by_series.get(series_key, 0) + 1

    entries.sort(
        key=lambda x: (
            clean(x.get("eventDate")) or "9999",
            clean(x.get("applyStart")) or clean(x.get("applyEnd")) or "9999",
            clean(x.get("group")),
            clean(x.get("ticketType")),
        )
    )
    result = dict(history)
    result["version"] = history.get("version") or 1
    result["updatedAt"] = now
    result["entries"] = entries
    stats = {
        "before": len(history.get("entries") or []),
        "after": len(entries),
        "added": added,
        "skippedExisting": skipped_existing,
        "addedBySeries": by_series,
    }
    return result, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill verified historical ticket phases from curated direct official sources.")
    parser.add_argument("--check", action="store_true", help="Validate and calculate the merge without writing.")
    args = parser.parse_args()

    backfill = load(BACKFILL_PATH)
    history = load(HISTORY_PATH)
    registry = load(REGISTRY_PATH)
    errors = validate(backfill, registry)
    if errors:
        print(json.dumps({"status": "blocked", "errors": errors}, ensure_ascii=False, indent=2))
        return 2

    now = datetime.now(JST).isoformat(timespec="seconds")
    result, stats = apply_backfill(backfill, history, now)
    print(json.dumps({"status": "ok", **stats}, ensure_ascii=False, indent=2))
    if args.check:
        return 0
    HISTORY_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
