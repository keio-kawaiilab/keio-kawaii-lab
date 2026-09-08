#!/usr/bin/env python3
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PAGE = Path("schedule.html")
JST = ZoneInfo("Asia/Tokyo")

START_TEXT_JS = (
    "function startText(e){var r=effectiveBand(e),missingStart=!e.applyStart||(r&&r.synthetic);"
    "return missingStart?'日時未取得':fmt(e.applyStart)}\n"
)

OFFER_HTML_JS = (
    "function offerHtml(o){var missingStart=!!o.synthetic||!o.applyStart,"
    "period=missingStart?('申込開始：日時未取得'+(o.applyEnd?' ／ 締切 '+fmt(o.applyEnd):'')):(fmt(o.applyStart)+' 〜 '+fmt(o.applyEnd)),"
    "start=moment(o.applyStart,false),end=moment(o.applyEnd,true),ended=!!end&&end<now,"
    "scheduled=!missingStart&&!!start&&start>now,open=!missingStart&&!ended&&!scheduled,"
    "state=ended?'受付終了':missingStart?'開始日時未取得':scheduled?'受付予定':'受付中',"
    "detailOnly=ended||missingStart,"
    "action=detailOnly?'受付詳細を確認 →':o.provider==='kawaii-store'?'整理券ページ →':/^(rakuten|hmv|tower)$/.test(o.provider)?'対象商品ページ →':'申込ページ →',"
    "mode=detailOnly?' detail-only':'',stateClass=open?' open':scheduled?' scheduled':ended?' ended':'';"
    "return'<div class=\"ticket-option\"><span class=\"provider '+esc(o.provider)+'\">'+esc(o.label)+'</span><span class=\"ticket-copy\"><b>'+esc(o.ticketType)+'<span class=\"sale-state'+stateClass+'\">'+state+'</span></b><small>'+esc(period)+'</small></span><a class=\"ticket-link'+mode+'\" data-action-mode=\"'+(detailOnly?'detail':'apply')+'\" href=\"'+esc(o.url)+'\" target=\"_blank\" rel=\"noopener\">'+action+'</a></div>'}"
    "\n"
)


def _replace_function(page: str, name: str, next_name: str, replacement: str, marker: str) -> str:
    start = page.find(f"function {name}(")
    if start < 0:
        raise RuntimeError(f"schedule runtime no longer contains {name}()")
    end = page.find(f"function {next_name}(", start)
    if end < 0:
        raise RuntimeError(f"schedule runtime no longer contains {next_name}() after {name}()")
    current = page[start:end]
    if marker in current:
        return page
    return page[:start] + replacement + page[end:]


def _parse_display_moment(value: str, *, end_of_day: bool = False) -> datetime | None:
    match = re.match(
        r"^\s*(\d{4})/(\d{1,2})/(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?\s*$",
        value or "",
    )
    if not match:
        return None
    hour = int(match.group(4)) if match.group(4) is not None else (23 if end_of_day else 0)
    minute = int(match.group(5)) if match.group(5) is not None else (59 if end_of_day else 0)
    second = 59 if end_of_day and match.group(4) is None else 0
    try:
        return datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            hour,
            minute,
            second,
            tzinfo=JST,
        )
    except ValueError:
        return None


def _window_values(window: str) -> tuple[str, str, bool]:
    text = (window or "").strip()
    if text == "受付期間未取得":
        return "", "", True
    if text.startswith("申込開始：日時未取得"):
        deadline = re.search(r"締切[： ]+(.+)$", text)
        return "", deadline.group(1).strip() if deadline else "", True
    if text.startswith("〜"):
        return "", text[1:].strip(), True
    if "〜" in text:
        start, end = text.split("〜", 1)
        return start.strip(), end.strip(), not start.strip()
    return text, "", not bool(text)


def _offer_state(window: str, now: datetime) -> tuple[str, str, bool]:
    start_text, end_text, missing_start = _window_values(window)
    start = _parse_display_moment(start_text)
    end = _parse_display_moment(end_text, end_of_day=True)

    # A confirmed passed deadline is stronger information than a missing start.
    if end and end < now:
        return "ended", "受付終了", True
    if missing_start or start is None:
        return "unknown", "開始日時未取得", True
    if start > now:
        return "scheduled", "受付予定", False
    return "open", "受付中", False


def _normalize_missing_start_window(window: str) -> str:
    start_text, end_text, missing_start = _window_values(window)
    if not missing_start:
        return window
    if end_text:
        return f"申込開始：日時未取得 ／ 締切 {end_text}"
    return "申込開始：日時未取得 ／ 締切：日時未取得"


def _set_static_state(block: str, state_key: str, state_label: str) -> str:
    state_class = "sale-state"
    if state_key in {"open", "scheduled", "ended"}:
        state_class += f" {state_key}"
    state_html = f'<span class="{state_class}">{state_label}</span>'

    def replace_ticket_copy(match: re.Match[str]) -> str:
        content = re.sub(r'<span class="sale-state[^\"]*">.*?</span>', "", match.group(2), flags=re.S)
        return match.group(1) + content + state_html + match.group(3)

    return re.sub(
        r'(<span class="ticket-copy"><b>)(.*?)(</b>)',
        replace_ticket_copy,
        block,
        count=1,
        flags=re.S,
    )


def _set_static_link_mode(block: str, *, detail_only: bool) -> str:
    block = block.replace(
        'class="ticket-link detail-only" data-action-mode="detail"',
        'class="ticket-link"',
    )
    block = block.replace(
        'class="ticket-link" data-action-mode="apply"',
        'class="ticket-link"',
    )
    if '<a class="ticket-link"' not in block:
        return block

    if detail_only:
        block = block.replace(
            '<a class="ticket-link"',
            '<a class="ticket-link detail-only" data-action-mode="detail"',
            1,
        )
        block = re.sub(
            r'(>)(?:申込先|申込ページ|整理券ページ|対象商品ページ|受付詳細を確認) →(</a>)',
            r'\1受付詳細を確認 →\2',
            block,
            count=1,
        )
    else:
        block = block.replace(
            '<a class="ticket-link"',
            '<a class="ticket-link" data-action-mode="apply"',
            1,
        )
    return block


def _patch_static_ticket_option(block: str, now: datetime) -> str:
    match = re.search(r"<small>(.*?)</small>", block, re.S)
    if not match:
        return block
    original_window = match.group(1).strip()
    normalized_window = _normalize_missing_start_window(original_window)
    if normalized_window != original_window:
        block = block[: match.start(1)] + normalized_window + block[match.end(1) :]

    state_key, state_label, detail_only = _offer_state(original_window, now)
    block = _set_static_state(block, state_key, state_label)
    return _set_static_link_mode(block, detail_only=detail_only)


def _assert_status_rules() -> None:
    now = datetime(2026, 9, 8, 14, 47, tzinfo=JST)
    cases = (
        ("2026/9/1 10:00〜2026/9/8 12:00", "ended", "受付終了", True),
        ("〜2026/9/8 12:00", "ended", "受付終了", True),
        ("〜2026/9/9 23:59", "unknown", "開始日時未取得", True),
        ("2026/9/9 10:00〜2026/9/10 23:59", "scheduled", "受付予定", False),
        ("2026/9/8 12:00〜2026/9/8 18:00", "open", "受付中", False),
    )
    for window, key, label, detail_only in cases:
        actual = _offer_state(window, now)
        if actual != (key, label, detail_only):
            raise RuntimeError(f"ticket reception state rule failed for {window}: {actual}")


def patch_page(page: str, *, now: datetime | None = None) -> str:
    now = now or datetime.now(JST)

    # Static source-row cards used to concatenate the label and fallback value as
    # 「申込開始開始日時未取得」. The value must be only 「日時未取得」.
    page = page.replace("<b>申込開始</b>開始日時未取得", "<b>申込開始</b>日時未取得")

    # Static performance cards must show the same time-aware reception state as
    # the browser runtime. A passed deadline always wins over missing-start data.
    page = re.sub(
        r'<div class="ticket-option">.*?</div>',
        lambda m: _patch_static_ticket_option(m.group(0), now),
        page,
        flags=re.S,
    )

    page = _replace_function(page, "startText", "performanceDate", START_TEXT_JS, "missingStart=!e.applyStart")
    page = _replace_function(page, "offerHtml", "detailList", OFFER_HTML_JS, "ended=!!end&&end<now")

    if "申込開始開始日時未取得" in page:
        raise RuntimeError("duplicate missing-start label remains in schedule.html")
    if "ended=!!end&&end<now" not in page:
        raise RuntimeError("runtime no longer calculates ended receptions from the current time")
    if "scheduled=!missingStart&&!!start&&start>now" not in page:
        raise RuntimeError("runtime no longer calculates future receptions from the current time")
    if "state=ended?'受付終了'" not in page:
        raise RuntimeError("ended receptions are not exposed as ended")
    if "detailOnly=ended||missingStart" not in page:
        raise RuntimeError("ended or unknown-start receptions still expose an application CTA")
    return page


def main() -> int:
    _assert_status_rules()
    page = PAGE.read_text(encoding="utf-8")
    page = patch_page(page)
    PAGE.write_text(page, encoding="utf-8")

    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", page, re.S)
    executable = [script for script in scripts if "(function(){'use strict';" in script]
    if len(executable) != 1:
        raise RuntimeError(f"expected one executable inline script, found {len(executable)}")
    Path("/tmp/schedule-inline.js").write_text(executable[0], encoding="utf-8")

    print("Ticket receptions render scheduled, open, ended, or unknown from the current time")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
