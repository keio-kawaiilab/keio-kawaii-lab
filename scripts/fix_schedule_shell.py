#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

PAGE = Path("schedule.html")

# A performance must not become a second calendar/card item just because a
# ticket source phrases the title differently.  Use the actual occurrence as
# the primary identity: group + date + kind + start time.  When start time is
# unavailable, fall back to normalized venue + visible title so genuinely
# different same-day events are not collapsed blindly.
PERFORMANCE_KEY_JS = (
    "function performanceVenueKey(e,o){var v=String((o&&o.venue)||e.venue||'').toLowerCase();"
    "v=v.replace(/^(?:北海道|東京都|京都府|大阪府|.{2,3}県)\\s*/,'').replace(/\\s+/g,'').replace(/[!！・|｜\\-–—_\\[\\]()（）『』「」]/g,'');return v}"
    "function performanceKey(e,o){var day=String((o&&o.date)||'').slice(0,10),kind=eventKind(e),"
    "time=String((o&&o.startTime)||e.startTime||'').replace(/\\s+/g,''),base=[String(e.group||''),day,kind];"
    "if(time)return base.concat(['time',time]).join('|');"
    "return base.concat(['fallback',performanceVenueKey(e,o),performanceTitleKey(e)]).join('|')}"
)


def literal_replacement(_match: re.Match[str]) -> str:
    """Return JavaScript verbatim instead of letting re.sub parse backslashes."""
    return PERFORMANCE_KEY_JS


def main() -> int:
    page = PAGE.read_text(encoding="utf-8")

    # Remove a previous helper if this script has already been applied.
    page = re.sub(
        r"function performanceVenueKey\(e,o\)\{.*?\}(?=function performanceKey\(e,o\))",
        "",
        page,
        count=1,
        flags=re.S,
    )

    pattern = (
        r"function performanceKey\(e,o\)\{"
        r"return\[String\(e\.group\|\|''\),String\(o\.date\|\|''\)\.slice\(0,10\),"
        r"eventKind\(e\),performanceTitleKey\(e\)\]\.join\('\|'\)\}"
    )
    page, count = re.subn(pattern, literal_replacement, page, count=1)

    if count != 1:
        # Also accept the occurrence-based form on repeated workflow runs and
        # replace it deterministically with the current definition.
        page, count = re.subn(
            r"function performanceVenueKey\(e,o\)\{.*?\}function performanceKey\(e,o\)\{.*?\}(?=function performanceKeyForEvent)",
            literal_replacement,
            page,
            count=1,
            flags=re.S,
        )

    if count != 1:
        raise RuntimeError("could not locate performanceKey() in schedule.html")

    required = (
        "function performanceTitleKey(e)",
        "function performanceVenueKey(e,o)",
        "function performanceKey(e,o)",
        "function performanceModels(vis)",
        "perfSeen[pk]",
        "data-performance-key",
    )
    missing = [token for token in required if token not in page]
    if missing:
        raise RuntimeError(f"schedule performance identity invariant missing: {missing}")

    scripts = re.findall(r"<script(?:\\s[^>]*)?>(.*?)</script>", page, re.S)
    executable = [script for script in scripts if "(function(){'use strict';" in script]
    if len(executable) != 1:
        raise RuntimeError(f"expected one executable inline script, found {len(executable)}")

    Path("/tmp/schedule-inline.js").write_text(executable[0], encoding="utf-8")
    PAGE.write_text(page, encoding="utf-8")
    print("Schedule performance identity normalized by occurrence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
