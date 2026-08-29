#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

PAGE = Path("schedule.html")

# Public schedule identity is based on the actual performance, not the sale row.
# Normal live performances can have two shows on the same day, so a verified
# start time remains part of their identity. Release events and large benefit
# events are different: the same physical event is often published once per
# sales channel/part, with different startTime values. For those special-event
# kinds, collapse by group + date + kind + venue + visible event title so the
# public card/calendar mark appears once while performanceModels() keeps every
# sale row as a separate offer inside that one card.
PERFORMANCE_KEY_JS = (
    "function performanceVenueKey(e,o){var v=String((o&&o.venue)||e.venue||'').toLowerCase();"
    "v=v.replace(/^(?:北海道|東京都|京都府|大阪府|.{2,3}県)\\s*/,'').replace(/\\s+/g,'').replace(/[!！・|｜\\-–—_\\[\\]()（）『』「」]/g,'');return v}"
    "function performanceKey(e,o){var day=String((o&&o.date)||'').slice(0,10),kind=eventKind(e),"
    "time=String((o&&o.startTime)||e.startTime||'').replace(/\\s+/g,''),venue=performanceVenueKey(e,o),titleKey=performanceTitleKey(e),base=[String(e.group||''),day,kind];"
    "if(kind==='release'||kind==='benefit')return base.concat(['special',venue,titleKey]).join('|');"
    "if(time)return base.concat(['time',time]).join('|');"
    "return base.concat(['fallback',venue,titleKey]).join('|')}"
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
        "kind==='release'||kind==='benefit'",
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
    print("Schedule performance identity normalized across sale rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
