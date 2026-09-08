#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


PAGE = Path("schedule.html")

START_TEXT_JS = (
    "function startText(e){var r=effectiveBand(e),missingStart=!e.applyStart||(r&&r.synthetic);"
    "return missingStart?'日時未取得':fmt(e.applyStart)}\n"
)

OFFER_HTML_JS = (
    "function offerHtml(o){var missingStart=!!o.synthetic||!o.applyStart,"
    "period=missingStart?('申込開始：日時未取得'+(o.applyEnd?' ／ 締切 '+fmt(o.applyEnd):'')):(fmt(o.applyStart)+' 〜 '+fmt(o.applyEnd)),"
    "end=moment(o.applyEnd,true),open=!missingStart&&(!end||end>=now),"
    "state=missingStart?'開始日時未取得':(open?'受付中・予定':'受付終了'),"
    "action=missingStart?'受付詳細を確認 →':o.provider==='kawaii-store'?'整理券ページ →':/^(rakuten|hmv|tower)$/.test(o.provider)?'対象商品ページ →':'申込ページ →',"
    "mode=missingStart?' detail-only':'';"
    "return'<div class=\"ticket-option\"><span class=\"provider '+esc(o.provider)+'\">'+esc(o.label)+'</span><span class=\"ticket-copy\"><b>'+esc(o.ticketType)+'<span class=\"sale-state '+((!missingStart&&open)?'open':'')+'\">'+state+'</span></b><small>'+esc(period)+'</small></span><a class=\"ticket-link'+mode+'\" data-action-mode=\"'+(missingStart?'detail':'apply')+'\" href=\"'+esc(o.url)+'\" target=\"_blank\" rel=\"noopener\">'+action+'</a></div>'}"
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


def _patch_static_ticket_option(block: str) -> str:
    match = re.search(r"<small>(.*?)</small>", block, re.S)
    if not match:
        return block
    window = match.group(1).strip()
    missing_start = window.startswith("〜") or window == "受付期間未取得"
    if not missing_start:
        return block

    if window.startswith("〜"):
        deadline = window[1:].strip()
        replacement = "申込開始：日時未取得" + (f" ／ 締切 {deadline}" if deadline else "")
    else:
        replacement = "申込開始：日時未取得 ／ 締切：日時未取得"
    block = block[: match.start(1)] + replacement + block[match.end(1) :]

    if "申込先 →" in block:
        block = block.replace('class="ticket-link"', 'class="ticket-link detail-only" data-action-mode="detail"', 1)
        block = block.replace("申込先 →", "受付詳細を確認 →", 1)
    return block


def patch_page(page: str) -> str:
    # Static source-row cards used to concatenate the label and fallback value as
    # 「申込開始開始日時未取得」. The value must be only 「日時未取得」.
    page = page.replace("<b>申込開始</b>開始日時未取得", "<b>申込開始</b>日時未取得")

    # Canonical performance cards show offers as ticket-option rows. If the
    # opening time is unknown, keep the official URL for fact checking but do not
    # present it as an active application CTA or claim that the reception is open.
    page = re.sub(r'<div class="ticket-option">.*?</div>', lambda m: _patch_static_ticket_option(m.group(0)), page, flags=re.S)

    page = _replace_function(page, "startText", "performanceDate", START_TEXT_JS, "missingStart=!e.applyStart")
    page = _replace_function(page, "offerHtml", "detailList", OFFER_HTML_JS, "data-action-mode")

    if "申込開始開始日時未取得" in page:
        raise RuntimeError("duplicate missing-start label remains in schedule.html")
    if "missingStart=!!o.synthetic||!o.applyStart" not in page:
        raise RuntimeError("runtime missing-start ticket guard was not installed")
    if "state=missingStart?'開始日時未取得'" not in page:
        raise RuntimeError("unknown application start is still exposed as an open reception")
    if "missingStart?'受付詳細を確認 →'" not in page:
        raise RuntimeError("unknown application start is still exposed as an application CTA")
    return page


def main() -> int:
    page = PAGE.read_text(encoding="utf-8")
    page = patch_page(page)
    PAGE.write_text(page, encoding="utf-8")

    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", page, re.S)
    executable = [script for script in scripts if "(function(){'use strict';" in script]
    if len(executable) != 1:
        raise RuntimeError(f"expected one executable inline script, found {len(executable)}")
    Path("/tmp/schedule-inline.js").write_text(executable[0], encoding="utf-8")

    print("Missing application starts render as unknown and use detail-only links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
