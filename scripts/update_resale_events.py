#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

import update_live_events as base

DATA_PATH = Path("data/live-events.json")
JST = ZoneInfo("Asia/Tokyo")
CENTRAL_BASE = "https://kawaiilab.asobisystem.com"
NEWS_PAGES = 15
WORKERS = 5
RESALE_TITLE_RE = re.compile(r"リセール", re.I)
RESALE_WINDOW_RE = re.compile(r"(?:リセール\s*)?(?:受付|申込)(?:・購入)?期間|リセール受付詳細", re.I)
GROUPS = tuple(base.GROUPS) + ("KAWAII LAB.合同",)


def clean(value: object) -> str:
    return base.normalize_space(str(value or ""))


def stable_id(*parts: object) -> str:
    raw = "\x1f".join(clean(x) for x in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def article_title_to_performance(title: str) -> str:
    text = clean(title)
    text = re.sub(r"[「『](.*?)[」』]\s*公演\s*リセールサービスのお知らせ.*$", r"\1", text)
    text = re.sub(r"\s*公演\s*[　 ]*リセールサービスのお知らせ.*$", "", text)
    text = re.sub(r"\s*リセールサービスのお知らせ.*$", "", text)
    return text.strip(" 　『』「」")


def title_key(value: object) -> str:
    text = clean(value).lower()
    text = re.sub(r"リセール(?:サービス)?(?:のお知らせ)?", "", text)
    text = re.sub(r"公演", "", text)
    return re.sub(r"[\s　!！・|｜\-–—_【】\[\]()（）『』「」:：./〜~]", "", text)


def infer_group(title: str, existing: list[dict], event_days: list[str]) -> str | None:
    direct = [g for g in base.GROUPS if g.lower() in title.lower()]
    if len(direct) == 1:
        return direct[0]
    if "KAWAII LAB." in title.upper() or "KAWAII LAB " in title.upper():
        return "KAWAII LAB.合同"
    candidates = []
    wanted = title_key(article_title_to_performance(title))
    for event in existing:
        group = clean(event.get("group"))
        if group not in GROUPS:
            continue
        day = clean(event.get("eventDate"))[:10]
        if event_days and day not in event_days:
            continue
        key = title_key(event.get("eventTitle") or event.get("title"))
        if key and wanted and (key in wanted or wanted in key):
            candidates.append(group)
    unique = list(dict.fromkeys(candidates))
    return unique[0] if len(unique) == 1 else None


def parse_date_match(match: re.Match, default_year: int) -> str | None:
    value = base.date_match_to_iso(match, default_year)
    return value


def date_matches(text: str, default_year: int) -> list[str]:
    result = []
    last_year = default_year
    for match in base.DATE_ANY_RE.finditer(text):
        value = parse_date_match(match, last_year)
        if not value:
            continue
        last_year = int(value[:4])
        result.append(value)
    return result


def extract_resale_windows(lines: list[str], article_year: int) -> list[tuple[int, str, str]]:
    found = []
    seen = set()
    for index, line in enumerate(lines):
        if not RESALE_WINDOW_RE.search(line):
            continue
        segment = " ".join(lines[index:index + 3])
        values = date_matches(segment, article_year)
        if len(values) < 2:
            continue
        start, end = values[0], values[1]
        if datetime.fromisoformat(end.replace("Z", "+00:00")) < datetime.fromisoformat(start.replace("Z", "+00:00")):
            end_dt = datetime.fromisoformat(end)
            end = end_dt.replace(year=end_dt.year + 1).strftime("%Y-%m-%dT%H:%M" if "T" in end else "%Y-%m-%d")
        marker = (start, end)
        if marker in seen:
            continue
        seen.add(marker)
        found.append((index, start, end))
    return found


def extract_event_day_candidates(lines: list[str], article_date: str | None, windows: list[tuple[int, str, str]], article_year: int) -> list[tuple[int, str]]:
    excluded = {str(article_date or "")[:10]}
    for _, start, end in windows:
        excluded.add(start[:10])
        excluded.add(end[:10])
    found = []
    seen = set()
    for index, line in enumerate(lines):
        if RESALE_WINDOW_RE.search(line) or "受付期間" in line or "申込期間" in line:
            continue
        values = date_matches(line, article_year)
        if not values:
            continue
        day = values[0][:10]
        if day in excluded or day in seen:
            continue
        if article_date and day < article_date[:10]:
            continue
        # Event dates in resale notices normally appear as 日程/対象公演 rows or a date-leading row.
        if not ("日程" in line or "公演" in line or "会場" in line or re.match(r"^[\s　【\[（(]*20?\d{0,4}年?\s*\d{1,2}[月/.-]\s*\d{1,2}", line)):
            continue
        seen.add(day)
        found.append((index, day))
    return found


def map_windows_to_days(event_days: list[tuple[int, str]], windows: list[tuple[int, str, str]]) -> list[tuple[str, str, str]] | None:
    if not event_days or not windows:
        return None
    if len(windows) == 1:
        _, start, end = windows[0]
        return [(day, start, end) for _, day in event_days]

    mapped = []
    used = set()
    for window_index, start, end in windows:
        preceding = [(idx, day) for idx, day in event_days if idx < window_index and day not in used]
        if not preceding:
            return None
        idx, day = max(preceding, key=lambda row: row[0])
        used.add(day)
        mapped.append((day, start, end))
    if len(mapped) != len(windows):
        return None
    return mapped


def performance_for(existing: list[dict], group: str, day: str, article_title: str) -> dict | None:
    wanted = title_key(article_title_to_performance(article_title))
    candidates = []
    for event in existing:
        if clean(event.get("group")) != group:
            continue
        days = []
        if isinstance(event.get("schedule"), list):
            days.extend(clean(row.get("date"))[:10] for row in event["schedule"] if isinstance(row, dict))
        if isinstance(event.get("eventDates"), list):
            days.extend(clean(x)[:10] for x in event["eventDates"])
        if event.get("eventDate"):
            days.append(clean(event.get("eventDate"))[:10])
        if day not in days:
            continue
        key = title_key(event.get("eventTitle") or event.get("title"))
        score = 0
        if key and wanted:
            if key == wanted:
                score = 100
            elif key in wanted or wanted in key:
                score = min(len(key), len(wanted))
        if clean(event.get("ticketType")) == "現在受付なし":
            score += 20
        if clean(event.get("sourceType")) not in {"pia", "eplus", "lawson"}:
            score += 5
        candidates.append((score, event))
    candidates.sort(key=lambda row: row[0], reverse=True)
    return dict(candidates[0][1]) if candidates else None


def resale_entry(article_url: str, article_title: str, article_date: str | None, group: str, day: str, start: str, end: str, existing: list[dict]) -> dict:
    base_event = performance_for(existing, group, day, article_title) or {}
    stable_title = clean(base_event.get("eventTitle") or base_event.get("title") or article_title_to_performance(article_title))
    now = datetime.now(JST)
    start_dt = datetime.fromisoformat(start).replace(tzinfo=JST)
    end_dt = datetime.fromisoformat(end).replace(tzinfo=JST)
    status = "upcoming" if now < start_dt else ("open" if now <= end_dt else "ended")
    return {
        "id": stable_id("official-resale", group, stable_title, day, start, end, article_url),
        "group": group,
        "title": stable_title,
        "eventTitle": stable_title,
        "ticketType": "公式リセール",
        "ticketProvider": "resale",
        "saleFamily": "resale",
        "applyStart": start,
        "applyEnd": end,
        "resultDate": None,
        "paymentEnd": None,
        "eventDate": day,
        "venue": base_event.get("venue"),
        "openTime": base_event.get("openTime"),
        "startTime": base_event.get("startTime"),
        "url": article_url,
        "urls": [article_url],
        "sourceType": "resale-official",
        "primarySource": "official",
        "sourceChannel": "kawaii-lab-resale",
        "sourceCandidates": ["kawaii-lab-resale"],
        "sourcePublishedAt": article_date,
        "applicationStatus": status,
        "applicationWindowVerified": True,
        "deadlineVerified": True,
        "applicationDisplayMode": "band",
        "applicationWindowSource": article_url,
        "deadlineSource": article_url,
    }


def parse_resale_article(html: str, article_url: str, article_title: str, existing: list[dict]) -> tuple[list[dict], dict | None]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [clean(x) for x in text.splitlines() if clean(x)]
    article_date = base.article_date_from_text(text)
    article_year = int(article_date[:4]) if article_date else datetime.now(JST).year
    windows = extract_resale_windows(lines, article_year)
    event_days = extract_event_day_candidates(lines, article_date, windows, article_year)
    mapped = map_windows_to_days(event_days, windows)
    if not mapped:
        return [], {
            "group": "KAWAII LAB. resale",
            "title": article_title,
            "url": article_url,
            "reason": "リセール告知を検出しましたが、公演日と受付期間を安全に対応付けできませんでした。",
            "windows": [{"applyStart": start, "applyEnd": end} for _, start, end in windows],
            "eventDates": [day for _, day in event_days],
        }
    group = infer_group(article_title, existing, [day for day, _, _ in mapped])
    if not group:
        return [], {
            "group": "KAWAII LAB. resale",
            "title": article_title,
            "url": article_url,
            "reason": "リセール対象グループを一意に特定できませんでした。",
            "eventDates": [day for day, _, _ in mapped],
        }
    rows = [resale_entry(article_url, article_title, article_date, group, day, start, end, existing) for day, start, end in mapped]
    return rows, None


def fetch_news_page(page: int, headers: dict[str, str]) -> str:
    url = f"{CENTRAL_BASE}/news/1/?page={page}"
    with requests.Session() as session:
        session.headers.update(headers)
        response = session.get(url, timeout=20)
        response.raise_for_status()
        return response.text


def discover_candidates(session: requests.Session) -> list[tuple[str, str]]:
    headers = {str(k): str(v) for k, v in session.headers.items()}
    html_by_page = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(fetch_news_page, page, headers): page for page in range(1, NEWS_PAGES + 1)}
        for future in as_completed(futures):
            page = futures[future]
            html_by_page[page] = future.result()
    if len(html_by_page) != NEWS_PAGES:
        raise RuntimeError(f"only {len(html_by_page)}/{NEWS_PAGES} KAWAII LAB. news pages were readable")
    found = {}
    for page in sorted(html_by_page):
        soup = BeautifulSoup(html_by_page[page], "html.parser")
        for anchor in soup.find_all("a", href=True):
            title = clean(anchor.get_text(" ", strip=True))
            href = clean(anchor.get("href"))
            if "/news/detail/" not in href or not RESALE_TITLE_RE.search(title):
                continue
            url = urljoin(CENTRAL_BASE, href)
            found[url] = title
    return list(found.items())


def merge_resale(existing_payload: dict, fresh: list[dict], today: date) -> dict:
    existing = [dict(x) for x in existing_payload.get("events", []) if isinstance(x, dict)]
    keep = [x for x in existing if clean(x.get("sourceType")) != "resale-official"]
    now = datetime.now(JST)
    for row in fresh:
        try:
            end = datetime.fromisoformat(clean(row.get("applyEnd"))).replace(tzinfo=JST)
        except ValueError:
            continue
        event_day = clean(row.get("eventDate"))[:10]
        if event_day < today.isoformat() or end < now:
            continue
        keep.append(row)
    seen = set()
    output = []
    for row in keep:
        marker = clean(row.get("id")) or stable_id(row.get("group"), row.get("eventDate"), row.get("ticketType"), row.get("applyStart"), row.get("applyEnd"), row.get("url"))
        if marker in seen:
            continue
        seen.add(marker)
        output.append(row)
    output.sort(key=lambda row: (clean(row.get("eventDate")) or "9999", clean(row.get("applyEnd")) or "9999", clean(row.get("group"))))
    result = dict(existing_payload)
    result["events"] = output
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect announced official KAWAII LAB. ticket resale windows.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    existing = [dict(x) for x in payload.get("events", []) if isinstance(x, dict)]
    session = requests.Session()
    session.headers.update({"User-Agent": "KeioKawaiiLabCalendarBot/2.4 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"})

    candidates = discover_candidates(session)
    rows = []
    pending = []
    failures = []
    for url, title in candidates:
        try:
            response = session.get(url, timeout=20)
            response.raise_for_status()
            parsed, review = parse_resale_article(response.text, url, title, existing)
            rows.extend(parsed)
            if review:
                pending.append(review)
        except Exception as exc:
            failures.append({"group": "KAWAII LAB. resale", "title": title, "url": url, "error": f"{type(exc).__name__}: {exc}"})
        time.sleep(0.05)

    diagnostics = {"articles": len(candidates), "parsedRows": len(rows), "pending": len(pending), "failures": failures}
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit("One or more official resale articles could not be read")
    if args.check:
        return 0

    merged = merge_resale(payload, rows, datetime.now(JST).date())
    existing_pending = [x for x in payload.get("pendingReview", []) if isinstance(x, dict) and clean(x.get("group")) != "KAWAII LAB. resale"]
    merged["pendingReview"] = existing_pending + pending
    merged["resaleDiagnostics"] = diagnostics
    DATA_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Merged {sum(1 for x in merged['events'] if clean(x.get('sourceType')) == 'resale-official')} active/upcoming official resale row(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
