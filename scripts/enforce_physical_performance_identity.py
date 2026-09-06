#!/usr/bin/env python3
from pathlib import Path
import re

PATH = Path("schedule.html")

NEW_FUNCTION = "function performanceKey(e,o){var day=String((o&&o.date)||e.eventDate||'').slice(0,10),time=String((o&&o.startTime)||e.startTime||'').replace(/\\s+/g,''),venue=performanceVenueKey(e,o),titleKey=performanceTitleKey(e),group=String(e.group||'').trim();if(day&&time)return [group,day,'time',time].join('|');return [group,day,'fallback',venue,titleKey].join('|')}"


def main() -> None:
    source = PATH.read_text(encoding="utf-8")

    pattern = re.compile(
        r"function performanceKey\(e,o\)\{.*?return base\.concat\(\['fallback',venue,titleKey\]\)\.join\('\|'\)\}",
        re.S,
    )
    updated, count = pattern.subn(NEW_FUNCTION, source, count=1)

    if count == 0:
        # Idempotent success if the hardened function is already present.
        if NEW_FUNCTION not in source:
            raise SystemExit("performanceKey target not found; refusing a silent no-op")
        updated = source

    # Always make the active helper-loader URL change when this guard is applied,
    # so browsers cannot keep an old dedupe helper behind a stale fixed query URL.
    updated = re.sub(
        r"schedule-weather\.js\?v=[A-Za-z0-9_-]+",
        "schedule-weather.js?v=202609062135",
        updated,
        count=1,
    )

    if "kind=eventKind(e)" in re.search(
        r"function performanceKey\(e,o\)\{.*?\}", updated, re.S
    ).group(0):
        raise SystemExit("eventKind is still part of performanceKey")

    if updated != source:
        PATH.write_text(updated, encoding="utf-8")
        print("schedule.html hardened: group + day + start time => one physical performance")
    else:
        print("schedule.html already hardened")


if __name__ == "__main__":
    main()
