#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import keikyu_cross_page_zushi_evidence as legacy
import keikyu_schedule_all_zushi_evidence as local

MARKER = 'official-previous-publication-section-chain-two-exact-station-times-v2'


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def validate_cross_page_sources_v2(stop_times: dict[str, Any], audit: dict[str, Any]) -> None:
    local.validate_official_dataset(stop_times)
    if audit.get('kind') != 'keikyu-official-section-cross-page-identity-audit':
        raise RuntimeError('unexpected section-aware cross-page audit kind')
    source_sha = str((stop_times.get('source') or {}).get('sha256') or '')
    audit_sha = str(audit.get('sourceSha256') or '')
    if not source_sha or source_sha != audit_sha:
        raise RuntimeError('cross-page audit source SHA does not match section-local stop-time source')
    if audit.get('issues') not in ([], None):
        raise RuntimeError('section-aware cross-page audit contains safety issues')
    policy = audit.get('identityPolicy') or {}
    required_true = {
        'officialPreviousPublicationPageRequired',
        'officialPreviousTrainNumberRequired',
        'uniqueTargetFragmentRequired',
        'pageSectionLocalFragmentMetadataMustMatch',
        'officialSectionIdentityRequired',
    }
    required_false = {
        'clockTimeUsedForIdentity',
        'destinationUsedForIdentity',
        'branchingAllowedForPromotion',
        'cyclesAllowedForPromotion',
    }
    if any(policy.get(key) is not True for key in required_true):
        raise RuntimeError('unsafe section-aware explicit previous-publication policy')
    if any(policy.get(key) is not False for key in required_false):
        raise RuntimeError('unsafe section-aware cross-page identity policy')
    if int(policy.get('runtimeSameTrainPromotions') or 0) != 0:
        raise RuntimeError('cross-page audit unexpectedly contains runtime promotions')
    if audit.get('branchingTargets') not in ({}, None):
        raise RuntimeError('cross-page graph branches')
    if audit.get('multiplePreviousSources') not in ({}, None):
        raise RuntimeError('cross-page graph has multiple previous sources')
    if audit.get('cycles') not in ([], None):
        raise RuntimeError('cross-page graph contains cycles')


def upgrade_entry(row: dict[str, Any]) -> dict[str, Any]:
    upgraded = dict(row)
    evidence = [str(value) for value in upgraded.get('evidence') or []]
    evidence = [value for value in evidence if value != legacy.MARKER]
    if MARKER not in evidence:
        evidence.append(MARKER)
    upgraded['evidence'] = evidence

    source_official = str(upgraded.get('sourceOfficialFragment') or '')
    target_official = str(upgraded.get('targetOfficialFragment') or '')
    if ':s' not in source_official or ':s' not in target_official:
        raise RuntimeError('cross-page proof uses non-section-aware official fragment')
    for edge in upgraded.get('officialPreviousPublicationPath') or []:
        if ':s' not in str(edge.get('fromFragment') or '') or ':s' not in str(edge.get('toFragment') or ''):
            raise RuntimeError('cross-page proof path contains non-section-aware official fragment')

    policy = dict(upgraded.get('matchPolicy') or {})
    policy.pop('pageLocalFragmentMetadataMustMatch', None)
    policy['pageSectionLocalFragmentMetadataMustMatch'] = True
    policy['officialSectionIdentityRequired'] = True
    upgraded['matchPolicy'] = policy
    return upgraded


def upgrade_summary(summary: dict[str, Any]) -> dict[str, Any]:
    output = dict(summary)
    output['proofMode'] = 'explicit-previous-publication-section-chain-two-point'
    policy = dict(output.get('policy') or {})
    policy.pop('pageLocalFragmentMetadataMustMatch', None)
    policy['pageSectionLocalFragmentMetadataMustMatch'] = True
    policy['officialSectionIdentityRequired'] = True
    output['policy'] = policy
    return output


def merge_payload(existing: dict[str, Any], entries: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    output = dict(existing or {})
    old_entries = [row for row in output.get('entries') or [] if isinstance(row, dict)]
    by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for row in old_entries + entries:
        key = (str(row.get('fromFragment') or ''), str(row.get('toFragment') or ''))
        if all(key):
            by_pair[key] = row
    policy = dict(output.get('policy') or {})
    policy.update({
        'officialSamePrintedColumnRequired': True,
        'twoExactPublishedStationTimesRequired': True,
        'singletonFragmentMatchRequiredAtBothPoints': True,
        'trainNumberAloneMayEstablishIdentity': False,
        'timeProximityAloneMayEstablishIdentity': False,
        'officialPreviousPublicationPageAndTrainNumberRequiredForCrossPage': True,
        'uniquePreviousPublicationTargetRequiredForCrossPage': True,
        'pageSectionLocalFragmentMetadataMustMatchForCrossPage': True,
        'officialSectionIdentityRequiredForCrossPage': True,
        'crossPageGraphMustBeNonBranchingAcyclic': True,
        'directedOfficialContinuationPathRequired': True,
    })
    output.update({
        'entries': list(by_pair.values()),
        'policy': policy,
        'latestCrossPageSummary': summary,
    })
    return output


def build_entries(
    coverage: dict[str, Any],
    fragments: list[dict[str, Any]],
    stop_times: dict[str, Any],
    audit: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    legacy.validate_cross_page_sources = validate_cross_page_sources_v2
    old_marker = legacy.MARKER
    try:
        legacy.MARKER = MARKER
        entries, summary = legacy.build_entries(coverage, fragments, stop_times, audit)
    finally:
        legacy.MARKER = old_marker
    upgraded_entries = [upgrade_entry(row) for row in entries]
    return upgraded_entries, upgrade_summary(summary)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--coverage', default='data/transit-v2/coverage.json')
    ap.add_argument('--fragments', default='data/transit-v2/fragments/keikyu.json')
    ap.add_argument('--official-stop-times', required=True)
    ap.add_argument('--cross-page-audit', required=True)
    ap.add_argument('--existing', default='data/transit-v2/keikyu-internal-official-train-evidence.json')
    ap.add_argument('--output', default='data/transit-v2/keikyu-internal-official-train-evidence.json')
    ap.add_argument('--report', required=True)
    args = ap.parse_args()

    coverage = load_json(Path(args.coverage), {}) or {}
    fragment_payload = load_json(Path(args.fragments), {}) or {}
    fragments = [row for row in fragment_payload.get('fragments') or [] if isinstance(row, dict) and row.get('id')]
    stop_times = load_json(Path(args.official_stop_times), {}) or {}
    audit = load_json(Path(args.cross_page_audit), {}) or {}
    entries, summary = build_entries(coverage, fragments, stop_times, audit)
    existing = load_json(Path(args.existing), {}) or {}
    output = merge_payload(existing, entries, summary)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    Path(args.report).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
