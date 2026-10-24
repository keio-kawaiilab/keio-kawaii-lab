#!/usr/bin/env python3
"""Reconnect official schedule-index rows to final merged event ids.

Distributed collectors may describe the same official event with different
stable ids (for example, a rich special-event row replacing an official-
schedule placeholder).  The official schedule URL, date and participant are
still authoritative.  Reconcile representedBy only when those three signals
identify exactly one final event; ambiguous or missing rows remain untouched so
the fail-closed coverage audit can still block publication.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from update_official_schedule import event_days, participants


def event_urls(event: dict) -> set[str]:
    values = {
        str(event.get("url") or "").strip(),
        str(event.get("officialScheduleUrl") or "").strip(),
    }
    values.update(str(value).strip() for value in event.get("urls") or [])
    return {value for value in values if value}


def event_matches_entry(event: dict, entry: dict) -> bool:
    target_url = str(entry.get("url") or "").strip()
    target_date = str(entry.get("date") or "").strip()
    target_group = str(entry.get("group") or "").strip()
    if not target_url or not target_date or not target_group:
        return False
    if target_url not in event_urls(event):
        return False
    if target_date not in event_days(event):
        return False
    if target_group not in participants(event):
        return False
    return True


def represented_identity_matches(event: dict, entry: dict) -> bool:
    """Trust the existing representedBy link only for the same dated scoped event."""
    target_date = str(entry.get("date") or "").strip()
    target_group = str(entry.get("group") or "").strip()
    target_scope = str(entry.get("eventScope") or "").strip()
    if not target_date or not target_group:
        return False
    if target_date not in event_days(event):
        return False
    if target_group not in participants(event):
        return False
    if target_scope and str(event.get("eventScope") or "").strip() != target_scope:
        return False
    return True


def attach_official_url(event: dict, target_url: str) -> bool:
    target_url = str(target_url or "").strip()
    if not target_url or target_url in event_urls(event):
        return False

    current_schedule_url = str(event.get("officialScheduleUrl") or "").strip()
    if not current_schedule_url:
        event["officialScheduleUrl"] = target_url
        return True

    urls = [str(value).strip() for value in event.get("urls") or [] if str(value).strip()]
    if target_url not in urls:
        urls.append(target_url)
        event["urls"] = urls
        return True
    return False


def project_joint_participant_rows(entries: list[dict], by_id: dict[str, dict]) -> list[dict]:
    """Give LINE's five-group index one verified entry per participating group.

    The deployed LINE Worker filters official index rows by entry.group and
    cannot see event.participants. Only project an already represented hosted
    joint performance when that participant has its own official source URL.
    Do not invent a URL or multiply ticket offers.
    """
    from update_official_schedule import GROUPS

    existing = {
        (str(row.get("representedBy") or ""), str(row.get("date") or ""),
         str(row.get("group") or ""))
        for row in entries
    }
    additions = []
    for entry in list(entries):
        event_id = str(entry.get("representedBy") or "")
        event = by_id.get(event_id)
        if (
            not event or not event_matches_entry(event, entry)
            or event.get("group") != "KAWAII LAB.合同"
            or event.get("eventScope") != "kawaii-lab"
            or entry.get("eventScope") != "kawaii-lab"
            or entry.get("category") not in {"LIVE", "EVENT"}
            or len(participants(event)) < 2
        ):
            continue
        for group in participants(event):
            key = (event_id, str(entry.get("date") or ""), group)
            if key in existing:
                continue
            base = GROUPS.get(group)
            if not base:
                continue
            official_urls = [
                url for url in event_urls(event)
                if url.startswith(base + "/")
                and ("/news/detail/" in url or "/live_information/detail/" in url)
            ]
            if not official_urls:
                continue
            # Prefer the participant's own official schedule detail, otherwise
            # the official announcement. Both are already attached to the event.
            official_urls.sort(key=lambda url: ("/live_information/detail/" not in url, url))
            new_row = dict(entry)
            new_row["group"] = group
            new_row["url"] = official_urls[0]
            new_row["projectionSource"] = "joint-participant-official-news"
            additions.append(new_row)
            existing.add(key)
    return additions


def reconcile(data: dict, index: dict) -> dict:
    events = [event for event in data.get("events", []) if isinstance(event, dict)]
    by_id = {str(event.get("id") or ""): event for event in events if event.get("id")}
    entries = [entry for entry in index.get("entries", []) if isinstance(entry, dict)]

    reassigned: list[dict] = []
    hydrated: list[dict] = []
    ambiguous: list[dict] = []
    unresolved: list[dict] = []

    for entry in entries:
        current_id = str(entry.get("representedBy") or "")
        current_event = by_id.get(current_id)
        if current_event and event_matches_entry(current_event, entry):
            continue

        # The official collector created representedBy from this exact schedule
        # row. Later canonical merging can retain that event id while dropping
        # the schedule URL in favour of a richer news/ticket URL. When every
        # identity signal still agrees, restore only the missing official URL;
        # do not guess a different event.
        if current_event and represented_identity_matches(current_event, entry):
            target_url = str(entry.get("url") or "").strip()
            if attach_official_url(current_event, target_url):
                hydrated.append({
                    "group": entry.get("group"),
                    "date": entry.get("date"),
                    "url": target_url,
                    "eventId": current_id,
                })
            if event_matches_entry(current_event, entry):
                continue

        matches = [event for event in events if event.get("id") and event_matches_entry(event, entry)]
        if len(matches) == 1:
            new_id = str(matches[0]["id"])
            entry["representedBy"] = new_id
            reassigned.append({
                "group": entry.get("group"),
                "date": entry.get("date"),
                "url": entry.get("url"),
                "from": current_id or None,
                "to": new_id,
            })
        elif len(matches) > 1:
            ambiguous.append({
                "group": entry.get("group"),
                "date": entry.get("date"),
                "url": entry.get("url"),
                "candidateIds": [str(event.get("id")) for event in matches],
            })
        else:
            unresolved.append({
                "group": entry.get("group"),
                "date": entry.get("date"),
                "url": entry.get("url"),
                "representedBy": current_id or None,
            })

    projected = project_joint_participant_rows(entries, by_id)
    entries.extend(projected)
    index["entries"] = entries
    return {
        "projectedJointParticipantCount": len(projected),
        "reassignedCount": len(reassigned),
        "hydratedCount": len(hydrated),
        "ambiguousCount": len(ambiguous),
        "unresolvedCount": len(unresolved),
        "reassigned": reassigned,
        "hydrated": hydrated,
        "ambiguous": ambiguous,
        "unresolved": unresolved,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/live-events.json"))
    parser.add_argument("--index", type=Path, default=Path("data/official-schedule-index.json"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    data = json.loads(args.data.read_text(encoding="utf-8"))
    index = json.loads(args.index.read_text(encoding="utf-8"))
    report = reconcile(data, index)
    args.data.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.index.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())