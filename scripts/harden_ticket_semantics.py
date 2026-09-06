#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

DATA_PATH = Path("data/live-events.json")


def event_text(event: dict) -> str:
    return " ".join(
        str(event.get(key) or "")
        for key in ("title", "eventTitle", "displayTitle")
    )


def harden_event(event: dict) -> tuple[dict, list[str]]:
    row = dict(event)
    changes: list[str] = []
    text = event_text(row)

    # Upgrade announcements are an additional ticket entitlement for an
    # existing performance, never an ordinary FC presale. Some official pages
    # mention annual-membership eligibility in the body, which previously made
    # the generic parser classify the row as 年会費コース会員先行.
    if "アップグレード" in text and row.get("ticketType") != "アップグレード抽選":
        row["ticketType"] = "アップグレード抽選"
        changes.append("upgrade-ticket-type")

    return row, changes


def harden_payload(payload: dict) -> tuple[dict, dict]:
    hardened: list[dict] = []
    changed: list[dict] = []

    for original in payload.get("events", []):
        if not isinstance(original, dict):
            continue
        row, reasons = harden_event(original)
        hardened.append(row)
        if reasons:
            changed.append({
                "id": row.get("id"),
                "group": row.get("group"),
                "title": row.get("title") or row.get("eventTitle"),
                "changes": reasons,
            })

    out = dict(payload)
    out["events"] = hardened
    return out, {"changedCount": len(changed), "changed": changed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Harden ticket semantics before calendar publication")
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.data.read_text(encoding="utf-8"))
    hardened, report = harden_payload(payload)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.check:
        return 1 if report["changedCount"] else 0

    if hardened != payload:
        args.data.write_text(json.dumps(hardened, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
