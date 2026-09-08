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


def _build_public_card(event: dict[str, Any]) -> str:
    card = build_schedule_snapshot.build_card(event)
    if event.get("entityType") != "performance":
        return card
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

    raw_fetch = "events=prepare(data.events||[])"
    public_fetch = "events=prepare(data.publicEvents||data.events||[])"
    if public_fetch not in page:
        if raw_fetch not in page:
            raise RuntimeError("live data loader changed; publicEvents preference cannot be installed")
        page = page.replace(raw_fetch, public_fetch, 1)
    return page


def _verify_sendai(payload: dict[str, Any], page: str) -> None:
    public_events = payload.get("publicEvents") or []
    sendai = [
        event
        for event in public_events
        if isinstance(event, dict)
        and event.get("entityType") == "performance"
        and event.get("group") == "CANDY TUNE"
        and _text(event.get("eventDate"))[:10] == "2026-10-08"
        and _text(event.get("startTime")) == "18:30"
    ]
    if len(sendai) != 1:
        raise RuntimeError(f"expected one canonical CANDY TUNE Sendai performance, found {len(sendai)}")
    offers = sendai[0].get("offers") or []
    ticket_types = {_text(offer.get("ticketType")) for offer in offers if isinstance(offer, dict)}
    if "FC先行" not in ticket_types or not any("一般発売" in value for value in ticket_types):
        raise RuntimeError(f"Sendai performance lost ticket offers: {sorted(ticket_types)}")

    static_sendai_cards = re.findall(
        r'<article class="card[^>]*data-group="CANDY TUNE"[^>]*>.*?2026/10/8.*?</article>',
        page,
        flags=re.S,
    )
    matching = [card for card in static_sendai_cards if "仙台サンプラザホール" in card and "JAPAN TOUR 2026" in card]
    if len(matching) != 1:
        raise RuntimeError(f"expected one static CANDY TUNE Sendai tour card, found {len(matching)}")
    card = matching[0]
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

    _verify_sendai(payload, page)

    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", page, re.S)
    executable = [script for script in scripts if "(function(){'use strict';" in script]
    if len(executable) != 1:
        raise RuntimeError(f"expected one executable inline script, found {len(executable)}")
    Path("/tmp/schedule-inline.js").write_text(executable[0], encoding="utf-8")

    print(json.dumps({"stored": model_report, "display": display_report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
