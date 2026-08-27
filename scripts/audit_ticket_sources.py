#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

REGISTRY_PATH = Path("data/ticket-source-registry.json")
HISTORY_PATH = Path("data/ticket-history.json")
REQUIRED_GROUPS = {"FRUITS ZIPPER", "CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR"}
REQUIRED_SOURCES = {"group-official", "kawaii-lab-fc", "pia", "eplus", "lawson", "official-x"}


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
        "status": "ok" if not errors else "blocked",
        "entries": len(history.get("entries") or []),
        "bySource": dict(sorted(counts.items())),
        "warnings": warnings[:50],
        "warningCount": len(warnings),
        "errors": errors,
    }
    return errors, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail closed when ticket history sources are unknown or non-authoritative.")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    registry = load(REGISTRY_PATH)
    history = load(HISTORY_PATH)
    errors = audit_registry(registry)
    history_errors, report = audit_history(registry, history)
    errors.extend(history_errors)
    report["registryErrors"] = [x for x in errors if x not in history_errors]
    report["status"] = "blocked" if errors else "ok"
    report["errors"] = errors

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
