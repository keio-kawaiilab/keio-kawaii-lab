#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import update_promoter_birthday_events as promoter

DATA_PATH = Path("data/live-events.json")
JST = timezone(timedelta(hours=9))
MONTHS_AHEAD = 8

GENERAL_RE = re.compile(r"一般(?:発売|販売)")
SOLD_OUT_RE = re.compile(r"SOLD\s*OUT|予定枚数終了|完売", re.I)
DATE_TIME_PATTERNS = (
    re.compile(
        r"(?P<m>\d{1,2})\s*/\s*(?P<d>\d{1,2})"
        r"(?:\s*[（(][^）)]*[）)])?\s*"
        r"(?P<h>\d{1,2})\s*[:：]\s*(?P<min>\d{2})"
    ),
    re.compile(
        r"(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日?"
        r"(?:\s*[（(][^）)]*[）)])?\s*"
        r"(?P<h>\d{1,2})\s*[:：]\s*(?P<min>\d{2})"
    ),
)
PROVIDER_HOSTS = {
    "t.pia.jp": "pia",
    "eplus.jp": "eplus",
    "l-tike.com": "lawson",
}


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def stable_id(*values: object) -> str:
    raw = "\x1f".join(str(value or "") for value in values)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def canonical_url(value: object) -> str:
    return str(value or "").strip().split("#", 1)[0]


def pid_values(node) -> set[str]:
    values: set[str] = set()
    try:
        anchors = node.find_all("a", href=True)
    except AttributeError:
        return values
    for anchor in anchors:
        href = str(anchor.get("href") or "")
        for match in promoter.PID_RE.finditer(href):
            values.add(match.group(1))
    return values


def candidate_context(anchor) -> str:
    own = normalize(anchor.get_text(" ", strip=True))
    node = anchor
    best = own
    for _ in range(6):
        node = getattr(node, "parent", None)
        if node is None:
            break
        # Once an ancestor contains multiple distinct performance IDs, it is a
        # list/grid wrapper rather than one event card. Never borrow text from a
        # neighbouring performance.
        pids = pid_values(node)
        if len(pids) > 1:
            break
        text = normalize(node.get_text(" ", strip=True))
        if len(text) > 1800:
            break
        best = text
        if promoter.BIRTHDAY_RE.search(text) and promoter.group_from_text(text):
            return text
    return best


def discover_birthday_candidates(html: str, base_url: str = promoter.BASE_URL) -> list[promoter.Candidate]:
    """Find only KAWAII LAB. birthday-event detail pages from a HOT STUFF month page.

    This deliberately avoids fetching every promoter event detail page.  A candidate
    must have birthday wording and one supported group in its local card/context.
    """
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, promoter.Candidate] = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        match = promoter.PID_RE.search(href)
        if not match:
            continue
        context = candidate_context(anchor)
        if not promoter.BIRTHDAY_RE.search(context):
            continue
        if not promoter.group_from_text(context):
            continue
        pid = match.group(1)
        url = promoter.canonical_detail_url(pid, base_url)
        found[url] = promoter.Candidate(url=url, context=context)
    return list(found.values())


def sale_year(event_day: str, month: int, day: int) -> int | None:
    try:
        event_date = date.fromisoformat(str(event_day)[:10])
        candidate = date(event_date.year, month, day)
    except ValueError:
        return None
    if candidate > event_date:
        candidate = date(event_date.year - 1, month, day)
    return candidate.year


def parse_sale_start(segment: str, event_day: str) -> str | None:
    for pattern in DATE_TIME_PATTERNS:
        match = pattern.search(segment)
        if not match:
            continue
        month = int(match.group("m"))
        day = int(match.group("d"))
        hour = int(match.group("h"))
        minute = int(match.group("min"))
        year = sale_year(event_day, month, day)
        if year is None:
            return None
        try:
            value = datetime(year, month, day, hour, minute)
        except ValueError:
            return None
        return value.strftime("%Y-%m-%dT%H:%M")
    return None


def provider_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    values: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = canonical_url(urljoin(base_url, str(anchor.get("href") or "")))
        try:
            host = (urlparse(href).hostname or "").lower()
        except ValueError:
            continue
        if host not in PROVIDER_HOSTS:
            continue
        if href not in values:
            values.append(href)
    return values


def provider_name(links: list[str]) -> str:
    for link in links:
        try:
            host = (urlparse(link).hostname or "").lower()
        except ValueError:
            continue
        if host in PROVIDER_HOSTS:
            return PROVIDER_HOSTS[host]
    return "promoter"


def extract_general_sale(soup: BeautifulSoup, event_day: str, source_url: str) -> dict | None:
    text = normalize(soup.get_text(" ", strip=True))
    match = GENERAL_RE.search(text)
    if not match:
        return None
    # Start after the explicit sale label so an earlier performance date can never
    # be mistaken for the ticket sale date.
    segment = text[match.start():match.start() + 600]
    start = parse_sale_start(segment, event_day)
    if not start:
        return None
    links = provider_links(soup, source_url)
    sold_out = bool(SOLD_OUT_RE.search(segment))
    return {
        "applyStart": start,
        "soldOutObserved": sold_out,
        "applicationStatus": "sold_out" if sold_out else "observed",
        "ticketProvider": provider_name(links),
        "providerLinks": links,
    }


def collect(session: requests.Session, today: date) -> tuple[list[dict], list[dict]]:
    candidates: dict[str, promoter.Candidate] = {}
    failures: list[dict] = []

    for year, month in promoter.month_pairs(today, MONTHS_AHEAD):
        url = f"{promoter.BASE_URL}/play/?mth={month}&y={year}"
        try:
            response = session.get(url, timeout=25)
            response.raise_for_status()
            for candidate in discover_birthday_candidates(response.text):
                candidates[candidate.url] = candidate
        except Exception as exc:
            failures.append({
                "stage": "month",
                "url": url,
                "error": f"{type(exc).__name__}: {exc}",
            })

    rows: list[dict] = []
    for candidate in candidates.values():
        try:
            response = session.get(candidate.url, timeout=25)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            event = promoter.parse_detail(candidate.url, response.text, today)
            if not event:
                continue
            sale = extract_general_sale(soup, str(event.get("eventDate") or ""), candidate.url)
            if not sale:
                continue
        except Exception as exc:
            failures.append({
                "stage": "detail",
                "url": candidate.url,
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue

        title = normalize(event.get("eventTitle") or event.get("title"))
        provider_links_list = sale["providerLinks"]
        row = {
            "id": stable_id(
                "promoter-general-sale",
                event.get("group"),
                event.get("eventDate"),
                sale["applyStart"],
                candidate.url,
            ),
            "group": event.get("group"),
            "title": title,
            "eventTitle": title,
            "displayTitle": title,
            "eventCategory": event.get("eventCategory") or "solo-live",
            "ticketType": "一般発売",
            "ticketProvider": sale["ticketProvider"],
            "applyStart": sale["applyStart"],
            "applyEnd": None,
            "resultDate": None,
            "paymentEnd": None,
            "applicationStatus": sale["applicationStatus"],
            "applicationDisplayMode": "offers",
            "applicationWindowVerified": True,
            "applicationWindowSource": candidate.url,
            "eventDate": event.get("eventDate"),
            "venue": event.get("venue"),
            "openTime": event.get("openTime"),
            "startTime": event.get("startTime"),
            "url": candidate.url,
            "urls": list(dict.fromkeys([candidate.url, *provider_links_list])),
            "sourceType": "ticket-history-guard",
            "sourceChannel": "promoter-general-sale",
            "primarySource": "promoter",
            "sourceCandidates": list(dict.fromkeys(["promoter", sale["ticketProvider"]])),
            "eventScope": "kawaii-lab",
            "historyPreserved": True,
            "soldOutObserved": sale["soldOutObserved"],
        }
        rows.append(row)
    return rows, failures


def general_sale_key(event: dict) -> tuple[str, str, str] | None:
    if "一般" not in normalize(event.get("ticketType")):
        return None
    group = normalize(event.get("group"))
    day = str(event.get("eventDate") or "")[:10]
    if not group or not day:
        return None
    return group, day, "一般発売"


def merge(payload: dict, rows: list[dict]) -> tuple[int, int]:
    events = [dict(x) for x in payload.get("events", []) if isinstance(x, dict)]
    index: dict[tuple[str, str, str], int] = {}
    for i, event in enumerate(events):
        key = general_sale_key(event)
        if key:
            index[key] = i

    added = 0
    enriched = 0
    for row in rows:
        key = general_sale_key(row)
        if key is None:
            continue
        if key not in index:
            events.append(row)
            index[key] = len(events) - 1
            added += 1
            continue

        target = events[index[key]]
        changed = False
        # Cross-source reconciliation: promoter often preserves the sale start after
        # sell-out while Pia may preserve the deadline.  Keep both direct facts.
        if not target.get("applyStart") and row.get("applyStart"):
            target["applyStart"] = row["applyStart"]
            target["applicationWindowVerified"] = True
            target["applicationWindowSource"] = row["applicationWindowSource"]
            changed = True
        if row.get("soldOutObserved") and not target.get("soldOutObserved"):
            target["soldOutObserved"] = True
            if target.get("applicationStatus") in (None, "", "none", "observed"):
                target["applicationStatus"] = "sold_out"
            changed = True
        urls = list(dict.fromkeys([*(target.get("urls") or []), *(row.get("urls") or [])]))
        if urls != (target.get("urls") or []):
            target["urls"] = urls
            changed = True
        if changed:
            target["historyPreserved"] = True
            enriched += 1

    payload["events"] = events
    return added, enriched


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; keio-kawaii-lab-promoter-sale-guard/1.1; +https://github.com/keio-kawaiilab/keio-kawaii-lab)",
        "Accept-Language": "ja,en;q=0.8",
    })
    return session


def run(check: bool = False, today: date | None = None) -> dict:
    today = today or datetime.now(JST).date()
    original = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    payload = json.loads(json.dumps(original, ensure_ascii=False))
    session = make_session()
    try:
        rows, failures = collect(session, today)
    finally:
        session.close()

    added, enriched = merge(payload, rows)
    changed = payload != original
    if changed and not check:
        payload["updatedAt"] = datetime.now(JST).isoformat(timespec="seconds")
        DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "checkedAt": datetime.now(JST).isoformat(timespec="seconds"),
        "birthdayGeneralSalesObserved": len(rows),
        "birthdayGeneralSalesAdded": added,
        "birthdayGeneralSalesEnriched": enriched,
        "changed": changed,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover birthday-event general-sale history from promoter pages after playguides mark it sold out.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(check=args.check), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
