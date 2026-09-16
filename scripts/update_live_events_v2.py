#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import update_live_events as parser_v1

CENTRAL_FC_BASE = "https://kawaiilab.asobisystem.com"
FC_HINT_RE = re.compile(r"OFFICIAL\s*FANCLUB|ファンクラブ|FC(?:会員)?先行", re.I)
NEWS_SCAN_PAGES = 15
NEWS_PAGE_WORKERS = 5
MAX_FETCH_ATTEMPTS = 3
DISCOVERED_BY_GROUP: dict[str, dict[str, parser_v1.Candidate]] = {}
FEED_FAILURES: dict[str, list[dict]] = {}


def _get_with_retry(session: requests.Session, url: str, timeout: int = 20):
    last_exc: Exception | None = None
    for attempt in range(MAX_FETCH_ATTEMPTS):
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            return response
        except Exception as exc:  # pragma: no cover - network dependent
            last_exc = exc
            if attempt + 1 < MAX_FETCH_ATTEMPTS:
                time.sleep(0.8 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def _fetch_news_page(url: str, headers: dict[str, str]) -> str:
    # requests.Session is deliberately not shared across threads.
    with requests.Session() as worker_session:
        worker_session.headers.update(headers)
        return _get_with_retry(worker_session, url, timeout=20).text


def deep_candidate_links(session: requests.Session, group: str, base: str) -> list[parser_v1.Candidate]:
    """Scan fifteen official news pages, at five-page concurrency, and account for every ticket article."""
    found: dict[str, parser_v1.Candidate] = {}
    page_urls = {page: f"{base}/news/1/?page={page}" for page in range(1, NEWS_SCAN_PAGES + 1)}
    page_urls[0] = f"{base}/"
    html_by_page: dict[int, str] = {}
    headers = {str(k): str(v) for k, v in session.headers.items()}

    with ThreadPoolExecutor(max_workers=NEWS_PAGE_WORKERS) as pool:
        futures = {pool.submit(_fetch_news_page, url, headers): page for page, url in page_urls.items()}
        for future in as_completed(futures):
            page = futures[future]
            try:
                html_by_page[page] = future.result()
            except Exception as exc:
                FEED_FAILURES.setdefault(group, []).append({
                    "group": group, "stage": "news-page", "url": page_urls[page], "error": str(exc),
                })
    if not html_by_page:
        raise RuntimeError(f"No official index was readable for {group}")

    # Parse in page order so diagnostics and dedupe stay deterministic.
    for page in sorted(html_by_page):
        soup = BeautifulSoup(html_by_page[page], "html.parser")
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "")
            if "/news/detail/" not in href:
                continue
            title = parser_v1.normalize_space(anchor.get_text(" ", strip=True))
            if not title:
                continue
            if page > 2 and not any(key in title for key in parser_v1.TICKET_HINTS):
                continue
            if any(key in title for key in parser_v1.IGNORE_TITLE_HINTS):
                continue
            full = urljoin(base, href)
            if urlparse(full).netloc == urlparse(base).netloc:
                found[full] = parser_v1.Candidate(group=group, title=title, url=full)

    DISCOVERED_BY_GROUP[group] = dict(found)
    return list(found.values())


def parse_day(value: object) -> date | None:
    text = str(value or "")[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def event_last_day(event: dict) -> date | None:
    values = [event.get("eventEndDate"), event.get("eventDate"), *(event.get("eventDates") or [])]
    values.extend(row.get("date") for row in (event.get("schedule") or []) if isinstance(row, dict))
    days = [day for value in values if (day := parse_day(value)) is not None]
    return max(days) if days else None


def should_show(event: dict, today: date) -> bool:
    last_day = event_last_day(event)
    if last_day is None:
        return True
    return last_day >= today


def event_urls(event: dict) -> set[str]:
    result = {str(x) for x in (event.get("urls") or []) if x}
    if event.get("url"):
        result.add(str(event["url"]))
    return result


def represented_by_fresh(event: dict, fresh_by_id: dict[str, dict], fresh_urls: set[str]) -> bool:
    source_type = event.get("sourceType")
    if source_type == "auto":
        return bool(event.get("id") and event.get("id") in fresh_by_id)
    if source_type == "derived":
        urls = event_urls(event)
        return bool(urls) and urls.issubset(fresh_urls)
    return False


def performance_title(title: str, group: str) -> str:
    text = parser_v1.normalize_space(title)
    text = re.sub(r"^[【\[]\s*" + re.escape(group) + r"\s*[】\]]\s*", "", text, flags=re.I)
    text = re.split(
        r"KAWAII\s*LAB\.?\s*OFFICIAL\s*FANCLUB|OFFICIAL\s*FANCLUB|"
        r"FC(?:会員)?先行|ファンクラブ先行|先行受付(?:開始)?|チケット受付",
        text,
        maxsplit=1,
        flags=re.I,
    )[0]
    text = text.strip(" 　!！｜|・-–—:：[]【】「」")
    if not text:
        text = title
    if not re.match(r"^" + re.escape(group) + r"(?:\s|$)", text, re.I):
        text = f"{group} {text}"
    return parser_v1.normalize_space(text)


def title_key(value: object, group: str = "") -> str:
    text = str(value or "").lower()
    if group:
        text = re.sub(re.escape(group.lower()), "", text)
    text = FC_HINT_RE.sub("", text)
    text = re.sub(r"先行受付(?:開始)?|受付開始|チケット|会員", "", text)
    return re.sub(r"[\s　!！・|｜\-–—_【】\[\]()（）『』「」:：./]", "", text)


def infer_group(title: str, existing: dict) -> str | None:
    direct = [group for group in parser_v1.GROUPS if group.lower() in title.lower()]
    if len(direct) == 1:
        return direct[0]
    raw_key = title_key(title)
    matches: list[str] = []
    for event in existing.get("events", []):
        if not isinstance(event, dict):
            continue
        group = str(event.get("group") or "")
        if group not in parser_v1.GROUPS:
            continue
        key = title_key(event.get("eventTitle") or event.get("title"), group)
        if key and raw_key and (key in raw_key or raw_key in key):
            matches.append(group)
    unique = list(dict.fromkeys(matches))
    return unique[0] if len(unique) == 1 else None


def find_existing_performance(existing: dict, group: str, title: str) -> dict | None:
    wanted = title_key(title, group)
    candidates = []
    for event in existing.get("events", []):
        if not isinstance(event, dict) or event.get("group") != group:
            continue
        key = title_key(event.get("eventTitle") or event.get("title"), group)
        if key and wanted and (key in wanted or wanted in key):
            candidates.append(event)
    candidates.sort(key=lambda event: (
        0 if event.get("ticketType") == "現在受付なし" else 1,
        str(event.get("eventDate") or "9999"),
    ))
    return dict(candidates[0]) if candidates else None


def central_fallback_event(candidate, review: dict, existing: dict, group: str) -> dict | None:
    start = review.get("applyStart")
    end = review.get("applyEnd")
    if not start or not end:
        return None
    stable_title = performance_title(candidate.title, group)
    base = find_existing_performance(existing, group, stable_title)
    if not base or not base.get("eventDate"):
        return None
    event_date = str(base["eventDate"])[:10]
    return {
        "id": parser_v1.event_id(group, candidate.url, event_date, str(start), "KAWAII LAB. FC先行"),
        "group": group,
        "title": candidate.title,
        "eventTitle": stable_title,
        "ticketType": "KAWAII LAB. FC先行",
        "applyStart": start,
        "applyEnd": end,
        "resultDate": None,
        "paymentEnd": None,
        "eventDate": event_date,
        "venue": base.get("venue"),
        "openTime": base.get("openTime"),
        "startTime": base.get("startTime"),
        "url": candidate.url,
        "sourceType": "auto",
        "sourceChannel": "kawaii-lab-fc",
    }


def collect_central_fc(session: requests.Session, existing: dict) -> tuple[dict[str, dict], list[dict], list[dict], list[parser_v1.Candidate]]:
    events_by_id: dict[str, dict] = {}
    pending: list[dict] = []
    failures: list[dict] = []
    try:
        all_candidates = deep_candidate_links(session, "KAWAII LAB. FC", CENTRAL_FC_BASE)
    except Exception as exc:
        return {}, [], [{"group": "KAWAII LAB. FC", "stage": "news-list", "error": str(exc)}], []

    candidates = [candidate for candidate in all_candidates if FC_HINT_RE.search(candidate.title)]
    for source_candidate in candidates:
        group = infer_group(source_candidate.title, existing)
        if not group:
            pending.append({
                "group": "KAWAII LAB. FC",
                "title": source_candidate.title,
                "url": source_candidate.url,
                "reason": "対象グループを一意に特定できないため確認待ちにしました。",
            })
            continue
        candidate = parser_v1.Candidate(group=group, title=source_candidate.title, url=source_candidate.url)
        try:
            parsed, review = parser_v1.parse_candidate(session, candidate)
            if parsed:
                stable_title = performance_title(candidate.title, group)
                for event in parsed:
                    event["ticketType"] = "KAWAII LAB. FC先行"
                    event["eventTitle"] = stable_title
                    event["sourceChannel"] = "kawaii-lab-fc"
                    event["id"] = parser_v1.event_id(
                        group,
                        str(event.get("url") or candidate.url),
                        str(event.get("eventDate") or "")[:10],
                        str(event.get("applyStart") or ""),
                        event["ticketType"],
                    )
                    events_by_id[event["id"]] = event
            elif review:
                fallback = central_fallback_event(candidate, review, existing, group)
                if fallback:
                    events_by_id[fallback["id"]] = fallback
                else:
                    pending.append(review)
        except Exception as exc:
            failures.append({"group": group, "url": candidate.url, "stage": "central-fc-article", "error": str(exc)})
    return events_by_id, pending, failures, candidates


def account_unresolved_candidates(
    fresh_by_id: dict[str, dict], pending: list[dict], failures: list[dict], central_candidates: list[parser_v1.Candidate]
) -> list[dict]:
    """Every discovered official ticket article must be parsed, pending, or failed explicitly."""
    intended: dict[str, parser_v1.Candidate] = {}
    for group in parser_v1.GROUPS:
        intended.update(DISCOVERED_BY_GROUP.get(group, {}))
    intended.update({candidate.url: candidate for candidate in central_candidates})

    accounted = {str(event.get("url") or "") for event in fresh_by_id.values() if event.get("url")}
    accounted.update(str(item.get("url") or "") for item in pending if isinstance(item, dict) and item.get("url"))
    accounted.update(str(item.get("url") or "") for item in failures if isinstance(item, dict) and item.get("url"))

    added: list[dict] = []
    for url, candidate in intended.items():
        if url in accounted:
            continue
        review = {
            "group": candidate.group,
            "title": candidate.title,
            "url": candidate.url,
            "reason": "チケット関連の公式記事として検出しましたが、申込期間または公演との対応を安全に自動抽出できなかったため確認待ちにしました。",
        }
        pending.append(review)
        added.append(review)
    return added


def build_payload(existing: dict, fresh_by_id: dict[str, dict], pending: list[dict], failures: list[dict], today: date) -> dict:
    from performance_entities import build_public_events
    from resolve_source_priority import canonical_title, event_days
    existing = deepcopy(existing)
    known, _ = build_public_events(existing.get("events", []))
    for event in fresh_by_id.values():
        matches = [row for row in known
                   if row.get("group") == event.get("group") and row.get("eventDate") == event.get("eventDate")
                   and event.get("url") in event_urls(row)
                   and (not event.get("startTime") or not row.get("startTime") or event["startTime"] == row["startTime"])]
        if not matches:
            wanted = canonical_title(event)
            matches = [row for row in known
                       if row.get("group") == event.get("group") and row.get("eventDate") == event.get("eventDate")
                       and wanted and canonical_title(row) and (wanted in canonical_title(row) or canonical_title(row) in wanted)
                       and (not event.get("startTime") or not row.get("startTime") or event["startTime"] == row["startTime"])]
        if len(matches) == 1:
            for field in ("eventTitle", "displayTitle", "venue", "openTime", "startTime", "eventScope", "officialScheduleUrl"):
                if not event.get(field) and matches[0].get(field):
                    event[field] = matches[0][field]
            if event.get("startTime") and not matches[0].get("startTime"):
                source_ids = set(matches[0].get("sourceRowIds") or [matches[0].get("id")])
                for previous in existing.get("events", []):
                    if previous.get("id") in source_ids and not previous.get("startTime") and len(event_days(previous)) == 1:
                        previous["startTime"] = event["startTime"]
                        previous["performanceTimeSourceUrl"] = event.get("url")
    fresh_urls = {str(e.get("url")) for e in fresh_by_id.values() if e.get("url")}
    fresh_events = []
    for event in fresh_by_id.values():
        if not should_show(event, today):
            continue
        end = str(event.get("applyEnd") or "")
        if end and end[:10] < today.isoformat():
            # The observation is archived before this merge. An ended reception
            # does not need another application row for an already known show.
            if any((row.get("group") == event.get("group") or event.get("group") in (row.get("participants") or []))
                   and event.get("eventDate") in event_days(row) for row in known):
                continue
        fresh_events.append(event)
    retained: list[dict] = []
    for original in existing.get("events", []):
        if not isinstance(original, dict):
            continue
        event = dict(original)
        if not should_show(event, today):
            continue
        if represented_by_fresh(event, fresh_by_id, fresh_urls):
            continue
        retained.append(event)

    result: list[dict] = []
    seen_ids: set[str] = set()
    for event in retained + fresh_events:
        event_id = str(event.get("id") or "")
        if event_id and event_id in seen_ids:
            continue
        if event_id:
            seen_ids.add(event_id)
        result.append(event)
    result.sort(key=lambda e: (
        str(e.get("eventDate") or "9999"),
        str(e.get("applyEnd") or "9999"),
        str(e.get("group") or ""),
    ))
    return {
        **existing,
        "demo": False,
        "updatedAt": datetime.now(parser_v1.JST).isoformat(timespec="seconds"),
        "source": "KAWAII LAB.各グループ公式サイト + KAWAII LAB. OFFICIAL FANCLUB公開情報（本日以降の公演のみ）",
        "events": result,
        "pendingReview": pending,
        "failures": failures,
    }


def main() -> int:
    cli = argparse.ArgumentParser(description="Update LIVE calendar with deep official ticket discovery and explicit conservation checks.")
    cli.add_argument("--check", action="store_true")
    args = cli.parse_args()

    DISCOVERED_BY_GROUP.clear()
    FEED_FAILURES.clear()
    session = requests.Session()
    session.headers.update({"User-Agent": "KeioKawaiiLabCalendarBot/2.2 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"})
    existing = parser_v1.read_existing()
    state_path = Path("data/official-discovery-state.json")
    if state_path.exists():
        existing["officialDiscoveryState"] = json.loads(state_path.read_text(encoding="utf-8"))

    from continuous_official_discovery import collect
    fresh_by_id, pending, failures, candidate_counts, observations = collect(session, existing)
    central_events = {key: row for key, row in fresh_by_id.items() if row.get("sourceChannel") == "kawaii-lab-fc"}
    central_candidates = range(candidate_counts.get("KAWAII LAB. FC", 0))
    newly_pending = pending
    failed_lists = {
        str(item.get("group")) for item in failures
        if isinstance(item, dict) and item.get("stage") == "news-list"
    }
    reachable_group_feeds = len(parser_v1.GROUPS) - len(failed_lists.intersection(set(parser_v1.GROUPS)))
    central_feed_reachable = "KAWAII LAB. FC" not in failed_lists

    official_candidates = sum(candidate_counts.get(group, 0) for group in parser_v1.GROUPS)
    pending_urls = sorted({str(x.get("url") or "") for x in pending if isinstance(x, dict) and x.get("url")})
    diagnostics = {
        "collectedAt": datetime.now(parser_v1.JST).isoformat(timespec="seconds"),
        "newsPagesScannedPerOfficialSource": NEWS_SCAN_PAGES,
        "newsPageWorkersPerSource": NEWS_PAGE_WORKERS,
        "reachableGroupNewsFeeds": reachable_group_feeds,
        "centralFcNewsFeedReachable": central_feed_reachable,
        "candidateCounts": candidate_counts,
        "discoveredOfficialTicketArticles": official_candidates + len(central_candidates),
        "parsedEvents": len(fresh_by_id),
        "centralFcEvents": len(central_events),
        "pendingReview": len(pending),
        "pendingReviewUrls": pending_urls,
        "newlyAccountedUnresolvedArticles": len(newly_pending),
        "failureCount": len(failures),
        "failures": failures,
        "status": "degraded" if failures or pending else "ok",
        "observations": observations,
    }
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))

    if args.check:
        return 2 if failures else 0

    import archive_ticket_history as archive
    history = archive.archive_payload(
        {"events": list(fresh_by_id.values())}, archive.load_json(archive.HISTORY_PATH),
        archive.load_json(archive.REGISTRY_PATH), diagnostics["collectedAt"],
    )
    archive.HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload = build_payload(existing, fresh_by_id, pending, failures, datetime.now(parser_v1.JST).date())
    payload["ticketCollectorDiagnostics"] = diagnostics
    payload.pop("officialDiscoveryState", None)
    parser_v1.OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    parser_v1.OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(payload['events'])} current/future events with collector diagnostics.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
