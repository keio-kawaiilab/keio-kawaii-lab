#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

DATA_PATH = Path("data/live-events.json")
INDEX_PATH = Path("data/official-schedule-index.json")


def reconcile(payload: dict, index: dict) -> tuple[dict, dict]:
    events = [dict(event) for event in payload.get("events", []) if isinstance(event, dict)]
    by_id = {str(event.get("id") or ""): event for event in events if event.get("id")}
    touched = 0
    missing_ids: list[str] = []
    links_added = 0

    for entry in index.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        represented_by = str(entry.get("representedBy") or "")
        official_url = str(entry.get("url") or "").strip()
        if not represented_by or not official_url:
            continue
        event = by_id.get(represented_by)
        if event is None:
            missing_ids.append(represented_by)
            continue

        changed = False
        urls = [str(value) for value in event.get("urls") or [] if value]
        primary_url = str(event.get("url") or "").strip()
        if primary_url and primary_url not in urls:
            urls.insert(0, primary_url)
        if official_url not in urls:
            urls.append(official_url)
            links_added += 1
            changed = True
        if event.get("officialScheduleUrl") != official_url:
            event["officialScheduleUrl"] = official_url
            changed = True
        event["urls"] = list(dict.fromkeys(urls))
        if changed:
            touched += 1

    out = dict(payload)
    out["events"] = events
    report = {
        "officialEntries": len([x for x in index.get("entries") or [] if isinstance(x, dict)]),
        "eventsTouched": touched,
        "linksAdded": links_added,
        "missingRepresentedIds": sorted(set(missing_ids)),
    }
    return out, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore official schedule URLs after distributed source merge")
    parser.add_argument("--data", default=str(DATA_PATH))
    parser.add_argument("--index", default=str(INDEX_PATH))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    data_path = Path(args.data)
    index_path = Path(args.index)
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    index = json.loads(index_path.read_text(encoding="utf-8"))
    result, report = reconcile(payload, index)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if report["missingRepresentedIds"]:
        raise SystemExit(
            "Official schedule index references missing event ids: "
            + ", ".join(report["missingRepresentedIds"][:20])
        )
    if args.check:
        if result != payload:
            raise SystemExit("Official schedule links are not reconciled")
        return 0

    data_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
