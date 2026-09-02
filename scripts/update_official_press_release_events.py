#!/usr/bin/env python3
"""Discover future KAWAII LAB. release/large-benefit events from official PR TIMES releases.

ASOBISYSTEM sometimes publishes a release schedule in a company press release
before a dedicated group-site event page exists.  Those verified date/venue
rows are published as schedule-only placeholders and later replaced by richer
official-site data.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import update_official_x_special_events as special

DATA_PATH = Path("data/live-events.json")
COMPANY_INDEX = "https://prtimes.jp/main/html/searchrlp/company_id/17258"
GROUPS = tuple(special.GROUP_X.keys())
ARTICLE_RE = re.compile(r"/main/html/rd/p/\d+\.\d+\.html")
DATE_LINE_RE = re.compile(
    r"(?:(20\d{2})\s*[./年-]\s*)?(\d{1,2})\s*[./月-]\s*(\d{1,2})\s*日?"
    r"(?:\s*[（(][^）)]*[）)])?\s*"
    r"(.*(?:大特典会|リリースイベント|リリイベ|発売記念イベント).*)",
    re.I,
)


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def article_links(html: str, limit: int = 40) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(COMPANY_INDEX, str(anchor.get("href") or ""))
        if not ARTICLE_RE.search(href):
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
    value = re.sub(r"^(?:大特典会|リリースイベント|リリイベ|発売記念イベント)\s*", "", value, flags=re.I)
    value = re.sub(r"^(?:大特典会|リリースイベント|リリイベ|発売記念イベント)\s*[@＠]?\s*", "", value, flags=re.I)
    value = value.lstrip("@＠：:・- ")
    value = re.sub(r"\s*(?:※.*)?$", "", value).strip()
    return value or None


def parse_article(url: str, html: str, today: date | None = None) -> list[dict]:
    today = today or datetime.now(special.JST).date()
    soup = BeautifulSoup(html, "html.parser")
    title = normalize(soup.find("h1").get_text(" ", strip=True)) if soup.find("h1") else ""
    if not title and soup.find("title"):
        title = normalize(soup.find("title").get_text(" ", strip=True))
    lines = [normalize(line) for line in soup.get_text("\n", strip=True).splitlines() if normalize(line)]
    text = "\n".join(lines)
    if not re.search(r"リリースイベント|リリイベ|大特典会|発売記念イベント", text, re.I):
        return []
    groups = groups_for_article(title, text)
    if not groups:
        return []

    published_year = published_year_from_text(text, today)
    rows: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for line in lines:
        match = DATE_LINE_RE.search(line)
        if not match:
            continue
        year_text, month_text, day_text, tail = match.groups()
        day = infer_day(year_text, month_text, day_text, published_year, today)
        if not day or day < today:
            continue
        category = "large-benefit" if "大特典会" in tail else "release-event"
        venue = venue_from_tail(tail)
        if not venue:
            continue
        # Ignore prose that only mentions a generic event type without an
        # actual location. Official release-plan rows have a concrete venue.
        if venue in {"開催予定", "開催決定", "詳細は後日発表", "詳細は後日改めてお知らせします"}:
            continue
        for group in groups:
            key = (group, day.isoformat(), category, venue)
            if key in seen:
                continue
            seen.add(key)
            display = f"{group} {'大特典会' if category == 'large-benefit' else 'リリースイベント'}"
            rows.append({
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
                "urls": [url],
                "sourceType": "official-social",
                "sourceChannel": "official-prtimes",
                "primarySource": "official",
                "sourceCandidates": ["official"],
                "eventScope": "kawaii-lab",
            })
    return rows


def collect(session: requests.Session, today: date | None = None) -> tuple[list[dict], list[dict], int]:
    today = today or datetime.now(special.JST).date()
    response = session.get(COMPANY_INDEX, timeout=20)
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

    # Deduplicate the same occurrence if multiple press releases repeat the
    # schedule. Prefer the most recently encountered row without multiplying it.
    deduped: dict[tuple[str, str, str, str], dict] = {}
    for event in collected:
        key = (
            str(event.get("group") or ""),
            str(event.get("eventDate") or "")[:10],
            str(event.get("eventCategory") or ""),
            str(event.get("venue") or ""),
        )
        deduped[key] = event
    collected = list(deduped.values())

    diagnostics = {
        "collector": "official-prtimes-special",
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

    merged = special.merge_payload(payload, collected)
    if args.check:
        return 0
    if merged != payload:
        DATA_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
