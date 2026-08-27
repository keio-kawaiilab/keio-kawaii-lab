#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

SOURCE_PATH = Path("data/ticket-history-backfill-oneoffs.json")
HISTORY_PATH = Path("data/ticket-history.json")
REGISTRY_PATH = Path("data/ticket-source-registry.json")
JST = ZoneInfo("Asia/Tokyo")


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def clean(value: object) -> str:
    return str(value or "").strip()


def mapped_source(url: str, registry: dict) -> str | None:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return None
    rules = registry.get("hostRules") or {}
    if host in rules:
        return str(rules[host])
    for known_host, key in rules.items():
        if host.endswith("." + str(known_host).lower()):
            return str(key)
    return None


def validate(payload: dict, registry: dict) -> list[str]:
    errors: list[str] = []
    configs = registry.get("sources") or {}
    seen: set[str] = set()
    for index, series in enumerate(payload.get("series") or []):
        key = clean(series.get("key"))
        label = key or f"series[{index}]"
        if not key:
            errors.append(f"series[{index}] missing key")
        elif key in seen:
            errors.append(f"duplicate series key: {key}")
        seen.add(key)
        if not clean(series.get("group")) or not clean(series.get("eventTitle")):
            errors.append(f"{label}: missing group/eventTitle")
        events = [x for x in series.get("events") or [] if isinstance(x, dict)]
        event_dates = {clean(x.get("date")) for x in events if clean(x.get("date"))}
        if not event_dates:
            errors.append(f"{label}: no event dates")
        for p_index, phase in enumerate(series.get("phases") or []):
            p_label = f"{label}/phase[{p_index}]"
            for field in ("ticketType", "applyEnd", "sourceKey", "sourceUrl"):
                if not clean(phase.get(field)):
                    errors.append(f"{p_label}: missing {field}")
            source_key = clean(phase.get("sourceKey"))
            source_url = clean(phase.get("sourceUrl"))
            config = configs.get(source_key)
            if not isinstance(config, dict) or config.get("publishPolicy") != "direct":
                errors.append(f"{p_label}: sourceKey {source_key!r} is not direct")
            if source_url and mapped_source(source_url, registry) != source_key:
                errors.append(f"{p_label}: sourceUrl does not map to {source_key!r}")
            for evidence in phase.get("evidenceUrls") or []:
                evidence_key = mapped_source(clean(evidence), registry)
                evidence_config = configs.get(evidence_key) if evidence_key else None
                if not isinstance(evidence_config, dict) or evidence_config.get("publishPolicy") != "direct":
                    errors.append(f"{p_label}: non-direct evidenceUrl {evidence!r}")
            targets = {clean(x) for x in phase.get("dates") or event_dates}
            unknown = targets - event_dates
            if unknown:
                errors.append(f"{p_label}: unknown dates {sorted(unknown)}")
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


def make_id(series_key: str, day: str, phase: dict) -> str:
    raw = "\x1f".join((
        "oneoff-backfill-v1", series_key, day,
        clean(phase.get("ticketType")), clean(phase.get("applyStart")),
        clean(phase.get("applyEnd")), clean(phase.get("ticketProvider")),
    ))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def make_entry(series: dict, event: dict, phase: dict, now: str) -> dict:
    start = phase.get("applyStart")
    end = phase.get("applyEnd")
    evidence = [clean(x) for x in phase.get("evidenceUrls") or [] if clean(x)]
    return {
        "id": make_id(clean(series.get("key")), clean(event.get("date")), phase),
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
        "sourceKey": phase.get("sourceKey"),
        "sourceLabel": phase.get("sourceLabel") or phase.get("sourceKey"),
        "sourceUrl": phase.get("sourceUrl"),
        "evidenceUrls": evidence,
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
        "observedWindows": [{
            "applyStart": start,
            "applyEnd": end,
            "resultDate": phase.get("resultDate"),
            "paymentEnd": phase.get("paymentEnd"),
        }],
    }


def merge(payload: dict, history: dict, now: str) -> tuple[dict, dict]:
    entries = [dict(x) for x in history.get("entries") or [] if isinstance(x, dict) and x.get("id")]
    signatures = {semantic_key(x) for x in entries}
    ids = {clean(x.get("id")) for x in entries}
    added = 0
    skipped = 0
    by_series: dict[str, int] = {}
    for series in payload.get("series") or []:
        series_key = clean(series.get("key"))
        events = {clean(x.get("date")): x for x in series.get("events") or [] if isinstance(x, dict)}
        for phase in series.get("phases") or []:
            targets = [clean(x) for x in phase.get("dates") or events.keys()]
            for day in targets:
                event = events.get(day)
                if not event:
                    continue
                incoming = make_entry(series, event, phase, now)
                signature = semantic_key(incoming)
                if signature in signatures or incoming["id"] in ids:
                    skipped += 1
                    continue
                entries.append(incoming)
                signatures.add(signature)
                ids.add(incoming["id"])
                added += 1
                by_series[series_key] = by_series.get(series_key, 0) + 1
    entries.sort(key=lambda x: (
        clean(x.get("eventDate")) or "9999",
        clean(x.get("applyStart")) or clean(x.get("applyEnd")) or "9999",
        clean(x.get("group")), clean(x.get("ticketType")),
    ))
    result = dict(history)
    result["updatedAt"] = now
    result["entries"] = entries
    return result, {
        "before": len(history.get("entries") or []),
        "after": len(entries),
        "added": added,
        "skippedExisting": skipped,
        "addedBySeries": by_series,
        "pendingDirectVerification": len(payload.get("pendingDirectVerification") or []),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = load(SOURCE_PATH)
    history = load(HISTORY_PATH)
    registry = load(REGISTRY_PATH)
    errors = validate(payload, registry)
    if errors:
        print(json.dumps({"status":"blocked","errors":errors}, ensure_ascii=False, indent=2))
        return 2
    now = datetime.now(JST).isoformat(timespec="seconds")
    result, stats = merge(payload, history, now)
    print(json.dumps({"status":"ok", **stats}, ensure_ascii=False, indent=2))
    if not args.check:
        HISTORY_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
