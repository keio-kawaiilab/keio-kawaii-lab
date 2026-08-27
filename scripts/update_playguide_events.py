#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote, urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

DATA_PATH = Path("data/live-events.json")
JST = ZoneInfo("Asia/Tokyo")

EPLUS_ARTIST_URLS = {
    "FRUITS ZIPPER": "https://eplus.jp/sf/word/0000152889",
    "CANDY TUNE": "https://eplus.jp/sf/word/0000157138",
    "SWEET STEADY": "https://eplus.jp/sf/word/0000163600",
    "CUTIE STREET": "https://eplus.jp/sf/word/0000166546",
    "MORE STAR": "https://eplus.jp/sf/word/0000173782",
}
GROUPS = tuple(EPLUS_ARTIST_URLS)
WINDOW_RE = re.compile(
    r"(20\d{2})/(\d{1,2})/(\d{1,2})(?:\([^)]*\))?\s*(\d{1,2}):(\d{2})"
    r"\s*[～〜~-]\s*"
    r"(20\d{2})/(\d{1,2})/(\d{1,2})(?:\([^)]*\))?\s*(\d{1,2}):(\d{2})"
)
DAY_RE = re.compile(r"(20\d{2})/\s*(\d{1,2})/(\d{1,2})")
EPLUS_ROOT_RE = re.compile(r"(https?://eplus\.jp)?(/sf/detail/\d+)")


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def stable_id(*parts: object) -> str:
    raw = "\x1f".join(str(value or "") for value in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def iso_day(value: str) -> str | None:
    match = DAY_RE.search(norm(value))
    if not match:
        return None
    year, month, day = map(int, match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def iso_window(value: str) -> tuple[str | None, str | None]:
    match = WINDOW_RE.search(norm(value))
    if not match:
        return None, None
    values = [int(x) for x in match.groups()]
    try:
        start = datetime(*values[:5]).strftime("%Y-%m-%dT%H:%M")
        end = datetime(*values[5:]).strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        return None, None
    return start, end


def clean_venue(value: object) -> str:
    text = norm(value)
    return re.sub(r"[（(](?:北海道|東京都|京都府|大阪府|.{2,3}県)[）)]$", "", text).strip()


def time_from_text(value: object, label: str) -> str | None:
    match = re.search(rf"{label}\s*[:：]\s*(\d{{1,2}}):(\d{{2}})", norm(value))
    return f"{int(match.group(1)):02d}:{match.group(2)}" if match else None


def is_current_window(end: str | None, today: date) -> bool:
    if not end:
        return False
    try:
        return date.fromisoformat(end[:10]) >= today
    except ValueError:
        return False


def event_record(
    *, provider: str, group: str, title: str, ticket_type: str,
    apply_start: str, apply_end: str, event_date: str, venue: str,
    url: str, open_time: str | None = None, start_time: str | None = None,
) -> dict:
    return {
        "id": stable_id(provider, group, title, ticket_type, apply_start, apply_end, event_date, venue, url),
        "group": group,
        "title": title or f"{group} 公演",
        "ticketType": ticket_type or "一般受付",
        "ticketProvider": provider,
        "applyStart": apply_start,
        "applyEnd": apply_end,
        "resultDate": None,
        "paymentEnd": None,
        "eventDate": event_date,
        "venue": venue or None,
        "openTime": open_time,
        "startTime": start_time,
        "url": url,
        "urls": [url],
        "sourceType": provider,
        "primarySource": provider,
        "sourceCandidates": [provider],
        "applicationStatus": "open",
        "applicationWindowVerified": True,
        "deadlineVerified": True,
        "applicationDisplayMode": "band",
        "applicationWindowSource": url,
        "deadlineSource": url,
    }


def jsonld_performances(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    result = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(script.string or script.get_text() or "null")
        except (TypeError, json.JSONDecodeError):
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if not isinstance(item, dict) or item.get("@type") != "Event" or not item.get("url"):
                continue
            start = str(item.get("startDate") or "")
            day = start[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", start) else None
            location = item.get("location") if isinstance(item.get("location"), dict) else {}
            result.append({
                "url": str(item["url"]),
                "day": day,
                "venue": clean_venue(location.get("name")),
                "startTime": start[11:16] if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}.*", start) else None,
            })
    return result


def eplus_performance_links(session: requests.Session, artist_html: str) -> list[dict]:
    soup = BeautifulSoup(artist_html, "html.parser")
    found: dict[str, dict] = {}
    roots = set()
    for anchor in soup.select("a.ticket-item--kouen[href]"):
        detail_url = urljoin("https://eplus.jp", str(anchor.get("href") or ""))
        day = iso_day(anchor.get_text(" ", strip=True))
        venue_node = anchor.select_one(".ticket-item__venue")
        time_node = anchor.select_one(".ticket-item__text")
        time_text = time_node.get_text(" ", strip=True) if time_node else ""
        found[detail_url] = {
            "url": detail_url,
            "day": day,
            "venue": clean_venue(venue_node.get_text(" ", strip=True) if venue_node else ""),
            "openTime": time_from_text(time_text, "開場"),
            "startTime": time_from_text(time_text, "開演"),
        }
        root_match = EPLUS_ROOT_RE.search(detail_url)
        if root_match:
            roots.add("https://eplus.jp" + root_match.group(2))
    for root_url in sorted(roots):
        response = session.get(root_url, timeout=20)
        response.raise_for_status()
        for row in jsonld_performances(response.text):
            found.setdefault(row["url"], row)
    return list(found.values())


def collect_eplus(session: requests.Session, group: str, today: date) -> list[dict]:
    response = session.get(EPLUS_ARTIST_URLS[group], timeout=25)
    response.raise_for_status()
    results: list[dict] = []
    for performance in eplus_performance_links(session, response.text):
        day = performance.get("day")
        if not day or date.fromisoformat(day) < today:
            continue
        detail_url = str(performance["url"])
        venue = str(performance.get("venue") or "")
        detail = session.get(detail_url, timeout=20)
        detail.raise_for_status()
        detail_soup = BeautifulSoup(detail.text, "html.parser")
        meta = detail_soup.select_one('meta[property="og:title"]')
        page_title = norm(meta.get("content") if meta else group)
        page_title = re.sub(r"のチケット情報.*$", "", page_title).strip() or group
        for block in detail_soup.select(".block-ticket"):
            text = norm(block.get_text(" ", strip=True))
            apply_start, apply_end = iso_window(text)
            if not (apply_start and apply_end and is_current_window(apply_end, today)):
                continue
            status = norm((block.select_one(".ticket-status") or block).get_text(" ", strip=True))
            if "受付終了" in status or "予定枚数終了" in status:
                continue
            title_node = block.select_one(".block-ticket__title")
            ticket_type = norm(title_node.get_text(" ", strip=True) if title_node else "イープラス受付")
            results.append(event_record(
                provider="eplus", group=group, title=page_title, ticket_type=ticket_type,
                apply_start=apply_start, apply_end=apply_end, event_date=day, venue=venue,
                url=detail_url, open_time=performance.get("openTime"), start_time=performance.get("startTime"),
            ))
    return results


def previous_schedule(item) -> tuple[str | None, str]:
    node = item.find_previous("dl", class_="ResultBox__informations")
    if not node:
        return None, ""
    parent = item.find_parent(class_="ResultBox")
    if parent is None or node.find_parent(class_="ResultBox") is not parent:
        return None, ""
    text = norm(node.get_text(" ", strip=True))
    day_match = re.search(r"公演日[:：]?\s*(20\d{2}/\d{1,2}/\d{1,2})", text)
    venue_match = re.search(r"会場[:：]?\s*(.+)$", text)
    return (iso_day(day_match.group(1)) if day_match else None, clean_venue(venue_match.group(1)) if venue_match else "")


def collect_lawson(session: requests.Session, group: str, today: date) -> list[dict]:
    search_url = f"https://l-tike.com/search/?keyword={quote(group)}"
    response = session.get(search_url, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    results: list[dict] = []
    for box in soup.select(".ResultBox"):
        title_node = box.select_one(".ResultBox__title")
        title = norm(title_node.get_text(" ", strip=True) if title_node else group)
        if group.replace(" ", "") not in title.replace(" ", "") and group not in title:
            continue
        for item in box.select(".prfItem"):
            event_date, venue = previous_schedule(item)
            if not event_date or date.fromisoformat(event_date) < today:
                continue
            text = norm(item.get_text(" ", strip=True))
            apply_start, apply_end = iso_window(text)
            if not (apply_start and apply_end and is_current_window(apply_end, today)):
                continue
            if "受付終了" in text or "予定枚数終了" in text:
                continue
            kind = norm((item.select_one("#reception_typename") or item).get_text(" ", strip=True))
            sale = item.select_one("#sale_name")
            sale_name = norm(sale.get_text(" ", strip=True) if sale else "")
            ticket_type = " ".join(x for x in (kind, sale_name) if x) or "ローチケ受付"
            button = item.select_one("[data-lcode]")
            lcode = norm(button.get("data-lcode") if button else "")
            if not lcode:
                continue
            detail_url = f"https://l-tike.com/order/?gLcode={lcode}"
            results.append(event_record(
                provider="lawson", group=group, title=title, ticket_type=ticket_type,
                apply_start=apply_start, apply_end=apply_end, event_date=event_date, venue=venue, url=detail_url,
            ))
    return results


def dedupe(events: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[tuple] = set()
    for event in events:
        key = (
            event.get("ticketProvider"), event.get("group"), event.get("eventDate"), event.get("venue"),
            event.get("ticketType"), event.get("applyStart"), event.get("applyEnd"), event.get("url"),
        )
        if key not in seen:
            seen.add(key)
            result.append(event)
    return result


def identity(event: dict) -> tuple[str, str, str, str]:
    return (
        str(event.get("ticketProvider") or event.get("sourceType") or "").lower(),
        str(event.get("group") or ""), str(event.get("eventDate") or "")[:10], str(event.get("url") or ""),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh Lawson Ticket and eplus public application windows")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    existing = [dict(item) for item in payload.get("events", []) if isinstance(item, dict)]
    now = datetime.now(JST)
    today = now.date()
    observed_at = now.isoformat(timespec="seconds")
    session = requests.Session()
    session.headers.update({"User-Agent": "KeioKawaiiLabCalendarBot/1.6 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"})

    fresh: list[dict] = []
    refreshed: set[tuple[str, str]] = set()
    failures: list[str] = []
    fresh_counts: Counter[str] = Counter()
    for group in GROUPS:
        for provider, collector in (("eplus", collect_eplus), ("lawson", collect_lawson)):
            try:
                rows = collector(session, group, today)
                for row in rows:
                    row["sourceObservedAt"] = observed_at
                    row["sourceStale"] = False
                    row.pop("sourceStaleSince", None)
                fresh.extend(rows)
                fresh_counts[f"{provider}:{group}"] = len(rows)
                refreshed.add((provider, group))
            except Exception as exc:
                failures.append(f"{provider}/{group}: {type(exc).__name__}: {exc}")

    fresh = dedupe(fresh)
    if args.check:
        if not refreshed:
            raise SystemExit("All playguide sources failed: " + "; ".join(failures))
        if failures:
            print("Playguide source warnings: " + "; ".join(failures), file=sys.stderr)
        print(json.dumps({
            "status": "ok", "activeWindows": len(fresh), "freshCounts": dict(sorted(fresh_counts.items())),
            "refreshedSources": [f"{p}:{g}" for p, g in sorted(refreshed)], "failures": failures,
        }, ensure_ascii=False, indent=2))
        return 0

    fresh_identity = {identity(event) for event in fresh}
    retained: list[dict] = []
    still_active_missing: list[dict] = []
    expired_pruned = 0
    for event in existing:
        provider = str(event.get("ticketProvider") or event.get("sourceType") or "").lower()
        group = str(event.get("group") or "")
        if provider not in {"eplus", "lawson"}:
            retained.append(event)
            continue
        if (provider, group) not in refreshed:
            # Network/source failure: fail safe and keep the previous observation unchanged.
            retained.append(event)
            continue
        if identity(event) in fresh_identity:
            # Current observation replaces every older window on the same provider/detail/performance.
            continue
        if is_current_window(str(event.get("applyEnd") or ""), today):
            # The page was reachable but a still-active known reception disappeared. Keep it only as
            # a safety fallback and flag it so the integrity audit can block flow publication.
            event["sourceStale"] = True
            event.setdefault("sourceStaleSince", observed_at)
            retained.append(event)
            still_active_missing.append({
                "provider": provider, "group": group, "eventDate": event.get("eventDate"),
                "ticketType": event.get("ticketType"), "applyEnd": event.get("applyEnd"), "url": event.get("url"),
            })
        else:
            # A successfully refreshed source no longer shows an ended reception: remove it from the
            # current UI dataset. The append-only ticket-history.json keeps the permanent record.
            expired_pruned += 1

    payload["events"] = retained + fresh
    payload["updatedAt"] = observed_at
    payload["playguideFailures"] = failures
    payload["playguideDiagnostics"] = {
        "collectedAt": observed_at,
        "freshCounts": dict(sorted(fresh_counts.items())),
        "refreshedSources": [f"{p}:{g}" for p, g in sorted(refreshed)],
        "failureCount": len(failures),
        "failures": failures,
        "stillActiveMissingCount": len(still_active_missing),
        "stillActiveMissing": still_active_missing,
        "expiredRowsPruned": expired_pruned,
    }
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["playguideDiagnostics"], ensure_ascii=False, indent=2))
    print(f"Refreshed playguides: {len(fresh)} active windows; pruned {expired_pruned} ended rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
