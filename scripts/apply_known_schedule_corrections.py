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
GIFT_OFFICIAL = "https://www.gift-idol.jp/"
GIFT_MULTI_VENUE = "複数会場（SGCホール有明・TOYOTA ARENA TOKYO）"
GIFT_LOCATIONS = ["東京都 SGC HALL ARIAKE", "東京都 TOYOTA ARENA TOKYO"]
MORE_STAR_7TH_DAY = "2026-11-25"
MORE_STAR_7TH_SCHEDULE = "https://morestar.asobisystem.com/live_information/detail/45677"
MORE_STAR_7TH_NEWS = "https://morestar.asobisystem.com/news/detail/92107"
MORE_STAR_7TH_FC = "https://kawaiilab.asobisystem.com/news/detail/93036"
DISASTER_RELIEF_NEWS = "https://fruitszipper.asobisystem.com/news/detail/93365"
DISASTER_RELIEF_PIA = "https://w.pia.jp/t/charityconcert2027/"
CANDY_ONLINE_20261020_DAY = "2026-10-20"
CANDY_ONLINE_20261020_OFFICIAL = "https://candytune.asobisystem.com/live_information/detail/46277"
CANDY_ONLINE_20261020_GOODS = {
    "https://sukisuki-shop.com/goods/6500000004622",
    "https://sukisuki-shop.com/goods/6500000004623",
}
CUTIE_PACIFICO_FC_ARTICLE = "https://cutiestreet.asobisystem.com/news/detail/93831"
FRUITS_SYNERGY_DAY = "2026-11-01"
FRUITS_SYNERGY_OFFICIAL = "https://fruitszipper.asobisystem.com/live_information/detail/44318"
FRUITS_SYNERGY_GOODS = {
    "https://sukisuki-shop.com/goods/6500000004023",
    "https://sukisuki-shop.com/goods/6500000004943",
}
CHRISTMAS_SESSION_OFFICIAL = "https://kawaiilab.asobisystem.com/news/detail/84218"
CHRISTMAS_SESSION_PIA = "https://t.pia.jp/pia/ticketInformation.do?lotRlsCd=30327"
CHRISTMAS_SESSION_DAYS = {"2026-12-12", "2026-12-13"}

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


def repair_cutie_upgrade_reception(event: dict) -> dict:
    """NEWS 92733's annual-FC wording is eligibility, not another sale.

    Keep occurrence identity, times, windows and provenance untouched. Restrict
    this verified correction to this article's four dates and exact window;
    other FC receptions (including ones mentioning upgrades) remain separate.
    """
    article = "https://cutiestreet.asobisystem.com/news/detail/92733"
    urls = [*_urls(event), event.get("discoverySourceUrl")]
    if not (
        event.get("group") == "CUTIE STREET"
        and article in urls
        and _day(event) in {"2026-11-14", "2026-11-15", "2026-11-28", "2026-11-29"}
        and event.get("ticketType") == "年会費コース会員先行"
        and event.get("applyStart") == "2026-10-15T12:00"
        and event.get("applyEnd") == "2026-10-20T23:59"
    ):
        return event
    out = deepcopy(event)
    out["ticketType"] = "アップグレード抽選"
    return out


def repair_cutie_sano_upgrade_reception(event: dict) -> dict:
    """Restore the verified NEWS 93573 upgrade window and performance time.

    The official SCHEDULE row originally exposed START 17:30.  NEWS 93573
    identifies that value as OPEN and confirms START 19:00.  A stale earlier
    birthday-news enrichment can also leave the same window labelled as an
    annual-FC presale, so correct only this exact article/day/window tuple.
    """
    article = "https://cutiestreet.asobisystem.com/news/detail/93573"
    if not (
        event.get("group") == "CUTIE STREET"
        and article in [*_urls(event), event.get("discoverySourceUrl")]
        and _day(event) == "2026-11-26"
        and event.get("applyStart") == "2026-10-26T12:00"
        and event.get("applyEnd") == "2026-10-29T23:59"
    ):
        return event
    out = deepcopy(event)
    out["ticketType"] = "アップグレード抽選"
    out["openTime"] = "17:30"
    out["startTime"] = "19:00"
    return out


def repair_cutie_sano_schedule_time(event: dict) -> dict:
    """Correct SCHEDULE 46341's stale START value from verified NEWS 93573."""
    schedule = "https://cutiestreet.asobisystem.com/live_information/detail/46341"
    if not (
        event.get("group") == "CUTIE STREET"
        and schedule in _urls(event)
        and _day(event) == "2026-11-26"
        and event.get("startTime") == "17:30"
        and "佐野愛花" in str(event.get("eventTitle") or event.get("title") or "")
    ):
        return event
    out = deepcopy(event)
    out["openTime"] = "17:30"
    out["startTime"] = "19:00"
    return out


def repair_sweet_shiraishi_central_fc(event: dict) -> dict:
    """NEWS 92282 is the central FC sale, not a second group-FC sale."""
    article = "https://kawaiilab.asobisystem.com/news/detail/92282"
    if not (
        event.get("group") == "SWEET STEADY"
        and article in [*_urls(event), event.get("discoverySourceUrl")]
        and _day(event) == "2026-12-08"
        and event.get("startTime") == "19:00"
        and event.get("ticketType") == "FC先行"
        and event.get("applyStart") == "2026-10-14T12:00"
        and event.get("applyEnd") == "2026-10-20T23:59"
    ):
        return event
    out = deepcopy(event)
    out["ticketType"] = "KAWAII LAB. FC先行"
    return out


def repair_pia_result_notice(event: dict) -> dict:
    """Attach the verified Pia result time and outage notice to exact offers.

    KAWAII LAB. NEWS 93888 is a delivery notice, not a new reception.  It
    explicitly identifies these already collected offers and their result
    times, so enrich only exact event/window matches and never create a band.
    """
    notice = "https://kawaiilab.asobisystem.com/news/detail/93888"
    facts = (
        ("FRUITS ZIPPER", "2026-12-17", "2026-10-09T12:00", "2026-10-15T23:59", "2026-10-22T20:00"),
        ("FRUITS ZIPPER", "2026-11-24", "2026-10-14T12:00", "2026-10-20T23:59", "2026-10-24T20:00"),
        ("SWEET STEADY", "2026-12-08", "2026-10-14T12:00", "2026-10-20T23:59", "2026-10-24T20:00"),
    )
    matched = next((result for group, day, start, end, result in facts if (
        event.get("group") == group and _day(event) == day
        and event.get("applyStart") == start and event.get("applyEnd") == end
    )), None)
    if not matched:
        title = str(event.get("eventTitle") or event.get("title") or "")
        if (
            event.get("group") == "KAWAII LAB.合同"
            and "5th ANNIVERSARY TOUR" in title
            and event.get("applyStart") == "2026-10-12T18:30"
            and event.get("applyEnd") == "2026-10-18T23:59"
        ):
            matched = "2026-10-23T18:00"
        else:
            return event
    out = deepcopy(event)
    out["resultDate"] = matched
    out["urls"] = list(dict.fromkeys([*_urls(out), notice]))
    out["resultDateSource"] = notice
    out["resultDeliveryNotice"] = "チケットぴあの結果案内メールが届かない可能性あり。マイページで確認"
    return out


def repair_cutie_pacifico_fc_lottery(event: dict) -> dict:
    """Keep the FC lottery on the existing 11/3 Pacifico Hall D event.

    The official article styles ``パシフィコ横浜`` and ``展示ホールD`` as
    separate text nodes.  Older collector output therefore used only the base
    facility and escaped physical-event consolidation.  The same article also
    states the exact post-result purchase deadline.
    """
    if not (
        event.get("group") == "CUTIE STREET"
        and _day(event) == "2026-11-03"
        and CUTIE_PACIFICO_FC_ARTICLE in _urls(event)
    ):
        return event
    out = deepcopy(event)
    out["venue"] = "神奈川県 パシフィコ横浜 展示ホールD"
    if isinstance(out.get("schedule"), list):
        for row in out["schedule"]:
            if isinstance(row, dict) and str(row.get("date") or "")[:10] == "2026-11-03":
                row["venue"] = out["venue"]
    if out.get("resultDate") == "2026-10-27" and out.get("paymentEnd") == "2026-12-02":
        out["paymentEnd"] = "2026-10-28T23:59"
    for offer in out.get("offers") or []:
        if not isinstance(offer, dict):
            continue
        if offer.get("resultDate") == "2026-10-27" and offer.get("paymentEnd") == "2026-12-02":
            offer["paymentEnd"] = "2026-10-28T23:59"
    return out


def repair_candy_oita_eplus_link(offer: dict, group: str, day: str, start_time: str) -> dict:
    """The Fukuoka eplus page is not an application page for Oita.

    Legacy bundled rows can survive as nested offers on both occurrences.
    Correct only this verified general-sale window after occurrence expansion.
    """
    wrong = "https://eplus.jp/sf/detail/3923750001-P0030012P021001"
    correct = "https://eplus.jp/sf/detail/3923750001-P0030013P021001"
    if not (
        group == "CANDY TUNE" and day == "2026-12-01" and start_time == "18:30"
        and str(offer.get("url") or "").split("?")[0] == wrong
        and offer.get("ticketType") == "先着 ★一般発売"
        and offer.get("applyStart") == "2026-09-26T10:00"
        and offer.get("applyEnd") == "2026-11-29T20:00"
        and "eplus" in {offer.get("provider"), offer.get("ticketProvider"), offer.get("primarySource")}
    ):
        return offer
    out = deepcopy(offer)
    out["url"] = correct
    out["urls"] = list(dict.fromkeys([
        correct, *(url for url in (offer.get("urls") or []) if str(url).split("?")[0] != wrong),
    ]))
    for field in ("applicationWindowSource", "deadlineSource"):
        if str(out.get(field) or "").split("?")[0] == wrong:
            out[field] = correct
    out["linkCorrection"] = {"originalUrl": wrong, "sourceUrl": correct,
                             "reason": "2026-12-01 Oita is a separate occurrence from 2026-11-30 Fukuoka"}
    return out


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


def _repair_cutie_hiroshima_pia(event: dict) -> dict:
    """Repair only the verified Hiroshima lot; never merge by title/day alone.

    Official facts: /live_information/detail/40366 and /40367, also
    /news/detail/92733. The old retained lot copied 16:00 to both days and
    lost its per-occurrence venue, creating two extra public performances.
    Keep the acquisition row, ticket history, and original sale URLs intact.
    """
    if event.get("group") != "CUTIE STREET" or not any(
        re.search(r"[?&]lotRlsCd=88970(?:&|$)", value) for value in _urls(event)
    ):
        return event
    facts = {
        "2026-11-14": ("16:00", "18:00", "40366"),
        "2026-11-15": ("14:30", "16:30", "40367"),
    }
    rows = event.get("schedule") or []
    days = [str(row.get("date") or "")[:10] for row in rows if isinstance(row, dict)]
    if not days:
        days = [str(day)[:10] for day in event.get("eventDates") or [event.get("eventDate")]]
    if not days or any(day not in facts for day in days):
        return event
    out = deepcopy(event)
    venue = "広島県 広島グリーンアリーナ"
    out["schedule"] = [{"date": day, "venue": venue,
                        "openTime": facts[day][0], "startTime": facts[day][1]} for day in days]
    out.update({"venue": venue, "venues": [venue],
                "openTime": facts[days[0]][0], "startTime": facts[days[0]][1],
                "officialScheduleUrl": "https://cutiestreet.asobisystem.com/live_information/detail/" + facts[days[0]][2]})
    sources = ["https://cutiestreet.asobisystem.com/live_information/detail/" + facts[day][2] for day in days]
    out["performanceFactSources"] = list(dict.fromkeys([*(out.get("performanceFactSources") or []), *sources]))
    out["urls"] = list(dict.fromkeys([*_urls(out), *sources]))
    return out


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


def _repair_gift_multi_venue(event: dict) -> dict:
    out = deepcopy(event)
    if "GIFT" not in str(event.get("title") or event.get("eventTitle") or "").upper():
        return out
    day = _day(event)
    if day not in {"2026-11-28", "2026-11-29"}:
        return out
    if day == "2026-11-28" and event.get("group") not in {"CANDY TUNE", "MORE STAR"}:
        return out
    if day == "2026-11-29" and event.get("group") != "SWEET STEADY":
        return out
    out["venue"] = GIFT_MULTI_VENUE
    out["venueLocations"] = list(GIFT_LOCATIONS)
    out["schedule"] = [{
        "date": day,
        "venue": GIFT_MULTI_VENUE,
        "venueLocations": list(GIFT_LOCATIONS),
        "openTime": out.get("openTime") or "11:30",
        "startTime": out.get("startTime") or "13:00",
    }]
    out["eventDate"] = day
    out["eventEndDate"] = day
    out["eventDates"] = [day]
    out["eventCount"] = 1
    values = _urls(out)
    if GIFT_OFFICIAL not in values:
        values.append(GIFT_OFFICIAL)
    out["urls"] = values
    out.setdefault("officialScheduleUrl", GIFT_OFFICIAL)
    return out


def _missing_more_star_gift(events: Iterable[dict]) -> dict | None:
    events = list(events)
    if any(
        event.get("group") == "MORE STAR"
        and _day(event) == "2026-11-28"
        and "GIFT" in str(event.get("title") or event.get("eventTitle") or "").upper()
        for event in events
    ):
        return None
    # This correction is an enrichment of a discovered GIFT event, not a
    # stand-alone event source.  Requiring the verified organizer-backed
    # CANDY TUNE row prevents this helper from injecting GIFT into unrelated
    # or partial payloads.
    if not any(
        event.get("group") == "CANDY TUNE"
        and _day(event) == "2026-11-28"
        and "GIFT" in str(event.get("title") or event.get("eventTitle") or "").upper()
        and GIFT_OFFICIAL in _urls(event)
        for event in events
    ):
        return None
    title = "GIFT 〜Girls Idol Festival Tokyo〜"
    return {
        "id": "known-gift-more-star-20261128",
        "group": "MORE STAR",
        "title": title,
        "eventTitle": title,
        "displayTitle": title,
        "eventDate": "2026-11-28",
        "eventEndDate": "2026-11-28",
        "eventDates": ["2026-11-28"],
        "eventCount": 1,
        "venue": GIFT_MULTI_VENUE,
        "venueLocations": list(GIFT_LOCATIONS),
        "openTime": "11:30",
        "startTime": "13:00",
        "schedule": [{
            "date": "2026-11-28",
            "venue": GIFT_MULTI_VENUE,
            "venueLocations": list(GIFT_LOCATIONS),
            "openTime": "11:30",
            "startTime": "13:00",
        }],
        "url": GIFT_OFFICIAL,
        "urls": [GIFT_OFFICIAL],
        "officialScheduleUrl": GIFT_OFFICIAL,
        "sourceType": "official-organizer",
        "sourceChannel": "known-official-correction",
        "primarySource": "official",
        "sourceCandidates": ["official"],
        "eventScope": "external",
        "ticketType": "現在受付なし",
        "applicationStatus": "none",
        "applicationDisplayMode": "schedule-only",
    }


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


def _repair_candy_birthday_facts(event: dict) -> dict:
    """Fill missing occurrence facts only for six verified birthday articles.

    Rechecked 2026-10-20: CANDY NEWS 91529/92278 and 91454/92279.
    A null venue/time must not produce a second concert next to its known
    schedule row. Explicit conflicting facts, other dates and all sale windows
    remain untouched for review instead of being guessed or merged.
    """
    out = deepcopy(event)
    if event.get("group") != "CANDY TUNE":
        return out
    verified = {
        "2026-12-03": ("村川緋杏", ("91529", "92278"), "92965"),
        "2026-12-16": ("福山梨乃", ("91454", "92279"), "92964"),
    }
    day = _day(event)
    if day not in verified:
        return out
    person, articles, central = verified[day]
    source_urls = {"https://candytune.asobisystem.com/news/detail/" + article for article in articles}
    source_urls.add("https://kawaiilab.asobisystem.com/news/detail/" + central)
    actual_urls = {re.sub(r"[?#].*$", "", value).rstrip("/") for value in _urls(event)}
    title = str(event.get("title") or event.get("eventTitle") or "")
    if not (source_urls & actual_urls) or person not in title or "生誕祭" not in title:
        return out
    dates = {str(value)[:10] for value in event.get("eventDates") or []}
    schedule = event.get("schedule") or []
    dates.update(str(row.get("date") or "")[:10] for row in schedule if isinstance(row, dict))
    if dates - {day}:
        return out
    rows = [out, *(row for row in schedule if isinstance(row, dict))]
    for row in rows:
        if row.get("openTime") not in (None, "", "17:30") or row.get("startTime") not in (None, "", "19:00"):
            return out
        venue = str(row.get("venue") or "")
        if venue and not ("SGCホール有明" in venue or "SGC HALL ARIAKE" in venue):
            return out
    facts = {"venue": "東京都 SGCホール有明", "openTime": "17:30", "startTime": "19:00"}
    changed = False
    for row in [out, *(row for row in out.get("schedule") or [] if isinstance(row, dict))]:
        for field, value in facts.items():
            if not row.get(field):
                row[field] = value
                changed = True
    if not changed:
        return out
    out["performanceFactSources"] = list(dict.fromkeys([
        *(out.get("performanceFactSources") or []),
        *("https://candytune.asobisystem.com/news/detail/" + article for article in articles),
    ]))
    return out


def _repair_more_star_seventh(event: dict) -> dict:
    out = deepcopy(event)
    title = str(event.get("title") or event.get("eventTitle") or "")
    if event.get("group") != "MORE STAR" or "単独ライブ 7th STAR" not in title:
        return out
    is_original_fc_reception = (
        event.get("applyStart") == "2026-10-07T18:00"
        or event.get("applyEnd") == "2026-10-12T23:59"
        or event.get("applicationWindowSource") == MORE_STAR_7TH_NEWS
        or (
            event.get("sourcePublishedAt") == "2026-10-07"
            and event.get("discoverySourceUrl") == MORE_STAR_7TH_NEWS
        )
        or title.startswith("2026.10.07")
    )
    out.update({
        "eventDate": MORE_STAR_7TH_DAY,
        "eventEndDate": MORE_STAR_7TH_DAY,
        "eventDates": [MORE_STAR_7TH_DAY],
        "eventCount": 1,
        "venue": "東京都 ヒューリックホール東京",
        "openTime": "17:00",
        "startTime": "18:00",
        "schedule": [{
            "date": MORE_STAR_7TH_DAY,
            "venue": "東京都 ヒューリックホール東京",
            "openTime": "17:00",
            "startTime": "18:00",
        }],
        "officialScheduleUrl": MORE_STAR_7TH_SCHEDULE,
        "sourceType": "official-schedule",
        "sourceChannel": "known-official-correction",
        "primarySource": "official",
        "sourceCandidates": ["official"],
    })
    if is_original_fc_reception:
        out.update({
            "ticketType": "FC先行",
            "applyStart": "2026-10-07T18:00",
            "applyEnd": "2026-10-12T23:59",
            "applicationWindowSource": MORE_STAR_7TH_NEWS,
            "url": MORE_STAR_7TH_NEWS,
        })
    else:
        out.update({
            "ticketType": "KAWAII LAB. FC先行",
            "applyStart": "2026-10-17T18:00",
            "applyEnd": "2026-10-25T23:59",
            "applicationWindowSource": MORE_STAR_7TH_FC,
            "url": MORE_STAR_7TH_FC,
        })
    values = [
        value for value in _urls(out)
        if not (is_original_fc_reception and value == MORE_STAR_7TH_FC)
    ]
    supporting_urls = (
        (MORE_STAR_7TH_NEWS, MORE_STAR_7TH_SCHEDULE)
        if is_original_fc_reception
        else (MORE_STAR_7TH_NEWS, MORE_STAR_7TH_FC, MORE_STAR_7TH_SCHEDULE)
    )
    for value in supporting_urls:
        if value not in values:
            values.append(value)
    out["urls"] = values
    for key in ("sourceStale", "sourceStaleSince", "releaseRetentionReason"):
        out.pop(key, None)
    return out


def _repair_disaster_relief_concert(event: dict) -> dict:
    out = deepcopy(event)
    title = str(event.get("title") or event.get("eventTitle") or "")
    if _day(event) != "2027-01-19" or "災害支援基金コンサート" not in title:
        return out
    original_urls = _urls(out)
    out.update({
        "group": "KAWAII LAB.合同",
        "participants": ["FRUITS ZIPPER", "CANDY TUNE", "SWEET STEADY"],
        "venue": "東京都 日本武道館",
        "openTime": "17:00",
        "startTime": "18:00",
        "ticketType": "チケット受付",
        "applyStart": "2026-10-19T20:00",
        "applyEnd": "2026-11-01T23:59",
        "applicationWindowVerified": True,
        "url": DISASTER_RELIEF_PIA,
        "applicationWindowSource": DISASTER_RELIEF_NEWS,
        "deadlineVerified": True,
        "deadlineSource": DISASTER_RELIEF_NEWS,
        "sourceType": "auto",
        "primarySource": "official",
        "ticketProvider": "pia",
        "sourceCandidates": ["official", "pia"],
    })
    values = list(dict.fromkeys([*original_urls, *_urls(out)]))
    for value in (DISASTER_RELIEF_PIA, DISASTER_RELIEF_NEWS):
        if value not in values:
            values.append(value)
    out["urls"] = values
    return out


def _collapse_disaster_relief_concert(events: list[dict]) -> tuple[list[dict], int]:
    matches = [event for event in events if _day(event) == "2027-01-19" and
               "災害支援基金コンサート" in str(event.get("title") or event.get("eventTitle") or "")]
    if len(matches) < 2:
        return events, 0
    winner = max(matches, key=lambda event: (bool(event.get("sourcePublishedAt")), len(_urls(event))))
    combined_urls = list(dict.fromkeys(url for event in matches for url in _urls(event)))
    winner["urls"] = combined_urls
    result = [event for event in events if event not in matches]
    result.append(winner)
    return result, len(matches) - 1


def _is_candy_online_20261020(event: dict) -> bool:
    return (
        event.get("group") == "CANDY TUNE"
        and _day(event) == CANDY_ONLINE_20261020_DAY
        and event.get("eventCategory") == "online-benefit"
        and "オンライン特典会" in str(event.get("title") or event.get("eventTitle") or "")
    )


def _has_impossible_birthday_year(event: dict) -> bool:
    title = str(event.get("title") or event.get("eventTitle") or "")
    match = re.search(r"生誕祭\s*(20\d{2})", title)
    return bool(match and _day(event)[:4] and _day(event)[:4] != match.group(1))


def _collapse_candy_online_20261020(events: list[dict]) -> tuple[list[dict], int]:
    matches = [event for event in events if _is_candy_online_20261020(event)]
    if len(matches) < 2:
        return events, 0
    all_source_urls = list(dict.fromkeys(url for event in matches for url in _urls(event)))
    if CANDY_ONLINE_20261020_OFFICIAL not in all_source_urls:
        return events, 0
    if not CANDY_ONLINE_20261020_GOODS.intersection(all_source_urls):
        return events, 0

    official_rows = [
        event for event in matches
        if CANDY_ONLINE_20261020_OFFICIAL in _urls(event)
    ]
    base = deepcopy(official_rows[0])
    title = "CANDY TUNE オンライン特典会"
    base.update({
        "id": "known-candy-tune-online-20261020",
        "title": title,
        "eventTitle": title,
        "displayTitle": title,
        "eventDate": CANDY_ONLINE_20261020_DAY,
        "eventEndDate": CANDY_ONLINE_20261020_DAY,
        "eventDates": [CANDY_ONLINE_20261020_DAY],
        "eventCount": 1,
        "startTime": "17:00",
        "venue": "オンライン（SUKISUKI）",
        "url": CANDY_ONLINE_20261020_OFFICIAL,
        "urls": all_source_urls,
        "officialScheduleUrl": CANDY_ONLINE_20261020_OFFICIAL,
        "sourceType": "official-schedule",
        "sourceChannel": "known-official-correction",
        "primarySource": "official",
        "sourceCandidates": ["official", "sukisuki"],
        "sourceRowIds": [str(event.get("id") or "") for event in matches if event.get("id")],
    })

    offers = []
    seen = set()
    for event in matches:
        ticket_type = str(event.get("ticketType") or "").strip()
        goods_urls = [url for url in _urls(event) if url in CANDY_ONLINE_20261020_GOODS]
        if not goods_urls or not ticket_type or ticket_type == "現在受付なし":
            continue
        marker = (
            goods_urls[0],
            ticket_type,
            str(event.get("applyStart") or ""),
            str(event.get("applyEnd") or ""),
        )
        if marker in seen:
            continue
        seen.add(marker)
        offer = {
            "sourceRowId": event.get("id"),
            "provider": "sukisuki",
            "url": goods_urls[0],
            "urls": goods_urls,
            "ticketType": ticket_type,
            "sourceType": event.get("sourceType") or "sukisuki",
            "primarySource": event.get("primarySource") or "sukisuki",
        }
        for field in ("applyStart", "applyEnd", "resultDate", "paymentEnd", "sourcePublishedAt"):
            if event.get(field) is not None:
                offer[field] = deepcopy(event[field])
        offers.append(offer)

    for field in ("applyStart", "applyEnd", "resultDate", "paymentEnd", "ticketProvider"):
        base.pop(field, None)
    base["offers"] = offers
    base["ticketType"] = "複数受付" if len(offers) > 1 else (
        str(offers[0].get("ticketType") or "現在受付なし") if offers else "現在受付なし"
    )
    base["applicationDisplayMode"] = "offers" if offers else "schedule-only"
    base["applicationStatus"] = "offers" if offers else "none"

    first_index = min(index for index, event in enumerate(events) if _is_candy_online_20261020(event))
    output = [event for event in events if not _is_candy_online_20261020(event)]
    output.insert(first_index, base)
    return output, len(matches) - 1


def _collapse_fruits_synergy_20261101(events: list[dict]) -> tuple[list[dict], int]:
    """Keep the initial and additional SYNERGY sales on one online event.

    The official schedule detail fixes one November 1, 18:00 stream. SUKISUKI
    goods 4023 and 4943 are two reception rounds for that stream, not two
    performances. Preserve both windows as offers and require every exact
    identity/source fact so unrelated online benefits stay separate.
    """
    def matches(row: dict) -> bool:
        if row.get("group") != "FRUITS ZIPPER" or _day(row) != FRUITS_SYNERGY_DAY:
            return False
        urls = set(_urls(row))
        if FRUITS_SYNERGY_OFFICIAL in urls:
            # The official SCHEDULE row is intentionally sparse: it currently
            # carries neither the 18:00 start nor SUKISUKI's normalized venue.
            # Its exact stable detail URL is the verified performance identity.
            title = str(row.get("title") or row.get("eventTitle") or "")
            return "4th Anniversary写真集" in title and "オンライン特典会" in title
        return (
            row.get("startTime") == "18:00"
            and row.get("venue") == "オンライン（SUKISUKI）"
            and row.get("eventCategory") == "online-benefit"
            and "SYNERGY" in str(row.get("title") or row.get("eventTitle") or "")
            and bool(FRUITS_SYNERGY_GOODS.intersection(urls))
        )

    rows = [row for row in events if matches(row)]
    all_urls = list(dict.fromkeys(url for row in rows for url in _urls(row)))
    if (len(rows) < 2 or FRUITS_SYNERGY_OFFICIAL not in all_urls
            or not FRUITS_SYNERGY_GOODS.issubset(set(all_urls))):
        return events, 0

    base = deepcopy(next(row for row in rows if FRUITS_SYNERGY_OFFICIAL in _urls(row)))
    offers, seen = [], set()
    for row in rows:
        for receipt in row.get("offers") or [row]:
            goods_urls = [url for url in _urls(receipt) if url in FRUITS_SYNERGY_GOODS]
            if not goods_urls:
                continue
            offer = deepcopy(receipt) if row.get("offers") else {
                "sourceRowId": row.get("id"), "provider": "sukisuki",
                "url": goods_urls[0], "urls": goods_urls,
                "ticketType": row.get("ticketType"),
                "sourceType": row.get("sourceType") or "sukisuki",
                "primarySource": row.get("primarySource") or "sukisuki",
                **{key: deepcopy(row[key]) for key in
                   ("applyStart", "applyEnd", "resultDate", "paymentEnd") if key in row},
            }
            marker = tuple(str(offer.get(key) or "") for key in
                           ("url", "ticketType", "applyStart", "applyEnd", "resultDate", "paymentEnd"))
            if marker not in seen:
                seen.add(marker)
                offers.append(offer)

    title = "FRUITS ZIPPER 4th Anniversary 写真集 『SYNERGY』オンライン特典会"
    base.update({
        "id": "known-fruits-synergy-online-20261101",
        "title": title, "eventTitle": title, "displayTitle": title,
        "eventDate": FRUITS_SYNERGY_DAY, "eventEndDate": FRUITS_SYNERGY_DAY,
        "eventDates": [FRUITS_SYNERGY_DAY], "eventCount": 1,
        "startTime": "18:00", "venue": "オンライン（SUKISUKI）",
        "url": FRUITS_SYNERGY_OFFICIAL, "urls": all_urls,
        "officialScheduleUrl": FRUITS_SYNERGY_OFFICIAL,
        "sourceType": "official-schedule", "sourceChannel": "known-official-correction",
        "primarySource": "official", "sourceCandidates": ["official", "sukisuki"],
        "sourceRowIds": list(dict.fromkeys(str(value) for row in rows for value in
            (row.get("sourceRowIds") or [row.get("id")]) if value)),
        "offers": offers,
        "ticketType": "複数受付" if len(offers) > 1 else offers[0]["ticketType"],
        "applicationDisplayMode": "offers", "applicationStatus": "offers",
    })
    for key in ("applyStart", "applyEnd", "resultDate", "paymentEnd", "ticketProvider"):
        base.pop(key, None)
    first = next(index for index, row in enumerate(events) if matches(row))
    out = [row for row in events if not matches(row)]
    out.insert(first, base)
    return out, len(rows) - 1


def _collapse_sweet_online_20261023(events: list[dict]) -> tuple[list[dict], int]:
    # SUKISUKI 4624/4625 bodies, rechecked 2026-10-20: same October 23
    # 15:00 stream, same seven members and ちょーだいHAPPY！ MV costume.
    # They are the initial and second reception, not two performances. Never
    # generalize this evidence to other goods, dates, groups or start times.
    goods = {"https://sukisuki-shop.com/goods/6500000004624",
             "https://sukisuki-shop.com/goods/6500000004625"}

    def matches(event: dict) -> bool:
        source_goods = {url for url in _urls(event) if "sukisuki-shop.com/goods/" in url}
        return (event.get("group") == "SWEET STEADY" and _day(event) == "2026-10-23"
                and event.get("startTime") == "15:00"
                and event.get("eventCategory") == "online-benefit"
                and bool(source_goods) and source_goods.issubset(goods))

    rows = [event for event in events if matches(event)]
    if len(rows) < 2 or not goods.issubset({url for event in rows for url in _urls(event)}):
        return events, 0
    base = deepcopy(rows[0])
    source_ids = list(dict.fromkeys(str(value) for row in rows for value in
        (row.get("sourceRowIds") or [row.get("id")]) if value))
    offers, seen = [], set()
    for row in rows:
        for receipt in row.get("offers") or [row]:
            receipt_goods = [url for url in _urls(receipt) if url in goods]
            if not receipt_goods:
                continue
            offer = deepcopy(receipt) if row.get("offers") else {
                "sourceRowId": row.get("id"), "provider": "sukisuki",
                "url": receipt_goods[0], "urls": receipt_goods,
                "ticketType": row.get("ticketType"), "sourceType": "sukisuki",
                "primarySource": "sukisuki",
                **{key: deepcopy(row[key]) for key in
                   ("applyStart", "applyEnd", "resultDate", "paymentEnd") if key in row},
            }
            marker = tuple(str(offer.get(key) or "") for key in
                           ("url", "ticketType", "applyStart", "applyEnd", "resultDate", "paymentEnd"))
            if marker not in seen:
                seen.add(marker)
                offers.append(offer)
    base.update({"id": "known-sweet-steady-online-20261023",
                 "eventEndDate": "2026-10-23", "eventDates": ["2026-10-23"], "eventCount": 1,
                 "urls": list(dict.fromkeys(url for row in rows for url in _urls(row))),
                 "sourceRowIds": source_ids, "offers": offers,
                 "sourceChannel": "known-official-correction", "ticketType": "複数受付",
                 "applicationDisplayMode": "offers", "applicationStatus": "offers"})
    for key in ("applyStart", "applyEnd", "resultDate", "paymentEnd", "ticketProvider"):
        base.pop(key, None)
    first = next(index for index, row in enumerate(events) if matches(row))
    out = [row for row in events if not matches(row)]
    out.insert(first, base)
    return out, len(rows) - 1


def _collapse_sweet_ebichu_20261116(events: list[dict]) -> tuple[list[dict], int]:
    # NEWS 91244 confirms one external appearance, not another event for its
    # ended FC reception. Keep the external scope and preserve receipt history.
    article = "https://sweetsteady.asobisystem.com/news/detail/91244"

    def matches(row: dict) -> bool:
        return (row.get("group") == "SWEET STEADY" and _day(row) == "2026-11-16"
                and row.get("startTime") == "18:30" and article in _urls(row))

    rows = [row for row in events if matches(row)]
    if len(rows) < 2:
        return events, 0
    base = deepcopy(next((row for row in rows if row.get("ticketType") == "現在受付なし"), rows[0]))
    offers, seen = [], set()
    for row in rows:
        for receipt in row.get("offers") or [row]:
            if receipt.get("ticketType") in (None, "", "現在受付なし"):
                continue
            offer = deepcopy(receipt) if row.get("offers") else {
                "sourceRowId": row.get("id"), "provider": "official", "url": article, "urls": [article],
                "ticketType": row.get("ticketType"), "primarySource": "official",
                **{key: deepcopy(row[key]) for key in
                   ("applyStart", "applyEnd", "resultDate", "paymentEnd") if key in row},
            }
            marker = tuple(str(offer.get(key) or "") for key in
                           ("url", "ticketType", "applyStart", "applyEnd", "resultDate", "paymentEnd"))
            if marker not in seen:
                seen.add(marker)
                offers.append(offer)
    base.update({"id": "known-sweet-ebichu-20261116", "offers": offers,
                 "sourceRowIds": list(dict.fromkeys(str(value) for row in rows for value in
                     (row.get("sourceRowIds") or [row.get("id")]) if value)),
                 "urls": list(dict.fromkeys(url for row in rows for url in _urls(row))),
                 "sourceChannel": "known-official-correction", "ticketType": "複数受付",
                 "applicationStatus": "offers", "applicationDisplayMode": "offers"})
    for key in ("applyStart", "applyEnd", "resultDate", "paymentEnd", "ticketProvider"):
        base.pop(key, None)
    first = next(index for index, row in enumerate(events) if matches(row))
    out = [row for row in events if not matches(row)]
    out.insert(first, base)
    return out, len(rows) - 1


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
        is_more_star_seventh_current = (
            event.get("group") == "MORE STAR"
            and "単独ライブ 7th STAR" in str(event.get("title") or event.get("eventTitle") or "")
            and _day(event) == MORE_STAR_7TH_DAY
            and event.get("ticketType") == "KAWAII LAB. FC先行"
            and event.get("applyStart") == "2026-10-17T18:00"
            and event.get("applyEnd") == "2026-10-25T23:59"
            and event.get("applicationWindowSource") == MORE_STAR_7TH_FC
        )
        if not (is_resale or is_sweet_second or is_more_star_seventh_current):
            return None
        family = (
            "resale" if is_resale
            else "sweet-fc2" if is_sweet_second
            else "more-star-7th-current"
        )
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
            int(bool(event.get("sourcePublishedAt"))),
            len(str(event.get("title") or "")),
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
        "cutieHiroshimaPiaFixed": 0,
        "candyBirthdayFactsFilled": 0,
        "cutieUpgradeReceptionFixed": 0,
        "cutieSanoUpgradeReceptionFixed": 0,
        "cutieSanoScheduleTimeFixed": 0,
        "cutieSanoUpgradeOfferAdded": 0,
        "sweetShiraishiCentralFcFixed": 0,
        "piaResultNoticesAttached": 0,
        "sweetWinterUpgradeOffersFixed": 0,
        "sweetWinterUpgradeOffersAdded": 0,
        "candyOitaEplusLinkFixed": 0,
        "candyTokyoPresaleAdded": 0,
        "sweetestStoryPerformancesAdded": 0,
        "fruitsJoyFanclubLiveAdded": 0,
        "fruitsJoyFcOfferAdded": 0,
        "kawaiilabFcFreeLiveAdded": 0,
        "kawaiilabFcFreeLiveOffersUpdated": 0,
        "christmasPiaPresaleOffersAdded": 0,
        "staleChristmasRowsRemoved": 0,
        "fmAichiFixed": 0,
        "sweetFcSecondStartFixed": 0,
        "giftMultiVenueFixed": 0,
        "giftMoreStarAdded": 0,
        "moreStarSeventhFixed": 0,
        "disasterReliefConcertFixed": 0,
        "disasterReliefConcertRowsCollapsed": 0,
        "impossibleBirthdayYearRowsRemoved": 0,
        "candyOnline20261020RowsCollapsed": 0,
        "sweetOnline20261023RowsCollapsed": 0,
        "sweetEbichu20261116RowsCollapsed": 0,
        "semanticTicketDuplicatesRemoved": 0,
        "semanticTicketDuplicateIds": [],
        "cutiePacificoFcLotteryFixed": 0,
    }

    for event in source:
        if _has_impossible_birthday_year(event):
            report["impossibleBirthdayYearRowsRemoved"] += 1
            continue
        if _is_cutie_wrong_bundle(event):
            report["cutieWrongPiaBundleRemoved"] += 1
            continue
        if _is_cutie_obsolete_tour_sale(event):
            report["cutieObsoletePiaRowsRemoved"] += 1
            continue
        if _is_redundant_more_star_christmas(event, has_joint_christmas):
            report["staleChristmasRowsRemoved"] += 1
            continue

        current = repair_cutie_upgrade_reception(event)
        if current != event:
            report["cutieUpgradeReceptionFixed"] += 1
        before_sano_upgrade = current
        current = repair_cutie_sano_upgrade_reception(current)
        if current != before_sano_upgrade:
            report["cutieSanoUpgradeReceptionFixed"] += 1
        before_sano_schedule = current
        current = repair_cutie_sano_schedule_time(current)
        if current != before_sano_schedule:
            report["cutieSanoScheduleTimeFixed"] += 1
        before_central_fc = current
        current = repair_sweet_shiraishi_central_fc(current)
        if current != before_central_fc:
            report["sweetShiraishiCentralFcFixed"] += 1
        before_result_notice = current
        current = repair_pia_result_notice(current)
        if current != before_result_notice:
            report["piaResultNoticesAttached"] += 1
        before_pacifico = current
        current = repair_cutie_pacifico_fc_lottery(current)
        if current != before_pacifico:
            report["cutiePacificoFcLotteryFixed"] += 1
        before_oita = current
        current = repair_candy_oita_eplus_link(current, current.get("group"), _day(current), current.get("startTime"))
        if current != before_oita:
            report["candyOitaEplusLinkFixed"] += 1
        before_birthday = current
        current = _repair_candy_birthday_facts(current)
        if current != before_birthday:
            report["candyBirthdayFactsFilled"] += 1
        before_hiroshima = current
        current = _repair_cutie_hiroshima_pia(current)
        if current != before_hiroshima:
            report["cutieHiroshimaPiaFixed"] += 1
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

        before_more_star_seventh = (
            current.get("eventDate"),
            tuple(current.get("eventDates") or []),
            current.get("officialScheduleUrl"),
        )
        current = _repair_more_star_seventh(current)
        if (
            current.get("eventDate"),
            tuple(current.get("eventDates") or []),
            current.get("officialScheduleUrl"),
        ) != before_more_star_seventh:
            report["moreStarSeventhFixed"] += 1

        before_disaster_relief = current
        current = _repair_disaster_relief_concert(current)
        if current != before_disaster_relief:
            report["disasterReliefConcertFixed"] += 1

        before_venue = (current.get("venue"), tuple(current.get("venueLocations") or []))
        current = _repair_gift_multi_venue(current)
        if (current.get("venue"), tuple(current.get("venueLocations") or [])) != before_venue:
            report["giftMultiVenueFixed"] += 1

        out.append(current)

    # Official NEWS 92529 (rechecked 2026-10-20): the FC reception ended
    # October 18, not the November 15 performances. Preserve the two starts
    # separately and retain their expired reception as history.
    story_source = "https://sweetsteady.asobisystem.com/news/detail/92529"
    # Enforce identical scope and truthful occurrence times for the two
    # November 15 Fuji TV public recordings. Previously an inherited 18:00
    # schedule inside the 15:00 record hid the matinee from one view.
    for event in out:
        if (event.get("group") != "SWEET STEADY"
                or story_source not in _urls(event)
                or _day(event) != "2026-11-15"
                or "SWEETEST STORY" not in str(event.get("eventTitle") or event.get("title") or "").upper()):
            continue
        start = str(event.get("startTime") or "")
        times = {"15:00": "14:00", "18:00": "17:00"}
        if start not in times:
            continue
        event["openTime"] = times[start]
        event["eventScope"] = "external"   # Fuji TV program production
        event["eventScopeSourceUrl"] = "https://www.fujitv.co.jp/fujitv/news/20261129.html"
        event["schedule"] = [{
            "date": "2026-11-15", "venue": "東京都 お台場特設会場（フジテレビ湾岸スタジオ）",
            "openTime": times[start], "startTime": start,
        }]
        if str(event.get("ticketType") or "") in {
            "現在受付なし", "FC先行", "SWEET STEADY FC先行",
        }:
            # Both public-recording sessions had the same published FC lottery.
            # A sanitized/expired schedule-only source row must not erase
            # evidence of its historical reception.
            event["ticketType"] = "SWEET STEADY FC先行"
            event["applyStart"] = "2026-10-15T10:00"
            event["applyEnd"] = "2026-10-18T23:59"
            event["applicationWindowVerified"] = True
            event["deadlineVerified"] = True
            event["applicationWindowSource"] = story_source
            event["deadlineSource"] = story_source
    has_sweet_official = any(event.get("group") == "SWEET STEADY" and any(
        value.startswith("https://sweetsteady.asobisystem.com/") for value in _urls(event)
    ) for event in out)
    if has_sweet_official:
        for part, opened, start, feature in (
            (1, "14:00", "15:00", "1755de4497d5965084df7cdde9a129f9"),
            (2, "17:00", "18:00", "ac644c49488eda39a7f361d8bdffb681"),
        ):
            represented = any(event.get("group") == "SWEET STEADY"
                and story_source in _urls(event) and _day(event) == "2026-11-15"
                and (event.get("startTime") == start or any(
                    row.get("date") == "2026-11-15" and row.get("startTime") == start
                    for row in event.get("schedule") or [] if isinstance(row, dict)
                )) for event in out)
            if represented:
                continue
            title = "SWEET STEADYのSWEETEST STORY 第" + str(part) + "部"
            out.append({
                "id": "known-sweetest-story-20261115-part" + str(part),
                "group": "SWEET STEADY", "title": title, "eventTitle": title,
                "eventDate": "2026-11-15", "eventEndDate": "2026-11-15",
                "eventDates": ["2026-11-15"], "eventCount": 1,
                "venue": "東京都 お台場特設会場（フジテレビ湾岸スタジオ）",
                "openTime": opened, "startTime": start,
                "schedule": [{"date": "2026-11-15", "venue": "東京都 お台場特設会場（フジテレビ湾岸スタジオ）",
                              "openTime": opened, "startTime": start}],
                "url": story_source,
                "urls": [story_source, "https://sweetsteady.asobisystem.com/feature/" + feature + "?_normalbrowse_=1"],
                "primarySource": "official", "sourceType": "official",
                "sourceChannel": "known-official-correction", "sourcePublishedAt": "2026-10-13",
                # TV production is not proven KAWAII LAB.-hosted. Preserve
                # the conservative classification instead of widening default UI.
                "eventScope": "external",
                "eventScopeSourceUrl": "https://www.fujitv.co.jp/fujitv/news/20261129.html",
                "ticketType": "SWEET STEADY FC先行",
                "applyStart": "2026-10-15T10:00", "applyEnd": "2026-10-18T23:59",
                "applicationWindowVerified": True, "applicationWindowSource": story_source,
                "deadlineVerified": True, "deadlineSource": story_source,
            })
            report["sweetestStoryPerformancesAdded"] += 1

    # Official autumn-tour TICKET section, checked 2026-10-20: this is a
    # Tokyo-only presale, not the general sales for every tour occurrence.
    candy_tour = "https://candytune.asobisystem.com/feature/candytune_nationwide_tour2026"
    if any(event.get("group") == "CANDY TUNE" and candy_tour in _urls(event) for event in out):
        for day, opened, start in (("2026-12-08", "17:30", "19:00"),
                                   ("2026-12-09", "17:00", "18:30")):
            represented = any(event.get("group") == "CANDY TUNE"
                and _day(event) == day and event.get("applyStart") == "2026-10-17T12:00"
                and event.get("applyEnd") == "2026-10-22T23:59"
                and any(word in str(event.get("ticketType") or "")
                        for word in ("プリセール", "先着")) for event in out)
            if represented:
                continue
            title = "CANDY TUNE JAPAN TOUR 2026 - AUTUMN - CANDY CIRCUS"
            venue = "東京都 東京ガーデンシアター"
            out.append({
                "id": "known-candy-tokyo-presale-" + day.replace("-", ""),
                "group": "CANDY TUNE", "title": title, "eventTitle": title,
                "eventDate": day, "eventEndDate": day, "eventDates": [day], "eventCount": 1,
                "venue": venue, "openTime": opened, "startTime": start,
                "schedule": [{"date": day, "venue": venue, "openTime": opened, "startTime": start}],
                "ticketType": "プリセール（先着先行）",
                "applyStart": "2026-10-17T12:00", "applyEnd": "2026-10-22T23:59",
                "applicationWindowVerified": True, "applicationWindowSource": candy_tour,
                "deadlineVerified": True, "deadlineSource": candy_tour,
                "url": candy_tour, "urls": [candy_tour], "primarySource": "official",
                "sourceType": "official", "sourceChannel": "known-official-correction",
                "eventScope": "kawaii-lab",
            })
            report["candyTokyoPresaleAdded"] += 1

    # Official feature page and NEWS 93491, checked 2026-10-23: one upgrade
    # lottery applies to all four winter-tour performances.  Model it as four
    # offers attached to the existing occurrences, not as another performance.
    sweet_winter = "https://sweetsteady.asobisystem.com/feature/sweetsteady_japanhalltour2026"
    sweet_winter_upgrade = "https://sweetsteady.asobisystem.com/news/detail/93491"
    sweet_winter_atsugi_venue = "神奈川県 厚木市文化会館 大ホール"
    if any(event.get("group") == "SWEET STEADY" and sweet_winter in _urls(event) for event in out):
        # Earlier backfills used the building name while the official
        # performance row includes its hall suffix.  They are the same
        # occurrence; keep the verified official venue spelling so the offer
        # joins that performance instead of creating a duplicate public card.
        for event in out:
            if not (event.get("group") == "SWEET STEADY" and sweet_winter in _urls(event)):
                continue
            venue = sweet_winter_atsugi_venue
            changed = False
            if (_day(event) == "2026-11-13"
                    and event.get("venue") == "神奈川県 厚木市文化会館"):
                event["venue"] = venue
                changed = True
            for occurrence in event.get("schedule") or []:
                if (isinstance(occurrence, dict)
                        and str(occurrence.get("date") or "")[:10] == "2026-11-13"
                        and occurrence.get("venue") == "神奈川県 厚木市文化会館"):
                    occurrence["venue"] = venue
                    changed = True
            if isinstance(event.get("venues"), list):
                normalized = [venue if value == "神奈川県 厚木市文化会館" else value
                              for value in event["venues"]]
                if normalized != event["venues"]:
                    event["venues"] = normalized
                    changed = True
            if changed:
                report["sweetWinterUpgradeOffersFixed"] += 1
        for day, venue, opened, start in (
            ("2026-11-13", sweet_winter_atsugi_venue, "17:30", "18:30"),
            ("2026-12-03", "大阪府 フェニーチェ堺 大ホール", "17:30", "18:30"),
            ("2026-12-06", "愛知県 Niterra日本特殊陶業市民会館フォレストホール", "16:00", "17:00"),
            ("2026-12-18", "東京都 SGC HALL ARIAKE", "17:00", "18:30"),
        ):
            represented = any(
                event.get("group") == "SWEET STEADY" and _day(event) == day
                and event.get("ticketType") == "アップグレード抽選"
                and event.get("applyStart") == "2026-10-23T18:00"
                and event.get("applyEnd") == "2026-10-26T23:59"
                for event in out
            )
            if represented:
                continue
            title = "SWEET STEADY JAPAN TOUR 2026 -WINTER- Snow Sparkle"
            out.append({
                "id": "known-sweet-winter-upgrade-" + day.replace("-", ""),
                "group": "SWEET STEADY", "title": title, "eventTitle": title,
                "eventDate": day, "eventEndDate": day, "eventDates": [day], "eventCount": 1,
                "venue": venue, "openTime": opened, "startTime": start,
                "schedule": [{"date": day, "venue": venue, "openTime": opened, "startTime": start}],
                "ticketType": "アップグレード抽選",
                "applyStart": "2026-10-23T18:00", "applyEnd": "2026-10-26T23:59",
                "applicationWindowVerified": True, "applicationWindowSource": sweet_winter,
                "deadlineVerified": True, "deadlineSource": sweet_winter,
                "url": sweet_winter, "urls": [sweet_winter, sweet_winter_upgrade],
                "primarySource": "official", "sourceType": "official",
                "sourceChannel": "known-official-correction", "sourcePublishedAt": "2026-10-23",
                "eventScope": "kawaii-lab",
            })
            report["sweetWinterUpgradeOffersAdded"] += 1

    gift_more_star = _missing_more_star_gift(out)
    if gift_more_star:
        out.append(gift_more_star)
        report["giftMoreStarAdded"] += 1

    # Official announcement 93201 gives one fixed occurrence but explicitly
    # says application details will follow. Do not invent an application band.
    joy_source = "https://fruitszipper.asobisystem.com/news/detail/93201"
    joy_title = "FRUITS ZIPPER FANCLUB LIVE -じょい！×３-"
    has_fruits_official = any(event.get("group") == "FRUITS ZIPPER" and any(
        value.startswith("https://fruitszipper.asobisystem.com/") for value in _urls(event)
    ) for event in out)
    if has_fruits_official and not any(event.get("group") == "FRUITS ZIPPER" and (
        joy_source in _urls(event)
        or (_day(event) == "2026-11-08" and "FANCLUB LIVE" in str(event.get("title") or "")
            and "じょい" in str(event.get("title") or ""))
    ) for event in out):
        out.append({
            "id": "known-fruits-joy-fanclub-live-20261108",
            "group": "FRUITS ZIPPER", "title": joy_title, "eventTitle": joy_title,
            "eventDate": "2026-11-08", "eventEndDate": "2026-11-08",
            "eventDates": ["2026-11-08"], "eventCount": 1,
            "venue": "東京都 東京ガーデンシアター", "openTime": "13:30", "startTime": "15:00",
            "schedule": [{"date": "2026-11-08", "venue": "東京都 東京ガーデンシアター",
                          "openTime": "13:30", "startTime": "15:00"}],
            "url": joy_source, "urls": [joy_source], "primarySource": "official",
            "sourceType": "official", "sourceChannel": "known-official-correction",
            "sourcePublishedAt": "2026-10-17", "eventScope": "kawaii-lab",
            "ticketType": "現在受付なし", "applicationStatus": "none",
            "applicationDisplayMode": "schedule-only",
        })
        report["fruitsJoyFanclubLiveAdded"] = 1

    # NEWS 93670, checked 2026-10-24, starts the paid-FC member lottery for
    # the already known 11/8 performance.  The generic discovery parser can
    # read the application window but currently quarantines it because it
    # cannot bind the article's Japanese-formatted performance date safely.
    # Add an offer row only when the exact performance is represented; the
    # performance entity builder will merge it into that occurrence.
    joy_fc_source = "https://fruitszipper.asobisystem.com/news/detail/93670"
    has_joy_performance = any(
        event.get("group") == "FRUITS ZIPPER"
        and _day(event) == "2026-11-08"
        and "FANCLUB LIVE" in str(event.get("eventTitle") or event.get("title") or "")
        and "じょい" in str(event.get("eventTitle") or event.get("title") or "")
        for event in out
    )
    has_joy_fc_offer = any(
        event.get("group") == "FRUITS ZIPPER"
        and _day(event) == "2026-11-08"
        and event.get("applyStart") == "2026-10-24T12:00"
        and event.get("applyEnd") == "2026-10-27T23:59"
        and "FC" in str(event.get("ticketType") or "")
        for event in out
    )
    if has_joy_performance and not has_joy_fc_offer:
        out.append({
            "id": "known-fruits-joy-fc-offer-20261108",
            "group": "FRUITS ZIPPER", "title": joy_title, "eventTitle": joy_title,
            "eventDate": "2026-11-08", "eventEndDate": "2026-11-08",
            "eventDates": ["2026-11-08"], "eventCount": 1,
            "venue": "東京都 東京ガーデンシアター", "openTime": "13:30", "startTime": "15:00",
            "schedule": [{"date": "2026-11-08", "venue": "東京都 東京ガーデンシアター",
                          "openTime": "13:30", "startTime": "15:00"}],
            "ticketType": "FC先行",
            "applyStart": "2026-10-24T12:00", "applyEnd": "2026-10-27T23:59",
            "applicationWindowVerified": True, "applicationWindowSource": joy_fc_source,
            "deadlineVerified": True, "deadlineSource": joy_fc_source,
            "applicationStatus": "open", "applicationDisplayMode": "band",
            "url": joy_fc_source, "urls": [joy_source, joy_fc_source],
            "primarySource": "official", "sourceType": "official",
            "sourceChannel": "known-official-correction", "sourcePublishedAt": "2026-10-24",
            "eventScope": "kawaii-lab",
        })
        report["fruitsJoyFcOfferAdded"] = 1

    # NEWS 93573, checked 2026-10-26, opens the seat-upgrade lottery for the
    # already represented Sano birthday performance.  The official schedule
    # row has no ticket fields after refresh and the account portal is not a
    # browsable Pia listing, so retain the verified NEWS provenance explicitly.
    sano_upgrade_source = "https://cutiestreet.asobisystem.com/news/detail/93573"
    sano_upgrade_application = "https://ticket-account.pia.jp/pia/digipoke/list.do"
    has_sano_performance = any(
        event.get("group") == "CUTIE STREET"
        and _day(event) == "2026-11-26"
        and event.get("startTime") == "19:00"
        and "佐野愛花" in str(event.get("eventTitle") or event.get("title") or "")
        for event in out
    )
    has_sano_upgrade_offer = any(
        event.get("group") == "CUTIE STREET"
        and _day(event) == "2026-11-26"
        and event.get("startTime") == "19:00"
        and event.get("ticketType") == "アップグレード抽選"
        and event.get("applyStart") == "2026-10-26T12:00"
        and event.get("applyEnd") == "2026-10-29T23:59"
        for event in out
    )
    if has_sano_performance and not has_sano_upgrade_offer:
        sano_title = "CUTIE STREET 佐野愛花 生誕祭 2026"
        out.append({
            "id": "known-cutie-sano-upgrade-20261126",
            "group": "CUTIE STREET", "title": sano_title, "eventTitle": sano_title,
            "eventDate": "2026-11-26", "eventEndDate": "2026-11-26",
            "eventDates": ["2026-11-26"], "eventCount": 1,
            "venue": "東京都 SGCホール有明", "openTime": "17:30", "startTime": "19:00",
            "schedule": [{"date": "2026-11-26", "venue": "東京都 SGCホール有明",
                          "openTime": "17:30", "startTime": "19:00"}],
            "ticketType": "アップグレード抽選",
            "applyStart": "2026-10-26T12:00", "applyEnd": "2026-10-29T23:59",
            "applicationWindowVerified": True, "applicationWindowSource": sano_upgrade_source,
            "deadlineVerified": True, "deadlineSource": sano_upgrade_source,
            "applicationStatus": "open", "applicationDisplayMode": "band",
            "url": sano_upgrade_application,
            "urls": [sano_upgrade_application, sano_upgrade_source],
            "primarySource": "official", "sourceType": "official",
            "sourceChannel": "known-official-correction", "sourcePublishedAt": "2026-10-26",
            "discoverySourceUrl": sano_upgrade_source, "eventScope": "kawaii-lab",
        })
        report["cutieSanoUpgradeOfferAdded"] = 1


    # Verified 2026-10-24 official announcement.  A four-group FC show must
    # not disappear merely because each official group's news collector has not
    # discovered the newly published article yet.  Match by performance date
    # and title rather than collector-specific article IDs to stay idempotent.
    free_live_sources = [
        (
            "CANDY TUNE FC先行",
            "https://candytune.asobisystem.com/news/detail/93706",
            "https://candytune.asobisystem.com/feature/6eb8e3c96d6f97adcc18f9bebd263edc?_normalbrowse_=1",
        ),
        (
            "SWEET STEADY FC先行",
            "https://sweetsteady.asobisystem.com/news/detail/93708",
            "https://sweetsteady.asobisystem.com/feature/7b23f21ed498eb6e114982bddcb80be0?_normalbrowse_=1",
        ),
        (
            "CUTIE STREET FC先行",
            "https://cutiestreet.asobisystem.com/news/detail/93709",
            "https://cutiestreet.asobisystem.com/feature/b0da2ae3d091956d61d96b98551c772a?_normalbrowse_=1",
        ),
        (
            "MORE STAR FC先行",
            "https://morestar.asobisystem.com/news/detail/93710",
            "https://morestar.asobisystem.com/feature/4887f2d087c4dd1ed6a0f466e46d1b56?_normalbrowse_=1",
        ),
        (
            "KAWAII LAB. FC先行",
            "https://kawaiilab.asobisystem.com/news/detail/93695",
            "https://kawaiilab.asobisystem.com/feature/952c3d505aa47ae5719a9a05de62fff8?_normalbrowse_=1",
        ),
    ]
    free_live_source = free_live_sources[-1][1]
    free_live_urls = list(dict.fromkeys(
        value for _, article, application in free_live_sources
        for value in (article, application)
    ))
    free_live_offers = [
        {
            "sourceRowId": "known-kawaiilab-fc-free-live-20261106-" + label.lower().replace(" ", "-"),
            "provider": "official",
            "ticketType": label,
            "url": application,
            "urls": [application, article],
            "applyStart": "2026-10-24T12:00",
            "applyEnd": "2026-10-26T23:59",
            "applicationWindowVerified": True,
            "applicationWindowSource": article,
            "deadlineVerified": True,
            "deadlineSource": article,
            "applicationStatus": "open",
            "sourceType": "official",
            "primarySource": "official",
            "sourceChannel": "known-official-correction",
            "sourcePublishedAt": "2026-10-24",
        }
        for label, article, application in free_live_sources
    ]
    free_live_title = "KAWAII LAB. ファンクラブ限定フリーライブ"
    free_live_day = "2026-11-06"
    # Run this site-wide backfill only on a complete multi-group calendar.
    # Unit tests and partial collector snapshots must remain untouched.
    has_all_participants = {"CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR"}.issubset(
        {str(event.get("group") or "") for event in out}
    )
    # Canonicalize every exact acquisition row, including the abbreviated
    # central official-schedule row.  Updating only the first NEWS-derived row
    # lets later schedule rendering select "KAWAII LAB." again.
    for event in out:
        event_days = {str(event.get("eventDate") or "")[:10], *(
            str(day)[:10] for day in (event.get("eventDates") or [])
        )}
        title = str(event.get("eventTitle") or event.get("title") or "")
        if (
            free_live_day in event_days
            and str(event.get("group") or "") in {"KAWAII LAB.", "KAWAII LAB.合同"}
            and "東京ガーデンシアター" in str(event.get("venue") or "")
            and (
                "ファンクラブ限定フリーライブ" in title
                or any(url.startswith("https://kawaiilab.asobisystem.com/") for url in _urls(event))
            )
        ):
            event["group"] = "KAWAII LAB.合同"
            event["title"] = free_live_title
            event["eventTitle"] = free_live_title

    free_live_matches = [event for event in out if
        free_live_day in {str(event.get("eventDate") or "")[:10], *(
            str(day)[:10] for day in (event.get("eventDates") or [])
        )}
        and "ファンクラブ限定フリーライブ" in str(
            event.get("eventTitle") or event.get("title") or ""
        )
    ]
    if has_all_participants and not free_live_matches:
        free_live_matches = [{
            "id": "known-kawaiilab-fc-free-live-20261106",
            "group": "KAWAII LAB.合同",
            "participants": ["CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR"],
            "title": free_live_title,
            "eventTitle": free_live_title,
            "eventDate": free_live_day,
            "eventEndDate": free_live_day,
            "eventDates": [free_live_day],
            "eventCount": 1,
            "venue": "東京都 東京ガーデンシアター",
            "openTime": "16:30",
            "startTime": "18:00",
            "schedule": [{"date": free_live_day,
                          "venue": "東京都 東京ガーデンシアター",
                          "openTime": "16:30", "startTime": "18:00"}],
            "url": free_live_source,
            "urls": free_live_urls,
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "sourceType": "official",
            "primarySource": "official",
            "sourceChannel": "known-official-correction",
            "sourcePublishedAt": "2026-10-24",
            "eventScope": "kawaii-lab",
        }]
        out.extend(free_live_matches)
        report["kawaiilabFcFreeLiveAdded"] = 1

    if has_all_participants and free_live_matches:
        target = free_live_matches[0]
        before = deepcopy(target)
        target.update({
            "group": "KAWAII LAB.合同",
            "participants": ["CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR"],
            "title": free_live_title,
            "eventTitle": free_live_title,
            "url": free_live_source,
            "urls": free_live_urls,
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "applicationDisplayMode": "offers",
            "offers": deepcopy(free_live_offers),
            "primarySource": "official",
            "eventScope": "kawaii-lab",
        })
        for field in (
            "applyStart", "applyEnd", "applicationWindowVerified", "applicationWindowSource",
            "deadlineVerified", "deadlineSource",
        ):
            target.pop(field, None)
        if target != before and report["kawaiilabFcFreeLiveAdded"] == 0:
            report["kawaiilabFcFreeLiveOffersUpdated"] = 1


    # Ticket Pia's live sales page, checked 2026-10-24, lists one current
    # Playguide presale for both Christmas SESSION performances.  Keep the
    # physical performances separate and attach the same verified reception to
    # each occurrence.  This is intentionally independent from the older FC
    # article so a lagging ticket collector cannot hide a closing reception.
    christmas_offer = {
        "sourceRowId": "known-kawaiilab-christmas-pia-presale3-2026",
        "provider": "pia",
        "ticketProvider": "pia",
        "ticketType": "プレリザーブ3次",
        "url": CHRISTMAS_SESSION_PIA,
        "urls": [CHRISTMAS_SESSION_PIA, CHRISTMAS_SESSION_OFFICIAL],
        "applyStart": "2026-10-21T18:00",
        "applyEnd": "2026-10-25T23:59",
        "resultDate": "2026-10-29T18:00",
        "applicationWindowVerified": True,
        "applicationWindowSource": CHRISTMAS_SESSION_PIA,
        "deadlineVerified": True,
        "deadlineSource": CHRISTMAS_SESSION_PIA,
        "resultDateSource": CHRISTMAS_SESSION_PIA,
        "applicationStatus": "open",
        "sourceType": "pia",
        "primarySource": "pia",
        "sourceChannel": "known-official-correction",
    }
    for event in out:
        title = str(event.get("eventTitle") or event.get("title") or "")
        event_days = {str(event.get("eventDate") or "")[:10], *(
            str(day)[:10] for day in (event.get("eventDates") or [])
        )}
        if not (
            event.get("group") == "KAWAII LAB.合同"
            and "Christmas SESSION 2026" in title
            and event_days & CHRISTMAS_SESSION_DAYS
        ):
            continue
        offers = [deepcopy(offer) for offer in (event.get("offers") or []) if isinstance(offer, dict)]
        if any(
            str(offer.get("url") or "").split("?")[0] == CHRISTMAS_SESSION_PIA
            or offer.get("sourceRowId") == christmas_offer["sourceRowId"]
            for offer in offers
        ):
            continue
        offers.append(deepcopy(christmas_offer))
        event["offers"] = offers
        event["applicationDisplayMode"] = "offers"
        event["urls"] = list(dict.fromkeys([*_urls(event), CHRISTMAS_SESSION_OFFICIAL, CHRISTMAS_SESSION_PIA]))
        report["christmasPiaPresaleOffersAdded"] += 1

    out, candy_online_removed = _collapse_candy_online_20261020(out)
    report["candyOnline20261020RowsCollapsed"] = candy_online_removed

    out, fruits_synergy_removed = _collapse_fruits_synergy_20261101(out)
    report["fruitsSynergy20261101RowsCollapsed"] = fruits_synergy_removed

    out, disaster_relief_removed = _collapse_disaster_relief_concert(out)
    report["disasterReliefConcertRowsCollapsed"] = disaster_relief_removed

    out, sweet_online_removed = _collapse_sweet_online_20261023(out)
    report["sweetOnline20261023RowsCollapsed"] = sweet_online_removed

    out, sweet_ebichu_removed = _collapse_sweet_ebichu_20261116(out)
    report["sweetEbichu20261116RowsCollapsed"] = sweet_ebichu_removed

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
