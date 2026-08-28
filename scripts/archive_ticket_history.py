#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

LIVE_PATH = Path("data/live-events.json")
HISTORY_PATH = Path("data/ticket-history.json")
REGISTRY_PATH = Path("data/ticket-source-registry.json")
JST = ZoneInfo("Asia/Tokyo")

SPECIAL_CATEGORIES = {
    "release-event",
    "large-benefit",
    "benefit-event",
    "online-benefit",
}


def load_json(path: Path, fallback: dict | None = None) -> dict:
    if not path.exists():
        return dict(fallback or {})
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(fallback or {})
    return value if isinstance(value, dict) else dict(fallback or {})


def clean(value: object) -> str:
    return str(value or "").strip()



def canonical_source_url(url: str) -> str:
    text = clean(url)
    if not text:
        return ""
    try:
        parsed = urlparse(text)
    except ValueError:
        return text
    host = (parsed.hostname or "").lower()
    tracking = {"p1", "fbclid", "gclid", "_ga"}
    pairs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lower = key.lower()
        if lower in tracking or lower.startswith("utm_"):
            continue
        pairs.append((key, value))
    query = urlencode(pairs, doseq=True)
    netloc = parsed.netloc.lower() if host else parsed.netloc
    return urlunparse((parsed.scheme.lower(), netloc, parsed.path, parsed.params, query, ""))


def source_key_for_url(url: str, registry: dict) -> str | None:
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


def source_config(source_key: str | None, registry: dict) -> dict:
    if not source_key:
        return {}
    value = (registry.get("sources") or {}).get(source_key)
    return value if isinstance(value, dict) else {}


def candidate_urls(event: dict) -> list[str]:
    values: list[str] = []
    for key in ("applicationWindowSource", "deadlineSource", "url"):
        value = clean(event.get(key))
        if value and value not in values:
            values.append(value)
    for value in event.get("urls") or []:
        text = clean(value)
        if text and text not in values:
            values.append(text)
    return values


def choose_direct_source(event: dict, registry: dict) -> tuple[str | None, str | None]:
    for url in candidate_urls(event):
        key = source_key_for_url(url, registry)
        config = source_config(key, registry)
        if key and config.get("publishPolicy") == "direct":
            return url, key
    return None, None


def event_dates(event: dict) -> list[str]:
    result: list[str] = []
    schedule = event.get("schedule")
    if isinstance(schedule, list):
        for row in schedule:
            if isinstance(row, dict):
                day = clean(row.get("date"))[:10]
                if day and day not in result:
                    result.append(day)
    dates = event.get("eventDates")
    if isinstance(dates, list):
        for value in dates:
            day = clean(value)[:10]
            if day and day not in result:
                result.append(day)
    if not result:
        day = clean(event.get("eventDate"))[:10]
        if day:
            result.append(day)
    return result


def title_for(event: dict) -> str:
    return clean(event.get("eventTitle") or event.get("displayTitle") or event.get("title"))


def window_completeness(event: dict) -> str:
    start = bool(clean(event.get("applyStart")))
    end = bool(clean(event.get("applyEnd")))
    if start and end:
        return "full"
    if start:
        return "start-only"
    if end:
        return "end-only"
    return "missing"


def verification_level(event: dict, source_key: str, registry: dict) -> str:
    if event.get("applicationWindowVerified") is True and event.get("deadlineVerified") is True:
        return "verified-fields"
    config = source_config(source_key, registry)
    if config.get("kind") == "official" and window_completeness(event) == "full":
        return "direct-official"
    if event.get("applicationWindowVerified") is True or event.get("deadlineVerified") is True:
        return "partially-verified-fields"
    return "direct-source-observation"


def publishable(event: dict, source_key: str, registry: dict) -> bool:
    config = source_config(source_key, registry)
    if config.get("publishPolicy") != "direct":
        return False
    if window_completeness(event) == "missing":
        return False
    if event.get("applicationWindowVerified") is True or event.get("deadlineVerified") is True:
        return True
    return config.get("kind") == "official" and window_completeness(event) == "full"


def history_identity(event: dict, source_url: str, source_key: str, day: str) -> str:
    source_url = canonical_source_url(source_url)
    parts = (
        clean(event.get("group")),
        title_for(event),
        day,
        clean(event.get("ticketType")),
        clean(event.get("ticketProvider") or event.get("primarySource") or source_key),
        source_url,
    )
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:20]


def snapshot_window(event: dict) -> dict:
    return {
        "applyStart": event.get("applyStart"),
        "applyEnd": event.get("applyEnd"),
        "resultDate": event.get("resultDate"),
        "paymentEnd": event.get("paymentEnd"),
    }


def make_entry(event: dict, source_url: str, source_key: str, day: str, registry: dict, now: str) -> dict:
    source_url = canonical_source_url(source_url)
    config = source_config(source_key, registry)
    return {
        "id": history_identity(event, source_url, source_key, day),
        "group": event.get("group"),
        "participants": event.get("participants") or [],
        "eventTitle": title_for(event),
        "eventDate": day,
        "venue": event.get("venue"),
        "ticketType": event.get("ticketType"),
        "ticketProvider": event.get("ticketProvider") or event.get("primarySource") or source_key,
        "saleFamily": event.get("saleFamily"),
        "applyStart": event.get("applyStart"),
        "applyEnd": event.get("applyEnd"),
        "resultDate": event.get("resultDate"),
        "paymentEnd": event.get("paymentEnd"),
        "sourceKey": source_key,
        "sourceLabel": config.get("label") or source_key,
        "sourceUrl": source_url,
        "sourcePublishedAt": event.get("sourcePublishedAt"),
        "verificationLevel": verification_level(event, source_key, registry),
        "windowCompleteness": window_completeness(event),
        "publishable": publishable(event, source_key, registry),
        "flowEligible": clean(event.get("eventCategory")) not in SPECIAL_CATEGORIES,
        "eventCategory": event.get("eventCategory"),
        "firstSeenAt": now,
        "lastSeenAt": now,
        "observedWindows": [snapshot_window(event)],
    }


def merge_entry(existing: dict, incoming: dict, now: str) -> dict:
    out = dict(existing)
    old_window = {
        "applyStart": out.get("applyStart"),
        "applyEnd": out.get("applyEnd"),
        "resultDate": out.get("resultDate"),
        "paymentEnd": out.get("paymentEnd"),
    }
    new_window = {
        "applyStart": incoming.get("applyStart"),
        "applyEnd": incoming.get("applyEnd"),
        "resultDate": incoming.get("resultDate"),
        "paymentEnd": incoming.get("paymentEnd"),
    }
    observations = [x for x in out.get("observedWindows") or [] if isinstance(x, dict)]
    if old_window not in observations:
        observations.append(old_window)
    if new_window not in observations:
        observations.append(new_window)

    for key, value in incoming.items():
        if key in {"firstSeenAt", "observedWindows"}:
            continue
        if value not in (None, "", []):
            out[key] = value
    out["firstSeenAt"] = existing.get("firstSeenAt") or incoming.get("firstSeenAt") or now
    out["lastSeenAt"] = now
    out["observedWindows"] = observations
    return out


def archive_payload(live: dict, history: dict, registry: dict, now: str) -> dict:
    entries = [dict(x) for x in history.get("entries", []) if isinstance(x, dict) and x.get("id")]
    by_id: dict[str, dict] = {}
    for existing in entries:
        canonical_url = canonical_source_url(clean(existing.get("sourceUrl")))
        source_key = clean(existing.get("sourceKey"))
        stub = {
            "group": existing.get("group"),
            "eventTitle": existing.get("eventTitle"),
            "ticketType": existing.get("ticketType"),
            "ticketProvider": existing.get("ticketProvider"),
        }
        canonical_id = history_identity(stub, canonical_url, source_key, clean(existing.get("eventDate")))
        existing["id"] = canonical_id
        existing["sourceUrl"] = canonical_url
        current = by_id.get(canonical_id)
        by_id[canonical_id] = merge_entry(current, existing, now) if current else existing

    for event in live.get("events", []):
        if not isinstance(event, dict):
            continue
        if clean(event.get("ticketType")) in {"", "現在受付なし"}:
            continue
        if window_completeness(event) == "missing":
            continue
        source_url, source_key = choose_direct_source(event, registry)
        if not source_url or not source_key:
            continue
        for day in event_dates(event):
            incoming = make_entry(event, source_url, source_key, day, registry, now)
            current = by_id.get(incoming["id"])
            by_id[incoming["id"]] = merge_entry(current, incoming, now) if current else incoming

    result = list(by_id.values())
    result.sort(key=lambda x: (
        clean(x.get("eventDate")) or "9999",
        clean(x.get("applyStart")) or clean(x.get("applyEnd")) or "9999",
        clean(x.get("group")),
        clean(x.get("ticketType")),
    ))
    return {
        "version": 1,
        "updatedAt": now,
        "sourceRegistryVersion": registry.get("version"),
        "entries": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Append direct-source ticket observations to a permanent history archive.")
    parser.add_argument("--check", action="store_true", help="Validate/preview without writing.")
    args = parser.parse_args()

    live = load_json(LIVE_PATH, {"events": []})
    registry = load_json(REGISTRY_PATH)
    history = load_json(HISTORY_PATH, {"version": 1, "entries": []})
    if not registry.get("sources") or not registry.get("hostRules"):
        raise SystemExit("ticket source registry is missing or invalid")

    now = datetime.now(JST).isoformat(timespec="seconds")
    result = archive_payload(live, history, registry, now)
    before = len(history.get("entries", []))
    after = len(result.get("entries", []))
    publishable_count = sum(1 for x in result["entries"] if x.get("publishable"))
    partial_count = sum(1 for x in result["entries"] if x.get("windowCompleteness") != "full")
    print(json.dumps({
        "historyBefore": before,
        "historyAfter": after,
        "newOrRecovered": max(0, after - before),
        "publishable": publishable_count,
        "partialWindows": partial_count,
    }, ensure_ascii=False, indent=2))

    if args.check:
        return 0
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
