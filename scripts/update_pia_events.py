#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

DATA_PATH = Path("data/live-events.json")
PIA_BASE = "https://t.pia.jp"
ARTIST_URLS = {
    "FRUITS ZIPPER": "https://t.pia.jp/pia/artist/artists.do?artistsCd=M4140001",
    "CANDY TUNE": "https://t.pia.jp/pia/artist/artists.do?artistsCd=N1260021",
    "SWEET STEADY": "https://t.pia.jp/pia/artist/artists.do?artistsCd=O1150071",
    "CUTIE STREET": "https://t.pia.jp/pia/artist/artists.do?artistsCd=O7260002",
    "MORE STAR": "https://t.pia.jp/pia/artist/artists.do?artistsCd=PC180040",
}
SALE_HINTS = (
    "一般発売", "一般販売", "プレリザーブ", "プレイガイド", "プリセール",
    "先行", "発売前", "販売期間中", "抽選受付中", "ぴあNICOS",
)
ACTIVE_HINTS = ("抽選受付中", "販売期間中", "発売前", "受付中")
ENDED_HINTS = ("抽選受付終了", "販売終了", "予定枚数終了")
DATE_RE = re.compile(
    r"(20\d{2})/(\d{1,2})/(\d{1,2})"
    r"(?:\([^)]*\))?"
    r"(?:\s*(\d{1,2}):(\d{2}))?"
)


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def to_iso(match: re.Match) -> str:
    year, month, day, hour, minute = match.groups()
    base = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return base if hour is None else f"{base}T{int(hour):02d}:{int(minute or 0):02d}"


def stable_id(*parts: object) -> str:
    raw = "\x1f".join(str(x or "") for x in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def ticket_type(text: str) -> str:
    text = norm(text)
    patterns = (
        (r"2次プレリザーブ", "2次プレリザーブ"),
        (r"プレリザーブ2次", "2次プレリザーブ"),
        (r"いち早プレリザーブ", "いち早プレリザーブ"),
        (r"プレリザーブ", "プレリザーブ"),
        (r"プレイガイド最速先行", "プレイガイド最速先行"),
        (r"最速プレイガイド先行", "プレイガイド最速先行"),
        (r"ぴあNICOSカード限定", "ぴあNICOSカード限定先行"),
        (r"プレミアム", "ぴあプレミアム先行"),
        (r"一般発売|一般販売", "一般発売"),
        (r"先行", "ぴあ先行"),
    )
    for pattern, label in patterns:
        if re.search(pattern, text, re.I):
            return label
    return "チケットぴあ受付"


def extract_live_title(page_text: str, fallback: str) -> str:
    head = page_text[:1800]
    quoted = re.findall(r"「([^」]{3,120})」", head)
    for value in quoted:
        if not re.search(r"入場券|特典|チケット", value):
            return norm(value)
    return norm(fallback)


def context_for_detail(anchor) -> str:
    node = anchor
    best = norm(anchor.get_text(" ", strip=True))
    for _ in range(8):
        node = getattr(node, "parent", None)
        if node is None:
            break
        text = norm(node.get_text(" ", strip=True))
        if any(hint in text for hint in SALE_HINTS) and DATE_RE.search(text):
            best = text
            if len(text) <= 900:
                return text
    return best


def event_window(context: str) -> tuple[str | None, str | None]:
    status_positions = [context.find(h) for h in (*ACTIVE_HINTS, *ENDED_HINTS) if context.find(h) >= 0]
    before_status = context[:min(status_positions)] if status_positions else context
    matches = list(DATE_RE.finditer(before_status))
    if not matches:
        return None, None
    start = to_iso(matches[0])[:10]
    end = None
    if len(matches) >= 2:
        between = before_status[matches[0].end():matches[1].start()]
        if re.search(r"[～〜~-]", between):
            end = to_iso(matches[1])[:10]
    return start, end


def sale_window(context: str) -> tuple[str | None, str | None]:
    if "発売前" in context:
        pos = context.find("発売前")
        match = DATE_RE.search(context[pos:pos + 180])
        return (to_iso(match) if match else None), None
    for token in ("抽選受付中", "販売期間中", "受付中"):
        pos = context.find(token)
        if pos < 0:
            continue
        tail = context[pos:pos + 220]
        matches = list(DATE_RE.finditer(tail))
        if matches:
            return None, to_iso(matches[-1])
    return None, None


def official_schedule(existing: list[dict], group: str, title: str, start: str, end: str | None) -> list[dict]:
    from resolve_source_priority import canonical_title

    probe = {"group": group, "title": title, "eventDate": start}
    wanted = canonical_title(probe)
    if not wanted:
        return []
    finish = end or start
    candidates: list[dict] = []
    for event in existing:
        if event.get("group") != group or event.get("sourceType") == "pia":
            continue
        candidate_title = canonical_title(event)
        if not candidate_title or not (candidate_title == wanted or candidate_title in wanted or wanted in candidate_title):
            continue
        schedule = event.get("schedule")
        if isinstance(schedule, list):
            for item in schedule:
                if not isinstance(item, dict):
                    continue
                day = str(item.get("date") or "")[:10]
                if start <= day <= finish:
                    candidates.append({"date": day, "venue": item.get("venue")})
        elif event.get("eventDate"):
            day = str(event.get("eventDate"))[:10]
            if start <= day <= finish:
                candidates.append({"date": day, "venue": event.get("venue")})
    seen = set()
    result = []
    for item in sorted(candidates, key=lambda x: x["date"]):
        if item["date"] in seen:
            continue
        seen.add(item["date"])
        result.append(item)
    return result


def parse_event_page(session: requests.Session, group: str, event_url: str, fallback_title: str, existing: list[dict], today) -> list[dict]:
    response = session.get(event_url, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    page_text = norm(soup.get_text(" ", strip=True))
    live_title = extract_live_title(page_text, fallback_title)
    out: list[dict] = []
    seen = set()

    detail_anchors = [a for a in soup.find_all("a", href=True) if "詳細" in norm(a.get_text(" ", strip=True))]
    for anchor in detail_anchors:
        context = context_for_detail(anchor)
        if not any(hint in context for hint in SALE_HINTS):
            continue
        if any(hint in context for hint in ENDED_HINTS) and not any(hint in context for hint in ACTIVE_HINTS):
            continue
        start, end = event_window(context)
        if not start:
            continue
        try:
            if datetime.strptime(end or start, "%Y-%m-%d").date() < today:
                continue
        except ValueError:
            continue
        apply_start, apply_end = sale_window(context)
        kind = ticket_type(context)
        href = canonical_url(urljoin(event_url, str(anchor.get("href") or "")))
        schedule = official_schedule(existing, group, live_title, start, end)
        if not schedule:
            schedule = [{"date": start, "venue": None}]
            if end and end != start:
                # 連続日程と断定せず、期間終端だけ保持する。公式日程がある場合は上で正確に補完される。
                schedule.append({"date": end, "venue": None})
        event_dates = [x["date"] for x in schedule]
        venues = [x.get("venue") for x in schedule if x.get("venue")]
        venue = venues[0] if len(set(venues)) == 1 and venues else (f"複数会場（全{len(event_dates)}公演）" if len(event_dates) > 1 else None)
        key = (kind, tuple(event_dates), apply_start, apply_end, href)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "id": stable_id("pia", group, live_title, kind, *event_dates, apply_start, apply_end, href),
            "group": group,
            "title": live_title,
            "ticketType": kind,
            "applyStart": apply_start,
            "applyEnd": apply_end,
            "resultDate": None,
            "paymentEnd": None,
            "eventDate": event_dates[0],
            "eventEndDate": event_dates[-1] if len(event_dates) > 1 else None,
            "eventDates": event_dates if len(event_dates) > 1 else None,
            "schedule": schedule if len(schedule) > 1 else None,
            "eventCount": len(event_dates) if len(event_dates) > 1 else None,
            "venue": venue,
            "url": href or event_url,
            "urls": [href or event_url, event_url] if href and href != event_url else [event_url],
            "sourceType": "pia",
            "sourcePublishedAt": None,
        })
    return out


def discover_event_pages(session: requests.Session, artist_url: str) -> list[tuple[str, str]]:
    response = session.get(artist_url, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    found: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if "/pia/event/event.do" not in href:
            continue
        url = canonical_url(urljoin(artist_url, href))
        heading = anchor.find_previous(["h2", "h3", "h4"])
        fallback = norm(heading.get_text(" ", strip=True) if heading else anchor.get_text(" ", strip=True))
        found[url] = fallback
    return list(found.items())


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge active public Ticket Pia sales into the calendar.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    existing_payload = json.loads(DATA_PATH.read_text(encoding="utf-8")) if DATA_PATH.exists() else {"events": []}
    existing = [x for x in existing_payload.get("events", []) if isinstance(x, dict)]
    today = datetime.now().date()
    session = requests.Session()
    session.headers.update({"User-Agent": "KeioKawaiiLabCalendarBot/1.7 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"})

    parsed: list[dict] = []
    succeeded: set[str] = set()
    failures: list[str] = []
    discovered = 0
    for group, artist_url in ARTIST_URLS.items():
        try:
            pages = discover_event_pages(session, artist_url)
            succeeded.add(group)
            discovered += len(pages)
            for event_url, fallback in pages[:30]:
                try:
                    parsed.extend(parse_event_page(session, group, event_url, fallback or group, existing, today))
                except Exception as exc:
                    failures.append(f"{group} {event_url}: {exc}")
        except Exception as exc:
            failures.append(f"{group} artist page: {exc}")

    print(json.dumps({
        "groupsRead": sorted(succeeded),
        "eventPagesDiscovered": discovered,
        "activePiaSales": len(parsed),
        "failures": failures,
    }, ensure_ascii=False, indent=2))

    if args.check or not DATA_PATH.exists():
        return 0
    if not succeeded:
        print("Ticket Pia could not be read; existing Pia data left untouched.")
        return 0

    kept = [
        event for event in existing
        if event.get("sourceType") != "pia" or event.get("group") not in succeeded
    ]
    ids = {str(event.get("id") or "") for event in kept}
    for event in parsed:
        if event["id"] not in ids:
            kept.append(event)
            ids.add(event["id"])
    existing_payload["events"] = kept
    DATA_PATH.write_text(json.dumps(existing_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Merged {len(parsed)} active Ticket Pia sale(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
