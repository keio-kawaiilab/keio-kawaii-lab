#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

PAGE = Path("schedule.html")

PREFECTURE_JS = (
    "function prefecture(v){var s=String(v||''),m=s.match(/北海道|東京都|京都府|大阪府|青森県|岩手県|宮城県|秋田県|山形県|福島県|茨城県|栃木県|群馬県|埼玉県|千葉県|神奈川県|新潟県|富山県|石川県|福井県|山梨県|長野県|岐阜県|静岡県|愛知県|三重県|滋賀県|兵庫県|奈良県|和歌山県|鳥取県|島根県|岡山県|広島県|山口県|徳島県|香川県|愛媛県|高知県|福岡県|佐賀県|長崎県|熊本県|大分県|宮崎県|鹿児島県|沖縄県/);"
    "if(m)return m[0];var a=[[/SGCホール有明|有明アリーナ|東京ガーデンシアター|日本武道館|ベルサール(?:汐留|渋谷)|LINE CUBE SHIBUYA|Zepp Haneda|Spotify O-/,'東京都'],[/ぴあアリーナMM|横浜アリーナ|パシフィコ横浜|カルッツかわさき|KT Zepp Yokohama/,'神奈川県'],[/幕張メッセ|幕張新都心|森のホール21/,'千葉県'],[/戸田市文化会館|大宮ソニックシティ/,'埼玉県']];"
    "for(var i=0;i<a.length;i++)if(a[i][0].test(s))return a[i][1];return''}"
)


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

    # Add a prefecture label to each physical live marker. Use the occurrence
    # venue so each date in a nationwide tour gets its own prefecture.
    if "function prefecture(v)" not in page:
        needle = "function online(e){return e.eventCategory==='online-benefit'||/オンライン(?:特典会|サイン会)/.test(String(e.title||''))}"
        if needle not in page:
            raise RuntimeError("could not locate online() insertion point")
        page = page.replace(needle, needle + PREFECTURE_JS, 1)

    # A group has at most one live performance marker per date. Ticket rows and
    # schedule-only rows can describe the same performance; collapse them here.
    page = page.replace("var perf=[],bands=[],miles=[];", "var perf=[],bands=[],miles=[],perfSeen={};")
    plain_push = "perf.push({event:e,s:i,end:i})"
    dedup_push = (
        "var pk=String(e.group||'')+'|'+String(o.date||'').slice(0,10)+'|'+(online(e)?'online':'live'),"
        "ps=(family(e)==='ticket'?2:0)+(pia(e)?1:0),oldp=perfSeen[pk];"
        "if(!oldp){var pe={event:e,s:i,end:i,score:ps,prefecture:online(e)?'':prefecture(o.venue||e.venue||'')};perfSeen[pk]=pe;perf.push(pe)}"
        "else if(ps>oldp.score){oldp.event=e;oldp.score=ps;oldp.prefecture=online(e)?'':(prefecture(o.venue||e.venue||'')||oldp.prefecture)}"
    )
    legacy_dedup = (
        "var pk=String(e.group||'')+'|'+String(o.date||'').slice(0,10)+'|'+(online(e)?'online':'live'),"
        "ps=(family(e)==='ticket'?2:0)+(pia(e)?1:0),oldp=perfSeen[pk];"
        "if(!oldp){var pe={event:e,s:i,end:i,score:ps};perfSeen[pk]=pe;perf.push(pe)}"
        "else if(ps>oldp.score){oldp.event=e;oldp.score=ps}"
    )
    if legacy_dedup in page:
        page = page.replace(legacy_dedup, dedup_push)
    elif dedup_push not in page:
        page = page.replace(plain_push, dedup_push)

    page = page.replace(
        "if(kind==='performance')b.textContent=(online(e)?'📱 ':'🎤 ')+shortTitle(e);",
        "if(kind==='performance')b.textContent=(online(e)?'📱 ':'🎤 ')+(item.prefecture?item.prefecture+'｜':'')+shortTitle(e);",
    )

    required = (
        'id="snapshot-data"',
        "function effectiveBand(e)",
        "function lane(items)",
        "function prepare(raw)",
        "function venueText(e)",
        "function prefecture(v)",
        "perfSeen[pk]",
        "item.prefecture?item.prefecture+'｜':''",
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
