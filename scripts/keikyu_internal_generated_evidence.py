#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import keikyu_official_train_evidence as calendar_parser

MAIN = 'odpt.Railway:Keikyu.Main'
AIRPORT = 'odpt.Railway:Keikyu.Airport'
KURIHAMA = 'odpt.Railway:Keikyu.Kurihama'
ZUSHI = 'odpt.Railway:Keikyu.Zushi'
BOUNDARY_ID = 'keikyu-main-airport-kamata'
KURIHAMA_BOUNDARY_ID = 'keikyu-main-kurihama-horinouchi'
ZUSHI_BOUNDARY_ID = 'keikyu-main-zushi-kanazawahakkei'
LEGACY_MARKER = 'same-printed-column-includes-shinagawa-and-haneda'
MARKER = 'same-printed-column-two-exact-station-times'
SECTION_LOCAL_MARKER = 'schedule-all-page-section-column-v2'
CROSS_PAGE_MARKER = 'official-previous-publication-section-chain-two-exact-station-times-v2'
DEPRECATED_UNBANDED_MARKERS = {
    'schedule-all-page-column-v1',
    'official-previous-publication-chain-two-exact-station-times-v1',
}
CROSS_PAGE_REFERENCE_EVIDENCE = 'keikyu-official-previous-publication-page-and-train-number'
RESOLVABLE_UNRESOLVED_KINDS = {
    'ambiguous-boundary-fragment-alignment',
    'missing-boundary-train-identity-evidence',
}

BOUNDARY_SPECS: dict[str, dict[str, Any]] = {
    BOUNDARY_ID: {
        'station': '京急蒲田',
        'pairs': {(MAIN, AIRPORT), (AIRPORT, MAIN)},
    },
    KURIHAMA_BOUNDARY_ID: {
        'station': '堀ノ内',
        'pairs': {(KURIHAMA, MAIN), (MAIN, KURIHAMA)},
    },
    ZUSHI_BOUNDARY_ID: {
        'station': '金沢八景',
        'pairs': {(ZUSHI, MAIN), (MAIN, ZUSHI)},
    },
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def runtime_calendar(fragment: dict[str, Any]) -> str:
    raw = fragment.get('calendar')
    if calendar_parser.calendar_matches(raw, 'weekday'):
        return 'weekday'
    if calendar_parser.calendar_matches(raw, 'holiday'):
        return 'holiday'
    return ''


def cross_page_global_policy_safe(policy: dict[str, Any]) -> bool:
    return (
        policy.get('officialPreviousPublicationPageAndTrainNumberRequiredForCrossPage') is True
        and policy.get('uniquePreviousPublicationTargetRequiredForCrossPage') is True
        and policy.get('pageSectionLocalFragmentMetadataMustMatchForCrossPage') is True
        and policy.get('crossPageGraphMustBeNonBranchingAcyclic') is True
        and policy.get('directedOfficialContinuationPathRequired') is True
        and policy.get('officialSectionIdentityRequiredForCrossPage') is True
    )


def validate_section_local_entry(entry: dict[str, Any]) -> str:
    match_policy = entry.get('matchPolicy') or {}
    required_true = {
        'officialSamePrintedColumnRequired',
        'twoExactPublishedStationTimesRequired',
        'singletonFragmentMatchRequiredAtBothPoints',
        'officialPageSectionColumnIsExactLocalIdentity',
        'officialSectionIdentityRequired',
        'literalPrintedCalendarRequired',
        'runtimeCalendarMustMatchOfficialPrintedCalendar',
        'sharedPublishedDestinationUsedOnlyForSearch',
        'candidateFragmentGapUsedOnlyForSearch',
    }
    if any(match_policy.get(key) is not True for key in required_true):
        return 'unsafe-section-local-entry-policy'
    if match_policy.get('calendarMayBeInferredFromPageNumber') is not False:
        return 'unsafe-section-local-calendar-inference-policy'
    if match_policy.get('crossPageIdentityUsed') is not False:
        return 'unsafe-section-local-cross-page-policy'
    if match_policy.get('trainNumberAloneMayEstablishIdentity') is not False:
        return 'unsafe-section-local-train-number-policy'
    if match_policy.get('timeProximityAloneMayEstablishIdentity') is not False:
        return 'unsafe-section-local-time-policy'

    official_fragment = str(entry.get('officialPageSectionLocalFragment') or '')
    page = entry.get('pdfPage')
    section = entry.get('pdfSection')
    column = entry.get('pdfColumn')
    official_calendar = str(entry.get('officialPrintedCalendar') or '')
    evidence_calendar = str(entry.get('calendar') or '')
    anchors = entry.get('officialAnchors') or []
    if official_calendar not in {'weekday', 'holiday'}:
        return 'missing-literal-printed-calendar'
    if evidence_calendar != official_calendar:
        return 'evidence-calendar-official-calendar-mismatch'
    if not official_fragment or ':s' not in official_fragment:
        return 'missing-section-aware-official-fragment-id'
    if not isinstance(page, int) or page <= 0:
        return 'invalid-section-local-pdf-page'
    if not isinstance(section, int) or section < 0:
        return 'invalid-section-local-pdf-section'
    if not isinstance(column, int) or column < 0:
        return 'invalid-section-local-pdf-column'
    expected = f'keikyu-official-pdf:p{page:03d}:s{section:02d}:c{column:02d}'
    if official_fragment != expected:
        return 'section-local-fragment-metadata-mismatch'
    if not isinstance(anchors, list) or len(anchors) != 2:
        return 'missing-section-local-two-point-anchors'
    return ''


def validate_cross_page_entry(entry: dict[str, Any]) -> str:
    match_policy = entry.get('matchPolicy') or {}
    required_true = {
        'crossPageIdentityUsed',
        'officialPreviousPublicationPageAndTrainNumberRequired',
        'uniquePreviousPublicationTargetRequired',
        'pageSectionLocalFragmentMetadataMustMatch',
        'crossPageGraphMustBeNonBranchingAcyclic',
        'directedOfficialContinuationPathRequired',
        'officialSectionIdentityRequired',
        'twoExactPublishedStationTimesRequired',
        'singletonFragmentMatchRequiredAtBothPoints',
        'sharedPublishedDestinationUsedOnlyForSearch',
        'candidateFragmentGapUsedOnlyForSearch',
    }
    if any(match_policy.get(key) is not True for key in required_true):
        return 'unsafe-cross-page-entry-policy'
    if match_policy.get('trainNumberAloneMayEstablishIdentity') is not False:
        return 'unsafe-cross-page-train-number-policy'
    if match_policy.get('timeProximityAloneMayEstablishIdentity') is not False:
        return 'unsafe-cross-page-time-policy'

    start = str(entry.get('sourceOfficialFragment') or '')
    target = str(entry.get('targetOfficialFragment') or '')
    root = str(entry.get('officialPhysicalComponentRoot') or '')
    path = entry.get('officialPreviousPublicationPath') or []
    anchors = entry.get('officialAnchors') or []
    if not start or not target or start == target or not root:
        return 'invalid-cross-page-official-endpoints'
    if ':s' not in start or ':s' not in target:
        return 'missing-section-aware-official-fragment-id'
    if not isinstance(path, list) or not path:
        return 'missing-cross-page-official-reference-path'
    if not isinstance(anchors, list) or len(anchors) != 2:
        return 'missing-cross-page-two-point-anchors'

    cursor = start
    seen = {cursor}
    for edge in path:
        if not isinstance(edge, dict):
            return 'invalid-cross-page-reference-edge'
        source = str(edge.get('fromFragment') or '')
        nxt = str(edge.get('toFragment') or '')
        previous_number = str(edge.get('previousTrainNumber') or '')
        previous_page = edge.get('previousPrintedPage')
        evidence = str(edge.get('evidence') or '')
        if source != cursor or not nxt:
            return 'discontinuous-cross-page-reference-path'
        if ':s' not in source or ':s' not in nxt:
            return 'unbanded-fragment-in-cross-page-reference-path'
        if evidence != CROSS_PAGE_REFERENCE_EVIDENCE:
            return 'missing-explicit-previous-publication-evidence'
        if not previous_number or not isinstance(previous_page, int) or previous_page <= 0:
            return 'missing-explicit-previous-publication-metadata'
        if nxt in seen:
            return 'cyclic-cross-page-reference-path'
        seen.add(nxt)
        cursor = nxt
    if cursor != target:
        return 'cross-page-reference-path-target-mismatch'
    return ''


def apply_generated_evidence(
    fragments: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    indexes: dict[str, Any],
    evidence_path: Path,
) -> list[dict[str, Any]]:
    payload = load_json(evidence_path)
    if not payload:
        return list(edges)
    policy = payload.get('policy') or {}
    if (
        policy.get('trainNumberAloneMayEstablishIdentity') is not False
        or policy.get('timeProximityAloneMayEstablishIdentity') is not False
        or policy.get('officialSamePrintedColumnRequired') is not True
        or policy.get('twoExactPublishedStationTimesRequired') is not True
        or policy.get('singletonFragmentMatchRequiredAtBothPoints') is not True
    ):
        unresolved.append({'kind': 'keikyu-internal-generated-evidence-unsafe-policy', 'path': str(evidence_path)})
        return list(edges)

    by_id = {str(row.get('id') or ''): row for row in fragments if row.get('id')}
    output = list(edges)
    seen = {(str(row.get('fromFragment') or ''), str(row.get('toFragment') or '')) for row in output}
    resolved_sources: set[str] = set()

    for entry in payload.get('entries') or []:
        if not isinstance(entry, dict) or entry.get('matchStatus') != 'matched-singleton':
            continue
        eid = str(entry.get('id') or '')
        source_id = str(entry.get('fromFragment') or '')
        target_id = str(entry.get('toFragment') or '')
        source = by_id.get(source_id)
        target = by_id.get(target_id)
        evidence = [str(value) for value in entry.get('evidence') or []]
        evidence_set = set(evidence)
        source_matches = [str(value) for value in entry.get('sourceMatches') or []]
        target_matches = [str(value) for value in entry.get('targetMatches') or []]
        pair = (str(entry.get('fromRailway') or ''), str(entry.get('toRailway') or ''))
        boundary_id = str(entry.get('boundaryId') or '')
        spec = BOUNDARY_SPECS.get(boundary_id)
        is_same_column = bool({MARKER, LEGACY_MARKER} & evidence_set)
        is_section_local = SECTION_LOCAL_MARKER in evidence_set
        is_cross_page = CROSS_PAGE_MARKER in evidence_set

        reason = ''
        if evidence_set & DEPRECATED_UNBANDED_MARKERS:
            reason = 'deprecated-unbanded-official-identity'
        elif not spec or (not is_same_column and not is_cross_page):
            reason = 'missing-supported-official-identity-marker'
        elif is_section_local:
            reason = validate_section_local_entry(entry)
        elif is_cross_page and not cross_page_global_policy_safe(policy):
            reason = 'unsafe-cross-page-global-policy'
        elif is_cross_page:
            reason = validate_cross_page_entry(entry)

        if not reason and source_matches != [source_id]:
            reason = 'non-singleton-recorded-match'
        elif not reason and target_matches != [target_id]:
            reason = 'non-singleton-recorded-match'
        elif not reason and (not source or not target):
            reason = 'stale-fragment-reference'
        elif not reason and pair not in spec['pairs']:
            reason = 'unexpected-railway-pair'
        elif not reason and (
            str(source.get('railway') or '') != pair[0]
            or str(target.get('railway') or '') != pair[1]
        ):
            reason = 'fragment-railway-mismatch'
        elif not reason and is_section_local:
            expected_calendar = str(entry.get('officialPrintedCalendar') or '')
            source_calendar = runtime_calendar(source)
            target_calendar = runtime_calendar(target)
            if source_calendar != expected_calendar or target_calendar != expected_calendar:
                reason = 'runtime-calendar-official-calendar-mismatch'
        if not reason:
            boundary = next((
                row for row in indexes.get('graph', {}).get(pair[0], [])
                if str(row.get('toRailway') or '') == pair[1]
                and str(row.get('boundaryId') or '') == boundary_id
            ), None)
            if not boundary:
                reason = 'unverified-operational-boundary'

        if reason:
            unresolved.append({
                'kind': 'keikyu-internal-generated-evidence-rejected',
                'evidenceId': eid,
                'reason': reason,
                'fromFragment': source_id,
                'toFragment': target_id,
            })
            continue

        key = (source_id, target_id)
        if key not in seen:
            seen.add(key)
            identity_evidence = (
                'keikyu-official-internal-explicit-section-cross-page-two-point'
                if is_cross_page
                else (
                    'keikyu-official-internal-same-section-calendar-column-two-point'
                    if is_section_local
                    else 'keikyu-official-internal-same-column-two-point'
                )
            )
            output.append({
                'fromFragment': source_id,
                'toFragment': target_id,
                'classification': 'same-train',
                'identityLevel': 'evidence-backed',
                'evidence': [identity_evidence, eid],
                'sourceUrls': [str(entry.get('sourceUrl'))] if entry.get('sourceUrl') else [],
                'boundary': {
                    'station': spec['station'],
                    'fromRailway': pair[0],
                    'toRailway': pair[1],
                },
            })
        resolved_sources.add(source_id)

    if resolved_sources:
        unresolved[:] = [
            row for row in unresolved
            if not (
                row.get('kind') in RESOLVABLE_UNRESOLVED_KINDS
                and str(row.get('fragment') or '') in resolved_sources
            )
        ]
    return output
