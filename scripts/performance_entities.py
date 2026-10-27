#!/usr/bin/env python3
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

from schedule_scope import HOSTED, infer_event_scope
from apply_known_schedule_corrections import repair_candy_oita_eplus_link


SPECIAL_CATEGORIES = {"release-event", "large-benefit"}
OUT_OF_SCOPE_SOLO_GROUPS = {"KAWAII LAB. MATES", "KAWAII LAB. SOUTH"}
ONLINE_RE = re.compile(r"オンライン(?:特典会|サイン会)", re.I)
TICKET_FIELDS = (
    "ticketType",
    "ticketProvider",
    "saleFamily",
    "applyStart",
    "applyEnd",
    "resultDate",
    "resultDateSource",
    "resultDeliveryNotice",
    "paymentEnd",
    "applicationStatus",
    "applicationWindowVerified",
    "deadlineVerified",
    "applicationDisplayMode",
    "applicationWindowSource",
    "deadlineSource",
    "sourceType",
    "sourceChannel",
    "primarySource",
    "sourcePublishedAt",
    "sourceObservedAt",
)
TOP_LEVEL_TICKET_FIELDS = {
    "ticketType",
    "ticketProvider",
    "saleFamily",
    "applyStart",
    "applyEnd",
    "resultDate",
    "paymentEnd",
    "applicationStatus",
    "applicationWindowVerified",
    "deadlineVerified",
    "applicationDisplayMode",
    "applicationWindowSource",
    "deadlineSource",
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _day(value: Any) -> str:
    return str(value or "")[:10]


def _time(value: Any) -> str:
    value = re.sub(r"\s+", "", str(value or "")).strip()
    if re.fullmatch(r"(?:(?:開場|開演|開始|時間|時刻|開場時間|開演時間))?(?:未定|未発表|調整中|確認中|不明)|[-－―]+|--:--|TBD", value, re.I):
        return ""
    match = re.fullmatch(r"(\d{1,2})[:：](\d{2})", value)
    if match and int(match.group(1)) < 24 and int(match.group(2)) < 60:
        return f"{int(match.group(1)):02d}:{match.group(2)}"
    return value


def _venue_key(value: Any) -> str:
    text = _text(value).casefold()
    text = re.sub(r"^(?:北海道|東京都|京都府|大阪府|.{2,3}県)\s*", "", text)
    key = re.sub(r"[\s　!！・･|｜\-–—_\[\]()（）『』「」,，.。]", "", text)
    # The venue owner uses both names for one physical hall.
    if key in {"sgchallariake", "sgcホール有明"}:
        return "sgcホール有明"
    return key


def _title_key(event: dict[str, Any]) -> str:
    text = _text(event.get("eventTitle") or event.get("displayTitle") or event.get("title")).casefold()
    text = re.sub(r"^(?:20\d{2}[.\/-]\d{1,2}[.\/-]\d{1,2}|20\d{2}年\d{1,2}月\d{1,2}日)\s*", "", text)
    return re.sub(r"[\s　!！・|｜\-–—_\[\]()（）『』「」]", "", text)


def _tour_key(event: dict[str, Any]) -> str:
    value = _text(event.get("officialTourUrl"))
    if not value:
        return ""
    return re.sub(r"[?#].*$", "", value).rstrip("/").casefold()


def _is_online(event: dict[str, Any]) -> bool:
    return event.get("eventCategory") == "online-benefit" or bool(
        ONLINE_RE.search(_text(event.get("displayTitle") or event.get("eventTitle") or event.get("title")))
    )


def _is_regular_hosted(event: dict[str, Any]) -> bool:
    if event.get("eventCategory") in SPECIAL_CATEGORIES:
        return False
    if event.get("entityType") == "special-event":
        return False
    if _is_online(event):
        return False
    return infer_event_scope(event) == HOSTED


def _unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return result


def _event_urls(event: dict[str, Any]) -> list[str]:
    return _unique_strings([event.get("url"), *(event.get("urls") or [])])


def _occurrences(event: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    schedule = event.get("schedule")
    if isinstance(schedule, list):
        for item in schedule:
            if not isinstance(item, dict) or not _day(item.get("date")):
                continue
            rows.append(
                {
                    "date": _day(item.get("date")),
                    "venue": _text(item.get("venue") or event.get("venue")),
                    "openTime": _time(item.get("openTime") or event.get("openTime")),
                    "startTime": _time(item.get("startTime") or event.get("startTime")),
                }
            )
    if rows:
        return rows

    dates = event.get("eventDates")
    if isinstance(dates, list):
        for value in dates:
            day = _day(value)
            if day:
                rows.append(
                    {
                        "date": day,
                        "venue": _text(event.get("venue")),
                        "openTime": _time(event.get("openTime")),
                        "startTime": _time(event.get("startTime")),
                    }
                )
    if rows:
        return rows

    day = _day(event.get("eventDate"))
    if day:
        rows.append(
            {
                "date": day,
                "venue": _text(event.get("venue")),
                "openTime": _time(event.get("openTime")),
                "startTime": _time(event.get("startTime")),
            }
        )
    return rows


def _reconcile_verified_christmas_session(event: dict[str, Any]) -> None:
    """Normalize only the source-identified joint Christmas performances.

    The central upgrade article was acquired once for each participant; those
    are not seven different concerts. Keep the acquisition rows and their
    offers intact, but give their public copies the joint performance identity.
    Facts rechecked against central NEWS 87775 and CANDY TUNE NEWS 85442 on
    2026-10-20. In particular central schedule 44572 inherited Day1's times.
    """
    source = "https://kawaiilab.asobisystem.com/news/detail/87775"
    day2_source = "https://kawaiilab.asobisystem.com/live_information/detail/44572"
    known_urls = {
        source,
        "https://kawaiilab.asobisystem.com/live_information/detail/44571",
        day2_source,
        "https://candytune.asobisystem.com/news/detail/85442",
    }
    urls = {re.sub(r"[?#].*$", "", value).rstrip("/") for value in _event_urls(event)}
    title = _title_key(event)
    occurrences = _occurrences(event)
    days = {row["date"] for row in occurrences}
    if not (urls & known_urls) or "christmassession2026" not in title:
        return
    if not days or not days <= {"2026-12-12", "2026-12-13"}:
        return
    if any("有明アリーナ" not in row["venue"] for row in occurrences):
        return
    # Preserve distinct starts unless this is the specifically identified stale
    # central Day2 schedule row. Never merge arbitrary same-day performances.
    if (day2_source in urls and days == {"2026-12-13"}
            and all((row["openTime"], row["startTime"]) == ("15:00", "17:00") for row in occurrences)):
        event["openTime"], event["startTime"] = "14:00", "16:00"
        for row in occurrences:
            row["openTime"], row["startTime"] = "14:00", "16:00"
        event["schedule"] = occurrences
    event["group"] = "KAWAII LAB.合同"
    event["participants"] = [
        "FRUITS ZIPPER", "CANDY TUNE", "SWEET STEADY", "CUTIE STREET",
        "MORE STAR", "KAWAII LAB. MATES", "KAWAII LAB. SOUTH",
    ]
    for field in ("title", "eventTitle", "displayTitle"):
        event[field] = "KAWAII LAB. Christmas SESSION 2026"
    event["performanceFactSources"] = _unique_strings([
        *(event.get("performanceFactSources") or []), source,
        "https://candytune.asobisystem.com/news/detail/85442",
    ])


def _reconcile_verified_fc_free_live(event: dict[str, Any]) -> None:
    """Keep the verified Nov 6 joint-show title through source consolidation.

    The central official schedule currently labels this occurrence only
    KAWAII LAB.  The official NEWS article gives the full event name.
    Canonicalize every exact joint occurrence before choosing a preferred base
    so an official-schedule row cannot overwrite the more specific title.
    """
    canonical = "KAWAII LAB. ファンクラブ限定フリーライブ"
    source = "https://kawaiilab.asobisystem.com/news/detail/93695"
    if _text(event.get("group")) not in {
        "KAWAII LAB.", "KAWAII LAB.合同",
        "CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR",
    }:
        return
    occurrences = _occurrences(event)
    if not any(
        row["date"] == "2026-11-06"
        and "東京ガーデンシアター" in _text(row.get("venue") or event.get("venue"))
        for row in occurrences
    ):
        return
    title = _text(event.get("eventTitle") or event.get("title"))
    urls = _event_urls(event)
    if "ファンクラブ限定フリーライブ" not in title and not any(
        value.startswith("https://kawaiilab.asobisystem.com/") for value in urls
    ):
        return
    # All four member-group INFORMATION pages refer to this same concert.
    # Keep their different FC receptions as offers; only the SHOW is joint.
    event["group"] = "KAWAII LAB.合同"
    event["participants"] = ["CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR"]
    for field in ("title", "eventTitle", "displayTitle"):
        event[field] = canonical
    event["performanceFactSources"] = _unique_strings([
        *(event.get("performanceFactSources") or []), source,
    ])


def _reconcile_verified_fifth_anniversary(event: dict[str, Any]) -> None:
    """Use official joint NEWS facts for the 2027 KAWAII LAB. fifth tour.

    Group SCHEDULE pages mirror the same joint performance under their own
    group headings. They must never become separate concerts. Limit this
    reconciliation to the explicitly verified 10 dates and venue identities;
    do not guess about another joint event or another time slot.
    """
    title = _text(event.get("eventTitle") or event.get("displayTitle") or event.get("title"))
    if not re.search(r"KAWAII\s*LAB\.?\s*5th\s*ANNIVERSARY\s*TOUR", title, re.I):
        return
    if _text(event.get("group")) not in {
        "KAWAII LAB.合同", "FRUITS ZIPPER", "CANDY TUNE",
        "SWEET STEADY", "CUTIE STREET", "MORE STAR",
    }:
        return
    if not _is_regular_hosted(event):
        return

    facts = {
        "2027-01-30": ("宮城セキスイハイムスーパーアリーナ", "15:00", "17:00"),
        "2027-01-31": ("宮城セキスイハイムスーパーアリーナ", "14:00", "16:00"),
        "2027-02-13": ("Kアリーナ横浜", "15:00", "17:00"),
        "2027-02-14": ("Kアリーナ横浜", "14:00", "16:00"),
        "2027-02-20": ("IGアリーナ", "15:00", "17:00"),
        "2027-02-21": ("IGアリーナ", "14:00", "16:00"),
        "2027-03-20": ("GLION ARENA KOBE", "15:00", "17:00"),
        "2027-03-21": ("GLION ARENA KOBE", "14:00", "16:00"),
        "2027-04-03": ("マリンメッセ福岡A館", "15:00", "17:00"),
        "2027-04-04": ("マリンメッセ福岡A館", "14:00", "16:00"),
    }
    def same_venue(actual: str, confirmed: str) -> bool:
        key, official = _venue_key(actual), _venue_key(confirmed)
        return bool(key and official and (
            key == official or
            (min(len(key), len(official)) >= 7 and (key in official or official in key))
        ))

    occurrences = _occurrences(event)
    if not occurrences:
        return
    for row in occurrences:
        fact = facts.get(row["date"])
        if not fact or not same_venue(row["venue"], fact[0]):
            return

    old_group = _text(event.get("group"))
    source = "https://kawaiilab.asobisystem.com/news/detail/92410"
    event["group"] = "KAWAII LAB.合同"
    participants = [
        "FRUITS ZIPPER", "CANDY TUNE", "SWEET STEADY",
        "CUTIE STREET", "MORE STAR",
    ]
    if len(occurrences) == 1 and occurrences[0]["date"] == "2027-04-03":
        participants.remove("SWEET STEADY")
    event["participants"] = participants
    for field in ("title", "eventTitle", "displayTitle"):
        event[field] = "KAWAII LAB. 5th ANNIVERSARY TOUR"
    normalized = []
    for row in occurrences:
        verified_venue, opened, start = facts[row["date"]]
        normalized.append(dict(row, venue=verified_venue, openTime=opened, startTime=start))
    event["schedule"] = normalized
    if len(normalized) == 1:
        event["venue"] = normalized[0]["venue"]
        event["openTime"] = normalized[0]["openTime"]
        event["startTime"] = normalized[0]["startTime"]
    else:
        event.pop("openTime", None)
        event.pop("startTime", None)
    event["performanceFactSources"] = _unique_strings([
        *(event.get("performanceFactSources") or []), source,
    ])
    event["urls"] = _unique_strings([*_event_urls(event), source])


def _time_match_keys(event: dict[str, Any], occurrence: dict[str, Any]) -> list[str]:
    group = _text(event.get("group"))
    day = _day(occurrence.get("date"))
    venue = _venue_key(occurrence.get("venue") or event.get("venue"))
    base = "|".join((group, day, venue))
    result = [base]
    tour = _tour_key(event)
    if tour:
        result.append(base + "|tour:" + tour)
    title = _title_key(event)
    if title:
        result.append(base + "|title:" + title)
    return result


def _reconcile_occurrence_times(records: list[dict[str, Any]]) -> None:
    # A missing venue is not evidence of a second show. Fill it only when
    # the same artist/date has exactly one known venue.
    venues: dict[tuple[str, str], dict[str, str]] = {}
    for record in records:
        event, occurrence = record["event"], record["occurrence"]
        venue = _text(occurrence.get("venue") or event.get("venue"))
        if venue:
            venues.setdefault((_text(event.get("group")), _day(occurrence.get("date"))), {})[_venue_key(venue)] = venue
    for record in records:
        event, occurrence = record["event"], record["occurrence"]
        if not _text(occurrence.get("venue") or event.get("venue")):
            possible = venues.get((_text(event.get("group")), _day(occurrence.get("date"))), {})
            if len(possible) == 1:
                occurrence["venue"] = next(iter(possible.values()))
    starts: dict[str, set[str]] = {}
    opens: dict[str, set[str]] = {}
    for record in records:
        event = record["event"]
        occurrence = record["occurrence"]
        start = _time(occurrence.get("startTime") or event.get("startTime"))
        opened = _time(occurrence.get("openTime") or event.get("openTime"))
        for key in _time_match_keys(event, occurrence):
            if start:
                starts.setdefault(key, set()).add(start)
            if opened:
                opens.setdefault(key, set()).add(opened)

    for record in records:
        event = record["event"]
        occurrence = record["occurrence"]
        keys = _time_match_keys(event, occurrence)
        start_values = sorted({value for key in keys for value in starts.get(key, set())})
        open_values = sorted({value for key in keys for value in opens.get(key, set())})
        current_start = _time(occurrence.get("startTime") or event.get("startTime"))
        current_open = _time(occurrence.get("openTime") or event.get("openTime"))
        if not current_start and len(start_values) == 1:
            occurrence["startTime"] = start_values[0]
            current_start = start_values[0]
        elif current_start and current_open and current_start == current_open:
            credible = [value for value in start_values if value != current_open]
            if len(credible) == 1:
                occurrence["startTime"] = credible[0]
        if not current_open and len(open_values) == 1:
            occurrence["openTime"] = open_values[0]


def _performance_key(event: dict[str, Any], occurrence: dict[str, Any]) -> str:
    group = _text(event.get("group"))
    day = _day(occurrence.get("date"))
    start = _time(occurrence.get("startTime") or event.get("startTime"))
    if day and start:
        # Same artist/date/start can still be two different venues. Conversely,
        # different spellings of the same venue normalize to one key.
        return "|".join((group, day, "time", start, _venue_key(occurrence.get("venue") or event.get("venue"))))
    return "|".join(
        (
            group,
            day,
            "fallback",
            _venue_key(occurrence.get("venue") or event.get("venue")),
            _title_key(event),
        )
    )


def _provider_id(event: dict[str, Any]) -> str:
    for value in (event.get("ticketProvider"), event.get("primarySource"), event.get("sourceType")):
        token = _text(value).casefold()
        if token in {"pia", "lawson", "eplus", "official", "resale", "sukisuki", "kawaii-store", "rakuten", "hmv", "tower", "ticketdive"}:
            return token
    for url in _event_urls(event):
        host = urlparse(url).netloc.casefold()
        if "pia.jp" in host:
            return "pia"
        if "l-tike.com" in host:
            return "lawson"
        if "eplus.jp" in host:
            return "eplus"
        if "sukisuki" in host:
            return "sukisuki"
        if "ticketdive.com" in host:
            return "ticketdive"
    return "official"


def _is_offer(event: dict[str, Any]) -> bool:
    if event.get("ticketGuardRejected") is True:
        return False
    ticket_type = _text(event.get("ticketType"))
    if not ticket_type or ticket_type == "現在受付なし":
        return False
    return bool(_event_urls(event))


def _offer_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    if not _is_offer(event):
        return None
    offer: dict[str, Any] = {
        "sourceRowId": event.get("id"),
        "provider": _provider_id(event),
        "url": event.get("url"),
        "urls": _event_urls(event),
    }
    for field in TICKET_FIELDS:
        value = deepcopy(event.get(field))
        if value is not None:
            offer[field] = value
    return offer


def _offer_key(offer: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        _text(offer.get(field))
        for field in ("provider", "ticketType", "applyStart", "applyEnd", "resultDate", "paymentEnd", "url")
    )


def _collapse_official_fc_aliases(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge one FC application recorded under generic and branded labels.

    Require a shared explicit source/application URL and the same *complete*
    application period. Two named fanclubs, separate URLs, or separate rounds
    remain different offers even when their sale periods overlap.
    """
    def fc_type(value: Any) -> str:
        label = _text(value)
        if "アップグレード" in label or "リセール" in label:
            return ""
        return label if re.search(r"(?:FC|ファンクラブ).*?先行", label, re.I) else ""

    def generic(value: str) -> bool:
        return bool(re.fullmatch(r"(?:FC(?:会員)?先行|ファンクラブ(?:会員)?先行)", value, re.I))

    def urls(offer: dict[str, Any]) -> set[str]:
        output = set()
        for raw in [offer.get("url"), *(offer.get("urls") or [])]:
            url = _text(raw)
            if not re.match(r"^https?://", url, re.I):
                continue
            parsed = urlparse(url)
            # The source identity includes all meaningful application parameters.
            query = "&".join(sorted(part for part in parsed.query.split("&") if part and
                                    not re.match(r"(?i)(?:utm_[^=]*|fbclid|gclid|yclid)=", part)))
            output.add(parsed.scheme.lower() + "://" + parsed.netloc.lower() +
                       parsed.path.rstrip("/") + ("?" + query if query else ""))
        return output

    collapsed: list[dict[str, Any]] = []
    for offer in offers:
        current_type = fc_type(offer.get("ticketType"))
        current_start = _text(offer.get("applyStart"))
        current_end = _text(offer.get("applyEnd"))
        current_urls = urls(offer)
        matched = None
        if current_type and current_start and current_end and current_urls:
            for index, previous in enumerate(collapsed):
                previous_type = fc_type(previous.get("ticketType"))
                if not previous_type:
                    continue
                if (current_start, current_end) != (_text(previous.get("applyStart")), _text(previous.get("applyEnd"))):
                    continue
                if not current_urls.intersection(urls(previous)):
                    continue
                if (current_type == previous_type or generic(current_type) or generic(previous_type)):
                    matched = index
                    break
        if matched is None:
            collapsed.append(offer)
            continue
        previous = collapsed[matched]
        # A qualified FC name carries more useful information than generic
        # FC先行. Preserve *both* official links and richer metadata.
        current_score = (not generic(current_type), sum(v not in (None, "", [], {}) for v in offer.values()))
        previous_type = fc_type(previous.get("ticketType"))
        previous_score = (not generic(previous_type), sum(v not in (None, "", [], {}) for v in previous.values()))
        preferred, supplement = (offer, previous) if current_score > previous_score else (previous, offer)
        merged = deepcopy(preferred)
        merged["urls"] = _unique_strings([*(_event_urls(preferred)), *(_event_urls(supplement))])
        for field, value in supplement.items():
            if merged.get(field) in (None, "", [], {}) and value not in (None, "", [], {}):
                merged[field] = deepcopy(value)
        collapsed[matched] = merged
    return collapsed


def _base_score(event: dict[str, Any]) -> tuple[int, int, int, int, str]:
    source_type = _text(event.get("sourceType")).casefold()
    primary = _text(event.get("primarySource")).casefold()
    official = 1 if primary == "official" else 0
    schedule_source = 1 if source_type == "official-schedule" else 0
    no_offer = 1 if not _is_offer(event) else 0
    schedule_size = len(event.get("schedule") or []) if isinstance(event.get("schedule"), list) else 0
    return schedule_source, official, no_offer, schedule_size, _text(event.get("id"))


def _preferred_base(records: list[dict[str, Any]]) -> dict[str, Any]:
    return max((record["event"] for record in records), key=_base_score)


def _canonical_entity(key: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    base = deepcopy(_preferred_base(records))
    occurrence = max(
        (record["occurrence"] for record in records),
        key=lambda item: (
            int(bool(_text(item.get("venue")))),
            int(bool(_time(item.get("startTime")))),
            int(bool(_time(item.get("openTime")))),
        ),
    )
    day = _day(occurrence.get("date"))
    venue = _text(occurrence.get("venue") or base.get("venue"))
    opened = _time(occurrence.get("openTime") or base.get("openTime"))
    start = _time(occurrence.get("startTime") or base.get("startTime"))

    source_ids = _unique_strings(
        [
            *(value for record in records for value in (record["event"].get("sourceRowIds") or [])),
            *(record["event"].get("id") for record in records),
        ]
    )
    all_urls = _unique_strings(
        [value for record in records for value in _event_urls(record["event"])]
    )
    official_urls = [
        value
        for record in records
        if _text(record["event"].get("primarySource")).casefold() == "official"
        for value in _event_urls(record["event"])
    ]

    offers: list[dict[str, Any]] = []
    seen_offers: set[tuple[str, ...]] = set()
    for record in records:
        event = record["event"]
        existing = event.get("offers")
        if isinstance(existing, list):
            for raw_offer in existing:
                if not isinstance(raw_offer, dict):
                    continue
                offer = deepcopy(raw_offer)
                offer = repair_candy_oita_eplus_link(offer, base.get("group"), day, start)
                marker = _offer_key(offer)
                if marker not in seen_offers:
                    offers.append(offer)
                    seen_offers.add(marker)
        offer = _offer_from_event(event)
        if offer is not None:
            offer = repair_candy_oita_eplus_link(offer, base.get("group"), day, start)
            marker = _offer_key(offer)
            if marker not in seen_offers:
                offers.append(offer)
                seen_offers.add(marker)

    offers = _collapse_official_fc_aliases(offers)

    for field in TOP_LEVEL_TICKET_FIELDS:
        base.pop(field, None)
    base["id"] = "performance-" + re.sub(r"[^0-9A-Za-z]+", "-", key).strip("-")[:120]
    base["entityType"] = "performance"
    base["performanceEntityVersion"] = 1
    base["performanceKey"] = key
    base["sourceRowIds"] = source_ids
    base["offers"] = offers
    base["eventDate"] = day
    base["eventEndDate"] = day
    base["eventDates"] = [day] if day else []
    base["eventCount"] = 1
    base["venue"] = venue or None
    if opened:
        base["openTime"] = opened
    else:
        base.pop("openTime", None)
    if start:
        base["startTime"] = start
    else:
        base.pop("startTime", None)
    base["schedule"] = [
        {
            "date": day,
            "venue": venue or None,
            **({"openTime": opened} if opened else {}),
            **({"startTime": start} if start else {}),
        }
    ] if day else []
    base["ticketType"] = "複数受付" if len(offers) > 1 else (_text(offers[0].get("ticketType")) if offers else "現在受付なし")
    base["applicationDisplayMode"] = "offers" if offers else "schedule-only"
    base["applicationStatus"] = "offers" if offers else "none"
    if all_urls:
        base["urls"] = all_urls
        base["url"] = (official_urls[0] if official_urls else all_urls[0])
    if official_urls:
        base["primarySource"] = "official"
    return base


def build_public_events(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build one hosted live-performance entity per physical performance.

    Acquisition rows remain untouched in ``events``. The returned public model
    folds FC/playguide/etc. rows into ``offers`` while retaining every source row
    id and URL as provenance. Special events, online events, and external
    appearances remain on their existing dedicated paths.
    """
    raw = [deepcopy(event) for event in events if isinstance(event, dict)]
    for event in raw:
        _reconcile_verified_christmas_session(event)
        _reconcile_verified_fc_free_live(event)
        _reconcile_verified_fifth_anniversary(event)
    records: list[dict[str, Any]] = []
    passthrough: list[dict[str, Any]] = []
    for index, event in enumerate(raw):
        if not _is_regular_hosted(event):
            passthrough.append(event)
            continue
        occurrences = _occurrences(event)
        if not occurrences:
            passthrough.append(event)
            continue
        for occurrence_index, occurrence in enumerate(occurrences):
            records.append(
                {
                    "event": event,
                    "occurrence": occurrence,
                    "eventIndex": index,
                    "occurrenceIndex": occurrence_index,
                }
            )

    _reconcile_occurrence_times(records)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        key = _performance_key(record["event"], record["occurrence"])
        grouped.setdefault(key, []).append(record)

    canonical = [_canonical_entity(key, grouped[key]) for key in sorted(grouped)]
    unfiltered_public_events = passthrough + canonical
    public_events = [
        event
        for event in unfiltered_public_events
        if _text(event.get("group")) not in OUT_OF_SCOPE_SOLO_GROUPS
    ]
    out_of_scope_solo_count = len(unfiltered_public_events) - len(public_events)

    source_occurrence_count = len(records)
    merged_source_occurrences = max(0, source_occurrence_count - len(canonical))
    report = {
        "rawEventCount": len(raw),
        "passthroughEventCount": len(passthrough),
        "performanceEntityCount": len(canonical),
        "sourceOccurrenceCount": source_occurrence_count,
        "mergedSourceOccurrences": merged_source_occurrences,
        "offerCount": sum(len(event.get("offers") or []) for event in canonical),
        "outOfScopeSoloEventCount": out_of_scope_solo_count,
    }
    return public_events, report


def performance_entities(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public, _ = build_public_events(events)
    return [event for event in public if event.get("entityType") == "performance"]
