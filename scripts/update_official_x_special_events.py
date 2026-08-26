#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DATA_PATH = Path("data/live-events.json")
JST = timezone(timedelta(hours=9))
GROUP_X = {
    "FRUITS ZIPPER": "FRUITS_ZIPPER",
    "CANDY TUNE": "CANDY_TUNE_",
    "SWEET STEADY": "SWEET_STEADY",
    "CUTIE STREET": "CUTIE_STREET_",
    "MORE STAR": "MORE_STAR_",
}
SPECIAL_RE = re.compile(r"大特典会|リリースイベント|リリイベ|発売記念イベント")
DATE_RE = re.compile(r"(?:(20\d{2})[./年-])?\s*(\d{1,2})\s*[./月-]\s*(\d{1,2})\s*日?")
VENUE_RE = re.compile(r"^(?:📍|会場[：:]?|場所[：:]?|開催場所[：:]?)\s*(.+)$")
PLACEHOLDER_VENUES = {"未定", "会場未定", "詳細は追ってお知らせします", "詳細は後日発表"}
APPLICATION_WORDS = ("受付", "申込", "販売", "予約開始", "締切")


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def stable_id(*values: object) -> str:
    raw = "\x1f".join(str(value or "") for value in values)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def special_category(value: object) -> str:
    text = str(value or "")
    if text in {"large-benefit", "release-event"}:
        return text
    return "large-benefit" if "大特典会" in text else "release-event" if SPECIAL_RE.search(text) else ""


def event_day(event: dict) -> str:
    return str(event.get("eventDate") or "")[:10]


def event_key(event: dict) -> tuple[str, str, str]:
    return (str(event.get("group") or ""), event_day(event), special_category(event.get("eventCategory") or event.get("title")))


def infer_date(match: re.Match, today: date) -> date | None:
    year_text, month_text, day_text = match.groups()
    try:
        year = int(year_text) if year_text else today.year
        candidate = date(year, int(month_text), int(day_text))
        if not year_text and candidate < today - timedelta(days=45):
            candidate = date(today.year + 1, candidate.month, candidate.day)
        return candidate
    except ValueError:
        return None


def dates_in_line(line: str, today: date) -> list[date]:
    if any(word in line for word in APPLICATION_WORDS):
        return []
    result = []
    for match in DATE_RE.finditer(line):
        parsed = infer_date(match, today)
        if parsed and parsed >= today and parsed not in result:
            result.append(parsed)
    return result


def extract_date(lines: list[str], today: date) -> date | None:
    preferred = []
    fallback = []
    for line in lines:
        parsed_values = dates_in_line(line, today)
        if not parsed_values:
            continue
        target = preferred if any(token in line for token in ("開催", "🗓", "📅", "日程")) else fallback
        target.extend(parsed_values)
    values = [*preferred, *fallback]
    return values[0] if values else None


def clean_venue(value: object) -> str | None:
    venue = normalize(value).strip("｜|・ ")
    if not venue or venue in PLACEHOLDER_VENUES or "詳細" in venue:
        return None
    return venue


def extract_venue(lines: list[str]) -> str | None:
    for line in lines:
        match = VENUE_RE.match(line.strip())
        if match:
            venue = clean_venue(match.group(1))
            if venue:
                return venue
    for index, line in enumerate(lines):
        if normalize(line) not in {"会場", "場所", "開催会場", "開催場所"}:
            continue
        for value in lines[index + 1:index + 3]:
            venue = clean_venue(value)
            if venue:
                return venue
    return None


def extract_occurrences(lines: list[str], today: date) -> list[tuple[date, str]]:
    """Pair each announced event date with the nearest following explicit venue.

    This handles official X posts that announce several release-event dates in one post,
    while deliberately refusing to guess venue text without an explicit venue marker.
    """
    paired: list[tuple[date, str]] = []
    for index, line in enumerate(lines):
        line_dates = dates_in_line(line, today)
        if not line_dates:
            continue
        venue = None
        for probe_index in range(index, min(len(lines), index + 5)):
            probe = lines[probe_index]
            if probe_index > index and dates_in_line(probe, today):
                break
            match = VENUE_RE.match(probe.strip())
            if match:
                venue = clean_venue(match.group(1))
                if venue:
                    break
            if normalize(probe) in {"会場", "場所", "開催会場", "開催場所"} and probe_index + 1 < len(lines):
                venue = clean_venue(lines[probe_index + 1])
                if venue:
                    break
        if not venue:
            continue
        for day in line_dates:
            item = (day, venue)
            if item not in paired:
                paired.append(item)

    if paired:
        return paired
    day = extract_date(lines, today)
    venue = extract_venue(lines)
    return [(day, venue)] if day and venue else []


def extract_title(group: str, text: str, lines: list[str], category: str) -> str:
    quoted = re.search(r"『([^』]*(?:リリースイベント|発売記念イベント|大特典会)[^』]*)』", text)
    if quoted:
        return normalize(quoted.group(1))
    for line in lines:
        if SPECIAL_RE.search(line) and len(normalize(line)) <= 180:
            return normalize(line).strip("💐🎡🎠📣🎪🌸✨🎁💿 ")
    return f"{group} {'大特典会' if category == 'large-benefit' else 'リリースイベント'}"


def post_url(article, handle: str) -> str | None:
    for meta in article.find_all("meta"):
        value = str(meta.get("content") or "")
        if re.fullmatch(rf"https://x\.com/{re.escape(handle)}/status/\d+", value):
            return value
    item_id = str(article.get("itemid") or article.get("itemID") or "")
    match = re.search(r"/status/(\d+)", item_id)
    if match:
        return f"https://x.com/{handle}/status/{match.group(1)}"
    for anchor in article.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        match = re.search(rf"/{re.escape(handle)}/status/(\d+)", href)
        if match:
            return f"https://x.com/{handle}/status/{match.group(1)}"
    return None


def article_text(article) -> str:
    candidates = [article.get_text("\n", strip=True)]
    for meta in article.find_all("meta"):
        value = str(meta.get("content") or "")
        if SPECIAL_RE.search(value):
            candidates.append(value)
    relevant = [value for value in candidates if SPECIAL_RE.search(value)]
    return max(relevant or candidates, key=len, default="")


def profile_payload_loaded(html: str) -> bool:
    return "SocialMediaPosting" in html and "/status/" in html


def parse_profile(group: str, handle: str, html: str, today: date | None = None) -> list[dict]:
    today = today or datetime.now(JST).date()
    soup = BeautifulSoup(html, "html.parser")
    found: dict[tuple[str, str, str], dict] = {}
    for article in soup.find_all("article"):
        item_type = str(article.get("itemtype") or article.get("itemType") or "")
        if "SocialMediaPosting" not in item_type:
            continue
        text = article_text(article)
        if not SPECIAL_RE.search(text):
            continue
        url = post_url(article, handle)
        if not url:
            continue
        lines = [normalize(value) for value in text.splitlines() if normalize(value)]
        category = special_category(text)
        if not category:
            continue
        title = extract_title(group, text, lines, category)
        for day, venue in extract_occurrences(lines, today):
            if day < today:
                continue
            key = (group, day.isoformat(), category)
            if key in found:
                continue
            found[key] = {
                "id": stable_id("official-x-special", group, day.isoformat(), category),
                "group": group,
                "title": title,
                "eventTitle": title,
                "displayTitle": title,
                "eventCategory": category,
                "ticketType": "現在受付なし",
                "applicationStatus": "none",
                "applyStart": None,
                "applyEnd": None,
                "resultDate": None,
                "paymentEnd": None,
                "specialDetailsStatus": "awaiting-details",
                "applicationDisplayMode": "schedule-only",
                "eventDate": day.isoformat(),
                "venue": venue,
                "url": url,
                "urls": [url],
                "sourceType": "official-social",
                "sourceChannel": "official-x",
                "primarySource": "official",
                "sourceCandidates": ["official"],
                "eventScope": "kawaii-lab",
            }
    return list(found.values())


def fetch_profile(session: requests.Session, handle: str) -> str:
    response = session.get(f"https://x.com/{handle}", timeout=25)
    response.raise_for_status()
    return response.text


def merge_payload(payload: dict, social_events: list[dict], today: date | None = None) -> dict:
    today = today or datetime.now(JST).date()
    events = [event for event in payload.get("events", []) if isinstance(event, dict)]
    social_by_key = {event_key(event): event for event in social_events if all(event_key(event))}

    official_site_keys = {
        event_key(event)
        for event in events
        if special_category(event.get("eventCategory") or event.get("title"))
        and event.get("sourceType") != "official-social"
        and event.get("primarySource") == "official"
    }

    result = []
    replaced = set()
    for event in events:
        key = event_key(event)
        if event.get("sourceType") != "official-social":
            result.append(event)
            continue
        try:
            if date.fromisoformat(event_day(event)) < today:
                continue
        except ValueError:
            continue
        if key in official_site_keys:
            continue
        fresh = social_by_key.get(key)
        if fresh:
            merged = dict(fresh)
            merged["id"] = event.get("id") or fresh.get("id")
            result.append(merged)
            replaced.add(key)
        else:
            result.append(event)

    for key, event in social_by_key.items():
        if key in official_site_keys or key in replaced:
            continue
        result.append(event)

    result.sort(key=lambda event: (event_day(event) or "9999-12-31", str(event.get("group") or ""), str(event.get("title") or "")))
    out = dict(payload)
    out["events"] = result
    if result != events:
        out["updatedAt"] = datetime.now(JST).isoformat(timespec="seconds")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en;q=0.8",
    })
    today = datetime.now(JST).date()
    fresh: list[dict] = []
    failures = []
    for group, handle in GROUP_X.items():
        try:
            html = fetch_profile(session, handle)
            if not profile_payload_loaded(html):
                raise RuntimeError("X returned HTML without a usable public timeline payload")
            fresh.extend(parse_profile(group, handle, html, today))
        except (requests.RequestException, RuntimeError) as exc:
            failures.append(f"{group} @{handle}: {exc}")

    print(f"Official X special-event scan: {len(fresh)} future placeholders, accounts={len(GROUP_X) - len(failures)}/{len(GROUP_X)}")
    for failure in failures:
        print(f"ERROR: official X scan failed: {failure}", file=sys.stderr)
    if failures:
        print("Official X special-event scan is incomplete; refusing to publish partial discovery data.", file=sys.stderr)
        return 1

    candidate = merge_payload(payload, fresh, today)
    changed = candidate.get("events", []) != payload.get("events", [])
    print(f"Official X merge: changed={changed}")
    if args.check:
        return 0
    if changed:
        DATA_PATH.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
