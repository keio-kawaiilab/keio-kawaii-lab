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

GROUP_VAR = {
    "FRUITS ZIPPER": "--fruits",
    "CANDY TUNE": "--candy",
    "SWEET STEADY": "--sweet",
    "CUTIE STREET": "--cutie",
    "MORE STAR": "--more",
    "KAWAII LAB.合同": "--lab",
}
GROUP_NAMES = (
    "FRUITS ZIPPER", "CANDY TUNE", "SWEET STEADY", "CUTIE STREET",
    "MORE STAR", "KAWAII LAB.合同", "KAWAII LAB.",
)
BAD_UI_TITLE_RE = re.compile(
    r"行きたい\s*[!！]?\s*公演アラート|お気に入り(?:登録)?|メールで通知|通信エラー",
    re.I,
)


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def parse_day(value: object):
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(value or ""))
    if not match:
        return None
    return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=JST).date()


def fmt(value: object) -> str:
    text = str(value or "")
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?", text)
    if not match:
        return "—"
    base = f"{int(match.group(1))}/{int(match.group(2))}/{int(match.group(3))}"
    if match.group(4):
        base += f" {match.group(4)}:{match.group(5)}"
    return base


def is_online(event: dict) -> bool:
    text = f"{event.get('eventCategory', '')} {event.get('title', '')}"
    return event.get("eventCategory") == "online-benefit" or bool(re.search(r"オンライン(?:特典会|サイン会)", text))


def is_pia(event: dict) -> bool:
    urls = [str(event.get("url") or "")] + [str(x) for x in (event.get("urls") or [])]
    return (
        str(event.get("sourceType") or "").lower() == "pia"
        or str(event.get("primarySource") or "").lower() == "pia"
        or any("t.pia.jp" in value for value in urls)
    )


def deadline_only(event: dict) -> bool:
    return (
        is_pia(event)
        and event.get("deadlineVerified") is True
        and event.get("applicationWindowVerified") is not True
        and bool(event.get("applyEnd"))
    )


def event_dates(event: dict) -> list[str]:
    values: list[str] = []
    schedule = event.get("schedule")
    if isinstance(schedule, list):
        for item in schedule:
            if isinstance(item, dict) and item.get("date"):
                values.append(str(item["date"])[:10])
    dates = event.get("eventDates")
    if not values and isinstance(dates, list):
        values.extend(str(value)[:10] for value in dates if value)
    if not values and event.get("eventDate"):
        values.append(str(event["eventDate"])[:10])
    return list(dict.fromkeys(values))


def display_title(event: dict) -> str:
    text = str(event.get("eventTitle") or event.get("title") or "ライブ情報").strip()
    text = re.sub(r"^20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+", "", text)
    quoted = re.search(r"「([^」]+)」", text)
    if quoted:
        text = quoted.group(1).strip()
    text = re.sub(r"^(?:20\d{2}年)?\d{1,2}月\d{1,2}日(?:\([^)]*\)|（[^）]*）)?\s*", "", text)
    for group in GROUP_NAMES:
        text = re.sub(rf"^{re.escape(group)}\s*", "", text, flags=re.I)
    text = re.split(
        r"\s*@|開催決定|出演決定|アップグレード抽選受付|一般(?:発売|販売|先行)|"
        r"FC\s*(?:会員)?先行|受付のお知らせ",
        text,
        maxsplit=1,
        flags=re.I,
    )[0]
    text = text.strip(" !！-|｜–—")
    return text or str(event.get("title") or "ライブ情報")


def source_url(event: dict) -> str:
    if event.get("url"):
        return str(event["url"])
    urls = event.get("urls")
    if isinstance(urls, list) and urls:
        return str(urls[0])
    return ""


def build_card(event: dict) -> str:
    online = is_online(event)
    icon = "📱" if online else "🎤"
    dates = event_dates(event)
    date_text = "・".join(fmt(value) for value in dates) if dates else "未定"
    label = "配信日" if online else "公演日"
    group = str(event.get("group") or "KAWAII LAB.")
    color = GROUP_VAR.get(group, "--lab")
    url = source_url(event)
    css = "card online-card" if online else "card"
    event_id = esc(event.get("id") or "")
    start_text = "ぴあで確認（締切のみ確定）" if deadline_only(event) else fmt(event.get("applyStart"))
    parts = [
        f'<article class="{css}" data-group="{esc(group)}" data-event-id="{event_id}" style="--gc:var({color})">',
        f'<h3>{icon} {esc(display_title(event))}</h3>',
        '<div class="meta">',
        f'<div><b>グループ</b>{esc(group)}</div>',
        f'<div><b>{label}</b>{esc(date_text)}</div>',
        f'<div><b>会場</b>{esc(event.get("venue") or ("オンライン（SUKISUKI）" if online else "未定"))}</div>',
        f'<div><b>受付</b>{esc(event.get("ticketType") or "未定")}</div>',
        f'<div><b>申込開始</b>{esc(start_text)}</div>',
        f'<div><b>申込締切</b>{esc(fmt(event.get("applyEnd")))}</div>',
        '</div>',
    ]
    if deadline_only(event):
        parts.append('<div class="deadline-note">⏰ 申込締切は確認済み。開始日時は推測せず、ぴあで確認してください。</div>')
    if url:
        source_label = "SUKISUKIを確認 →" if online and "sukisuki-shop.com" in url else "情報源を確認 →"
        parts.append(f'<a class="src" href="{esc(url)}" target="_blank" rel="noopener">{source_label}</a>')
    parts.append('</article>')
    return "".join(parts)


def patch_runtime(page: str) -> str:
    """Keep the standalone page conservative even when live JSON contains partial Pia timing."""
    # CSS for deadline-only milestones and explanatory note.
    if ".deadline-note{" not in page:
        page = page.replace(
            ".bar{height:42px;color:#fff;text-align:left}",
            ".bar{height:42px;color:#fff;text-align:left}.deadline{height:32px;text-align:left;color:#fff;border-radius:8px}.deadline-note{margin-top:10px;padding:8px 10px;border-radius:9px;background:#fff7dc;color:#66531d;font-size:12px;font-weight:700}",
        )

    # A Pia row is safe if it has either a verified full window or a verified exact deadline.
    page = re.sub(
        r"function safe\(e\)\{.*?\}",
        "function safe(e){if(!pia(e)||e.ticketType==='現在受付なし')return true;if(genericTitle(e))return false;if(e.applicationWindowVerified===true)return !!e.applyStart&&!!e.applyEnd;return e.deadlineVerified===true&&!!e.applyEnd}",
        page,
        count=1,
    )
    if "function deadlineOnly(e)" not in page:
        page = page.replace(
            "function parts(e){",
            "function deadlineOnly(e){return pia(e)&&e.deadlineVerified===true&&e.applicationWindowVerified!==true&&!!e.applyEnd}\nfunction parts(e){",
            1,
        )

    # Show the exact deadline instead of dropping a sale whose start time cannot be proven.
    if "function addDeadline(" not in page:
        marker_fn = (
            "function addDeadline(week,e,ws,we,ge,row){if(!deadlineOnly(e))return;var z=p(e.applyEnd);"
            "if(!z||z<start||z<ws||z>we||z>ge)return;var idx=Math.round((z-ws)/86400000),b=document.createElement('button');"
            "b.type='button';b.className='mark deadline '+gc(e);b.textContent='⏰ '+shortTitle(e)+'｜'+fmt(e.applyEnd);"
            "b.title=fullTitle(e)+' / 申込締切 '+fmt(e.applyEnd)+'（開始日時はぴあで確認）';"
            "b.style.left='calc('+(idx/7*100)+'% + 4px)';b.style.width='calc('+(100/7)+'% - 8px)';"
            "b.style.top=(112+(row.value%2)*36)+'px';b.onclick=function(){scrollCard(e)};week.appendChild(b);row.value++}\n"
        )
        page = page.replace("function render(){", marker_fn + "function render(){", 1)

    page = page.replace(
        "var pr={value:0},br={value:0};vis.forEach(function(e){addPerformance(week,e,ws,we,ge,pr);addBand(week,e,ws,we,ge,br)});week.style.minHeight=(184+Math.max(0,br.value-2)*18)+'px';",
        "var pr={value:0},br={value:0},dr={value:0};vis.forEach(function(e){addPerformance(week,e,ws,we,ge,pr);addBand(week,e,ws,we,ge,br);addDeadline(week,e,ws,we,ge,dr)});week.style.minHeight=(184+Math.max(0,br.value+dr.value-2)*18)+'px';",
        1,
    )

    if "function startText(e)" not in page:
        page = page.replace(
            "function fmt(v){",
            "function startText(e){return deadlineOnly(e)?'ぴあで確認（締切のみ確定）':fmt(e.applyStart)}\nfunction fmt(v){",
            1,
        )
    page = page.replace("esc(fmt(e.applyStart))", "esc(startText(e))")

    return page


def main() -> int:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    page = PAGE_PATH.read_text(encoding="utf-8")
    today = datetime.now(JST).date()

    events = []
    for raw in payload.get("events", []):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("eventTitle") or raw.get("title") or "")
        if BAD_UI_TITLE_RE.search(title):
            # Last-resort display guard: UI labels can never become public event names.
            continue
        dates = [parse_day(value) for value in event_dates(raw)]
        dates = [value for value in dates if value]
        last = max(dates) if dates else parse_day(raw.get("eventEndDate") or raw.get("eventDate"))
        if last is None or last >= today:
            events.append(raw)

    events.sort(key=lambda event: min([parse_day(value) for value in event_dates(event) if parse_day(value)] or [today]))
    cards = "\n".join(build_card(event) for event in events)

    cards_pattern = re.compile(r'(<div class="cards" id="cards">).*?(</div>\s*</main>\s*<script>)', re.S)
    if not cards_pattern.search(page):
        raise RuntimeError("schedule.html cards block not found")
    page = cards_pattern.sub(lambda match: match.group(1) + "\n" + cards + "\n" + match.group(2), page, count=1)

    days_since_sunday = (today.weekday() + 1) % 7
    grid_start = today - timedelta(days=days_since_sunday)
    grid_end = grid_start + timedelta(days=34)
    range_text = f"{today.month}/{today.day}〜{grid_end.month}/{grid_end.day}（5週間）"
    page = re.sub(r'<div id="range">.*?</div>', f'<div id="range">{range_text}</div>', page, count=1)

    updated_at = str(payload.get("updatedAt") or "")
    note = f"※予定はHTMLにも自動生成済みです。最終データ更新: {esc(updated_at)}"
    page = re.sub(r'<p class="fallback-note" id="fallback-note">.*?</p>', f'<p class="fallback-note" id="fallback-note">{note}</p>', page, count=1, flags=re.S)
    page = re.sub(r'<div class="summary" id="summary">.*?</div>', f'<div class="summary" id="summary">{len(events)}件掲載中</div>', page, count=1, flags=re.S)

    page = patch_runtime(page)
    PAGE_PATH.write_text(page, encoding="utf-8")
    print(f"Built static schedule snapshot: {len(events)} events ({updated_at})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
