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
COLLAPSE_RATIO = 0.35


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


def known_urls(existing: dict) -> set[str]:
    urls: set[str] = set()
    for event in existing.get("events", []):
        if not isinstance(event, dict):
            continue
        if event.get("url"):
            urls.add(str(event["url"]))
        for url in event.get("urls") or []:
            if url:
                urls.add(str(url))
    for item in existing.get("pendingReview", []):
        if isinstance(item, dict) and item.get("url"):
            urls.add(str(item["url"]))
    return urls


def collect_deep(session: requests.Session, skip_urls: set[str] | None = None):
    skip_urls = skip_urls or set()
    all_events: dict[str, dict] = {}
    pending: list[dict] = []
    failures: list[dict] = []
    candidates_by_group: dict[str, int] = {}
    pages_by_group: dict[str, int] = {}
    skipped_by_group: dict[str, int] = {}

    for group, base in parser_v1.GROUPS.items():
        try:
            candidates, pages = candidate_links_deep(session, group, base)
            candidates_by_group[group] = len(candidates)
            pages_by_group[group] = pages
        except Exception as exc:
            candidates_by_group[group] = 0
            pages_by_group[group] = 0
            skipped_by_group[group] = 0
            failures.append({"group": group, "stage": "deep-news-list", "error": str(exc)})
            continue

        skipped = 0
        for candidate in candidates:
            # Old known articles are retained from existing data. The normal six-hour
            # crawler is responsible for re-reading recent articles for updates.
            if candidate.url in skip_urls:
                skipped += 1
                continue
            try:
                events, review = parser_v1.parse_candidate(session, candidate)
                for event in events:
                    all_events[event["id"]] = event
                if review:
                    pending.append(review)
            except Exception as exc:
                failures.append({"group": group, "url": candidate.url, "stage": "deep-article", "error": str(exc)})
            time.sleep(0.12)
        skipped_by_group[group] = skipped

    return all_events, pending, failures, candidates_by_group, pages_by_group, skipped_by_group


def detect_candidate_collapse(previous: dict, current: dict) -> list[dict]:
    """Flag a large listing-count drop, which usually means the official HTML changed."""
    issues = []
    for group, old_value in previous.items():
        try:
            old = int(old_value)
            new = int(current.get(group, 0))
        except (TypeError, ValueError):
            continue
        if old < 10:
            continue
        threshold = max(3, int(old * COLLAPSE_RATIO))
        if new < threshold:
            issues.append({"group": group, "previous": old, "current": new, "threshold": threshold})
    return issues


def merge_pending(existing: dict, new_pending: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for item in list(existing.get("pendingReview", [])) + list(new_pending):
        if not isinstance(item, dict):
            continue
        key = (item.get("url"), item.get("reason"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def main() -> int:
    cli = argparse.ArgumentParser(description="Weekly deep backfill for LIVE & TICKET calendar.")
    cli.add_argument("--check", action="store_true", help="Parse official pages without writing data.")
    args = cli.parse_args()

    existing = parser_v1.read_existing()
    already_known = known_urls(existing)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "KeioKawaiiLabCalendarBot/1.4 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"
    })

    fresh_by_id, pending, failures, counts, pages, skipped = collect_deep(session, already_known)
    reachable_groups = sum(1 for count in counts.values() if count > 0)

    previous_counts = ((existing.get("deepDiagnostics") or {}).get("candidateCounts") or {})
    collapse = detect_candidate_collapse(previous_counts, counts)
    diagnostics = {
        "mode": "weekly-deep-backfill",
        "scannedPages": pages,
        "candidateCounts": counts,
        "skippedKnownCandidates": skipped,
        "newParsedEvents": len(fresh_by_id),
        "newPendingReview": len(pending),
        "failures": failures,
        "collapseWarnings": collapse,
    }
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))

    if reachable_groups < 4:
        print("Fewer than four group news feeds were reachable during deep backfill.", file=sys.stderr)
        return 2
    if collapse:
        print("Candidate counts collapsed; existing data left untouched for safety.", file=sys.stderr)
        return 2
    if args.check:
        print("Deep live source check passed; no files were modified.")
        return 0

    payload = retention.build_payload(
        existing,
        fresh_by_id,
        merge_pending(existing, pending),
        failures,
        datetime.now(parser_v1.JST).date(),
    )
    payload["source"] = "KAWAII LAB.各グループ公式サイトの公開INFORMATION（通常巡回＋週次深掘り）"
    payload["deepDiagnostics"] = {
        "updatedAt": datetime.now(parser_v1.JST).isoformat(timespec="seconds"),
        "scannedPages": pages,
        "candidateCounts": counts,
        "skippedKnownCandidates": skipped,
    }
    parser_v1.OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    parser_v1.OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Deep backfill wrote {len(payload['events'])} retained/future events; {len(fresh_by_id)} newly parsed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
