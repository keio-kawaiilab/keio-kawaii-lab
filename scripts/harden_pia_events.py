#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

DATA_PATH = Path("data/live-events.json")

BAD_TITLE_RE = re.compile(
    r"(?:行きたい\s*[!！]?\s*公演アラート|お気に入り(?:登録)?|メールで通知|"
    r"チケットぴあ|通信中|通信エラー|登録完了|詳細はこちら)$",
    re.I,
)

DATE_RE = re.compile(
    r"(20\d{2})\s*(?:/|\.|-|年)\s*(\d{1,2})\s*(?:/|\.|-|月)\s*(\d{1,2})\s*(?:日)?"
    r"(?:\s*[（(][^）)]*[）)])?\s*(?:午前|午後|昼)?\s*(\d{1,2})?\s*(?::|時)?\s*(\d{2})?\s*(?:分)?"
)
PERIOD_LABELS = ("抽選受付期間", "受付期間", "申込期間", "販売期間", "発売期間")


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def to_iso(match: re.Match) -> str:
    year, month, day, hour, minute = match.groups()
    base = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    if hour is None:
        return base
    return f"{base}T{int(hour):02d}:{int(minute or 0):02d}"


def exact_period_from_text(text: str) -> tuple[str | None, str | None]:
    text = norm(text)
    for label in PERIOD_LABELS:
        pos = text.find(label)
        if pos < 0:
            continue
        tail = text[pos:pos + 900]
        matches = list(DATE_RE.finditer(tail))
        if len(matches) < 2:
            continue
        first, second = matches[0], matches[1]
        between = tail[first.end():second.start()]
        if not re.search(r"[～〜~\-–—]|から", between):
            continue
        start, end = to_iso(first), to_iso(second)
        if start <= end:
            return start, end
    return None, None


def event_days(event: dict) -> list[str]:
    days: list[str] = []
    schedule = event.get("schedule")
    if isinstance(schedule, list):
        for item in schedule:
            if isinstance(item, dict) and item.get("date"):
                days.append(str(item["date"])[:10])
    dates = event.get("eventDates")
    if isinstance(dates, list):
        days.extend(str(value)[:10] for value in dates if value)
    if not days and event.get("eventDate"):
        days.append(str(event["eventDate"])[:10])
    return list(dict.fromkeys(days))


def is_pia(event: dict) -> bool:
    urls = [str(event.get("url") or "")] + [str(x) for x in (event.get("urls") or [])]
    return (
        str(event.get("sourceType") or "").lower() == "pia"
        or str(event.get("primarySource") or "").lower() == "pia"
        or any("t.pia.jp" in url for url in urls)
    )


def pia_detail_urls(event: dict) -> list[str]:
    urls = [str(event.get("url") or "")] + [str(x) for x in (event.get("urls") or [])]
    result = []
    for url in urls:
        if "t.pia.jp" not in url or "ticketInformation.do" not in url:
            continue
        if url not in result:
            result.append(url)
    return result


def is_bad_title(value: object) -> bool:
    title = norm(value)
    if not title:
        return True
    return bool(BAD_TITLE_RE.search(title))


def official_candidates(events: list[dict], target: dict) -> list[dict]:
    target_days = set(event_days(target))
    if not target_days:
        return []
    result = []
    for event in events:
        if event is target or is_pia(event):
            continue
        if event.get("group") != target.get("group"):
            continue
        if event.get("eventCategory") == "online-benefit":
            continue
        candidate_days = set(event_days(event))
        overlap = target_days & candidate_days
        if not overlap:
            continue
        title = event.get("eventTitle") or event.get("title")
        if is_bad_title(title):
            continue
        score = len(overlap) * 10
        if target_days <= candidate_days:
            score += 100
        score += min(len(candidate_days), 40)
        result.append((score, event))
    result.sort(key=lambda pair: pair[0], reverse=True)
    return [event for _, event in result]


def subset_schedule(source: dict, wanted_days: list[str]) -> list[dict]:
    wanted = set(wanted_days)
    schedule = source.get("schedule")
    if isinstance(schedule, list):
        rows = [
            {"date": str(item.get("date"))[:10], "venue": item.get("venue")}
            for item in schedule
            if isinstance(item, dict) and str(item.get("date") or "")[:10] in wanted
        ]
        if rows:
            return rows
    venue = source.get("venue")
    return [{"date": day, "venue": venue} for day in wanted_days]


def repair_title_and_schedule(event: dict, all_events: list[dict]) -> dict:
    out = dict(event)
    candidates = official_candidates(all_events, event)
    if not candidates:
        return out
    source = candidates[0]
    if is_bad_title(out.get("title")) or not norm(out.get("title")):
        out["title"] = source.get("eventTitle") or source.get("title")
        out["eventTitle"] = source.get("eventTitle") or source.get("title")
        out["titleSource"] = "official-schedule-match"
    wanted_days = event_days(out)
    schedule = subset_schedule(source, wanted_days)
    if schedule:
        out["schedule"] = schedule if len(schedule) > 1 else None
        venues = [str(item.get("venue") or "").strip() for item in schedule if item.get("venue")]
        unique_venues = list(dict.fromkeys(venues))
        if len(unique_venues) == 1:
            out["venue"] = unique_venues[0]
        elif len(unique_venues) > 1:
            out["venue"] = f"複数会場（全{len(schedule)}公演）"
            out["venues"] = unique_venues
    return out


def fetch_exact_period(session: requests.Session, event: dict) -> tuple[str | None, str | None, str | None]:
    for url in pia_detail_urls(event):
        try:
            response = session.get(url, timeout=12)
            response.raise_for_status()
        except Exception:
            continue
        text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
        start, end = exact_period_from_text(text)
        if start and end:
            return start, end, url
    start = str(event.get("applyStart") or "") or None
    end = str(event.get("applyEnd") or "") or None
    if start and end and start <= end:
        return start, end, None
    return None, None, None


def harden(events: list[dict], session: requests.Session) -> tuple[list[dict], list[dict]]:
    kept: list[dict] = []
    rejected: list[dict] = []
    for raw in events:
        event = dict(raw)
        if not is_pia(event) or event.get("ticketType") == "現在受付なし":
            kept.append(event)
            continue

        event = repair_title_and_schedule(event, events)
        start, end, verified_url = fetch_exact_period(session, event)
        reasons = []
        if is_bad_title(event.get("title")):
            reasons.append("generic-or-ui-title")
        if not start or not end:
            reasons.append("incomplete-application-window")
        elif start > end:
            reasons.append("application-window-reversed")

        if reasons:
            rejected.append({
                "id": event.get("id"),
                "group": event.get("group"),
                "title": event.get("title"),
                "ticketType": event.get("ticketType"),
                "reasons": reasons,
                "urls": event.get("urls") or [event.get("url")],
            })
            continue

        event["applyStart"] = start
        event["applyEnd"] = end
        event["applicationWindowVerified"] = True
        event["applicationWindowSource"] = verified_url or event.get("url")
        kept.append(event)
    return kept, rejected


def validate_public_pia(events: list[dict]) -> list[str]:
    problems = []
    for event in events:
        if not is_pia(event) or event.get("ticketType") == "現在受付なし":
            continue
        if is_bad_title(event.get("title")):
            problems.append(f"generic title: {event.get('id')} {event.get('title')}")
        start, end = event.get("applyStart"), event.get("applyEnd")
        if not start or not end:
            problems.append(f"incomplete window: {event.get('id')} {start} -> {end}")
        elif str(start) > str(end):
            problems.append(f"reversed window: {event.get('id')} {start} -> {end}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Ticket Pia titles and exact application windows before publication.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    events = [dict(x) for x in payload.get("events", []) if isinstance(x, dict)]
    session = requests.Session()
    session.headers.update({"User-Agent": "KeioKawaiiLabCalendarBot/2.0 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"})

    hardened, rejected = harden(events, session)
    problems = validate_public_pia(hardened)
    print(json.dumps({
        "piaBefore": sum(1 for x in events if is_pia(x)),
        "piaAfter": sum(1 for x in hardened if is_pia(x)),
        "rejected": rejected,
        "validationProblems": problems,
    }, ensure_ascii=False, indent=2))

    if problems:
        return 1
    if not args.check:
        payload["events"] = hardened
        DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
