#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
EVENTS_PATH = Path("data/live-events.json")
VENUES_PATH = Path("data/venues.json")
OUTPUT_PATH = Path("data/train-status.json")
SOURCE_URL = "https://transit.yahoo.co.jp/diainfo"

PREFECTURE_AREA = {
    "北海道": "2",
    "青森県": "3", "岩手県": "3", "宮城県": "3", "秋田県": "3", "山形県": "3", "福島県": "3",
    "茨城県": "4", "栃木県": "4", "群馬県": "4", "埼玉県": "4", "千葉県": "4", "東京都": "4", "神奈川県": "4",
    "新潟県": "5", "富山県": "5", "石川県": "5", "福井県": "5", "山梨県": "5", "長野県": "5", "岐阜県": "5", "静岡県": "5", "愛知県": "5", "三重県": "5",
    "滋賀県": "6", "京都府": "6", "大阪府": "6", "兵庫県": "6", "奈良県": "6", "和歌山県": "6",
    "鳥取県": "8", "島根県": "8", "岡山県": "8", "広島県": "8", "山口県": "8",
    "徳島県": "9", "香川県": "9", "愛媛県": "9", "高知県": "9",
    "福岡県": "7", "佐賀県": "7", "長崎県": "7", "熊本県": "7", "大分県": "7", "宮崎県": "7", "鹿児島県": "7", "沖縄県": "7",
}


def normalize_venue(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"^[^\s　]+?[都道府県][\s　]+", "", text)
    text = re.sub(r"[\s　・･]", "", text)
    text = re.sub(r"(?:メイン)?大ホール|劇場棟", "", text)
    return text.lower()


def occurrence_rows(event: dict) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if isinstance(event.get("schedule"), list) and event["schedule"]:
        for item in event["schedule"]:
            if not isinstance(item, dict) or not item.get("venue"):
                continue
            rows.append((str(item.get("date") or event.get("eventDate") or "")[:10], str(item["venue"])))
        return rows
    venue = str(event.get("venue") or "")
    if not venue or re.search(r"オンライン|複数会場|会場未定", venue):
        return rows
    dates = event.get("eventDates") if isinstance(event.get("eventDates"), list) else [event.get("eventDate")]
    for day in dates:
        if day:
            rows.append((str(day)[:10], venue))
    return rows


def resolve_venue(name: str, venues: list[dict]) -> dict | None:
    requested = normalize_venue(name)
    for venue in venues:
        for candidate in [venue.get("name"), *(venue.get("aliases") or [])]:
            key = normalize_venue(candidate)
            if key and (requested == key or requested in key or key in requested):
                return venue
    return None


def event_area_ids(events: list[dict], venues: list[dict], day: str) -> list[str]:
    areas: set[str] = set()
    for event in events:
        for event_day, venue_name in occurrence_rows(event):
            if event_day != day:
                continue
            venue = resolve_venue(venue_name, venues)
            if venue and venue.get("prefecture") in PREFECTURE_AREA:
                areas.add(PREFECTURE_AREA[str(venue["prefecture"])])
    return sorted(areas)


def parse_trouble_routes(page: str) -> list[dict]:
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', page, re.S)
    if not match:
        raise ValueError("Yahoo!路線情報の構造化データが見つかりません")
    payload = json.loads(match.group(1))
    trouble = payload.get("props", {}).get("pageProps", {}).get("troubleRails", [])
    routes: list[dict] = []
    for item in trouble:
        prop = item.get("routeInfo", {}).get("property", {}) if isinstance(item, dict) else {}
        info = (prop.get("diainfo") or [{}])[0]
        name = str(prop.get("displayName") or prop.get("railName") or "").strip()
        status = str(info.get("status") or "運行情報あり").strip()
        url = str(prop.get("pcUrl1") or "").strip()
        if not name or not url:
            continue
        routes.append({
            "name": name,
            "company": str(prop.get("companyName") or "").strip(),
            "status": status,
            "updatedAt": str(info.get("updateDate") or "").strip(),
            "url": url,
        })
    return routes


def fetch_area(area_id: str, session: Any = None) -> str:
    import requests

    client = session or requests.Session()
    response = client.get(
        f"https://transit.yahoo.co.jp/diainfo/area/{area_id}",
        timeout=25,
        headers={"User-Agent": "KeioKawaiiLabVenueGuide/1.0 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"},
    )
    response.raise_for_status()
    return response.text


def build_payload(
    day: str,
    now: datetime,
    events: list[dict],
    venues: list[dict],
    fetcher: Callable[[str], str] = fetch_area,
) -> dict:
    areas = event_area_ids(events, venues, day)
    routes: list[dict] = []
    for area_id in areas:
        routes.extend(parse_trouble_routes(fetcher(area_id)))
    unique: dict[tuple[str, str], dict] = {}
    for route in routes:
        unique[(route["name"], route["url"])] = route
    return {
        "date": day,
        "checkedAt": now.astimezone(JST).isoformat(timespec="minutes"),
        "source": {"name": "Yahoo!路線情報", "url": SOURCE_URL},
        "routes": sorted(unique.values(), key=lambda item: (item["company"], item["name"])),
    }


def stable_payload(payload: dict, old: dict | None) -> dict:
    if old and old.get("date") == payload.get("date") and old.get("routes") == payload.get("routes"):
        payload["checkedAt"] = old.get("checkedAt") or payload["checkedAt"]
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="JST date in YYYY-MM-DD (tests/manual refresh)")
    args = parser.parse_args()

    now = datetime.now(JST)
    day = args.date or now.date().isoformat()
    events_payload = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    venues_payload = json.loads(VENUES_PATH.read_text(encoding="utf-8"))
    old = json.loads(OUTPUT_PATH.read_text(encoding="utf-8")) if OUTPUT_PATH.exists() else None
    payload = build_payload(day, now, events_payload.get("events", []), venues_payload.get("venues", []))
    payload = stable_payload(payload, old)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Train status refreshed for {day}: {len(payload['routes'])} active routes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
