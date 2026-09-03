#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

DATA_PATH = Path("data/live-events.json")
HISTORY_PATH = Path("data/ticket-history.json")
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
UPGRADE_RE = re.compile(r"アップグレード|upgrade", re.I)
UPGRADE_NOTICE_RE = re.compile(r"アップグレード.*(?:抽選|受付|申込|販売)|(?:抽選|受付|申込|販売).*アップグレード", re.I)
ANNUAL_SALE_RE = re.compile(
    r"(?:"
    r"年会費コース\s*(?:会員)?\s*(?:限定)?\s*(?:チケット)?\s*(?:最速)?\s*(?:先行|受付|申込|販売)"
    r"|(?:先行|受付|申込|販売)\s*(?:開始|期間)?\s*(?:[:：・／/\-]\s*)?年会費コース\s*(?:会員)?"
    r")",
    re.I,
)


def normalize(value: object) -> str:
    return re.sub(r"[ \t\u3000]+", " ", str(value or "")).strip()


def clauses(text: str) -> list[str]:
    return [
        normalize(part)
        for part in re.split(r"[\n\r。！？!?]+", str(text or ""))
        if normalize(part)
    ]


def annual_sale_evidence(text: str) -> str | None:
    for clause in clauses(text):
        if UPGRADE_RE.search(clause):
            continue
        match = ANNUAL_SALE_RE.search(clause)
        if match:
            return match.group(0)
    return None


def has_explicit_annual_sale(text: str) -> bool:
    return annual_sale_evidence(text) is not None


def is_upgrade_notice(soup: BeautifulSoup, text: str) -> bool:
    # Article titles/headings define what the page is announcing.  An upgrade
    # notice may legitimately list the old FC sales that are eligible to upgrade;
    # those historical names must never be treated as the sale currently announced.
    heading_texts: list[str] = []
    if soup.title:
        heading_texts.append(normalize(soup.title.get_text(" ", strip=True)))
    for node in soup.find_all(["h1", "h2", "h3"], limit=8):
        value = normalize(node.get_text(" ", strip=True))
        if value:
            heading_texts.append(value)
    if any(UPGRADE_NOTICE_RE.search(value) for value in heading_texts):
        return True

    # Some templates do not expose the article title in a heading.  Limit the
    # fallback to the opening clauses so an upgrade note far below a real sale
    # announcement cannot invalidate the real sale.
    lead = "\n".join(clauses(text)[:8])
    return bool(UPGRADE_NOTICE_RE.search(lead))


def canonical_url(value: object) -> str:
    return str(value or "").strip().split("#", 1)[0]


def source_urls(event: dict) -> list[str]:
    result: list[str] = []
    for key in ("applicationWindowSource", "deadlineSource", "url"):
        value = canonical_url(event.get(key))
        if value and value not in result:
            result.append(value)
    for value in event.get("urls") or []:
        text = canonical_url(value)
        if text and text not in result:
            result.append(text)
    return result


def official_source_url(event: dict) -> str | None:
    for value in source_urls(event):
        try:
            host = (urlparse(value).hostname or "").lower()
        except ValueError:
            continue
        if host in OFFICIAL_HOSTS:
            return value
    return None


def quarantine_ticket_fields(event: dict, source: str, reason: str) -> None:
    event["ticketType"] = NO_TICKET_LABEL
    event["applicationStatus"] = "none"
    event["applyStart"] = None
    event["applyEnd"] = None
    event["resultDate"] = None
    event["paymentEnd"] = None
    event["applicationDisplayMode"] = "schedule-only"
    for key in (
        "applicationWindowVerified",
        "deadlineVerified",
        "applicationWindowSource",
        "deadlineSource",
        "ticketClassificationVerified",
        "ticketClassificationSource",
        "ticketClassificationEvidence",
    ):
        event.pop(key, None)
    event["ticketGuardRejected"] = True
    event["ticketGuardReason"] = reason
    event["ticketGuardSource"] = source


def validate_annual_rows(payload: dict, session: requests.Session) -> tuple[list[str], list[dict]]:
    invalid_sources: list[str] = []
    failures: list[dict] = []
    for event in payload.get("events", []):
        if not isinstance(event, dict) or normalize(event.get("ticketType")) != ANNUAL_LABEL:
            continue
        source = official_source_url(event)
        if not source:
            failures.append({
                "event": normalize(event.get("title")),
                "stage": "annual-classification",
                "error": "direct official source missing",
            })
            continue
        try:
            response = session.get(source, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text("\n", strip=True)
        except Exception as exc:
            # Never delete data merely because a source is temporarily unavailable.
            failures.append({
                "event": normalize(event.get("title")),
                "stage": "annual-classification",
                "url": source,
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue

        if is_upgrade_notice(soup, text):
            invalid_sources.append(canonical_url(source))
            quarantine_ticket_fields(
                event,
                source,
                "upgrade notice cannot be used as the source of an annual-fee ticket sale",
            )
            continue

        evidence = annual_sale_evidence(text)
        if evidence:
            event["ticketClassificationVerified"] = True
            event["ticketClassificationSource"] = source
            event["ticketClassificationEvidence"] = evidence
            event.pop("ticketGuardRejected", None)
            event.pop("ticketGuardReason", None)
            event.pop("ticketGuardSource", None)
            continue

        invalid_sources.append(canonical_url(source))
        quarantine_ticket_fields(
            event,
            source,
            "direct source does not explicitly support annual-fee sale classification",
        )
    return invalid_sources, failures


def purge_invalid_history(history: dict, invalid_sources: list[str]) -> int:
    bad = {canonical_url(value) for value in invalid_sources if value}
    kept = []
    removed = 0
    for entry in history.get("entries", []):
        if not isinstance(entry, dict):
            continue
        if (
            normalize(entry.get("ticketType")) == ANNUAL_LABEL
            and canonical_url(entry.get("sourceUrl")) in bad
        ):
            removed += 1
            continue
        kept.append(entry)
    history["entries"] = kept
    return removed


def run(check: bool = False) -> dict:
    original_payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    payload = json.loads(json.dumps(original_payload, ensure_ascii=False))
    history = (
        json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        if HISTORY_PATH.exists()
        else {"version": 1, "entries": []}
    )
    original_history = json.loads(json.dumps(history, ensure_ascii=False))

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; keio-kawaii-lab-ticket-classification-guard/2.1; +https://github.com/keio-kawaiilab/keio-kawaii-lab)",
        "Accept-Language": "ja,en;q=0.8",
    })
    try:
        invalid_sources, failures = validate_annual_rows(payload, session)
    finally:
        session.close()

    removed_history = purge_invalid_history(history, invalid_sources)
    changed_live = payload != original_payload
    changed_history = history != original_history
    now = datetime.now(JST).isoformat(timespec="seconds")
    if not check:
        if changed_live:
            payload["updatedAt"] = now
            DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if changed_history:
            history["updatedAt"] = now
            HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "checkedAt": now,
        "invalidAnnualFeeSources": invalid_sources,
        "invalidHistoryEntriesRemoved": removed_history,
        "changedLive": changed_live,
        "changedHistory": changed_history,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reject unsupported annual-fee ticket classifications using article-purpose-aware evidence.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(check=args.check), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
