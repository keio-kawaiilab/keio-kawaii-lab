#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

DATA_PATH = Path("data/live-events.json")
GROUP_NAMES = (
    "FRUITS ZIPPER", "CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR",
    "KAWAII LAB.合同", "KAWAII LAB.",
)
LOT_RE = re.compile(r"[?&]lotRlsCd=([A-Za-z0-9_-]+)")
SUKISUKI_GOODS_RE = re.compile(r"https?://(?:api\.)?sukisuki-shop\.com/goods/(\d+)", re.I)
PREFECTURE_PREFIX_RE = re.compile(r"^(?:北海道|東京都|京都府|大阪府|.{2,3}県)\s*")


def normalize_text(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def source_urls(event: dict) -> list[str]:
    values = []
    if event.get("url"):
        values.append(str(event["url"]))
    for url in event.get("urls") or []:
        if url and str(url) not in values:
            values.append(str(url))
    return values


def pia_lots(event: dict) -> tuple[str, ...]:
    values = []
    for url in source_urls(event):
        match = LOT_RE.search(url)
        if match and match.group(1) not in values:
            values.append(match.group(1))
    return tuple(values)


def sukisuki_goods(event: dict) -> tuple[str, ...]:
    values = []
    for url in source_urls(event):
        match = SUKISUKI_GOODS_RE.search(url)
        if match and match.group(1) not in values:
            values.append(match.group(1))
    return tuple(values)


def source_kind(event: dict) -> str:
    source = normalize_text(event.get("sourceType")).lower()
    urls = " ".join(source_urls(event)).lower()
    primary = normalize_text(event.get("primarySource")).lower()
    if source == "sukisuki" or primary == "sukisuki" or "sukisuki-shop.com" in urls:
        return "sukisuki"
    if source == "pia" or primary == "pia" or "t.pia.jp" in urls:
        return "pia"
    if source == "lawson" or primary == "lawson" or "l-tike.com" in urls:
        return "lawson"
    if source == "eplus" or primary == "eplus" or "eplus.jp" in urls:
        return "eplus"
    return "official"


def is_online(event: dict) -> bool:
    text = f"{event.get('eventCategory', '')} {event.get('ticketType', '')} {event.get('title', '')}"
    return event.get("eventCategory") == "online-benefit" or bool(re.search(r"オンライン(?:特典会|サイン会)", text))


def sale_family(event: dict) -> str:
    text = normalize_text(f"{event.get('ticketType', '')} {event.get('title', '')}")
    if is_online(event):
        return "online-benefit"
    if "アップグレード" in text:
        return "upgrade"
    if re.search(
        r"(?:年会費コース|OFFICIAL FANCLUB|ファンクラブ|(?:^|\s)FC(?:\s*(?:会員|先行|限定|2次先行|2次|年会費コース))?)",
        text,
        re.I,
    ):
        return "fc"
    if re.search(r"(?:一般発売|一般販売|一般先着|一般先行)", text):
        return "general"
    if re.search(r"(?:プレリザーブ|プレイガイド|ぴあNICOS|ぴあカード|プリセール)", text, re.I):
        return "playguide"
    if "先行" in text:
        return "presale"
    if event.get("ticketType") == "現在受付なし" or event.get("applicationStatus") == "none":
        return "schedule-only"
    return "other"


def canonical_title(event: dict) -> str:
    text = normalize_text(event.get("eventTitle") or event.get("title") or "")
    text = re.sub(r"^20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+", "", text)
    quoted = re.search(r"「([^」]+)」", text)
    if quoted:
        text = quoted.group(1)
    text = re.sub(r"^(?:20\d{2}年)?\d{1,2}月\d{1,2}日(?:\([^)]*\)|（[^）]*）)?\s*", "", text)
    for group in GROUP_NAMES:
        text = re.sub(rf"^{re.escape(group)}\s*", "", text, flags=re.I)
    text = re.split(
        r"\s*@|開催決定|出演決定|アップグレード抽選受付|一般(?:発売|販売|先行)|"
        r"FC\s*(?:会員)?先行|ファンクラブ|OFFICIAL FANCLUB|プレリザーブ|プレイガイド|"
        r"先行受付|チケット受付|受付のお知らせ",
        text,
        maxsplit=1,
        flags=re.I,
    )[0]
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[!！・|｜\-–—_\[\]()（）『』「」]", "", text)
    return text.lower()


def event_days(event: dict) -> tuple[str, ...]:
    values: list[str] = []
    schedule = event.get("schedule")
    if isinstance(schedule, list):
        for item in schedule:
            if isinstance(item, dict) and item.get("date"):
                values.append(str(item["date"])[:10])
    dates = event.get("eventDates")
    if isinstance(dates, list):
        values.extend(str(value)[:10] for value in dates if value)
    if not values and event.get("eventDate"):
        values.append(str(event["eventDate"])[:10])
    return tuple(sorted(dict.fromkeys(values)))


def group_key(event: dict) -> tuple[str, tuple[str, ...]]:
    participants = tuple(sorted(str(x) for x in (event.get("participants") or []) if x))
    return normalize_text(event.get("group")), participants


def canonical_source_url(event: dict) -> str:
    values = source_urls(event)
    if not values:
        return ""
    url = values[0].strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    host = parts.netloc.lower()
    # eplus adds tracking / route query parameters (for example ?P1=0175)
    # to the same /sf/detail/... performance. They are not separate receptions.
    if source_kind(event) == "eplus" and host.endswith("eplus.jp") and "/sf/detail/" in parts.path:
        return urlunsplit((parts.scheme.lower(), host, parts.path.rstrip("/"), "", ""))
    return urlunsplit((parts.scheme.lower(), host, parts.path.rstrip("/"), parts.query, ""))


def normalize_venue(value: object) -> str:
    text = normalize_text(value).lower()
    text = PREFECTURE_PREFIX_RE.sub("", text)
    return re.sub(r"[\s　・･,，.。()（）\-–—_]", "", text)


def occurrences(event: dict) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    schedule = event.get("schedule")
    if isinstance(schedule, list) and schedule:
        for item in schedule:
            if not isinstance(item, dict) or not item.get("date"):
                continue
            rows.append((
                str(item.get("date"))[:10],
                normalize_venue(item.get("venue") or event.get("venue")),
                normalize_text(item.get("startTime") or event.get("startTime")),
            ))
    elif isinstance(event.get("eventDates"), list) and event.get("eventDates"):
        for value in event.get("eventDates") or []:
            if value:
                rows.append((
                    str(value)[:10],
                    normalize_venue(event.get("venue")),
                    normalize_text(event.get("startTime")),
                ))
    elif event.get("eventDate"):
        rows.append((
            str(event.get("eventDate"))[:10],
            normalize_venue(event.get("venue")),
            normalize_text(event.get("startTime")),
        ))
    return rows


def generic_same_source_duplicate(a: dict, b: dict) -> bool:
    source_a, source_b = source_kind(a), source_kind(b)
    if source_a != source_b or source_a not in {"pia", "lawson", "eplus"}:
        return False
    if normalize_text(a.get("ticketType")) != normalize_text(b.get("ticketType")):
        return False
    if normalize_text(a.get("applyStart")) != normalize_text(b.get("applyStart")):
        return False
    if normalize_text(a.get("applyEnd")) != normalize_text(b.get("applyEnd")):
        return False
    if event_days(a) != event_days(b) or not event_days(a):
        return False

    url_a, url_b = canonical_source_url(a), canonical_source_url(b)
    if url_a and url_b and url_a == url_b:
        return True

    rows_a, rows_b = occurrences(a), occurrences(b)
    if not rows_a or not rows_b:
        return False
    # Generic provider titles (often just the artist name) are safe to collapse
    # when every performance date resolves to the same venue/start combination.
    return set(rows_a) == set(rows_b)


def same_event_and_sale(a: dict, b: dict) -> bool:
    if group_key(a) != group_key(b):
        return False
    if sale_family(a) != sale_family(b):
        return False

    # A performance can have simultaneous application windows at multiple
    # playguides. They must remain independent rows so the calendar can draw
    # one band and one outbound link for each provider.
    playguides = {"pia", "lawson", "eplus"}
    source_a, source_b = source_kind(a), source_kind(b)
    if source_a in playguides and source_b in playguides and source_a != source_b:
        return False

    # A Ticket Pia lotRlsCd is an actual application page. Never collapse two
    # different application pages into one record, even if dates/windows match.
    if source_a == "pia" and source_b == "pia":
        lots_a, lots_b = pia_lots(a), pia_lots(b)
        if lots_a and lots_b and lots_a != lots_b:
            return False

    # SUKISUKI often adds a separate first-come / bingo-first-come goods page
    # immediately before the stream. Keep each goods page as a distinct sale
    # round, and never collapse lottery and first-come ticket types together.
    if source_a == "sukisuki" and source_b == "sukisuki":
        if normalize_text(a.get("ticketType")) != normalize_text(b.get("ticketType")):
            return False
        goods_a, goods_b = sukisuki_goods(a), sukisuki_goods(b)
        if goods_a and goods_b and goods_a != goods_b:
            return False

    if event_days(a) != event_days(b) or not event_days(a):
        return False
    title_a, title_b = canonical_title(a), canonical_title(b)
    if not title_a or not title_b:
        return generic_same_source_duplicate(a, b)
    return title_a == title_b or title_a in title_b or title_b in title_a


def priority(event: dict) -> int:
    source = source_kind(event)
    family = sale_family(event)
    if family == "online-benefit":
        return {"sukisuki": 500, "official": 350, "pia": 250}.get(source, 0)
    if family in {"fc", "upgrade"}:
        return {"official": 500, "pia": 100, "sukisuki": 50}.get(source, 0)
    return {"pia": 500, "lawson": 500, "eplus": 500, "official": 350, "sukisuki": 100}.get(source, 0)


def with_source_metadata(event: dict) -> dict:
    out = dict(event)
    source = source_kind(out)
    out["primarySource"] = source
    out["sourceCandidates"] = [source]
    return out


def merge_duplicate(items: list[dict]) -> dict:
    ranked = sorted(items, key=priority, reverse=True)
    winner = dict(ranked[0])
    all_urls: list[str] = []
    for item in ranked:
        for url in source_urls(item):
            if url not in all_urls:
                all_urls.append(url)
        # Keep richer timing/venue data when the winning URL variant omitted it.
        for field in ("venue", "openTime", "startTime", "eventTitle", "displayTitle"):
            if not winner.get(field) and item.get(field):
                winner[field] = item[field]
    if all_urls:
        winner["urls"] = all_urls
        winner["url"] = source_urls(ranked[0])[0] if source_urls(ranked[0]) else all_urls[0]
    winner["primarySource"] = source_kind(ranked[0])
    winner["sourceCandidates"] = sorted({source_kind(item) for item in ranked})
    winner.pop("sourceStale", None)
    winner.pop("sourceStaleSince", None)
    winner.pop("releaseRetentionReason", None)
    return winner


def resolve(events: list[dict]) -> list[dict]:
    result: list[dict] = []
    used: set[int] = set()
    for index, event in enumerate(events):
        if index in used:
            continue
        bucket = [event]
        used.add(index)
        for other_index in range(index + 1, len(events)):
            if other_index in used:
                continue
            if same_event_and_sale(event, events[other_index]):
                bucket.append(events[other_index])
                used.add(other_index)
        result.append(merge_duplicate(bucket) if len(bucket) > 1 else with_source_metadata(event))
    return result


def match_score(playguide_event: dict, official_event: dict) -> int:
    if group_key(playguide_event) != group_key(official_event):
        return -1
    if is_online(playguide_event) != is_online(official_event):
        return -1
    play_rows = occurrences(playguide_event)
    off_rows = occurrences(official_event)
    if not play_rows or not off_rows:
        return -1

    score = 0
    matched_days: set[str] = set()
    for day, venue, start in play_rows:
        best = -1
        for o_day, o_venue, o_start in off_rows:
            if day != o_day:
                continue
            local = 10
            if venue and o_venue:
                if venue != o_venue:
                    continue
                local += 30
            if start and o_start:
                if start != o_start:
                    continue
                local += 20
            best = max(best, local)
        if best >= 0:
            score += best
            matched_days.add(day)

    if not matched_days:
        return -1
    play_days = set(event_days(playguide_event))
    if play_days and matched_days == play_days:
        score += 40
    return score


def align_playguide_event_titles(events: list[dict]) -> list[dict]:
    official = [
        event for event in events
        if source_kind(event) == "official" and canonical_title(event)
    ]
    out: list[dict] = []
    for event in events:
        source = source_kind(event)
        if source not in {"pia", "lawson", "eplus"}:
            out.append(event)
            continue

        scored: list[tuple[int, dict]] = []
        for candidate in official:
            score = match_score(event, candidate)
            if score >= 0:
                scored.append((score, candidate))
        if not scored:
            out.append(event)
            continue

        top_score = max(score for score, _ in scored)
        top = [candidate for score, candidate in scored if score == top_score]
        canonical_titles = {canonical_title(candidate) for candidate in top if canonical_title(candidate)}
        # If two genuinely different official events are equally plausible, keep the
        # provider title rather than risking a false merge in the public calendar.
        if len(canonical_titles) != 1:
            out.append(event)
            continue

        candidate = next(candidate for candidate in top if canonical_title(candidate) in canonical_titles)
        authoritative_title = normalize_text(
            candidate.get("displayTitle") or candidate.get("eventTitle") or candidate.get("title")
        )
        if not authoritative_title:
            out.append(event)
            continue
        updated = dict(event)
        updated["eventTitle"] = authoritative_title
        updated["performanceMatchedToOfficial"] = True
        out.append(updated)
    return out


def resolve_payload(payload: dict) -> dict:
    out = dict(payload)
    events = [dict(x) for x in payload.get("events", []) if isinstance(x, dict)]
    resolved = resolve(events)
    out["events"] = align_playguide_event_titles(resolved)
    out["source"] = "KAWAII LAB.各グループ公式公開情報 + チケットぴあ・ローチケ・イープラス公開情報 + SUKISUKI公開オンライン特典会情報 + 公式大特典会・リリースイベント情報"
    return out


def main() -> int:
    if not DATA_PATH.exists():
        return 0
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    resolved = resolve_payload(payload)
    DATA_PATH.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Resolved source priority: {len(payload.get('events', []))} -> {len(resolved.get('events', []))} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
