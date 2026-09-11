#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

PAGE = Path("schedule.html")
LEGACY_FETCH = "fetch('./data/live-events.json?ts='+Date.now(),{cache:'no-store'})"
GUARDED_FETCH = "fetchLatestScheduleData('./data/live-events.json?ts='+Date.now(),10000)"
RAW_LATEST_SWAP = "events=prepare(data.publicEvents||data.events||[]);document.getElementById('status').textContent="
GUARDED_LATEST_SWAP = "if(!hasRequiredCandyTuneTour(data))throw new Error('integrity');" + RAW_LATEST_SWAP
HELPER = (
    "function fetchLatestScheduleData(url,timeoutMs){return new Promise(function(resolve,reject){"
    "var settled=false;setTimeout(function(){if(settled)return;settled=true;reject(new Error('timeout'))},timeoutMs);"
    "fetch(url,{cache:'no-store'}).then(function(response){if(settled)return;settled=true;resolve(response)},"
    "function(error){if(settled)return;settled=true;reject(error)})})}\n"
)
INTEGRITY_HELPER = (
    "function hasRequiredCandyTuneTour(data){"
    "var required=['2026-08-29','2026-08-30','2026-09-04','2026-09-09','2026-09-10','2026-09-19','2026-10-02','2026-10-04','2026-10-08','2026-10-09','2026-10-26','2026-10-27','2026-10-29','2026-11-10','2026-11-12','2026-11-17','2026-11-19','2026-11-24','2026-11-26','2026-11-30','2026-12-01','2026-12-08','2026-12-09'],"
    "rows=Array.isArray(data&&data.publicEvents)?data.publicEvents:Array.isArray(data&&data.events)?data.events:[],found={};"
    "rows.forEach(function(e){if(!e||String(e.group||'').trim().toUpperCase()!=='CANDY TUNE')return;"
    "var tour=String(e.officialTourUrl||'').toLowerCase().replace(/[?#].*$/,'').replace(/\\/$/,''),"
    "text=[e.title,e.eventTitle,e.displayTitle].join(' ').toUpperCase();"
    "if(tour!=='https://candytune.asobisystem.com/feature/candytune_nationwide_tour2026'&&"
    "!(text.indexOf('JAPAN TOUR 2026')>=0&&(text.indexOf('AUTUMN')>=0||text.indexOf('CANDY CIRCUS')>=0)))return;"
    "function add(v){v=String(v||'').slice(0,10);if(/^2026-\\d{2}-\\d{2}$/.test(v))found[v]=1}"
    "add(e.eventDate);(e.eventDates||[]).forEach(function(v){add(v&&typeof v==='object'?v.date:v)});"
    "(e.schedule||[]).forEach(function(v){if(v&&typeof v==='object')add(v.date)})});"
    "return required.every(function(day){return found[day]===1})}\n"
)


def install_guard(page: str) -> str:
    if GUARDED_FETCH not in page and LEGACY_FETCH not in page:
        raise RuntimeError("schedule latest-data fetch changed; timeout guard could not be installed")

    fetch_anchor = page.find(GUARDED_FETCH if GUARDED_FETCH in page else LEGACY_FETCH)
    if "function fetchLatestScheduleData(url,timeoutMs)" not in page:
        page = page[:fetch_anchor] + HELPER + page[fetch_anchor:]
        fetch_anchor += len(HELPER)
    if "function hasRequiredCandyTuneTour(data)" not in page:
        page = page[:fetch_anchor] + INTEGRITY_HELPER + page[fetch_anchor:]

    page = page.replace(LEGACY_FETCH, GUARDED_FETCH, 1)
    if GUARDED_LATEST_SWAP not in page:
        if RAW_LATEST_SWAP not in page:
            raise RuntimeError("schedule latest-data assignment changed; integrity guard could not be installed")
        page = page.replace(RAW_LATEST_SWAP, GUARDED_LATEST_SWAP, 1)
    return page


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
