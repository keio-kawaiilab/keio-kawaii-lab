#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

DATA = Path("data/live-events.json")
OUTPUT = Path("live-runtime-fallback.js")


def load_events(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        events = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("publicEvents"), list):
            events = payload["publicEvents"]
        else:
            events = payload.get("events")
    else:
        events = None

    if not isinstance(events, list) or not events:
        raise SystemExit("runtime fallback build: canonical calendar has no event list")

    cleaned = [event for event in events if isinstance(event, dict)]
    if not cleaned:
        raise SystemExit("runtime fallback build: canonical calendar has no usable events")
    return cleaned


def main() -> int:
    events = load_events(DATA)
    # Keep the fallback payload structurally equivalent to the normal JSON path.
    # Compact JSON keeps the extra static asset small while preserving every
    # occurrence, schedule row and source field used by the public renderer.
    payload = json.dumps(events, ensure_ascii=False, separators=(",", ":"))
    OUTPUT.write_text(f"window.KL_LIVE_FALLBACK={payload};\n", encoding="utf-8")
    print(f"runtime fallback rebuilt from canonical calendar: {len(events)} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
