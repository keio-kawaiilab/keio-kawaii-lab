#!/usr/bin/env python3
from pathlib import Path
import re

PATH = Path("schedule.html")

# Public identity rules:
# - ordinary performances: same group + day + verified start time => one card
# - release events / large benefit events: same group + day => one card
#   Their internal parts, sales rows, venue spellings and source titles must never
#   split one calendar day into multiple public cards.
NEW_FUNCTION = "function performanceKey(e,o){var day=String((o&&o.date)||e.eventDate||'').slice(0,10),time=String((o&&o.startTime)||e.startTime||'').replace(/\\s+/g,''),venue=performanceVenueKey(e,o),titleKey=performanceTitleKey(e),group=String(e.group||'').trim();if(e.eventCategory==='release-event'||e.eventCategory==='large-benefit')return [group,day,'special'].join('|');if(day&&time)return [group,day,'time',time].join('|');return [group,day,'fallback',venue,titleKey].join('|')}"


def main() -> None:
    source = PATH.read_text(encoding="utf-8")

    # Replace whichever performanceKey implementation the snapshot/release shell
    # generated. Keep the replacement bounded by performanceKeyForEvent so this
    # stays safe even when the minified implementation changes shape.
    start = source.find("function performanceKey(e,o)")
    end = source.find("function performanceKeyForEvent", start)
    if start < 0 or end < 0:
        raise SystemExit("performanceKey target not found; refusing a silent no-op")

    updated = source[:start] + NEW_FUNCTION + source[end:]

    # Make the loader URL change as well, so clients do not keep an old helper.
    updated = re.sub(
        r"schedule-weather\.js\?v=[A-Za-z0-9_-]+",
        "schedule-weather.js?v=202609071052",
        updated,
        count=1,
    )

    function_match = re.search(r"function performanceKey\(e,o\)\{.*?\}", updated, re.S)
    if not function_match:
        raise SystemExit("performanceKey missing after patch")
    block = function_match.group(0)
    if "kind=eventKind(e)" in block:
        raise SystemExit("eventKind is still part of ordinary performance identity")
    required = "if(e.eventCategory==='release-event'||e.eventCategory==='large-benefit')return [group,day,'special'].join('|')"
    if required not in block:
        raise SystemExit("same-day special-event identity is missing")

    if updated != source:
        PATH.write_text(updated, encoding="utf-8")
        print("schedule.html hardened: ordinary shows use time; special events use one card per group/day")
    else:
        print("schedule.html already hardened")


if __name__ == "__main__":
    main()
