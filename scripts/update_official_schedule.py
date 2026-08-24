#!/usr/bin/env python3
"""Merge every future LIVE/EVENT row from each group's official SCHEDULE page."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from schedule_scope import EXTERNAL, HOSTED, apply_event_scope, infer_event_scope, special_event_category

DATA_PATH = Path("data/live-events.json")
INDEX_PATH = Path("data/official-schedule-index.json")
JST = ZoneInfo("Asia/Tokyo")
MONTHS_AHEAD = 12

GROUPS = {
    "FRUITS ZIPPER": "https://fruitszipper.asobisystem.com",
    "CANDY TUNE": "https://candytune.asobisystem.com",
    "SWEET STEADY": "https://sweetsteady.asobisystem.com",
    "CUTIE STREET": "https://cutiestreet.asobisystem.com",
    "MORE STAR": "https://morestar.asobisystem.com",
}

DATE_RE = re.compile(r"(20\d{2})[./年](\d{1,2})[./月](\d{1,2})")
OPEN_RE = re.compile(r"(?:OPEN|開場)\s*[：:]?\s*(\d{1,2})[:：](\d{2})", re.I)
START_RE = re.compile(r"(?:START|開演|開演時間|開始)\s*[：:]?\s*(\d{1,2})[:：](\d{2})", re.I)
GENERIC_TITLE_RE = re.compile(r"^(?:FRUITS ZIPPER|CANDY TUNE|SWEET STEADY|CUTIE STREET|MORE STAR)$", re.I)
PLAYGUIDE_SOURCES = {"pia", "eplus", "lawson"}


@dataclass
class OfficialRow:
    group: str
    day: str
    category: str
    title: str
    url: str
    event_scope: str
    venue: str | None = None
    open_time: str | None = None
    start_time: str | None = None
    represented_by: str | None = None

    def as_index(self) -> dict:
        return {
            "group": self.group,
            "date": self.day,
            "category": self.category,
            "title": self.title,
            "url": self.url,
            "eventScope": self.event_scope,
            "representedBy": self.represented_by,
        }


def normalize_space(value: object) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def month_pairs(today: date, months_ahead: int = MONTHS_AHEAD) -> list[tuple[int, int]]:
    values = []
    for offset in range(months_ahead + 1):
        serial = today.year * 12 + today.month - 1 + offset
        values.append((serial // 12, serial % 12 + 1))
    return values


def stable_id(*values: object) -> str:
    raw = "\x1f".join(str(value or "") for value in values)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def event_days(event: dict) -> list[str]:
    values = []
    for row in event.get("schedule") or []:
        if isinstance(row, dict) and row.get("date"):
            values.append(str(row["date"])[:10])
    if not values:
        values.extend(str(value)[:10] for value in event.get("eventDates") or [] if value)
    if not values and event.get("eventDate"):
        values.append(str(event["eventDate"])[:10])
    return list(dict.fromkeys(values))


def participants(event: dict) -> list[str]:
    values = [str(value) for value in event.get("participants") or [] if value in GROUPS]
    group = str(event.get("group") or "")
    if group in GROUPS and group not in values:
        values.append(group)
    return values


def event_key(title: object) -> str:
    text = normalize_space(title).upper()
    families = (
        (r"KAWAII LAB\.?\s*CHRISTMAS SESSION", "KAWAII-LAB-CHRISTMAS"),
        (r"KAWAII LAB\.?\s*COLLECTION", "KAWAII-LAB-COLLECTION"),
        (r"ROCK IN JAPAN", "ROCK-IN-JAPAN"),
        (r"TOMAKOMAI MIRAI FEST", "TOMAKOMAI-MIRAI-FEST"),
        (r"東京ガールズコレクション|\bTGC\b", "TOKYO-GIRLS-COLLECTION"),
        (r"IDOL RUNWAY", "IDOL-RUNWAY"),
        (r"HIROSHIMA CONTI", "HIROSHIMA-CONTINEW"),
        (r"MOTOGP", "MOTOGP"),
        (r"AGESTOCK", "AGESTOCK"),
        (r"KAWAII KON|HONOLULU|HAWAII", "HAWAII"),
    )
    for pattern, key in families:
        if re.search(pattern, text, re.I):
            return key
    text = re.sub(r"(?:FRUITS ZIPPER|CANDY TUNE|SWEET STEADY|CUTIE STREET|MORE STAR)", "", text)
    text = re.split(r"\s*[@＠]\s*", text, maxsplit=1)[0]
    text = re.sub(r"[（(][^）)]*(?:出演|メンバー|櫻井|鎮西|中山)[^）)]*[）)]", "", text)
    return re.sub(r"[^0-9A-Zぁ-んァ-ヶ一-龠]+", "", text)


def event_family(title: object) -> str:
    text = normalize_space(title)
    for pattern, name in (
        (r"(?:ARENA )?TOUR", "tour"),
        (r"ANNIVERSARY", "anniversary"),
        (r"生誕祭|BIRTHDAY", "birthday"),
        (r"大特典会", "large-benefit"),
        (r"リリースイベント|発売記念イベント", "release"),
        (r"オンライン(?:特典会|サイン会)", "online"),
    ):
        if re.search(pattern, text, re.I):
            return name
    return ""


def parse_schedule_list(html: str, group: str, base: str, year: int, month: int, today: date) -> list[OfficialRow]:
    soup = BeautifulSoup(html, "html.parser")
    result = []
    for anchor in soup.select('a[href*="/live_information/detail/"]'):
        category_node = anchor.select_one(".category")
        category = normalize_space(category_node.get_text(" ", strip=True) if category_node else "").upper()
        if category not in {"LIVE", "EVENT"}:
            continue
        month_node = anchor.select_one(".block--date__month")
        day_node = anchor.select_one(".block--date__date")
        title_node = anchor.select_one(".tit")
        try:
            listed_month = int(normalize_space(month_node.get_text() if month_node else month))
            listed_day = int(normalize_space(day_node.get_text() if day_node else ""))
            event_day = date(year, listed_month, listed_day)
        except (TypeError, ValueError):
            continue
        if event_day < today:
            continue
        title = normalize_space(title_node.get_text(" ", strip=True) if title_node else "")
        if not title:
            continue
        url = urljoin(base, str(anchor.get("href") or ""))
        probe = {"group": group, "title": title}
        result.append(OfficialRow(group, event_day.isoformat(), category, title, url, infer_event_scope(probe)))
    return result


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, str] = {}
    title = soup.select_one(".block--title .tit")
    if title:
        result["title"] = normalize_space(title.get_text(" ", strip=True))
    for item in soup.select(".block--liveinfo li"):
        label_node = item.select_one(".item-tit")
        detail_node = item.select_one(".item-detail")
        label = normalize_space(label_node.get_text(" ", strip=True) if label_node else "")
        detail = normalize_space(detail_node.get_text(" ", strip=True) if detail_node else "")
        if "開催場所" in label or label == "会場":
            result["venue"] = detail
        if "公演日" in label:
            match = DATE_RE.search(detail)
            if match:
                result["date"] = f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    text = normalize_space(soup.get_text(" ", strip=True))
    for pattern, key in ((OPEN_RE, "openTime"), (START_RE, "startTime")):
        match = pattern.search(text)
        if match:
            result[key] = f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"
    return result


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.6, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "KeioKawaiiLabCalendarBot/2.0 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"})
    return session


def collect(session: requests.Session, today: date) -> tuple[list[OfficialRow], dict]:
    rows: list[OfficialRow] = []
    status = {}
    failures = []
    for group, base in GROUPS.items():
        group_rows = []
        for year, month in month_pairs(today):
            url = f"{base}/live_information/schedule/list/?viewMode=default&year={year}&month={month:02d}"
            try:
                response = session.get(url, timeout=25)
                response.raise_for_status()
                group_rows.extend(parse_schedule_list(response.text, group, base, year, month, today))
            except Exception as exc:
                failures.append({"group": group, "url": url, "error": f"{type(exc).__name__}: {exc}"})
            time.sleep(0.04)
        deduped = {(row.group, row.day, row.url): row for row in group_rows}
        group_rows = list(deduped.values())
        rows.extend(group_rows)
        status[group] = {"count": len(group_rows), "monthsChecked": MONTHS_AHEAD + 1}
    if failures:
        raise RuntimeError("Official schedule crawl was incomplete: " + json.dumps(failures, ensure_ascii=False))
    return rows, status


def match_existing(row: OfficialRow, events: list[dict]) -> dict | None:
    candidates = [
        event for event in events
        if row.day in event_days(event) and row.group in participants(event)
    ]
    if not candidates:
        return None
    key = event_key(row.title)
    def best(values: list[dict]) -> dict | None:
        if not values:
            return None
        ranked = []
        for event in values:
            source = str(event.get("sourceType") or event.get("primarySource") or "").lower()
            source_urls = [str(event.get("url") or ""), *(str(value) for value in event.get("urls") or [])]
            score = (
                (8 if source not in PLAYGUIDE_SOURCES else 0)
                + (5 if isinstance(event.get("schedule"), list) and len(event["schedule"]) > 2 else 0)
                + (3 if any("asobisystem.com" in value for value in source_urls) else 0)
            )
            ranked.append((score, event))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return ranked[0][1] if len(ranked) == 1 or ranked[0][0] > ranked[1][0] else None

    exact = [event for event in candidates if event_key(event.get("eventTitle") or event.get("title")) == key]
    selected = best(exact)
    if selected:
        return selected
    family = event_family(row.title)
    same_family = [event for event in candidates if family and event_family(event.get("eventTitle") or event.get("title")) == family]
    selected = best(same_family)
    if selected:
        return selected
    same_scope = [event for event in candidates if infer_event_scope(event) == row.event_scope]
    return best(same_scope)


def enrich_existing(event: dict, row: OfficialRow, detail: dict) -> None:
    event["eventScope"] = row.event_scope
    values = [str(event.get("url") or ""), *(str(value) for value in event.get("urls") or [])]
    values = [value for value in dict.fromkeys(values) if value]
    if row.url not in values:
        values.append(row.url)
    event["urls"] = values
    event["officialScheduleUrl"] = row.url
    current_title = normalize_space(event.get("eventTitle") or event.get("title"))
    source = str(event.get("sourceType") or event.get("primarySource") or "").lower()
    if source in PLAYGUIDE_SOURCES or GENERIC_TITLE_RE.fullmatch(current_title):
        event["title"] = detail.get("title") or row.title
        event["eventTitle"] = event["title"]
    special_category = special_event_category(row.title)
    if special_category:
        event["eventCategory"] = special_category
        if source == "official-schedule":
            event["specialDetailsStatus"] = "awaiting-details"
            event["applicationDisplayMode"] = "schedule-only"
    for field in ("venue", "openTime", "startTime"):
        if detail.get(field) and not event.get(field):
            event[field] = detail[field]


def build_event(rows: list[OfficialRow], detail: dict) -> dict:
    first = rows[0]
    groups = list(dict.fromkeys(row.group for row in rows))
    joint = len(groups) > 1
    title = detail.get("title") or first.title
    event_id = stable_id("official-schedule", first.day, event_key(title), ",".join(groups), first.url)
    event = {
        "id": event_id,
        "group": "KAWAII LAB.合同" if joint else first.group,
        "participants": groups if joint else None,
        "title": title,
        "eventTitle": title,
        "ticketType": "現在受付なし",
        "applicationStatus": "none",
        "applyStart": None,
        "applyEnd": None,
        "resultDate": None,
        "paymentEnd": None,
        "eventDate": first.day,
        "venue": detail.get("venue"),
        "openTime": detail.get("openTime"),
        "startTime": detail.get("startTime"),
        "url": first.url,
        "urls": list(dict.fromkeys(row.url for row in rows)),
        "sourceType": "official-schedule",
        "primarySource": "official",
        "eventScope": first.event_scope,
    }
    special_category = special_event_category(title)
    if special_category:
        event["eventCategory"] = special_category
        event["specialDetailsStatus"] = "awaiting-details"
        event["applicationDisplayMode"] = "schedule-only"
    return {key: value for key, value in event.items() if value is not None}


def collapse_missing(rows: list[OfficialRow]) -> list[list[OfficialRow]]:
    buckets: dict[tuple[str, str, str], list[OfficialRow]] = {}
    for row in rows:
        shared_key = event_key(row.title) if row.event_scope == EXTERNAL or event_key(row.title).startswith("KAWAII-LAB-") else row.url
        buckets.setdefault((row.day, row.event_scope, shared_key), []).append(row)
    result = []
    for bucket in buckets.values():
        result.append(bucket)
    return result


def remove_redundant_rows(events: list[dict]) -> list[dict]:
    joint_days = {
        day
        for event in events
        if len(participants(event)) > 1 and "CHRISTMAS SESSION" in normalize_space(event.get("title")).upper()
        for day in event_days(event)
    }
    return [
        event for event in events
        if not (
            event.get("group") == "MORE STAR"
            and "チケット先行情報" in normalize_space(event.get("title"))
            and any(day in joint_days for day in event_days(event))
        )
    ]


def propagate_ticket_scopes(events: list[dict], rows: list[OfficialRow]) -> int:
    """Give ticket-only rows the scope of their represented official performance."""
    changed = 0
    for row in rows:
        official_family = event_family(row.title)
        for event in events:
            source = str(event.get("sourceType") or event.get("primarySource") or "").lower()
            if source not in PLAYGUIDE_SOURCES or row.day not in event_days(event) or row.group not in participants(event):
                continue
            current_title = normalize_space(event.get("eventTitle") or event.get("title"))
            if not (GENERIC_TITLE_RE.fullmatch(current_title) or (official_family and event_family(current_title) == official_family)):
                continue
            if event.get("eventScope") != row.event_scope:
                event["eventScope"] = row.event_scope
                changed += 1
    return changed


def merge(payload: dict, rows: list[OfficialRow], session: requests.Session) -> tuple[dict, dict]:
    events = [dict(event) for event in payload.get("events", []) if isinstance(event, dict)]
    events = [event for event in events if event.get("sourceType") != "official-schedule"]
    detail_cache: dict[str, dict] = {}

    def detail(row: OfficialRow) -> dict:
        if row.url not in detail_cache:
            response = session.get(row.url, timeout=25)
            response.raise_for_status()
            detail_cache[row.url] = parse_detail(response.text)
            time.sleep(0.04)
        return detail_cache[row.url]

    missing = []
    for row in rows:
        matched = match_existing(row, events)
        if matched:
            source = str(matched.get("sourceType") or matched.get("primarySource") or "").lower()
            current_title = normalize_space(matched.get("eventTitle") or matched.get("title"))
            single_performance = len(event_days(matched)) == 1
            needs_detail = (
                source in PLAYGUIDE_SOURCES
                or bool(GENERIC_TITLE_RE.fullmatch(current_title))
                or not matched.get("venue")
                or (single_performance and not (matched.get("openTime") and matched.get("startTime")))
            )
            enrich_existing(matched, row, detail(row) if needs_detail else {})
            row.represented_by = str(matched.get("id") or "")
        else:
            missing.append(row)

    added = []
    for cluster in collapse_missing(missing):
        info = detail(cluster[0])
        event = build_event(cluster, info)
        events.append(event)
        added.append(event)
        for row in cluster:
            row.represented_by = str(event["id"])

    events = remove_redundant_rows(events)
    propagated = propagate_ticket_scopes(events, rows)
    events = [apply_event_scope(event) for event in events]
    out = dict(payload)
    out["events"] = events
    out["updatedAt"] = datetime.now(JST).isoformat(timespec="seconds")
    diagnostics = {
        "officialRows": len(rows),
        "matchedRows": len(rows) - len(missing),
        "addedEvents": len(added),
        "detailPages": len(detail_cache),
        "ticketScopesPropagated": propagated,
    }
    return out, diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--reconcile-ticket-scopes", action="store_true")
    args = parser.parse_args()
    if args.reconcile_ticket_scopes:
        payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        rows = [
            OfficialRow(
                group=str(entry.get("group") or ""), day=str(entry.get("date") or ""),
                category=str(entry.get("category") or ""), title=str(entry.get("title") or ""),
                url=str(entry.get("url") or ""), event_scope=str(entry.get("eventScope") or EXTERNAL),
                represented_by=str(entry.get("representedBy") or ""),
            )
            for entry in index.get("entries") or [] if isinstance(entry, dict)
        ]
        events = [dict(event) for event in payload.get("events", []) if isinstance(event, dict)]
        changed = propagate_ticket_scopes(events, rows)
        payload["events"] = events
        DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Reconciled {changed} ticket-row scopes from the official schedule index")
        return 0
    today = datetime.now(JST).date()
    session = make_session()
    rows, status = collect(session, today)
    if not rows or any(status[group]["count"] == 0 for group in GROUPS):
        raise SystemExit(f"Official schedule crawl returned an unsafe result: {status}")
    if args.check:
        print(json.dumps({"officialRows": len(rows), "groups": status}, ensure_ascii=False, indent=2))
        return 0
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    merged, diagnostics = merge(payload, rows, session)
    if any(not row.represented_by for row in rows):
        raise SystemExit("Not every official schedule row was represented; refusing to write")
    index = {
        "updatedAt": datetime.now(JST).isoformat(timespec="seconds"),
        "range": {"start": today.isoformat(), "monthsAhead": MONTHS_AHEAD},
        "groups": status,
        "entries": [row.as_index() for row in rows],
    }
    DATA_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
