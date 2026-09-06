#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

PAGE = Path("schedule.html")
HIDDEN_POLICY = "<!-- schedule-source-policy: FC先行・アップグレードを除いて原則すべて採用 -->"

# A multi-day event remains in the dataset until its final performance has passed.
# The detail renderer must still hide individual performances whose date is already past.
PAST_OCCURRENCE_RENDERER = "occ(e).forEach(function(o){var k=performanceKey(e,o)"
CURRENT_OCCURRENCE_RENDERER = "occ(e).forEach(function(o){var od=p(o.date);if(od&&od<today)return;var k=performanceKey(e,o)"

# Physical performance identity is independent from source/event kind/ticket row.
# Same group + same day + same verified start time is one public performance.
LEGACY_PERFORMANCE_KEY = "function performanceKey(e,o){return[String(e.group||''),String(o.date||'').slice(0,10),eventKind(e),canon(e)].join('|')}"
PERFORMANCE_KEY = (
    "function performanceTitleKey(e){return String(title(e)||'').toLowerCase().replace(/\\s+/g,'').replace(/[!！・|｜\\-–—_\\[\\]()（）『』「」]/g,'')}"
    "function performanceVenueKey(e,o){var v=String((o&&o.venue)||e.venue||'').toLowerCase();"
    "v=v.replace(/^(?:北海道|東京都|京都府|大阪府|.{2,3}県)\\s*/,'').replace(/\\s+/g,'').replace(/[!！・|｜\\-–—_\\[\\]()（）『』「」]/g,'');return v}"
    "function performanceKey(e,o){var day=String((o&&o.date)||e.eventDate||'').slice(0,10),"
    "time=String((o&&o.startTime)||e.startTime||'').replace(/\\s+/g,''),venue=performanceVenueKey(e,o),titleKey=performanceTitleKey(e),group=String(e.group||'').trim();"
    "if(day&&time)return [group,day,'time',time].join('|');"
    "return [group,day,'fallback',venue,titleKey].join('|')}"
)

# fix_schedule_shell.py installs the final occurrence-based identity. These
# markers validate the physical rule without depending on minified formatting.
OCCURRENCE_PERFORMANCE_MARKERS = (
    "function performanceVenueKey(e,o)",
    "function performanceKey(e,o)",
    "performanceTitleKey(e)",
    "if(day&&time)return [group,day,'time',time].join('|')",
    "return [group,day,'fallback',venue,titleKey].join('|')",
)
LEGACY_BAND_KEY_TAIL = "String(e.applyEnd||''),canon(e)].join('|')"
BAND_KEY_TAIL = "String(e.applyEnd||''),performanceTitleKey(e)].join('|')"
APPLICATION_BAND_MARKERS = (
    "function applicationBandSubjectKey(e)",
    "function applicationBandKey(e,index)",
    "applicationBandSubjectKey(e)",
)


def ensure_past_performances_hidden(page: str) -> str:
    if CURRENT_OCCURRENCE_RENDERER in page:
        return page
    if PAST_OCCURRENCE_RENDERER not in page:
        raise RuntimeError("schedule detail renderer changed; past-performance guard could not be installed")
    return page.replace(PAST_OCCURRENCE_RENDERER, CURRENT_OCCURRENCE_RENDERER, 1)


def has_visible_title_performance_identity(page: str) -> bool:
    return PERFORMANCE_KEY in page or all(marker in page for marker in OCCURRENCE_PERFORMANCE_MARKERS)


def has_application_band_identity(page: str) -> bool:
    return BAND_KEY_TAIL in page or all(marker in page for marker in APPLICATION_BAND_MARKERS)


def ensure_visible_title_performance_identity(page: str) -> str:
    if has_visible_title_performance_identity(page):
        fixed = page
    elif LEGACY_PERFORMANCE_KEY in page:
        fixed = page.replace(LEGACY_PERFORMANCE_KEY, PERFORMANCE_KEY, 1)
    else:
        raise RuntimeError("schedule performance identity changed; physical-performance dedupe could not be installed")

    if has_application_band_identity(fixed):
        return fixed
    if LEGACY_BAND_KEY_TAIL not in fixed:
        raise RuntimeError("schedule application-band identity changed; title dedupe could not be installed")
    return fixed.replace(LEGACY_BAND_KEY_TAIL, BAND_KEY_TAIL, 1)


def assert_physical_identity(page: str) -> None:
    start = page.find("function performanceKey(e,o)")
    end = page.find("function performanceKeyForEvent", start)
    if start < 0 or end < 0:
        raise RuntimeError("physical performance identity block is missing")
    block = page[start:end]
    if "eventKind(e)" in block:
        raise RuntimeError("eventKind must not participate in physical performance identity")
    if "if(day&&time)return [group,day,'time',time].join('|')" not in block:
        raise RuntimeError("group/date/start-time physical performance key is missing")


def main() -> int:
    page = PAGE.read_text(encoding="utf-8")

    page = re.sub(r'<p class="lead">.*?</p>\s*', '', page, count=1, flags=re.S)
    page = re.sub(r'<p class="policy">.*?</p>\s*', '', page, count=1, flags=re.S)
    page = re.sub(r'<div class="deadline-note">.*?</div>', '', page, flags=re.S)

    dynamic_note = "+(synthetic?'<div class=\"deadline-note\">開始日時は未取得です。カレンダーの帯は今日から締切まで表示しています。</div>':'')+"
    page = page.replace(dynamic_note, "+")

    page = ensure_past_performances_hidden(page)
    page = ensure_visible_title_performance_identity(page)
    assert_physical_identity(page)

    if HIDDEN_POLICY not in page:
        marker = '<aside class="schedule-disclaimer"'
        pos = page.find(marker)
        if pos >= 0:
            page = page[:pos] + HIDDEN_POLICY + "\n" + page[pos:]
        else:
            page = page.replace('<main>', '<main>\n' + HIDDEN_POLICY, 1)

    forbidden_visible = (
        'チケットぴあ掲載の受付は、',
        '一般発売・プレリザーブ等はぴあを優先。',
        '開始日時は未取得です。カレンダーの帯は今日から締切まで表示しています。',
    )
    for text in forbidden_visible:
        if text in page:
            raise RuntimeError(f"user-facing implementation note still present: {text}")

    if CURRENT_OCCURRENCE_RENDERER not in page:
        raise RuntimeError("past-performance guard is missing from schedule detail renderer")
    if not has_visible_title_performance_identity(page) or not has_application_band_identity(page):
        raise RuntimeError("physical performance dedupe is missing from schedule renderer")

    PAGE.write_text(page, encoding="utf-8")
    print("Removed internal schedule copy, hid past details, and preserved one physical performance identity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
