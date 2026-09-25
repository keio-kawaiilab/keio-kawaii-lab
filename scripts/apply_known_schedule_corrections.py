#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Iterable

DATA_PATH = Path("data/live-events.json")

CUTIE_HAKATA_DAY = "2026-09-27"
CUTIE_HAKATA_OFFICIAL = "https://cutiestreet.asobisystem.com/news/detail/89828"
CUTIE_HAKATA_GOODS = "https://cutiestreet.asobisystem.com/news/detail/90299"
CUTIE_IG_DAYS = ("2026-11-28", "2026-11-29")
CUTIE_IG_1128 = "https://cutiestreet.asobisystem.com/live_information/detail/40368"
CUTIE_IG_1129 = "https://cutiestreet.asobisystem.com/live_information/detail/40369"
SWEET_FC_SECOND_ARTICLE = "https://sweetsteady.asobisystem.com/news/detail/89498"
FM_AICHI_OFFICIAL = "https://fma.co.jp/f/event/?id=6g2EwJVP"

HAKATA_PARTS = [
    {"part": "第1部", "content": "2ショットチェキ撮影会（FC限定）", "start": "10:00", "end": "11:00", "receptionStart": "09:40", "receptionEnd": "10:40"},
    {"part": "第2部", "content": "プリントチェキお渡し会", "start": "11:20", "end": "12:20", "receptionStart": "11:00", "receptionEnd": "12:00"},
    {"part": "第3部", "content": "2ショットチェキ撮影会（FC限定）", "start": "13:20", "end": "14:20", "receptionStart": "13:00", "receptionEnd": "14:00"},
    {"part": "第4部", "content": "プリントチェキお渡し会", "start": "14:40", "end": "15:40", "receptionStart": "14:20", "receptionEnd": "15:20"},
    {"part": "第5部", "content": "プリントチェキお渡し会", "start": "16:40", "end": "17:40", "receptionStart": "16:20", "receptionEnd": "17:20"},
    {"part": "第6部", "content": "2ショットチェキ撮影会（FC限定）", "start": "18:00", "end": "19:00", "receptionStart": "17:40", "receptionEnd": "18:40"},
]

IG_SCHEDULE = [
    {"date": "2026-11-28", "venue": "愛知県 IGアリーナ", "openTime": "16:00", "startTime": "18:00"},
    {"date": "2026-11-29", "venue": "愛知県 IGアリーナ", "openTime": "14:30", "startTime": "16:30"},
]


def _urls(event: dict) -> list[str]:
    values: list[str] = []
    for value in [event.get("url"), *(event.get("urls") or [])]:
        text = str(value or "").strip()
        if text and text not in values:
            values.append(text)
    return values


def _day(event: dict) -> str:
    return str(event.get("eventDate") or "")[:10]


def _is_hakata_special(event: dict) -> bool:
    return (
        event.get("group") == "CUTIE STREET"
        and _day(event) == CUTIE_HAKATA_DAY
        and event.get("eventCategory") == "large-benefit"
        and ("博多" in str(event.get("title") or "") or "大特典会" in str(event.get("title") or ""))
    )


def _repair_hakata(event: dict) -> dict:
    out = deepcopy(event)
    title = "CUTIE STREET大特典会＠博多国際展示場"
    venue = "福岡県 博多国際展示場＆カンファレンスセンター 3F"
    out.update({
        "title": title,
        "eventTitle": title,
        "eventDate": CUTIE_HAKATA_DAY,
        "eventEndDate": CUTIE_HAKATA_DAY,
        "eventDates": [CUTIE_HAKATA_DAY],
        "eventCount": 1,
        "venue": venue,
        "openTime": None,
        "startTime": "10:00",
        "schedule": [{"date": CUTIE_HAKATA_DAY, "venue": venue, "startTime": "10:00"}],
        "eventScope": "kawaii-lab",
        "sourceType": "official-special",
        "sourceChannel": "known-official-correction",
        "primarySource": "official",
        "url": CUTIE_HAKATA_OFFICIAL,
        "urls": [CUTIE_HAKATA_OFFICIAL, CUTIE_HAKATA_GOODS],
        "ticketType": "現在受付なし",
        "applicationStatus": "none",
        "applicationDisplayMode": "schedule-only",
        "specialDetailsStatus": "ticket-details-found",
        "partsStatus": "complete",
        "parts": deepcopy(HAKATA_PARTS),
        "offers": [],
    })
    for key in ("applyStart", "applyEnd", "resultDate", "paymentEnd", "ticketProvider"):
        out.pop(key, None)
    return out


def _is_cutie_wrong_bundle(event: dict) -> bool:
    return event.get("group") == "CUTIE STREET" and any("eventCd=2635331" in value for value in _urls(event))


def _is_cutie_obsolete_tour_sale(event: dict) -> bool:
    if event.get("group") != "CUTIE STREET":
        return False
    if str(event.get("sourceChannel") or "") != "pia-ended-sale":
        return False
    values = _urls(event)
    return any(
        marker in value
        for value in values
        for marker in ("lotRlsCd=95188", "lotRlsCd=23843")
    )


def _is_cutie_ig_offer(event: dict) -> bool:
    if event.get("group") != "CUTIE STREET":
        return False
    values = _urls(event)
    days = {str(row.get("date") or "")[:10] for row in event.get("schedule") or [] if isinstance(row, dict)}
    return (
        any("lotRlsCd=52216" in value for value in values)
        or ("IGアリーナ" in str(event.get("title") or "") and bool(days.intersection(CUTIE_IG_DAYS)))
    )


def _repair_cutie_ig(event: dict) -> dict:
    out = deepcopy(event)
    out.update({
        "eventDate": "2026-11-28",
        "eventEndDate": "2026-11-29",
        "eventDates": list(CUTIE_IG_DAYS),
        "eventCount": 2,
        "venue": "愛知県 IGアリーナ",
        "openTime": "16:00",
        "startTime": "18:00",
        "schedule": deepcopy(IG_SCHEDULE),
        "officialScheduleUrl": CUTIE_IG_1128,
    })
    values = _urls(out)
    for value in (CUTIE_IG_1128, CUTIE_IG_1129):
        if value not in values:
            values.append(value)
    out["urls"] = values
    return out


def _is_joint_christmas(event: dict) -> bool:
    return (
        str(event.get("group") or "") in {"KAWAII LAB.合同", "KAWAII LAB."}
        and "CHRISTMAS SESSION 2026" in str(event.get("title") or event.get("eventTitle") or "").upper()
    )


def _is_redundant_more_star_christmas(event: dict, has_joint: bool) -> bool:
    return (
        has_joint
        and event.get("group") == "MORE STAR"
        and event.get("sourceStale") is True
        and "CHRISTMAS SESSION 2026" in str(event.get("title") or event.get("eventTitle") or "").upper()
    )


def _repair_fm_aichi(event: dict) -> dict:
    out = deepcopy(event)
    if (
        event.get("group") == "SWEET STEADY"
        and _day(event) == "2026-10-18"
        and "FM AICHI" in str(event.get("title") or event.get("eventTitle") or "")
    ):
        out["openTime"] = "12:00"
        out["startTime"] = "13:00"
        out["eventScope"] = "external"
        out["eventScopeCorrectionId"] = "verified-fm-aichi-public-recording"
        out["eventScopeSource"] = "verified-organizer"
        out["eventScopeSourceUrl"] = FM_AICHI_OFFICIAL
        out["organizer"] = "FM AICHI"
        rows = out.get("schedule")
        if isinstance(rows, list) and rows:
            fixed = []
            for row in rows:
                item = dict(row) if isinstance(row, dict) else {}
                if str(item.get("date") or "")[:10] == "2026-10-18":
                    item["openTime"] = "12:00"
                    item["startTime"] = "13:00"
                fixed.append(item)
            out["schedule"] = fixed
    return out


def _repair_sweet_second_fc(event: dict) -> dict:
    out = deepcopy(event)
    if (
        event.get("group") == "SWEET STEADY"
        and str(event.get("applyEnd") or "") == "2026-09-28T23:59"
        and str(event.get("ticketType") or "") == "FC先行"
        and ("FC2次" in str(event.get("title") or "") or SWEET_FC_SECOND_ARTICLE in _urls(event))
        and str(event.get("applyStart") or "") == "2026-09-19T12:00"
    ):
        out["applyStart"] = "2026-09-19T20:00"
        out["applicationWindowVerified"] = True
        out["applicationWindowSource"] = SWEET_FC_SECOND_ARTICLE
        out["deadlineSource"] = SWEET_FC_SECOND_ARTICLE
    return out


def _sale_url(event: dict) -> str:
    value = str(event.get("url") or "").strip().lower()
    return re.sub(r"[?#].*$", "", value).rstrip("/")


def _dedupe_ticket_rows(events: Iterable[dict]) -> tuple[list[dict], int, list[str]]:
    result: list[dict] = []
    positions: dict[tuple, int] = {}
    removed_ids: list[str] = []

    def key(event: dict) -> tuple | None:
        ticket_type = str(event.get("ticketType") or "")
        is_resale = "リセール" in ticket_type
        is_sweet_second = (
            event.get("group") == "SWEET STEADY"
            and str(event.get("applyEnd") or "") == "2026-09-28T23:59"
            and str(event.get("applyStart") or "") == "2026-09-19T20:00"
            and ticket_type == "FC先行"
            and ("FC2次" in str(event.get("title") or "") or SWEET_FC_SECOND_ARTICLE in _urls(event))
        )
        if not (is_resale or is_sweet_second):
            return None
        family = "resale" if is_resale else "sweet-fc2"
        return (
            family,
            str(event.get("group") or ""),
            _day(event),
            str(event.get("startTime") or ""),
            str(event.get("applyStart") or ""),
            str(event.get("applyEnd") or ""),
            _sale_url(event),
        )

    def score(event: dict) -> tuple:
        source = str(event.get("sourceType") or "")
        channel = str(event.get("sourceChannel") or "")
        return (
            int(source == "resale-official"),
            int(channel == "kawaii-lab-resale"),
            int(event.get("applicationWindowVerified") is True),
            len(_urls(event)),
        )

    for event in events:
        k = key(event)
        if k is None:
            result.append(event)
            continue
        if k not in positions:
            positions[k] = len(result)
            result.append(event)
            continue
        old_index = positions[k]
        old = result[old_index]
        if score(event) > score(old):
            removed_ids.append(str(old.get("id") or ""))
            result[old_index] = event
        else:
            removed_ids.append(str(event.get("id") or ""))
    return result, len(removed_ids), removed_ids


def apply_known_corrections(events: Iterable[dict]) -> tuple[list[dict], dict]:
    source = [deepcopy(event) for event in events if isinstance(event, dict)]
    has_joint_christmas = any(_is_joint_christmas(event) for event in source)
    out: list[dict] = []
    report = {
        "hakataSpecialFixed": 0,
        "cutieWrongPiaBundleRemoved": 0,
        "cutieObsoletePiaRowsRemoved": 0,
        "cutieIgFixed": 0,
        "staleChristmasRowsRemoved": 0,
        "fmAichiFixed": 0,
        "sweetFcSecondStartFixed": 0,
        "semanticTicketDuplicatesRemoved": 0,
        "semanticTicketDuplicateIds": [],
    }

    for event in source:
        if _is_cutie_wrong_bundle(event):
            report["cutieWrongPiaBundleRemoved"] += 1
            continue
        if _is_cutie_obsolete_tour_sale(event):
            report["cutieObsoletePiaRowsRemoved"] += 1
            continue
        if _is_redundant_more_star_christmas(event, has_joint_christmas):
            report["staleChristmasRowsRemoved"] += 1
            continue

        current = event
        if _is_hakata_special(current):
            current = _repair_hakata(current)
            report["hakataSpecialFixed"] += 1
        if _is_cutie_ig_offer(current):
            current = _repair_cutie_ig(current)
            report["cutieIgFixed"] += 1

        before_fm = (current.get("startTime"), current.get("eventScope"))
        current = _repair_fm_aichi(current)
        if (current.get("startTime"), current.get("eventScope")) != before_fm:
            report["fmAichiFixed"] += 1

        before_start = current.get("applyStart")
        current = _repair_sweet_second_fc(current)
        if current.get("applyStart") != before_start:
            report["sweetFcSecondStartFixed"] += 1

        out.append(current)

    out, removed, removed_ids = _dedupe_ticket_rows(out)
    report["semanticTicketDuplicatesRemoved"] = removed
    report["semanticTicketDuplicateIds"] = removed_ids
    return out, report


def apply_payload(payload: dict) -> tuple[dict, dict]:
    out = deepcopy(payload)
    events, report = apply_known_corrections(out.get("events") or [])
    out["events"] = events
    return out, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply verified calendar corrections before publication")
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.data.read_text(encoding="utf-8"))
    corrected, report = apply_payload(payload)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.check:
        args.data.write_text(json.dumps(corrected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
