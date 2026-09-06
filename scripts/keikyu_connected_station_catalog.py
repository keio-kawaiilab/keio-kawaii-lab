#!/usr/bin/env python3
"""Canonical station-title catalog for the Keisei/Asakusa/Keikyu component.

This module is only about interpreting station labels printed in the Keikyu
official all-line timetable.  Membership in this catalog does not prove that a
specific train crosses any operator boundary.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPE = ROOT / "data/transit/keisei/system-scope.json"
ENTITY_FILES = (
    ROOT / "data/transit/keikyu/entities.json",
    ROOT / "data/transit/toei/entities.json",
    ROOT / "data/transit/keisei/entities.json",
    ROOT / "data/transit/hokuso/entities.json",
    ROOT / "data/transit/shibayama/entities.json",
)

# Printed aliases in the Keikyu PDF. Values are canonical entity titles.
PDF_ALIASES = {
    "空港第２ビル": "空港第2ビル",
    "羽田第１・第２": "羽田空港第１・第２ターミナル",
    "羽田第３": "羽田空港第３ターミナル",
}


def _values(value):
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def _title(row: dict) -> str | None:
    title = row.get("dc:title")
    localized = row.get("odpt:stationTitle")
    if isinstance(localized, dict):
        title = localized.get("ja") or title
    if not title:
        return None
    return re.sub(r"\s+", "", str(title))


def catalog() -> dict[str, dict]:
    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    allowed = {str(row["id"]) for row in scope.get("railways", []) if row.get("id")}
    result: dict[str, dict] = {}
    for path in ENTITY_FILES:
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("Station") or []:
            if not isinstance(row, dict):
                continue
            railways = set(_values(row.get("odpt:railway")))
            if not railways.intersection(allowed):
                continue
            title = _title(row)
            if not title:
                continue
            entry = result.setdefault(title, {"canonical": title, "railways": set(), "ids": set()})
            entry["railways"].update(railways.intersection(allowed))
            station_id = row.get("owl:sameAs")
            if station_id:
                entry["ids"].add(str(station_id))

    for alias, canonical in PDF_ALIASES.items():
        if canonical in result:
            base = result[canonical]
            result[alias] = {
                "canonical": canonical,
                "railways": set(base["railways"]),
                "ids": set(base["ids"]),
                "alias": True,
            }

    return result


def station_titles() -> list[str]:
    return sorted(catalog(), key=lambda value: (-len(value), value))


def canonical_title(printed_title: str) -> str:
    row = catalog().get(printed_title)
    return str(row.get("canonical")) if row else printed_title


if __name__ == "__main__":
    data = catalog()
    local = sum(1 for row in data.values() if any(r.startswith("odpt.Railway:Keikyu.") for r in row["railways"]))
    print(json.dumps({"titles": len(data), "keikyuTitles": local}, ensure_ascii=False))
