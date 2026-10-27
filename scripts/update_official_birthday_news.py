#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import update_official_x_birthday_events as birthday
import update_official_x_special_events as social_base

DATA_PATH = Path("data/live-events.json")
NEWS_PAGES = 5
CENTRAL_FC = "https://kawaiilab.asobisystem.com"
GROUPS = {
    "FRUITS ZIPPER": "https://fruitszipper.asobisystem.com",
    "CANDY TUNE": "https://candytune.asobisystem.com",
    "SWEET STEADY": "https://sweetsteady.asobisystem.com",
    "CUTIE STREET": "https://cutiestreet.asobisystem.com",
    "MORE STAR": "https://morestar.asobisystem.com",
}
PERSON_RE = re.compile(r"([一-龠々〆ヵヶぁ-んァ-ヶー]{2,12})\s*(?:生誕祭|BIRTHDAY)", re.I)
FULL_EVENT_DATE_RE = re.compile(r"(?<!\\d)(20\\d{2})年\\s*(\\d{1,2})月\\s*(\\d{1,2})日")


def normalize(value: object) -> str:
    return social_base.normalize(value)


def birthday_person(value: object) -> str | None:
    match = PERSON_RE.search(normalize(value))
    return match.group(1) if match else None


def known_birthday_people(payload: dict) -> set[str]:
    result = set()
    for event in payload.get("events", []):
        if not isinstance(event, dict):
            continue
        title = event.get("eventTitle") or event.get("title")
        if not social_base.BIRTHDAY_RE.search(str(title or "")):
            continue
        person = birthday_person(title)
        if person:
            result.add(person)
    return result


def scan_news_candidates(
    session: requests.Session,
    base_url: str,
    group_hint: str | None,
    people: set[str],
    pages: int = NEWS_PAGES,
) -> tuple[list[dict], list[dict]]:
    candidates: dict[str, dict] = {}
    failures = []
    for page in range(1, pages + 1):
        page_url = f"{base_url}/news/1/?page={page}"
        try:
            response = session.get(page_url, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            for anchor in soup.find_all("a", href=True):
                href = str(anchor.get("href") or "")
                if "/news/detail/" not in href:
                    continue
                title = normalize(anchor.get_text(" ", strip=True))
                if not title:
                    continue
                if not social_base.BIRTHDAY_RE.search(title) and not any(person in title for person in people):
                    continue
                full_url = urljoin(base_url, href)
                candidates[full_url] = {
                    "group": group_hint,
                    "title": title,
                    "url": full_url,
                }
        except Exception as exc:
            failures.append({
                "group": group_hint or "KAWAII LAB. FC",
                "stage": "news-list",
                "url": page_url,
                "error": f"{type(exc).__name__}: {exc}",
            })
        time.sleep(0.05)
    return list(candidates.values()), failures



def scoped_ticket_details_from_article(text: str, today: date) -> dict:
    """Extract one FC window near an explicit reception-period label."""
    lines = [normalize(line) for line in text.splitlines() if normalize(line)]
    candidates: dict[tuple[str, str], dict] = {}
    for index, line in enumerate(lines):
        if not re.search(r"(?:受付|申込)(?:期間|日時)", line):
            continue
        snippet = "\n".join(lines[max(0, index - 4): index + 5])
        details = birthday.ticket_details_from_text(snippet, today)
        apply_start = details.get("applyStart")
        apply_end = details.get("applyEnd")
        if details.get("ticketType") and apply_start and apply_end:
            candidates[(str(apply_start), str(apply_end))] = details
    return next(iter(candidates.values())) if len(candidates) == 1 else {}


def ticket_details_from_official_article(text: str, url: str, today: date) -> dict:
    # The conservative parser is tried first. If the article uses a compact
    # social-style range, the birthday parser handles that exact FC window.
    article_date = birthday.ticket_parser.article_date_from_text(text)
    default_year = int(article_date[:4]) if article_date else today.year
    windows = birthday.ticket_parser.extract_windows(text, default_year)
    if len(windows) > 1:
        scoped = scoped_ticket_details_from_article(text, today)
        if not scoped:
            return {}
        scoped["applicationWindowVerified"] = True
        scoped["deadlineVerified"] = True
        scoped["applicationWindowSource"] = url
        scoped["deadlineSource"] = url
        if article_date:
            scoped["sourcePublishedAt"] = article_date
        return scoped
    if len(windows) == 1:
        apply_start, apply_end = windows[0]
        ticket_type = birthday.ticket_parser.extract_ticket_type("", text)
        status = "none"
        try:
            start_day = date.fromisoformat(apply_start[:10])
            end_day = date.fromisoformat(apply_end[:10])
            if end_day >= today:
                status = "upcoming" if start_day > today else "open"
        except ValueError:
            pass
        result = {
            "ticketType": ticket_type,
            "applicationStatus": status,
            "applyStart": apply_start,
            "applyEnd": apply_end,
            "applicationDisplayMode": "band",
            "applicationWindowVerified": True,
            "deadlineVerified": True,
            "applicationWindowSource": url,
            "deadlineSource": url,
        }
        if article_date:
            result["sourcePublishedAt"] = article_date
        return result

    result = birthday.ticket_details_from_text(text, today)
    if result.get("applyEnd"):
        result["deadlineSource"] = url
        result["deadlineVerified"] = True
    if result.get("applyStart") and result.get("applyEnd"):
        result["applicationWindowSource"] = url
        result["applicationWindowVerified"] = True
    if article_date:
        result["sourcePublishedAt"] = article_date
    return result


def matching_existing_birthdays(payload: dict, group: str, corpus: str) -> list[dict]:
    matches = []
    for event in payload.get("events", []):
        if not isinstance(event, dict) or event.get("group") != group:
            continue
        title = str(event.get("eventTitle") or event.get("title") or "")
        if not social_base.BIRTHDAY_RE.search(title):
            continue
        person = birthday_person(title)
        if person and person in corpus:
            matches.append(event)
    return matches


def fallback_events_from_existing(
    payload: dict,
    group: str,
    article_url: str,
    article_text: str,
    details: dict,
) -> list[dict]:
    result = []
    for existing in matching_existing_birthdays(payload, group, article_text):
        if birthday._has_application(existing):
            continue
        event = dict(existing)
        event["url"] = article_url
        event["urls"] = birthday._unique_urls(article_url, existing.get("url"), existing.get("urls"))
        event["discoverySourceUrl"] = article_url
        event["sourceType"] = "auto"
        event["sourceChannel"] = "official-birthday-news"
        event["primarySource"] = "official"
        event["sourceCandidates"] = list(dict.fromkeys(["official", *(existing.get("sourceCandidates") or [])]))
        for key, value in details.items():
            if value is not None:
                event[key] = value
        if event.get("ticketType") and event.get("ticketType") != "現在受付なし":
            event["specialDetailsStatus"] = "ticket-details-found"
        result.append(event)
    return result



def official_event_times(article_text: str) -> dict:
    result = {}
    for key, labels in (
        ("openTime", r"(?:開場|OPEN)"),
        ("startTime", r"(?:開演|START)"),
    ):
        match = re.search(
            rf"{labels}\s*[:：]?\s*(\d{{1,2}}):(\d{{2}})",
            article_text,
            re.I,
        )
        if not match:
            continue
        hour, minute = (int(value) for value in match.groups())
        if 0 <= hour < 24 and 0 <= minute < 60:
            result[key] = f"{hour:02d}:{minute:02d}"
    return result


def canonical_birthday_event_text(listing_title: str, article_text: str) -> str:
    """Prefer the dated birthday headline when the body repeats that day with a stale year."""
    listing_title = normalize(listing_title)
    if not social_base.BIRTHDAY_RE.search(listing_title):
        return article_text

    title_dates = {
        (int(year), int(month), int(day))
        for year, month, day in FULL_EVENT_DATE_RE.findall(listing_title)
    }
    if len(title_dates) != 1:
        return "\n".join(value for value in (listing_title, article_text) if value)

    title_year, title_month, title_day = next(iter(title_dates))
    kept_lines = []
    for line in article_text.splitlines():
        conflicting_repeat = any(
            int(year) != title_year
            and int(month) == title_month
            and int(day) == title_day
            for year, month, day in FULL_EVENT_DATE_RE.findall(line)
        )
        if not conflicting_repeat:
            kept_lines.append(line)

    return "\n".join(value for value in (listing_title, *kept_lines) if value)


def article_events(
    payload: dict,
    group: str,
    article_url: str,
    article_text: str,
    today: date,
) -> list[dict]:
    # Upgrade notices are already handled by the continuous official collector,
    # which binds the reception to the exact performance time.  This secondary
    # birthday enrichment starts from schedule placeholders; applying an
    # upgrade there can turn OPEN into a second apparent START and can also
    # misread annual-course eligibility text as an FC presale.  Leave these
    # notices to the authoritative collector instead of publishing a shadow row.
    first_line = next(
        (normalize(line) for line in article_text.splitlines() if normalize(line)),
        "",
    )
    if "アップグレード" in first_line:
        return []
    details = ticket_details_from_official_article(article_text, article_url, today)
    if not details or not details.get("ticketType") or details.get("ticketType") == "現在受付なし":
        return []

    # If an official article names a birthday member already present in the
    # schedule, that existing event identity is authoritative for the physical
    # date. Do not re-infer the event date from a page that also contains FC
    # application dates; doing so can bind the ticket window to the wrong day.
    times = official_event_times(article_text)
    matched = fallback_events_from_existing(payload, group, article_url, article_text, details)
    if matched:
        for event in matched:
            event.update(times)
        return matched

    # Only discover a brand-new birthday event from article text when there is
    # no known schedule/promoter row to enrich.
    parsed = birthday.event_from_post(
        group,
        article_url,
        article_text,
        today,
        [article_url],
        details,
    )
    for event in parsed:
        event.update(times)
        event["sourceType"] = "auto"
        event["sourceChannel"] = "official-birthday-news"
        event["primarySource"] = "official"
        event["discoverySourceUrl"] = article_url
    return parsed


def infer_groups(payload: dict, group_hint: str | None, corpus: str) -> list[str]:
    if group_hint:
        return [group_hint]
    explicit = [group for group in GROUPS if group in corpus]
    if explicit:
        return explicit
    matches = []
    for group in GROUPS:
        if matching_existing_birthdays(payload, group, corpus):
            matches.append(group)
    return matches


def collect(
    session: requests.Session,
    payload: dict,
    today: date | None = None,
    pages: int = NEWS_PAGES,
) -> tuple[list[dict], list[dict], dict]:
    today = today or datetime.now(social_base.JST).date()
    people = known_birthday_people(payload)
    sources = [(group, base_url) for group, base_url in GROUPS.items()]
    sources.append((None, CENTRAL_FC))

    candidates: dict[str, dict] = {}
    failures = []
    for group_hint, base_url in sources:
        found, source_failures = scan_news_candidates(session, base_url, group_hint, people, pages)
        for candidate in found:
            candidates[candidate["url"]] = candidate
        failures.extend(source_failures)

    events = []
    articles_with_ticket_details = 0
    for candidate in candidates.values():
        try:
            response = session.get(candidate["url"], timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text("\n", strip=True)
            event_text = canonical_birthday_event_text(candidate.get("title") or "", text)
            if not social_base.BIRTHDAY_RE.search(event_text):
                continue
            groups = infer_groups(payload, candidate.get("group"), event_text)
            produced = []
            for group in groups:
                produced.extend(article_events(payload, group, candidate["url"], event_text, today))
            if produced:
                articles_with_ticket_details += 1
                events.extend(produced)
        except Exception as exc:
            failures.append({
                "group": candidate.get("group") or "KAWAII LAB. FC",
                "stage": "news-detail",
                "url": candidate["url"],
                "error": f"{type(exc).__name__}: {exc}",
            })
        time.sleep(0.05)

    deduped: dict[tuple[str, str, str], dict] = {}
    for event in events:
        key = (
            str(event.get("group") or ""),
            str(event.get("eventDate") or "")[:10],
            str(event.get("ticketType") or ""),
        )
        current = deduped.get(key)
        if current is None or len(str(event.get("url") or "")) > len(str(current.get("url") or "")):
            deduped[key] = event

    rows = list(deduped.values())
    diagnostics = {
        "candidateArticles": len(candidates),
        "articlesWithTicketDetails": articles_with_ticket_details,
        "ticketEvents": len(rows),
        "pagesPerSource": pages,
        "ticketRows": [
            {
                "id": event.get("id"),
                "group": event.get("group"),
                "title": event.get("eventTitle") or event.get("title"),
                "eventDate": event.get("eventDate"),
                "ticketType": event.get("ticketType"),
                "applyStart": event.get("applyStart"),
                "applyEnd": event.get("applyEnd"),
                "url": event.get("url"),
            }
            for event in rows
        ],
    }
    return rows, failures, diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect birthday ticket windows from official KAWAII LAB. news pages")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update({
        "User-Agent": "KeioKawaiiLabCalendarBot/2.3 (+https://keio-kawaiilab.github.io/keio-kawaii-lab/)",
        "Accept-Language": "ja,en;q=0.8",
    })
    try:
        events, failures, diagnostics = collect(session, payload)
    finally:
        session.close()

    merged = birthday.merge_birthday_events(payload, events)
    report = {
        "collector": "official-birthday-news",
        **diagnostics,
        "withTicketDetails": sum(1 for event in events if birthday._has_application(event)),
        "failures": failures,
        "changed": merged != payload,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.check:
        return 0

    DATA_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Fail soft. Existing good rows must survive a temporary official-site outage.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
