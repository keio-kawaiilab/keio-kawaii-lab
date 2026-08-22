#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

DATA_PATH = Path("data/live-events.json")
TITLE_PREFIX_RE = re.compile(r"^20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+")


def clean_title(value: str) -> str:
    return TITLE_PREFIX_RE.sub("", str(value or "")).strip()


def sanitize_payload(payload: dict) -> dict:
    cleaned = dict(payload)
    events = []
    seen = set()

    for original in payload.get("events", []):
        if not isinstance(original, dict):
            continue
        event = dict(original)
        event["title"] = clean_title(event.get("title", ""))

        event_date = str(event.get("eventDate") or "")[:10]
        result_date = str(event.get("resultDate") or "")[:10]
        # 当落発表日時を公演日時と誤認したデータは表示しない。
        if event_date and result_date and event_date == result_date:
            continue

        key = (
            event.get("group"), event.get("url"), event_date,
            event.get("ticketType"), event.get("applyStart"),
        )
        if key in seen:
            continue
        seen.add(key)
        events.append(event)

    cleaned["events"] = events
    return cleaned


def main() -> int:
    if not DATA_PATH.exists():
        return 0
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    cleaned = sanitize_payload(payload)
    DATA_PATH.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Sanitized live calendar data: {len(payload.get('events', []))} -> {len(cleaned.get('events', []))} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
