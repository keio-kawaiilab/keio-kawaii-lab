#!/usr/bin/env python3
"""Discover schedule/ticket updates from the umbrella KAWAII LAB. official site.

This is a supplemental collector. It crawls the KAWAII LAB. OFFICIAL FANCLUB
itself in addition to the five individual group sites, maps umbrella NEWS posts
to explicitly named groups, and imports future LIVE/EVENT rows from the umbrella
SCHEDULE. A failure here never destroys the last-good public calendar.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import augment_recent_official_news as body
import update_live_events as ticket
import update_official_schedule as official
from schedule_scope import infer_event_scope

DATA_PATH = Path("data/live-events.json")
BASE = "https://kawaiilab.asobisystem.com"
NEWS_INDEX_PAGES = 5
MAX_NEWS_ARTICLES = 120
SCHEDULE_PAGES_PER_MONTH = 5
WORKERS = 12
TIMEOUT = 20

EXTRA_GROUPS = ("KAWAII LAB. MATES", "KAWAII LAB. SOUTH")
ALL_NAMED_GROUPS = (*ticket.GROUPS.keys(), *EXTRA_GROUPS)


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def compact(value: object) -> str:
    return re.sub(r"[^0-9A-Zぁ-んァ-ヶ一-龠]+", "", normalize(value).upper())


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "KeioKawaiiLabCalendarBot/2.4 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"
    })
    return s


def infer_target_groups(text: object) -> list[str]:
    """Infer groups only when the official page explicitly names them."""
    haystack = compact(text)
    found: list[str] = []
    for group in ALL_NAMED_GROUPS:
        if compact(group) in haystack:
            found.append(group)
    return found


def fetch_page(url: str, headers: dict[str, str]) -> tuple[str, str]:
    with requests.Session() as s:
        s.headers.update(headers)
        response = s.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        return response.text, response.url


def discover_news_links(s: requests.Session) -> tuple[list[tuple[str, str]], list[dict]]:
    links: dict[str, str] = {}
    failures: list[dict] = []
    urls = [f"{BASE}/", *(f"{BASE}/news/1/?page={page}" for page in range(1, NEWS_INDEX_PAGES + 1))]
    for index_url in urls:
        try:
            response = s.get(index_url, timeout=TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as exc:
            failures.append({"stage": "umbrella-news-index", "url": index_url, "error": f"{type(exc).__name__}: {exc}"})
            continue
        for anchor in soup.find_all("a", href=True):
            href = urljoin(BASE, str(anchor.get("href") or ""))
            if "/news/detail/" not in href:
                continue
            links.setdefault(href, normalize(anchor.get_text(" ", strip=True)))
            if len(links) >= MAX_NEWS_ARTICLES:
                break
        if len(links) >= MAX_NEWS_ARTICLES:
            break
    return list(links.items()), failures


def collect_news_articles(s: requests.Session) -> tuple[list[dict], list[dict], dict]:
    links, failures = discover_news_links(s)
    headers = {str(k): str(v) for k, v in s.headers.items()}
    articles: list[dict] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(fetch_page, url, title, headers) if False else pool.submit(fetch_page, url, headers): (url, title) for url, title in links}
        for future in as_completed(futures):
            url, list_title = futures[future]
            try:
                html, resolved_url = future.result()
                soup = BeautifulSoup(html, "html.parser")
                heading = soup.find("h1")
                title = normalize(heading.get_text(" ", strip=True) if heading else list_title)
                text = normalize(soup.get_text(" ", strip=True))
                articles.append({"url": resolved_url or url, "title": title or list_title, "text": text, "html": html})
            except Exception as exc:
                failures.append({"stage": "umbrella-news-article", "url": url, "error": f"{type(exc).__name__}: {exc}"})

    expanded: list[dict] = []
    group_counts: dict[str, int] = {}
    unmapped_relevant: list[dict] = []
    for article in articles:
        groups = infer_target_groups(f"{article.get('title', '')} {article.get('text', '')[:20000]}")
        relevant = body.has_ticket_signal(article) or bool(body.special.SPECIAL_RE.search(f"{article.get('title', '')} {article.get('text', '')[:16000]}"))
        if not groups:
            if relevant:
                unmapped_relevant.append({"title": article.get("title"), "url": article.get("url")})
            continue
        for group in groups:
            row = dict(article)
            row["group"] = group
            row["umbrellaSource"] = True
            expanded.append(row)
            group_counts[group] = group_counts.get(group, 0) + 1

    diagnostics = {
        "newsLinksDiscovered": len(links),
        "newsArticlesRead": len(articles),
        "mappedArticleCopies": len(expanded),
        "mappedGroupCounts": group_counts,
        "unmappedRelevantCount": len(unmapped_relevant),
        "unmappedRelevant": unmapped_relevant[:20],
    }
    return expanded, failures, diagnostics


def event_days(event: dict) -> list[str]:
    return official.event_days(event)


def event_groups(event: dict) -> list[str]:
    values = [str(v) for v in event.get("participants") or [] if v]
    group = str(event.get("group") or "")
    if group and group not in values:
        values.append(group)
    return values


def find_existing(events: list[dict], day: str, title: str, url: str, groups: list[str]) -> dict | None:
    # URL identity is strongest and does not depend on display titles.
    for event in events:
        urls = [str(event.get("url") or ""), str(event.get("officialScheduleUrl") or ""), *(str(v) for v in event.get("urls") or [])]
        if url in urls:
            return event

    key = official.event_key(title)
    candidates = [event for event in events if day in event_days(event) and official.event_key(event.get("eventTitle") or event.get("title")) == key]
    if groups:
        group_matched = [event for event in candidates if set(groups) & set(event_groups(event))]
        if len(group_matched) == 1:
            return group_matched[0]
    return candidates[0] if len(candidates) == 1 else None


def collect_schedule(s: requests.Session, today) -> tuple[list[tuple[official.OfficialRow, str]], list[dict], dict]:
    rows_by_key: dict[tuple[str, str], official.OfficialRow] = {}
    failures: list[dict] = []
    pages_checked = 0
    for year, month in official.month_pairs(today):
        for page in range(1, SCHEDULE_PAGES_PER_MONTH + 1):
            url = f"{BASE}/live_information/schedule/list/?viewMode=default&year={year}&month={month:02d}&page={page}"
            try:
                response = s.get(url, timeout=TIMEOUT)
                response.raise_for_status()
                pages_checked += 1
                parsed = official.parse_schedule_list(response.text, "KAWAII LAB.", BASE, year, month, today)
                for row in parsed:
                    rows_by_key[(row.day, row.url)] = row
                # Later pages usually repeat no LIVE/EVENT links. Stop early only after page 2.
                if page >= 2 and not parsed:
                    break
            except Exception as exc:
                failures.append({"stage": "umbrella-schedule-list", "url": url, "error": f"{type(exc).__name__}: {exc}"})
                break

    headers = {str(k): str(v) for k, v in s.headers.items()}
    hydrated: list[tuple[official.OfficialRow, str]] = []
    rows = list(rows_by_key.values())
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(fetch_page, row.url, headers): row for row in rows}
        for future in as_completed(futures):
            row = futures[future]
            try:
                html, _ = future.result()
                hydrated.append((row, html))
            except Exception as exc:
                failures.append({"stage": "umbrella-schedule-detail", "url": row.url, "error": f"{type(exc).__name__}: {exc}"})
                hydrated.append((row, ""))

    diagnostics = {
        "schedulePagesChecked": pages_checked,
        "scheduleRowsDiscovered": len(rows),
        "scheduleRowsHydrated": len(hydrated),
    }
    return hydrated, failures, diagnostics


def augment_schedule(payload: dict, rows: list[tuple[official.OfficialRow, str]]) -> tuple[dict, dict]:
    events = [dict(event) for event in payload.get("events", []) if isinstance(event, dict)]
    added = 0
    enriched = 0
    neutral = 0
    represented: list[dict] = []

    for source_row, html in rows:
        detail = official.parse_detail(html) if html else {}
        detail_text = normalize(BeautifulSoup(html, "html.parser").get_text(" ", strip=True)) if html else ""
        groups = infer_target_groups(f"{source_row.title} {detail_text}")
        if groups:
            mapped_rows = [
                official.OfficialRow(
                    group=group,
                    day=source_row.day,
                    category=source_row.category,
                    title=source_row.title,
                    url=source_row.url,
                    event_scope=infer_event_scope({"group": group, "title": source_row.title}),
                )
                for group in groups
            ]
        else:
            neutral += 1
            mapped_rows = [
                official.OfficialRow(
                    group="KAWAII LAB.",
                    day=source_row.day,
                    category=source_row.category,
                    title=source_row.title,
                    url=source_row.url,
                    event_scope=infer_event_scope({"group": "KAWAII LAB.", "title": source_row.title}),
                )
            ]

        existing = find_existing(events, source_row.day, source_row.title, source_row.url, groups)
        if existing is not None:
            for row in mapped_rows:
                official.enrich_existing(existing, row, detail)
            existing.setdefault("discoverySource", "kawaii-lab-official-schedule")
            enriched += 1
            event_id = str(existing.get("id") or "")
        else:
            event = official.build_event(mapped_rows, detail)
            event["discoverySource"] = "kawaii-lab-official-schedule"
            event["officialScheduleSource"] = "KAWAII LAB. OFFICIAL FANCLUB"
            events.append(event)
            added += 1
            event_id = str(event.get("id") or "")

        represented.append({
            "date": source_row.day,
            "title": source_row.title,
            "url": source_row.url,
            "groups": groups or ["KAWAII LAB."],
            "representedBy": event_id,
        })

    out = dict(payload)
    out["events"] = events
    diagnostics = {
        "scheduleEventsAdded": added,
        "scheduleEventsEnriched": enriched,
        "neutralUmbrellaRows": neutral,
        "representedScheduleRows": represented,
    }
    return out, diagnostics


def main() -> int:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    s = session()
    expanded_articles, failures, news_diag = collect_news_articles(s)

    previous_body_ticket = payload.get("recentOfficialBodyDiscovery")
    previous_body_special = payload.get("recentOfficialBodySpecialDiscovery")

    ticket_diag: dict = {}
    special_diag: dict = {}
    if expanded_articles:
        payload, ticket_diag = body.augment_ticket(payload, expanded_articles, failures)
        if previous_body_ticket is None:
            payload.pop("recentOfficialBodyDiscovery", None)
        else:
            payload["recentOfficialBodyDiscovery"] = previous_body_ticket

        payload, special_diag = body.augment_special(payload, expanded_articles, failures)
        if previous_body_special is None:
            payload.pop("recentOfficialBodySpecialDiscovery", None)
        else:
            payload["recentOfficialBodySpecialDiscovery"] = previous_body_special

    today = datetime.now(ticket.JST).date()
    schedule_rows, schedule_failures, schedule_collect_diag = collect_schedule(s, today)
    failures.extend(schedule_failures)
    schedule_diag: dict = {}
    if schedule_rows:
        payload, schedule_diag = augment_schedule(payload, schedule_rows)

    payload["kawaiiLabOfficialDiscovery"] = {
        "status": "ok" if (expanded_articles or schedule_rows) else "degraded",
        "checkedAt": datetime.now(ticket.JST).isoformat(timespec="seconds"),
        **news_diag,
        "ticketParser": ticket_diag,
        "specialParser": special_diag,
        **schedule_collect_diag,
        **schedule_diag,
        "failureCount": len(failures),
        "failures": failures[:50],
    }
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["kawaiiLabOfficialDiscovery"], ensure_ascii=False, indent=2))
    # Supplemental discovery must never globally block the primary collectors.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
