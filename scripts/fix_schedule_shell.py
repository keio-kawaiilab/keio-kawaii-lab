#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

PAGE = Path("schedule.html")

# A performance must not become a second calendar/card item just because a
# ticket source phrases the title differently. Use the actual occurrence as
# the primary identity: group + date + kind + start time. When start time is
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


def replace_identity_block(page: str) -> str:
    """Replace the performance identity functions using stable JS anchors.

    Do not parse minified JavaScript functions with a regex: regex literals in
    the JS contain braces such as ``.{2,3}``, which look like function-closing
    braces to a non-JS parser. The next named function is a stable delimiter
    for both the legacy and current forms.
    """
    current_start = page.find("function performanceVenueKey(e,o)")
    legacy_start = page.find("function performanceKey(e,o)")
    if current_start >= 0:
        start = current_start
    elif legacy_start >= 0:
        start = legacy_start
    else:
        raise RuntimeError("could not locate performanceKey() in schedule.html")

    end = page.find("function performanceKeyForEvent", start)
    if end < 0:
        raise RuntimeError("could not locate performanceKeyForEvent() in schedule.html")

    return page[:start] + PERFORMANCE_KEY_JS + page[end:]


def main() -> int:
    page = PAGE.read_text(encoding="utf-8")
    page = replace_identity_block(page)

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

    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", page, re.S)
    executable = [script for script in scripts if "(function(){'use strict';" in script]
    if len(executable) != 1:
        raise RuntimeError(f"expected one executable inline script, found {len(executable)}")

    Path("/tmp/schedule-inline.js").write_text(executable[0], encoding="utf-8")
    PAGE.write_text(page, encoding="utf-8")
    print("Schedule performance identity normalized by occurrence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
