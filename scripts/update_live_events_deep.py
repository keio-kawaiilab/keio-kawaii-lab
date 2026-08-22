#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import update_live_events as parser_v1
import update_live_events_v2 as retention

DEEP_NEWS_PAGES = 15
REQUEST_PAUSE = 0.10


def candidate_links_deep(session: requests.Session, group: str, base: str, max_pages: int = DEEP_NEWS_PAGES):
    """Scan farther back than the normal six-hour crawler.

    We stop only when a listing page no longer contains news-detail links, not merely
    because one page has no ticket article. This avoids missing sparse older ticket
    announcements.
    """
    found: dict[str, parser_v1.Candidate] = {}
    scanned_pages = 0

    for page in range(1, max_pages + 1):
        url = f"{base}/news/1/?page={page}"
        response = session.get(url, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        detail_links = [a for a in soup.find_all("a", href=True) if "/news/detail/" in a.get("href", "")]
        if not detail_links:
            break

        scanned_pages += 1
        for a in detail_links:
            title = parser_v1.normalize_space(a.get_text(" ", strip=True))
            if not title:
                continue
            if not any(key in title for key in parser_v1.TICKET_HINTS):
                continue
            if any(key in title for key in parser_v1.IGNORE_TITLE_HINTS):
                continue
            full = urljoin(base, a.get("href", ""))
            found[full] = parser_v1.Candidate(group=group, title=title, url=full)
        time.sleep(REQUEST_PAUSE)

    return list(found.values()), scanned_pages


def collect_deep(session: requests.Session):
    all_events: dict[str, dict] = {}
    pending: list[dict] = []
    failures: list[dict] = []
    candidates_by_group: dict[str, int] = {}
    pages_by_group: dict[str, int] = {}

    for group, base in parser_v1.GROUPS.items():
        try:
            candidates, pages = candidate_links_deep(session, group, base)
            candidates_by_group[group] = len(candidates)
            pages_by_group[group] = pages
        except Exception as exc:
            candidates_by_group[group] = 0
            pages_by_group[group] = 0
            failures.append({"group": group, "stage": "deep-news-list", "error": str(exc)})
            continue

        for candidate in candidates:
            try:
                events, review = parser_v1.parse_candidate(session, candidate)
                for event in events:
                    all_events[event["id"]] = event
                if review:
                    pending.append(review)
            except Exception as exc:
                failures.append({"group": group, "url": candidate.url, "stage": "deep-article", "error": str(exc)})
            time.sleep(0.12)

    return all_events, pending, failures, candidates_by_group, pages_by_group


def main() -> int:
    cli = argparse.ArgumentParser(description="Weekly deep backfill for LIVE & TICKET calendar.")
    cli.add_argument("--check", action="store_true", help="Parse official pages without writing data.")
    args = cli.parse_args()

    session = requests.Session()
    session.headers.update({
        "User-Agent": "KeioKawaiiLabCalendarBot/1.3 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"
    })

    fresh_by_id, pending, failures, counts, pages = collect_deep(session)
    reachable_groups = sum(1 for count in counts.values() if count > 0)
    diagnostics = {
        "mode": "weekly-deep-backfill",
        "scannedPages": pages,
        "candidateCounts": counts,
        "parsedEvents": len(fresh_by_id),
        "pendingReview": len(pending),
        "failures": failures,
    }
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))

    if reachable_groups < 4:
        print("Fewer than four group news feeds were reachable during deep backfill.", file=sys.stderr)
        return 2
    if not fresh_by_id:
        print("No events parsed during deep backfill; existing data left untouched.", file=sys.stderr)
        return 2
    if args.check:
        print("Deep live source check passed; no files were modified.")
        return 0

    existing = parser_v1.read_existing()
    payload = retention.build_payload(
        existing,
        fresh_by_id,
        pending,
        failures,
        datetime.now(parser_v1.JST).date(),
    )
    payload["source"] = "KAWAII LAB.各グループ公式サイトの公開INFORMATION（通常巡回＋週次深掘り）"
    parser_v1.OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    parser_v1.OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Deep backfill wrote {len(payload['events'])} retained/future events.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
