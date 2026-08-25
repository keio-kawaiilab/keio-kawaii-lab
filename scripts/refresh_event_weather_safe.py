#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import re
from datetime import date, datetime, timedelta

import requests
from PIL import Image

import refresh_event_weather as core

# 直前イベントで venues.json に未登録の会場だけ、施設公式サイトで確認した住所を補う。
# 会場名だけの曖昧検索は5kmメッシュに使わない。
VERIFIED_ADDRESS_HINTS = [
    (r"animate hall BLACK|アニメイト池袋本店", "東京都豊島区東池袋1-20-7"),
    (r"ららぽーと立川立飛", "東京都立川市泉町935-1"),
    (r"テラスモール松戸", "千葉県松戸市八ヶ崎2-8-1"),
    (r"ところざわサクラタウン", "埼玉県所沢市東所沢和田3-31-3"),
]

RAIN_TARGETS_URL = "https://www.jma.go.jp/bosai/jmatile/data/rasrf/targetTimes.json"
RAIN_BASE = "https://www.jma.go.jp/bosai/jmatile/data/rasrf"
TIMELINE_HOURS = (6, 9, 12, 15, 18, 21, 24)


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
        # 保存済み座標でも、その検索元が今回の確認済み住所と完全一致している時だけ再利用する。
        saved["verifiedAddress"] = True
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


def _latest_target_near(targets: list[dict], desired: datetime, element: str, tolerance_minutes: int = 45):
    candidates = []
    for item in targets:
        if not isinstance(item, dict) or element not in (item.get("elements") or []):
            continue
        try:
            valid = core.utc_target_datetime(str(item.get("validtime") or ""))
        except Exception:
            continue
        diff = abs((valid - desired).total_seconds()) / 60
        if diff <= tolerance_minutes:
            try:
                base_rank = int(str(item.get("basetime") or "0"))
            except ValueError:
                base_rank = 0
            candidates.append((diff, -base_rank, item))
    return sorted(candidates, key=lambda x: (x[0], x[1]))[0][2] if candidates else None


def _tile_image(session: requests.Session, url: str, cache: dict[str, Image.Image]):
    if url in cache:
        return cache[url]
    response = session.get(url, timeout=30)
    if not response.ok:
        return None
    image = Image.open(io.BytesIO(response.content)).convert("RGBA")
    cache[url] = image
    return image


def _sample_palette(session: requests.Session, target: dict, element: str, lon: float, lat: float, palette: dict, cache: dict[str, Image.Image]):
    tile_x, tile_y, px, py = core.slippy_pixel(lon, lat)
    url = f"{core.WDIST_BASE}/{target['basetime']}/none/{target['validtime']}/surf/{element}/{core.TILE_ZOOM}/{tile_x}/{tile_y}.png"
    image = _tile_image(session, url, cache)
    if image is None:
        return None
    labels = []
    for dx, dy in [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0), (0, 2), (0, -2)]:
        x, y = max(0, min(255, px + dx)), max(0, min(255, py + dy))
        r, g, b, a = image.getpixel((x, y))
        if a >= 80:
            labels.append(core.closest_palette((r, g, b), palette))
    return max(set(labels), key=labels.count) if labels else None


def build_mesh_timeline(session: requests.Session, targets: list[dict], day: str, lon: float, lat: float, tile_cache: dict[str, Image.Image]):
    base_day = date.fromisoformat(day)
    rows = []
    for hour in TIMELINE_HOURS:
        if hour == 24:
            wanted = datetime.combine(base_day + timedelta(days=1), datetime.min.time(), tzinfo=core.JST)
            label_time = "24:00"
        else:
            wanted = datetime.combine(base_day, datetime.min.time(), tzinfo=core.JST) + timedelta(hours=hour)
            label_time = f"{hour:02d}:00"
        target = _latest_target_near(targets, wanted, "wm", tolerance_minutes=20)
        if not target:
            continue
        weather = _sample_palette(session, target, "wm", lon, lat, core.WEATHER_PALETTE, tile_cache)
        if not weather:
            continue
        temp_band = None
        if "temp" in (target.get("elements") or []):
            temp_band = _sample_palette(session, target, "temp", lon, lat, core.TEMP_PALETTE, tile_cache)
        valid = core.utc_target_datetime(str(target.get("validtime") or ""))
        rows.append({
            "time": label_time,
            "label": weather,
            "tempBand": temp_band,
            "validAt": valid.isoformat(timespec="minutes"),
        })
    return rows


def _sample_rain_presence(session: requests.Session, target: dict, lon: float, lat: float, tile_cache: dict[str, Image.Image]):
    tile_x, tile_y, px, py = core.slippy_pixel(lon, lat)
    url = f"{RAIN_BASE}/{target['basetime']}/none/{target['validtime']}/surf/rasrf/{core.TILE_ZOOM}/{tile_x}/{tile_y}.png"
    image = _tile_image(session, url, tile_cache)
    if image is None:
        return None
    opaque = 0
    for dx, dy in [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0), (0, 2), (0, -2)]:
        x, y = max(0, min(255, px + dx)), max(0, min(255, py + dy))
        _r, _g, _b, a = image.getpixel((x, y))
        if a >= 40:
            opaque += 1
    return opaque > 0


def build_hourly_rain(session: requests.Session, targets: list[dict], day: str, start_times: list[str], lon: float, lat: float, tile_cache: dict[str, Image.Image]):
    if not start_times:
        return []
    base_day = date.fromisoformat(day)
    selected = {}
    for start_time in start_times:
        minutes = core.parse_minutes(start_time)
        if minutes is None:
            continue
        start_dt = datetime.combine(base_day, datetime.min.time(), tzinfo=core.JST) + timedelta(minutes=minutes)
        for offset in (-60, 0, 60):
            desired = start_dt + timedelta(minutes=offset)
            target = _latest_target_near(targets, desired, "rasrf", tolerance_minutes=40)
            if target:
                selected[str(target.get("validtime") or "")] = target

    rows = []
    for target in selected.values():
        try:
            valid = core.utc_target_datetime(str(target.get("validtime") or ""))
            rain = _sample_rain_presence(session, target, lon, lat, tile_cache)
        except Exception:
            continue
        if rain is None:
            continue
        rows.append({
            "time": valid.strftime("%H:%M"),
            "rain": bool(rain),
            "validAt": valid.isoformat(timespec="minutes"),
        })
    rows.sort(key=lambda row: row["validAt"])
    return rows


def _start_time_map():
    try:
        events = (json.loads(core.EVENTS_PATH.read_text(encoding="utf-8")).get("events") or [])
    except Exception:
        return {}
    result = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        for row in core.occurrence_rows(event):
            start_time = str(row.get("startTime") or "")
            if core.parse_minutes(start_time) is None:
                continue
            key = (str(row.get("date") or ""), core.normalize_venue(row.get("venue") or ""))
            result.setdefault(key, set()).add(start_time)
    return {key: sorted(values) for key, values in result.items()}


def augment_weather_output():
    if not core.OUTPUT_PATH.exists() or not core.COORDS_PATH.exists():
        return
    try:
        payload = json.loads(core.OUTPUT_PATH.read_text(encoding="utf-8"))
        coords = json.loads(core.COORDS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return

    entries = payload.get("entries") or []
    if not isinstance(entries, list):
        return
    try:
        today = date.fromisoformat(str(payload.get("date") or ""))
    except ValueError:
        return

    session = requests.Session()
    session.headers.update({"User-Agent": "KeioKawaiiLabWeather/1.0 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"})
    try:
        weather_targets = core.get_json(session, core.WDIST_TARGETS_URL)
    except Exception:
        weather_targets = []
    try:
        rain_targets = core.get_json(session, RAIN_TARGETS_URL)
    except Exception:
        rain_targets = []

    weather_targets = weather_targets if isinstance(weather_targets, list) else []
    rain_targets = rain_targets if isinstance(rain_targets, list) else []
    starts = _start_time_map()
    tile_cache: dict[str, Image.Image] = {}
    mesh_timeline_count = 0
    hourly_rain_count = 0

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            event_day = date.fromisoformat(str(entry.get("date") or ""))
        except ValueError:
            continue
        if not (0 <= (event_day - today).days <= core.MESH_DAYS):
            entry.pop("meshTimeline", None)
            entry.pop("hourlyRain", None)
            continue

        venue_key = str(entry.get("venueKey") or core.normalize_venue(entry.get("venue") or ""))
        saved = ((coords.get("venues") or {}).get(venue_key) or {}) if isinstance(coords, dict) else {}
        if not isinstance(saved, dict) or not saved.get("verifiedAddress"):
            continue
        try:
            lon, lat = float(saved["lon"]), float(saved["lat"])
        except (KeyError, TypeError, ValueError):
            continue

        timeline = build_mesh_timeline(session, weather_targets, entry["date"], lon, lat, tile_cache)
        if timeline:
            entry["meshTimeline"] = timeline
            entry["precision"] = "mesh5km"
            entry["coordinates"] = {"lat": lat, "lon": lon}
            mesh_timeline_count += 1

        start_times = starts.get((entry["date"], venue_key), [])
        hourly_rain = build_hourly_rain(session, rain_targets, entry["date"], start_times, lon, lat, tile_cache)
        if hourly_rain:
            entry["hourlyRain"] = hourly_rain
            hourly_rain_count += 1
        else:
            entry.pop("hourlyRain", None)

    stats = payload.setdefault("stats", {})
    stats["meshTimelineEntries"] = mesh_timeline_count
    stats["hourlyRainEntries"] = hourly_rain_count
    core.OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Weather detail augmented: timeline={mesh_timeline_count}, hourly-rain={hourly_rain_count}")


core.geocode = safe_geocode
core.choose_mesh_target = safe_choose_mesh_target

if __name__ == "__main__":
    code = core.main()
    if code == 0:
        augment_weather_output()
    raise SystemExit(code)
