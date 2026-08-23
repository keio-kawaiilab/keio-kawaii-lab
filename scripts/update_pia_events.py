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

# Artist pages occasionally omit or defer individual bundle links. Keep high-confidence
# public event bundles as seeds, then merge them with the normal discovery result.
SEEDED_EVENT_PAGES = {
    "CANDY TUNE": [
        ("https://t.pia.jp/pia/event/event.do?eventBundleCd=b2669827", "CANDY TUNE JAPAN TOUR 2026 - AUTUMN -"),
    ],
    "FRUITS ZIPPER": [
        ("https://t.pia.jp/pia/event/event.do?eventBundleCd=b2669209", "FRUITS ZIPPER"),
    ],
}

SALE_HINTS = (
    "一般発売", "一般販売", "プレリザーブ", "プレイガイド", "プリセール",
    "先行", "発売前", "販売期間中", "抽選受付中", "ぴあNICOS",
    "まもなく抽選受付", "まもなく受付", "まもなく発売", "本日発売初日",
)
ACTIVE_HINTS = ("抽選受付中", "販売期間中", "受付中", "本日発売初日")
UPCOMING_HINTS = ("発売前", "まもなく抽選受付", "まもなく受付", "まもなく発売")
ENDED_HINTS = (
    "抽選受付終了", "販売終了", "予定枚数終了",
    "抽選結果発表前", "抽選結果発表中", "抽選結果発表済",
)
STATUS_HINTS = (*ACTIVE_HINTS, *UPCOMING_HINTS, *ENDED_HINTS)

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
    fallback = norm(fallback)
    head = page_text[:3600]
    quoted = re.findall(r"「([^」]{3,140})」", head)
    bad_ui = re.compile(r"行きたい|アラート|お気に入り|通知|入場券|特典|チケット|メール")

    if any(word.lower() in fallback.lower() for word in ("live", "tour", "session", "fest")) or any(
        word in fallback for word in ("フェス", "生誕", "祭")
    ):
        preferred_fallback = fallback
    else:
        preferred_fallback = ""

    for value in quoted:
        value = norm(value)
        if bad_ui.search(value):
            continue
        if any(word.lower() in value.lower() for word in ("live", "tour", "session", "fest")) or any(
            word in value for word in ("フェス", "祭", "生誕", "公演")
        ):
            return value
    if preferred_fallback:
        return preferred_fallback
    for value in quoted:
        value = norm(value)
        if not bad_ui.search(value):
            return value
    return fallback


def context_for_detail(anchor) -> str:
    own = norm(anchor.get_text(" ", strip=True))
    if any(hint in own for hint in SALE_HINTS) and DATE_RE.search(own):
        return own

    node = anchor
    best = own
    for _ in range(8):
        node = getattr(node, "parent", None)
        if node is None:
            break
        text = norm(node.get_text(" ", strip=True))
        if any(hint in text for hint in SALE_HINTS) and DATE_RE.search(text):
            best = text
            if len(text) <= 1200:
                return text
    return best


def availability_status(context: str) -> str | None:
    if any(hint in context for hint in ACTIVE_HINTS):
        return "open"
    if any(hint in context for hint in UPCOMING_HINTS):
        return "upcoming"
    if any(hint in context for hint in ENDED_HINTS):
        return None
    return None


def event_window(context: str) -> tuple[str | None, str | None]:
    status_positions = [context.find(h) for h in STATUS_HINTS if context.find(h) >= 0]
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


def _range_from_tail(tail: str) -> tuple[str | None, str | None]:
    matches = list(DATE_RE.finditer(tail))
    if not matches:
        return None, None
    first = to_iso(matches[0])
    if len(matches) >= 2:
        between = tail[matches[0].end():matches[1].start()]
        if re.search(r"[～〜~-]", between):
            return first, to_iso(matches[1])
    return first, None


def sale_window(context: str) -> tuple[str | None, str | None]:
    for token in ("まもなく抽選受付", "まもなく受付", "まもなく発売"):
        pos = context.find(token)
        if pos >= 0:
            start, end = _range_from_tail(context[pos:pos + 320])
            return start, end

    if "発売前" in context:
        pos = context.find("発売前")
        match = DATE_RE.search(context[pos:pos + 220])
        return (to_iso(match) if match else None), None

    for token in ("抽選受付中", "販売期間中", "受付中", "本日発売初日"):
        pos = context.find(token)
        if pos < 0:
            continue
        tail = context[pos:pos + 280]
        matches = list(DATE_RE.finditer(tail))
        if matches:
            return None, to_iso(matches[-1])

    return None, None


def detail_sale_window(session: requests.Session, detail_url: str) -> tuple[str | None, str | None]:
    try:
        response = session.get(detail_url, timeout=8)
        response.raise_for_status()
    except Exception:
        return None, None

    text = norm(BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True))
    for token in ("受付期間", "申込期間", "販売期間", "発売期間", "抽選受付期間"):
        pos = text.find(token)
        if pos < 0:
            continue
        start, end = _range_from_tail(text[pos:pos + 520])
        if start or end:
            return start, end
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
        if not candidate_title or not (
            candidate_title == wanted or candidate_title in wanted or wanted in candidate_title
        ):
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


def candidate_anchors(soup: BeautifulSoup):
    result = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        text = norm(anchor.get_text(" ", strip=True))
        context = context_for_detail(anchor)
        if not DATE_RE.search(context):
            continue
        if not any(hint in context for hint in SALE_HINTS):
            continue
        if "詳細" not in text and "ticketInformation.do" not in str(anchor.get("href") or ""):
            continue
        marker = (str(anchor.get("href") or ""), context[:500])
        if marker in seen:
            continue
        seen.add(marker)
        result.append(anchor)
    return result


def parse_event_page(
    session: requests.Session,
    group: str,
    event_url: str,
    fallback_title: str,
    existing: list[dict],
    today,
) -> list[dict]:
    response = session.get(event_url, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    page_text = norm(soup.get_text(" ", strip=True))
    live_title = extract_live_title(page_text, fallback_title)
    out: list[dict] = []
    seen = set()

    for anchor in candidate_anchors(soup):
        context = context_for_detail(anchor)
        application_status = availability_status(context)
        if application_status is None:
            continue

        start, end = event_window(context)
        if not start:
            continue
        try:
            if datetime.strptime(end or start, "%Y-%m-%d").date() < today:
                continue
        except ValueError:
            continue

        kind = ticket_type(context)
        href = canonical_url(urljoin(event_url, str(anchor.get("href") or "")))
        apply_start, apply_end = sale_window(context)

        detail_start, detail_end = (None, None)
        if href and (apply_start is None and apply_end is None):
            detail_start, detail_end = detail_sale_window(session, href)
        apply_start = detail_start or apply_start
        apply_end = detail_end or apply_end

        schedule = official_schedule(existing, group, live_title, start, end)
        if not schedule:
            schedule = [{"date": start, "venue": None}]
            if end and end != start:
                schedule.append({"date": end, "venue": None})

        event_dates = [x["date"] for x in schedule]
        venues = [x.get("venue") for x in schedule if x.get("venue")]
        venue = (
            venues[0]
            if len(set(venues)) == 1 and venues
            else (f"複数会場（全{len(event_dates)}公演）" if len(event_dates) > 1 else None)
        )

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
            "applicationStatus": application_status,
        })
    return out


def discover_event_pages(session: requests.Session, group: str, artist_url: str) -> list[tuple[str, str]]:
    found: dict[str, str] = {
        canonical_url(url): fallback for url, fallback in SEEDED_EVENT_PAGES.get(group, [])
    }
    response = session.get(artist_url, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if "/pia/event/event.do" not in href:
            continue
        url = canonical_url(urljoin(artist_url, href))
        heading = anchor.find_previous(["h2", "h3", "h4"])
        fallback = norm(
            heading.get_text(" ", strip=True)
            if heading
            else anchor.get_text(" ", strip=True)
        )
        seeded_fallback = found.get(url)
        if seeded_fallback and len(seeded_fallback) > len(fallback):
            found[url] = seeded_fallback
        else:
            found[url] = fallback or seeded_fallback or group
    return list(found.items())


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge active public Ticket Pia sales into the calendar.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    existing_payload = (
        json.loads(DATA_PATH.read_text(encoding="utf-8"))
        if DATA_PATH.exists()
        else {"events": []}
    )
    existing = [x for x in existing_payload.get("events", []) if isinstance(x, dict)]
    today = datetime.now().date()
    session = requests.Session()
    session.headers.update({
        "User-Agent": "KeioKawaiiLabCalendarBot/1.8 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"
    })

    parsed: list[dict] = []
    succeeded: set[str] = set()
    failures: list[str] = []
    discovered = 0

    for group, artist_url in ARTIST_URLS.items():
        pages: list[tuple[str, str]] = list(SEEDED_EVENT_PAGES.get(group, []))
        artist_ok = False
        try:
            pages = discover_event_pages(session, group, artist_url)
            artist_ok = True
        except Exception as exc:
            failures.append(f"{group} artist page: {exc}")

        if pages:
            succeeded.add(group)
        elif artist_ok:
            succeeded.add(group)

        unique_pages = []
        page_seen = set()
        for event_url, fallback in pages:
            event_url = canonical_url(event_url)
            if event_url in page_seen:
                continue
            page_seen.add(event_url)
            unique_pages.append((event_url, fallback))
        discovered += len(unique_pages)

        for event_url, fallback in unique_pages[:40]:
            try:
                parsed.extend(
                    parse_event_page(session, group, event_url, fallback or group, existing, today)
                )
            except Exception as exc:
                failures.append(f"{group} {event_url}: {exc}")

    print(json.dumps({
        "groupsRead": sorted(succeeded),
        "eventPagesDiscovered": discovered,
        "activePiaSales": len(parsed),
        "activePiaSalesByGroup": {
            group: sum(1 for event in parsed if event.get("group") == group)
            for group in ARTIST_URLS
        },
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
    DATA_PATH.write_text(
        json.dumps(existing_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Merged {len(parsed)} active Ticket Pia sale(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
