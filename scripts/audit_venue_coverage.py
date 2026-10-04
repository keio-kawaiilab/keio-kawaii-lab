#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

VENUES_PATH = Path("data/venues.json")
EVENTS_PATH = Path("data/live-events.json")
JST = timezone(timedelta(hours=9))
REQUIRED_FIELDS = (
    "id", "name", "prefecture", "area", "type", "address",
    "access", "capacityNote", "officialUrl", "mapUrl",
)
PREFECTURES = (
    "北海道", "東京都", "京都府", "大阪府",
    "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県", "滋賀県", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県",
    "山口県", "徳島県", "香川県", "愛媛県", "高知県", "福岡県",
    "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県",
    "沖縄県",
)
PREFECTURE_ONLY = set(PREFECTURES) | {"海外", "その他"}
NON_PHYSICAL_RE = re.compile(
    r"オンライン|当選者のみ|YouTube|https?://|某所|会場未定|未発表|詳細発表待ち",
    re.I,
)
MULTI_RE = re.compile(r"複数会場")


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"[（(][^）)]*(?:都|道|府|県|市|区|〒|\d{3}-\d)[^）)]*[）)]", "", text)
    text = re.sub(r"^(?:北海道|東京都|京都府|大阪府|.{2,3}県|その他)\s*", "", text)
    text = re.sub(r"[\s　・･]", "", text)
    text = re.sub(r"(?:メイン)?大ホール|劇場棟", "", text)
    return text.casefold()


def is_blank(value: object) -> bool:
    return value is None or value == "" or (isinstance(value, list) and not value)


def is_non_physical(value: object) -> bool:
    text = str(value or "").strip()
    return not text or bool(NON_PHYSICAL_RE.search(text))


def occurrence_rows(event: dict) -> list[dict]:
    rows = event.get("schedule") if isinstance(event.get("schedule"), list) else []
    if rows:
        result = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            locations = item.get("venueLocations") if isinstance(item.get("venueLocations"), list) else []
            if locations:
                for venue in locations:
                    result.append({"date": str(item.get("date") or event.get("eventDate") or "")[:10], "venue": venue})
            else:
                result.append({"date": str(item.get("date") or event.get("eventDate") or "")[:10], "venue": item.get("venue")})
        return result

    dates = event.get("eventDates") if isinstance(event.get("eventDates"), list) and event.get("eventDates") else [event.get("eventDate")]
    locations = event.get("venueLocations") if isinstance(event.get("venueLocations"), list) else []
    result = []
    for day in dates:
        if locations:
            for venue in locations:
                result.append({"date": str(day or "")[:10], "venue": venue})
        else:
            result.append({"date": str(day or "")[:10], "venue": event.get("venue")})
    return result


def audit(venues_payload: dict, events_payload: dict, today: str) -> dict:
    venues = [v for v in venues_payload.get("venues", []) if isinstance(v, dict)]
    events = [e for e in events_payload.get("events", []) if isinstance(e, dict)]

    missing_required = []
    duplicate_ids = []
    duplicate_names = []
    alias_collisions = []
    invalid_official_urls = []

    ids: dict[str, list[str]] = {}
    names: dict[str, list[str]] = {}
    aliases: dict[str, list[str]] = {}
    canonical: dict[str, str] = {}

    for venue in venues:
        name = str(venue.get("name") or "")
        missing = [field for field in REQUIRED_FIELDS if is_blank(venue.get(field))]
        if missing:
            missing_required.append({"name": name, "fields": missing})
        if venue.get("officialUrl") and not str(venue.get("officialUrl")).startswith(("https://", "http://")):
            invalid_official_urls.append({"name": name, "officialUrl": venue.get("officialUrl")})

        ids.setdefault(str(venue.get("id") or ""), []).append(name)
        names.setdefault(name, []).append(str(venue.get("id") or ""))
        for alias in [name, *(venue.get("aliases") or [])]:
            key = normalize(alias)
            if not key:
                continue
            aliases.setdefault(key, []).append(name)
            canonical.setdefault(key, name)

    for key, values in ids.items():
        if key and len(values) > 1:
            duplicate_ids.append({"id": key, "venues": values})
    for key, values in names.items():
        if key and len(values) > 1:
            duplicate_names.append({"name": key, "ids": values})
    for key, values in aliases.items():
        unique = list(dict.fromkeys(values))
        if len(unique) > 1:
            alias_collisions.append({"normalizedAlias": key, "venues": unique})

    unmatched: dict[str, dict] = {}
    opaque_multi = []
    prefecture_only = []
    invalid_values = []
    checked_occurrences = 0

    for event in events:
        for row in occurrence_rows(event):
            day = str(row.get("date") or "")[:10]
            if day and day < today:
                continue
            venue = str(row.get("venue") or "").strip()
            if not venue:
                continue
            if MULTI_RE.search(venue):
                # Explicit multi-venue rows must be expanded through venueLocations.
                opaque_multi.append({
                    "date": day,
                    "group": event.get("group"),
                    "title": event.get("title") or event.get("eventTitle"),
                    "venue": venue,
                })
                continue
            if is_non_physical(venue):
                continue
            checked_occurrences += 1
            if venue in PREFECTURE_ONLY:
                prefecture_only.append({
                    "date": day,
                    "group": event.get("group"),
                    "title": event.get("title") or event.get("eventTitle"),
                    "venue": venue,
                })
                continue
            if re.search(r"https?://", venue, re.I):
                invalid_values.append({
                    "date": day,
                    "group": event.get("group"),
                    "title": event.get("title") or event.get("eventTitle"),
                    "venue": venue,
                })
                continue
            key = normalize(venue)
            if key not in canonical:
                entry = unmatched.setdefault(venue, {
                    "venue": venue,
                    "count": 0,
                    "dates": [],
                    "groups": [],
                    "titles": [],
                })
                entry["count"] += 1
                if day and day not in entry["dates"]:
                    entry["dates"].append(day)
                group = str(event.get("group") or "")
                if group and group not in entry["groups"]:
                    entry["groups"].append(group)
                title = str(event.get("title") or event.get("eventTitle") or "")
                if title and title not in entry["titles"]:
                    entry["titles"].append(title)

    errors = (
        missing_required + duplicate_ids + duplicate_names + alias_collisions
        + invalid_official_urls + list(unmatched.values()) + opaque_multi
        + prefecture_only + invalid_values
    )
    return {
        "status": "ok" if not errors else "degraded",
        "today": today,
        "venueCount": len(venues),
        "checkedFuturePhysicalOccurrences": checked_occurrences,
        "missingRequired": missing_required,
        "duplicateIds": duplicate_ids,
        "duplicateNames": duplicate_names,
        "aliasCollisions": alias_collisions,
        "invalidOfficialUrls": invalid_official_urls,
        "unmatchedVenues": list(unmatched.values()),
        "opaqueMultiVenueRows": opaque_multi,
        "prefectureOnlyVenueRows": prefecture_only,
        "invalidVenueValues": invalid_values,
        "errorCount": len(errors),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit canonical venue coverage without blocking calendar collection.")
    parser.add_argument("--venues", type=Path, default=VENUES_PATH)
    parser.add_argument("--events", type=Path, default=EVENTS_PATH)
    parser.add_argument("--today")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    today = args.today or datetime.now(JST).date().isoformat()
    venues_payload = json.loads(args.venues.read_text(encoding="utf-8"))
    events_payload = json.loads(args.events.read_text(encoding="utf-8"))
    report = audit(venues_payload, events_payload, today)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
