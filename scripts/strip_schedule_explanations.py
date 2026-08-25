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


def ensure_past_performances_hidden(page: str) -> str:
    if CURRENT_OCCURRENCE_RENDERER in page:
        return page
    if PAST_OCCURRENCE_RENDERER not in page:
        raise RuntimeError("schedule detail renderer changed; past-performance guard could not be installed")
    return page.replace(PAST_OCCURRENCE_RENDERER, CURRENT_OCCURRENCE_RENDERER, 1)


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

    PAGE.write_text(page, encoding="utf-8")
    print("Removed internal schedule implementation copy and hid past performance details")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
