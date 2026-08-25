#!/usr/bin/env python3
from __future__ import annotations

import re

import refresh_event_weather as core

# 直前イベントで venues.json に未登録の会場だけ、施設公式サイトで確認した住所を補う。
# 会場名だけの曖昧検索は5kmメッシュに使わない。
VERIFIED_ADDRESS_HINTS = [
    (r"animate hall BLACK|アニメイト池袋本店", "東京都豊島区東池袋1-20-7"),
    (r"ららぽーと立川立飛", "東京都立川市泉町935-1"),
    (r"テラスモール松戸", "千葉県松戸市八ヶ崎2-8-1"),
    (r"ところざわサクラタウン", "埼玉県所沢市東所沢和田3-31-3"),
]


def verified_address(venue_name: str, venue_record: dict | None) -> str:
    if venue_record and venue_record.get("address"):
        return str(venue_record["address"]).strip()
    for pattern, address in VERIFIED_ADDRESS_HINTS:
        if re.search(pattern, venue_name, re.I):
            return address
    return ""


def safe_geocode(session, venue_name: str, venue_record: dict | None, cache: dict):
    key = core.normalize_venue(venue_name)
    address = verified_address(venue_name, venue_record)
    venues = cache.setdefault("venues", {})

    # 住所を公式/会場DBで確認できない地点は5km化しない。
    # 以前の会場名だけによる誤マッチ座標があればここで捨てる。
    if not address:
        venues.pop(key, None)
        return None

    saved = venues.get(key)
    if (
        isinstance(saved, dict)
        and saved.get("query") == address
        and saved.get("lat") is not None
        and saved.get("lon") is not None
    ):
        return saved

    try:
        payload = core.get_json(session, core.GSI_GEOCODE_URL, {"q": address})
    except Exception:
        venues.pop(key, None)
        return None
    if not isinstance(payload, list) or not payload:
        venues.pop(key, None)
        return None

    feature = payload[0] or {}
    coords = (feature.get("geometry") or {}).get("coordinates") or []
    title = str((feature.get("properties") or {}).get("title") or "")
    if len(coords) < 2:
        venues.pop(key, None)
        return None

    expected_pref = core.prefecture_from_text(address)
    actual_pref = core.prefecture_from_text(title)
    if expected_pref and actual_pref and expected_pref != actual_pref:
        venues.pop(key, None)
        return None

    try:
        lon, lat = float(coords[0]), float(coords[1])
    except (TypeError, ValueError):
        venues.pop(key, None)
        return None

    result = {
        "query": address,
        "title": title,
        "lon": round(lon, 6),
        "lat": round(lat, 6),
        "prefecture": actual_pref or expected_pref,
        "verifiedAddress": True,
    }
    venues[key] = result
    return result


def safe_choose_mesh_target(targets: list[dict], day: str, start_time: str):
    start_minutes = core.parse_minutes(start_time)
    desired = start_minutes if start_minutes is not None else 15 * 60
    candidates = []

    for item in targets:
        if not isinstance(item, dict) or "wm" not in (item.get("elements") or []):
            continue
        try:
            valid = core.utc_target_datetime(str(item.get("validtime") or ""))
        except Exception:
            continue
        if valid.date().isoformat() != day:
            continue

        mins = valid.hour * 60 + valid.minute
        # 開始時刻未発表なら、深夜・早朝のメッシュを「開催時の天気」のようには表示しない。
        # 9〜21時の予報がまだ配信されていない場合は広域予報のまま待つ。
        if start_minutes is None and not (9 * 60 <= mins <= 21 * 60):
            continue
        candidates.append((abs(mins - desired), item))

    return sorted(candidates, key=lambda pair: pair[0])[0][1] if candidates else None


core.geocode = safe_geocode
core.choose_mesh_target = safe_choose_mesh_target

if __name__ == "__main__":
    raise SystemExit(core.main())
