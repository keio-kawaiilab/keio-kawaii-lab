"""Read current announcements AND revisit future performances and unresolved articles.

Each URL has an outcome. A failed page never discards successful observations.
No event dates or ticket deadlines are inferred from a sale's start time.
"""
from __future__ import annotations

import hashlib
import re
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
    source = direct_matches if direct_matches else existing.get("events", [])
    for event in source:
        if not isinstance(event, dict) or event.get("group") != group or not retention.should_show(event, today):
            continue
        if not direct_matches:
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
    text = soup.get_text("\n", strip=True)
    if not any(hint in text or hint in title for hint in (*parser.TICKET_HINTS, "一般販売")):
        return [], None, "irrelevant"
    group = candidate.group
    if group == "KAWAII LAB. FC":
        group = infer_central_group(title, text, candidate.url, existing)
        if not group:
            return [], {"group": candidate.group, "title": title, "url": candidate.url,
                        "reason": "Official article group is ambiguous"}, "pending"
    candidate = parser.Candidate(group, title, candidate.url)
    rows, review = parser.parse_candidate(CachedArticle(str(soup)), candidate)
    if not rows and not review:
        published = parser.article_date_from_text(text)
        default_year = int(published[:4]) if published else datetime.now(parser.JST).year
        window = unlabeled_ticket_window(text, default_year)
        if window:
            review = {
                "group": group, "title": title, "url": candidate.url,
                "reason": "受付見出し直後の申込期間を取得しましたが、公演への結合待ちです。",
                "applyStart": window[0], "applyEnd": window[1],
            }
    if not rows and review:
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
        if "/live_information/detail/" in candidate.url:
            return [], None, "schedule-only"
        review = {"group": group, "title": title, "url": candidate.url,
                  "reason": "Ticket article found; performance/reception could not be extracted",
                  "sourcePublishedAt": parser.article_date_from_text(text)}
    return rows, review, "parsed" if rows and not review else "pending"


def collect(session, existing):
    candidates = revisit_candidates(existing, datetime.now(parser.JST).date())
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
                candidates.update({item.url: item for item in found})
                failures.extend(retention.FEED_FAILURES.get(group, []))
                if not found:
                    failures.append({"group": group, "stage": "news-list", "error": "No detail links in official feed"})
            except Exception as exc:
                counts[group] = 0
                failures.append({"group": group, "stage": "news-list", "error": str(exc)})
    now = datetime.now(parser.JST).isoformat(timespec="seconds")
    headers = dict(session.headers)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(read_candidate, item, existing, headers): item for item in candidates.values()}
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
