#!/usr/bin/env python3
"""Collect KAWAII LAB. special events from the public X syndication timeline.

This is a redundant discovery path for release events, large benefit events and
solo/birthday lives.  It exists because x.com profile HTML is intermittent and
must never be the only gate between an official announcement and the calendar.
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
from datetime import date, datetime
from pathlib import Path

import requests

import update_official_x_birthday_events as syndication
import update_official_x_special_events as base

DATA_PATH = Path("data/live-events.json")


def extract_posts_from_next_data(html: str, handle: str) -> list[tuple[str, str, list[str]]]:
    match = syndication.NEXT_DATA_RE.search(html)
    if not match:
        raise ValueError("X syndication payload did not contain __NEXT_DATA__")

    payload = json.loads(html_lib.unescape(match.group(1)))
    posts: dict[str, tuple[str, list[str]]] = {}
    for node in syndication._walk(payload):
        if not isinstance(node, dict):
            continue
        tweet_id = syndication._tweet_id(node)
        text = syndication._tweet_text(node)
        if not tweet_id or not text:
            continue
        if not base.TRACKED_RE.search(text):
            continue
        if not base.DATE_RE.search(text):
            continue
        # A schedule placeholder is only publishable when a real venue can be
        # paired with the announced date. This avoids turning vague teasers into
        # calendar rows while still accepting "details later" announcements.
        if not ("📍" in text or "会場" in text or "場所" in text):
            continue
        official_urls = syndication._official_urls(node)
        previous = posts.get(tweet_id)
        if previous:
            merged_urls = list(dict.fromkeys([*previous[1], *official_urls]))
            posts[tweet_id] = (previous[0] if len(previous[0]) >= len(text) else text, merged_urls)
        else:
            posts[tweet_id] = (text, official_urls)

    return [
        (f"https://x.com/{handle}/status/{tweet_id}", text, urls)
        for tweet_id, (text, urls) in posts.items()
    ]


def events_from_post(
    group: str,
    x_url: str,
    text: str,
    today: date,
    official_urls: list[str] | None = None,
) -> list[dict]:
    official_urls = official_urls or []
    lines = [base.normalize(value) for value in text.splitlines() if base.normalize(value)]
    category = base.special_category(text)
    if not category:
        return []

    fallback_title = base.extract_title(group, text, lines, category)
    primary_url = official_urls[0] if official_urls else x_url
    urls = list(dict.fromkeys([primary_url, *official_urls, x_url]))
    events = []
    for day, venue in base.extract_occurrences(lines, today):
        if day < today:
            continue
        title = base.extract_occurrence_title(group, lines, day, today, category, fallback_title)
        events.append({
            "id": base.stable_id("official-x-event", group, day.isoformat(), category),
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
            "url": primary_url,
            "urls": urls,
            "discoverySourceUrl": x_url,
            "sourceType": "official-social",
            "sourceChannel": "official-x-syndication",
            "primarySource": "official",
            "sourceCandidates": ["official"],
            "eventScope": "kawaii-lab",
        })
    return events


def collect(session: requests.Session, today: date | None = None) -> tuple[list[dict], list[dict]]:
    today = today or datetime.now(base.JST).date()
    events: list[dict] = []
    failures: list[dict] = []
    for group, handle in base.GROUP_X.items():
        try:
            html = syndication.fetch_syndication(session, handle)
            posts = extract_posts_from_next_data(html, handle)
            for x_url, text, official_urls in posts:
                events.extend(events_from_post(group, x_url, text, today, official_urls))
        except Exception as exc:
            failures.append({
                "group": group,
                "handle": handle,
                "error": f"{type(exc).__name__}: {exc}",
            })
    return events, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect official-X special events through syndication")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; keio-kawaii-lab-calendar/1.0; +https://github.com/keio-kawaiilab/keio-kawaii-lab)",
        "Accept-Language": "ja,en;q=0.8",
    })
    try:
        collected, failures = collect(session)
    finally:
        session.close()

    diagnostics = {
        "collector": "official-x-syndication-special",
        "collected": len(collected),
        "failures": failures,
        "events": [
            {
                "group": event.get("group"),
                "eventDate": event.get("eventDate"),
                "eventCategory": event.get("eventCategory"),
                "title": event.get("title"),
                "venue": event.get("venue"),
                "url": event.get("url"),
                "discoverySourceUrl": event.get("discoverySourceUrl"),
            }
            for event in collected
        ],
    }
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))

    # One flaky group must not erase good discoveries from the other groups.
    # But two or more missing group timelines means the fallback itself is too
    # degraded to claim healthy monitoring.
    if len(failures) >= 2:
        return 2

    merged = base.merge_payload(payload, collected)
    if args.check:
        return 0
    if merged != payload:
        DATA_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
