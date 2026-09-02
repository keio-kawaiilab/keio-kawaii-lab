#!/usr/bin/env python3
"""Compatibility entrypoint for official-X event collection.

Run two independent generic special-event discovery surfaces plus the
birthday-specific enrichment collector.  Birthday success must never mask a
failure of ordinary release-event / large-benefit / solo-event monitoring.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(script: str) -> tuple[str, int]:
    completed = subprocess.run([sys.executable, str(ROOT / script)], check=False)
    return script, completed.returncode


def main() -> int:
    profile = run("update_official_x_special_events.py")
    syndication = run("update_official_x_special_events_syndication.py")
    birthday = run("update_official_x_birthday_events.py")
    results = [profile, syndication, birthday]
    print(json.dumps({"officialXCollectors": dict(results)}, ensure_ascii=False, indent=2))

    # The calendar's generic special-event monitor is healthy only when at
    # least one independent generic discovery path completed successfully.
    # Birthday monitoring is supplementary and can no longer make a broken
    # release-event monitor look healthy.
    generic_ok = profile[1] == 0 or syndication[1] == 0
    return 0 if generic_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
