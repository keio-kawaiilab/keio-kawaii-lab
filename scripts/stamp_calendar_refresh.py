#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_DATA = Path("data/live-events.json")
JST = ZoneInfo("Asia/Tokyo")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Advance the public calendar refresh timestamp after a successful refresh/build."
    )
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    args = parser.parse_args()

    payload = json.loads(args.data.read_text(encoding="utf-8"))
    stamp = datetime.now(JST).replace(microsecond=0).isoformat()

    # `checkedAt` is used by freshness monitoring. `updatedAt` remains the
    # user-visible compatibility field, so both must move together whenever a
    # successful public refresh is published.
    payload["checkedAt"] = stamp
    payload["updatedAt"] = stamp
    args.data.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(stamp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
