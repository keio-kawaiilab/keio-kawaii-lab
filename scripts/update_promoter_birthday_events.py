#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

DATA_PATH = Path("data/live-events.json")
JST = timezone(timedelta(hours=9))
BASE_URL = "https://red-hot.ne.jp"
MONTHS_AHEAD = 12
GROUPS = (
    "FRUITS ZIPPER",
    "CANDY TUNE",
    "SWEET STEADY",
    "CUTIE STREET",
    "MORE STAR",
)
BIRTHDAY_RE = re.compile(
    r"生誕(?:祭|ライブ|イベント|公演)?|BIRTHDAY\s*(?:LIVE|EVENT|PARTY|FES|FESTIVAL)?|BD\s*(?:LIVE|EVENT)",
    re.I,
)
DATE_RE = re.compile(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日")
OPEN_RE = re.compile(r"OPEN\s*(\d{1,2})[:：](\d{2})", re.I)
START_RE = re.compile(r"START\s*(\d{1,2})[:：](\d{2})", re.I)
DETAIL_RE = re.compile(r"/play/detail\.php\?pid=[A-Za-z0-9_-]+")


@dataclass(frozen=True)
class Candidate:
    url: str
    context: str


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def stable_id(*values: object) -> str:
    raw = "\x1f".join(str(value or "") for value in values)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def month_pairs(today: date, count: int = MONTHS_AHEAD) -> list[tuple[int, int]]:
    pairs = []
    year, month = today.year, today.month
    for _ in range(count):
        pairs.append((year, month))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return pairs


def discover_candidates(html: str, base_url: str = BASE_URL) -> list[Candidate]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, Candidate] = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if not DETAIL_RE.search(href):
            continue
        pieces = [anchor.get_text(" ", strip=True)]
        parent = anchor.parent
        if parent is not None:
            pieces.append(parent.get_text(" ", strip=True))
        context = normalize(" ".join(pieces))
        if not BIRTHDAY_RE.search(context):
            continue
        url = urljoin(base_url, href)
        found[url] = Candidate(url=url, context=context)
    return list(found.values())


def group_from_text(text: str) -> str | None:
    upper = text.upper()
    for group in GROUPS:
        if group.upper() in upper:
            return group
    return None


def title_from_lines(lines: list[str], group: str) -> str | None:
    candidates = []
    for line in lines:
        if not BIRTHDAY_RE.search(line):
            continue
        value = normalize(line)
        if len(value) < 4 or len(value) > 200:
            continue
        candidates.append(value)
    if not candidates:
        return None
    candidates.sort(key=lambda value: (group.lower() in value.lower(), len(value)), reverse=True)
    return candidates[0]


def first_match(pattern: re.Pattern, text: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def parse_detail(url: str, html: str, today: date | None = None) -> dict | None:
    today = today or datetime.now(JST).date()
    soup = BeautifulSoup(html, "html.parser")
    lines = [normalize(value) for value in soup.stripped_strings if normalize(value)]
    text = "\n".join(lines)
    if not BIRTHDAY_RE.search(text):
        return None

    group = group_from_text(text)
    if not group:
        return None
    title = title_from_lines(lines, group)
    if not title:
        return None

    date_match = DATE_RE.search(text)
    if not date_match:
        return None
    try:
        day = date(*(int(value) for value in date_match.groups()))
    except ValueError:
        return None
    if day < today:
        return None

    venue = None
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if "/venue/detail.php" not in href:
            continue
        value = normalize(anchor.get_text(" ", strip=True))
        if value:
            venue = value
            break
    if not venue:
        return None

    return {
        "id": stable_id("promoter-birthday", group, day.isoformat(), url),
        "group": group,
        "title": title,
        "eventTitle": title,
        "displayTitle": title,
        "eventCategory": "solo-live",
        "ticketType": "現在受付なし",
        "applicationStatus": "none",
        "applyStart": None,
        "applyEnd": None,
        "resultDate": None,
        "paymentEnd": None,
        "applicationDisplayMode": "schedule-only",
        "eventDate": day.isoformat(),
        "venue": venue,
        "openTime": first_match(OPEN_RE, text),
        "startTime": first_match(START_RE, text),
        "url": url,
        "urls": [url],
        "sourceType": "promoter",
        "sourceChannel": "hot-stuff-promotion",
        "primarySource": "promoter",
        "sourceCandidates": ["promoter"],
        "eventScope": "kawaii-lab",
        "promoterVerified": True,
    }


def birthday_key(event: dict) -> tuple[str, str] | None:
    title = str(event.get("eventTitle") or event.get("title") or "")
    if not BIRTHDAY_RE.search(title):
        return None
    group = str(event.get("group") or "")
    day = str(event.get("eventDate") or "")[:10]
    if not group or not day:
        return None
    return group, day


def merge_payload(payload: dict, fresh_events: list[dict]) -> dict:
    if not fresh_events:
        return payload

    existing = [dict(event) for event in payload.get("events", []) if isinstance(event, dict)]
    fresh_by_key = {birthday_key(event): event for event in fresh_events if birthday_key(event)}
    official_keys = {
        birthday_key(event)
        for event in existing
        if birthday_key(event)
        and str(event.get("primarySource") or "").lower() == "official"
    }

    result = []
    handled = set()
    for event in existing:
        key = birthday_key(event)
        if not key or str(event.get("sourceType") or "").lower() != "promoter":
            result.append(event)
            continue
        if key in official_keys:
            continue
        fresh = fresh_by_key.get(key)
        if fresh:
            merged = dict(fresh)
            merged["id"] = event.get("id") or fresh.get("id")
            result.append(merged)
            handled.add(key)
        else:
            result.append(event)

    for key, event in fresh_by_key.items():
        if key in official_keys or key in handled:
            continue
        result.append(event)

    result.sort(key=lambda event: (
        str(event.get("eventDate") or "9999-12-31")[:10],
        str(event.get("group") or ""),
        str(event.get("title") or ""),
    ))
    out = dict(payload)
    out["events"] = result
    if result != existing:
        out["updatedAt"] = datetime.now(JST).isoformat(timespec="seconds")
    return out


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; keio-kawaii-lab-calendar/1.0; +https://github.com/keio-kawaiilab/keio-kawaii-lab)",
        "Accept-Language": "ja,en;q=0.8",
    })
    return session


def collect(session: requests.Session, today: date | None = None) -> tuple[list[dict], dict]:
    today = today or datetime.now(JST).date()
    candidates: dict[str, Candidate] = {}
    failures = []
    months = month_pairs(today)

    for year, month in months:
        url = f"{BASE_URL}/play/?mth={month}&y={year}"
        try:
            response = session.get(url, timeout=25)
            response.raise_for_status()
            for candidate in discover_candidates(response.text):
                candidates[candidate.url] = candidate
        except Exception as exc:
            failures.append({"stage": "month", "url": url, "error": f"{type(exc).__name__}: {exc}"})
        time.sleep(0.1)

    events = []
    for candidate in candidates.values():
        try:
            response = session.get(candidate.url, timeout=25)
            response.raise_for_status()
            event = parse_detail(candidate.url, response.text, today)
            if event:
                events.append(event)
        except Exception as exc:
            failures.append({"stage": "detail", "url": candidate.url, "error": f"{type(exc).__name__}: {exc}"})
        time.sleep(0.1)

    diagnostics = {
        "source": "HOT STUFF PROMOTION",
        "monthsChecked": len(months),
        "candidates": len(candidates),
        "events": len(events),
        "failures": failures,
    }
    return events, diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect KAWAII LAB. birthday lives from HOT STUFF PROMOTION as a secondary source")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    session = make_session()
    try:
        events, diagnostics = collect(session)
    finally:
        session.close()

    merged = merge_payload(payload, events)
    diagnostics["changed"] = merged != payload
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))

    if args.check:
        return 0

    DATA_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
