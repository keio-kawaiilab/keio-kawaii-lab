#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

PAGE = Path("schedule.html")


def main() -> int:
    page = PAGE.read_text(encoding="utf-8")

    page = page.replace(
        "チケットぴあ掲載の受付は、<strong>FC先行・アップグレードを除いて原則すべて採用</strong>します。開始日時が取れない場合も、締切が分かれば<strong>今日〜締切を申込帯</strong>として表示します。📱シマシマ＝オンライン特典会。",
        "チケットぴあ掲載の受付は、<strong>FC先行・アップグレードを除いて原則すべて採用</strong>します。開始日時が未取得でも、締切が分かる受付は<strong>今日〜締切を申込帯</strong>で表示します。📱シマシマ＝オンライン特典会。",
    )
    page = page.replace(
        "色＝グループ ／ 横帯＝申込期間（開始不明時は今日から） ／ 🎫＝当落 ／ 💳＝入金期限 ／ 🎤＝ライブ ／ 📱＝オンライン特典会",
        "色＝グループ ／ 横帯＝申込期間 ／ 🎫＝当落 ／ 💳＝入金期限 ／ 🎤＝ライブ ／ 📱＝オンライン特典会",
    )
    page = page.replace("本日から帯表示（開始日時未取得）", "開始日時未取得")

    page = page.replace(
        "mbase=bbase+bl*44+10;height=mbase+ml*30+12;",
        "mbase=bbase+bl*44+10;var height=mbase+ml*30+12;",
    )

    page = page.replace("perf.push({e:e,s:i,e:i})", "perf.push({event:e,s:i,end:i})")
    page = page.replace(
        "bands.push({e:e,s:Math.round((aa-ws)/86400000),e:Math.round((zz-ws)/86400000),band:r})",
        "bands.push({event:e,s:Math.round((aa-ws)/86400000),end:Math.round((zz-ws)/86400000),band:r})",
    )
    page = page.replace(
        "miles.push({e:e,s:i,e:i,icon:m[1]})",
        "miles.push({event:e,s:i,end:i,icon:m[1]})",
    )
    page = page.replace(
        "items.sort(function(a,b){return a.s-b.s||a.e-b.e})",
        "items.sort(function(a,b){return a.s-b.s||a.end-b.end})",
    )
    page = page.replace("ends[n]=x.endnd", "ends[n]=x.end")
    page = re.sub(r"ends\[n\]=x\.e(?!nd)", "ends[n]=x.end", page)
    page = page.replace("var e=item.e,b=document.createElement('button')", "var e=item.event,b=document.createElement('button')")
    page = page.replace("((item.e-item.s+1)/7*100)", "((item.end-item.s+1)/7*100)")

    page = page.replace("e.eventTitle||e.title||'ライブ情報'", "e.eventTitle||e.title||'公演'")
    page = page.replace("+(r.synthetic?'今日から表示｜':'')+", "+")
    page = page.replace(
        "return r&&r.synthetic?'本日から帯表示（開始日時未取得）':fmt(e.applyStart)",
        "return r&&r.synthetic?'開始日時未取得':fmt(e.applyStart)",
    )
    page = page.replace(
        "開始日時は未取得のため、カレンダー上では今日から締切までを申込帯として表示しています。",
        "開始日時は未取得です。カレンダーの帯は今日から締切まで表示しています。",
    )
    page = page.replace("+' ／ ぴあ非FC・非アップグレードは全件採用'", "")

    # Display short multi-date venue schedules explicitly. Long tours stay summarized.
    if "function venueText(e)" not in page:
        needle = "function days(e){return occ(e).map(function(x){return x.date})}"
        venue_js = (
            "function venueText(e){if(online(e))return e.venue||'オンライン（SUKISUKI）';"
            "var rows=occ(e),seen={},clean=[];rows.forEach(function(r){var k=String(r.date||'')+'|'+String(r.venue||'');"
            "if(!seen[k]){seen[k]=1;clean.push(r)}});"
            "if(clean.length===1)return clean[0].venue||e.venue||'未定';"
            "if(clean.length>=2&&clean.length<=6)return clean.map(function(r){var dt=p(r.date);return(dt?sd(dt):String(r.date||''))+' '+(r.venue||'会場未定')}).join(' ／ ');"
            "if(clean.length>6)return e.venue||('複数会場（全'+clean.length+'公演）');return e.venue||'未定'}"
        )
        if needle not in page:
            raise RuntimeError("could not locate days() insertion point")
        page = page.replace(needle, venue_js + needle, 1)

    page = page.replace(
        "esc(e.venue||(on?'オンライン（SUKISUKI）':'未定'))",
        "esc(venueText(e))",
    )

    # A group has at most one live performance marker per date. Ticket rows and
    # schedule-only rows can describe the same performance; collapse them here.
    page = page.replace("var perf=[],bands=[],miles=[];", "var perf=[],bands=[],miles=[],perfSeen={};")
    plain_push = "perf.push({event:e,s:i,end:i})"
    dedup_push = (
        "var pk=String(e.group||'')+'|'+String(o.date||'').slice(0,10)+'|'+(online(e)?'online':'live'),"
        "ps=(family(e)==='ticket'?2:0)+(pia(e)?1:0),oldp=perfSeen[pk];"
        "if(!oldp){var pe={event:e,s:i,end:i,score:ps};perfSeen[pk]=pe;perf.push(pe)}"
        "else if(ps>oldp.score){oldp.event=e;oldp.score=ps}"
    )
    if dedup_push not in page:
        page = page.replace(plain_push, dedup_push)

    required = (
        'id="snapshot-data"',
        "function effectiveBand(e)",
        "function lane(items)",
        "function prepare(raw)",
        "function venueText(e)",
        "perfSeen[pk]",
        "FC先行・アップグレードを除いて原則すべて採用",
        "var e=item.event,b=document.createElement('button')",
        "ends[n]=x.end",
        "esc(venueText(e))",
    )
    missing = [token for token in required if token not in page]
    if missing:
        raise RuntimeError(f"schedule shell invariant missing: {missing}")

    forbidden = (
        "perf.push({e:e,s:i,e:i})",
        "var e=item.e,b=",
        "x.endnd",
        "今日から表示｜",
        "ライブ情報",
    )
    present = [token for token in forbidden if token in page]
    if present:
        raise RuntimeError(f"legacy/broken schedule shell tokens remain: {present}")

    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", page, re.S)
    executable = [s for s in scripts if "(function(){'use strict';" in s]
    if len(executable) != 1:
        raise RuntimeError(f"expected one executable inline script, found {len(executable)}")
    Path("/tmp/schedule-inline.js").write_text(executable[0], encoding="utf-8")

    PAGE.write_text(page, encoding="utf-8")
    print("Schedule shell checked and normalized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
