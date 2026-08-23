#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

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
PERIOD_LABELS = (
    "抽選受付期間", "受付期間", "申込期間", "販売期間", "発売期間",
    "お申し込み期間", "申込み期間", "エントリー期間",
)
DEADLINE_HINTS = (
    "抽選受付中", "販売期間中", "受付中", "申込受付中", "受付締切",
    "申込締切", "販売終了日時", "受付終了日時",
)


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def to_iso(match: re.Match) -> str:
    year, month, day, hour, minute = match.groups()
    base = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return base if hour is None else f"{base}T{int(hour):02d}:{int(minute or 0):02d}"


def exact_period_from_text(text: str) -> tuple[str | None, str | None]:
    text = norm(text)
    for label in PERIOD_LABELS:
        pos = text.find(label)
        if pos < 0:
            continue
        tail = text[pos:pos + 1200]
        matches = list(DATE_RE.finditer(tail))
        if len(matches) < 2:
            continue
        first, second = matches[0], matches[1]
        between = tail[first.end():second.start()]
        if not re.search(r"[～〜~\-–—]|から|より", between):
            continue
        start, end = to_iso(first), to_iso(second)
        if start <= end:
            return start, end
    return None, None


def deadline_from_text(text: str) -> str | None:
    text = norm(text)
    for hint in DEADLINE_HINTS:
        pos = text.find(hint)
        if pos < 0:
            continue
        tail = text[pos:pos + 500]
        matches = list(DATE_RE.finditer(tail))
        if matches:
            return to_iso(matches[-1])
    return None


def event_days(event: dict) -> list[str]:
    days: list[str] = []
    if isinstance(event.get("schedule"), list):
        for item in event["schedule"]:
            if isinstance(item, dict) and item.get("date"):
                days.append(str(item["date"])[:10])
    if isinstance(event.get("eventDates"), list):
        days.extend(str(value)[:10] for value in event["eventDates"] if value)
    if not days and event.get("eventDate"):
        days.append(str(event["eventDate"])[:10])
    return list(dict.fromkeys(days))


def is_pia(event: dict) -> bool:
    urls = [str(event.get("url") or "")] + [str(x) for x in (event.get("urls") or [])]
    return (
        str(event.get("sourceType") or "").lower() == "pia"
        or str(event.get("primarySource") or "").lower() == "pia"
        or any("t.pia.jp" in value for value in urls)
    )


def official_only_family(event: dict) -> bool:
    text = norm(f"{event.get('ticketType', '')} {event.get('title', '')}")
    upper = text.upper()
    return (
        "アップグレード" in text
        or "ファンクラブ" in text
        or "年会費コース" in text
        or "OFFICIAL FANCLUB" in upper
        or "FC先行" in upper
        or "FC会員" in upper
        or "FC限定" in upper
    )


def is_bad_title(value: object) -> bool:
    text = norm(value)
    return not text or bool(BAD_TITLE_RE.search(text))


def pia_detail_urls(event: dict) -> list[str]:
    values = [str(event.get("url") or "")] + [str(x) for x in (event.get("urls") or [])]
    result = []
    for value in values:
        if value and "t.pia.jp" in value and "ticketInformation.do" in value and value not in result:
            result.append(value)
    return result


def official_candidates(all_events: list[dict], target: dict) -> list[dict]:
    group = str(target.get("group") or "")
    target_days = set(event_days(target))
    if not group or not target_days:
        return []
    result: list[tuple[int, dict]] = []
    for event in all_events:
        if event is target or is_pia(event) or str(event.get("group") or "") != group:
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
    if isinstance(source.get("schedule"), list):
        rows = [
            {"date": str(item.get("date"))[:10], "venue": item.get("venue")}
            for item in source["schedule"]
            if isinstance(item, dict) and str(item.get("date") or "")[:10] in wanted
        ]
        if rows:
            return rows
    venue = source.get("venue")
    return [{"date": day, "venue": venue} for day in wanted_days]


def repair_title_and_schedule(event: dict, all_events: list[dict]) -> dict:
    out = dict(event)
    candidates = official_candidates(all_events, event)
    if candidates:
        source = candidates[0]
        if is_bad_title(out.get("title")):
            out["title"] = source.get("eventTitle") or source.get("title")
            out["eventTitle"] = source.get("eventTitle") or source.get("title")
            out["titleSource"] = "official-schedule-match"
        wanted_days = event_days(out)
        schedule = subset_schedule(source, wanted_days)
        if schedule:
            out["schedule"] = schedule if len(schedule) > 1 else None
            venues = [str(item.get("venue") or "").strip() for item in schedule if item.get("venue")]
            unique = list(dict.fromkeys(venues))
            if len(unique) == 1:
                out["venue"] = unique[0]
            elif len(unique) > 1:
                out["venue"] = f"複数会場（全{len(schedule)}公演）"
                out["venues"] = unique
    if is_bad_title(out.get("title")):
        out["title"] = f"{out.get('group') or 'KAWAII LAB.'} 公演"
        out["eventTitle"] = out["title"]
        out["titleSource"] = "safe-pia-fallback"
    return out


def fetch_detail_evidence(session: requests.Session, event: dict) -> tuple[str | None, str | None, str | None, str | None]:
    for url in pia_detail_urls(event):
        try:
            response = session.get(url, timeout=12)
            response.raise_for_status()
        except Exception:
            continue
        text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
        start, end = exact_period_from_text(text)
        if start and end:
            return start, end, end, url
        deadline = deadline_from_text(text)
        if deadline:
            return None, None, deadline, url
    return None, None, None, None


def valid_isoish(value: object) -> bool:
    return bool(re.match(r"^20\d{2}-\d{2}-\d{2}(?:T\d{2}:\d{2})?$", str(value or "")))


def harden(events: list[dict], session: requests.Session) -> tuple[list[dict], list[dict]]:
    kept: list[dict] = []
    rejected: list[dict] = []

    for raw in events:
        event = dict(raw)
        if not is_pia(event) or event.get("ticketType") == "現在受付なし":
            kept.append(event)
            continue

        # FC/upgrade information remains official-only by product policy.
        if official_only_family(event):
            rejected.append({"id": event.get("id"), "reason": "official-only-fc-or-upgrade"})
            continue

        event = repair_title_and_schedule(event, events)
        detail_start, detail_end, detail_deadline, evidence_url = fetch_detail_evidence(session, event)

        if detail_start and detail_end:
            event["applyStart"] = detail_start
            event["applyEnd"] = detail_end
            event["applicationWindowVerified"] = True
            event["deadlineVerified"] = True
            event["applicationDisplayMode"] = "band"
            event["applicationWindowSource"] = evidence_url
            event["deadlineSource"] = evidence_url
        else:
            deadline = detail_deadline
            if not deadline and valid_isoish(event.get("applyEnd")):
                deadline = str(event.get("applyEnd"))
            if deadline:
                # Keep the source start unknown, but the UI intentionally draws the band
                # from today through this known deadline.
                event["applyStart"] = None
                event["applyEnd"] = deadline
                event["applicationWindowVerified"] = False
                event["deadlineVerified"] = True
                event["applicationDisplayMode"] = "band-from-today"
                event["deadlineSource"] = evidence_url or event.get("url")
            else:
                # Pia is the ticketing authority for non-FC/non-upgrade sales. Keep the
                # listing even when timing fields cannot be extracted in this run.
                event["applicationWindowVerified"] = False
                event["deadlineVerified"] = False
                event["applicationDisplayMode"] = "pia-listing"

        kept.append(event)

    return kept, rejected


def validate_public_pia(events: list[dict]) -> list[str]:
    problems = []
    for event in events:
        if not is_pia(event) or event.get("ticketType") == "現在受付なし":
            continue
        if official_only_family(event):
            problems.append(f"Pia FC/upgrade should not publish: {event.get('id')}")
            continue
        if is_bad_title(event.get("title")):
            problems.append(f"generic title remains: {event.get('id')} {event.get('title')}")
            continue
        if event.get("applicationWindowVerified") is True:
            start, end = event.get("applyStart"), event.get("applyEnd")
            if not start or not end or str(start) > str(end):
                problems.append(f"invalid verified band: {event.get('id')} {start} -> {end}")
        elif event.get("deadlineVerified") is True and not event.get("applyEnd"):
            problems.append(f"verified deadline missing: {event.get('id')}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize Ticket Pia listings before publication.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    events = [dict(x) for x in payload.get("events", []) if isinstance(x, dict)]
    session = requests.Session()
    session.headers.update({"User-Agent": "KeioKawaiiLabCalendarBot/2.2 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"})

    hardened, rejected = harden(events, session)
    problems = validate_public_pia(hardened)
    print(json.dumps({
        "piaBefore": sum(1 for x in events if is_pia(x)),
        "piaAfter": sum(1 for x in hardened if is_pia(x)),
        "fullBands": sum(1 for x in hardened if is_pia(x) and x.get("applicationDisplayMode") == "band"),
        "todayBands": sum(1 for x in hardened if is_pia(x) and x.get("applicationDisplayMode") == "band-from-today"),
        "piaListingsWithoutTiming": sum(1 for x in hardened if is_pia(x) and x.get("applicationDisplayMode") == "pia-listing"),
        "rejectedOfficialOnly": rejected,
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
