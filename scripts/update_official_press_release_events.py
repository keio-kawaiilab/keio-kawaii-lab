#!/usr/bin/env python3
"""Discover future KAWAII LAB. release/large-benefit events from official PR TIMES releases.

ASOBISYSTEM sometimes publishes a release schedule in a company press release
before a dedicated group-site event page exists. Those verified date/venue
rows are published as schedule-only placeholders and later replaced by richer
official-site data.

This collector intentionally discovers articles, not hard-coded event dates.
It watches PR TIMES' server-rendered search surface for new ASOBISYSTEM releases,
filters article URLs to ASOBISYSTEM's company id, then parses every future
release-event / large-benefit row it can verify from those official releases.
It supports both inline rows ("9/11 リリースイベント 会場") and section-style
plans where a "＜リリースイベント＞" heading is followed by dates and venues.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

import update_official_x_special_events as special

DATA_PATH = Path("data/live-events.json")
ASOBISYSTEM_COMPANY_ID = "000017258"
DISCOVERY_URL = (
    "https://prtimes.jp/main/action.php?page=searchkey&run=html&search_word="
    + quote("アソビシステム株式会社")
)
GROUP_BASES = {
    "FRUITS ZIPPER": "https://fruitszipper.asobisystem.com/",
    "CANDY TUNE": "https://candytune.asobisystem.com/",
    "SWEET STEADY": "https://sweetsteady.asobisystem.com/",
    "CUTIE STREET": "https://cutiestreet.asobisystem.com/",
    "MORE STAR": "https://morestar.asobisystem.com/",
}
GROUPS = tuple(GROUP_BASES)
ARTICLE_RE = re.compile(r"/main/html/rd/p/\d+\.(\d+)\.html")
EVENT_LABEL_RE = r"(?:大特典会|リリースイベント|リリイベ|発売記念イベント)"
DATE_PREFIX_RE = re.compile(
    r"^(?:(20\d{2})\s*[./年-]\s*)?(\d{1,2})\s*[./月-]\s*(\d{1,2})\s*日?"
    r"(?:\s*[（(][^）)]*[）)])?\s*(.*)$",
    re.I,
)
HEADING_RE = re.compile(r"^[＜<【〖■◆◇].{1,80}[＞>】〗]?$", re.I)


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def article_links(html: str, limit: int = 60) -> list[str]:
    """Return only ASOBISYSTEM's own PR TIMES release URLs."""
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(DISCOVERY_URL, str(anchor.get("href") or ""))
        match = ARTICLE_RE.search(href)
        if not match or match.group(1) != ASOBISYSTEM_COMPANY_ID:
            continue
        href = href.split("?", 1)[0].split("#", 1)[0]
        if href not in found:
            found.append(href)
        if len(found) >= limit:
            break
    return found


def infer_day(year_text: str | None, month_text: str, day_text: str, published_year: int, today: date) -> date | None:
    year = int(year_text) if year_text else published_year
    try:
        candidate = date(year, int(month_text), int(day_text))
    except ValueError:
        return None
    if not year_text and candidate < today - timedelta(days=60):
        try:
            candidate = date(year + 1, candidate.month, candidate.day)
        except ValueError:
            return None
    return candidate


def published_year_from_text(text: str, today: date) -> int:
    for pattern in (
        r"(20\d{2})年\s*\d{1,2}月\s*\d{1,2}日",
        r"(20\d{2})[./-]\d{1,2}[./-]\d{1,2}",
    ):
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return today.year


def groups_for_article(title: str, text: str) -> list[str]:
    in_title = [group for group in GROUPS if group in title]
    if in_title:
        return in_title
    return [group for group in GROUPS if group in text]


def venue_from_tail(tail: str) -> str | None:
    value = normalize(tail)
    value = re.sub(rf"^(?:{EVENT_LABEL_RE}\s*[@＠]?\s*)+", "", value, flags=re.I)
    value = re.sub(rf"\s*{EVENT_LABEL_RE}\s*$", "", value, flags=re.I)
    value = value.lstrip("@＠：:・- ")
    value = re.sub(r"\s*(?:参加メンバー|出演メンバー)\s*[：:].*$", "", value, flags=re.I)
    value = re.sub(r"\s*(?:※.*)?$", "", value).strip()
    return value or None


def section_category(line: str) -> str | None:
    clean = normalize(line).strip("＜＞<>【】〖〗■◆◇ ")
    if DATE_PREFIX_RE.match(clean):
        return None
    if "大特典会" in clean and len(clean) <= 40:
        return "large-benefit"
    if re.search(r"(?:CD)?リリースイベント(?:情報)?|発売記念イベント", clean, re.I) and len(clean) <= 50:
        return "release-event"
    return None


def plausible_section_venue(line: str) -> str | None:
    value = venue_from_tail(line)
    if not value:
        return None
    if value.startswith("※") or value.startswith("注"):
        return None
    if re.search(r"詳細|お問い合わせ|今後も日程|オフィシャルサイト|発売情報|ツアー情報", value):
        return None
    if HEADING_RE.match(value):
        return None
    return value


def make_event(group: str, day: date, category: str, venue: str, url: str) -> dict:
    display = f"{group} {'大特典会' if category == 'large-benefit' else 'リリースイベント'}"
    return {
        "id": special.stable_id("official-prtimes-event", group, day.isoformat(), category, venue),
        "group": group,
        "title": display,
        "eventTitle": display,
        "displayTitle": display,
        "eventCategory": category,
        "ticketType": "現在受付なし",
        "applicationStatus": "none",
        "applyStart": None,
        "applyEnd": None,
        "resultDate": None,
        "paymentEnd": None,
        "specialDetailsStatus": "awaiting-details",
        "applicationDisplayMode": "schedule-only",
        "eventDate": day.isoformat(),
        "venue": venue,
        "url": url,
        "urls": [url, GROUP_BASES[group]],
        "sourceType": "official-special",
        "sourceChannel": "official-prtimes",
        "primarySource": "official",
        "sourceCandidates": ["official"],
        "eventScope": "kawaii-lab",
    }


def parse_article(url: str, html: str, today: date | None = None) -> list[dict]:
    today = today or datetime.now(special.JST).date()
    soup = BeautifulSoup(html, "html.parser")
    title = normalize(soup.find("h1").get_text(" ", strip=True)) if soup.find("h1") else ""
    if not title and soup.find("title"):
        title = normalize(soup.find("title").get_text(" ", strip=True))
    lines = [normalize(line) for line in soup.get_text("\n", strip=True).splitlines() if normalize(line)]
    text = "\n".join(lines)
    if not re.search(EVENT_LABEL_RE, text, re.I):
        return []
    groups = groups_for_article(title, text)
    if not groups:
        return []

    published_year = published_year_from_text(text, today)
    rows: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    active_section: str | None = None

    def add(day: date, category: str, venue: str) -> None:
        if day < today:
            return
        for group in groups:
            key = (group, day.isoformat(), category, venue)
            if key in seen:
                continue
            seen.add(key)
            rows.append(make_event(group, day, category, venue, url))

    index = 0
    while index < len(lines):
        line = lines[index]
        new_section = section_category(line)
        if new_section:
            active_section = new_section
            index += 1
            continue
        if active_section and HEADING_RE.match(line) and not re.search(EVENT_LABEL_RE, line, re.I):
            active_section = None

        match = DATE_PREFIX_RE.match(line)
        if not match:
            index += 1
            continue
        year_text, month_text, day_text, tail = match.groups()
        day = infer_day(year_text, month_text, day_text, published_year, today)
        if not day:
            index += 1
            continue

        explicit_category = None
        if "大特典会" in tail:
            explicit_category = "large-benefit"
        elif re.search(r"リリースイベント|リリイベ|発売記念イベント", tail, re.I):
            explicit_category = "release-event"

        if explicit_category:
            venue = venue_from_tail(tail)
            if venue:
                add(day, explicit_category, venue)
            index += 1
            continue

        if active_section:
            same_line_venue = plausible_section_venue(tail)
            if same_line_venue:
                add(day, active_section, same_line_venue)
                index += 1
                continue

            # Section-style releases can put one date on its own line and then
            # list multiple location/member rows below it (e.g. FRUITS ZIPPER).
            scan = index + 1
            while scan < len(lines):
                candidate = lines[scan]
                if DATE_PREFIX_RE.match(candidate) or HEADING_RE.match(candidate):
                    break
                if candidate.startswith("※"):
                    break
                venue = plausible_section_venue(candidate)
                if venue:
                    add(day, active_section, venue)
                scan += 1
            index = max(index + 1, scan)
            continue

        index += 1
    return rows


def collect(session: requests.Session, today: date | None = None) -> tuple[list[dict], list[dict], int]:
    today = today or datetime.now(special.JST).date()
    response = session.get(DISCOVERY_URL, timeout=20)
    response.raise_for_status()
    links = article_links(response.text)
    events: list[dict] = []
    failures: list[dict] = []
    fetched = 0
    for url in links:
        try:
            article = session.get(url, timeout=15)
            article.raise_for_status()
            fetched += 1
            events.extend(parse_article(url, article.text, today))
        except requests.RequestException as exc:
            failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
    return events, failures, fetched


def merge_payload(payload: dict, collected: list[dict], today: date | None = None) -> dict:
    """Refresh PR placeholders without overriding richer official-site rows."""
    today = today or datetime.now(special.JST).date()
    events = [event for event in payload.get("events", []) if isinstance(event, dict)]

    def key(event: dict) -> tuple[str, str, str]:
        return (
            str(event.get("group") or ""),
            str(event.get("eventDate") or "")[:10],
            str(event.get("eventCategory") or ""),
        )

    richer_keys = {
        key(event)
        for event in events
        if event.get("primarySource") == "official"
        and event.get("sourceChannel") != "official-prtimes"
        and event.get("sourceType") in {"official-special", "official-schedule"}
    }
    fresh = {key(event): event for event in collected if key(event) not in richer_keys}
    result: list[dict] = []
    used: set[tuple[str, str, str]] = set()
    for event in events:
        event_key = key(event)
        if event.get("sourceChannel") != "official-prtimes":
            result.append(event)
            continue
        try:
            if date.fromisoformat(event_key[1]) < today:
                continue
        except ValueError:
            continue
        replacement = fresh.get(event_key)
        if replacement:
            result.append(replacement)
            used.add(event_key)
        elif event_key in richer_keys:
            continue
        else:
            result.append(event)
    for event_key, event in fresh.items():
        if event_key not in used:
            result.append(event)
    result.sort(key=lambda event: (str(event.get("eventDate") or "9999"), str(event.get("group") or ""), str(event.get("title") or "")))
    out = dict(payload)
    out["events"] = result
    if result != events:
        out["updatedAt"] = datetime.now(special.JST).isoformat(timespec="seconds")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect ASOBISYSTEM official PR TIMES release-event schedules")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; keio-kawaii-lab-calendar/1.0; +https://github.com/keio-kawaiilab/keio-kawaii-lab)",
        "Accept-Language": "ja,en;q=0.8",
    })
    try:
        collected, failures, fetched = collect(session)
    except Exception as exc:
        print(json.dumps({
            "collector": "official-prtimes-special",
            "error": f"{type(exc).__name__}: {exc}",
        }, ensure_ascii=False, indent=2))
        return 2
    finally:
        session.close()

    deduped: dict[tuple[str, str, str, str], dict] = {}
    for event in collected:
        event_key = (
            str(event.get("group") or ""),
            str(event.get("eventDate") or "")[:10],
            str(event.get("eventCategory") or ""),
            str(event.get("venue") or ""),
        )
        deduped[event_key] = event
    collected = list(deduped.values())

    diagnostics = {
        "collector": "official-prtimes-special",
        "discoveryUrl": DISCOVERY_URL,
        "articleLinks": fetched,
        "collected": len(collected),
        "failures": failures,
        "events": [
            {
                "group": event.get("group"),
                "eventDate": event.get("eventDate"),
                "eventCategory": event.get("eventCategory"),
                "venue": event.get("venue"),
                "url": event.get("url"),
            }
            for event in collected
        ],
    }
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
    if fetched == 0:
        return 2

    merged = merge_payload(payload, collected)
    if args.check:
        return 0
    if merged != payload:
        DATA_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
