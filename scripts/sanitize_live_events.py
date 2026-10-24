#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DATA_PATH = Path("data/live-events.json")
TITLE_PREFIX_RE = re.compile(r"^20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+")
TITLE_DATE_RE = re.compile(r"(?:(?:20\d{2})年\s*)?\d{1,2}月\s*\d{1,2}日(?:\s*[（(][^）)]*[）)])?")
AGGREGATE_TICKET_RE = re.compile(r"(?:チケット.*まとめ|まとめ.*チケット)")
GROUP_ORDER = {
    "FRUITS ZIPPER": 0,
    "CANDY TUNE": 1,
    "SWEET STEADY": 2,
    "CUTIE STREET": 3,
    "MORE STAR": 4,
}


def playguide_key(event: dict) -> str:
    explicit = str(event.get("ticketProvider") or event.get("sourceType") or "").lower()
    joined = " ".join(str(x) for x in [event.get("url"), *(event.get("urls") or [])] if x).lower()
    if explicit in {"pia", "lawson", "eplus"}:
        return explicit
    if "t.pia.jp" in joined:
        return "pia"
    if "l-tike.com" in joined:
        return "lawson"
    if "eplus.jp" in joined:
        return "eplus"
    return ""


def clean_title(value: str) -> str:
    return TITLE_PREFIX_RE.sub("", str(value or "")).strip()


def neutral_title(value: str) -> str:
    """受付終了後に表示する公演予定用の、受付文言を含まないタイトルを作る。"""
    title = clean_title(value)
    quoted = re.search(r"「([^」]+)」", title)
    if quoted:
        return quoted.group(1).strip()
    title = re.split(r"(?:開催決定|FC\s*先行|ファンクラブ|OFFICIAL FANCLUB|先行受付|チケット受付)", title, maxsplit=1)[0]
    return title.strip(" !！-–—｜|　") or clean_title(value)


def title_merge_key(value: str) -> str:
    title = clean_title(value)
    title = TITLE_DATE_RE.sub("", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip(" -–—｜|　")


def stable_id(*parts: object) -> str:
    raw = "\x1f".join(str(x or "") for x in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def distinct(values):
    result = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def parse_day(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def event_dates(event: dict) -> list[str]:
    values = []
    raw_dates = event.get("eventDates")
    if isinstance(raw_dates, list):
        values.extend(str(x)[:10] for x in raw_dates if parse_day(x))
    elif parse_day(event.get("eventDate")):
        values.append(str(event.get("eventDate"))[:10])
    return sorted(distinct(values))


def event_schedule(event: dict) -> list[dict]:
    raw = event.get("schedule")
    if isinstance(raw, list) and raw:
        result = []
        seen = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            day = str(item.get("date") or "")[:10]
            venue = str(item.get("venue") or "").strip() or None
            if not parse_day(day):
                continue
            key = (day, venue)
            if key in seen:
                continue
            seen.add(key)
            row = {"date": day, "venue": venue}
            if item.get("openTime"):
                row["openTime"] = item["openTime"]
            if item.get("startTime"):
                row["startTime"] = item["startTime"]
            result.append(row)
        return sorted(result, key=lambda x: x["date"])

    venue = str(event.get("venue") or "").strip() or None
    return [
        {
            "date": day,
            "venue": venue,
            **({"openTime": event["openTime"]} if event.get("openTime") else {}),
            **({"startTime": event["startTime"]} if event.get("startTime") else {}),
        }
        for day in event_dates(event)
    ]


def base_cleanup(payload: dict) -> list[dict]:
    events = []
    seen = set()
    for original in payload.get("events", []):
        if not isinstance(original, dict):
            continue
        event = dict(original)
        event["title"] = clean_title(event.get("title", ""))

        # 「チケット先行まとめ情報」のような集約記事は、1つの受付期間と
        # 複数の別公演の対応関係を安全に特定できないため自動掲載に使わない。
        if AGGREGATE_TICKET_RE.search(event["title"]):
            continue

        event_date = str(event.get("eventDate") or "")[:10]
        result_date = str(event.get("resultDate") or "")[:10]
        if event_date and result_date and event_date == result_date:
            continue

        key = (
            event.get("group"), event.get("url"), event_date,
            event.get("ticketType"), event.get("applyStart"),
        )
        if key in seen:
            continue
        seen.add(key)
        events.append(event)
    return events


def merge_joint_events(events: list[dict]) -> list[dict]:
    buckets: dict[tuple, list[dict]] = {}
    for event in events:
        key = (
            title_merge_key(event.get("title", "")),
            str(event.get("eventDate") or "")[:10],
            event.get("ticketType"),
            event.get("applyStart"),
            event.get("applyEnd"),
            event.get("resultDate"),
            event.get("paymentEnd"),
            re.sub(r"\s+", "", str(event.get("venue") or "")),
        )
        buckets.setdefault(key, []).append(event)

    merged: list[dict] = []
    for key, items in buckets.items():
        groups = distinct(item.get("group") for item in items if item.get("group") in GROUP_ORDER)
        if len(groups) < 2:
            merged.extend(items)
            continue

        groups.sort(key=lambda g: GROUP_ORDER.get(g, 99))
        first = dict(items[0])
        urls = distinct(
            url
            for item in items
            for url in (item.get("urls") or ([item.get("url")] if item.get("url") else []))
        )
        first["id"] = stable_id("joint", *key, *groups)
        first["group"] = "KAWAII LAB.合同"
        first["participants"] = groups
        first["urls"] = urls
        first["url"] = urls[0] if urls else None
        first["sourceType"] = "derived"
        published = [x.get("sourcePublishedAt") for x in items if x.get("sourcePublishedAt")]
        if published:
            first["sourcePublishedAt"] = max(published)
        merged.append(first)
    return merged


def merge_consecutive_days(events: list[dict]) -> list[dict]:
    buckets: dict[tuple, list[dict]] = {}
    for event in events:
        participants = tuple(event.get("participants") or [])
        key = (
            event.get("group"),
            participants,
            title_merge_key(event.get("title", "")),
            playguide_key(event),
            event.get("ticketType"),
            event.get("applyStart"),
            event.get("applyEnd"),
            event.get("resultDate"),
            event.get("paymentEnd"),
            re.sub(r"\s+", "", str(event.get("venue") or "")),
        )
        buckets.setdefault(key, []).append(event)

    result: list[dict] = []
    for key, items in buckets.items():
        dated = [(parse_day(item.get("eventDate")), item) for item in items]
        dated = [(d, item) for d, item in dated if d]
        undated = [item for item in items if not parse_day(item.get("eventDate"))]
        dated.sort(key=lambda pair: pair[0])
        run: list[tuple] = []

        def flush():
            nonlocal run
            if not run:
                return
            if len(run) == 1:
                result.append(run[0][1])
                run = []
                return
            merged = dict(run[0][1])
            dates = [pair[0] for pair in run]
            all_urls = distinct(
                url
                for _, item in run
                for url in (item.get("urls") or ([item.get("url")] if item.get("url") else []))
            )
            merged["eventDate"] = dates[0].isoformat()
            merged["eventEndDate"] = dates[-1].isoformat()
            merged["eventDates"] = [d.isoformat() for d in dates]
            merged["schedule"] = [
                {
                    "date": day.isoformat(),
                    "venue": item.get("venue"),
                    **({"openTime": item["openTime"]} if item.get("openTime") else {}),
                    **({"startTime": item["startTime"]} if item.get("startTime") else {}),
                }
                for day, item in run
            ]
            merged["urls"] = all_urls
            merged["url"] = all_urls[0] if all_urls else merged.get("url")
            merged["id"] = stable_id("range", *key, dates[0], dates[-1])
            if not playguide_key(merged):
                merged["sourceType"] = "derived"
            result.append(merged)
            run = []

        for day, item in dated:
            if not run:
                run = [(day, item)]
                continue
            if day == run[-1][0] + timedelta(days=1):
                run.append((day, item))
            else:
                flush()
                run = [(day, item)]
        flush()
        result.extend(undated)

    return result


def merge_same_window(events: list[dict]) -> list[dict]:
    """同じ公演告知・受付種別・申込期間の複数日程を1件に圧縮する。"""
    buckets: dict[tuple, list[dict]] = {}
    for event in events:
        participants = tuple(event.get("participants") or [])
        key = (
            event.get("group"),
            participants,
            title_merge_key(event.get("title", "")),
            playguide_key(event),
            event.get("ticketType"),
            event.get("applyStart"),
            event.get("applyEnd"),
            event.get("resultDate"),
            event.get("paymentEnd"),
        )
        buckets.setdefault(key, []).append(event)

    result: list[dict] = []
    for key, items in buckets.items():
        schedules = []
        for item in items:
            schedules.extend(event_schedule(item))

        schedule_seen = set()
        schedule = []
        for item in sorted(schedules, key=lambda x: (x["date"], x.get("venue") or "")):
            marker = (item["date"], item.get("venue"))
            if marker in schedule_seen:
                continue
            schedule_seen.add(marker)
            schedule.append(item)

        dates = sorted(distinct(item["date"] for item in schedule))
        if len(dates) <= 1:
            result.extend(items)
            continue

        first = dict(items[0])
        urls = distinct(
            url
            for item in items
            for url in (item.get("urls") or ([item.get("url")] if item.get("url") else []))
        )
        venues = distinct(item.get("venue") for item in schedule)
        first["eventDate"] = dates[0]
        first["eventEndDate"] = dates[-1]
        first["eventDates"] = dates
        first["eventCount"] = len(dates)
        first["schedule"] = schedule
        first["venues"] = venues
        first["venue"] = venues[0] if len(venues) == 1 else f"複数会場（全{len(dates)}公演）"
        first["urls"] = urls
        first["url"] = urls[0] if urls else first.get("url")
        first["id"] = stable_id("same-window", *key, dates[0], dates[-1], len(dates))
        if not playguide_key(first):
            first["sourceType"] = "derived"
        result.append(first)

    return result


def event_identity(event: dict) -> tuple:
    schedule = tuple(
        (item.get("date"), re.sub(r"\s+", "", str(item.get("venue") or "")))
        for item in event_schedule(event)
    )
    return (
        event.get("group"),
        tuple(event.get("participants") or []),
        schedule,
    )


def is_resale_event(event: dict) -> bool:
    return "リセール" in str(event.get("ticketType") or "")


def resale_source_urls(event: dict) -> set[str]:
    values = [
        event.get("url"),
        *(event.get("urls") or []),
        event.get("applicationWindowSource"),
        event.get("deadlineSource"),
    ]
    return {str(value).strip() for value in values if str(value or "").strip()}


def resale_preference(event: dict) -> tuple:
    return (
        str(event.get("sourceType") or "") == "resale-official",
        str(event.get("ticketType") or "") == "公式リセール",
        bool(event.get("applicationWindowVerified")),
        bool(event.get("deadlineVerified")),
        str(event.get("sourcePublishedAt") or ""),
    )


def resale_venue_keys(event: dict) -> set[str]:
    values = [event.get("venue")]
    values.extend(item.get("venue") for item in event_schedule(event))
    result = set()
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        raw = re.sub(r"^(?:北海道|東京都|京都府|大阪府|.{2,3}県)[\s　・]+", "", raw)
        raw = re.sub(r"^[^・]{1,8}・", "", raw)
        key = re.sub(r"[\s　・･/／()（）\-－]", "", raw).lower()
        if key:
            result.add(key)
    return result


def resale_start_times(event: dict) -> set[str]:
    values = [event.get("startTime")]
    values.extend(item.get("startTime") for item in event_schedule(event))
    return {str(value).strip() for value in values if str(value or "").strip()}


def resale_performances_compatible(left: dict, right: dict) -> bool:
    left_venues = resale_venue_keys(left)
    right_venues = resale_venue_keys(right)
    if not left_venues or not right_venues or left_venues.isdisjoint(right_venues):
        return False

    left_times = resale_start_times(left)
    right_times = resale_start_times(right)
    if left_times and right_times:
        return not left_times.isdisjoint(right_times)
    if not left_times and not right_times:
        return title_merge_key(left.get("title", "")) == title_merge_key(right.get("title", ""))
    return True


def merge_duplicate_resale_windows(events: list[dict]) -> list[dict]:
    """同一公演・同一期間・同一URLの公式リセールを取得経路に関係なく1件に統合する。"""
    result: list[dict] = []
    positions: dict[tuple, list[int]] = {}

    for event in events:
        if not is_resale_event(event):
            result.append(event)
            continue

        key = (
            event.get("group"),
            tuple(event.get("participants") or []),
            tuple(event_dates(event)),
            event.get("applyStart"),
            event.get("applyEnd"),
            event.get("resultDate"),
            event.get("paymentEnd"),
        )
        urls = resale_source_urls(event)
        match = next(
            (
                index
                for index in positions.get(key, [])
                if (
                    urls
                    and urls.intersection(resale_source_urls(result[index]))
                    and resale_performances_compatible(event, result[index])
                )
            ),
            None,
        )
        if match is None:
            positions.setdefault(key, []).append(len(result))
            result.append(event)
            continue

        previous = result[match]
        preferred = max((previous, event), key=resale_preference)
        merged = dict(preferred)
        merged_urls = distinct(
            url
            for item in (previous, event)
            for url in (item.get("urls") or ([item.get("url")] if item.get("url") else []))
        )
        source_candidates = distinct(
            source
            for item in (previous, event)
            for source in (item.get("sourceCandidates") or [])
        )
        merged["id"] = stable_id("same-resale-window", key, *merged_urls)
        merged["ticketType"] = "公式リセール"
        merged["urls"] = merged_urls
        merged["url"] = preferred.get("url") or (merged_urls[0] if merged_urls else None)
        merged["sourceCandidates"] = source_candidates
        merged["applicationWindowVerified"] = any(
            bool(item.get("applicationWindowVerified")) for item in (previous, event)
        )
        merged["deadlineVerified"] = any(
            bool(item.get("deadlineVerified")) for item in (previous, event)
        )
        published = [str(item.get("sourcePublishedAt") or "") for item in (previous, event)]
        merged["sourcePublishedAt"] = max(published) or None
        result[match] = merged

    return result


def latest_relevant_ticket_day(event: dict):
    days = [parse_day(event.get(key)) for key in ("applyEnd", "resultDate", "paymentEnd")]
    days = [d for d in days if d]
    return max(days) if days else None


def collapse_expired_application_windows(events: list[dict], today: date) -> list[dict]:
    """終了済み受付を古い締切のまま残さず、未来公演は「現在受付なし」1件にする。"""
    buckets: dict[tuple, list[dict]] = {}
    for event in events:
        buckets.setdefault(event_identity(event), []).append(event)

    result: list[dict] = []
    for identity, items in buckets.items():
        current = []
        expired = []
        schedule_only = []
        for item in items:
            if item.get("ticketType") == "現在受付なし" or (not item.get("applyStart") and not item.get("applyEnd")):
                schedule_only.append(item)
                continue
            last_relevant = latest_relevant_ticket_day(item)
            unknown_deadline = bool(item.get("applyStart")) and not item.get("applyEnd")
            explicitly_closed = str(item.get("applicationStatus") or "").lower() in {"ended", "closed", "sold_out", "cancelled", "canceled"}
            if unknown_deadline and not explicitly_closed:
                current.append(item)
            elif last_relevant and last_relevant >= today:
                current.append(item)
            else:
                expired.append(item)

        if current:
            result.extend(current)
            continue
        if schedule_only:
            result.append(max(schedule_only, key=lambda x: str(x.get("sourcePublishedAt") or "")))
            continue
        if not expired:
            continue

        latest = max(
            expired,
            key=lambda x: (
                str(x.get("applyEnd") or ""),
                str(x.get("sourcePublishedAt") or ""),
            ),
        )
        placeholder = dict(latest)
        all_urls = distinct(
            url
            for item in expired
            for url in (item.get("urls") or ([item.get("url")] if item.get("url") else []))
        )
        placeholder["id"] = stable_id("schedule-only", identity)
        placeholder["title"] = neutral_title(latest.get("title", ""))
        placeholder["ticketType"] = "現在受付なし"
        placeholder["applicationStatus"] = "none"
        placeholder["applyStart"] = None
        placeholder["applyEnd"] = None
        placeholder["resultDate"] = None
        placeholder["paymentEnd"] = None
        placeholder["urls"] = all_urls
        placeholder["url"] = all_urls[0] if all_urls else latest.get("url")
        placeholder["sourceType"] = "derived"
        result.append(placeholder)

    return result


def sanitize_payload(payload: dict, today: date | None = None) -> dict:
    cleaned = dict(payload)
    events = base_cleanup(payload)
    events = merge_joint_events(events)
    events = merge_consecutive_days(events)
    events = merge_same_window(events)
    events = merge_duplicate_resale_windows(events)
    if today is not None:
        events = collapse_expired_application_windows(events, today)
    events.sort(key=lambda e: (
        str(e.get("applyEnd") or "9999"),
        str(e.get("eventDate") or "9999"),
        str(e.get("group") or ""),
    ))
    cleaned["events"] = events
    return cleaned


def main() -> int:
    if not DATA_PATH.exists():
        return 0
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    cleaned = sanitize_payload(payload, today=today)
    DATA_PATH.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Sanitized live calendar data: {len(payload.get('events', []))} -> {len(cleaned.get('events', []))} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
