#!/usr/bin/env python3
"""Compatibility entrypoint for fallback special-event discovery.

Run independent discovery surfaces for ordinary release-event / large-benefit
announcements, official-X solo-event announcements, and birthday enrichment.
The PR TIMES collector is intentionally part of this production entrypoint so
body-only ASOBISYSTEM release schedules are discovered by the normal 15-minute
calendar refresh rather than by a health-check-only workflow.
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
    prtimes = run("update_official_press_release_events.py")
    birthday = run("update_official_x_birthday_events.py")
    results = [profile, syndication, prtimes, birthday]
    print(json.dumps({"specialEventFallbackCollectors": dict(results)}, ensure_ascii=False, indent=2))

    # Release-event / large-benefit discovery must remain publishable when X is
    # rate-limited, as long as the independent verified ASOBISYSTEM PR TIMES
    # path succeeds.  Conversely, PR TIMES failure must not suppress a healthy
    # official-X refresh. Birthday monitoring is supplementary and never masks
    # a failure of all ordinary special-event discovery paths.
    generic_special_ok = profile[1] == 0 or syndication[1] == 0 or prtimes[1] == 0
    return 0 if generic_special_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
