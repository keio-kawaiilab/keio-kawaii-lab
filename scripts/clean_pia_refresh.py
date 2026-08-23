#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

DATA_PATH = Path("data/live-events.json")


def urls(event: dict) -> list[str]:
    result = [str(event.get("url") or "")]
    result.extend(str(x) for x in (event.get("urls") or []))
    return [x for x in result if x]


def pia_origin(event: dict) -> bool:
    return (
        str(event.get("sourceType") or "").lower() == "pia"
        or str(event.get("primarySource") or "").lower() == "pia"
        or any("t.pia.jp" in url for url in urls(event))
    )


def clean(events: list[dict], drop_all: bool = False) -> tuple[list[dict], list[str]]:
    fresh_groups = {
        str(event.get("group") or "")
        for event in events
        if str(event.get("sourceType") or "").lower() == "pia"
    }
    removed: list[str] = []
    kept: list[dict] = []
    for event in events:
        group = str(event.get("group") or "")
        source_type = str(event.get("sourceType") or "").lower()
        should_remove = pia_origin(event) and (
            drop_all or (group in fresh_groups and source_type != "pia")
        )
        if should_remove:
            removed.append(str(event.get("id") or ""))
            continue
        kept.append(event)
    return kept, removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove stale Ticket Pia-derived rows before or after a refresh.")
    parser.add_argument("--drop-all", action="store_true", help="Remove all Pia-origin rows so the next scrape starts clean.")
    args = parser.parse_args()

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    events = [dict(x) for x in payload.get("events", []) if isinstance(x, dict)]
    cleaned, removed = clean(events, drop_all=args.drop_all)
    payload["events"] = cleaned
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "mode": "drop-all" if args.drop_all else "replace-derived",
        "removedPiaOrigin": removed,
        "eventCount": len(cleaned),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
