"""Read current announcements AND revisit future performances and unresolved articles.

Each URL has an outcome. A failed page never discards successful observations.
No event dates or ticket deadlines are inferred from a sale's start time.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from types import SimpleNamespace
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

import update_live_events as parser
import update_live_events_v2 as retention

WORKERS = 24
SALE_RE = re.compile(r"一般(?:発売|販売)|当日券|リセール")
RETRACTED_SOURCES_PATH = "data/retracted-ticket-sources.json"


def retracted_source_urls():
    try:
        import json
        from pathlib import Path
        payload = json.loads(Path(RETRACTED_SOURCES_PATH).read_text(encoding="utf-8"))
    except Exception:
        return set()
    return {
        str(item.get("url") or "").strip()
        for item in payload.get("entries", [])
        if isinstance(item, dict) and item.get("url")
    }


class CachedArticle:
    def __init__(self, html):
        self.html = html

    def get(self, *_args, **_kwargs):
        return SimpleNamespace(text=self.html, raise_for_status=lambda: None)


def revisit_candidates(existing, today):
    """Revisit only sources that can still change a live result.

    Fresh official index scans already rediscover recent unresolved articles on
    every pass. Re-injecting every historical pending/failure/observation here
    made the candidate set grow forever and spent most cycles re-reading stale
    pages. Keep old sources only when they belong to a still-future event, or
    when the publication audit explicitly says a parsed offer failed to reach
    the public output.
    """
    hosts = {urlparse(base).netloc: group for group, base in parser.GROUPS.items()}
    hosts[urlparse(retention.CENTRAL_FC_BASE).netloc] = "KAWAII LAB. FC"
    found = {}

    rows = [row for row in existing.get("events", []) if retention.should_show(row, today)]
    rows += [
        row for row in existing.get("officialDiscoveryState", {}).get("observations", [])
        if isinstance(row, dict) and row.get("status") == "publication-missing"
    ]

    for row in rows:
        for url in sorted(retention.event_urls(row) | {str(row.get("officialScheduleUrl") or "")}):
            host = urlparse(url).netloc
            if host not in hosts or not any(path in url for path in ("/news/detail/", "/live_information/detail/")):
                continue
            group = hosts[host]
            found[url] = parser.Candidate(group, str(row.get("eventTitle") or row.get("title") or ""), url)
    return found


def general_sale_rows(candidate, text, existing):
    """Handle explicitly dated general sales without requiring an invented deadline.

    Restrict the start-date scan to the sale's own line/block. The ordinary
    parser handles dated performances; an exact article URL can supply an
    existing performance when an update omits its original date.
    """
    published = parser.article_date_from_text(text)
    year = int(published[:4]) if published else datetime.now(parser.JST).year
    occurrences = parser.extract_event_occurrences(text.splitlines(), candidate.title, published)
    if not occurrences:
        occurrences = [(str(e.get("eventDate"))[:10], e.get("venue"), e.get("openTime"), e.get("startTime"))
                       for e in existing.get("events", [])
                       if e.get("group") == candidate.group and e.get("eventDate")
                       and candidate.url in retention.event_urls(e)]
    rows = []
    for marker in SALE_RE.finditer(text):
        if marker.group() in {"リセール", "当日券"} and len({item[0] for item in occurrences}) > 1:
            # Tour resale articles list a different reception for each date.
            # Never form the Cartesian product of all dates and all windows.
            continue
        line_prefix = text[text.rfind("\n", 0, marker.start()) + 1:marker.start()].strip()
        if len(line_prefix) > 12 or re.search(r"[。をはがのと]", line_prefix):
            continue
        # Do not cross another ticket heading or a performance/date/venue label.
        block = text[marker.end():marker.end() + 180]
        block = re.split(r"一般(?:発売|販売)|FC.*?先行|会場[：:]|(?:公演日|開催日|日程|日時)[：:]", block)[0]
        match = parser.DATE_ANY_RE.search(block)
        if not match:
            continue
        start = parser.date_match_to_iso(match, year)
        if not start or "T" not in start:
            continue
        end = None
        remainder = block[match.end():]
        if re.match(r"\s*[〜～~－–—-]", remainder):
            end_match = parser.DATE_ANY_RE.search(remainder)
            if end_match:
                end = parser.date_match_to_iso(end_match, int(start[:4]))
                if end and end < start:
                    end = None
        kind = "一般発売" if marker.group().startswith("一般") else marker.group()
        for day, venue, open_time, start_time in set(occurrences):
            if start[:10] > day:
                continue
            rows.append({
                "id": parser.event_id(candidate.group, candidate.url, day, start, kind) +
                      hashlib.sha1(str(start_time or "").encode()).hexdigest()[:6],
                "group": candidate.group, "title": candidate.title, "ticketType": kind,
                "eventDate": day, "venue": venue, "openTime": open_time, "startTime": start_time,
                "applyStart": start, "applyEnd": end,
                "url": candidate.url, "sourceType": "auto", "sourceChannel": "official-continuous",
                "applicationStatus": "sold_out" if re.search(r"SOLD\s*OUT|完売|予定枚数終了", block, re.I) else "observed",
                "applicationWindowVerified": True, "applicationWindowSource": candidate.url,
                "sourcePublishedAt": published,
            })
    return rows


def paired_resale_rows(candidate, text):
    """Parse tour resale tables as one reception window per performance.

    Official tour articles repeat: performance date/venue, then that show's
    resale period.  Treating all dates in the article as one generic window can
    fabricate a year-long range, so preserve the local one-to-one pairing.
    """
    lines = [parser.normalize_space(line) for line in text.splitlines() if parser.normalize_space(line)]
    published = parser.article_date_from_text(text)
    default_year = int(published[:4]) if published else datetime.now(parser.JST).year
    rows = []
    seen = set()
    for i, line in enumerate(lines):
        if "リセール" not in line or "受付" not in line:
            continue
        segment = " ".join(lines[i:i + 2])
        sale_matches = list(parser.DATE_ANY_RE.finditer(segment))
        if len(sale_matches) < 2:
            continue

        event_line = None
        event_match = None
        for j in range(i - 1, max(-1, i - 4), -1):
            candidate_line = lines[j]
            if "リセール" in candidate_line or "受付" in candidate_line:
                continue
            match = parser.DATE_ANY_RE.search(candidate_line)
            if match:
                event_line, event_match = candidate_line, match
                break
        if event_line is None or event_match is None:
            continue

        event_iso = parser.date_match_to_iso(event_match, default_year)
        if not event_iso:
            continue
        event_date = event_iso[:10]
        event_year = int(event_date[:4])
        start = parser.date_match_to_iso(sale_matches[0], event_year)
        if not start:
            continue
        # A January performance may have a December resale window in the
        # previous year when the year is omitted in the article.
        if sale_matches[0].group(1) is None and start[:10] > event_date:
            start_dt = parser._iso_datetime(start)
            start = start_dt.replace(year=start_dt.year - 1).strftime("%Y-%m-%dT%H:%M" if "T" in start else "%Y-%m-%d")
        end = parser.date_match_to_iso(sale_matches[1], int(start[:4]))
        if not end:
            continue
        if sale_matches[1].group(1) is None and parser._iso_datetime(end) < parser._iso_datetime(start):
            end_dt = parser._iso_datetime(end)
            end = end_dt.replace(year=end_dt.year + 1).strftime("%Y-%m-%dT%H:%M" if "T" in end else "%Y-%m-%d")
        if parser._iso_datetime(end) < parser._iso_datetime(start) or start[:10] > event_date:
            continue

        venue = parser.normalize_space(event_line[event_match.end():]).strip(" 　-–—:：()（）[]【】") or None
        identity = (event_date, start, end)
        if identity in seen:
            continue
        seen.add(identity)
        row = {
            "id": parser.event_id(candidate.group, candidate.url, event_date, start, "リセール"),
            "group": candidate.group,
            "title": candidate.title,
            "eventTitle": _stable_performance_title(candidate.title, candidate.group),
            "ticketType": "リセール",
            "eventDate": event_date,
            "venue": venue,
            "openTime": None,
            "startTime": None,
            "applyStart": start,
            "applyEnd": end,
            "resultDate": None,
            "paymentEnd": None,
            "url": candidate.url,
            "sourceType": "auto",
            "sourceChannel": "kawaii-lab-fc" if urlparse(candidate.url).netloc == urlparse(retention.CENTRAL_FC_BASE).netloc else "official-continuous",
            "applicationWindowVerified": True,
            "deadlineVerified": True,
            "applicationWindowSource": candidate.url,
            "deadlineSource": candidate.url,
            "sourcePublishedAt": published,
        }
        rows.append(row)
    return rows


def _stable_performance_title(title, group):
    """Remove ticket-announcement boilerplate while preserving the show name."""
    text = retention.performance_title(title, group)
    text = re.split(
        r"(?:公演\\s*)?(?:リセールサービスのお知らせ|リセール|一般(?:発売|販売)|"
        r"当日券|アップグレード(?:抽選)?|年会費コース会員限定先行|FC(?:会員)?先行)",
        text,
        maxsplit=1,
        flags=re.I,
    )[0]
    return parser.normalize_space(text).strip(" 　!！｜|・-–—:：[]【】『』「」")


def _future_url_matches(url, existing):
    today = datetime.now(parser.JST).date()
    return [
        event for event in existing.get("events", [])
        if isinstance(event, dict)
        and retention.should_show(event, today)
        and url in retention.event_urls(event)
    ]


def infer_central_group(title, text, url, existing):
    """Resolve a central-FC article from the strongest evidence first."""
    matches = _future_url_matches(url, existing)
    if matches:
        # Joint KAWAII LAB. performances are intentionally represented by the
        # canonical joint row even if a subgroup mirror row shares the URL.
        joint = [row for row in matches if row.get("group") == "KAWAII LAB.合同"]
        if joint:
            return "KAWAII LAB.合同"
        groups = {str(row.get("group") or "") for row in matches if row.get("group")}
        if len(groups) == 1:
            return next(iter(groups))

    combined = f"{title}\n{text}"
    explicit = [group for group in parser.GROUPS if group.lower() in combined.lower()]
    if len(explicit) == 1:
        return explicit[0]

    # A joint announcement may list all five artists, making an ordinary
    # artist-name inference ambiguous. Match its announced series against
    # the ALREADY published joint SCHEDULE, not against one random subgroup.
    def series_words(value):
        raw = re.sub(r"^.*?KAWAII\s*LAB\.?\s*", "", str(value or ""), flags=re.I)
        raw = re.sub(r"^\s*[『「〖【(\[]?\s*", "", raw)
        return tuple(re.findall(r"[A-Za-z0-9]+", raw.casefold())[:3])

    headline_words = series_words(title)
    if "KAWAII" in title.upper() and "LAB" in title.upper() and len(headline_words) >= 2:
        joint_shows = [
            row for row in existing.get("events", [])
            if isinstance(row, dict) and row.get("group") == "KAWAII LAB.合同"
            and retention.should_show(row, datetime.now(parser.JST).date())
            and series_words(row.get("eventTitle") or row.get("title"))[:len(headline_words)] == headline_words
        ]
        if joint_shows:
            return "KAWAII LAB.合同"
    return retention.infer_group(title, existing) or retention.infer_group(text, existing)


def unlabeled_ticket_window(text, default_year):
    """Extract a nearby date range after a ticket-reception heading.

    Official FC articles often render the actual period on the line after
    '<...先行受付>' without the words 受付期間/申込期間, which the legacy parser
    intentionally required.  Keep this fallback local and require an explicit
    range so ordinary performance dates are not mistaken for applications.
    """
    lines = [parser.normalize_space(line) for line in text.splitlines() if parser.normalize_space(line)]
    heading_re = re.compile(r"(?:先行受付|会員先行|一般発売|リセール受付|抽選受付)")
    range_re = re.compile(r"[〜～~－–—-]")
    for i, line in enumerate(lines):
        if not heading_re.search(line):
            continue
        segment = " ".join(lines[i:i + 4])
        matches = list(parser.DATE_ANY_RE.finditer(segment))
        if len(matches) < 2:
            continue
        between = segment[matches[0].end():matches[1].start()]
        if not range_re.search(between):
            continue
        start = parser.date_match_to_iso(matches[0], default_year)
        if not start:
            continue
        end = parser.date_match_to_iso(matches[1], int(start[:4]))
        if not end:
            continue
        if matches[1].group(1) is None and parser._iso_datetime(end) < parser._iso_datetime(start):
            end_dt = parser._iso_datetime(end)
            end = end_dt.replace(year=end_dt.year + 1).strftime("%Y-%m-%dT%H:%M" if "T" in end else "%Y-%m-%d")
        if parser._iso_datetime(end) < parser._iso_datetime(start):
            continue
        return start, end
    return None


def standalone_ticket_window(text, default_year):
    """Extract an explicit two-ended ticket range even when the page omits a label.

    Some resale/upgrade articles print only the range itself on a dedicated line
    after explanatory copy. The article has already passed ticket-intent checks
    before this helper is used, so require both endpoints and a range separator
    on the same normalized line to avoid treating performance dates as sales.
    """
    range_re = re.compile(r"[〜～~－–—-]")
    for line in [parser.normalize_space(value) for value in text.splitlines() if parser.normalize_space(value)]:
        matches = list(parser.DATE_ANY_RE.finditer(line))
        if len(matches) < 2:
            continue
        between = line[matches[0].end():matches[1].start()]
        if not range_re.search(between):
            continue
        start = parser.date_match_to_iso(matches[0], default_year)
        if not start:
            continue
        end = parser.date_match_to_iso(matches[1], int(start[:4]))
        if not end:
            continue
        if matches[1].group(1) is None and parser._iso_datetime(end) < parser._iso_datetime(start):
            end_dt = parser._iso_datetime(end)
            end = end_dt.replace(year=end_dt.year + 1).strftime("%Y-%m-%dT%H:%M" if "T" in end else "%Y-%m-%d")
        if parser._iso_datetime(end) >= parser._iso_datetime(start):
            return start, end
    return None


def end_only_ticket_window_is_expired(text, today):
    """Recognize a proven, already-ended reception when its start is omitted.

    Official pages sometimes publish an end-only reception such as
    "受付期間：～2026/3/2 23:59まで". We must not invent a start time, but once
    the explicit end is in the past the article no longer belongs in current
    pending review.
    """
    published = parser.article_date_from_text(text)
    default_year = int(published[:4]) if published else today.year
    heading_re = re.compile(r"(?:受付期間|申込期間|お申込期間|お申し込み期間|販売期間|先行受付)")
    range_re = re.compile(r"[〜～~－–—-]")
    lines = [parser.normalize_space(value) for value in text.splitlines() if parser.normalize_space(value)]
    for i, line in enumerate(lines):
        if not heading_re.search(line):
            continue
        segment = " ".join(lines[i:i + 2])
        matches = list(parser.DATE_ANY_RE.finditer(segment))
        if len(matches) != 1:
            continue
        match = matches[0]
        prefix = segment[:match.start()]
        suffix = segment[match.end():]
        if not (range_re.search(prefix) or "まで" in suffix):
            continue
        end = parser.date_match_to_iso(match, default_year)
        end_day = retention.parse_day(end)
        if end_day is not None and end_day < today:
            return True
    return False


def ticket_windows_are_all_expired(text, today):
    """Return true only when every explicit ticket reception has ended."""
    published = parser.article_date_from_text(text)
    default_year = int(published[:4]) if published else today.year
    windows = parser.extract_windows(text, default_year)
    if not windows:
        standalone = standalone_ticket_window(text, default_year)
        windows = [standalone] if standalone else []
    if not windows:
        return end_only_ticket_window_is_expired(text, today)
    ends = [retention.parse_day(end) for _start, end in windows]
    ends = [day for day in ends if day is not None]
    return bool(ends) and len(ends) == len(windows) and all(day < today for day in ends)


def title_is_past_event(title, text, today):
    """Only an actual past SHOW date can retire a ticket announcement.

    Official news list headings often start with their *publication* date,
    e.g. '2026.10.12 [Tour] 開催決定'. That is not the performance date.
    """
    published = parser.article_date_from_text(text)
    default_year = int(published[:4]) if published else today.year
    title = str(title or "")
    prefix = re.match(r"^\s*(20\d{2})[./-](\d{1,2})[./-](\d{1,2})\s+", title)
    if prefix and published:
        prefix_day = f"{int(prefix.group(1)):04d}-{int(prefix.group(2)):02d}-{int(prefix.group(3)):02d}"
        if prefix_day == published[:10]:
            title = title[prefix.end():]
    dates = []
    for match in parser.DATE_ANY_RE.finditer(title):
        value = parser.date_match_to_iso(match, default_year)
        if value:
            dates.append(retention.parse_day(value))
    dates = [day for day in dates if day is not None]
    return bool(dates) and max(dates) < today


def review_is_expired(review, today):
    """Do not keep already-ended receptions in the current unresolved queue."""
    ends = []
    if review.get("applyEnd"):
        ends.append(str(review["applyEnd"])[:10])
    for window in review.get("windows") or []:
        if isinstance(window, dict) and window.get("applyEnd"):
            ends.append(str(window["applyEnd"])[:10])
    parsed = [retention.parse_day(value) for value in ends]
    parsed = [day for day in parsed if day is not None]
    return bool(parsed) and all(day < today for day in parsed)


def review_is_already_represented(candidate, review, existing):
    """Recognize an exact reception already attached to this official URL.

    A schedule detail can be discovered after a richer NEWS/HMV collector has
    already merged the same performance and reception.  In that case the URL
    may match both the lightweight schedule row and the enriched special-event
    row, so fallback_row_from_review() correctly refuses to guess between two
    raw rows.  The public reception is nevertheless unambiguous when one of
    those matching rows already carries the exact verified application window.
    """
    if not review or not review.get("applyStart") or not review.get("applyEnd"):
        return False
    wanted = (str(review["applyStart"]), str(review["applyEnd"]))
    for event in _future_url_matches(candidate.url, existing):
        if event.get("group") != candidate.group:
            continue
        offers = event.get("offers") or []
        if not offers and event.get("applyStart"):
            offers = [event]
        for offer in offers:
            if not isinstance(offer, dict):
                continue
            if (str(offer.get("applyStart") or ""), str(offer.get("applyEnd") or "")) == wanted:
                return True
    return False


def source_notice_is_already_represented(candidate, title, existing):
    """Clear a date-less review when its exact official notice is published.

    Some notices cover several already-known performances and the generic
    parser cannot choose one date, even though a verified correction has
    attached that exact source URL and reception to every occurrence.  Treat
    the article as represented only when a current/future row for the same
    group keeps the exact URL, the notice's ticket family, and a complete
    application window.  A merely related performance or a different sale
    therefore remains pending.
    """
    family = None
    if "アップグレード" in title:
        family = "アップグレード"
    elif "リセール" in title:
        family = "リセール"
    elif re.search(r"一般(?:発売|販売)", title):
        family = "一般"
    if not family:
        return False

    today = datetime.now(parser.JST).date()
    for event in _future_url_matches(candidate.url, existing):
        if event.get("group") != candidate.group or not retention.should_show(event, today):
            continue
        rows = event.get("offers") or [event]
        for row in rows:
            if not isinstance(row, dict):
                continue
            ticket_type = str(row.get("ticketType") or "")
            if family not in ticket_type:
                continue
            if row.get("applyStart") and row.get("applyEnd"):
                return True
    return False


def explicit_event_days(title, text):
    published = parser.article_date_from_text(text)
    default_year = int(published[:4]) if published else datetime.now(parser.JST).year
    days = []
    for match in parser.DATE_ANY_RE.finditer(title):
        value = parser.date_match_to_iso(match, default_year)
        if value:
            day = value[:10]
            if day not in days:
                days.append(day)
    return days


def fallback_row_from_review(candidate, title, text, review, existing):
    """Attach a ticket window to one uniquely matching known future performance.

    Some official ticket articles intentionally omit the performance date because
    the show was announced earlier.  The old collector discovered those pages but
    left them in pendingReview forever.  When the article supplies one verified
    application window and its show title maps to exactly one current/future
    performance, reuse that already-published performance date instead of asking
    for manual intervention.  Ambiguous matches still stay pending.
    """
    if not review or not review.get("applyStart") or not review.get("applyEnd"):
        return None

    group = candidate.group
    stable_title = _stable_performance_title(title, group)
    wanted = retention.title_key(stable_title, group)
    wanted = re.sub(r"(?:公演|開催)+$", "", wanted)
    if not wanted:
        return None

    today = datetime.now(parser.JST).date()
    performances = {}
    direct_matches = [
        event for event in _future_url_matches(candidate.url, existing)
        if event.get("group") == group
    ]
    dated_matches = []
    if not direct_matches:
        title_days = set(explicit_event_days(title, text))
        if title_days:
            dated_matches = [
                event for event in existing.get("events", [])
                if isinstance(event, dict)
                and event.get("group") == group
                and retention.should_show(event, today)
                and str(event.get("eventDate") or "")[:10] in title_days
            ]
    source = direct_matches or dated_matches or existing.get("events", [])
    for event in source:
        if not isinstance(event, dict) or event.get("group") != group or not retention.should_show(event, today):
            continue
        if not direct_matches and not dated_matches:
            current_title = event.get("eventTitle") or event.get("displayTitle") or event.get("title")
            current = retention.title_key(_stable_performance_title(str(current_title or ""), group), group)
            current = re.sub(r"(?:公演|開催)+$", "", current)
            if not current or current != wanted:
                continue
        event_date = str(event.get("eventDate") or "")[:10]
        if not event_date:
            continue
        identity = (event_date, str(event.get("startTime") or ""), str(event.get("venue") or ""))
        performances.setdefault(identity, event)

    if len(performances) != 1:
        return None

    base = next(iter(performances.values()))
    ticket_type = parser.extract_ticket_type(title, text)
    source_channel = "official-continuous"
    if "アップグレード" in title:
        ticket_type = "アップグレード抽選"
    elif "リセール" in title:
        ticket_type = "リセール"
    elif re.search(r"一般(?:発売|販売)", title):
        ticket_type = "一般発売"
    elif urlparse(candidate.url).netloc == urlparse(retention.CENTRAL_FC_BASE).netloc and retention.FC_HINT_RE.search(title):
        ticket_type = "KAWAII LAB. FC先行"
        source_channel = "kawaii-lab-fc"

    event_date = str(base.get("eventDate"))[:10]
    start = str(review["applyStart"])
    row = {
        "id": parser.event_id(group, candidate.url, event_date, start, ticket_type),
        "group": group,
        "title": title,
        "eventTitle": stable_title,
        "ticketType": ticket_type,
        "applyStart": start,
        "applyEnd": review.get("applyEnd"),
        "resultDate": None,
        "paymentEnd": None,
        "eventDate": event_date,
        "venue": base.get("venue"),
        "openTime": base.get("openTime"),
        "startTime": base.get("startTime"),
        "url": candidate.url,
        "sourceType": "auto",
        "sourceChannel": source_channel,
        "applicationWindowVerified": True,
        "applicationWindowSource": candidate.url,
        "sourcePublishedAt": parser.article_date_from_text(text),
        "participants": base.get("participants") or [],
        "eventScope": base.get("eventScope"),
    }
    if row.get("startTime"):
        row["id"] += hashlib.sha1(str(row["startTime"]).encode()).hexdigest()[:6]
    return row


def official_show_announcement_rows(candidate, title, text):
    """Import a newly announced live show even before any tickets are announced."""
    if not re.search(r"(?:開催決定|開催のお知らせ|公演決定|出演決定)", title):
        return []
    if not re.search(r"(?:ライブ|LIVE|公演|TOUR|ツアー|フェス|FES|生誕祭|コンサート|フリーライブ)", title, re.I):
        return []
    published = parser.article_date_from_text(text)
    if not published:
        return []
    occurrences = parser.extract_event_occurrences(
        [line for line in text.splitlines() if parser.normalize_space(line)], title, published,
    )
    today = datetime.now(parser.JST).date().isoformat()
    title_stable = _stable_performance_title(title, candidate.group)
    result = []
    for day, venue, opened, start in occurrences:
        if day < today:
            continue
        # The body must explicitly identify the venue or confirm the schedule
        # in an official list; do not publish a fabricated venue.
        if not venue:
            continue
        result.append({
            "id": parser.event_id(candidate.group, candidate.url, day, "", "現在受付なし"),
            "group": candidate.group, "title": title,
            "eventTitle": title_stable,
            "ticketType": "現在受付なし", "applicationStatus": "none",
            "eventDate": day, "venue": venue,
            "openTime": opened, "startTime": start,
            "url": candidate.url, "sourceType": "auto",
            "primarySource": "official", "sourceChannel": "official-information",
            "sourcePublishedAt": published,
            "participants": parser.extract_target_participants(text, day),
        })
    return result


def verified_unlabeled_window_rows(candidate, title, text, existing):
    """Preserve each physical show when official NEWS lists an unlabeled range.

    A two-part live often prints the venue once after both sessions and the
    ticket window under a separate FC heading. Attach that ONE verified range
    to both distinct starts, retaining the original NEWS URL for provenance.
    """
    published = parser.article_date_from_text(text)
    if not published:
        return []
    year = int(published[:4])
    window = unlabeled_ticket_window(text, year) or standalone_ticket_window(text, year)
    if not window:
        return []
    occurrences = parser.extract_event_occurrences(
        [line for line in text.splitlines() if parser.normalize_space(line)], title, published,
    )
    if not occurrences:
        return []
    venues = {
        parser.normalize_space(match.group(1))
        for line in text.splitlines()
        for match in [parser.VENUE_RE.search(line)]
        if match
    }
    unique_venue = next(iter(venues)) if len(venues) == 1 else None
    group = candidate.group
    if group == "KAWAII LAB. FC":
        group = infer_central_group(title, text, candidate.url, existing)
        if not group:
            return []
    ticket_type = parser.extract_ticket_type(title, text)
    if ticket_type == "FC先行" and group != "KAWAII LAB.合同":
        ticket_type = f"{group} FC先行"
    if candidate.group == "KAWAII LAB. FC" and "FC" in ticket_type:
        ticket_type = "KAWAII LAB. FC先行"
    today = datetime.now(parser.JST).date().isoformat()
    rows = []
    for day, venue, opened, performance_start in occurrences:
        if day < today:
            continue
        venue = venue or unique_venue
        if not venue:
            return []
        rows.append({
            "id": parser.event_id(group, candidate.url, day, window[0], ticket_type)
                  + hashlib.sha1(str(performance_start or opened or day).encode()).hexdigest()[:6],
            "group": group, "title": title,
            "eventTitle": _stable_performance_title(title, group),
            "ticketType": ticket_type, "applyStart": window[0], "applyEnd": window[1],
            "eventDate": day, "venue": venue,
            "openTime": opened, "startTime": performance_start,
            "url": candidate.url, "urls": [candidate.url],
            "sourceType": "auto", "primarySource": "official",
            "sourceChannel": "kawaii-lab-fc" if candidate.group == "KAWAII LAB. FC" else "official-continuous",
            "applicationWindowVerified": True, "deadlineVerified": True,
            "applicationWindowSource": candidate.url,
            "deadlineSource": candidate.url,
            "sourcePublishedAt": published,
            "participants": parser.extract_target_participants(text, day),
        })
    return rows


def confirmed_start_only_rows(candidate, title, text, existing):
    """Publish a verifiable ticket opening even when NEWS gives no closing time.

    Never invent a deadline. Restrict the fallback to an explicit same-sentence
    reception start announcement and a future performance spelled out on that
    page; the general full-window parser remains the first choice.
    """
    published = parser.article_date_from_text(text)
    if not published:
        return []
    year = int(published[:4])
    starts = []
    for line in text.splitlines():
        line = parser.normalize_space(line)
        if not re.search(r"(?:先行(?:受付)?|一般(?:販売|発売)|チケット(?:先行)?受付)", line, re.I):
            continue
        if not re.search(r"(?:スタート|開始|受付中|受付開始)", line):
            continue
        match = parser.DATE_ANY_RE.search(line)
        if not match:
            continue
        value = parser.date_match_to_iso(match, year)
        if not value or "T" not in value:
            continue
        if value not in starts:
            starts.append(value)
    if len(starts) != 1:
        return []
    start = starts[0]
    occurrences = parser.extract_event_occurrences(
        [line for line in text.splitlines() if parser.normalize_space(line)], title, published,
    )
    if not occurrences:
        return []
    group = candidate.group
    if group == "KAWAII LAB. FC":
        group = infer_central_group(title, text, candidate.url, existing)
        if not group:
            return []
    if group == "KAWAII LAB.合同":
        label = "KAWAII LAB. FC先行"
    elif re.search(r"(?:FC|FANCLUB|ファンクラブ)", title, re.I):
        label = f"{group} FC先行"
    else:
        label = parser.extract_ticket_type(title, text)
    today = datetime.now(parser.JST).date().isoformat()
    source_rows = []
    for event_date, venue, opened, start_time in occurrences:
        if event_date < today:
            continue
        source_rows.append({
            "id": parser.event_id(group, candidate.url, event_date, start, label),
            "group": group, "title": title,
            "eventTitle": _stable_performance_title(title, group),
            "ticketType": label, "applyStart": start, "applyEnd": None,
            "eventDate": event_date, "venue": venue,
            "openTime": opened, "startTime": start_time,
            "url": candidate.url, "urls": [candidate.url],
            "sourceType": "auto", "primarySource": "official",
            "sourceChannel": "kawaii-lab-fc" if candidate.group == "KAWAII LAB. FC" else "official-continuous",
            "applicationStartVerified": True,
            "applicationWindowSource": candidate.url,
            "sourcePublishedAt": published,
            "windowCompleteness": "start-only",
            "participants": parser.extract_target_participants(text, event_date),
            "eventScope": "kawaii-lab",
        })
    return source_rows


def read_candidate(candidate, existing, headers):
    with requests.Session() as session:
        session.headers.update(headers)
        response = session.get(candidate.url, timeout=18)
        response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    soup = soup.select_one(".section--detail") or soup
    for node in soup.select("header, footer, nav, script, style"):
        node.decompose()
    heading = soup.select_one(".block--title .tit, h1")
    title = parser.normalize_space(heading.get_text(" ", strip=True)) if heading else candidate.title
    if not title or title.upper() in {"NEWS", "INFORMATION", "LIVE", "SCHEDULE"}:
        title = candidate.title
    # Official Fanplus articles sometimes use compatibility CJK characters
    # (e.g. 2026年11⽉6⽇); normalize before date/window extraction.
    title = unicodedata.normalize("NFKC", title)
    text = unicodedata.normalize("NFKC", soup.get_text("\n", strip=True))
    non_sale_title_hints = (
        *parser.IGNORE_TITLE_HINTS,
        "払い戻し", "連動企画", "デジタル整理券", "AUDITION", "ご注意とお願い",
        "システムメンテナンス", "店頭キャンペーン",
        "JTBオフィシャルファンクラブツアー", "に関しまして",
    )
    if any(hint in title for hint in non_sale_title_hints):
        return [], None, "irrelevant"
    if title_is_past_event(title, text, datetime.now(parser.JST).date()):
        return [], None, "past"
    if not any(hint in text or hint in title for hint in (*parser.TICKET_HINTS, "一般販売")):
        announced = official_show_announcement_rows(candidate, title, text)
        if announced:
            return announced, None, "schedule-only"
        if re.search(r"(?:開催決定|公演決定|出演決定)", title) and re.search(
            r"(?:ライブ|LIVE|公演|ツアー|TOUR|フェス|FES|生誕祭|コンサート)", title, re.I
        ):
            return [], {"group": candidate.group, "title": title, "url": candidate.url,
                        "reason": "公式INFORMATIONの新公演記事ですが日付・会場を特定できません。公式URLを保存して再試行します。",
                        "sourcePublishedAt": parser.article_date_from_text(text)}, "pending"
        return [], None, "irrelevant"
    today = datetime.now(parser.JST).date()
    group = candidate.group
    if group == "KAWAII LAB. FC":
        group = infer_central_group(title, text, candidate.url, existing)
        if not group:
            # Old central-FC articles can remain ambiguous forever after their
            # receptions end. Do not keep asking a human to resolve a sale that
            # can no longer be acted on; only current/future ambiguous windows
            # belong in pendingReview.
            if ticket_windows_are_all_expired(text, today):
                return [], None, "past"
            return [], {
                "group": candidate.group,
                "title": title,
                "url": candidate.url,
                "reason": "Official article group is ambiguous",
                "sourcePublishedAt": parser.article_date_from_text(text),
            }, "pending"
    candidate = parser.Candidate(group, title, candidate.url)
    rows, review = parser.parse_candidate(CachedArticle(str(soup)), candidate)
    if not rows and not review:
        rows = (verified_unlabeled_window_rows(candidate, title, text, existing)
                or confirmed_start_only_rows(candidate, title, text, existing))
    if not rows and not review:
        # An INFORMATION notice can announce a concert and merely mention
        # 'tickets' in its fine print. Keep the verified performance even when
        # the sale detail cannot yet be extracted.
        rows = official_show_announcement_rows(candidate, title, text)
        if rows and any(hint in title for hint in parser.TICKET_HINTS):
            review = {
                "group": candidate.group, "title": title, "url": candidate.url,
                "reason": "公式公演は登録済みですが、記事内の受付条件はまだ抽出できません。受付情報を継続照合します。",
                "sourcePublishedAt": parser.article_date_from_text(text),
            }
    paired_resales = paired_resale_rows(candidate, text)
    if paired_resales:
        existing_keys = {(row.get("eventDate"), row.get("ticketType"), row.get("applyStart"), row.get("applyEnd")) for row in rows}
        for row in paired_resales:
            key = (row.get("eventDate"), row.get("ticketType"), row.get("applyStart"), row.get("applyEnd"))
            if key not in existing_keys:
                rows.append(row)
                existing_keys.add(key)
        review = None
    # A parser may return a usable historical/partial row and a review at the
    # same time.  The review is still resolved when the exact official notice
    # is already attached to a current/future event with the same verified
    # ticket family and complete window; keep any parsed rows, but do not keep
    # emitting the already-published notice as pending.
    if review and source_notice_is_already_represented(candidate, title, existing):
        review = None
    if not rows and not review:
        published = parser.article_date_from_text(text)
        default_year = int(published[:4]) if published else datetime.now(parser.JST).year
        window = unlabeled_ticket_window(text, default_year) or standalone_ticket_window(text, default_year)
        if window:
            review = {
                "group": group, "title": title, "url": candidate.url,
                "reason": "申込期間を取得しましたが、公演への結合待ちです。",
                "applyStart": window[0], "applyEnd": window[1],
            }
        elif end_only_ticket_window_is_expired(text, today):
            return [], None, "past"
    if not rows and review:
        if review_is_already_represented(candidate, review, existing):
            return [], None, "represented"
        if source_notice_is_already_represented(candidate, title, existing):
            return [], None, "represented"
        fallback = fallback_row_from_review(candidate, title, text, review, existing)
        if fallback:
            rows = [fallback]
            review = None
        elif review_is_expired(review, datetime.now(parser.JST).date()):
            return [], None, "past"
    # The announcement's subject takes precedence over mentions of previous
    # receptions in its terms (e.g. "FC purchasers may apply for this upgrade").
    for row in rows:
        if "アップグレード" in title:
            row["ticketType"] = "アップグレード抽選"
        elif "リセール" in title:
            row["ticketType"] = "リセール"
        elif re.search(r"一般(?:発売|販売)", title):
            row["ticketType"] = "一般発売"
        elif urlparse(candidate.url).netloc == urlparse(retention.CENTRAL_FC_BASE).netloc and retention.FC_HINT_RE.search(title):
            row["ticketType"] = "KAWAII LAB. FC先行"
            row["sourceChannel"] = "kawaii-lab-fc"
        row["id"] = parser.event_id(group, candidate.url, row["eventDate"], row.get("applyStart", ""), row["ticketType"])
        if row.get("startTime"):
            row["id"] += hashlib.sha1(row["startTime"].encode()).hexdigest()[:6]
    # Additional explicit sale sections must be parsed even if an older FC
    # reception in this same article was already parsed successfully.
    sales = general_sale_rows(candidate, text, existing)
    for row in sales:
        if not any(all(old.get(k) == row.get(k) for k in ("eventDate", "startTime", "ticketType", "applyStart")) for old in rows):
            rows.append(row)
    if not rows and not review:
        if source_notice_is_already_represented(candidate, title, existing):
            return [], None, "represented"
        if "/live_information/detail/" in candidate.url:
            return [], None, "schedule-only"
        review = {"group": group, "title": title, "url": candidate.url,
                  "reason": "Ticket article found; performance/reception could not be extracted",
                  "sourcePublishedAt": parser.article_date_from_text(text)}
    return rows, review, "parsed" if rows and not review else "pending"


def collect(session, existing):
    today = datetime.now(parser.JST).date()
    candidates = revisit_candidates(existing, today)
    must_refresh_urls = set(candidates)
    prior_observations = {
        str(row.get("url")): row
        for row in existing.get("officialDiscoveryState", {}).get("observations", [])
        if isinstance(row, dict) and row.get("url")
    }
    retracted_urls = retracted_source_urls()
    failures, pending, observations = [], [], []
    counts, fresh = {}, {}
    feeds = {**parser.GROUPS, "KAWAII LAB. FC": retention.CENTRAL_FC_BASE}
    with ThreadPoolExecutor(max_workers=len(feeds)) as pool:
        futures = {pool.submit(retention.deep_candidate_links, session, group, base): group for group, base in feeds.items()}
        for future in as_completed(futures):
            group = futures[future]
            try:
                found = future.result()
                counts[group] = len(found)
                candidates.update({item.url: item for item in found if item.url not in retracted_urls})
                failures.extend(retention.FEED_FAILURES.get(group, []))
                if not found:
                    failures.append({"group": group, "stage": "news-list", "error": "No detail links in official feed"})
            except Exception as exc:
                counts[group] = 0
                failures.append({"group": group, "stage": "news-list", "error": str(exc)})
    for url in retracted_urls:
        candidates.pop(url, None)
    now = datetime.now(parser.JST).isoformat(timespec="seconds")
    headers = dict(session.headers)
    to_read = []
    for item in candidates.values():
        previous = prior_observations.get(item.url)
        # Keep the full INVENTORY of every official URL. To avoid hundreds of
        # irrelevant old notices being downloaded every 15 minutes, reuse only
        # previously inspected non-ticket notices older than two weeks. Rotate
        # a deterministic 1/7 of these through a fresh read each day.
        old_irrelevant = False
        if previous and previous.get("status") == "irrelevant" and item.url not in must_refresh_urls:
            date_prefix = re.match(r"^\s*(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", item.title)
            if date_prefix and previous.get("title") == item.title:
                try:
                    published = datetime(
                        int(date_prefix.group(1)), int(date_prefix.group(2)), int(date_prefix.group(3)),
                    ).date()
                    old_irrelevant = (today - published).days > 14
                except ValueError:
                    pass
        if old_irrelevant and int(hashlib.sha256(item.url.encode()).hexdigest(), 16) % 7 != today.weekday():
            observations.append({
                **previous, "listedAt": now, "cached": True,
            })
            continue
        to_read.append(item)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(read_candidate, item, existing, headers): item for item in to_read}
        for future in as_completed(futures):
            item = futures[future]
            observation = {"group": item.group, "url": item.url, "title": item.title, "checkedAt": now}
            try:
                rows, review, status = future.result()
                fresh.update({row["id"]: row for row in rows})
                if review:
                    pending.append(review)
                observation.update(status=status, eventIds=[row["id"] for row in rows])
                observation["expectedOffers"] = [
                    {key: row.get(key) for key in ("id", "group", "eventDate", "startTime", "ticketType", "applyStart", "applyEnd", "url")}
                    for row in rows if retention.should_show(row, datetime.now(parser.JST).date())
                ]
                if rows and all(not retention.should_show(row, datetime.now(parser.JST).date()) for row in rows):
                    observation["status"] = "past"
            except Exception as exc:
                failure = {"group": item.group, "url": item.url, "title": item.title, "stage": "article", "error": str(exc)}
                failures.append(failure)
                observation.update(status="failed", error=str(exc))
            observations.append(observation)
    observations.sort(key=lambda row: row["url"])
    return fresh, pending, failures, counts, observations
