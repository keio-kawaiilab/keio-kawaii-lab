#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import update_sukisuki_events as sukisuki
import update_special_events as special

JST = timezone(timedelta(hours=9))
PLAYGUIDE_PROVIDERS = {"eplus", "lawson"}
SPECIAL_CATEGORIES = {"release-event", "large-benefit", "large-benefit-event"}


def event_text(event: dict) -> str:
    return " ".join(str(event.get(key) or "") for key in ("title", "eventTitle", "displayTitle"))


def is_playguide_event(event: dict) -> bool:
    provider = str(event.get("ticketProvider") or "").lower()
    source = str(event.get("sourceType") or "").lower()
    return provider in PLAYGUIDE_PROVIDERS or source in PLAYGUIDE_PROVIDERS


def is_special_event(event: dict) -> bool:
    source = str(event.get("sourceType") or "").lower()
    category = str(event.get("eventCategory") or "").lower()
    if source == "official-special" or category in SPECIAL_CATEGORIES:
        return True
    return bool(special.SPECIAL_RE.search(event_text(event)))


def is_sukisuki_event(event: dict) -> bool:
    # Some physical release-event pages link to SUKISUKI. Those remain owned by
    # the special-event collector rather than the online-benefit collector.
    return not is_special_event(event) and sukisuki.is_sukisuki_event(event)


def read_payload(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def events(payload: dict) -> list[dict]:
    return [dict(item) for item in payload.get("events", []) if isinstance(item, dict)]


def dedupe_by_id(rows: list[dict]) -> list[dict]:
    result: list[dict] = []
    positions: dict[str, int] = {}
    for row in rows:
        event_id = str(row.get("id") or "")
        if not event_id:
            result.append(row)
            continue
        if event_id in positions:
            result[positions[event_id]] = row
        else:
            positions[event_id] = len(result)
            result.append(row)
    return result


def replace_owned_rows(
    current: list[dict],
    snapshot: list[dict],
    owner: Callable[[dict], bool],
) -> tuple[list[dict], dict]:
    previous_owned = [row for row in current if owner(row)]
    new_owned = [row for row in snapshot if owner(row)]
    merged = [row for row in current if not owner(row)] + new_owned
    return dedupe_by_id(merged), {
        "previous": len(previous_owned),
        "replacement": len(new_owned),
    }


def preserve_core_official_links(core_rows: list[dict], merged_rows: list[dict]) -> int:
    """Never lose authoritative official-schedule links during source replacement.

    The core collector enriches represented events with officialScheduleUrl and
    official live-information URLs. A richer special/playguide snapshot can
    replace the same event later in the distributed merge. Preserve the core
    official-link metadata for identical stable event ids so the official
    coverage index remains valid without another network crawl.
    """
    core_by_id = {
        str(row.get("id") or ""): row
        for row in core_rows
        if row.get("id")
    }
    touched = 0
    for row in merged_rows:
        event_id = str(row.get("id") or "")
        core_row = core_by_id.get(event_id)
        if not core_row:
            continue

        official_url = str(core_row.get("officialScheduleUrl") or "").strip()
        core_urls = [str(value) for value in core_row.get("urls") or [] if value]
        authoritative_urls = [
            value for value in core_urls
            if "asobisystem.com/live_information/detail/" in value
        ]
        if official_url and official_url not in authoritative_urls:
            authoritative_urls.append(official_url)
        if not authoritative_urls:
            continue

        changed = False
        urls = [str(value) for value in row.get("urls") or [] if value]
        primary_url = str(row.get("url") or "").strip()
        if primary_url and primary_url not in urls:
            urls.insert(0, primary_url)
        for value in authoritative_urls:
            if value not in urls:
                urls.append(value)
                changed = True
        if official_url and row.get("officialScheduleUrl") != official_url:
            row["officialScheduleUrl"] = official_url
            changed = True
        row["urls"] = list(dict.fromkeys(urls))
        if changed:
            touched += 1
    return touched


def merge_payloads(core: dict, playguide: dict, sukisuki_payload: dict, special_payload: dict) -> dict:
    core_rows = events(core)
    merged_events = [dict(row) for row in core_rows]
    report: dict[str, dict] = {}

    merged_events, report["playguide"] = replace_owned_rows(
        merged_events, events(playguide), is_playguide_event
    )
    merged_events, report["sukisuki"] = replace_owned_rows(
        merged_events, events(sukisuki_payload), is_sukisuki_event
    )
    merged_events, report["special"] = replace_owned_rows(
        merged_events, events(special_payload), is_special_event
    )
    official_links_preserved = preserve_core_official_links(core_rows, merged_events)

    merged_events.sort(key=lambda event: (
        str(event.get("eventDate") or "9999"),
        str(event.get("applyEnd") or "9999"),
        str(event.get("group") or ""),
        str(event.get("id") or ""),
    ))

    out = dict(core)
    out["events"] = merged_events
    out["updatedAt"] = datetime.now(JST).isoformat(timespec="seconds")
    out["source"] = (
        "KAWAII LAB.各グループ公式公開情報 + チケットぴあ・ローチケ・イープラス公開情報 + "
        "SUKISUKI公開オンライン特典会情報 + 公式大特典会・リリースイベント情報"
    )

    for key in ("playguideFailures", "playguideDiagnostics"):
        if key in playguide:
            out[key] = playguide[key]

    out["distributedMergeDiagnostics"] = {
        "mergedAt": out["updatedAt"],
        "sources": report,
        "officialLinksPreserved": official_links_preserved,
        "eventCount": len(merged_events),
    }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge independently collected calendar snapshots")
    parser.add_argument("--core", required=True)
    parser.add_argument("--playguide", required=True)
    parser.add_argument("--sukisuki", required=True)
    parser.add_argument("--special", required=True)
    parser.add_argument("--output", default="data/live-events.json")
    parser.add_argument("--report")
    args = parser.parse_args()

    result = merge_payloads(
        read_payload(args.core),
        read_payload(args.playguide),
        read_payload(args.sukisuki),
        read_payload(args.special),
    )
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.report:
        Path(args.report).write_text(
            json.dumps(result["distributedMergeDiagnostics"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result["distributedMergeDiagnostics"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
