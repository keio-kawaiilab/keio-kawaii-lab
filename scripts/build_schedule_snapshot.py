#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DATA_PATH = Path("data/live-events.json")
PAGE_PATH = Path("schedule.html")
JST = ZoneInfo("Asia/Tokyo")
SHORT_SCHEDULE_VENUE_LIMIT = 6

GROUP_VAR = {
    "FRUITS ZIPPER": "--fruits",
    "CANDY TUNE": "--candy",
    "SWEET STEADY": "--sweet",
    "CUTIE STREET": "--cutie",
    "MORE STAR": "--more",
    "KAWAII LAB.合同": "--lab",
}
BAD_UI_TITLE_RE = re.compile(r"行きたい\s*[!！]?\s*公演アラート|お気に入り(?:登録)?|メールで通知", re.I)
OFFICIAL_ONLY_RE = re.compile(r"アップグレード|(?:^|\s)FC(?:\s|$)|ファンクラブ|年会費コース", re.I)


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def parse_day(value: object):
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(value or ""))
    if not match:
        return None
    return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=JST).date()


def fmt(value: object) -> str:
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?", str(value or ""))
    if not match:
        return "—"
    text = f"{int(match.group(1))}/{int(match.group(2))}/{int(match.group(3))}"
    if match.group(4):
        text += f" {match.group(4)}:{match.group(5)}"
    return text


def fmt_md(value: object) -> str:
    match = re.match(r"^\d{4}-(\d{2})-(\d{2})", str(value or ""))
    if not match:
        return "?/?"
    return f"{int(match.group(1))}/{int(match.group(2))}"


def urls(event: dict) -> list[str]:
    result = []
    if event.get("url"):
        result.append(str(event["url"]))
    for url in event.get("urls") or []:
        if url and str(url) not in result:
            result.append(str(url))
    return result


def is_pia(event: dict) -> bool:
    return (
        str(event.get("sourceType") or "").lower() == "pia"
        or str(event.get("primarySource") or "").lower() == "pia"
        or any("t.pia.jp" in url for url in urls(event))
    )


def is_online(event: dict) -> bool:
    return event.get("eventCategory") == "online-benefit" or bool(
        re.search(r"オンライン(?:特典会|サイン会)", str(event.get("title") or ""))
    )


def official_only(event: dict) -> bool:
    text = f"{event.get('ticketType', '')} {event.get('title', '')}"
    return bool(OFFICIAL_ONLY_RE.search(text))


def event_dates(event: dict) -> list[str]:
    result: list[str] = []
    if isinstance(event.get("schedule"), list):
        for item in event["schedule"]:
            if isinstance(item, dict) and item.get("date"):
                result.append(str(item["date"])[:10])
    if not result and isinstance(event.get("eventDates"), list):
        result.extend(str(value)[:10] for value in event["eventDates"] if value)
    if not result and event.get("eventDate"):
        result.append(str(event["eventDate"])[:10])
    return list(dict.fromkeys(result))


def schedule_rows(event: dict) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    seen = set()
    if isinstance(event.get("schedule"), list):
        for item in event["schedule"]:
            if not isinstance(item, dict) or not item.get("date"):
                continue
            day = str(item.get("date"))[:10]
            venue = str(item.get("venue") or "").strip()
            marker = (day, venue)
            if marker in seen:
                continue
            seen.add(marker)
            rows.append(marker)
    return rows


def venue_text(event: dict, online: bool = False) -> str:
    if online:
        return str(event.get("venue") or "オンライン（SUKISUKI）")
    rows = schedule_rows(event)
    if len(rows) == 1:
        return rows[0][1] or str(event.get("venue") or "未定")
    if 2 <= len(rows) <= SHORT_SCHEDULE_VENUE_LIMIT:
        return " ／ ".join(f"{fmt_md(day)} {venue or '会場未定'}" for day, venue in rows)
    if len(rows) > SHORT_SCHEDULE_VENUE_LIMIT:
        return str(event.get("venue") or f"複数会場（全{len(rows)}公演）")
    return str(event.get("venue") or "未定")


def display_title(event: dict) -> str:
    text = str(event.get("eventTitle") or event.get("title") or "").strip()
    if not text or BAD_UI_TITLE_RE.search(text):
        return f"{event.get('group') or 'KAWAII LAB.'} 公演"
    quoted = re.search(r"「([^」]+)」", text)
    if quoted:
        text = quoted.group(1).strip()
    text = re.sub(r"^(?:20\d{2}年)?\d{1,2}月\d{1,2}日(?:\([^)]*\)|（[^）]*）)?\s*", "", text)
    for group in ("FRUITS ZIPPER", "CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR", "KAWAII LAB.合同", "KAWAII LAB."):
        text = re.sub(rf"^{re.escape(group)}\s*", "", text, flags=re.I)
    return text.strip(" !！-|｜–—") or f"{event.get('group') or 'KAWAII LAB.'} 公演"


def source_url(event: dict) -> str:
    values = urls(event)
    return values[0] if values else ""


def visible_event(event: dict, today) -> bool:
    if is_pia(event) and official_only(event):
        return False
    dates = [parse_day(value) for value in event_dates(event)]
    dates = [value for value in dates if value]
    last = max(dates) if dates else parse_day(event.get("eventEndDate") or event.get("eventDate"))
    deadline = parse_day(event.get("applyEnd"))
    if last and last < today and (not deadline or deadline < today):
        return False
    if is_pia(event) and event.get("ticketType") != "現在受付なし" and deadline and deadline < today:
        return False
    return True


def build_card(event: dict) -> str:
    online = is_online(event)
    pia = is_pia(event)
    dates = event_dates(event)
    date_text = "・".join(fmt(value) for value in dates) if dates else "未定"
    group = str(event.get("group") or "KAWAII LAB.")
    color = GROUP_VAR.get(group, "--lab")
    url = source_url(event)
    synthetic = pia and bool(event.get("applyEnd")) and not event.get("applyStart")
    start_text = "開始日時未取得" if synthetic else fmt(event.get("applyStart"))
    icon = "📱" if online else "🎤"
    css = "card online-card" if online else "card"
    parts = [
        f'<article class="{css}" data-group="{esc(group)}" data-event-id="{esc(event.get("id") or "")}" style="--gc:var({color})">',
        f'<h3>{icon} {esc(display_title(event))}</h3>',
        '<div class="meta">',
        f'<div><b>グループ</b>{esc(group)}</div>',
        f'<div><b>{"配信日" if online else "公演日"}</b>{esc(date_text)}</div>',
        f'<div><b>会場</b>{esc(venue_text(event, online))}</div>',
        f'<div><b>受付</b>{esc(event.get("ticketType") or "未定")}</div>',
        f'<div><b>申込開始</b>{esc(start_text)}</div>',
        f'<div><b>申込締切</b>{esc(fmt(event.get("applyEnd")))}</div>',
        '</div>',
    ]
    if synthetic:
        parts.append('<div class="deadline-note">開始日時は未取得です。カレンダーの帯は今日から締切まで表示しています。</div>')
    if url:
        label = "チケットぴあを確認 →" if pia else ("SUKISUKIを確認 →" if "sukisuki-shop.com" in url else "情報源を確認 →")
        parts.append(f'<a class="src" href="{esc(url)}" target="_blank" rel="noopener">{label}</a>')
    parts.append('</article>')
    return "".join(parts)


def main() -> int:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    page = PAGE_PATH.read_text(encoding="utf-8")

    if 'id="snapshot-data"' not in page:
        print("schedule.html has no snapshot-data block yet; leaving page untouched")
        return 0

    today = datetime.now(JST).date()
    events = [dict(x) for x in payload.get("events", []) if isinstance(x, dict)]
    visible = [event for event in events if visible_event(event, today)]
    visible.sort(key=lambda event: min([parse_day(x) for x in event_dates(event) if parse_day(x)] or [today]))

    snapshot = json.dumps({"updatedAt": payload.get("updatedAt"), "events": visible}, ensure_ascii=False, separators=(",", ":"))
    snapshot = snapshot.replace("</", "<\\/")
    page = re.sub(
        r'(<script id="snapshot-data" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + snapshot + m.group(2),
        page,
        count=1,
        flags=re.S,
    )

    cards = "\n".join(build_card(event) for event in visible)
    page = re.sub(
        r'(<div class="cards" id="cards">).*?(</div>\s*<script id="snapshot-data")',
        lambda m: m.group(1) + "\n" + cards + "\n" + m.group(2),
        page,
        count=1,
        flags=re.S,
    )

    days_since_sunday = (today.weekday() + 1) % 7
    grid_end = today - timedelta(days=days_since_sunday) + timedelta(days=34)
    page = re.sub(r'<div id="range">.*?</div>', f'<div id="range">{today.month}/{today.day}〜{grid_end.month}/{grid_end.day}（5週間）</div>', page, count=1)
    page = re.sub(r'<div class="summary" id="summary">.*?</div>', f'<div class="summary" id="summary">{len(visible)}件掲載中</div>', page, count=1, flags=re.S)

    PAGE_PATH.write_text(page, encoding="utf-8")
    print(f"Built layout-safe schedule snapshot: {len(visible)} events ({payload.get('updatedAt') or ''})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
