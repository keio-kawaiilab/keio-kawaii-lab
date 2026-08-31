#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

import update_live_events as ticket_parser
import update_official_x_special_events as base

DATA_PATH = Path("data/live-events.json")
NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
TWEET_ID_RE = re.compile(r"^\d{10,22}$")
OFFICIAL_HOSTS = {
    "kawaiilab.asobisystem.com",
    "fruitszipper.asobisystem.com",
    "candytune.asobisystem.com",
    "sweetsteady.asobisystem.com",
    "cutiestreet.asobisystem.com",
    "morestar.asobisystem.com",
}
TICKET_FIELDS = (
    "ticketType",
    "applicationStatus",
    "applyStart",
    "applyEnd",
    "resultDate",
    "paymentEnd",
    "applicationDisplayMode",
    "applicationWindowVerified",
    "deadlineVerified",
    "applicationWindowSource",
    "deadlineSource",
)
APP_HINT_RE = re.compile(
    r"(?:FC|FANCLUB|ファンクラブ|年会費コース).{0,30}(?:先行|受付|申込|販売)|"
    r"(?:先行|受付|申込|販売).{0,30}(?:FC|FANCLUB|ファンクラブ|年会費コース)",
    re.I | re.S,
)
APP_WINDOW_RE = re.compile(
    r"(?:(20\d{2})\s*[./年-]\s*)?(\d{1,2})\s*[./月-]\s*(\d{1,2})日?"
    r"(?:\s*[（(][^）)]*[）)])?\s*(\d{1,2})[:：](\d{2})\s*"
    r"(?:〜|～|~|から|－|—)\s*"
    r"(?:(20\d{2})\s*[./年-]\s*)?(\d{1,2})\s*[./月-]\s*(\d{1,2})日?"
    r"(?:\s*[（(][^）)]*[）)])?\s*(\d{1,2})[:：](\d{2})",
    re.I,
)
APP_END_RE = re.compile(
    r"(?:〜|～|~|まで|締切\s*[：:]?)\s*"
    r"(?:(20\d{2})\s*[./年-]\s*)?(\d{1,2})\s*[./月-]\s*(\d{1,2})日?"
    r"(?:\s*[（(][^）)]*[）)])?\s*(\d{1,2})[:：](\d{2})",
    re.I,
)


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


def _official_urls(node: dict) -> list[str]:
    found: list[str] = []
    for child in _walk(node):
        if not isinstance(child, dict):
            continue
        for key in ("expanded_url", "unwound_url", "expandedUrl", "unwoundUrl"):
            value = normalize_text(child.get(key))
            if not value.startswith(("https://", "http://")):
                continue
            host = (urlparse(value).hostname or "").lower()
            if host not in OFFICIAL_HOSTS:
                continue
            if value not in found:
                found.append(value)
    return found


def extract_posts_from_next_data(html: str, handle: str) -> list[tuple[str, str, list[str]]]:
    match = NEXT_DATA_RE.search(html)
    if not match:
        raise ValueError("X syndication payload did not contain __NEXT_DATA__")

    payload = json.loads(html_lib.unescape(match.group(1)))
    posts: dict[str, tuple[str, list[str]]] = {}
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
        urls = _official_urls(node)
        previous = posts.get(tweet_id)
        if previous:
            merged_urls = list(dict.fromkeys([*previous[1], *urls]))
            posts[tweet_id] = (previous[0] if len(previous[0]) >= len(text) else text, merged_urls)
        else:
            posts[tweet_id] = (text, urls)

    return [
        (f"https://x.com/{handle}/status/{tweet_id}", text, urls)
        for tweet_id, (text, urls) in posts.items()
    ]


def _future_year(month: int, day: int, today: date) -> int | None:
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate >= today - timedelta(days=7):
            return year
    return None


def _iso_datetime(
    year_text: str | None,
    month_text: str,
    day_text: str,
    hour_text: str,
    minute_text: str,
    today: date,
    fallback_year: int | None = None,
) -> str | None:
    month, day = int(month_text), int(day_text)
    year = int(year_text) if year_text else fallback_year or _future_year(month, day, today)
    if not year:
        return None
    try:
        value = datetime(year, month, day, int(hour_text), int(minute_text))
    except ValueError:
        return None
    return value.strftime("%Y-%m-%dT%H:%M")


def _ticket_type(text: str) -> str | None:
    if not APP_HINT_RE.search(text):
        return None
    if "年会費コース" in text and ("先行" in text or "受付" in text):
        return "年会費コース会員先行"
    if re.search(r"KAWAII\s*LAB\.?\s*(?:OFFICIAL\s*)?(?:FANCLUB|FC)", text, re.I):
        return "KAWAII LAB. FC先行"
    if re.search(r"(?:FC|FANCLUB|ファンクラブ).{0,20}(?:先行|受付)|(?:先行|受付).{0,20}(?:FC|FANCLUB|ファンクラブ)", text, re.I | re.S):
        return "FC先行"
    return "チケット受付"


def ticket_details_from_text(text: str, today: date) -> dict:
    ticket_type = _ticket_type(text)
    if not ticket_type:
        return {}

    apply_start = None
    apply_end = None
    window = APP_WINDOW_RE.search(text)
    if window:
        sy, sm, sd, sh, smin, ey, em, ed, eh, emin = window.groups()
        apply_start = _iso_datetime(sy, sm, sd, sh, smin, today)
        start_year = int(apply_start[:4]) if apply_start else None
        apply_end = _iso_datetime(ey, em, ed, eh, emin, today, start_year)
        if apply_start and apply_end and apply_end < apply_start and not ey:
            end_dt = datetime.strptime(apply_end, "%Y-%m-%dT%H:%M").replace(year=start_year + 1)
            apply_end = end_dt.strftime("%Y-%m-%dT%H:%M")
    else:
        end_match = APP_END_RE.search(text)
        if end_match:
            ey, em, ed, eh, emin = end_match.groups()
            apply_end = _iso_datetime(ey, em, ed, eh, emin, today)

    status = "none"
    if apply_start:
        try:
            start_day = date.fromisoformat(apply_start[:10])
            end_day = date.fromisoformat((apply_end or apply_start)[:10])
            if end_day < today:
                status = "none"
            elif start_day > today:
                status = "upcoming"
            else:
                status = "open"
        except ValueError:
            status = "open"
    elif apply_end and re.search(r"ただいまより|受付(?:が)?スタート|受付開始|受付中", text):
        status = "open"

    result = {
        "ticketType": ticket_type,
        "applicationStatus": status,
        "applyStart": apply_start,
        "applyEnd": apply_end,
    }
    if apply_start and apply_end:
        result["applicationDisplayMode"] = "band"
        result["applicationWindowVerified"] = True
        result["deadlineVerified"] = True
    elif apply_end:
        result["applicationDisplayMode"] = "offers"
        result["deadlineVerified"] = True
    return result


def official_ticket_details(session: requests.Session, url: str, today: date) -> dict:
    response = session.get(url, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text("\n", strip=True)
    article_date = ticket_parser.article_date_from_text(text)
    default_year = int(article_date[:4]) if article_date else today.year
    windows = ticket_parser.extract_windows(text, default_year)
    if len(windows) != 1:
        return {}
    apply_start, apply_end = windows[0]
    ticket_type = ticket_parser.extract_ticket_type("", text)
    status = "none"
    try:
        start_day = date.fromisoformat(apply_start[:10])
        end_day = date.fromisoformat(apply_end[:10])
        if end_day >= today:
            status = "upcoming" if start_day > today else "open"
    except ValueError:
        pass
    result = {
        "ticketType": ticket_type,
        "applicationStatus": status,
        "applyStart": apply_start,
        "applyEnd": apply_end,
        "applicationDisplayMode": "band",
        "applicationWindowVerified": True,
        "deadlineVerified": True,
        "applicationWindowSource": url,
        "deadlineSource": url,
    }
    if article_date:
        result["sourcePublishedAt"] = article_date
    return result


def _unique_urls(primary: str | None, *groups: object) -> list[str]:
    values: list[str] = []
    for value in (primary, *groups):
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, (list, tuple, set)):
            candidates = [str(item) for item in value if item]
        else:
            candidates = []
        for candidate in candidates:
            if candidate and candidate not in values:
                values.append(candidate)
    return values


def event_from_post(
    group: str,
    url: str,
    text: str,
    today: date,
    official_urls: list[str] | None = None,
    official_details: dict | None = None,
) -> list[dict]:
    official_urls = official_urls or []
    direct_details = ticket_details_from_text(text, today)
    application = dict(direct_details)
    if official_details:
        application.update({key: value for key, value in official_details.items() if value is not None})

    lines = [base.normalize(value) for value in text.splitlines() if base.normalize(value)]
    category = "solo-live"
    fallback_title = base.extract_title(group, text, lines, category)
    primary_url = official_urls[0] if official_urls else url
    all_urls = _unique_urls(primary_url, official_urls, url)
    events = []
    for day, venue in base.extract_occurrences(lines, today):
        if day < today:
            continue
        title = base.extract_occurrence_title(group, lines, day, today, category, fallback_title)
        event = {
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
            "url": primary_url,
            "urls": all_urls,
            "discoverySourceUrl": url,
            "sourceType": "official-social",
            "sourceChannel": "official-x-syndication",
            "primarySource": "official",
            "sourceCandidates": ["official"],
            "eventScope": "kawaii-lab",
        }
        if application:
            for key, value in application.items():
                if key in TICKET_FIELDS or key == "sourcePublishedAt":
                    event[key] = value
            if event.get("ticketType") != "現在受付なし":
                event["specialDetailsStatus"] = "ticket-details-found"
                if event.get("applyEnd"):
                    event.setdefault("deadlineSource", official_details and primary_url or url)
                if event.get("applyStart") and event.get("applyEnd"):
                    event.setdefault("applicationWindowSource", official_details and primary_url or url)
        events.append(event)
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
            for post_url, text, official_urls in posts:
                details: dict = {}
                for official_url in official_urls:
                    try:
                        candidate = official_ticket_details(session, official_url, today)
                        if candidate:
                            details = candidate
                            break
                    except Exception as exc:
                        failures.append({
                            "group": group,
                            "handle": handle,
                            "stage": "official-detail-enrichment",
                            "url": official_url,
                            "error": f"{type(exc).__name__}: {exc}",
                        })
                events.extend(event_from_post(group, post_url, text, today, official_urls, details))
        except Exception as exc:
            failures.append({
                "group": group,
                "handle": handle,
                "stage": "timeline",
                "error": f"{type(exc).__name__}: {exc}",
            })
    return events, failures


def birthday_key(event: dict) -> tuple[str, str] | None:
    title = str(event.get("eventTitle") or event.get("title") or "")
    if not base.BIRTHDAY_RE.search(title):
        return None
    group = str(event.get("group") or "")
    day = str(event.get("eventDate") or "")[:10]
    if not group or not day:
        return None
    return group, day


def _has_application(event: dict) -> bool:
    ticket_type = str(event.get("ticketType") or "")
    return bool(
        (ticket_type and ticket_type != "現在受付なし")
        or event.get("applyStart")
        or event.get("applyEnd")
    )


def _official_site_row(event: dict) -> bool:
    # Promoter pages (for example HOT STUFF) are trusted fallback evidence, but
    # they are not KAWAII LAB./group official pages. Treating promoter rows as
    # official-site rows caused a rich official ticket update to be enriched
    # onto the promoter row and then immediately removed by fallback cleanup.
    return (
        str(event.get("primarySource") or "").lower() == "official"
        and str(event.get("sourceType") or "").lower() not in {"official-social", "promoter"}
    )


def _merge_source_metadata(target: dict, *rows: dict) -> dict:
    out = dict(target)
    urls = _unique_urls(out.get("url"), out.get("urls"))
    sources = [str(value) for value in (out.get("sourceCandidates") or []) if value]
    for row in rows:
        urls = _unique_urls(urls[0] if urls else None, urls, row.get("url"), row.get("urls"))
        for source in row.get("sourceCandidates") or []:
            source = str(source)
            if source and source not in sources:
                sources.append(source)
        if str(row.get("sourceType") or "").lower() == "promoter" and "promoter" not in sources:
            sources.append("promoter")
    if urls:
        out["urls"] = urls
    if sources:
        out["sourceCandidates"] = sources
    return out


def merge_birthday_events(payload: dict, birthday_events: list[dict]) -> dict:
    if not birthday_events:
        return payload

    events = [dict(event) for event in payload.get("events", []) if isinstance(event, dict)]
    changed = False

    for fresh in birthday_events:
        key = birthday_key(fresh)
        if not key:
            continue
        matching = [event for event in events if birthday_key(event) == key]
        promoter_rows = [event for event in matching if str(event.get("sourceType") or "").lower() == "promoter"]
        social_rows = [event for event in matching if str(event.get("sourceType") or "").lower() == "official-social"]
        official_rows = [event for event in matching if _official_site_row(event)]

        if official_rows:
            if _has_application(fresh):
                schedule_only = next((event for event in official_rows if not _has_application(event)), None)
                if schedule_only is not None:
                    enriched = dict(schedule_only)
                    for field in TICKET_FIELDS:
                        if field in fresh and fresh.get(field) is not None:
                            enriched[field] = fresh.get(field)
                    for field in ("specialDetailsStatus", "sourcePublishedAt", "discoverySourceUrl"):
                        if fresh.get(field) is not None:
                            enriched[field] = fresh.get(field)
                    enriched = _merge_source_metadata(enriched, fresh, *promoter_rows, *social_rows)
                    events = [event for event in events if event is not schedule_only]
                    events.append(enriched)
                    changed = True
            # An official page/ticket row is authoritative. Social/promoter rows are
            # fallback evidence only and must not render as duplicate events.
            before = len(events)
            events = [
                event for event in events
                if not (
                    birthday_key(event) == key
                    and str(event.get("sourceType") or "").lower() in {"promoter", "official-social"}
                )
            ]
            changed = changed or len(events) != before
            continue

        merged_fresh = dict(fresh)
        if social_rows and social_rows[0].get("id"):
            merged_fresh["id"] = social_rows[0]["id"]
        merged_fresh = _merge_source_metadata(merged_fresh, *promoter_rows, *social_rows)
        before = len(events)
        events = [
            event for event in events
            if not (
                birthday_key(event) == key
                and str(event.get("sourceType") or "").lower() in {"promoter", "official-social"}
            )
        ]
        events.append(merged_fresh)
        if len(events) != before or not social_rows or merged_fresh != social_rows[0]:
            changed = True

    events.sort(key=lambda event: (
        str(event.get("eventDate") or "9999-12-31")[:10],
        str(event.get("group") or ""),
        str(event.get("title") or ""),
    ))
    out = dict(payload)
    out["events"] = events
    if changed:
        out["updatedAt"] = datetime.now(base.JST).isoformat(timespec="seconds")
    return out


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
        "withTicketDetails": sum(1 for event in events if _has_application(event)),
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
