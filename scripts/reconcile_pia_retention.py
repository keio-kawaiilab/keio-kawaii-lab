#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
DATA_PATH = Path("data/live-events.json")
LOT_RE = re.compile(r"[?&]lotRlsCd=([A-Za-z0-9_-]+)")


def is_pia(event: dict) -> bool:
    urls = [str(event.get("url") or "")] + [str(x) for x in (event.get("urls") or [])]
    return (
        str(event.get("sourceType") or "").lower() == "pia"
        or str(event.get("primarySource") or "").lower() == "pia"
        or any("t.pia.jp" in url for url in urls)
    )


def source_key(event: dict) -> str | None:
    urls = [str(event.get("url") or "")] + [str(x) for x in (event.get("urls") or [])]
    for url in urls:
        match = LOT_RE.search(url)
        if match:
            return f"lot:{match.group(1)}"
    for url in urls:
        if "t.pia.jp" in url:
            return f"url:{url.split('#', 1)[0]}"
    value = str(event.get("id") or "").strip()
    return f"id:{value}" if value else None


def parse_day(value: object):
    text = str(value or "")[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def known_active(event: dict, today=None) -> bool:
    if today is None:
        today = datetime.now(JST).date()
    if not is_pia(event):
        return False
    if event.get("ticketType") == "現在受付なし" or event.get("applicationStatus") == "none":
        return False
    deadline = parse_day(event.get("applyEnd"))
    return bool(deadline and deadline >= today)


def is_bad_title(value: object) -> bool:
    text = str(value or "")
    return bool(re.search(r"行きたい\s*[!！]?\s*公演アラート|お気に入り|メールで通知", text, re.I))


def reconcile(current_events: list[dict], previous_events: list[dict], today=None):
    if today is None:
        today = datetime.now(JST).date()

    out = [dict(x) for x in current_events]
    index: dict[str, int] = {}
    for i, event in enumerate(out):
        key = source_key(event)
        if key and is_pia(event):
            index[key] = i

    retained = []
    enriched = []
    for previous in previous_events:
        if not known_active(previous, today):
            continue
        key = source_key(previous)
        if not key:
            continue

        if key not in index:
            copy = dict(previous)
            copy["retainedFromPreviousPiaRun"] = True
            copy["piaRetentionReason"] = "not rediscovered; kept until known deadline"
            copy["sourceStale"] = True
            out.append(copy)
            index[key] = len(out) - 1
            retained.append(key)
            continue

        current = out[index[key]]
        changed = False
        # Never lose an already-known exact deadline just because this scrape returned
        # a thinner row. Start times are intentionally NOT copied here.
        if not current.get("applyEnd") and previous.get("applyEnd"):
            current["applyEnd"] = previous.get("applyEnd")
            current["deadlineRecoveredFromPreviousRun"] = True
            changed = True
        if is_bad_title(current.get("title")) and previous.get("title") and not is_bad_title(previous.get("title")):
            current["title"] = previous.get("title")
            if previous.get("eventTitle"):
                current["eventTitle"] = previous.get("eventTitle")
            current["titleRecoveredFromPreviousRun"] = True
            changed = True
        if changed:
            enriched.append(key)

    return out, retained, enriched


def main() -> int:
    parser = argparse.ArgumentParser(description="Retain known-active Ticket Pia sales across transient scrape misses.")
    parser.add_argument("--previous", required=True)
    args = parser.parse_args()

    current_payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    previous_payload = json.loads(Path(args.previous).read_text(encoding="utf-8"))
    current_events = [x for x in current_payload.get("events", []) if isinstance(x, dict)]
    previous_events = [x for x in previous_payload.get("events", []) if isinstance(x, dict)]

    merged, retained, enriched = reconcile(current_events, previous_events)
    current_payload["events"] = merged
    DATA_PATH.write_text(json.dumps(current_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "retainedKnownActivePia": retained,
        "enrichedFromPreviousPia": enriched,
        "eventCount": len(merged),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
