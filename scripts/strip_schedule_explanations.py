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

# The UI already normalizes raw source headlines through title(e). The performance
# identity must use that same visible title. Using canon(e) here made two source rows
# render as separate cards even when the user-visible performance title was identical.
LEGACY_PERFORMANCE_KEY = "function performanceKey(e,o){return[String(e.group||''),String(o.date||'').slice(0,10),eventKind(e),canon(e)].join('|')}"
PERFORMANCE_KEY = (
    "function performanceTitleKey(e){return String(title(e)||'').toLowerCase().replace(/\\s+/g,'').replace(/[!！・|｜\\-–—_\\[\\]()（）『』「」]/g,'')}"
    "function performanceKey(e,o){return[String(e.group||''),String(o.date||'').slice(0,10),eventKind(e),performanceTitleKey(e)].join('|')}"
)
LEGACY_BAND_KEY_TAIL = "String(e.applyEnd||''),canon(e)].join('|')"
BAND_KEY_TAIL = "String(e.applyEnd||''),performanceTitleKey(e)].join('|')"


def ensure_past_performances_hidden(page: str) -> str:
    if CURRENT_OCCURRENCE_RENDERER in page:
        return page
    if PAST_OCCURRENCE_RENDERER not in page:
        raise RuntimeError("schedule detail renderer changed; past-performance guard could not be installed")
    return page.replace(PAST_OCCURRENCE_RENDERER, CURRENT_OCCURRENCE_RENDERER, 1)


def ensure_visible_title_performance_identity(page: str) -> str:
    if PERFORMANCE_KEY in page:
        fixed = page
    elif LEGACY_PERFORMANCE_KEY in page:
        fixed = page.replace(LEGACY_PERFORMANCE_KEY, PERFORMANCE_KEY, 1)
    else:
        raise RuntimeError("schedule performance identity changed; visible-title dedupe could not be installed")

    # Application bands for the same provider/window should follow the same
    # normalized performance name too, otherwise a duplicate card can disappear
    # while duplicate bands remain above it.
    if BAND_KEY_TAIL in fixed:
        return fixed
    if LEGACY_BAND_KEY_TAIL not in fixed:
        raise RuntimeError("schedule application-band identity changed; title dedupe could not be installed")
    return fixed.replace(LEGACY_BAND_KEY_TAIL, BAND_KEY_TAIL, 1)


def main() -> int:
    page = PAGE.read_text(encoding="utf-8")

    page = re.sub(r'<p class="lead">.*?</p>\s*', '', page, count=1, flags=re.S)
    page = re.sub(r'<p class="policy">.*?</p>\s*', '', page, count=1, flags=re.S)
    page = re.sub(r'<div class="deadline-note">.*?</div>', '', page, flags=re.S)

    dynamic_note = "+(synthetic?'<div class=\"deadline-note\">開始日時は未取得です。カレンダーの帯は今日から締切まで表示しています。</div>':'')+"
    page = page.replace(dynamic_note, "+")

    # Keep multi-day events themselves, but never render an already-finished date
    # in the detailed performance cards. This is applied after every snapshot build,
    # so generated updates cannot reintroduce yesterday's performance.
    page = ensure_past_performances_hidden(page)

    # Deduplicate by the title users actually see, not by raw source headlines.
    page = ensure_visible_title_performance_identity(page)

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
    if PERFORMANCE_KEY not in page or BAND_KEY_TAIL not in page:
        raise RuntimeError("visible-title performance dedupe is missing from schedule renderer")

    PAGE.write_text(page, encoding="utf-8")
    print("Removed internal schedule copy, hid past details, and deduplicated visible performances")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
