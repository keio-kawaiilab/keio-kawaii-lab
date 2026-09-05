#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import keikyu_official_train_evidence as parser


def endpoint_matches(fragment, railway, calendar, first, minute, tolerance=0):
    return parser.fragment_matches(fragment, railway, calendar, first, minute, tolerance)


def near_matches(fragments, railway, calendar, first, minute, tolerance):
    return [
        row for row in fragments
        if endpoint_matches(row, railway, calendar, first, minute, tolerance)
    ]


def endpoint_inventory(fragments, railway, calendar, first):
    out = []
    for fragment in fragments:
        if str(fragment.get('railway') or '') != railway:
            continue
        if not parser.calendar_matches(fragment.get('calendar'), calendar):
            continue
        stop = parser.endpoint(fragment, first)
        if not stop or not str(stop[0] or '').endswith('.Sengakuji'):
            continue
        values = [int(value) for value in stop[1:3] if isinstance(value, (int, float))]
        out.append((fragment.get('id'), values, fragment.get('sourceKind'), fragment.get('trainNumber')))
    return out


def classify(candidate, fragments):
    calendar = str(candidate['calendar'])
    source_minute = int(candidate['sourceBoundaryMinute'])
    target_minute = int(candidate['targetBoundaryMinute'])

    src0 = near_matches(fragments, parser.KEIKYU_MAIN, calendar, False, source_minute, 0)
    dst0 = near_matches(fragments, parser.TOEI_ASAKUSA, calendar, True, target_minute, 0)
    src1 = near_matches(fragments, parser.KEIKYU_MAIN, calendar, False, source_minute, 1)
    dst1 = near_matches(fragments, parser.TOEI_ASAKUSA, calendar, True, target_minute, 1)
    src2 = near_matches(fragments, parser.KEIKYU_MAIN, calendar, False, source_minute, 2)
    dst2 = near_matches(fragments, parser.TOEI_ASAKUSA, calendar, True, target_minute, 2)

    if len(src0) == 1 and len(dst0) == 1:
        reason = 'exact-singleton-both'
    elif not src0 and not dst0:
        reason = 'missing-both-exact'
    elif not src0:
        reason = 'missing-keikyu-source-exact'
    elif not dst0:
        reason = 'missing-toei-target-exact'
    elif len(src0) > 1 and len(dst0) > 1:
        reason = 'ambiguous-both-exact'
    elif len(src0) > 1:
        reason = 'ambiguous-keikyu-source-exact'
    else:
        reason = 'ambiguous-toei-target-exact'

    return {
        'reason': reason,
        'calendar': calendar,
        'page': candidate.get('pdfPage'),
        'columnX': candidate.get('columnX'),
        'sourceMinute': source_minute,
        'targetMinute': target_minute,
        'trainNumber': candidate.get('boundaryTrainNumber') or '',
        'sourceExact': [row.get('id') for row in src0],
        'targetExact': [row.get('id') for row in dst0],
        'sourceWithin1': [row.get('id') for row in src1],
        'targetWithin1': [row.get('id') for row in dst1],
        'sourceWithin2': [row.get('id') for row in src2],
        'targetWithin2': [row.get('id') for row in dst2],
    }


def main():
    fragments = parser.load_fragments(Path('data/transit-v2/fragments'))
    all_rows = []
    inventory = {}
    for calendar, url in (
        ('weekday', parser.DEFAULT_WEEKDAY_URL),
        ('holiday', parser.DEFAULT_HOLIDAY_URL),
    ):
        candidates = parser.extract_pdf(parser.fetch_pdf(url), calendar, url)
        reverse = [row for row in candidates if row.get('direction') == 'keikyu-to-toei']
        rows = [classify(row, fragments) for row in reverse]
        all_rows.extend(rows)
        inventory[calendar] = {
            'reverseCandidates': len(reverse),
            'keikyuSengakujiEndFragments': len(endpoint_inventory(fragments, parser.KEIKYU_MAIN, calendar, False)),
            'toeiSengakujiStartFragments': len(endpoint_inventory(fragments, parser.TOEI_ASAKUSA, calendar, True)),
        }

    reasons = Counter(row['reason'] for row in all_rows)
    near_source_only = sum(1 for row in all_rows if not row['sourceExact'] and row['sourceWithin1'])
    near_target_only = sum(1 for row in all_rows if not row['targetExact'] and row['targetWithin1'])
    near_source2 = sum(1 for row in all_rows if not row['sourceExact'] and row['sourceWithin2'])
    near_target2 = sum(1 for row in all_rows if not row['targetExact'] and row['targetWithin2'])
    payload = {
        'summary': {
            'totalReverseCandidates': len(all_rows),
            'reasons': dict(reasons),
            'missingExactButSourceWithin1Minute': near_source_only,
            'missingExactButTargetWithin1Minute': near_target_only,
            'missingExactButSourceWithin2Minutes': near_source2,
            'missingExactButTargetWithin2Minutes': near_target2,
            'inventory': inventory,
        },
        'examples': {
            reason: [row for row in all_rows if row['reason'] == reason][:12]
            for reason in reasons
        },
    }
    Path('/tmp/keikyu-reverse-diagnostic.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print(json.dumps(payload['summary'], ensure_ascii=False, indent=2))
    print('EXAMPLES', json.dumps(payload['examples'], ensure_ascii=False, indent=2))
    if not all_rows:
        raise RuntimeError('No Keikyu -> Toei official candidates were extracted')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
