#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import time
from datetime import date, datetime
from pathlib import Path

import requests

import update_official_x_special_events as base

DATA_PATH = Path("data/live-events.json")
NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
TWEET_ID_RE = re.compile(r"^\d{10,22}$")


def normalize_text(value: object) -> str:
    return html_lib.unescape(str(value or "")).replace("\\n", "\n").strip()


def _walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _tweet_id(node: dict) -> str | None:
    for key in ("id_str", "rest_id", "id"):
        value = str(node.get(key) or "")
        if TWEET_ID_RE.fullmatch(value):
            return value
    return None


def _tweet_text(node: dict) -> str:
    for key in ("full_text", "text"):
        value = normalize_text(node.get(key))
        if value:
            return value

    legacy = node.get("legacy")
    if isinstance(legacy, dict):
        for key in ("full_text", "text"):
            value = normalize_text(legacy.get(key))
            if value:
                return value
    return ""


def extract_posts_from_next_data(html: str, handle: str) -> list[tuple[str, str]]:
    match = NEXT_DATA_RE.search(html)
    if not match:
        raise ValueError("X syndication payload did not contain __NEXT_DATA__")

    payload = json.loads(html_lib.unescape(match.group(1)))
    posts: dict[str, str] = {}
    for node in _walk(payload):
        if not isinstance(node, dict):
            continue
        tweet_id = _tweet_id(node)
        text = _tweet_text(node)
        if not tweet_id or not text:
            continue
        if not base.BIRTHDAY_RE.search(text):
            continue
        if not base.DATE_RE.search(text):
            continue
        if not ("📍" in text or "会場" in text or "場所" in text):
            continue
        posts[tweet_id] = text

    return [(f"https://x.com/{handle}/status/{tweet_id}", text) for tweet_id, text in posts.items()]


def event_from_post(group: str, url: str, text: str, today: date) -> list[dict]:
    lines = [base.normalize(value) for value in text.splitlines() if base.normalize(value)]
    category = "solo-live"
    fallback_title = base.extract_title(group, text, lines, category)
    events = []
    for day, venue in base.extract_occurrences(lines, today):
        if day < today:
            continue
        title = base.extract_occurrence_title(group, lines, day, today, category, fallback_title)
        events.append({
            "id": base.stable_id("official-x-birthday", group, day.isoformat(), title),
            "group": group,
            "title": title,
            "eventTitle": title,
            "displayTitle": title,
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
            "sourceChannel": "official-x-syndication",
            "primarySource": "official",
            "sourceCandidates": ["official"],
            "eventScope": "kawaii-lab",
        })
    return events


def fetch_syndication(session: requests.Session, handle: str) -> str:
    errors = []
    for host in ("syndication.twitter.com", "syndication.x.com"):
        url = f"https://{host}/srv/timeline-profile/screen-name/{handle}"
        try:
            response = session.get(url, timeout=25)
            response.raise_for_status()
            if NEXT_DATA_RE.search(response.text):
                return response.text
            errors.append(f"{host}: missing __NEXT_DATA__")
        except Exception as exc:
            errors.append(f"{host}: {type(exc).__name__}: {exc}")
    raise RuntimeError("; ".join(errors))


def collect(session: requests.Session, today: date | None = None, sleep_seconds: float = 2.0) -> tuple[list[dict], list[dict]]:
    today = today or datetime.now(base.JST).date()
    events = []
    failures = []
    for index, (group, handle) in enumerate(base.GROUP_X.items()):
        if index and sleep_seconds:
            time.sleep(sleep_seconds)
        try:
            html = fetch_syndication(session, handle)
            posts = extract_posts_from_next_data(html, handle)
            for url, text in posts:
                events.extend(event_from_post(group, url, text, today))
        except Exception as exc:
            failures.append({
                "group": group,
                "handle": handle,
                "error": f"{type(exc).__name__}: {exc}",
            })
    return events, failures


def merge_birthday_events(payload: dict, birthday_events: list[dict]) -> dict:
    # The base merge logic already deduplicates by group/date/category and
    # gives official-site rows priority over social placeholders.
    return base.merge_payload(payload, birthday_events)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fallback collector for KAWAII LAB. birthday events from X syndication timelines")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; keio-kawaii-lab-calendar/1.0; +https://github.com/keio-kawaiilab/keio-kawaii-lab)",
        "Accept-Language": "ja,en;q=0.8",
    })
    try:
        events, failures = collect(session)
    finally:
        session.close()

    merged = merge_birthday_events(payload, events)
    diagnostics = {
        "collector": "official-x-syndication-birthday",
        "collected": len(events),
        "failures": failures,
        "changed": merged != payload,
    }

    if args.check:
        print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
        return 0 if events or not failures else 1

    DATA_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
    # This is a redundant collector: a partial endpoint outage must not erase
    # previously good data or block unrelated schedule updates.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
