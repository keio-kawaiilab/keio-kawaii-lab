#!/usr/bin/env python3
"""Augment calendar collectors by reading the bodies of the newest official news articles.

The primary collectors intentionally use cheap title filters for deep history scans.
This companion catches same-day announcements whose list-page title does not contain
obvious ticket/special-event keywords.  It only feeds existing parsers; it does not
invent dates, venues or sales windows.
"""
from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import update_live_events as ticket
import update_special_events as special

DATA_PATH = Path("data/live-events.json")
LATEST_INDEX_PAGES = 2
MAX_ARTICLES_PER_GROUP = 36
WORKERS = 12
TIMEOUT = 18


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def get(session: requests.Session, url: str) -> requests.Response:
    response = session.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response


def discover_links(session: requests.Session, group: str, base: str) -> tuple[list[tuple[str, str]], list[dict]]:
    links: dict[str, str] = {}
    failures: list[dict] = []
    index_urls = [f"{base}/", *(f"{base}/news/1/?page={page}" for page in range(1, LATEST_INDEX_PAGES + 1))]
    for index_url in index_urls:
        try:
            soup = BeautifulSoup(get(session, index_url).text, "html.parser")
        except Exception as exc:
            failures.append({"group": group, "stage": "index", "url": index_url, "error": f"{type(exc).__name__}: {exc}"})
            continue
        for anchor in soup.find_all("a", href=True):
            href = urljoin(base, str(anchor.get("href") or ""))
            if "/news/detail/" not in href:
                continue
            label = normalize(anchor.get_text(" ", strip=True))
            links.setdefault(href, label)
            if len(links) >= MAX_ARTICLES_PER_GROUP:
                break
        if len(links) >= MAX_ARTICLES_PER_GROUP:
            break
    return list(links.items()), failures


def fetch_article(url: str, list_title: str, headers: dict[str, str]) -> dict:
    with requests.Session() as session:
        session.headers.update(headers)
        response = get(session, url)
    soup = BeautifulSoup(response.text, "html.parser")
    heading = soup.find("h1")
    title = normalize(heading.get_text(" ", strip=True) if heading else list_title)
    text = normalize(soup.get_text(" ", strip=True))
    return {"url": url, "title": title or list_title, "text": text, "html": response.text}


def scan_articles(session: requests.Session) -> tuple[list[dict], list[dict]]:
    queued: dict[str, tuple[str, str]] = {}
    failures: list[dict] = []
    for group, base in ticket.GROUPS.items():
        links, failed = discover_links(session, group, base)
        failures.extend(failed)
        for url, title in links:
            queued.setdefault(url, (group, title))

    headers = {str(k): str(v) for k, v in session.headers.items()}
    articles: list[dict] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(fetch_article, url, title, headers): (group, url)
            for url, (group, title) in queued.items()
        }
        for future in as_completed(futures):
            group, url = futures[future]
            try:
                row = future.result()
                row["group"] = group
                articles.append(row)
            except Exception as exc:
                failures.append({"group": group, "stage": "article", "url": url, "error": f"{type(exc).__name__}: {exc}"})
    return articles, failures


def has_ticket_signal(article: dict) -> bool:
    corpus = f"{article.get('title', '')} {article.get('text', '')[:12000]}"
    if any(hint in str(article.get("title") or "") for hint in ticket.IGNORE_TITLE_HINTS):
        return False
    return any(hint in corpus for hint in ticket.TICKET_HINTS)


def future_event(event: dict) -> bool:
    today = datetime.now(ticket.JST).date().isoformat()
    dates = []
    for row in event.get("schedule") or []:
        if isinstance(row, dict) and row.get("date"):
            dates.append(str(row["date"])[:10])
    dates.extend(str(value)[:10] for value in event.get("eventDates") or [] if value)
    if event.get("eventDate"):
        dates.append(str(event["eventDate"])[:10])
    return not dates or max(dates) >= today


def augment_ticket(payload: dict, articles: list[dict], failures: list[dict]) -> tuple[dict, dict]:
    session = requests.Session()
    session.headers.update({"User-Agent": "KeioKawaiiLabCalendarBot/2.3 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"})
    additions: dict[str, dict] = {}
    pending = list(payload.get("pendingReview") or [])
    pending_urls = {str(row.get("url") or "") for row in pending if isinstance(row, dict)}
    candidates = 0

    for article in articles:
        if not has_ticket_signal(article):
            continue
        candidates += 1
        candidate = ticket.Candidate(
            group=str(article["group"]),
            title=str(article.get("title") or ""),
            url=str(article["url"]),
        )
        try:
            parsed, review = ticket.parse_candidate(session, candidate)
        except Exception as exc:
            failures.append({"group": candidate.group, "stage": "ticket-parse", "url": candidate.url, "error": f"{type(exc).__name__}: {exc}"})
            continue
        for event in parsed or []:
            if not future_event(event):
                continue
            event = dict(event)
            event["sourceChannel"] = "recent-official-body"
            event["discoverySourceUrl"] = candidate.url
            event_id = str(event.get("id") or "")
            if event_id:
                additions[event_id] = event
        if review and candidate.url not in pending_urls:
            row = dict(review)
            row["discoveryMethod"] = "recent-official-body"
            pending.append(row)
            pending_urls.add(candidate.url)

    by_id: dict[str, dict] = {}
    no_id: list[dict] = []
    for event in payload.get("events", []):
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("id") or "")
        if event_id:
            by_id[event_id] = event
        else:
            no_id.append(event)
    by_id.update(additions)
    out = dict(payload)
    out["events"] = sorted(
        [*no_id, *(event for event in by_id.values() if future_event(event))],
        key=lambda event: (str(event.get("eventDate") or "9999"), str(event.get("group") or ""), str(event.get("applyEnd") or "9999")),
    )
    out["pendingReview"] = pending
    diagnostics = {
        "scannedArticles": len(articles),
        "bodyTicketCandidates": candidates,
        "parsedAdditionsOrRefreshes": len(additions),
        "failureCount": len(failures),
        "failures": failures,
    }
    out["recentOfficialBodyDiscovery"] = diagnostics
    return out, diagnostics


def augment_special(payload: dict, articles: list[dict], failures: list[dict]) -> tuple[dict, dict]:
    fresh: list[dict] = []
    candidates = 0
    for article in articles:
        corpus = f"{article.get('title', '')} {article.get('text', '')[:16000]}"
        if not special.SPECIAL_RE.search(corpus):
            continue
        if special.ANCILLARY_SPECIAL_RE.search(str(article.get("title") or "")):
            continue
        candidates += 1
        try:
            parsed = special.parse_page(str(article["group"]), str(article["url"]), str(article["html"]))
        except Exception as exc:
            failures.append({"group": article["group"], "stage": "special-parse", "url": article["url"], "error": f"{type(exc).__name__}: {exc}"})
            continue
        for event in parsed:
            event = special.add_discovery_source(event, str(article["url"]))
            fresh.append(event)

    out = special.merge_payload(payload, fresh) if fresh else dict(payload)
    diagnostics = {
        "scannedArticles": len(articles),
        "bodySpecialCandidates": candidates,
        "parsedSpecialRows": len(fresh),
        "failureCount": len(failures),
        "failures": failures,
    }
    out["recentOfficialBodySpecialDiscovery"] = diagnostics
    return out, diagnostics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("ticket", "special"), required=True)
    args = parser.parse_args()

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update({"User-Agent": "KeioKawaiiLabCalendarBot/2.3 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"})
    articles, failures = scan_articles(session)
    if not articles:
        print(json.dumps({"status": "degraded", "reason": "no recent official articles readable", "failures": failures}, ensure_ascii=False, indent=2))
        return 2

    if args.mode == "ticket":
        out, diagnostics = augment_ticket(payload, articles, failures)
    else:
        out, diagnostics = augment_special(payload, articles, failures)

    DATA_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "mode": args.mode, **diagnostics}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
