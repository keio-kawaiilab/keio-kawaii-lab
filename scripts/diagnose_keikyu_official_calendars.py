#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from audit_keikyu_official_columns import FIRST_POSSIBLE_TIMETABLE_PAGE, page_scope_reason
from keikyu_official_pdf import (
    bbox_words,
    cluster_by_y,
    compact,
    detect_train_column_sections,
    download_official_pdf,
    page_count,
)

WEEKDAY_LABEL = '平日用'
HOLIDAY_LABEL = '土休日用'
CALENDAR_HINTS = ('平日', '土休', '休日', 'ダイヤ', '用その')


def printed_calendar(page_text: str) -> str | None:
    has_weekday = WEEKDAY_LABEL in page_text
    has_holiday = HOLIDAY_LABEL in page_text
    if has_weekday == has_holiday:
        return None
    return 'weekday' if has_weekday else 'holiday'


def _row_text(row) -> str:
    return compact(''.join(word.text for word in sorted(row, key=lambda word: word.x)))


def diagnose(pdf_path: Path) -> dict[str, Any]:
    total_pages = page_count(pdf_path)
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    section_counts: Counter[str] = Counter()
    invalid: list[dict[str, Any]] = []
    invalid_with_sections: list[dict[str, Any]] = []

    for page_number in range(FIRST_POSSIBLE_TIMETABLE_PAGE, total_pages + 1):
        _width, _height, words = bbox_words(pdf_path, page_number)
        page_text = compact(''.join(word.text for word in words))
        excluded = page_scope_reason(page_text)
        if excluded:
            continue
        calendar = printed_calendar(page_text)
        sections = detect_train_column_sections(words)
        has_weekday = WEEKDAY_LABEL in page_text
        has_holiday = HOLIDAY_LABEL in page_text
        row = {
            'page': page_number,
            'calendar': calendar,
            'sectionCount': len(sections),
            'hasWeekdayLabel': has_weekday,
            'hasHolidayLabel': has_holiday,
        }
        rows.append(row)
        counts[calendar or 'unclassified'] += 1
        if sections:
            section_counts[calendar or 'unclassified'] += len(sections)
        if calendar is None:
            clustered = cluster_by_y(words)
            texts = [_row_text(group) for group in clustered]
            hint_rows = [text for text in texts if text and any(hint in text for hint in CALENDAR_HINTS)]
            detail = {
                **row,
                'calendarHintRows': hint_rows[:20],
                'topNonEmptyRows': [text for text in texts if text][:30],
            }
            invalid.append(detail)
            if sections:
                invalid_with_sections.append(detail)

    return {
        'kind': 'keikyu-official-printed-calendar-diagnosis',
        'labels': {'weekday': WEEKDAY_LABEL, 'holiday': HOLIDAY_LABEL},
        'pagesAudited': len(rows),
        'counts': dict(counts),
        'sectionCountsByCalendarClass': dict(section_counts),
        'unclassifiedOrAmbiguous': invalid,
        'unclassifiedOrAmbiguousWithIdentitySections': invalid_with_sections,
        'pages': rows,
        'policy': {
            'calendarComesOnlyFromLiteralPrintedPageLabel': True,
            'bothOrNeitherLabelsAcceptedForIdentity': False,
            'unclassifiedPagesMustBeExcludedFromIdentity': True,
            'pageNumberRangeMayInferCalendar': False,
            'neighboringPagesMayInferCalendar': False,
            'runtimeCalendarPromotions': 0,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--pdf', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--fail-on-unclassified-sections', action='store_true')
    args = ap.parse_args()
    if args.pdf:
        payload = diagnose(args.pdf)
    else:
        with tempfile.TemporaryDirectory(prefix='keikyu-calendar-diagnosis-') as td:
            pdf = Path(td) / 'schedule_all.pdf'
            download_official_pdf(pdf)
            payload = diagnose(pdf)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'output': str(args.output),
        'pagesAudited': payload['pagesAudited'],
        'counts': payload['counts'],
        'sectionCountsByCalendarClass': payload['sectionCountsByCalendarClass'],
        'unclassifiedOrAmbiguous': payload['unclassifiedOrAmbiguous'],
        'unclassifiedWithIdentitySections': len(payload['unclassifiedOrAmbiguousWithIdentitySections']),
        'runtimeCalendarPromotions': 0,
    }, ensure_ascii=False, indent=2))
    if args.fail_on_unclassified_sections and payload['unclassifiedOrAmbiguousWithIdentitySections']:
        raise SystemExit('identity-bearing official pages remain unclassified by literal calendar label')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
