#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable

from schedule_scope import VALID_SCOPES

JST = timezone(timedelta(hours=9))
BAD_UI_TITLE_RE = re.compile(
    r"行きたい\s*[!！]?\s*公演アラート|お気に入り(?:登録)?|メールで通知|通信中|通信エラー|登録完了",
    re.I,
)
OFFICIAL_ONLY_RE = re.compile(
    r"アップグレード|ファンクラブ|年会費コース|OFFICIAL FANCLUB|FC先行|FC会員|FC限定",
    re.I,
)
PIA_LOT_RE = re.compile(r"[?&]lotRlsCd=([A-Za-z0-9_-]+)")
SUKISUKI_GOODS_RE = re.compile(r"sukisuki-shop\.com/goods/(\d+)")
PLACEHOLDER_RE = re.compile(r"^(?:会場未定|未定|TBD|公式ページ記載(?:のイベント参加対象商品)?)$", re.I)


def load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    if not isinstance(payload.get("events"), list):
        raise ValueError(f"{path} must contain an events array")
    return payload


def parse_dt(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return datetime.combine(date.fromisoformat(text), time(23, 59, 59), tzinfo=JST)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=JST)
        return parsed.astimezone(JST)
    except ValueError:
        return None


def parse_day(value: object) -> date | None:
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def clock_minutes(value: object) -> int | None:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", str(value or "").strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def urls(event: dict) -> list[str]:
    result: list[str] = []
    for value in [event.get("url"), *(event.get("urls") or [])]:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def event_days(event: dict) -> list[str]:
    result: list[str] = []
    if isinstance(event.get("schedule"), list):
        for row in event["schedule"]:
            if isinstance(row, dict) and row.get("date"):
                result.append(str(row["date"])[:10])
    if not result and isinstance(event.get("eventDates"), list):
        result.extend(str(value)[:10] for value in event["eventDates"] if value)
    if not result and event.get("eventDate"):
        result.append(str(event["eventDate"])[:10])
    return list(dict.fromkeys(result))


def is_pia(event: dict) -> bool:
    return (
        str(event.get("sourceType") or "").lower() == "pia"
        or str(event.get("primarySource") or "").lower() == "pia"
        or any("t.pia.jp" in value for value in urls(event))
    )


def playguide_provider(event: dict) -> str | None:
    source = str(event.get("ticketProvider") or event.get("sourceType") or event.get("primarySource") or "").lower()
    joined = " ".join(urls(event)).lower()
    if source == "pia" or "t.pia.jp" in joined:
        return "pia"
    if source == "lawson" or "l-tike.com" in joined:
        return "lawson"
    if source == "eplus" or "eplus.jp" in joined:
        return "eplus"
    return None


def is_online(event: dict) -> bool:
    return event.get("eventCategory") == "online-benefit" or bool(
        re.search(r"オンライン(?:特典会|サイン会)", str(event.get("title") or ""))
    )


def official_only(event: dict) -> bool:
    return bool(OFFICIAL_ONLY_RE.search(f"{event.get('ticketType', '')} {event.get('title', '')}"))


def is_ticket_listing(event: dict) -> bool:
    ticket = str(event.get("ticketType") or "").strip()
    return bool(ticket and ticket != "現在受付なし" and event.get("applicationStatus") != "none")


def lot_key(event: dict) -> str | None:
    for value in urls(event):
        match = PIA_LOT_RE.search(value)
        if match:
            return f"pia:{match.group(1)}"
    return None


def goods_key(event: dict) -> str | None:
    for value in urls(event):
        match = SUKISUKI_GOODS_RE.search(value)
        if match:
            return f"sukisuki:{match.group(1)}"
    return None


def stable_keys(event: dict) -> list[str]:
    result: list[str] = []
    for key in (lot_key(event), goods_key(event)):
        if key and key not in result:
            result.append(key)
    provider = playguide_provider(event)
    day_suffix = ",".join(event_days(event))
    for value in urls(event):
        if not value:
            continue
        if provider in {"lawson", "eplus"}:
            key = f"{provider}:{value}:days:{day_suffix}"
        else:
            key = f"url:{value}"
        if key not in result:
            result.append(key)
    if event.get("id"):
        result.append(f"id:{event['id']}")
    return result


def future_or_active(event: dict, today: date) -> bool:
    dates = [parse_day(value) for value in event_days(event)]
    dates = [value for value in dates if value]
    if dates and max(dates) >= today:
        return True
    deadline = parse_day(event.get("applyEnd"))
    return bool(deadline and deadline >= today)


def source_evidence_for_deadline(event: dict) -> bool:
    if is_pia(event):
        source = str(event.get("deadlineSource") or event.get("applicationWindowSource") or "")
        return bool(event.get("deadlineVerified") is True and "t.pia.jp" in source and "ticketInformation.do" in source)
    provider = playguide_provider(event)
    source = str(event.get("deadlineSource") or event.get("applicationWindowSource") or "")
    if provider == "lawson":
        return event.get("deadlineVerified") is True and "l-tike.com" in source
    if provider == "eplus":
        return event.get("deadlineVerified") is True and "eplus.jp" in source
    return any("asobisystem.com" in value or "sukisuki-shop.com" in value for value in urls(event))


def label(event: dict) -> str:
    return f"{event.get('group') or '?'} / {event.get('title') or '?'} / {event.get('ticketType') or '?'}"


def build_index(events: Iterable[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for event in events:
        for key in stable_keys(event):
            index.setdefault(key, event)
    return index


def replaced_by_joint_christmas(old: dict, candidates: Iterable[dict]) -> bool:
    if "チケット先行情報" not in str(old.get("title") or ""):
        return False
    group = str(old.get("group") or "")
    old_days = set(event_days(old))
    for event in candidates:
        title = str(event.get("eventTitle") or event.get("title") or "")
        event_participants = {str(value) for value in event.get("participants") or []}
        if (
            "CHRISTMAS SESSION" in title.upper()
            and group in event_participants
            and old_days.intersection(event_days(event))
        ):
            return True
    return False


def audit(previous: dict, candidate: dict, now: datetime) -> tuple[list[str], list[str], dict]:
    errors: list[str] = []
    warnings: list[str] = []
    prev_events = [event for event in previous.get("events", []) if isinstance(event, dict)]
    cand_events = [event for event in candidate.get("events", []) if isinstance(event, dict)]
    now = now.astimezone(JST)
    today = now.date()

    prev_updated = parse_dt(previous.get("updatedAt"))
    cand_updated = parse_dt(candidate.get("updatedAt"))
    if previous.get("updatedAt") and not prev_updated:
        errors.append("previous updatedAt is invalid")
    if candidate.get("updatedAt") and not cand_updated:
        errors.append("candidate updatedAt is invalid")
    if prev_updated and cand_updated and cand_updated < prev_updated:
        errors.append("candidate updatedAt moved backwards")

    seen_ids: set[str] = set()
    seen_lots: dict[str, dict] = {}
    for event in cand_events:
        if event.get("eventScope") not in VALID_SCOPES:
            errors.append(f"missing or invalid eventScope: {label(event)}")

        event_id = str(event.get("id") or "").strip()
        if event_id:
            if event_id in seen_ids:
                errors.append(f"duplicate event id: {event_id}")
            seen_ids.add(event_id)

        title = str(event.get("eventTitle") or event.get("title") or "").strip()
        if not title:
            errors.append(f"missing title: {label(event)}")
        elif BAD_UI_TITLE_RE.search(title):
            errors.append(f"UI text leaked into title: {label(event)}")

        days = event_days(event)
        if not days:
            errors.append(f"missing performance date: {label(event)}")
        for value in days:
            if not parse_day(value):
                errors.append(f"invalid performance date {value}: {label(event)}")

        for field in ("applyStart", "applyEnd", "resultDate", "paymentEnd"):
            value = event.get(field)
            if value and not parse_dt(value):
                errors.append(f"invalid {field}={value}: {label(event)}")

        start = parse_dt(event.get("applyStart"))
        end = parse_dt(event.get("applyEnd"))
        if start and end and start > end:
            errors.append(f"application window reversed: {label(event)}")

        result_day = parse_day(event.get("resultDate"))
        end_day = parse_day(event.get("applyEnd"))
        payment_day = parse_day(event.get("paymentEnd"))
        if result_day and end_day and result_day < end_day:
            errors.append(f"result date is before application deadline: {label(event)}")
        if payment_day and result_day and payment_day < result_day:
            errors.append(f"payment deadline is before result date: {label(event)}")

        if is_ticket_listing(event) and not urls(event):
            errors.append(f"ticket listing has no source URL: {label(event)}")

        if is_pia(event):
            if official_only(event):
                errors.append(f"Pia row contains FC/upgrade-only sale: {label(event)}")
            key = lot_key(event)
            if is_ticket_listing(event) and not key:
                errors.append(f"active Pia row has no lotRlsCd detail URL: {label(event)}")
            if key:
                if key in seen_lots:
                    errors.append(f"duplicate Pia lot {key}: {label(event)}")
                else:
                    seen_lots[key] = event
            mode = str(event.get("applicationDisplayMode") or "")
            if mode == "band" and is_ticket_listing(event):
                if not (start and end and event.get("applicationWindowVerified") is True):
                    errors.append(f"verified Pia band is missing exact endpoints: {label(event)}")
            elif mode == "band-from-today" and is_ticket_listing(event):
                if not (end and event.get("deadlineVerified") is True):
                    errors.append(f"Pia deadline band is not verified: {label(event)}")
            elif mode == "pia-listing" and is_ticket_listing(event):
                warnings.append(f"Pia listing published without deadline: {label(event)}")
            if event.get("deadlineVerified") is True and end and not source_evidence_for_deadline(event):
                errors.append(f"Pia deadline claims verified without detail-page evidence: {label(event)}")

        if is_online(event) and is_ticket_listing(event):
            if not any("sukisuki-shop.com/goods/" in value for value in urls(event)):
                errors.append(f"online benefit sale has no SUKISUKI product URL: {label(event)}")

        category = str(event.get("eventCategory") or "")
        if category in {"large-benefit", "release-event"}:
            social_schedule_only = (
                event.get("sourceType") == "official-social"
                and event.get("primarySource") == "official"
                and event.get("specialDetailsStatus") == "awaiting-details"
                and event.get("applicationDisplayMode") == "schedule-only"
                and not (event.get("applyStart") or event.get("applyEnd"))
                and any(re.search(r"https://x\.com/(?:FRUITS_ZIPPER|CANDY_TUNE_|SWEET_STEADY|CUTIE_STREET_|MORE_STAR_)(?:/status/\d+)?", value) for value in urls(event))
            )
            if not any("asobisystem.com" in value for value in urls(event)) and not social_schedule_only:
                errors.append(f"special event has no official source URL: {label(event)}")
            venue = str(event.get("venue") or "").strip()
            if not venue or PLACEHOLDER_RE.fullmatch(venue):
                errors.append(f"special event has no verified venue: {label(event)}")
            schedule_only = (
                (
                    event.get("sourceType") in {"official-schedule", "official-special"}
                    and event.get("specialDetailsStatus") == "awaiting-details"
                    and event.get("applicationDisplayMode") == "schedule-only"
                    and not (event.get("applyStart") or event.get("applyEnd"))
                )
                or social_schedule_only
            )
            if not schedule_only:
                if event.get("sourceType") != "official-special":
                    errors.append(f"special event is not marked as official-source data: {label(event)}")
                if not event.get("purchaseMethod") or not event.get("ticketIssueMethod"):
                    errors.append(f"special event has no participation method: {label(event)}")
                product = str(event.get("product") or "").strip()
                if not product or PLACEHOLDER_RE.fullmatch(product):
                    errors.append(f"special event has no target product: {label(event)}")
                if not (
                    start and end
                    and event.get("applicationWindowVerified") is True
                    and event.get("deadlineVerified") is True
                ):
                    errors.append(f"special event has no verified purchase/ticket window: {label(event)}")
                for field in ("applicationWindowSource", "deadlineSource"):
                    source = str(event.get(field) or "")
                    if "asobisystem.com" not in source:
                        errors.append(f"special event {field} is not backed by an official page: {label(event)}")
                for row in event.get("numberedCallTimes") or []:
                    if not isinstance(row, dict) or not str(row.get("numbers") or "").strip():
                        errors.append(f"special event has an invalid numbered-call row: {label(event)}")
                        continue
                    if clock_minutes(row.get("time")) is None:
                        errors.append(f"special event has an invalid numbered-call time: {label(event)}")
        if category == "release-event" and event.get("specialDetailsStatus") != "awaiting-details":
            if not any("kawaiilab.goods-order.com" in value for value in urls(event)):
                errors.append(f"release event has no KAWAII LAB. STORE URL: {label(event)}")
            release_times = [clock_minutes(event.get(field)) for field in ("salesStartTime", "gatheringTime", "startTime")]
            if any(value is None for value in release_times):
                errors.append(f"release event is missing a verified sales/gathering/start time: {label(event)}")
            elif not (release_times[0] <= release_times[1] <= release_times[2]):
                errors.append(f"release event sales/gathering/start times are out of order: {label(event)}")
        if category == "large-benefit" and event.get("specialDetailsStatus") != "awaiting-details":
            parts = event.get("parts")
            if not isinstance(parts, list) or not parts:
                errors.append(f"large benefit event has no part schedule: {label(event)}")
            else:
                for row in parts:
                    required = ("part", "content", "start", "end", "receptionStart", "receptionEnd")
                    if not isinstance(row, dict) or any(not str(row.get(field) or "").strip() for field in required):
                        errors.append(f"large benefit event has an incomplete part row: {label(event)}")
                        continue
                    clocks = [clock_minutes(row.get(field)) for field in ("start", "end", "receptionStart", "receptionEnd")]
                    if any(value is None for value in clocks):
                        errors.append(f"large benefit event has an invalid part time: {label(event)}")
                    elif clocks[0] >= clocks[1] or clocks[2] > clocks[3] or clocks[3] > clocks[1]:
                        errors.append(f"large benefit event part times are out of order: {label(event)}")

    if prev_events and len(cand_events) > len(prev_events) + max(25, len(prev_events)):
        errors.append(f"candidate event count spiked from {len(prev_events)} to {len(cand_events)}")

    cand_index = build_index(cand_events)
    protected = 0
    for old in prev_events:
        if not future_or_active(old, today):
            continue
        protected += 1
        match = None
        match_key = None
        for key in stable_keys(old):
            if key in cand_index:
                match = cand_index[key]
                match_key = key
                break
        if match is None:
            if replaced_by_joint_christmas(old, cand_events):
                warnings.append(f"redundant group row replaced by joint Christmas event: {label(old)}")
                continue
            errors.append(f"protected future/active item disappeared: {label(old)}")
            continue

        old_days = {value for value in event_days(old) if parse_day(value) and parse_day(value) >= today}
        new_days = set(event_days(match))
        missing_days = sorted(old_days - new_days)
        if missing_days:
            errors.append(f"future performance dates disappeared for {match_key}: {', '.join(missing_days)}")
        added_days = sorted(new_days - set(event_days(old)))
        if added_days:
            warnings.append(f"performance dates added for {match_key}: {', '.join(added_days)}")

        old_end = parse_dt(old.get("applyEnd"))
        new_end = parse_dt(match.get("applyEnd"))
        if old_end and old_end.date() >= today:
            if not new_end:
                errors.append(f"active deadline disappeared for {match_key}: {label(old)}")
            elif new_end < old_end:
                errors.append(
                    f"deadline moved earlier for {match_key}: {old.get('applyEnd')} -> {match.get('applyEnd')} (manual review required)"
                )
            elif new_end > old_end:
                if source_evidence_for_deadline(match):
                    warnings.append(
                        f"deadline extended for {match_key}: {old.get('applyEnd')} -> {match.get('applyEnd')}"
                    )
                else:
                    errors.append(f"deadline changed without source evidence for {match_key}")

    digest = hashlib.sha256(
        json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    report = {
        "status": "blocked" if errors else "ok",
        "generatedAt": now.isoformat(),
        "candidateUpdatedAt": candidate.get("updatedAt"),
        "previousEventCount": len(prev_events),
        "candidateEventCount": len(cand_events),
        "protectedPreviousCount": protected,
        "errorCount": len(errors),
        "warningCount": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "candidateSha256": digest,
    }
    return errors, warnings, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed release audit for the public schedule data")
    parser.add_argument("--previous", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--now", help="ISO-8601 time used by tests")
    args = parser.parse_args()

    now = parse_dt(args.now) if args.now else datetime.now(JST)
    if now is None:
        raise SystemExit("invalid --now")

    previous = load(args.previous)
    candidate = load(args.candidate)
    errors, warnings, report = audit(previous, candidate, now)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Schedule release audit: {report['status']} ({len(errors)} errors, {len(warnings)} warnings)")
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
