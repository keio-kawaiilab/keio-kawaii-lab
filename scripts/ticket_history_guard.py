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
HISTORY_PATH = Path("data/ticket-history.json")
DIAGNOSTICS_PATH = Path("data/ticket-history-guard.json")
JST = timezone(timedelta(hours=9))

ANNUAL_LABEL = "年会費コース会員先行"
NO_TICKET_LABEL = "現在受付なし"
OFFICIAL_HOSTS = {
    "kawaiilab.asobisystem.com",
    "fruitszipper.asobisystem.com",
    "candytune.asobisystem.com",
    "sweetsteady.asobisystem.com",
    "cutiestreet.asobisystem.com",
    "morestar.asobisystem.com",
}

# 年会費コースという単語がページの別の場所にあるだけでは先行種別の根拠にしない。
# 「年会費コース会員限定先行」等の、販売を直接述べる近接表現だけを認める。
ANNUAL_SALE_PATTERNS = (
    re.compile(r"年会費コース\s*(?:会員)?\s*(?:限定)?\s*(?:チケット)?\s*(?:最速)?\s*先行", re.I),
    re.compile(r"年会費コース\s*(?:会員)?\s*(?:限定)?\s*(?:先行)?\s*(?:受付|申込|販売)(?:開始|期間)?", re.I),
    re.compile(r"(?:先行|受付|申込|販売).{0,18}年会費コース\s*(?:会員)?", re.I | re.S),
)
UPGRADE_RE = re.compile(r"アップグレード|upgrade", re.I)
GENERAL_RE = re.compile(r"一般(?:発売|販売)")
SOLD_OUT_RE = re.compile(r"SOLD\s*OUT|予定枚数終了|完売", re.I)

SALE_START_PATTERNS = (
    re.compile(
        r"(?P<m>\d{1,2})\s*/\s*(?P<d>\d{1,2})(?:\s*[（(][^）)]*[）)])?\s*"
        r"(?P<h>\d{1,2})\s*[:：]\s*(?P<min>\d{2})"
    ),
    re.compile(
        r"(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日?"
        r"(?:\s*[（(][^）)]*[）)])?\s*(?P<h>\d{1,2})\s*[:：]\s*(?P<min>\d{2})"
    ),
)


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def stable_id(*values: object) -> str:
    raw = "\x1f".join(str(value or "") for value in values)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def canonical_url(value: object) -> str:
    text = str(value or "").strip()
    return text.split("#", 1)[0]


def source_urls(event: dict) -> list[str]:
    values: list[str] = []
    for key in ("applicationWindowSource", "deadlineSource", "url"):
        value = canonical_url(event.get(key))
        if value and value not in values:
            values.append(value)
    for value in event.get("urls") or []:
        text = canonical_url(value)
        if text and text not in values:
            values.append(text)
    return values


def official_source_url(event: dict) -> str | None:
    for value in source_urls(event):
        try:
            host = (urlparse(value).hostname or "").lower()
        except ValueError:
            continue
        if host in OFFICIAL_HOSTS:
            return value
    return None


def has_explicit_annual_sale(text: str) -> bool:
    text = normalize(text)
    for pattern in ANNUAL_SALE_PATTERNS:
        for match in pattern.finditer(text):
            phrase = match.group(0)
            if UPGRADE_RE.search(phrase):
                continue
            return True
    return False


def is_upgrade_only_article(text: str) -> bool:
    return bool(UPGRADE_RE.search(text)) and not has_explicit_annual_sale(text)


def quarantine_ticket_fields(event: dict, reason: str) -> None:
    event["ticketType"] = NO_TICKET_LABEL
    event["applicationStatus"] = "none"
    event["applyStart"] = None
    event["applyEnd"] = None
    event["resultDate"] = None
    event["paymentEnd"] = None
    event["applicationDisplayMode"] = "schedule-only"
    event.pop("applicationWindowVerified", None)
    event.pop("deadlineVerified", None)
    event.pop("applicationWindowSource", None)
    event.pop("deadlineSource", None)
    event["ticketGuardRejected"] = True
    event["ticketGuardReason"] = reason


def validate_annual_fee_rows(payload: dict, session: requests.Session) -> tuple[list[str], list[dict]]:
    invalid_sources: list[str] = []
    failures: list[dict] = []
    for event in payload.get("events", []):
        if not isinstance(event, dict) or normalize(event.get("ticketType")) != ANNUAL_LABEL:
            continue
        source = official_source_url(event)
        if not source:
            failures.append({
                "stage": "annual-validation",
                "event": normalize(event.get("title")),
                "error": "no direct official source URL",
            })
            continue
        try:
            response = session.get(source, timeout=20)
            response.raise_for_status()
            text = BeautifulSoup(response.text, "html.parser").get_text("\n", strip=True)
        except Exception as exc:
            failures.append({
                "stage": "annual-validation",
                "event": normalize(event.get("title")),
                "url": source,
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue

        if has_explicit_annual_sale(text):
            event["ticketClassificationVerified"] = True
            event["ticketClassificationSource"] = source
            event.pop("ticketGuardRejected", None)
            event.pop("ticketGuardReason", None)
            continue

        # A successfully fetched direct source that talks about an upgrade but does
        # not explicitly describe an annual-fee ticket sale must never be published
        # as 年会費コース会員先行.
        if is_upgrade_only_article(text):
            invalid_sources.append(canonical_url(source))
            quarantine_ticket_fields(event, "upgrade article is not evidence of an annual-fee ticket sale")
        else:
            invalid_sources.append(canonical_url(source))
            quarantine_ticket_fields(event, "direct source does not explicitly support annual-fee sale classification")
    return invalid_sources, failures


def _sale_year(event_day: str, month: int, day: int) -> int | None:
    try:
        event_date = date.fromisoformat(str(event_day)[:10])
        candidate = date(event_date.year, month, day)
    except ValueError:
        return None
    if candidate > event_date:
        candidate = date(event_date.year - 1, month, day)
    return candidate.year


def _to_iso(event_day: str, match: re.Match) -> str | None:
    month = int(match.group("m"))
    day = int(match.group("d"))
    hour = int(match.group("h"))
    minute = int(match.group("min"))
    year = _sale_year(event_day, month, day)
    if year is None:
        return None
    try:
        value = datetime(year, month, day, hour, minute)
    except ValueError:
        return None
    return value.strftime("%Y-%m-%dT%H:%M")


def extract_promoter_general_sale(text: str, event_day: str) -> dict | None:
    text = normalize(text)
    match = GENERAL_RE.search(text)
    if not match:
        return None
    # Start at the explicit 一般発売/一般販売 label so the performance date earlier
    # on the page cannot be mistaken for the sale date.
    segment = text[match.start():match.start() + 520]
    start = None
    for pattern in SALE_START_PATTERNS:
        found = pattern.search(segment)
        if found:
            start = _to_iso(event_day, found)
            break
    if not start:
        return None
    return {
        "applyStart": start,
        "applyEnd": None,
        "applicationStatus": "sold_out" if SOLD_OUT_RE.search(segment) else "observed",
        "soldOutObserved": bool(SOLD_OUT_RE.search(segment)),
    }


def provider_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    values: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, str(anchor.get("href") or ""))
        try:
            host = (urlparse(href).hostname or "").lower()
        except ValueError:
            continue
        if host not in {"t.pia.jp", "eplus.jp", "l-tike.com"}:
            continue
        if href not in values:
            values.append(href)
    return values


def provider_from_links(values: list[str]) -> str:
    for value in values:
        host = (urlparse(value).hostname or "").lower()
        if host == "t.pia.jp":
            return "pia"
        if host == "eplus.jp":
            return "eplus"
        if host == "l-tike.com":
            return "lawson"
    return "promoter"


def promoter_general_sale_rows(
    session: requests.Session,
    today: date,
) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    failures: list[dict] = []
    try:
        events, diagnostics = promoter.collect(session, today)
        failures.extend(diagnostics.get("failures") or [])
    except Exception as exc:
        return [], [{
            "stage": "promoter-collection",
            "error": f"{type(exc).__name__}: {exc}",
        }]

    for event in events:
        promoter_url = canonical_url(event.get("url"))
        event_day = str(event.get("eventDate") or "")[:10]
        if not promoter_url or not event_day:
            continue
        try:
            response = session.get(promoter_url, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text(" ", strip=True)
        except Exception as exc:
            failures.append({
                "stage": "promoter-general-sale",
                "url": promoter_url,
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue

        sale = extract_promoter_general_sale(text, event_day)
        if not sale:
            continue
        links = provider_links(soup, promoter_url)
        provider = provider_from_links(links)
        title = normalize(event.get("eventTitle") or event.get("title"))
        row = {
            "id": stable_id("ticket-history-guard", event.get("group"), event_day, "一般発売", sale["applyStart"], promoter_url),
            "group": event.get("group"),
            "title": title,
            "eventTitle": title,
            "displayTitle": title,
            "eventCategory": event.get("eventCategory") or "solo-live",
            "ticketType": "一般発売",
            "ticketProvider": provider,
            "applyStart": sale["applyStart"],
            "applyEnd": sale["applyEnd"],
            "resultDate": None,
            "paymentEnd": None,
            "applicationStatus": sale["applicationStatus"],
            "applicationDisplayMode": "offers",
            "applicationWindowVerified": True,
            "applicationWindowSource": promoter_url,
            "eventDate": event_day,
            "venue": event.get("venue"),
            "url": promoter_url,
            "urls": list(dict.fromkeys([promoter_url, *links])),
            "sourceType": "ticket-history-guard",
            "sourceChannel": "hot-stuff-general-sale",
            "primarySource": "promoter",
            "sourceCandidates": list(dict.fromkeys(["promoter", provider])),
            "historyPreserved": True,
            "soldOutObserved": sale["soldOutObserved"],
        }
        rows.append(row)
    return rows, failures


def same_general_sale(a: dict, b: dict) -> bool:
    if normalize(a.get("group")) != normalize(b.get("group")):
        return False
    if str(a.get("eventDate") or "")[:10] != str(b.get("eventDate") or "")[:10]:
        return False
    return "一般" in normalize(a.get("ticketType")) and "一般" in normalize(b.get("ticketType"))


def merge_guard_rows(payload: dict, rows: list[dict]) -> int:
    events = [dict(x) for x in payload.get("events", []) if isinstance(x, dict)]
    added = 0
    for row in rows:
        matches = [event for event in events if same_general_sale(event, row)]
        if matches:
            # Never replace a richer direct observation. Only fill information that
            # is missing and preserve the independent promoter evidence URL.
            target = matches[0]
            if not target.get("applyStart") and row.get("applyStart"):
                target["applyStart"] = row["applyStart"]
                target["applicationWindowVerified"] = True
                target["applicationWindowSource"] = row["applicationWindowSource"]
            target["urls"] = list(dict.fromkeys([*(target.get("urls") or []), *row.get("urls", [])]))
            if row.get("soldOutObserved"):
                target["soldOutObserved"] = True
            continue
        events.append(row)
        added += 1
    payload["events"] = events
    return added


def purge_invalid_history(history: dict, invalid_sources: list[str]) -> int:
    bad = {canonical_url(value) for value in invalid_sources if value}
    if not bad:
        return 0
    before = [x for x in history.get("entries", []) if isinstance(x, dict)]
    kept = []
    removed = 0
    for entry in before:
        source = canonical_url(entry.get("sourceUrl"))
        if normalize(entry.get("ticketType")) == ANNUAL_LABEL and source in bad:
            removed += 1
            continue
        kept.append(entry)
    history["entries"] = kept
    if removed:
        history["updatedAt"] = datetime.now(JST).isoformat(timespec="seconds")
    return removed


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; keio-kawaii-lab-ticket-history-guard/1.0; +https://github.com/keio-kawaiilab/keio-kawaii-lab)",
        "Accept-Language": "ja,en;q=0.8",
    })
    return session


def run(check: bool = False, today: date | None = None) -> dict:
    today = today or datetime.now(JST).date()
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else {"version": 1, "entries": []}

    with make_session() as session:
        invalid_sources, annual_failures = validate_annual_fee_rows(payload, session)
        general_rows, general_failures = promoter_general_sale_rows(session, today)

    added = merge_guard_rows(payload, general_rows)
    removed_history = purge_invalid_history(history, invalid_sources)
    changed_live = payload != json.loads(DATA_PATH.read_text(encoding="utf-8"))

    diagnostics = {
        "checkedAt": datetime.now(JST).isoformat(timespec="seconds"),
        "policy": {
            "annualFeeNeedsExplicitSaleWording": True,
            "upgradeAloneNeverCountsAsAnnualFeeSale": True,
            "preserveEndedGeneralSales": True,
            "promoterUsedAsIndependentGeneralSaleEvidence": True,
        },
        "invalidAnnualFeeSources": invalid_sources,
        "promoterGeneralSalesObserved": len(general_rows),
        "promoterGeneralSalesAdded": added,
        "invalidHistoryEntriesRemoved": removed_history,
        "failures": [*annual_failures, *general_failures],
    }

    if not check:
        if changed_live:
            payload["updatedAt"] = datetime.now(JST).isoformat(timespec="seconds")
            DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if removed_history:
            HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        DIAGNOSTICS_PATH.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description="Prevent ticket-history regressions and preserve sold-out general sales.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    diagnostics = run(check=args.check)
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
