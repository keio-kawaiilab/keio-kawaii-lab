#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import build_schedule_snapshot
from performance_entities import build_public_events
from schedule_scope import HOSTED, infer_event_scope
from special_event_occurrence_details import expand_occurrence_views


DATA = Path("data/live-events.json")
PAGE = Path("schedule.html")
JST = build_schedule_snapshot.JST

PROVIDER_LABELS = {
    "pia": "チケットぴあ",
    "lawson": "ローチケ",
    "eplus": "イープラス",
    "official": "公式 / FC",
    "resale": "公式リセール",
    "sukisuki": "SUKISUKI",
    "kawaii-store": "KAWAII LAB. STORE",
    "rakuten": "楽天チケット",
    "hmv": "HMV",
    "tower": "タワーレコード",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _provider(offer: dict[str, Any]) -> str:
    return _text(offer.get("provider") or offer.get("ticketProvider") or "official").lower()


def _offer_url(offer: dict[str, Any]) -> str:
    if offer.get("url"):
        return _text(offer.get("url"))
    for value in offer.get("urls") or []:
        if value:
            return _text(value)
    return ""


def _offer_window(offer: dict[str, Any]) -> str:
    start = build_schedule_snapshot.fmt(offer.get("applyStart"))
    end = build_schedule_snapshot.fmt(offer.get("applyEnd"))
    if start != "—" and end != "—":
        return f"{start}〜{end}"
    if start != "—":
        return f"{start}〜"
    if end != "—":
        return f"〜{end}"
    return "受付期間未取得"


def _ticket_options_html(event: dict[str, Any]) -> str:
    offers = [offer for offer in event.get("offers") or [] if isinstance(offer, dict)]
    if not offers:
        return '<div class="no-ticket">現在掲載中の申込受付はありません。</div>'
    rows: list[str] = ['<div class="ticket-options">']
    for offer in sorted(
        offers,
        key=lambda item: (
            _text(item.get("applyEnd")),
            _text(item.get("applyStart")),
            _text(item.get("ticketType")),
        ),
    ):
        provider = _provider(offer)
        label = PROVIDER_LABELS.get(provider, provider or "公式")
        ticket_type = _text(offer.get("ticketType") or "チケット受付")
        window = _offer_window(offer)
        url = _offer_url(offer)
        link = (
            f'<a class="ticket-link" href="{build_schedule_snapshot.esc(url)}" target="_blank" rel="noopener">申込先 →</a>'
            if url
            else '<span class="ticket-link" aria-disabled="true">リンク未取得</span>'
        )
        rows.append(
            '<div class="ticket-option">'
            f'<span class="provider {build_schedule_snapshot.esc(provider)}">{build_schedule_snapshot.esc(label)}</span>'
            '<span class="ticket-copy">'
            f'<b>{build_schedule_snapshot.esc(ticket_type)}</b>'
            f'<small>{build_schedule_snapshot.esc(window)}</small>'
            '</span>'
            f'{link}'
            '</div>'
        )
    rows.append('</div>')
    return "".join(rows)


def _performance_datetime(event: dict[str, Any]) -> tuple[str, str]:
    dates = build_schedule_snapshot.event_dates(event)
    date_text = "・".join(build_schedule_snapshot.fmt(value) for value in dates) if dates else "未定"
    open_time = _text(event.get("openTime"))
    start_time = _text(event.get("startTime"))
    online = build_schedule_snapshot.is_online(event)
    pieces: list[str] = []
    if open_time:
        pieces.append(f"開場 {open_time}")
    if start_time:
        pieces.append(f"{'開始' if online else '開演'} {start_time}")
    time_text = " ／ ".join(pieces) if pieces else "時刻未発表"
    return ("配信日時" if online else "開催日時"), f"{date_text} ／ {time_text}"


def _build_public_card(event: dict[str, Any]) -> str:
    card = build_schedule_snapshot.build_card(event)
    if event.get("entityType") != "performance":
        return card

    dates = build_schedule_snapshot.event_dates(event)
    date_text = "・".join(build_schedule_snapshot.fmt(value) for value in dates) if dates else "未定"
    online = build_schedule_snapshot.is_online(event)
    old_date = (
        f'<div><b>{"配信日" if online else "開催日"}</b>'
        f'{build_schedule_snapshot.esc(date_text)}</div>'
    )
    date_label, date_and_time = _performance_datetime(event)
    new_date = (
        f'<div><b>{date_label}</b>'
        f'{build_schedule_snapshot.esc(date_and_time)}</div>'
    )
    if old_date not in card:
        raise RuntimeError("generated performance card date field changed; performance times cannot be installed safely")
    card = card.replace(old_date, new_date, 1)

    options = _ticket_options_html(event)
    anchor = card.rfind('<a class="src"')
    if anchor >= 0:
        return card[:anchor] + options + card[anchor:]
    close = card.rfind("</article>")
    if close < 0:
        raise RuntimeError("generated performance card has no closing article tag")
    return card[:close] + options + card[close:]


def _public_display_events(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    display_source = expand_occurrence_views(payload.get("events") or [])
    public_events, report = build_public_events(display_source)
    now = datetime.now(JST)
    today = now.date()
    visible = [
        event
        for event in public_events
        if build_schedule_snapshot.visible_event(event, today, now)
    ]
    visible.sort(
        key=lambda event: min(
            [
                build_schedule_snapshot.parse_day(day)
                for day in build_schedule_snapshot.event_dates(event)
                if build_schedule_snapshot.parse_day(day)
            ]
            or [today]
        )
    )
    return visible, report


def _replace_snapshot(page: str, payload: dict[str, Any], visible: list[dict[str, Any]]) -> str:
    snapshot = json.dumps(
        {
            "updatedAt": payload.get("updatedAt"),
            "checkedAt": payload.get("checkedAt"),
            "events": visible,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    page, count = re.subn(
        r'(<script id="snapshot-data" type="application/json">).*?(</script>)',
        lambda match: match.group(1) + snapshot + match.group(2),
        page,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("could not replace public snapshot-data")
    return page


def _replace_cards(page: str, visible: list[dict[str, Any]]) -> str:
    default_visible = [event for event in visible if infer_event_scope(event) == HOSTED]
    cards = "\n".join(_build_public_card(event) for event in default_visible)
    page, count = re.subn(
        r'(<div class="cards" id="cards">).*?(</div>\s*<script id="snapshot-data")',
        lambda match: match.group(1) + "\n" + cards + "\n" + match.group(2),
        page,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("could not replace static public performance cards")
    page = re.sub(
        r'<div class="summary" id="summary">.*?</div>',
        f'<div class="summary" id="summary">{len(default_visible)}公演を掲載中（KAWAII LAB.主催のみ）</div>',
        page,
        count=1,
        flags=re.S,
    )
    return page


def _patch_runtime(page: str) -> str:
    special_only = "if(!e||e.entityType!=='special-event'||!Array.isArray(e.offers)){out.push(e);return}"
    performance_aware = "if(!e||(e.entityType!=='special-event'&&e.entityType!=='performance')||!Array.isArray(e.offers)){out.push(e);return}"
    if performance_aware not in page:
        if special_only not in page:
            raise RuntimeError("canonical offer adapter changed; performance entities cannot be expanded safely")
        page = page.replace(special_only, performance_aware, 1)

    # When an old raw multi-day tour row is repaired from an official schedule,
    # the official occurrence's OPEN/START must win over a ticket row's top-level
    # fallback. Otherwise one day's time can be copied onto every tour date.
    ticket_first = "openTime:x.openTime||r.openTime||'',startTime:x.startTime||r.startTime||''"
    occurrence_first = "openTime:r.openTime||x.openTime||'',startTime:r.startTime||x.startTime||''"
    if ticket_first in page:
        page = page.replace(ticket_first, occurrence_first, 1)
    if occurrence_first not in page:
        raise RuntimeError("tour occurrence time repair changed; per-day time priority cannot be installed safely")

    raw_fetch = "events=prepare(data.events||[])"
    public_fetch = "events=prepare(data.publicEvents||data.events||[])"
    if public_fetch not in page:
        if raw_fetch not in page:
            raise RuntimeError("live data loader changed; publicEvents preference cannot be installed")
        page = page.replace(raw_fetch, public_fetch, 1)
    return page


def _tour_performance(
    payload: dict[str, Any],
    *,
    day: str,
    venue_fragment: str,
    open_time: str,
    start_time: str,
) -> dict[str, Any]:
    matches = [
        event
        for event in payload.get("publicEvents") or []
        if isinstance(event, dict)
        and event.get("entityType") == "performance"
        and event.get("group") == "CANDY TUNE"
        and "JAPAN TOUR 2026" in _text(event.get("title"))
        and _text(event.get("eventDate"))[:10] == day
        and venue_fragment in _text(event.get("venue"))
        and _text(event.get("openTime")) == open_time
        and _text(event.get("startTime")) == start_time
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one CANDY TUNE tour performance for {day} "
            f"OPEN {open_time} / START {start_time}, found {len(matches)}"
        )
    return matches[0]


def _verify_tour_times(payload: dict[str, Any], page: str) -> None:
    # Two dates deliberately use different times. Keeping both in the check
    # prevents a tour-level fallback from silently stamping one time on all days.
    hakodate = _tour_performance(
        payload,
        day="2026-10-04",
        venue_fragment="函館市民会館",
        open_time="16:30",
        start_time="17:30",
    )
    sendai = _tour_performance(
        payload,
        day="2026-10-08",
        venue_fragment="仙台サンプラザホール",
        open_time="17:30",
        start_time="18:30",
    )

    offers = sendai.get("offers") or []
    ticket_types = {_text(offer.get("ticketType")) for offer in offers if isinstance(offer, dict)}
    if "FC先行" not in ticket_types or not any("一般発売" in value for value in ticket_types):
        raise RuntimeError(f"Sendai performance lost ticket offers: {sorted(ticket_types)}")

    checks = (
        (hakodate, "2026/10/4 ／ 開場 16:30 ／ 開演 17:30", "函館市民会館"),
        (sendai, "2026/10/8 ／ 開場 17:30 ／ 開演 18:30", "仙台サンプラザホール"),
    )
    for event, expected_datetime, venue_fragment in checks:
        day_text = build_schedule_snapshot.fmt(event.get("eventDate"))
        static_cards = re.findall(
            rf'<article class="card[^>]*data-group="CANDY TUNE"[^>]*>.*?{re.escape(day_text)}.*?</article>',
            page,
            flags=re.S,
        )
        matching = [
            card for card in static_cards
            if venue_fragment in card and "JAPAN TOUR 2026" in card
        ]
        if len(matching) != 1:
            raise RuntimeError(
                f"expected one static CANDY TUNE tour card for {event.get('eventDate')}, found {len(matching)}"
            )
        card = matching[0]
        if "<b>開催日時</b>" not in card or expected_datetime not in card:
            raise RuntimeError(
                f"static tour card lost per-day OPEN/START for {event.get('eventDate')}"
            )

    sendai_day = build_schedule_snapshot.fmt(sendai.get("eventDate"))
    sendai_cards = re.findall(
        rf'<article class="card[^>]*data-group="CANDY TUNE"[^>]*>.*?{re.escape(sendai_day)}.*?</article>',
        page,
        flags=re.S,
    )
    matching_sendai = [
        card for card in sendai_cards
        if "仙台サンプラザホール" in card and "JAPAN TOUR 2026" in card
    ]
    card = matching_sendai[0]
    if "FC先行" not in card or "一般発売" not in card:
        raise RuntimeError("static Sendai performance card does not expose both FC and general-sale offers")


def main() -> int:
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    public_events, model_report = build_public_events(payload.get("events") or [])
    payload["publicEvents"] = public_events
    payload["publicEventModelVersion"] = 1
    payload["publicEventModelReport"] = model_report
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    visible, display_report = _public_display_events(payload)
    page = PAGE.read_text(encoding="utf-8")
    page = _replace_snapshot(page, payload, visible)
    page = _replace_cards(page, visible)
    page = _patch_runtime(page)
    PAGE.write_text(page, encoding="utf-8")

    _verify_tour_times(payload, page)

    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", page, re.S)
    executable = [script for script in scripts if "(function(){'use strict';" in script]
    if len(executable) != 1:
        raise RuntimeError(f"expected one executable inline script, found {len(executable)}")
    Path("/tmp/schedule-inline.js").write_text(executable[0], encoding="utf-8")

    print(json.dumps({"stored": model_report, "display": display_report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())