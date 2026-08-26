#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

DATA_PATH = Path("data/live-events.json")
JST = timezone(timedelta(hours=9))
GROUPS = {
    "FRUITS ZIPPER": "https://fruitszipper.asobisystem.com",
    "CANDY TUNE": "https://candytune.asobisystem.com",
    "SWEET STEADY": "https://sweetsteady.asobisystem.com",
    "CUTIE STREET": "https://cutiestreet.asobisystem.com",
    "MORE STAR": "https://morestar.asobisystem.com",
}
SPECIAL_RE = re.compile(r"大特典会|リリースイベント|リリイベ|発売記念イベント")
DATE_RE = re.compile(
    r"(?:(20\d{2})年)?\s*(\d{1,2})月\s*(\d{1,2})日"
    r"(?:\s*[（(][^）)]*[）)])?(?:\s*(\d{1,2})[：:](\d{2}))?"
)
SLASH_DATE_RE = re.compile(
    r"(?:(20\d{2})[./-])?(\d{1,2})[/-](\d{1,2})"
    r"(?:\s*[（(][^）)]*[）)])?(?:\s*(\d{1,2})[：:](\d{2}))?"
)
TIME_RE = re.compile(r"(\d{1,2})[：:](\d{2})")


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def stable_id(*values: object) -> str:
    raw = "\x1f".join(str(value or "") for value in values)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def iso(match: re.Match, default_year: int) -> str | None:
    year, month, day, hour, minute = match.groups()
    try:
        value = datetime(
            int(year or default_year), int(month), int(day),
            int(hour or 0), int(minute or 0), tzinfo=JST,
        )
    except ValueError:
        return None
    result = value.strftime("%Y-%m-%d")
    if hour is not None:
        result += value.strftime("T%H:%M")
    return result


def time_value(text: str) -> str | None:
    match = TIME_RE.search(text)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def article_date(lines: list[str]) -> str | None:
    for line in lines[:80]:
        match = re.fullmatch(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", line)
        if match:
            return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return None


def value_after(lines: list[str], labels: tuple[str, ...]) -> str | None:
    for index, line in enumerate(lines):
        if not any(label in line for label in labels):
            continue
        tail = line
        for label in labels:
            tail = tail.split(label, 1)[-1] if label in tail else tail
        tail = tail.strip(" ：:")
        if tail:
            return tail
        for following in lines[index + 1:index + 4]:
            if following and not following.startswith("■"):
                return following
    return None


def value_after_heading(lines: list[str], labels: tuple[str, ...]) -> str | None:
    for index, line in enumerate(lines):
        clean = line.lstrip("■□●◇◆ ").strip()
        if clean not in labels:
            continue
        for following in lines[index + 1:index + 5]:
            if following and not following.startswith(("■", "□", "●", "◇", "◆")):
                return following
    return None


def date_after(lines: list[str], labels: tuple[str, ...], default_year: int) -> str | None:
    for index, line in enumerate(lines):
        if not any(label in line for label in labels):
            continue
        segment = " ".join(lines[index:index + 4])
        matches = [match for match in (DATE_RE.search(segment), SLASH_DATE_RE.search(segment)) if match]
        match = min(matches, key=lambda value: value.start()) if matches else None
        if match:
            return iso(match, default_year)
    return None


def window_rows(lines: list[str], default_year: int) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for index, line in enumerate(lines):
        if not re.search(r"受付(?:時間|期間)|予約期間|応募期間|エントリー受付|\d次受付", line):
            continue
        segment = " ".join(lines[index:index + 3])
        matches = list(DATE_RE.finditer(segment))
        if len(matches) < 2:
            continue
        start = iso(matches[0], default_year)
        end_year = int(start[:4]) if start else default_year
        end = iso(matches[1], end_year)
        if not start or not end or "T" not in start or "T" not in end:
            continue
        label_match = re.search(
            r"((?:(?:第?\d+部)[、・／/]\s*)*(?:第?\d+部)\s*\d次エントリー受付|\d次エントリー受付|応募期間|(?:\d次)?受付)",
            line,
        )
        label = label_match.group(1).replace("、", "・") if label_match else "予約受付"
        if label == "応募期間":
            label = "応募受付"
        row = (label, start, end)
        duplicate_index = next(
            (row_index for row_index, existing in enumerate(rows) if existing[1:] == row[1:]),
            None,
        )
        if duplicate_index is None:
            rows.append(row)
        elif "エントリー" in label and "エントリー" not in rows[duplicate_index][0]:
            rows[duplicate_index] = row
    return rows


def source_links(soup: BeautifulSoup, page_url: str) -> list[str]:
    result: list[str] = [page_url]
    for anchor in soup.find_all("a", href=True):
        href = urljoin(page_url, anchor.get("href", ""))
        if re.search(r"kawaiilab\.goods-order\.com|pages-kawaiilab\.goods-order\.com|sukisuki-shop\.com|r10\.to|rakuten|hmv\.co\.jp|tower\.jp", href, re.I):
            if href not in result:
                result.append(href)
    return result


def product_text(lines: list[str], title: str) -> str:
    for index, line in enumerate(lines):
        clean = line.lstrip("■□●◇◆〖〈＜ ").rstrip("〗〉＞ ")
        if clean not in {"対象商品", "イベント参加対象商品"}:
            continue
        block = []
        for value in lines[index + 1:index + 12]:
            if value.startswith(("■", "□", "◇", "◆")):
                break
            block.append(value)
        useful = [x for x in block if re.search(r"発売|シングル|アルバム|通常盤|限定盤|税込|¥|￥", x)]
        if useful:
            return " ／ ".join(useful[:4]).replace("\\", "¥")
    for index, line in enumerate(lines):
        if not re.search(r"(?:KLF|KLC|KLS|KLM)-?\d+|通常盤.*(?:税込|¥|￥)", line, re.I):
            continue
        nearby = [value for value in lines[max(0, index - 5):index] if "発売" in value]
        return " ／ ".join([*(nearby[-1:] if nearby else []), line]).replace("\\", "¥")
    match = re.search(r"[『「]([^』」]+)[』」]", title)
    return match.group(1) if match else "公式ページ記載のイベント参加対象商品"


def call_times(lines: list[str]) -> list[dict]:
    result = []
    for line in lines:
        match = re.search(r"[・●]\s*([\d〜～~\-番]+)\s*[＝=:：]\s*(\d{1,2})[：:](\d{2})", line)
        if not match:
            continue
        result.append({"numbers": match.group(1), "time": f"{int(match.group(2)):02d}:{match.group(3)}"})
    return result


def benefit_parts(lines: list[str]) -> list[dict]:
    result = []
    pattern = re.compile(
        r"<第(\d+)部>\s*(.*?)\s*(\d{1,2}:\d{2})\s*[〜～~-]\s*(\d{1,2}:\d{2})"
        r".*?受付開始\s*(\d{1,2}:\d{2}).*?受付終了\s*(\d{1,2}:\d{2})"
    )
    for line in lines:
        match = pattern.search(line)
        if not match:
            continue
        result.append({
            "part": f"第{match.group(1)}部",
            "content": normalize(match.group(2)),
            "start": time_value(match.group(3)),
            "end": time_value(match.group(4)),
            "receptionStart": time_value(match.group(5)),
            "receptionEnd": time_value(match.group(6)),
        })
    return result


def ticket_details(lines: list[str]) -> list[str]:
    result = []
    active = False
    for line in lines:
        if "配券種類" in line:
            active = True
            continue
        if active and line.startswith("■"):
            break
        if active and ("券＞" in line or "券」" in line) and "…" in line:
            result.append(line)
    return result[:5]


def provider(links: list[str], category: str) -> str:
    joined = " ".join(links).lower()
    if category == "release-event" or "goods-order.com" in joined:
        return "kawaii-store"
    if "r10.to" in joined or "rakuten" in joined:
        return "rakuten"
    if "hmv.co.jp" in joined:
        return "hmv"
    if "tower.jp" in joined:
        return "tower"
    if "sukisuki-shop.com/goods/" in joined:
        return "sukisuki"
    return "official"


def parse_page(group: str, url: str, html_text: str, now: datetime | None = None) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    lines = [normalize(x) for x in soup.get_text("\n", strip=True).splitlines() if normalize(x)]
    title_candidates = [
        normalize(node.get_text(" ", strip=True))
        for node in soup.find_all("h1")
        if node and normalize(node.get_text(" ", strip=True))
    ]
    title_candidates.extend(line for line in lines[:100] if SPECIAL_RE.search(line))
    if soup.find("title") and normalize(soup.find("title").get_text(" ", strip=True)):
        title_candidates.append(normalize(soup.find("title").get_text(" ", strip=True)))
    title = next((value for value in title_candidates if SPECIAL_RE.search(value)), title_candidates[0] if title_candidates else "")
    if not SPECIAL_RE.search(title + " " + " ".join(lines[:80])):
        return []
    category = "large-benefit" if "大特典会" in title else "release-event"
    display_title = re.split(r"\s*@|\s*＠", title, maxsplit=1)[0]
    display_title = re.sub(rf"^[【〖]?{re.escape(group)}[】〗]?\s*", "", display_title, flags=re.I)
    if category == "large-benefit":
        release = re.search(r"(\d+(?:st|nd|rd|th)シングル発売記念)", title, re.I)
        display_title = f"{group} {release.group(1) + ' ' if release else ''}大特典会"
    published = article_date(lines)
    default_year = int(published[:4]) if published else (now or datetime.now(JST)).year
    event_date = date_after(lines, ("開催日程", "開催日時", "公演日"), default_year)
    if not event_date:
        return []
    event_date = event_date[:10]
    venue = value_after_heading(lines, ("開催会場", "場所")) or value_after(lines, ("開催場所・会場",)) or "会場未定"
    links = source_links(soup, url)
    windows = window_rows(lines, default_year)
    current = (now or datetime.now(JST)).astimezone(JST)
    if category == "release-event" and not windows:
        if venue == "会場未定":
            return []
        return [{
            "id": stable_id("special-placeholder", group, url, event_date),
            "group": group,
            "title": title,
            "eventTitle": title,
            "displayTitle": display_title,
            "eventCategory": category,
            "ticketType": "現在受付なし",
            "applicationStatus": "none",
            "applyStart": None,
            "applyEnd": None,
            "resultDate": None,
            "paymentEnd": None,
            "specialDetailsStatus": "awaiting-details",
            "applicationDisplayMode": "schedule-only",
            "eventDate": event_date,
            "venue": venue,
            "url": url,
            "urls": links,
            "sourceType": "official-special",
            "primarySource": "official",
            "sourceCandidates": ["official"],
            "sourcePublishedAt": published,
            "eventScope": "kawaii-lab",
        }]
    if not windows:
        windows = [("対象商品予約", "", "")]

    sales_text = value_after(lines, ("CD販売開始時間", "販売開始時間")) or ""
    gathering_text = value_after(lines, ("優先エリア入場集合時間", "ミニライブ入場集合時間")) or ""
    start_text = value_after(lines, ("開演時間",)) or ""
    product = product_text(lines, title)
    calls = call_times(lines)
    parts = benefit_parts(lines)
    tickets = ticket_details(lines)
    full_text = " ".join(lines)
    is_lottery = (
        category == "large-benefit"
        and any("sukisuki-shop.com/goods/" in link.lower() for link in links)
        and bool(re.search(r"応募期間|エントリー受付", full_text))
    )
    is_fc_lottery = is_lottery and bool(re.search(r"ファンクラブ|FC限定|FC会員", full_text, re.I))
    result_date = date_after(lines, ("当選発表日時", "当選発表"), default_year) if is_lottery else None
    payment_end = date_after(lines, ("購入期間",), default_year) if is_lottery else None
    ticket_issue_date = date_after(lines, ("電子チケットの発行",), default_year) if is_lottery else None
    if is_lottery and "1部、5部" in full_text:
        parts = [part for part in parts if part.get("part") in {"第1部", "第5部"}]

    events = []
    for round_label, apply_start, apply_end in windows:
        provider_id = provider(links, category)
        if category == "release-event":
            ticket_type = "商品購入電子整理券（先着）"
            purchase_method = "KAWAII LAB. STOREアプリで商品購入整理券を取得し、会場で対象商品を購入"
            ticket_name = "商品購入整理券"
            issue_method = "KAWAII LAB. STOREアプリ（1人1回・先着順）"
        else:
            ticket_type = (
                f"{'FC限定・' if is_fc_lottery else ''}対象商品応募（抽選／{round_label}）"
                if is_lottery else f"対象商品予約（参加権付き・先着／{round_label}）"
            )
            purchase_method = (
                f"SUKISUKIで対象商品{'3枚' if '対象商品3枚' in full_text else ''}1セットの抽選に応募し、当選後に購入すると選択した部／メンバーの参加券が付与"
                if is_lottery else "指定の参加権付き対象商品を予約・購入すると、選択した部／メンバーの参加券が付与"
            )
            ticket_name = "メンバー個別2ショットチェキ撮影会参加券" if "2ショットチェキ" in full_text else "大特典会参加券"
            issue_method = (
                "SUKISUKIマイページへ電子チケットを付与"
                + (
                    f"（{int(ticket_issue_date[5:7])}月{int(ticket_issue_date[8:10])}日中予定）"
                    if ticket_issue_date else ""
                )
                if provider_id == "sukisuki" else "対象商品の購入後に案内される電子チケットまたは参加券"
            )
            if not tickets:
                tickets = [
                    "対象商品3枚1セットで、選択した部／メンバーの個別2ショットチェキ撮影会へ1口応募"
                    if is_lottery else "参加権付き対象商品1セットにつき、選択した部／メンバーの大特典会参加券1枚"
                ]
        end_dt = datetime.fromisoformat(apply_end).replace(tzinfo=JST) if apply_end else None
        status = "open" if end_dt and end_dt >= current else "none"
        event = {
            "id": stable_id("special", group, url, event_date, apply_start, round_label),
            "group": group,
            "title": title,
            "eventTitle": title,
            "displayTitle": display_title,
            "eventCategory": category,
            "ticketType": ticket_type,
            "ticketProvider": provider_id,
            "applyStart": apply_start or None,
            "applyEnd": apply_end or None,
            "resultDate": result_date,
            "paymentEnd": payment_end,
            "eventDate": event_date,
            "venue": venue,
            "salesStartTime": time_value(sales_text),
            "gatheringTime": time_value(gathering_text),
            "startTime": time_value(start_text) or (parts[0]["start"] if parts else None),
            "purchaseMethod": purchase_method,
            "ticketName": ticket_name,
            "ticketIssueMethod": issue_method,
            "product": product,
            "numberedCallTimes": calls,
            "parts": parts,
            "ticketBenefits": tickets,
            "url": url,
            "urls": links,
            "sourceType": "official-special",
            "primarySource": "official",
            "sourceCandidates": list(dict.fromkeys(["official", provider_id])),
            "sourcePublishedAt": published,
            "applicationStatus": status,
            "applicationWindowVerified": bool(apply_start and apply_end),
            "deadlineVerified": bool(apply_end),
            "applicationDisplayMode": "band" if apply_start and apply_end else "schedule-only",
            "applicationWindowSource": url if apply_start and apply_end else None,
            "deadlineSource": url if apply_end else None,
        }
        events.append(event)
    return events


def discovery_seed_urls(payload: dict, group: str, today) -> list[str]:
    result: list[str] = []
    for event in payload.get("events", []):
        if not isinstance(event, dict) or event.get("group") != group:
            continue
        if event.get("sourceType") != "official-special":
            continue
        if str(event.get("eventDate") or "")[:10] < today.isoformat():
            continue
        value = str(event.get("discoverySourceUrl") or "").strip()
        if value and value not in result:
            result.append(value)
    return result


def add_discovery_source(event: dict, source_url: str | None) -> dict:
    if not source_url:
        return event
    out = dict(event)
    out["discoverySourceUrl"] = source_url
    links = list(out.get("urls") or [])
    if source_url not in links:
        links.append(source_url)
    out["urls"] = links
    return out


def discover(
    session: requests.Session,
    group: str,
    base: str,
    seed_urls: list[str] | None = None,
    today=None,
) -> tuple[list[dict], list[dict], bool]:
    today = today or datetime.now(JST).date()
    pages: dict[str, str] = {}
    page_origins: dict[str, set[str]] = {}
    for url in seed_urls or []:
        if url.startswith(base + "/news/detail/"):
            pages[url] = "article"
            page_origins.setdefault(url, set()).add("seed")
        elif url.startswith(base + "/live_information/detail/"):
            pages[url] = "live"
            page_origins.setdefault(url, set()).add("seed")
    live_parents: dict[str, str] = {}
    failures: list[dict] = []
    index_reachable = False
    discovery_sources_reached: set[str] = set()
    # Newly published articles can appear on the official home page before the
    # paginated INFORMATION index cache is refreshed.  Scan both so a same-day
    # application announcement cannot be missed during that cache window.
    discovery_urls = [f"{base}/", *(f"{base}/news/1/?page={page}" for page in range(1, 4))]
    for source_index, index_url in enumerate(discovery_urls):
        origin = "home" if source_index == 0 else f"index-{source_index}"
        try:
            response = session.get(index_url, timeout=20)
            response.raise_for_status()
        except requests.RequestException as exc:
            failures.append({"group": group, "url": index_url, "error": str(exc)})
            continue
        index_reachable = True
        soup = BeautifulSoup(response.text, "html.parser")
        news_links_found = False
        for anchor in soup.find_all("a", href=True):
            label = normalize(anchor.get_text(" ", strip=True))
            href = urljoin(base, anchor.get("href", ""))
            if "/news/detail/" in href:
                news_links_found = True
            if "/news/detail/" in href and SPECIAL_RE.search(label):
                pages[href] = "article"
                page_origins.setdefault(href, set()).add(origin)
        if news_links_found or origin not in {"home", "index-1"}:
            discovery_sources_reached.add(origin)
        time.sleep(0.08)

    missing_priority_sources = {"home", "index-1"} - discovery_sources_reached
    if missing_priority_sources:
        failures.append({
            "group": group,
            "url": base,
            "stage": "discovery",
            "critical": True,
            "error": "priority announcement sources unreachable: " + ", ".join(sorted(missing_priority_sources)),
        })

    events: list[dict] = []
    for url, page_type in list(pages.items()):
        if page_type != "article":
            continue
        try:
            response = session.get(url, timeout=20)
            response.raise_for_status()
        except requests.RequestException as exc:
            failures.append({
                "group": group,
                "url": url,
                "stage": "fetch",
                "critical": bool(page_origins.get(url, set()).intersection({"home", "seed", "index-1"})),
                "error": str(exc),
            })
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        parsed = parse_page(group, url, response.text)
        events.extend(add_discovery_source(event, url) for event in parsed)
        linked_live: list[str] = []
        for anchor in soup.find_all("a", href=True):
            href = urljoin(base, anchor.get("href", ""))
            if "/live_information/detail/" in href:
                pages.setdefault(href, "live")
                live_parents.setdefault(href, url)
                page_origins.setdefault(href, set()).update({"article", *page_origins.get(url, set())})
                linked_live.append(href)
        if not parsed and not linked_live:
            lines = [normalize(x) for x in soup.get_text("\n", strip=True).splitlines() if normalize(x)]
            published = article_date(lines)
            recent = False
            if published:
                try:
                    recent = datetime.fromisoformat(published).date() >= today - timedelta(days=2)
                except ValueError:
                    pass
            origins = page_origins.get(url, set())
            if recent or origins.intersection({"home", "seed", "index-1"}):
                failures.append({
                    "group": group,
                    "url": url,
                    "stage": "parse",
                    "critical": True,
                    "error": "recent special-event announcement could not be parsed",
                })
        time.sleep(0.08)

    for url, page_type in list(pages.items()):
        if page_type != "live":
            continue
        try:
            response = session.get(url, timeout=20)
            response.raise_for_status()
            parent = live_parents.get(url)
            parsed = parse_page(group, url, response.text)
            events.extend(add_discovery_source(event, parent) for event in parsed)
            if not parsed and page_origins.get(url, set()).intersection({"home", "seed", "index-1"}):
                failures.append({
                    "group": group,
                    "url": url,
                    "stage": "parse",
                    "critical": True,
                    "error": "linked special-event detail could not be parsed",
                })
        except requests.RequestException as exc:
            failures.append({
                "group": group,
                "url": url,
                "stage": "fetch",
                "critical": bool(page_origins.get(url, set()).intersection({"home", "seed", "index-1"})),
                "error": str(exc),
            })
        time.sleep(0.08)
    return events, failures, index_reachable


def merge_payload(payload: dict, fresh: list[dict], today=None) -> dict:
    today = today or datetime.now(JST).date()
    kept = []
    fresh_urls = {event.get("url") for event in fresh}
    replacements: dict[int, dict] = {}
    consumed_fresh: set[int] = set()

    # The official schedule often announces only a date and venue first.  When
    # the later news article adds the purchase window, replace that placeholder
    # in place.  Keeping its id preserves official-schedule audit references and
    # prevents the public page from showing the same event twice.
    for fresh_index, fresh_event in enumerate(fresh):
        fresh_category = str(fresh_event.get("eventCategory") or "")
        # Once a schedule placeholder has been upgraded, retain its id on every
        # later refresh as well; the official coverage index points to that id.
        for index, event in enumerate(payload.get("events", [])):
            if (
                not isinstance(event, dict)
                or event.get("sourceType") != "official-special"
                or not event.get("officialScheduleUrl")
            ):
                continue
            if not (
                event.get("url") == fresh_event.get("url")
                and event.get("group") == fresh_event.get("group")
                and str(event.get("eventDate") or "")[:10] == str(fresh_event.get("eventDate") or "")[:10]
                and event.get("applyStart") == fresh_event.get("applyStart")
                and event.get("applyEnd") == fresh_event.get("applyEnd")
            ):
                continue
            merged = dict(fresh_event)
            merged["id"] = event.get("id") or fresh_event.get("id")
            official_url = str(event.get("officialScheduleUrl") or "").strip()
            links = list(dict.fromkeys([
                *(fresh_event.get("urls") or []), str(fresh_event.get("url") or ""),
                *(event.get("urls") or []), official_url,
            ]))
            merged["urls"] = [value for value in links if value]
            if official_url:
                merged["officialScheduleUrl"] = official_url
            replacements[index] = merged
            consumed_fresh.add(fresh_index)
            break
        if fresh_index in consumed_fresh:
            continue
        for index, event in enumerate(payload.get("events", [])):
            if index in replacements or not isinstance(event, dict):
                continue
            if not (
                event.get("sourceType") == "official-special"
                and event.get("officialScheduleUrl")
                and event.get("url") == fresh_event.get("url")
                and event.get("group") == fresh_event.get("group")
                and str(event.get("eventDate") or "")[:10] == str(fresh_event.get("eventDate") or "")[:10]
            ):
                continue
            merged = dict(fresh_event)
            merged["id"] = event.get("id") or fresh_event.get("id")
            official_url = str(event.get("officialScheduleUrl") or "").strip()
            links = list(dict.fromkeys([
                *(fresh_event.get("urls") or []), str(fresh_event.get("url") or ""),
                *(event.get("urls") or []), official_url,
            ]))
            merged["urls"] = [value for value in links if value]
            merged["officialScheduleUrl"] = official_url
            replacements[index] = merged
            consumed_fresh.add(fresh_index)
            break
        if fresh_index in consumed_fresh:
            continue
        for index, event in enumerate(payload.get("events", [])):
            if not isinstance(event, dict) or event.get("sourceType") != "official-schedule":
                continue
            text = f"{event.get('eventTitle', '')} {event.get('title', '')}"
            schedule_category = (
                "large-benefit" if "大特典会" in text
                else "release-event" if re.search(r"リリースイベント|発売記念イベント", text)
                else ""
            )
            if not (
                schedule_category == fresh_category
                and event.get("group") == fresh_event.get("group")
                and str(event.get("eventDate") or "")[:10] == str(fresh_event.get("eventDate") or "")[:10]
            ):
                continue
            merged = dict(fresh_event)
            merged["id"] = event.get("id") or fresh_event.get("id")
            official_url = str(event.get("officialScheduleUrl") or event.get("url") or "").strip()
            links = list(dict.fromkeys([
                *(fresh_event.get("urls") or []),
                str(fresh_event.get("url") or ""),
                *(event.get("urls") or []),
                official_url,
            ]))
            merged["urls"] = [value for value in links if value]
            if official_url:
                merged["officialScheduleUrl"] = official_url
            replacements[index] = merged
            consumed_fresh.add(fresh_index)
            break

    for original_index, event in enumerate(payload.get("events", [])):
        if not isinstance(event, dict):
            continue
        if original_index in replacements:
            kept.append(replacements[original_index])
            continue
        if event.get("sourceType") == "official-special" and event.get("url") in fresh_urls:
            continue
        if event.get("sourceType") == "official-special":
            try:
                if datetime.fromisoformat(str(event.get("eventDate"))[:10]).date() < today:
                    continue
            except ValueError:
                pass
        kept.append(event)
    result = kept + [event for index, event in enumerate(fresh) if index not in consumed_fresh]
    result.sort(key=lambda event: (str(event.get("eventDate") or "9999"), str(event.get("group") or "")))
    out = dict(payload)
    out["events"] = result
    out["updatedAt"] = datetime.now(JST).isoformat(timespec="seconds")
    out["source"] = "KAWAII LAB.各グループ公式公開情報 + チケットぴあ・ローチケ・イープラス公開情報 + SUKISUKI公開オンライン特典会情報 + 公式大特典会・リリースイベント情報"
    return out


def event_data_changed(previous: dict, candidate: dict) -> bool:
    """Ignore timestamp-only refreshes so the fast job stays quiet."""
    return previous.get("events", []) != candidate.get("events", [])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers["User-Agent"] = "KeioKawaiiLabCalendarBot/1.5 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)"
    fresh: list[dict] = []
    failures: list[dict] = []
    reachable_groups = 0
    today = datetime.now(JST).date()
    for group, base in GROUPS.items():
        seeds = discovery_seed_urls(payload, group, today)
        found, failed, reachable = discover(session, group, base, seeds)
        fresh.extend(found)
        failures.extend(failed)
        reachable_groups += int(reachable)
    fresh = [
        event for event in fresh
        if str(event.get("eventDate") or "")[:10] >= today.isoformat()
    ]
    diagnostics = {
        "specialEvents": len(fresh),
        "reachableGroups": reachable_groups,
        "totalGroups": len(GROUPS),
        "criticalFailures": sum(1 for failure in failures if failure.get("critical")),
        "failures": failures,
    }
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
    if args.check:
        healthy = (
            reachable_groups >= len(GROUPS) - 1
            and not any(failure.get("critical") for failure in failures)
        )
        return 0 if healthy else 2
    if reachable_groups < len(GROUPS) - 1:
        print("Too many official group sites were unreachable; existing special-event data left untouched.")
        return 2
    if any(failure.get("critical") for failure in failures):
        print("A recent special-event announcement could not be verified; existing public data left untouched.")
        return 2
    if not fresh:
        print("No special events found; existing special-event data left untouched.")
        return 0
    merged = merge_payload(payload, fresh)
    if not event_data_changed(payload, merged):
        print("Special-event data is unchanged.")
        return 0
    DATA_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
