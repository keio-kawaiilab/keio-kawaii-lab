#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import keikyu_official_train_evidence as parser

SERVICES = ('weekday', 'holiday')


def build_endpoint_indexes(fragments):
    indexes = defaultdict(lambda: defaultdict(dict))
    inventory = Counter()
    for fragment in fragments:
        railway = str(fragment.get('railway') or '')
        if railway not in {parser.KEIKYU_MAIN, parser.TOEI_ASAKUSA}:
            continue
        for calendar in SERVICES:
            if not parser.calendar_matches(fragment.get('calendar'), calendar):
                continue
            for first in (False, True):
                stop = parser.endpoint(fragment, first)
                if not stop or not str(stop[0] or '').endswith('.Sengakuji'):
                    continue
                key = (railway, calendar, first)
                inventory[key] += 1
                for value in stop[1:3]:
                    if isinstance(value, (int, float)):
                        minute = int(value) % 1440
                        indexes[key][minute][str(fragment.get('id'))] = fragment
    return indexes, inventory


def indexed_matches(indexes, railway, calendar, first, minute, tolerance):
    bucket = {}
    table = indexes[(railway, calendar, first)]
    center = int(minute) % 1440
    for delta in range(-tolerance, tolerance + 1):
        for fragment_id, fragment in table.get((center + delta) % 1440, {}).items():
            bucket[fragment_id] = fragment
    return list(bucket.values())


def classify(candidate, indexes):
    calendar = str(candidate['calendar'])
    source_minute = int(candidate['sourceBoundaryMinute'])
    target_minute = int(candidate['targetBoundaryMinute'])

    src0 = indexed_matches(indexes, parser.KEIKYU_MAIN, calendar, False, source_minute, 0)
    dst0 = indexed_matches(indexes, parser.TOEI_ASAKUSA, calendar, True, target_minute, 0)
    src1 = indexed_matches(indexes, parser.KEIKYU_MAIN, calendar, False, source_minute, 1)
    dst1 = indexed_matches(indexes, parser.TOEI_ASAKUSA, calendar, True, target_minute, 1)
    src2 = indexed_matches(indexes, parser.KEIKYU_MAIN, calendar, False, source_minute, 2)
    dst2 = indexed_matches(indexes, parser.TOEI_ASAKUSA, calendar, True, target_minute, 2)

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
    indexes, endpoint_inventory = build_endpoint_indexes(fragments)
    all_rows = []
    inventory = {}
    for calendar, url in (
        ('weekday', parser.DEFAULT_WEEKDAY_URL),
        ('holiday', parser.DEFAULT_HOLIDAY_URL),
    ):
        candidates = parser.extract_pdf(parser.fetch_pdf(url), calendar, url)
        reverse = [row for row in candidates if row.get('direction') == 'keikyu-to-toei']
        rows = [classify(row, indexes) for row in reverse]
        all_rows.extend(rows)
        inventory[calendar] = {
            'reverseCandidates': len(reverse),
            'keikyuSengakujiEndFragments': endpoint_inventory[(parser.KEIKYU_MAIN, calendar, False)],
            'toeiSengakujiStartFragments': endpoint_inventory[(parser.TOEI_ASAKUSA, calendar, True)],
        }

    reasons = Counter(row['reason'] for row in all_rows)
    payload = {
        'summary': {
            'totalReverseCandidates': len(all_rows),
            'reasons': dict(reasons),
            'missingExactButSourceWithin1Minute': sum(1 for row in all_rows if not row['sourceExact'] and row['sourceWithin1']),
            'missingExactButTargetWithin1Minute': sum(1 for row in all_rows if not row['targetExact'] and row['targetWithin1']),
            'missingExactButSourceWithin2Minutes': sum(1 for row in all_rows if not row['sourceExact'] and row['sourceWithin2']),
            'missingExactButTargetWithin2Minutes': sum(1 for row in all_rows if not row['targetExact'] and row['targetWithin2']),
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
