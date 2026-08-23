#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

PAGE = Path("schedule.html")


def main() -> int:
    page = PAGE.read_text(encoding="utf-8")

    # Strict-mode JavaScript must declare the computed week height.
    page = page.replace(
        "mbase=bbase+bl*44+10;height=mbase+ml*30+12;",
        "mbase=bbase+bl*44+10;var height=mbase+ml*30+12;",
    )

    required = (
        'id="snapshot-data"',
        "function effectiveBand(e)",
        "function lane(items)",
        "function prepare(raw)",
        "FC先行・アップグレードを除いて原則すべて採用",
    )
    missing = [token for token in required if token not in page]
    if missing:
        raise RuntimeError(f"schedule shell invariant missing: {missing}")

    # Extract the executable inline script for node --check in CI.
    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", page, re.S)
    executable = [s for s in scripts if "(function(){'use strict';" in s]
    if len(executable) != 1:
        raise RuntimeError(f"expected one executable inline script, found {len(executable)}")
    Path("/tmp/schedule-inline.js").write_text(executable[0], encoding="utf-8")

    PAGE.write_text(page, encoding="utf-8")
    print("Schedule shell checked and normalized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
