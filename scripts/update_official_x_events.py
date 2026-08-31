#!/usr/bin/env python3
"""Compatibility entrypoint for official-X event collection.

The distributed workflow historically invokes this filename. Keep that public
entrypoint stable and fan it out to both the general special-event collector and
the birthday-specific syndication fallback so birthday announcements cannot be
lost just because one X surface is unavailable.
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
    results = [
        run("update_official_x_special_events.py"),
        run("update_official_x_birthday_events.py"),
    ]
    print(json.dumps({"officialXCollectors": dict(results)}, ensure_ascii=False, indent=2))

    # The birthday syndication collector is deliberately fail-soft and preserves
    # last-good data. The generic X page can be intermittently unavailable, so
    # do not block all schedule publication when only that redundant surface
    # fails. A total wrapper failure is reserved for the impossible case where
    # both child entrypoints fail before completing their own safety behavior.
    return 0 if any(code == 0 for _, code in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
