#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))
DATA_PATH = Path("data/live-events.json")
LIST_URLS = (
    "https://api.sukisuki-shop.com/goods",
    "https://sukisuki-shop.com/goods",
    "https://sukisuki-shop.com/",
)
GROUPS = (
    "FRUITS ZIPPER",
    "CANDY TUNE",
    "SWEET STEADY",
    "CUTIE STREET",
    "MORE STAR",
)
# SUKISUKI changes the wording used for the same family of online events.
# Do not require only the historical "オンライン特典会" label at discovery time.
ONLINE_HINTS = (
    "オンライン特典会",
    "オンラインサイン会",
    "オンラインリリイベ",
    "オンラインリリースイベント",
    "オン特",
)
YEARLESS_MAX_DAYS = 60
MAX_DISCOVERED_GOODS = 180
YEAR_HINT_LABELS = (
    "抽選申込期間", "申込期間", "販売期間",
    "当落発表日", "当落発表", "当選発表",
    "入金期限", "支払期限", "お支払い期限",
)
DATE_RE = re.compile(
    r"(?:(20\d{2})年\s*)?(\d{1,2})月\s*(\d{1,2})日"
    r"(?:\s*[（(][^）)]*[）)])?"
    r"(?:\s*(\d{1,2})[:：](\d{2}))?"
)
GOODS_ID_RE = re.compile(r"/goods/(\d+)")


def normalize_space(value: str) -> str:
    return re.sub(r"[\s\u3000]+", " ", str(value or "")).strip()


def canonical_goods_url(url: str) -> str:
    parts = urlsplit(url)
    netloc = parts.netloc
    if netloc == "api.sukisuki-shop.com" and GOODS_ID_RE.search(parts.path):
        netloc = "sukisuki-shop.com"
    return urlunsplit((parts.scheme or "https", netloc, parts.path, "", ""))


def goods_rank(url: str) -> int:
    match = GOODS_ID_RE.search(urlsplit(url).path)
    return int(match.group(1)) if match else 0


def event_urls(event: dict) -> list[str]:
    values: list[str] = []
    if event.get("url"):
        values.append(str(event["url"]))
    for url in event.get("urls") or []:
        if url and str(url) not in values:
            values.append(str(url))
    return values


def is_sukisuki_event(event: dict) -> bool:
    source = str(event.get("sourceType") or "").lower()
    primary = str(event.get("primarySource") or "").lower()
    return source == "sukisuki" or primary == "sukisuki" or any(
        "sukisuki-shop.com" in url.lower() for url in event_urls(event)
    )


def to_iso(match: re.Match, default_year: int | None = None) -> str | None:
    year, month, day, hour, minute = match.groups()
    year = int(year) if year else default_year
    if not year:
        return None
    try:
        dt = datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0))
    except ValueError:
        return None
    base = dt.strftime("%Y-%m-%d")
    return base if hour is None else dt.strftime("%Y-%m-%dT%H:%M")


def resolve_yearless_date(match: re.Match, today) -> str | None:
    if match.group(1):
        return to_iso(match)

    month = int(match.group(2))
    day = int(match.group(3))
    hour = int(match.group(4) or 0)
    minute = int(match.group(5) or 0)
    candidates = []
    for year in (today.year, today.year + 1):
        try:
            candidate = datetime(year, month, day, hour, minute)
        except ValueError:
            continue
        delta = (candidate.date() - today).days
        if 0 <= delta <= YEARLESS_MAX_DAYS:
            candidates.append((delta, candidate))
    if not candidates:
        return None
    candidate = min(candidates, key=lambda x: x[0])[1]
    return candidate.strftime("%Y-%m-%d") if match.group(4) is None else candidate.strftime("%Y-%m-%dT%H:%M")


def explicit_year_hint(text: str) -> int | None:
    for label in YEAR_HINT_LABELS:
        pos = text.find(label)
        if pos < 0:
            continue
        for match in DATE_RE.finditer(text[pos:pos + 420]):
            if match.group(1):
                return int(match.group(1))
    return None


def resolve_event_date(match: re.Match, today, year_hint: int | None = None) -> str | None:
    if match.group(1):
        return to_iso(match)
    if year_hint is not None:
        month = int(match.group(2))
        inferred_year = year_hint
        if year_hint == today.year and today.month >= 11 and month <= 2:
            inferred_year += 1
        return to_iso(match, inferred_year)
    return resolve_yearless_date(match, today)


def first_date_after(text: str, labels: tuple[str, ...], default_year: int | None = None) -> str | None:
    for label in labels:
        pos = text.find(label)
        if pos < 0:
            continue
        match = DATE_RE.search(text[pos:pos + 260])
        if match:
            return to_iso(match, default_year)
    return None


def date_window_after(text: str, labels: tuple[str, ...], default_year: int | None = None) -> tuple[str | None, str | None]:
    for label in labels:
        pos = text.find(label)
        if pos < 0:
            continue
        matches = list(DATE_RE.finditer(text[pos:pos + 420]))
        if not matches:
            continue
        first = to_iso(matches[0], default_year)
        year = int(first[:4]) if first else default_year
        second = to_iso(matches[1], year) if len(matches) >= 2 else None
        if second:
            return first, second
        return None, first
    return None, None


def clean_event_title(title: str) -> str:
    text = normalize_space(title)
    text = re.sub(r"^[〖【][^〗】]+[〗】]\s*", "", text)
    text = re.sub(r"^20\d{2}年\d{1,2}月\d{1,2}日\s*", "", text)
    return text.strip() or "オンライン特典会"


def group_from(text: str) -> str | None:
    upper = text.upper()
    for group in GROUPS:
        if group.upper() in upper:
            return group
    return None


def sale_type(title: str, text: str) -> str:
    corpus = f"{title}\n{text[:2500]}"
    if "オンラインリリースイベント" in corpus or "オンラインリリイベ" in corpus:
        kind = "オンラインリリースイベント"
    elif "オンラインサイン会" in corpus:
        kind = "オンラインサイン会"
    else:
        kind = "オンライン特典会"
    if "抽選販売" in corpus or "抽選申込" in corpus:
        return f"{kind}・抽選販売"
    if "先着販売" in corpus or "先着" in corpus:
        return f"{kind}・先着販売"
    return kind


def stable_id(*parts: object) -> str:
    raw = "\x1f".join(str(x or "") for x in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def discover(session: requests.Session) -> tuple[list[str], list[str]]:
    urls: set[str] = set()
    failures: list[str] = []
    for list_url in LIST_URLS:
        try:
            response = session.get(list_url, timeout=25)
            response.raise_for_status()
        except Exception as exc:
            failures.append(f"{list_url}: {exc}")
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href") or "")
            if "/goods/" not in href:
                continue
            context = normalize_space(anchor.get_text(" ", strip=True))
            parent = anchor.parent
            if parent is not None:
                context += " " + normalize_space(parent.get_text(" ", strip=True))
            # Group attribution is intentionally NOT required here. SUKISUKI
            # cards sometimes expose only a member name or a shortened title.
            # Read the detail page first, then identify the KAWAII LAB. group
            # from the full official product text in parse_goods().
            if not any(hint in context for hint in ONLINE_HINTS):
                continue
            urls.add(canonical_goods_url(urljoin(list_url, href)))

    ordered = sorted(urls, key=lambda url: (goods_rank(url), url), reverse=True)
    return ordered[:MAX_DISCOVERED_GOODS], failures


def parse_goods(session: requests.Session, url: str, today) -> dict | None:
    response = session.get(url, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text("\n", strip=True)
    h1 = soup.find("h1")
    title = normalize_space(h1.get_text(" ", strip=True) if h1 else soup.title.get_text(" ", strip=True) if soup.title else "")
    corpus = f"{title}\n{text}"
    group = group_from(corpus)
    if not group or not any(hint in corpus for hint in ONLINE_HINTS):
        return None

    year_hint = explicit_year_hint(text)
    stream_time = None
    for label in ("配信予定日", "開催日時"):
        pos = text.find(label)
        if pos < 0:
            continue
        stream_match = DATE_RE.search(text[pos:pos + 260])
        stream_value = resolve_event_date(stream_match, today, year_hint) if stream_match else None
        if stream_value and "T" in stream_value:
            stream_time = stream_value.split("T", 1)[1]
            break
    title_match = DATE_RE.search(title)
    event_date = resolve_event_date(title_match, today, year_hint) if title_match else None
    if not event_date:
        for label in ("配信予定日", "開催日時", "開催日"):
            pos = text.find(label)
            if pos < 0:
                continue
            match = DATE_RE.search(text[pos:pos + 260])
            if not match:
                continue
            event_date = resolve_event_date(match, today, year_hint)
            if event_date:
                break
    event_date = event_date[:10] if event_date else None
    if not event_date:
        return None

    try:
        event_day = datetime.strptime(event_date, "%Y-%m-%d").date()
    except ValueError:
        return None
    if event_day < today:
        return None

    year = int(event_date[:4])
    apply_start, apply_end = date_window_after(text, ("抽選申込期間", "申込期間", "販売期間"), year)
    result_date = first_date_after(text, ("当落発表日", "当落発表", "当選発表"), year)
    payment_end = first_date_after(text, ("入金期限", "支払期限", "お支払い期限"), year)
    ticket_type = sale_type(title, text)
    cleaned_title = clean_event_title(title)

    return {
        "id": stable_id("sukisuki", group, url, event_date, apply_start, apply_end, ticket_type),
        "group": group,
        "title": cleaned_title,
        "ticketType": ticket_type,
        "applyStart": apply_start,
        "applyEnd": apply_end,
        "resultDate": result_date,
        "paymentEnd": payment_end,
        "eventDate": event_date,
        "startTime": stream_time,
        "venue": "オンライン（SUKISUKI）",
        "url": url,
        "urls": [url],
        "sourceType": "sukisuki",
        "eventCategory": "online-benefit",
        "sourcePublishedAt": None,
    }


def main() -> int:
    cli = argparse.ArgumentParser(description="Merge public SUKISUKI online benefit events into the calendar.")
    cli.add_argument("--check", action="store_true")
    args = cli.parse_args()

    session = requests.Session()
    session.headers.update({
        "User-Agent": "KeioKawaiiLabCalendarBot/2.0 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"
    })
    urls, discovery_failures = discover(session)
    today = datetime.now(JST).date()
    parsed: list[dict] = []
    failures = list(discovery_failures)
    for url in urls:
        try:
            event = parse_goods(session, url, today)
            if event:
                parsed.append(event)
        except Exception as exc:
            failures.append(f"{url}: {exc}")

    print(json.dumps({
        "discovered": len(urls),
        "futureOnlineEvents": len(parsed),
        "failures": failures,
    }, ensure_ascii=False, indent=2))

    if not urls and discovery_failures:
        print("SUKISUKI listings could not be read; existing calendar left untouched.")
        return 0
    if args.check:
        return 0
    if not DATA_PATH.exists():
        print("Calendar data file does not exist; skipping SUKISUKI merge.")
        return 0

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    # Replace every prior SUKISUKI-derived row, even if a sanitizer changed
    # sourceType to derived. This prevents stale schedule-only duplicates from
    # surviving next to the current lottery/first-come sale rows.
    existing = [
        event for event in payload.get("events", [])
        if isinstance(event, dict) and not is_sukisuki_event(event)
    ]
    seen = {str(event.get("id") or "") for event in existing}
    for event in parsed:
        if event["id"] not in seen:
            existing.append(event)
            seen.add(event["id"])
    existing.sort(key=lambda event: (
        str(event.get("eventDate") or "9999"),
        str(event.get("applyEnd") or "9999"),
        str(event.get("group") or ""),
    ))
    payload["events"] = existing
    payload["updatedAt"] = datetime.now(JST).isoformat(timespec="seconds")
    payload["source"] = "KAWAII LAB.各グループ公式公開情報 + チケットぴあ公開情報 + SUKISUKI公開オンライン特典会情報"
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Merged {len(parsed)} future SUKISUKI online events.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
