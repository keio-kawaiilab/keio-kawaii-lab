#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Callable, Iterable

import reconcile_birthday_ticket_rows as birthday_reconcile
import update_official_birthday_news as birthday_news
import update_official_schedule as official
import update_official_x_birthday_events as birthday_merge

BIRTHDAY_NEWS_PAGES = 3


def _fetch_month(group: str, base: str, year: int, month: int, today: date, session_factory=official.make_session):
    session = session_factory()
    url = f"{base}/live_information/schedule/list/?viewMode=default&year={year}&month={month:02d}"
    try:
        response = session.get(url, timeout=25)
        response.raise_for_status()
        rows = official.parse_schedule_list(response.text, group, base, year, month, today)
        return group, rows, url
    finally:
        close = getattr(session, "close", None)
        if callable(close):
            close()


def collect_parallel(
    today: date,
    *,
    max_workers: int = 10,
    groups: dict[str, str] | None = None,
    months: Iterable[tuple[int, int]] | None = None,
    session_factory=official.make_session,
) -> tuple[list[official.OfficialRow], dict, dict]:
    groups = groups or official.GROUPS
    months = tuple(months or official.month_pairs(today))
    tasks = [(group, base, year, month) for group, base in groups.items() for year, month in months]
    workers = max(1, min(max_workers, len(tasks) or 1))
    started = time.monotonic()
    grouped_rows: dict[str, list[official.OfficialRow]] = defaultdict(list)
    failures: list[dict] = []

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="official-list") as pool:
        futures = {
            pool.submit(_fetch_month, group, base, year, month, today, session_factory): (group, base, year, month)
            for group, base, year, month in tasks
        }
        for future in as_completed(futures):
            group, base, year, month = futures[future]
            url = f"{base}/live_information/schedule/list/?viewMode=default&year={year}&month={month:02d}"
            try:
                _, rows, _ = future.result()
                grouped_rows[group].extend(rows)
            except Exception as exc:
                failures.append({"group": group, "url": url, "error": f"{type(exc).__name__}: {exc}"})

    if failures:
        raise RuntimeError("Official schedule parallel crawl was incomplete: " + json.dumps(failures, ensure_ascii=False))

    all_rows: list[official.OfficialRow] = []
    status = {}
    for group in groups:
        deduped = {(row.group, row.day, row.url): row for row in grouped_rows.get(group, [])}
        rows = list(deduped.values())
        all_rows.extend(rows)
        status[group] = {"count": len(rows), "monthsChecked": len(months)}

    diagnostics = {
        "listMode": "parallel",
        "listWorkers": workers,
        "listRequests": len(tasks),
        "listDurationSeconds": round(time.monotonic() - started, 3),
    }
    return all_rows, status, diagnostics


def _needs_detail(row: official.OfficialRow, events: list[dict]) -> bool:
    matched = official.match_existing(row, events)
    if not matched:
        return True
    source = str(matched.get("sourceType") or matched.get("primarySource") or "").lower()
    current_title = official.normalize_space(matched.get("eventTitle") or matched.get("title"))
    single_performance = len(official.event_days(matched)) == 1
    return (
        source in official.PLAYGUIDE_SOURCES
        or bool(official.GENERIC_TITLE_RE.fullmatch(current_title))
        or not matched.get("venue")
        or (single_performance and not (matched.get("openTime") and matched.get("startTime")))
    )


def detail_urls_needed(payload: dict, rows: list[official.OfficialRow]) -> list[str]:
    events = [dict(event) for event in payload.get("events", []) if isinstance(event, dict)]
    events = [event for event in events if event.get("sourceType") != "official-schedule"]
    return list(dict.fromkeys(row.url for row in rows if _needs_detail(row, events)))


def _fetch_detail(url: str, session_factory=official.make_session):
    session = session_factory()
    try:
        response = session.get(url, timeout=25)
        response.raise_for_status()
        return url, response
    finally:
        close = getattr(session, "close", None)
        if callable(close):
            close()


def prefetch_details(
    urls: Iterable[str],
    *,
    max_workers: int = 10,
    session_factory=official.make_session,
) -> tuple[dict[str, object], dict]:
    urls = tuple(dict.fromkeys(urls))
    workers = max(1, min(max_workers, len(urls) or 1))
    started = time.monotonic()
    responses: dict[str, object] = {}
    failures: list[dict] = []
    if not urls:
        return responses, {"detailMode": "parallel", "detailWorkers": 0, "detailRequests": 0, "detailDurationSeconds": 0.0}

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="official-detail") as pool:
        futures = {pool.submit(_fetch_detail, url, session_factory): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                _, response = future.result()
                responses[url] = response
            except Exception as exc:
                failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
    if failures:
        raise RuntimeError("Official detail parallel crawl was incomplete: " + json.dumps(failures, ensure_ascii=False))
    return responses, {
        "detailMode": "parallel",
        "detailWorkers": workers,
        "detailRequests": len(urls),
        "detailDurationSeconds": round(time.monotonic() - started, 3),
    }


class CachedSession:
    def __init__(self, responses: dict[str, object], fallback):
        self.responses = responses
        self.fallback = fallback

    def get(self, url: str, *args, **kwargs):
        if url in self.responses:
            return self.responses[url]
        return self.fallback.get(url, *args, **kwargs)


def enrich_birthday_ticket_windows(
    payload: dict,
    today: date,
    *,
    pages: int = BIRTHDAY_NEWS_PAGES,
    session_factory=official.make_session,
    collector=birthday_news.collect,
) -> tuple[dict, dict]:
    """Enrich birthday rows from official NEWS inside the main 15-minute path.

    Birthday announcements used to run only in a side workflow. The main
    distributed refresh could therefore publish a schedule/promoter-only row
    afterwards and put `現在受付なし` back on an event whose FC sale was open.
    Running the official NEWS enrichment here makes the core snapshot itself
    authoritative for birthday application windows.
    """
    session = session_factory()
    try:
        rows, failures, diagnostics = collector(session, payload, today=today, pages=pages)
    finally:
        close = getattr(session, "close", None)
        if callable(close):
            close()

    enriched = birthday_merge.merge_birthday_events(payload, rows)
    reconciled, reconcile_report = birthday_reconcile.reconcile(enriched)
    return reconciled, {
        "collector": "official-birthday-news-in-core",
        "ticketRows": len(rows),
        "failures": failures,
        "scan": diagnostics,
        "reconcile": reconcile_report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Parallel official schedule crawler")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    today = datetime.now(official.JST).date()
    rows, status, list_diag = collect_parallel(today, max_workers=args.workers)
    if not rows or any(status[group]["count"] == 0 for group in official.GROUPS):
        raise SystemExit(f"Official schedule crawl returned an unsafe result: {status}")
    if args.check:
        print(json.dumps({"officialRows": len(rows), "groups": status, **list_diag}, ensure_ascii=False, indent=2))
        return 0

    payload = json.loads(official.DATA_PATH.read_text(encoding="utf-8"))
    needed_urls = detail_urls_needed(payload, rows)
    detail_responses, detail_diag = prefetch_details(needed_urls, max_workers=args.workers)
    fallback = official.make_session()
    try:
        merged, diagnostics = official.merge(payload, rows, CachedSession(detail_responses, fallback))
    finally:
        fallback.close()

    # Birthday ticket information is part of the main source snapshot, not a
    # best-effort side patch. Fail soft on a temporary NEWS outage: the merged
    # payload already contains the previous known-good rows, so no ticket data
    # is erased when official NEWS cannot be reached.
    try:
        merged, birthday_diag = enrich_birthday_ticket_windows(merged, today)
    except Exception as exc:
        birthday_diag = {
            "collector": "official-birthday-news-in-core",
            "failures": [{"stage": "collector", "error": f"{type(exc).__name__}: {exc}"}],
            "ticketRows": 0,
        }

    if any(not row.represented_by for row in rows):
        raise SystemExit("Not every official schedule row was represented; refusing to write")

    index = {
        "updatedAt": datetime.now(official.JST).isoformat(timespec="seconds"),
        "range": {"start": today.isoformat(), "monthsAhead": official.MONTHS_AHEAD},
        "groups": status,
        "entries": [row.as_index() for row in rows],
    }
    official.DATA_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    official.INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**diagnostics, **list_diag, **detail_diag, "birthdayNews": birthday_diag}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
