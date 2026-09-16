"""Reapply collected JSON changes to latest main without text-rebasing generated files."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

MISSING = object()


def merge_value(base, collected, latest):
    if collected == base:
        return deepcopy(latest)
    if latest == base or latest == collected:
        return deepcopy(collected)
    if all(isinstance(value, dict) for value in (base, collected, latest)):
        out = {}
        for key in sorted(set(base) | set(collected) | set(latest)):
            b, c, l = (value.get(key, MISSING) for value in (base, collected, latest))
            if c == b:
                if l is not MISSING:
                    out[key] = deepcopy(l)
            elif l == b:
                if c is not MISSING:
                    out[key] = deepcopy(c)
            elif c is not MISSING and l is not MISSING:
                out[key] = merge_value(b, c, l)
            elif l is not MISSING:
                out[key] = deepcopy(l)
        return out
    # Newer main wins ambiguous edits to the same fact. New independent rows
    # and fields from the collector are retained by the structured merge above.
    return deepcopy(latest)


def merge_rows(base, collected, latest, identity):
    maps = [{identity(row): row for row in values} for values in (base, collected, latest)]
    return list(merge_value(*maps).values())


def merge_payload(base, collected, latest, key="events"):
    out = merge_value(base, collected, latest)
    identity = (lambda row: row["id"]) if key == "events" or any(row.get("id") for row in collected.get(key, [])) else (
        lambda row: (row.get("group"), row.get("date"), row.get("url")))
    out[key] = merge_rows(base.get(key, []), collected.get(key, []), latest.get(key, []), identity)
    out.pop("publicEvents", None)
    return out


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--base", type=Path, required=True)
    cli.add_argument("--collected", type=Path, required=True)
    cli.add_argument("--latest", type=Path, default=Path("data"))
    args = cli.parse_args()
    for name, key in (("live-events.json", "events"), ("official-schedule-index.json", "entries"), ("ticket-history.json", "entries")):
        paths = [directory / name for directory in (args.base, args.collected, args.latest)]
        values = [json.loads(path.read_text()) if path.exists() else {} for path in paths]
        merged = merge_payload(*values, key=key)
        paths[-1].write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name in ("official-discovery-state.json", "ticket-collection-health.json"):
        source = args.collected / name
        if source.exists():
            (args.latest / name).write_bytes(source.read_bytes())


if __name__ == "__main__":
    main()
