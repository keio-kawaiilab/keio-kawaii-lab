#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

import update_live_events as official

DATA_PATH = Path("data/live-events.json")


def official_urls(event: dict) -> list[str]:
    values = []
    for value in [event.get("url"), *(event.get("urls") or [])]:
        url = str(value or "")
        host = urlparse(url).netloc.lower()
        if host.endswith(".asobisystem.com") and (
            "/news/detail/" in url or "/live_information/detail/" in url
        ) and url not in values:
            values.append(url)
    return values


def occurrence_map(html: str, title: str = "") -> dict[str, dict]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [official.normalize_space(line) for line in text.splitlines() if official.normalize_space(line)]
    article_date = official.article_date_from_text(text)
    result = {}
    for day, venue, open_time, start_time in official.extract_event_occurrences(lines, title, article_date):
        row = result.setdefault(day, {"date": day})
        if venue:
            row["venue"] = venue
        if open_time:
            row["openTime"] = open_time
        if start_time:
            row["startTime"] = start_time
    return result


def merge_occurrences(target: dict[str, dict], source: dict[str, dict]) -> None:
    for day, source_row in source.items():
        target_row = target.setdefault(day, {"date": day})
        for key in ("venue", "openTime", "startTime"):
            if source_row.get(key) and not target_row.get(key):
                target_row[key] = source_row[key]


def enrich_event(event: dict, by_url: dict[str, dict[str, dict]]) -> tuple[dict, int]:
    out = dict(event)
    occurrences: dict[str, dict] = {}
    for url in official_urls(out):
        merge_occurrences(occurrences, by_url.get(url, {}))
    if not occurrences:
        return out, 0

    changed = 0
    schedule = out.get("schedule")
    if isinstance(schedule, list) and schedule:
        rows = []
        for original in schedule:
            if not isinstance(original, dict):
                rows.append(original)
                continue
            row = dict(original)
            source = occurrences.get(str(row.get("date") or "")[:10], {})
            for key in ("openTime", "startTime"):
                if source.get(key) and row.get(key) != source[key]:
                    row[key] = source[key]
                    changed += 1
            rows.append(row)
        out["schedule"] = rows
        return out, changed

    dates = [str(day)[:10] for day in (out.get("eventDates") or []) if day]
    if len(dates) > 1:
        rows = []
        for day in dates:
            source = occurrences.get(day, {})
            row = {"date": day, "venue": source.get("venue") or out.get("venue")}
            for key in ("openTime", "startTime"):
                if source.get(key):
                    row[key] = source[key]
                    changed += 1
            rows.append(row)
        out["schedule"] = rows
        return out, changed

    day = str(out.get("eventDate") or "")[:10]
    source = occurrences.get(day, {})
    for key in ("openTime", "startTime"):
        if source.get(key) and out.get(key) != source[key]:
            out[key] = source[key]
            changed += 1
    return out, changed


def enrich_payload(payload: dict, session: requests.Session) -> tuple[dict, dict]:
    events = [dict(event) for event in payload.get("events", []) if isinstance(event, dict)]
    urls = sorted({url for event in events for url in official_urls(event)})
    by_url: dict[str, dict[str, dict]] = {}
    failures = []

    for url in urls:
        try:
            response = session.get(url, timeout=20)
            response.raise_for_status()
            by_url[url] = occurrence_map(response.text)
        except Exception as exc:
            failures.append({"url": url, "error": str(exc)})

    enriched = []
    changed_fields = 0
    changed_events = 0
    for event in events:
        updated, changed = enrich_event(event, by_url)
        enriched.append(updated)
        changed_fields += changed
        if changed:
            changed_events += 1

    out = dict(payload)
    out["events"] = enriched
    return out, {
        "officialPages": len(urls),
        "changedEvents": changed_events,
        "changedTimeFields": changed_fields,
        "failures": failures,
    }


def main() -> int:
    if not DATA_PATH.exists():
        return 0
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update({
        "User-Agent": "KeioKawaiiLabCalendarBot/1.5 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"
    })
    enriched, diagnostics = enrich_payload(payload, session)
    DATA_PATH.write_text(json.dumps(enriched, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
