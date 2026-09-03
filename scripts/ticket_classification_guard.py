#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import ticket_history_guard as guard

DATA_PATH = Path("data/live-events.json")
HISTORY_PATH = Path("data/ticket-history.json")
JST = timezone(timedelta(hours=9))


def run(check: bool = False) -> dict:
    original_payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    payload = json.loads(json.dumps(original_payload, ensure_ascii=False))
    history = (
        json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        if HISTORY_PATH.exists()
        else {"version": 1, "entries": []}
    )
    original_history = json.loads(json.dumps(history, ensure_ascii=False))

    session = guard.make_session()
    try:
        invalid_sources, failures = guard.validate_annual_fee_rows(payload, session)
    finally:
        session.close()

    removed_history = guard.purge_invalid_history(history, invalid_sources)
    changed_live = payload != original_payload
    changed_history = history != original_history
    now = datetime.now(JST).isoformat(timespec="seconds")

    if not check:
        if changed_live:
            payload["updatedAt"] = now
            DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if changed_history:
            history["updatedAt"] = now
            HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "checkedAt": now,
        "invalidAnnualFeeSources": invalid_sources,
        "invalidHistoryEntriesRemoved": removed_history,
        "changedLive": changed_live,
        "changedHistory": changed_history,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Quarantine unsupported ticket classifications before publication.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(check=args.check), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
