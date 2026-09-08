#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

PAGE = Path("schedule.html")
LEGACY_FETCH = "fetch('./data/live-events.json?ts='+Date.now(),{cache:'no-store'})"
GUARDED_FETCH = "fetchLatestScheduleData('./data/live-events.json?ts='+Date.now(),10000)"
HELPER = (
    "function fetchLatestScheduleData(url,timeoutMs){return new Promise(function(resolve,reject){"
    "var settled=false;setTimeout(function(){if(settled)return;settled=true;reject(new Error('timeout'))},timeoutMs);"
    "fetch(url,{cache:'no-store'}).then(function(response){if(settled)return;settled=true;resolve(response)},"
    "function(error){if(settled)return;settled=true;reject(error)})})}\n"
)


def install_guard(page: str) -> str:
    if GUARDED_FETCH in page:
        if "function fetchLatestScheduleData(url,timeoutMs)" not in page:
            raise RuntimeError("schedule has guarded latest-data call without timeout helper")
        return page

    if LEGACY_FETCH not in page:
        raise RuntimeError("schedule latest-data fetch changed; timeout guard could not be installed")

    anchor = page.find(LEGACY_FETCH)
    page = page[:anchor] + HELPER + page[anchor:]
    return page.replace(LEGACY_FETCH, GUARDED_FETCH, 1)


def main() -> int:
    page = PAGE.read_text(encoding="utf-8")
    updated = install_guard(page)
    if updated != page:
        PAGE.write_text(updated, encoding="utf-8")
        print("Installed bounded latest schedule data loading")
    else:
        print("Latest schedule data loading guard already installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
