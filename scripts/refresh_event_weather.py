#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from PIL import Image

JST = ZoneInfo("Asia/Tokyo")
EVENTS_PATH = Path("data/live-events.json")
VENUES_PATH = Path("data/venues.json")
OUTPUT_PATH = Path("data/event-weather.json")
COORDS_PATH = Path("data/venue-coordinates.json")

AREA_URL = "https://www.jma.go.jp/bosai/common/const/area.json"
FORECAST_AREA_URL = "https://www.jma.go.jp/bosai/forecast/const/forecast_area.json"
FORECAST_BASE = "https://www.jma.go.jp/bosai/forecast/data/forecast/"
WDIST_TARGETS_URL = "https://www.jma.go.jp/bosai/jmatile/data/wdist/targetTimes.json"
WDIST_BASE = "https://www.jma.go.jp/bosai/jmatile/data/wdist"
JMA_SOURCE_URL = "https://www.jma.go.jp/bosai/forecast/"
GSI_GEOCODE_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"

HORIZON_DAYS = 7
MESH_DAYS = 1  # 当日・翌日のみ、気象庁の約5km天気分布を優先
TILE_ZOOM = 10

WEATHER_PALETTE = {
    "晴れ": (255, 170, 0),
    "くもり": (170, 170, 170),
    "雨": (0, 65, 255),
    "雨または雪": (160, 210, 255),
    "雪": (242, 242, 255),
}
TEMP_PALETTE = {
    "35℃以上": (180, 0, 104),
    "30〜34℃": (255, 40, 0),
    "25〜29℃": (255, 153, 0),
    "20〜24℃": (250, 245, 0),
    "15〜19℃": (255, 255, 150),
    "10〜14℃": (255, 255, 240),
    "5〜9℃": (185, 235, 255),
    "0〜4℃": (0, 150, 255),
    "-5〜-1℃": (0, 65, 255),
    "-5℃未満": (0, 32, 128),
}

# 会場名しか持たない直前イベント向けの安全な都道府県補助。
# 座標が取れない場合でも、広域予報を誤った都道府県に結び付けないための最小限の辞書。
FACILITY_PREFECTURE_HINTS = [
    (r"日本武道館|Zepp Haneda|アニメイト池袋|animate hall BLACK|ららぽーと立川立飛|豊洲|有明|東京ガーデンシアター|LINE CUBE SHIBUYA|ベルサール", "東京都"),
    (r"テラスモール松戸|幕張|森のホール21", "千葉県"),
    (r"戸田市文化会館|ところざわサクラタウン|大宮ソニックシティ", "埼玉県"),
    (r"横浜|ぴあアリーナ|カルッツかわさき|KT Zepp Yokohama", "神奈川県"),
]

WEATHER_CODE_LABELS = {
    "100": "晴れ", "101": "晴れ時々くもり", "102": "晴れ一時雨", "103": "晴れ時々雨",
    "110": "晴れのち時々くもり", "111": "晴れのちくもり", "112": "晴れのち一時雨",
    "113": "晴れのち時々雨", "114": "晴れのち雨", "200": "くもり", "201": "くもり時々晴れ",
    "202": "くもり一時雨", "203": "くもり時々雨", "210": "くもりのち時々晴れ",
    "211": "くもりのち晴れ", "212": "くもりのち一時雨", "213": "くもりのち時々雨",
    "214": "くもりのち雨", "300": "雨", "301": "雨時々晴れ", "302": "雨時々止む",
    "311": "雨のち晴れ", "313": "雨のちくもり", "400": "雪", "401": "雪時々晴れ",
    "402": "雪時々止む", "403": "雪時々雨", "411": "雪のち晴れ", "413": "雪のちくもり",
    "414": "雪のち雨",
}


def normalize_venue(value: object) -> str:
    text = str(value or "").normalize("NFKC") if hasattr(str(value or ""), "normalize") else str(value or "")
    # Python str has no normalize method; NFKC is intentionally approximated below for our venue keys.
    text = re.sub(r"^(北海道|東京都|京都府|大阪府|.{2,3}県)[\s　]*", "", text)
    text = re.sub(r"[\s　・･]", "", text)
    text = re.sub(r"(?:メイン)?大ホール|劇場棟", "", text)
    text = re.sub(r"[()（）]", "", text)
    return text.lower()


def normalize_venue(value: object) -> str:  # noqa: F811 - keep implementation explicit with unicodedata
    import unicodedata

    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"^(北海道|東京都|京都府|大阪府|.{2,3}県)[\s　]*", "", text)
    text = re.sub(r"[\s　・･]", "", text)
    text = re.sub(r"(?:メイン)?大ホール|劇場棟", "", text)
    text = re.sub(r"[()（）]", "", text)
    return text.lower()


def parse_day(value: object) -> str:
    match = re.match(r"^(20\d{2}-\d{2}-\d{2})", str(value or ""))
    return match.group(1) if match else ""


def occurrence_rows(event: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if isinstance(event.get("schedule"), list) and event["schedule"]:
        for item in event["schedule"]:
            if not isinstance(item, dict) or not item.get("venue"):
                continue
            rows.append({
                "date": parse_day(item.get("date") or event.get("eventDate")),
                "venue": str(item.get("venue") or ""),
                "startTime": str(item.get("startTime") or event.get("startTime") or ""),
                "eventId": str(event.get("id") or ""),
                "title": str(event.get("eventTitle") or event.get("title") or ""),
            })
        return [row for row in rows if row["date"]]

    venue = str(event.get("venue") or "")
    if not venue or re.search(r"オンライン|複数会場|会場未定|その他\s", venue):
        return rows
    days = event.get("eventDates") if isinstance(event.get("eventDates"), list) else [event.get("eventDate")]
    for value in days:
        day = parse_day(value)
        if day:
            rows.append({
                "date": day,
                "venue": venue,
                "startTime": str(event.get("startTime") or ""),
                "eventId": str(event.get("id") or ""),
                "title": str(event.get("eventTitle") or event.get("title") or ""),
            })
    return rows


def resolve_venue(name: str, venues: list[dict[str, Any]]) -> dict[str, Any] | None:
    requested = normalize_venue(name)
    if not requested:
        return None
    for venue in venues:
        for candidate in [venue.get("name"), *(venue.get("aliases") or [])]:
            key = normalize_venue(candidate)
            if key and (requested == key or requested in key or key in requested):
                return venue
    return None


def prefecture_from_text(text: str) -> str:
    match = re.search(
        r"北海道|東京都|京都府|大阪府|青森県|岩手県|宮城県|秋田県|山形県|福島県|茨城県|栃木県|群馬県|埼玉県|千葉県|神奈川県|新潟県|富山県|石川県|福井県|山梨県|長野県|岐阜県|静岡県|愛知県|三重県|滋賀県|兵庫県|奈良県|和歌山県|鳥取県|島根県|岡山県|広島県|山口県|徳島県|香川県|愛媛県|高知県|福岡県|佐賀県|長崎県|熊本県|大分県|宮崎県|鹿児島県|沖縄県",
        str(text or ""),
    )
    if match:
        return match.group(0)
    for pattern, prefecture in FACILITY_PREFECTURE_HINTS:
        if re.search(pattern, str(text or ""), re.I):
            return prefecture
    return ""


def session_get_json(session: requests.Session, url: str, *, params: dict[str, str] | None = None) -> Any:
    response = session.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def clean_geocode_query(value: str) -> str:
    text = re.sub(r"^[^\s　]+?[都道府県][\s　]+", "", str(value or ""))
    text = re.sub(r"\([^)]*\)|（[^）]*）", "", text)
    text = re.sub(r"\b\d+F\b|\d+階|イベント広場|メインステージ|シーサイドデッキ|千人テラス", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def geocode(
    session: requests.Session,
    venue_name: str,
    venue_record: dict[str, Any] | None,
    cache: dict[str, Any],
) -> dict[str, Any] | None:
    key = normalize_venue(venue_name)
    saved = (cache.get("venues") or {}).get(key)
    if isinstance(saved, dict) and saved.get("lat") is not None and saved.get("lon") is not None:
        return saved

    queries: list[str] = []
    if venue_record and venue_record.get("address"):
        queries.append(str(venue_record["address"]))
    queries.extend([venue_name, clean_geocode_query(venue_name)])
    seen: set[str] = set()
    for query in queries:
        query = query.strip()
        if not query or query in seen:
            continue
        seen.add(query)
        try:
            payload = session_get_json(session, GSI_GEOCODE_URL, params={"q": query})
        except Exception:
            continue
        if not isinstance(payload, list) or not payload:
            continue
        feature = payload[0]
        coords = ((feature or {}).get("geometry") or {}).get("coordinates") or []
        title = str(((feature or {}).get("properties") or {}).get("title") or "")
        if len(coords) < 2:
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            continue
        result = {
            "query": query,
            "title": title,
            "lon": round(lon, 6),
            "lat": round(lat, 6),
            "prefecture": prefecture_from_text(title) or prefecture_from_text(venue_name),
        }
        cache.setdefault("venues", {})[key] = result
        return result
    return None


def office_code_for_prefecture(prefecture: str, area_map: dict[str, Any]) -> str:
    for code, office in (area_map.get("offices") or {}).items():
        if isinstance(office, dict) and office.get("name") == prefecture:
            return code
    return ""


def class10_for_location(
    office_code: str,
    location_text: str,
    area_map: dict[str, Any],
) -> str:
    class20s = area_map.get("class20s") or {}
    class15s = area_map.get("class15s") or {}
    class10s = area_map.get("class10s") or {}
    candidates: list[tuple[int, str]] = []
    for _, area20 in class20s.items():
        if not isinstance(area20, dict):
            continue
        name = str(area20.get("name") or "")
        if not name or name not in location_text:
            continue
        area15 = class15s.get(area20.get("parent")) or {}
        class10_code = str(area15.get("parent") or "")
        area10 = class10s.get(class10_code) or {}
        if class10_code and area10.get("parent") == office_code:
            candidates.append((len(name), class10_code))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]
    office = (area_map.get("offices") or {}).get(office_code) or {}
    children = office.get("children") or []
    return str(children[0]) if children else ""


def area_name(class10_code: str, area_map: dict[str, Any]) -> str:
    return str(((area_map.get("class10s") or {}).get(class10_code) or {}).get("name") or "")


def representative_point(office_code: str, class10_code: str, forecast_area: dict[str, Any]) -> str:
    for item in forecast_area.get(office_code, []) if isinstance(forecast_area, dict) else []:
        if isinstance(item, dict) and item.get("class10") == class10_code:
            points = item.get("amedas") or []
            return str(points[0]) if points else ""
    return ""


def weather_label(code: str, raw: str = "") -> str:
    raw = re.sub(r"[\s　]+", " ", str(raw or "")).strip()
    if raw:
        return raw
    if str(code) in WEATHER_CODE_LABELS:
        return WEATHER_CODE_LABELS[str(code)]
    first = str(code or "")[:1]
    return {"1": "晴れ", "2": "くもり", "3": "雨", "4": "雪"}.get(first, "天気予報")


def find_area(series: dict[str, Any], code: str) -> dict[str, Any] | None:
    for item in series.get("areas", []) if isinstance(series, dict) else []:
        if str(((item or {}).get("area") or {}).get("code") or "") == code:
            return item
    return None


def index_for_date(series: dict[str, Any], day: str) -> int:
    for index, value in enumerate(series.get("timeDefines", []) if isinstance(series, dict) else []):
        if str(value)[:10] == day:
            return index
    return -1


def parse_minutes(value: str) -> int | None:
    match = re.match(r"^(\d{1,2}):(\d{2})$", str(value or ""))
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def broad_forecast(
    payload: list[Any],
    day: str,
    class10_code: str,
    point_code: str,
    start_time: str,
) -> dict[str, Any] | None:
    if not isinstance(payload, list) or not payload:
        return None
    start_minutes = parse_minutes(start_time)

    short = payload[0] if len(payload) > 0 and isinstance(payload[0], dict) else {}
    series = short.get("timeSeries") or []
    if series:
        weather_series = series[0] if len(series) > 0 else {}
        weather_area = find_area(weather_series, class10_code)
        wi = index_for_date(weather_series, day)
        if weather_area is not None and wi >= 0:
            codes = weather_area.get("weatherCodes") or []
            texts = weather_area.get("weathers") or []
            code = str(codes[wi]) if wi < len(codes) else ""
            raw = str(texts[wi]) if wi < len(texts) else ""
            result: dict[str, Any] = {
                "label": weather_label(code, raw),
                "code": code,
                "max": None,
                "min": None,
                "pop": None,
                "popLabel": "",
                "issuedAt": str(short.get("reportDatetime") or ""),
            }

            if len(series) > 1:
                pop_series = series[1]
                pop_area = find_area(pop_series, class10_code)
                if pop_area:
                    choices: list[tuple[int, int, str]] = []
                    for idx, ts in enumerate(pop_series.get("timeDefines") or []):
                        if str(ts)[:10] != day:
                            continue
                        values = pop_area.get("pops") or []
                        if idx >= len(values) or values[idx] in (None, ""):
                            continue
                        dt = datetime.fromisoformat(str(ts))
                        mins = dt.hour * 60 + dt.minute
                        choices.append((mins, int(values[idx]), str(values[idx])))
                    if choices:
                        if start_minutes is not None:
                            prior = [item for item in choices if item[0] <= start_minutes]
                            chosen = prior[-1] if prior else choices[0]
                            result["pop"] = chosen[2]
                            result["popLabel"] = f"{chosen[0] // 60:02d}〜{(chosen[0] // 60 + 6) % 24:02d}時"
                        else:
                            chosen = max(choices, key=lambda item: item[1])
                            result["pop"] = chosen[2]
                            result["popLabel"] = "当日最大"

            if len(series) > 2 and point_code:
                temp_series = series[2]
                temp_area = find_area(temp_series, point_code)
                if temp_area:
                    values: list[float] = []
                    temps = temp_area.get("temps") or []
                    for idx, ts in enumerate(temp_series.get("timeDefines") or []):
                        if str(ts)[:10] != day or idx >= len(temps):
                            continue
                        try:
                            values.append(float(temps[idx]))
                        except (TypeError, ValueError):
                            pass
                    if values:
                        result["min"] = min(values)
                        result["max"] = max(values)
            return result

    weekly = payload[1] if len(payload) > 1 and isinstance(payload[1], dict) else {}
    weekly_series = weekly.get("timeSeries") or []
    if not weekly_series:
        return None
    weather_series = weekly_series[0]
    weather_area = find_area(weather_series, class10_code)
    wi = index_for_date(weather_series, day)
    if weather_area is None or wi < 0:
        return None
    codes = weather_area.get("weatherCodes") or []
    pops = weather_area.get("pops") or []
    code = str(codes[wi]) if wi < len(codes) else ""
    result = {
        "label": weather_label(code),
        "code": code,
        "max": None,
        "min": None,
        "pop": str(pops[wi]) if wi < len(pops) and pops[wi] not in (None, "") else None,
        "popLabel": "1日",
        "issuedAt": str(weekly.get("reportDatetime") or ""),
    }
    if len(weekly_series) > 1 and point_code:
        temp_series = weekly_series[1]
        temp_area = find_area(temp_series, point_code)
        ti = index_for_date(temp_series, day)
        if temp_area is not None and ti >= 0:
            mins = temp_area.get("tempsMin") or []
            maxs = temp_area.get("tempsMax") or []
            try:
                if ti < len(mins) and mins[ti] not in (None, ""):
                    result["min"] = float(mins[ti])
            except (TypeError, ValueError):
                pass
            try:
                if ti < len(maxs) and maxs[ti] not in (None, ""):
                    result["max"] = float(maxs[ti])
            except (TypeError, ValueError):
                pass
    return result


def utc_target_datetime(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).astimezone(JST)


def choose_mesh_target(targets: list[dict[str, Any]], day: str, start_time: str) -> dict[str, Any] | None:
    desired = parse_minutes(start_time)
    if desired is None:
        desired = 15 * 60
    candidates: list[tuple[int, dict[str, Any]]] = []
    for item in targets:
        if not isinstance(item, dict) or "wm" not in (item.get("elements") or []):
            continue
        try:
            valid = utc_target_datetime(str(item.get("validtime") or ""))
        except Exception:
            continue
        if valid.date().isoformat() != day:
            continue
        mins = valid.hour * 60 + valid.minute
        candidates.append((abs(mins - desired), item))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0])
    return candidates[0][1]


def slippy_pixel(lon: float, lat: float, zoom: int = TILE_ZOOM) -> tuple[int, int, int, int]:
    n = 2**zoom
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(max(min(lat, 85.05112878), -85.05112878))
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    tile_x, tile_y = int(x), int(y)
    px = max(0, min(255, int((x - tile_x) * 256)))
    py = max(0, min(255, int((y - tile_y) * 256)))
    return tile_x, tile_y, px, py


def closest_palette(rgb: tuple[int, int, int], palette: dict[str, tuple[int, int, int]]) -> str:
    return min(
        palette,
        key=lambda label: sum((rgb[i] - palette[label][i]) ** 2 for i in range(3)),
    )


def sample_tile(
    session: requests.Session,
    target: dict[str, Any],
    element: str,
    lon: float,
    lat: float,
    palette: dict[str, tuple[int, int, int]],
) -> str | None:
    tile_x, tile_y, px, py = slippy_pixel(lon, lat)
    url = (
        f"{WDIST_BASE}/{target['basetime']}/none/{target['validtime']}/surf/{element}/"
        f"{TILE_ZOOM}/{tile_x}/{tile_y}.png"
    )
    response = session.get(url, timeout=30)
    if not response.ok:
        return None
    image = Image.open(io.BytesIO(response.content)).convert("RGBA")
    samples: list[tuple[int, int, int]] = []
    for dx, dy in [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0), (0, 2), (0, -2)]:
        x, y = max(0, min(255, px + dx)), max(0, min(255, py + dy))
        r, g, b, a = image.getpixel((x, y))
        if a >= 80:
            samples.append((r, g, b))
    if not samples:
        return None
    # 最頻の近似カテゴリを採ることで境界ピクセルの影響を抑える。
    labels = [closest_palette(rgb, palette) for rgb in samples]
    return max(set(labels), key=labels.count)


def mesh_forecast(
    session: requests.Session,
    targets: list[dict[str, Any]],
    day: str,
    start_time: str,
    lon: float,
    lat: float,
) -> dict[str, Any] | None:
    target = choose_mesh_target(targets, day, start_time)
    if not target:
        return None
    label = sample_tile(session, target, "wm", lon, lat, WEATHER_PALETTE)
    if not label:
        return None
    temp_band = None
    if "temp" in (target.get("elements") or []):
        temp_band = sample_tile(session, target, "temp", lon, lat, TEMP_PALETTE)
    valid = utc_target_datetime(str(target.get("validtime") or ""))
    return {
        "label": label,
        "meshTempBand": temp_band,
        "meshTime": valid.strftime("%H:%M"),
        "validAt": valid.isoformat(timespec="minutes"),
    }


def stable_output(payload: dict[str, Any], old: dict[str, Any] | None) -> dict[str, Any]:
    if old and old.get("date") == payload.get("date") and old.get("entries") == payload.get("entries"):
        payload["generatedAt"] = old.get("generatedAt") or payload["generatedAt"]
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="JST date YYYY-MM-DD (tests/manual run)")
    args = parser.parse_args()

    now = datetime.now(JST)
    today = date.fromisoformat(args.date) if args.date else now.date()
    last_day = today + timedelta(days=HORIZON_DAYS)

    events_payload = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    venues_payload = json.loads(VENUES_PATH.read_text(encoding="utf-8"))
    events = events_payload.get("events") or []
    venues = venues_payload.get("venues") or []

    coords_cache: dict[str, Any] = {"updatedAt": "", "venues": {}}
    if COORDS_PATH.exists():
        try:
            coords_cache = json.loads(COORDS_PATH.read_text(encoding="utf-8"))
            coords_cache.setdefault("venues", {})
        except Exception:
            coords_cache = {"updatedAt": "", "venues": {}}
    original_coords = json.dumps(coords_cache.get("venues", {}), ensure_ascii=False, sort_keys=True)

    session = requests.Session()
    session.headers.update({"User-Agent": "KeioKawaiiLabWeather/1.0 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"})

    area_map = session_get_json(session, AREA_URL)
    forecast_area = session_get_json(session, FORECAST_AREA_URL)
    targets = session_get_json(session, WDIST_TARGETS_URL)

    rows: list[dict[str, str]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        for row in occurrence_rows(event):
            try:
                row_day = date.fromisoformat(row["date"])
            except ValueError:
                continue
            if today <= row_day <= last_day:
                rows.append(row)

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = f"{row['date']}|{normalize_venue(row['venue'])}"
        if key not in grouped:
            grouped[key] = {**row, "eventIds": [], "titles": []}
        if row["eventId"] and row["eventId"] not in grouped[key]["eventIds"]:
            grouped[key]["eventIds"].append(row["eventId"])
        if row["title"] and row["title"] not in grouped[key]["titles"]:
            grouped[key]["titles"].append(row["title"])

    office_cache: dict[str, list[Any]] = {}
    entries: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for key in sorted(grouped):
        row = grouped[key]
        venue_name = row["venue"]
        venue_record = resolve_venue(venue_name, venues)
        address = str((venue_record or {}).get("address") or "")
        location_text = " ".join(filter(None, [venue_name, address]))
        prefecture = str((venue_record or {}).get("prefecture") or "") or prefecture_from_text(location_text)

        geo = geocode(session, venue_name, venue_record, coords_cache)
        if geo:
            location_text += " " + str(geo.get("title") or "")
            prefecture = str(geo.get("prefecture") or prefecture)

        office_code = office_code_for_prefecture(prefecture, area_map)
        if not office_code:
            failures.append({"date": row["date"], "venue": venue_name, "reason": "都道府県を解決できません"})
            continue
        class10_code = class10_for_location(office_code, location_text, area_map)
        if not class10_code:
            failures.append({"date": row["date"], "venue": venue_name, "reason": "気象庁予報区域を解決できません"})
            continue
        point_code = representative_point(office_code, class10_code, forecast_area)

        try:
            if office_code not in office_cache:
                office_cache[office_code] = session_get_json(session, FORECAST_BASE + quote(office_code) + ".json")
            broad = broad_forecast(office_cache[office_code], row["date"], class10_code, point_code, row["startTime"])
        except Exception as error:
            failures.append({"date": row["date"], "venue": venue_name, "reason": f"広域予報取得失敗: {error}"})
            continue
        if not broad:
            failures.append({"date": row["date"], "venue": venue_name, "reason": "開催日の予報がまだありません"})
            continue

        day_distance = (date.fromisoformat(row["date"]) - today).days
        precision = "area"
        mesh: dict[str, Any] | None = None
        if day_distance <= MESH_DAYS and geo:
            try:
                mesh = mesh_forecast(
                    session,
                    targets if isinstance(targets, list) else [],
                    row["date"],
                    row["startTime"],
                    float(geo["lon"]),
                    float(geo["lat"]),
                )
            except Exception:
                mesh = None
            if mesh:
                precision = "mesh5km"

        entry = {
            "date": row["date"],
            "venue": venue_name,
            "venueKey": normalize_venue(venue_name),
            "eventIds": row["eventIds"],
            "areaCode": class10_code,
            "areaName": area_name(class10_code, area_map),
            "precision": precision,
            "label": mesh.get("label") if mesh else broad.get("label"),
            "max": broad.get("max"),
            "min": broad.get("min"),
            "pop": broad.get("pop"),
            "popLabel": broad.get("popLabel"),
            "issuedAt": broad.get("issuedAt"),
            "meshTime": mesh.get("meshTime") if mesh else None,
            "meshTempBand": mesh.get("meshTempBand") if mesh else None,
            "coordinates": {"lat": geo.get("lat"), "lon": geo.get("lon")} if mesh and geo else None,
        }
        entries.append(entry)

    payload = {
        "date": today.isoformat(),
        "horizonDays": HORIZON_DAYS,
        "generatedAt": now.isoformat(timespec="minutes"),
        "source": {"name": "気象庁", "url": JMA_SOURCE_URL},
        "entries": entries,
        "stats": {
            "occurrencesInRange": len(rows),
            "uniqueVenueDates": len(grouped),
            "weatherEntries": len(entries),
            "meshEntries": sum(1 for item in entries if item.get("precision") == "mesh5km"),
            "failures": len(failures),
        },
        "failures": failures,
    }

    old = None
    if OUTPUT_PATH.exists():
        try:
            old = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        except Exception:
            old = None
    payload = stable_output(payload, old)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    current_coords = json.dumps(coords_cache.get("venues", {}), ensure_ascii=False, sort_keys=True)
    if current_coords != original_coords:
        coords_cache["updatedAt"] = now.isoformat(timespec="minutes")
    COORDS_PATH.write_text(json.dumps(coords_cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        "Event weather refreshed:",
        f"{len(entries)}/{len(grouped)} venue-date entries,",
        f"mesh={payload['stats']['meshEntries']}, failures={len(failures)}",
    )
    for failure in failures:
        print("WARN", failure["date"], failure["venue"], failure["reason"])

    # 予報が存在するはずの範囲で全件ゼロは明確な異常としてActionsを落とす。
    if grouped and not entries:
        raise SystemExit("No weather entry was generated although upcoming events exist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
