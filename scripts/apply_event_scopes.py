#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from schedule_scope import apply_event_scope

DATA_PATH = Path("data/live-events.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply the shared hosted/external schedule classification.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    original = [event for event in payload.get("events", []) if isinstance(event, dict)]
    updated = [apply_event_scope(event) for event in original]
    missing = sum(1 for event in original if not event.get("eventScope"))
    invalid = [event.get("id") for event in updated if event.get("eventScope") not in {"kawaii-lab", "external"}]
    if invalid:
        raise SystemExit(f"Invalid eventScope values: {invalid}")
    if args.check:
        if missing:
            raise SystemExit(f"{missing} events have no eventScope")
        print(f"Event scope check passed: {len(updated)} events")
        return 0
    payload["events"] = updated
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Applied event scopes: {len(updated)} events ({missing} newly classified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
