#!/usr/bin/env python3
"""Audit the *whole* Keisei/Asakusa/Keikyu through-service system.

Important: this is deliberately not a "trains that touch Keisei" audit.
A system is complete only when every train on every in-scope railway is present
and exact same-train identity is known across every through boundary.  This
prevents a Keisei-led source snapshot from being mistaken for whole-system
coverage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCOPE_PATH = ROOT / "data/transit/keisei/system-scope.json"
MANIFEST_PATH = ROOT / "data/transit/manifest.json"
NETWORK_REPORT_PATH = ROOT / "data/transit/keisei/official-network-report.json"
INDEX_PATHS = {
    "keisei": ROOT / "data/transit/keisei/timetable-index.json",
    "toei": ROOT / "data/transit/toei/timetable-index.json",
    "keikyu": ROOT / "data/transit/keikyu/timetable-index.json",
    "hokuso": ROOT / "data/transit/hokuso/timetable-index.json",
    "shibayama": ROOT / "data/transit/shibayama/timetable-index.json",
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized_line_coverage(
    railway_id: str,
    row: dict[str, Any],
    manifest: dict[str, Any],
) -> str:
    trips = int(row.get("trips") or 0)
    inferred = int(row.get("inferredTrips") or 0)
    time_basis = str(row.get("timeBasis") or "")
    status = str(row.get("status") or "")

    if railway_id.startswith("manual.Railway:Hokuso"):
        operator_status = str((manifest.get("operators", {}).get("hokuso") or {}).get("timetableStatus") or "")
        if trips > 0 and operator_status == "partial":
            return "partial-exact-projection"
    if railway_id.startswith("manual.Railway:Shibayama"):
        operator_status = str((manifest.get("operators", {}).get("shibayama") or {}).get("timetableStatus") or "")
        if trips > 0 and operator_status == "partial":
            return "partial-exact-projection"

    if trips > 0 and ("train-timetable" in time_basis or "exact" in status or railway_id.startswith("odpt.Railway:Toei.")):
        return "exact"
    if inferred > 0:
        return "departure-only"
    return "missing"


def collect_indices() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for source, path in INDEX_PATHS.items():
        payload = load(path)
        for railway_id, row in (payload.get("lines") or {}).items():
            if not isinstance(row, dict):
                continue
            item = dict(row)
            item["_source"] = source
            result[str(railway_id)] = item
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", type=Path, help="write a machine-readable coverage report")
    parser.add_argument("--require-complete", action="store_true", help="fail unless whole-system coverage is complete")
    args = parser.parse_args()

    scope = load(SCOPE_PATH)
    manifest = load(MANIFEST_PATH)
    network_report = load(NETWORK_REPORT_PATH)
    indices = collect_indices()

    network_supported = set(network_report.get("supportedRailways") or [])
    from keikyu_internal_runtime import NETWORK, CORE
    internal_verified = False
    if NETWORK.exists():
        from verify_keikyu_internal_network import verify
        verify()
        internal_verified = True
    toei_audit_path = ROOT / 'docs/transit/toei-asakusa-independent-mother-set-audit.json'
    toei_audit = load(toei_audit_path) if toei_audit_path.exists() else {}
    toei_verified = (toei_audit.get('actualTripCount') == 1260
                     and not toei_audit.get('issues')
                     and int(indices.get('odpt.Railway:Toei.Asakusa', {}).get('trips') or 0) == 1260)
    boundary_verified = False
    if (ROOT / 'data/transit/toei/timetables/official-through-network.json').exists():
        from verify_asakusa_boundary_network import verify as verify_asakusa
        from verify_sengakuji_runtime import verify as verify_sengakuji
        verify_asakusa()
        verify_sengakuji()
        boundary_verified = True
    northern_verified = False
    if (ROOT / 'data/transit/hokuso/official-independent-inventory.json.gz').exists():
        from verify_hokuso_independent_inventory import verify as verify_hokuso
        from audit_shibayama_independent_inventory import verify as verify_shibayama
        verify_hokuso()
        verify_shibayama()
        from audit_keisei_exact_network import load_builder, build_station_names, audit_source_network, audit_all_projections, audit_metadata
        builder = load_builder()
        names = build_station_names(builder)
        audit_source_network(builder, names)
        keisei, hokuso, shibayama = audit_all_projections(names)
        audit_metadata(keisei, hokuso, shibayama)
        northern_verified = True
    rows: list[dict[str, Any]] = []
    errors: list[str] = []

    for configured in scope.get("railways") or []:
        railway_id = str(configured.get("id") or "")
        if not railway_id:
            errors.append("scope contains a railway without id")
            continue
        index_row = indices.get(railway_id)
        if index_row is None:
            actual_line_coverage = "missing"
            errors.append(f"missing timetable index for {railway_id}")
        else:
            actual_line_coverage = normalized_line_coverage(railway_id, index_row, manifest)

        if railway_id.startswith("odpt.Railway:Keisei."):
            actual_identity = "exact-for-all-keisei-source-trains"
        elif railway_id in network_supported:
            actual_identity = "keisei-led-exact-only"
        else:
            actual_identity = "none"

        if railway_id == 'odpt.Railway:Toei.Asakusa' and toei_verified:
            actual_line_coverage = 'exact-independent-1260-verified'
            actual_identity = 'exact-all-independent-asakusa-trains' if boundary_verified else 'cross-boundary-reconciliation-incomplete'
        if railway_id in CORE and internal_verified:
            actual_line_coverage = 'exact'
            actual_identity = 'internal-exact-all-published-sengakuji-continuations' if boundary_verified else 'internal-exact-external-reconciliation-incomplete'
        if northern_verified and railway_id.startswith('manual.Railway:Hokuso.'):
            actual_line_coverage = 'exact'
            actual_identity = 'exact-all-independent-hokuso-trains'
        if northern_verified and railway_id.startswith('manual.Railway:Shibayama.'):
            actual_line_coverage = 'exact'
            actual_identity = 'exact-all-independent-shibayama-trains'

        declared_line = str(configured.get("lineTimetableCoverage") or "")
        declared_identity = str(configured.get("sameTrainCoverage") or "")
        if declared_line != actual_line_coverage:
            errors.append(
                f"stale scope line coverage for {railway_id}: declared={declared_line} actual={actual_line_coverage}"
            )
        if declared_identity != actual_identity:
            errors.append(
                f"stale scope identity coverage for {railway_id}: declared={declared_identity} actual={actual_identity}"
            )

        rows.append(
            {
                "railway": railway_id,
                "label": configured.get("label"),
                "lineTimetableCoverage": actual_line_coverage,
                "sameTrainCoverage": actual_identity,
                "indexedTrips": int((index_row or {}).get("trips") or 0),
                "inferredTrips": int((index_row or {}).get("inferredTrips") or 0),
            }
        )

    all_line_exact = all(row["lineTimetableCoverage"] in {"exact", "exact-independent-1260-verified"} for row in rows)
    proven_identities = {'exact-all-in-scope-trains'}
    if northern_verified and boundary_verified and internal_verified and toei_verified:
        proven_identities.update({'exact-for-all-keisei-source-trains', 'exact-all-independent-asakusa-trains',
            'internal-exact-all-published-sengakuji-continuations', 'exact-all-independent-hokuso-trains',
            'exact-all-independent-shibayama-trains'})
    all_identity_exact = all(row["sameTrainCoverage"] in proven_identities for row in rows)
    complete = bool(rows) and all_line_exact and all_identity_exact and not errors

    if scope.get("status") == "complete" and not complete:
        errors.append("scope is marked complete even though whole-system requirements are not satisfied")

    report = {
        "version": 1,
        "scopeId": scope.get("id"),
        "complete": complete,
        "definition": "all trains on all in-scope railways + exact cross-boundary same-train identity",
        "railwayCount": len(rows),
        "allLineTimetablesExact": all_line_exact,
        "allSameTrainIdentitiesExact": all_identity_exact,
        "keiseiLedNetworkTripCount": network_report.get("networkTripCount"),
        "keiseiLedSourceTrainCount": network_report.get("sourceTrainCount"),
        "railways": rows,
        "blockingItems": scope.get("blockingItems") or [],
        "errors": errors,
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if errors:
        return 1
    if args.require_complete and not complete:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
