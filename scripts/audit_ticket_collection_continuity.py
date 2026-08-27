#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import requests

REGISTRY_PATH = Path("data/ticket-source-registry.json")
HISTORY_PATH = Path("data/ticket-history.json")
LIVE_PATH = Path("data/live-events.json")
DEFAULT_REPORT_PATH = Path("data/ticket-collection-health.json")
JST = ZoneInfo("Asia/Tokyo")
SPECIAL_CATEGORIES = {"release-event", "large-benefit", "benefit-event", "online-benefit"}
PLAYGUIDE_KEYS = {"pia", "eplus", "lawson"}
FC_WORDS = ("FC", "FANCLUB", "ファンクラブ")


def load(path: Path, fallback: dict | None = None) -> dict:
    if not path.exists():
        return dict(fallback or {})
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def clean(value: object) -> str:
    return str(value or "").strip()


def host(url: object) -> str:
    try:
        return (urlparse(clean(url)).hostname or "").lower()
    except ValueError:
        return ""


def mapped_source(url: object, registry: dict) -> str | None:
    source_host = host(url)
    for known_host, key in (registry.get("hostRules") or {}).items():
        known = str(known_host).lower()
        if source_host == known or source_host.endswith("." + known):
            return str(key)
    return None


def candidate_urls(event: dict) -> list[str]:
    result: list[str] = []
    for key in ("applicationWindowSource", "deadlineSource", "url"):
        value = clean(event.get(key))
        if value and value not in result:
            result.append(value)
    for value in event.get("urls") or []:
        text = clean(value)
        if text and text not in result:
            result.append(text)
    return result


def direct_source(event: dict, registry: dict) -> tuple[str | None, str | None]:
    sources = registry.get("sources") or {}
    for url in candidate_urls(event):
        key = mapped_source(url, registry)
        config = sources.get(key) if key else None
        if isinstance(config, dict) and config.get("publishPolicy") == "direct":
            return url, key
    return None, None


def event_dates(event: dict) -> list[str]:
    values: list[str] = []
    for row in event.get("schedule") or []:
        if isinstance(row, dict):
            day = clean(row.get("date"))[:10]
            if day and day not in values:
                values.append(day)
    for value in event.get("eventDates") or []:
        day = clean(value)[:10]
        if day and day not in values:
            values.append(day)
    if not values:
        day = clean(event.get("eventDate"))[:10]
        if day:
            values.append(day)
    return values


def parse_iso_day(value: object) -> date | None:
    try:
        return date.fromisoformat(clean(value)[:10])
    except ValueError:
        return None


def is_ticket_row(event: dict) -> bool:
    return clean(event.get("ticketType")) not in {"", "現在受付なし"} and bool(
        event.get("applyStart") or event.get("applyEnd")
    )


def is_active(event: dict, today: date) -> bool:
    end = parse_iso_day(event.get("applyEnd"))
    return bool(end and end >= today and is_ticket_row(event))


def source_endpoints(registry: dict) -> list[dict]:
    sources = registry.get("sources") or {}
    checks: list[dict] = []
    group_source = sources.get("group-official") or {}
    for group, config in (group_source.get("groups") or {}).items():
        if config.get("newsUrl"):
            checks.append({"key": f"group-official:{group}:news", "url": config["newsUrl"], "marker": "/news/detail/"})
        if config.get("scheduleUrl"):
            checks.append({"key": f"group-official:{group}:schedule", "url": config["scheduleUrl"], "marker": "/live_information/detail/"})
    central = sources.get("kawaii-lab-fc") or {}
    if central.get("newsUrl"):
        checks.append({"key": "kawaii-lab-fc:news", "url": central["newsUrl"], "marker": "/news/detail/"})
    for provider in ("pia", "eplus"):
        for group, url in ((sources.get(provider) or {}).get("artistUrls") or {}).items():
            checks.append({"key": f"{provider}:{group}", "url": url, "marker": None})
    lawson = sources.get("lawson") or {}
    base = clean(lawson.get("searchBaseUrl"))
    if base:
        for group in (group_source.get("groups") or {}):
            sep = "&" if "?" in base else "?"
            checks.append({"key": f"lawson:{group}", "url": f"{base}{sep}keyword={quote(group)}", "marker": None})
    return checks


def fetch_check(session: requests.Session, url: str, marker: str | None) -> tuple[bool, str, int | None]:
    last_error = "unknown"
    for attempt in range(3):
        try:
            response = session.get(url, timeout=18)
            status = response.status_code
            response.raise_for_status()
            text = response.text
            if len(text) < 400:
                return False, f"response too small ({len(text)} bytes)", status
            if marker and marker not in text:
                return False, f"expected marker {marker!r} missing", status
            return True, "ok", status
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < 2:
                time.sleep(0.7 * (attempt + 1))
    return False, last_error, None


def live_history_gaps(live: dict, history: dict, registry: dict) -> list[dict]:
    entries = [x for x in history.get("entries") or [] if isinstance(x, dict)]
    gaps: list[dict] = []
    for event in live.get("events") or []:
        if not isinstance(event, dict) or not is_ticket_row(event):
            continue
        source_url, source_key = direct_source(event, registry)
        if not source_url or not source_key:
            continue
        for day in event_dates(event):
            matched = False
            for item in entries:
                if clean(item.get("group")) != clean(event.get("group")):
                    continue
                if clean(item.get("eventDate"))[:10] != day:
                    continue
                if clean(item.get("ticketType")) != clean(event.get("ticketType")):
                    continue
                if clean(item.get("sourceKey")) != source_key:
                    continue
                live_end = clean(event.get("applyEnd"))
                hist_end = clean(item.get("applyEnd"))
                if live_end and hist_end and live_end != hist_end:
                    continue
                live_start = clean(event.get("applyStart"))
                hist_start = clean(item.get("applyStart"))
                if live_start and hist_start and live_start != hist_start:
                    continue
                matched = True
                break
            if not matched:
                gaps.append({
                    "group": event.get("group"),
                    "eventDate": day,
                    "ticketType": event.get("ticketType"),
                    "sourceKey": source_key,
                    "sourceUrl": source_url,
                    "applyStart": event.get("applyStart"),
                    "applyEnd": event.get("applyEnd"),
                })
    return gaps


def flow_coverage(live: dict, history: dict, today: date) -> dict:
    by_group_day: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in history.get("entries") or []:
        if not isinstance(item, dict) or not item.get("flowEligible"):
            continue
        by_group_day[(clean(item.get("group")), clean(item.get("eventDate"))[:10])].append(item)

    no_history: list[dict] = []
    suspicious_missing_fc: list[dict] = []
    checked: set[tuple[str, str]] = set()
    for event in live.get("events") or []:
        if not isinstance(event, dict):
            continue
        if clean(event.get("eventScope")) != "kawaii-lab":
            continue
        if clean(event.get("eventCategory")) in SPECIAL_CATEGORIES:
            continue
        for day in event_dates(event):
            parsed = parse_iso_day(day)
            if parsed and parsed < today:
                continue
            key = (clean(event.get("group")), day)
            if key in checked:
                continue
            checked.add(key)
            rows = by_group_day.get(key, [])
            if not rows:
                no_history.append({"group": key[0], "eventDate": day, "title": event.get("eventTitle") or event.get("title")})
                continue
            has_playguide = any(clean(x.get("sourceKey")) in PLAYGUIDE_KEYS or clean(x.get("ticketProvider")) in PLAYGUIDE_KEYS for x in rows)
            has_fc = any(
                clean(x.get("saleFamily")) in {"group-fc", "kawaii-lab-fc"}
                or any(word.lower() in clean(x.get("ticketType")).lower() for word in FC_WORDS)
                for x in rows
            )
            if has_playguide and not has_fc:
                suspicious_missing_fc.append({
                    "group": key[0],
                    "eventDate": day,
                    "title": event.get("eventTitle") or event.get("title"),
                    "knownHistoryRows": len(rows),
                })
    return {
        "eligibleFuturePerformancesChecked": len(checked),
        "noHistory": no_history,
        "suspiciousMissingFcBeforePlayguide": suspicious_missing_fc,
    }


def active_rows(live: dict, today: date) -> list[dict]:
    rows = []
    for event in live.get("events") or []:
        if not isinstance(event, dict) or not is_active(event, today):
            continue
        provider = clean(event.get("ticketProvider") or event.get("primarySource") or event.get("sourceType")).lower()
        if provider not in PLAYGUIDE_KEYS:
            continue
        rows.append({
            "provider": provider,
            "group": event.get("group"),
            "eventDate": clean(event.get("eventDate"))[:10],
            "ticketType": event.get("ticketType"),
            "applyEnd": event.get("applyEnd"),
            "url": event.get("url"),
            "sourceStale": bool(event.get("sourceStale")),
        })
    return rows


def deep_link_failures(session: requests.Session, history: dict, today: date) -> list[dict]:
    urls: dict[str, dict] = {}
    for item in history.get("entries") or []:
        if not isinstance(item, dict):
            continue
        event_day = parse_iso_day(item.get("eventDate"))
        if event_day and event_day < today:
            continue
        url = clean(item.get("sourceUrl"))
        if url:
            urls.setdefault(url, {"sourceKey": item.get("sourceKey"), "eventDate": item.get("eventDate")})
    failures = []
    for url, meta in urls.items():
        ok, message, status = fetch_check(session, url, None)
        if not ok:
            failures.append({"url": url, "status": status, "error": message, **meta})
    return failures


def build_report(*, deep_links: bool = False) -> dict:
    registry = load(REGISTRY_PATH)
    history = load(HISTORY_PATH, {"entries": []})
    live = load(LIVE_PATH, {"events": []})
    previous = load(DEFAULT_REPORT_PATH, {})
    now = datetime.now(JST)
    today = now.date()

    session = requests.Session()
    session.headers.update({"User-Agent": "KeioKawaiiLabTicketIntegrityBot/1.0 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"})

    previous_checks = previous.get("sourceChecks") or {}
    source_checks: dict[str, dict] = {}
    source_errors: list[str] = []
    for spec in source_endpoints(registry):
        ok, message, status = fetch_check(session, spec["url"], spec.get("marker"))
        old = previous_checks.get(spec["key"]) if isinstance(previous_checks, dict) else {}
        old = old if isinstance(old, dict) else {}
        consecutive = 0 if ok else int(old.get("consecutiveFailures") or 0) + 1
        last_success = now.isoformat(timespec="seconds") if ok else old.get("lastSuccessAt")
        source_checks[spec["key"]] = {
            "url": spec["url"],
            "ok": ok,
            "httpStatus": status,
            "message": message,
            "lastSuccessAt": last_success,
            "consecutiveFailures": consecutive,
        }
        if not ok:
            source_errors.append(f"{spec['key']}: {message}")

    diagnostics = live.get("ticketCollectorDiagnostics") if isinstance(live.get("ticketCollectorDiagnostics"), dict) else {}
    collector_failures = diagnostics.get("failures") if isinstance(diagnostics.get("failures"), list) else []
    pending_urls = diagnostics.get("pendingReviewUrls") if isinstance(diagnostics.get("pendingReviewUrls"), list) else []
    playguide_failures = live.get("playguideFailures") if isinstance(live.get("playguideFailures"), list) else []

    freshness_error = None
    collected_at = clean(diagnostics.get("collectedAt"))
    if collected_at:
        try:
            stamp = datetime.fromisoformat(collected_at)
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=JST)
            age = now - stamp.astimezone(JST)
            if age > timedelta(hours=2, minutes=30):
                freshness_error = f"official collector diagnostics are stale by {age}"
        except ValueError:
            freshness_error = f"invalid collectedAt: {collected_at!r}"
    else:
        freshness_error = "ticketCollectorDiagnostics.collectedAt is missing"

    candidate_counts = diagnostics.get("candidateCounts") if isinstance(diagnostics.get("candidateCounts"), dict) else {}
    previous_counts = previous.get("officialCandidateCounts") if isinstance(previous.get("officialCandidateCounts"), dict) else {}
    sudden_drops = []
    for group, old_value in previous_counts.items():
        if group not in candidate_counts:
            continue
        old_count = int(old_value or 0)
        new_count = int(candidate_counts.get(group) or 0)
        if old_count >= 4 and new_count <= max(1, old_count // 4):
            sudden_drops.append({"source": group, "previous": old_count, "current": new_count})

    history_entries = len(history.get("entries") or [])
    previous_history_entries = int(previous.get("historyEntries") or 0)
    history_decreased = previous_history_entries > 0 and history_entries < previous_history_entries
    archive_gaps = live_history_gaps(live, history, registry)
    flow = flow_coverage(live, history, today)
    current_active_rows = active_rows(live, today)
    stale_active_pia = [row for row in current_active_rows if row.get("provider") == "pia" and row.get("sourceStale")]

    active_counts = Counter(f"{x['provider']}:{x['group']}" for x in current_active_rows)
    link_failures = deep_link_failures(session, history, today) if deep_links else []

    errors: list[str] = []
    warnings: list[str] = []
    errors.extend(source_errors)
    if freshness_error:
        errors.append(freshness_error)
    if collector_failures:
        errors.append(f"official collector reported {len(collector_failures)} failure(s)")
    if playguide_failures:
        errors.append(f"playguide collector reported {len(playguide_failures)} failure(s)")
    if history_decreased:
        errors.append(f"append-only history shrank from {previous_history_entries} to {history_entries}")
    if archive_gaps:
        errors.append(f"{len(archive_gaps)} current direct-source ticket row(s) are missing from permanent history")
    if sudden_drops:
        warnings.append(f"{len(sudden_drops)} official candidate count(s) dropped abruptly")
    if pending_urls:
        warnings.append(f"{len(pending_urls)} official ticket article(s) still require direct mapping review")
    if stale_active_pia:
        warnings.append(f"{len(stale_active_pia)} active Pia row(s) were retained after a scrape miss")
    if flow["noHistory"]:
        warnings.append(f"{len(flow['noHistory'])} hosted future performance(s) have no ticket history yet")
    if flow["suspiciousMissingFcBeforePlayguide"]:
        warnings.append(
            f"{len(flow['suspiciousMissingFcBeforePlayguide'])} hosted performance(s) have playguide history but no verified FC phase"
        )
    if link_failures:
        warnings.append(f"{len(link_failures)} future-history source link(s) failed deep verification")

    status = "degraded" if errors else "attention" if warnings else "healthy"
    safe_for_flow = status == "healthy" and not pending_urls and not flow["noHistory"] and not flow["suspiciousMissingFcBeforePlayguide"]

    return {
        "version": 1,
        "checkedAt": now.isoformat(timespec="seconds"),
        "status": status,
        "safeForTicketFlowPublication": safe_for_flow,
        "historyEntries": history_entries,
        "historyNeverShrank": not history_decreased,
        "officialNewsPagesPerSource": diagnostics.get("newsPagesScannedPerOfficialSource"),
        "officialCandidateCounts": candidate_counts,
        "officialCollectorPendingReviewCount": len(pending_urls),
        "officialCollectorPendingReviewUrls": pending_urls[:100],
        "officialCollectorFailures": collector_failures[:50],
        "playguideFailures": playguide_failures[:50],
        "sourceChecks": source_checks,
        "sourceFailureCount": len(source_errors),
        "suddenCandidateDrops": sudden_drops,
        "currentActivePlayguideRows": len(current_active_rows),
        "activePlayguideRowsBySource": dict(sorted(active_counts.items())),
        "staleActivePiaRows": stale_active_pia[:50],
        "currentRowsMissingFromHistory": archive_gaps[:100],
        "currentRowsMissingFromHistoryCount": len(archive_gaps),
        "flowCoverage": flow,
        "deepLinkAuditRan": deep_links,
        "deepLinkFailures": link_failures[:100],
        "deepLinkFailureCount": len(link_failures),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Continuously audit ticket collection completeness and source health.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--no-fail", action="store_true", help="Write health state but do not fail the workflow.")
    parser.add_argument("--deep-links", action="store_true", help="Also re-check every future-history source URL.")
    parser.add_argument("--verify-report", action="store_true", help="Fail if an already-written report is not healthy.")
    args = parser.parse_args()

    if args.verify_report:
        report = load(args.report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("status") == "healthy" else 2

    report = build_report(deep_links=args.deep_links)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.no_fail:
        return 0
    return 0 if report.get("status") == "healthy" else 2


if __name__ == "__main__":
    raise SystemExit(main())
