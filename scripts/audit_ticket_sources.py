#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

REGISTRY_PATH = Path("data/ticket-source-registry.json")
HISTORY_PATH = Path("data/ticket-history.json")
LIVE_PATH = Path("data/live-events.json")
REQUIRED_GROUPS = {"FRUITS ZIPPER", "CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR"}
REQUIRED_SOURCES = {"group-official", "kawaii-lab-fc", "pia", "eplus", "lawson", "official-x"}
SPECIAL_CATEGORIES = {"release-event", "large-benefit", "benefit-event", "online-benefit"}


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def host(url: object) -> str:
    try:
        return (urlparse(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""


def mapped_source(url: object, registry: dict) -> str | None:
    source_host = host(url)
    rules = registry.get("hostRules") or {}
    if source_host in rules:
        return str(rules[source_host])
    for known_host, key in rules.items():
        if source_host.endswith("." + str(known_host).lower()):
            return str(key)
    return None


def candidate_urls(event: dict) -> list[str]:
    result: list[str] = []
    for key in ("applicationWindowSource", "deadlineSource", "url"):
        value = str(event.get(key) or "").strip()
        if value and value not in result:
            result.append(value)
    for value in event.get("urls") or []:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def audit_registry(registry: dict) -> list[str]:
    errors: list[str] = []
    sources = registry.get("sources") or {}
    missing_sources = REQUIRED_SOURCES - set(sources)
    if missing_sources:
        errors.append("missing sources: " + ", ".join(sorted(missing_sources)))

    groups = ((sources.get("group-official") or {}).get("groups") or {})
    missing_groups = REQUIRED_GROUPS - set(groups)
    if missing_groups:
        errors.append("missing official group sources: " + ", ".join(sorted(missing_groups)))

    rules = registry.get("hostRules") or {}
    for source_key, config in sources.items():
        if not isinstance(config, dict):
            errors.append(f"source {source_key} is not an object")
            continue
        policy = config.get("publishPolicy")
        if policy not in {"direct", "discovery-only"}:
            errors.append(f"source {source_key} has invalid publishPolicy={policy!r}")
    for rule_host, source_key in rules.items():
        if source_key not in sources:
            errors.append(f"host rule {rule_host} points to unknown source {source_key}")
    if (sources.get("official-x") or {}).get("publishPolicy") != "discovery-only":
        errors.append("official-x must remain discovery-only")
    return errors


def audit_collector_alignment(registry: dict) -> list[str]:
    """Keep the crawler constants in sync with the central source registry."""
    errors: list[str] = []
    try:
        import update_live_events as official
        import update_live_events_v2 as central
        import update_pia_events as pia
        import update_playguide_events as playguide
    except Exception as exc:  # pragma: no cover - import failure is itself an audit failure
        return [f"could not import ticket collectors: {type(exc).__name__}: {exc}"]

    sources = registry.get("sources") or {}
    official_groups = (sources.get("group-official") or {}).get("groups") or {}
    expected_group_bases = {group: str(config.get("baseUrl") or "") for group, config in official_groups.items()}
    if dict(official.GROUPS) != expected_group_bases:
        errors.append("update_live_events.GROUPS differs from ticket-source-registry.json")

    expected_central = str((sources.get("kawaii-lab-fc") or {}).get("baseUrl") or "")
    if central.CENTRAL_FC_BASE != expected_central:
        errors.append("update_live_events_v2.CENTRAL_FC_BASE differs from ticket-source-registry.json")

    expected_pia = dict((sources.get("pia") or {}).get("artistUrls") or {})
    if dict(pia.ARTIST_URLS) != expected_pia:
        errors.append("update_pia_events.ARTIST_URLS differs from ticket-source-registry.json")

    expected_eplus = dict((sources.get("eplus") or {}).get("artistUrls") or {})
    if dict(playguide.EPLUS_ARTIST_URLS) != expected_eplus:
        errors.append("update_playguide_events.EPLUS_ARTIST_URLS differs from ticket-source-registry.json")
    return errors


def audit_live_source_coverage(registry: dict, live: dict) -> tuple[list[str], list[str]]:
    """Flag KAWAII LAB-hosted live ticket rows that have no registered direct source.

    External festivals may legitimately use many organizer ticket systems, so those are
    warnings rather than release-blocking errors. Special/release events are handled by
    their own pipelines and are excluded from the concert-ticket-flow source gate.
    """
    errors: list[str] = []
    warnings: list[str] = []
    sources = registry.get("sources") or {}

    for event in live.get("events") or []:
        if not isinstance(event, dict):
            continue
        if str(event.get("ticketType") or "") in {"", "現在受付なし"}:
            continue
        if not event.get("applyStart") and not event.get("applyEnd"):
            continue
        if str(event.get("eventCategory") or "") in SPECIAL_CATEGORIES:
            continue

        direct = []
        for url in candidate_urls(event):
            key = mapped_source(url, registry)
            config = sources.get(key) if key else None
            if isinstance(config, dict) and config.get("publishPolicy") == "direct":
                direct.append((url, key))
        if direct:
            continue

        label = f"{event.get('group')} / {event.get('eventDate')} / {event.get('ticketType')} / {event.get('title')}"
        unknown_hosts = sorted({host(url) for url in candidate_urls(event) if host(url)})
        message = f"unregistered ticket source for {label}; hosts={unknown_hosts or ['none']}"
        if event.get("eventScope") == "kawaii-lab":
            errors.append(message)
        else:
            warnings.append(message)
    return errors, warnings


def audit_history(registry: dict, history: dict) -> tuple[list[str], dict]:
    errors: list[str] = []
    warnings: list[str] = []
    sources = registry.get("sources") or {}
    rules = registry.get("hostRules") or {}
    ids: set[str] = set()
    counts = Counter()

    for index, item in enumerate(history.get("entries") or []):
        if not isinstance(item, dict):
            errors.append(f"entry[{index}] is not an object")
            continue
        entry_id = str(item.get("id") or "")
        if not entry_id:
            errors.append(f"entry[{index}] missing id")
        elif entry_id in ids:
            errors.append(f"duplicate history id: {entry_id}")
        ids.add(entry_id)

        source_key = str(item.get("sourceKey") or "")
        if source_key not in sources:
            errors.append(f"{entry_id or index}: unknown sourceKey={source_key!r}")
            continue
        config = sources[source_key]
        if config.get("publishPolicy") != "direct":
            errors.append(f"{entry_id or index}: discovery-only source cannot be archived as direct history")

        source_url = str(item.get("sourceUrl") or "")
        source_host = host(source_url)
        mapped = rules.get(source_host)
        if not source_url or not source_host:
            errors.append(f"{entry_id or index}: missing sourceUrl")
        elif mapped != source_key:
            errors.append(f"{entry_id or index}: sourceUrl host {source_host} maps to {mapped!r}, not {source_key!r}")

        if not item.get("eventDate") or not item.get("group") or not item.get("ticketType"):
            errors.append(f"{entry_id or index}: missing eventDate/group/ticketType")
        if not item.get("applyStart") and not item.get("applyEnd"):
            errors.append(f"{entry_id or index}: missing application window")
        if item.get("publishable") and item.get("windowCompleteness") == "missing":
            errors.append(f"{entry_id or index}: publishable entry has missing window")
        if item.get("windowCompleteness") != "full":
            warnings.append(f"{entry_id or index}: partial window ({item.get('windowCompleteness')})")
        counts[source_key] += 1

    report = {
        "entries": len(history.get("entries") or []),
        "bySource": dict(sorted(counts.items())),
        "historyWarnings": warnings[:50],
        "historyWarningCount": len(warnings),
    }
    return errors, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail closed when ticket history sources are unknown or non-authoritative.")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    registry = load(REGISTRY_PATH)
    history = load(HISTORY_PATH)
    live = load(LIVE_PATH)

    registry_errors = audit_registry(registry)
    alignment_errors = audit_collector_alignment(registry)
    live_errors, live_warnings = audit_live_source_coverage(registry, live)
    history_errors, report = audit_history(registry, history)
    errors = registry_errors + alignment_errors + live_errors + history_errors

    report.update({
        "status": "blocked" if errors else "ok",
        "registryErrors": registry_errors,
        "collectorAlignmentErrors": alignment_errors,
        "liveCoverageErrors": live_errors,
        "liveCoverageWarnings": live_warnings[:50],
        "liveCoverageWarningCount": len(live_warnings),
        "errors": errors,
    })

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
