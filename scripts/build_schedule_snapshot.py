#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
from urllib.parse import quote
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from schedule_scope import HOSTED, infer_event_scope

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

SCHEDULE_NAV_STYLE = """
/* schedule-site-nav-style */
.head{position:sticky;top:0;z-index:60;background:rgba(255,255,255,.96);backdrop-filter:blur(10px);box-shadow:0 5px 18px rgba(34,51,95,.08)}
.schedule-home-link{display:inline-flex;align-items:center;gap:7px;margin:0 0 10px;padding:8px 13px;border-radius:999px;background:#22335f;color:#fff;text-decoration:none;font-weight:800;font-size:12px;box-shadow:0 3px 10px rgba(34,51,95,.18)}
.schedule-home-link:hover{filter:brightness(1.08)}
.schedule-home-link:focus-visible{outline:3px solid #c19b46;outline-offset:3px}
.schedule-head-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
.schedule-home-link.schedule-venue-link{background:#a93b4f}
.venue-link{display:inline;font-weight:800;color:var(--navy);text-decoration:underline;text-decoration-color:#a93b4f66;text-decoration-thickness:2px;text-underline-offset:3px}
.venue-link:hover{color:#a93b4f}
.venue-schedule summary{cursor:pointer;color:var(--navy);font-weight:800}
.venue-schedule ul{display:grid;gap:6px;margin:8px 0 0;padding:0;list-style:none}
.venue-schedule li{display:grid;grid-template-columns:4.5em 1fr;gap:7px}
.venue-schedule time{color:var(--muted);font-size:12px;font-weight:700}
/* special-event-polka-style */
.special-event{background-image:radial-gradient(circle at 2px 2px,rgba(255,255,255,.88) 0 1.7px,transparent 1.9px)!important;background-size:9px 9px!important}
.card.release-card,.card.benefit-card{background-color:#fffdf9;background-image:radial-gradient(circle at 2px 2px,rgba(34,51,95,.13) 0 1.7px,transparent 1.9px);background-size:12px 12px}
.card.benefit-card{background-color:#fff9fc}
.card.release-card .special-info,.card.benefit-card .special-info{background:rgba(246,247,251,.96)}
"""
SCHEDULE_NAV_HTML = '<div class="schedule-head-actions"><a class="schedule-home-link schedule-venue-link" href="./venues.html">📍 会場ガイド</a><a class="schedule-home-link" href="./index.html" aria-label="慶應KAWAII LAB.同好会公式サイトへ戻る">← 同好会公式サイトへ戻る</a></div>'


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def parse_day(value: object):
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(value or ""))
    if not match:
        return None
    return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=JST).date()


def parse_moment(value: object, *, end_of_day: bool = False):
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?", str(value or ""))
    if not match:
        return None
    hour = int(match.group(4)) if match.group(4) is not None else (23 if end_of_day else 0)
    minute = int(match.group(5)) if match.group(5) is not None else (59 if end_of_day else 0)
    second = 59 if end_of_day and match.group(4) is None else 0
    try:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), hour, minute, second, tzinfo=JST)
    except ValueError:
        return None


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


def event_kind(event: dict) -> str:
    if event.get("eventCategory") == "large-benefit":
        return "benefit"
    if event.get("eventCategory") == "release-event":
        return "release"
    return "online" if is_online(event) else "live"


def event_icon(event: dict) -> str:
    return {"benefit": "🎁", "release": "💿", "online": "📱", "live": "🎤"}[event_kind(event)]


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


def venue_link(name: str, label: str | None = None) -> str:
    text = label or name or "未定"
    if not name or re.search(r"オンライン|会場未定|未定", name):
        return esc(text)
    return f'<a class="venue-link" href="venue.html?name={quote(name, safe="")}">{esc(text)}</a>'


def venue_html(event: dict, online: bool = False) -> str:
    if online:
        return esc(event.get("venue") or "オンライン（SUKISUKI）")
    rows = schedule_rows(event)
    if len(rows) == 1:
        return venue_link(rows[0][1] or str(event.get("venue") or "未定"))
    if 2 <= len(rows) <= SHORT_SCHEDULE_VENUE_LIMIT:
        return " ／ ".join(f'{esc(fmt_md(day) + " ")}{venue_link(venue or "会場未定")}' for day, venue in rows)
    if len(rows) > SHORT_SCHEDULE_VENUE_LIMIT:
        items = "".join(
            f'<li><time datetime="{esc(day)}">{esc(fmt_md(day))}</time><span>{venue_link(venue or "会場未定")}</span></li>'
            for day, venue in rows
        )
        return f'<details class="venue-schedule"><summary>複数会場（全{len(rows)}公演）を表示</summary><ul>{items}</ul></details>'
    return venue_link(str(event.get("venue") or "未定"))


def display_title(event: dict) -> str:
    text = str(event.get("displayTitle") or event.get("eventTitle") or event.get("title") or "").strip()
    if not text or BAD_UI_TITLE_RE.search(text):
        return f"{event.get('group') or 'KAWAII LAB.'} 公演"
    quoted = re.search(r"「([^」]+)」", text)
    if quoted:
        return quoted.group(1).strip()
    text = re.sub(r"^(?:20\d{2}年)?\d{1,2}月\d{1,2}日(?:\([^)]*\)|（[^）]*）)?\s*", "", text)
    for group in ("FRUITS ZIPPER", "CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR", "KAWAII LAB.合同", "KAWAII LAB."):
        text = re.sub(rf"^{re.escape(group)}\s*", "", text, flags=re.I)
    return text.strip(" !！-|｜–—") or f"{event.get('group') or 'KAWAII LAB.'} 公演"


def source_url(event: dict) -> str:
    values = urls(event)
    return values[0] if values else ""


def visible_event(event: dict, today, now=None) -> bool:
    if is_pia(event) and official_only(event):
        return False
    dates = [parse_day(value) for value in event_dates(event)]
    dates = [value for value in dates if value]
    last = max(dates) if dates else parse_day(event.get("eventEndDate") or event.get("eventDate"))
    deadline = parse_day(event.get("applyEnd"))
    deadline_moment = parse_moment(event.get("applyEnd"), end_of_day=True)
    if last and last < today and (not deadline or deadline < today):
        return False
    if is_pia(event) and event.get("ticketType") != "現在受付なし" and (
        (deadline and deadline < today) or (now and deadline_moment and deadline_moment < now)
    ):
        return False
    return True


def build_card(event: dict) -> str:
    online = is_online(event)
    kind = event_kind(event)
    pia = is_pia(event)
    dates = event_dates(event)
    date_text = "・".join(fmt(value) for value in dates) if dates else "未定"
    group = str(event.get("group") or "KAWAII LAB.")
    color = GROUP_VAR.get(group, "--lab")
    url = source_url(event)
    synthetic = pia and bool(event.get("applyEnd")) and not event.get("applyStart")
    start_text = "開始日時未取得" if synthetic else fmt(event.get("applyStart"))
    icon = event_icon(event)
    css = "card online-card" if online else ("card release-card" if kind == "release" else ("card benefit-card" if kind == "benefit" else "card"))
    parts = [
        f'<article class="{css}" data-group="{esc(group)}" data-scope="{esc(infer_event_scope(event))}" data-event-id="{esc(event.get("id") or "")}" style="--gc:var({color})">',
        '<span class="scope-badge">外部出演</span>' if infer_event_scope(event) != HOSTED else '',
        f'<h3>{icon} {esc(display_title(event))}</h3>',
        '<div class="meta">',
        f'<div><b>グループ</b>{esc(group)}</div>',
        f'<div><b>{"配信日" if online else "開催日"}</b>{esc(date_text)}</div>',
        f'<div><b>会場</b>{venue_html(event, online)}</div>',
        f'<div><b>受付</b>{esc(event.get("ticketType") or "未定")}</div>',
        f'<div><b>申込開始</b>{esc(start_text)}</div>',
        f'<div><b>申込締切</b>{esc(fmt(event.get("applyEnd")))}</div>',
        '</div>',
    ]
    if synthetic:
        parts.append('<div class="deadline-note">開始日時は未取得です。カレンダーの帯は今日から締切まで表示しています。</div>')
    if kind in {"benefit", "release"}:
        detail = [
            '<section class="special-info"><h4>参加方法・整理券</h4><div class="special-grid">',
        ]
        if event.get("salesStartTime"):
            detail.append(f'<div><b>会場販売開始</b>{esc(event["salesStartTime"])}</div>')
        if event.get("gatheringTime"):
            detail.append(f'<div><b>集合</b>{esc(event["gatheringTime"])}</div>')
        if event.get("startTime"):
            detail.append(f'<div><b>イベント開始</b>{esc(event["startTime"])}</div>')
        if event.get("ticketName"):
            detail.append(f'<div><b>必要な整理券・参加券</b>{esc(event["ticketName"])}</div>')
        detail.append('</div>')
        if event.get("specialDetailsStatus") == "awaiting-details":
            detail.append('<p class="special-method"><b>受付情報：</b>公式の詳細発表待ちです。開催日と会場のみ確認済みです。</p>')
        if event.get("purchaseMethod"):
            detail.append(f'<p class="special-method"><b>参加方法：</b>{esc(event["purchaseMethod"])}</p>')
        if event.get("ticketIssueMethod"):
            detail.append(f'<p class="special-method"><b>発券・付与：</b>{esc(event["ticketIssueMethod"])}</p>')
        if event.get("product"):
            detail.append(f'<p class="special-method"><b>対象商品：</b>{esc(event["product"])}</p>')
        benefits = event.get("ticketBenefits") or []
        if isinstance(benefits, list) and benefits:
            detail.append('<h4>参加券・特典</h4><ul class="detail-list">')
            detail.extend(f'<li>{esc(item)}</li>' for item in benefits if item)
            detail.append('</ul>')
        calls = event.get("numberedCallTimes") or []
        if isinstance(calls, list) and calls:
            detail.append('<h4>整理番号別の集合・呼び出し目安</h4><div class="call-times">')
            for item in calls:
                if not isinstance(item, dict):
                    continue
                numbers = item.get("numbers") or "整理番号"
                time = item.get("time") or "時刻未定"
                detail.append(f'<span class="time-chip">{esc(numbers)}｜{esc(time)}</span>')
            detail.append('</div>')
        event_parts = event.get("parts") or []
        if isinstance(event_parts, list) and event_parts:
            detail.append('<h4>各部の時間・受付</h4><div class="part-times">')
            for item in event_parts:
                if not isinstance(item, dict):
                    continue
                part = esc(item.get("part") or "部")
                content = str(item.get("content") or "").strip()
                start = str(item.get("start") or "—")
                end = str(item.get("end") or "—")
                reception_start = str(item.get("receptionStart") or "—")
                reception_end = str(item.get("receptionEnd") or "—")
                label = (content + "｜" if content else "") + f"{start}〜{end}（受付 {reception_start}〜{reception_end}）"
                detail.append(f'<div class="part-row"><b>{part}</b><span>{esc(label)}</span></div>')
            detail.append('</div>')
        detail.append('</section>')
        parts.extend(detail)
    if url:
        label = "チケットぴあを確認 →" if pia else ("SUKISUKIを確認 →" if "sukisuki-shop.com" in url else "情報源を確認 →")
        parts.append(f'<a class="src" href="{esc(url)}" target="_blank" rel="noopener">{label}</a>')
    parts.append('</article>')
    return "".join(parts)


def ensure_site_navigation(page: str) -> str:
    if "schedule-site-nav-style" not in page:
        page = page.replace("</style>", SCHEDULE_NAV_STYLE + "\n</style>", 1)
    if 'class="schedule-home-link"' not in page:
        page = page.replace('<header class="head">', '<header class="head">' + SCHEDULE_NAV_HTML, 1)
    return page


def main() -> int:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    page = PAGE_PATH.read_text(encoding="utf-8")

    if 'id="snapshot-data"' not in page:
        print("schedule.html has no snapshot-data block yet; leaving page untouched")
        return 0

    page = ensure_site_navigation(page)
    if 'href="./train-status.css"' not in page:
        page = page.replace("<style>", '<link rel="stylesheet" href="./train-status.css">\n<style>', 1)
    page = re.sub(r'<script src="\./train-status\.js(?:\?v=[^"]*)?"></script>\s*', "", page)
    page = page.replace("</body>", '<script src="./train-status.js?v=202608281825"></script>\n</body>', 1)

    now = datetime.now(JST)
    today = now.date()
    events = [dict(x) for x in payload.get("events", []) if isinstance(x, dict)]
    visible = [event for event in events if visible_event(event, today, now)]
    visible.sort(key=lambda event: min([parse_day(x) for x in event_dates(event) if parse_day(x)] or [today]))
    default_visible = [event for event in visible if infer_event_scope(event) == HOSTED]

    snapshot = json.dumps({"updatedAt": payload.get("updatedAt"), "events": visible}, ensure_ascii=False, separators=(",", ":"))
    snapshot = snapshot.replace("</", "<\\/")
    page = re.sub(
        r'(<script id="snapshot-data" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + snapshot + m.group(2),
        page,
        count=1,
        flags=re.S,
    )

    cards = "\n".join(build_card(event) for event in default_visible)
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
    page = re.sub(r'<div class="summary" id="summary">.*?</div>', f'<div class="summary" id="summary">{len(default_visible)}イベントを掲載中（KAWAII LAB.主催のみ）</div>', page, count=1, flags=re.S)

    PAGE_PATH.write_text(page, encoding="utf-8")
    print(f"Built layout-safe schedule snapshot: {len(default_visible)} hosted / {len(visible)} total ({payload.get('updatedAt') or ''})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
