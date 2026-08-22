#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))
OUTPUT_PATH = Path("data/live-events.json")

GROUPS = {
    "FRUITS ZIPPER": "https://fruitszipper.asobisystem.com",
    "CANDY TUNE": "https://candytune.asobisystem.com",
    "SWEET STEADY": "https://sweetsteady.asobisystem.com",
    "CUTIE STREET": "https://cutiestreet.asobisystem.com",
    "MORE STAR": "https://morestar.asobisystem.com",
}

TICKET_HINTS = (
    "先行", "チケット", "受付", "一般発売", "プレリザーブ", "抽選受付",
    "当日券", "リセール", "アップグレード",
)
IGNORE_TITLE_HINTS = (
    "物販", "通販", "グッズ", "特典会", "抽選会", "リリースイベント",
    "オンライン個別", "会員証", "PHOTOBOOK",
)

DATE_ANY_RE = re.compile(
    r"(?:(20\d{2})年\s*)?(\d{1,2})月\s*(\d{1,2})日"
    r"(?:\s*[（(][月火水木金土日・祝]+[）)])?"
    r"(?:\s*(\d{1,2})[:：](\d{2}))?"
)
WINDOW_LABEL_RE = re.compile(r"(?:受付期間|申込期間|お申込期間|お申し込み期間|販売期間)\s*[：:]?")
EVENT_LABEL_RE = re.compile(r"(?:公演日時|日程|公演日|開催日|日時)\s*[：:]")
VENUE_RE = re.compile(r"(?:会場|場所)\s*[：:]\s*(.+)")
RESULT_LABELS = ("当落発表", "当選発表", "抽選結果", "結果発表")
PAYMENT_LABELS = ("入金期限", "入金期間", "支払期限", "お支払い期限")


@dataclass
class Candidate:
    group: str
    title: str
    url: str


def normalize_space(value: str) -> str:
    return re.sub(r"[ \t\u3000]+", " ", value).strip()


def to_iso(year: str | int, month: str | int, day: str | int, hour: str | int | None = None, minute: str | int | None = None) -> str:
    base = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    if hour is None:
        return base
    return f"{base}T{int(hour):02d}:{int(minute or 0):02d}"


def date_match_to_iso(match: re.Match, default_year: int | None = None) -> str | None:
    year, month, day, hour, minute = match.groups()
    year = int(year) if year else default_year
    if not year:
        return None
    return to_iso(year, month, day, hour, minute)


def extract_window(text: str, default_year: int | None = None) -> tuple[str, str] | None:
    for label in WINDOW_LABEL_RE.finditer(text):
        segment = text[label.end():label.end() + 260]
        matches = list(DATE_ANY_RE.finditer(segment))
        if len(matches) < 2:
            continue
        start = date_match_to_iso(matches[0], default_year)
        start_year = int(start[:4]) if start else default_year
        end = date_match_to_iso(matches[1], start_year)
        if start and end:
            return start, end
    return None


def extract_labeled_date(text: str, labels: Iterable[str], default_year: int | None = None) -> str | None:
    for label in labels:
        pos = text.find(label)
        if pos < 0:
            continue
        m = DATE_ANY_RE.search(text[pos:pos + 160])
        if m:
            return date_match_to_iso(m, default_year)
    return None


def extract_ticket_type(title: str, text: str) -> str:
    corpus = f"{title}\n{text[:2600]}"
    patterns = (
        ("年会費コース会員先行", "年会費コース会員先行"),
        ("KAWAII LAB. OFFICIAL FANCLUB 会員先行", "KAWAII LAB. FC先行"),
        ("KAWAII LAB.OFFICIAL FANCLUB 会員先行", "KAWAII LAB. FC先行"),
        ("OFFICIAL FANCLUB 先行", "FC先行"),
        ("ファンクラブ先行", "FC先行"),
        ("FC先行", "FC先行"),
        ("最速プレイガイド先行", "最速プレイガイド先行"),
        ("いち早プレリザーブ", "いち早プレリザーブ"),
        ("プレリザーブ", "プレリザーブ"),
        ("一般先行", "一般先行"),
        ("一般発売", "一般発売"),
        ("アップグレード", "アップグレード抽選"),
        ("リセール", "リセール"),
        ("当日券", "当日券"),
    )
    for needle, label in patterns:
        if needle in corpus:
            return label
    return "チケット受付"


def extract_event_occurrences(lines: list[str], title: str, article_date: str | None) -> list[tuple[str, str | None]]:
    article_year = int(article_date[:4]) if article_date else datetime.now(JST).year
    occurrences: list[tuple[str, str | None]] = []

    for i, line in enumerate(lines):
        label = EVENT_LABEL_RE.search(line)
        if not label:
            continue
        m = DATE_ANY_RE.search(line[label.end():])
        if not m:
            continue
        event_date = date_match_to_iso(m, article_year)
        if not event_date:
            continue
        event_date = event_date[:10]
        venue = None
        for near in lines[i:i + 8]:
            vm = VENUE_RE.search(near)
            if vm:
                venue = normalize_space(vm.group(1))
                break
        occurrences.append((event_date, venue))

    if not occurrences and ("開催" in title or "生誕祭" in title or "ライブ" in title or "TOUR" in title):
        for m in DATE_ANY_RE.finditer(title):
            d = date_match_to_iso(m, article_year)
            if not d:
                continue
            d = d[:10]
            if article_date and d == article_date:
                continue
            occurrences.append((d, None))

    seen = set()
    result = []
    for item in occurrences:
        if item[0] in seen:
            continue
        seen.add(item[0])
        result.append(item)
    return result


def article_title(soup: BeautifulSoup) -> str:
    if soup.title:
        title = normalize_space(soup.title.get_text(" ", strip=True).split("｜")[0])
        if len(title) >= 8 and title not in {"INFORMATION", "SCHEDULE"}:
            return title
    candidates = []
    for tag_name in ("h1", "h2"):
        for node in soup.find_all(tag_name):
            text = normalize_space(node.get_text(" ", strip=True))
            if len(text) >= 8 and text not in {"INFORMATION", "SCHEDULE"}:
                candidates.append(text)
    return max(candidates, key=len) if candidates else "ライブ・チケット情報"


def article_date_from_text(text: str) -> str | None:
    for line in text.splitlines()[:50]:
        m = re.fullmatch(r"\s*(20\d{2})[./](\d{1,2})[./](\d{1,2})\s*", line)
        if m:
            return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def candidate_links(session: requests.Session, group: str, base: str) -> list[Candidate]:
    found: dict[str, Candidate] = {}
    for page in range(1, 4):
        url = f"{base}/news/1/?page={page}"
        r = session.get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "/news/detail/" not in href:
                continue
            title = normalize_space(a.get_text(" ", strip=True))
            if not title:
                continue
            if not any(k in title for k in TICKET_HINTS):
                continue
            if any(k in title for k in IGNORE_TITLE_HINTS):
                continue
            full = urljoin(base, href)
            found[full] = Candidate(group=group, title=title, url=full)
        time.sleep(0.2)
    return list(found.values())


def event_id(group: str, url: str, event_date: str, apply_start: str, ticket_type: str) -> str:
    raw = "\x1f".join((group, url, event_date, apply_start, ticket_type))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def parse_candidate(session: requests.Session, candidate: Candidate) -> tuple[list[dict], dict | None]:
    r = session.get(candidate.url, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    title = article_title(soup) or candidate.title
    text = soup.get_text("\n", strip=True)
    lines = [normalize_space(x) for x in text.splitlines() if normalize_space(x)]

    article_date = article_date_from_text(text)
    default_year = int(article_date[:4]) if article_date else datetime.now(JST).year
    window = extract_window(text, default_year)
    if not window:
        return [], None

    occurrences = extract_event_occurrences(lines, title, article_date)
    ticket_type = extract_ticket_type(title, text)
    apply_year = int(window[0][:4])
    result_date = extract_labeled_date(text, RESULT_LABELS, apply_year)
    payment_end = extract_labeled_date(text, PAYMENT_LABELS, apply_year)

    if not occurrences:
        return [], {
            "group": candidate.group,
            "title": title,
            "url": candidate.url,
            "reason": "申込期間は取得できましたが、公演日を安全に特定できませんでした。",
            "applyStart": window[0],
            "applyEnd": window[1],
        }

    events = []
    for event_date, venue in occurrences:
        events.append({
            "id": event_id(candidate.group, candidate.url, event_date, window[0], ticket_type),
            "group": candidate.group,
            "title": title,
            "ticketType": ticket_type,
            "applyStart": window[0],
            "applyEnd": window[1],
            "resultDate": result_date,
            "paymentEnd": payment_end,
            "eventDate": event_date,
            "venue": venue,
            "url": candidate.url,
            "sourceType": "auto",
            "sourcePublishedAt": article_date,
        })
    return events, None


def read_existing() -> dict:
    if not OUTPUT_PATH.exists():
        return {}
    try:
        return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "KeioKawaiiLabCalendarBot/1.0 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"
    })

    all_events: dict[str, dict] = {}
    pending: list[dict] = []
    failures: list[dict] = []

    for group, base in GROUPS.items():
        try:
            candidates = candidate_links(session, group, base)
        except Exception as exc:
            failures.append({"group": group, "stage": "news-list", "error": str(exc)})
            continue

        for candidate in candidates:
            try:
                events, review = parse_candidate(session, candidate)
                for event in events:
                    all_events[event["id"]] = event
                if review:
                    pending.append(review)
            except Exception as exc:
                failures.append({"group": group, "url": candidate.url, "stage": "article", "error": str(exc)})
            time.sleep(0.3)

    existing = read_existing()
    existing_events = [e for e in existing.get("events", []) if isinstance(e, dict)]
    manual_events = [e for e in existing_events if e.get("sourceType") == "manual"]

    keep_after = datetime.now(JST).date() - timedelta(days=7)
    retained_auto = []
    for e in existing_events:
        if e.get("sourceType") != "auto" or e.get("id") in all_events:
            continue
        end = str(e.get("applyEnd") or "")[:10]
        try:
            end_date = datetime.strptime(end, "%Y-%m-%d").date()
        except ValueError:
            continue
        if end_date >= keep_after:
            retained_auto.append(e)

    if not all_events:
        print("No automatically parsed events were found; existing data left untouched.", file=sys.stderr)
        print(json.dumps({"failures": failures, "pendingReview": pending}, ensure_ascii=False, indent=2))
        return 2

    merged = manual_events + retained_auto + sorted(
        all_events.values(),
        key=lambda e: (e.get("applyEnd") or "9999", e.get("eventDate") or "9999", e.get("group") or "")
    )

    payload = {
        "demo": False,
        "updatedAt": datetime.now(JST).isoformat(timespec="seconds"),
        "source": "KAWAII LAB.各グループ公式サイトの公開INFORMATION",
        "events": merged,
        "pendingReview": pending,
        "failures": failures,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(merged)} events; {len(pending)} pending review; {len(failures)} failures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
