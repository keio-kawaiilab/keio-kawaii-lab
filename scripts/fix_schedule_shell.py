#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

PAGE = Path("schedule.html")

PREFECTURE_JS = (
    "function prefecture(v){var s=String(v||''),m=s.match(/北海道|東京都|京都府|大阪府|青森県|岩手県|宮城県|秋田県|山形県|福島県|茨城県|栃木県|群馬県|埼玉県|千葉県|神奈川県|新潟県|富山県|石川県|福井県|山梨県|長野県|岐阜県|静岡県|愛知県|三重県|滋賀県|兵庫県|奈良県|和歌山県|鳥取県|島根県|岡山県|広島県|山口県|徳島県|香川県|愛媛県|高知県|福岡県|佐賀県|長崎県|熊本県|大分県|宮崎県|鹿児島県|沖縄県/);"
    "if(m){var x=m[0];return x==='北海道'?x:x.replace(/[都府県]$/,'')}"
    "var a=[[/SGCホール有明|SGC HALL ARIAKE|有明アリーナ|東京ガーデンシアター|日本武道館|ベルサール(?:汐留|渋谷)|LINE CUBE SHIBUYA|Zepp Haneda|Spotify O-/,'東京'],[/ぴあアリーナ\\s*MM|横浜アリーナ|パシフィコ横浜|カルッツかわさき|KT Zepp Yokohama/,'神奈川'],[/幕張メッセ|幕張新都心|森のホール21/,'千葉'],[/戸田市文化会館|大宮ソニックシティ/,'埼玉']];"
    "for(var i=0;i<a.length;i++)if(a[i][0].test(s))return a[i][1];return''}"
)

BAND_LOCATION_JS = (
    "function bandLocation(e){if(online(e))return'';var seen={},a=[];"
    "occ(e).forEach(function(o){var x=prefecture(o.venue||e.venue||'');if(x&&!seen[x]){seen[x]=1;a.push(x)}});"
    "if(!a.length){var x=prefecture(e.venue||'');if(x)a.push(x)}"
    "return a.length<=4?a.join('・'):(a[0]+'ほか'+(a.length-1)+'地域')}"
)

TITLE_JS = (
    "function title(e){var t=String(e.eventTitle||e.title||'').trim(),fb=(e.group||'KAWAII LAB.')+' 公演';"
    "if(!t||badTitle.test(t))return fb;var q=t.match(/「([^」]+)」/);if(q)return q[1].trim()||fb;"
    "t=t.replace(/^(?:20\\d{2}年)?\\d{1,2}月\\d{1,2}日(?:\\([^)]*\\)|（[^）]*）)?\\s*/,'');"
    "t=t.split(/\\s*@|開催決定|出演決定|アップグレード抽選受付|一般(?:発売|販売|先行)|FC\\s*(?:会員)?先行|ファンクラブ|OFFICIAL FANCLUB|プレリザーブ|プレイガイド|先行受付|チケット受付|受付のお知らせ/i)[0];"
    "return t.trim()||fb}"
)

DISCLAIMER_HTML = (
    '<aside class="schedule-disclaimer" aria-label="ご利用上の注意">'
    '<strong>⚠️ ご利用前にご確認ください</strong>'
    '<p>本ページは、各グループ公式サイト・チケットぴあ・ローチケ・イープラス・SUKISUKI等で一般公開されている情報をもとに、慶應義塾大学KAWAII LAB.同好会が独自に整理した<strong>非公式の情報ページ</strong>です。'
    '<br>当会から所属事務所・運営会社・出演者・会場・プレイガイド等へ、掲載内容の確認・監修依頼は行っておらず、これらの関係先による確認・承認を受けたものではありません。<strong>本ページに関するお問い合わせを各関係先へ行わないでください。</strong>'
    '<br>自動取得・整理を含むため、誤記・欠落・反映遅延・内容変更が生じる場合があります。申込・決済・来場前には、必ずリンク先の公式情報をご確認ください。法令上認められる範囲で、掲載内容の利用により生じた損害について当会は責任を負いかねます。</p>'
    '</aside>'
)


def main() -> int:
    page = PAGE.read_text(encoding="utf-8")

    if 'href="./train-status.css"' not in page:
        page = page.replace("<style>", '<link rel="stylesheet" href="./train-status.css">\n<style>', 1)
    if 'src="./train-status.js"' not in page:
        page = page.replace("</body>", '<script src="./train-status.js"></script>\n</body>', 1)

    if "schedule-home-link" not in page:
        page = page.replace(
            ".head small{display:block;margin-top:3px;color:var(--muted)}",
            ".head small{display:block;margin-top:3px;color:var(--muted)}.schedule-head-inner{max-width:980px;margin:auto;display:flex;align-items:center;justify-content:space-between;gap:14px}.schedule-home-link{flex:0 0 auto;text-decoration:none;background:var(--navy);color:#fff;border-radius:999px;padding:10px 14px;font-weight:800;font-size:13px;box-shadow:0 4px 14px #22335f2b}.schedule-home-link:hover{opacity:.9}@media(max-width:620px){.schedule-head-inner{align-items:flex-start}.schedule-home-link{padding:9px 11px;font-size:12px}}",
            1,
        )
        page = page.replace(
            '<header class="head"><b>KAWAII LAB.同好会</b><small>慶應義塾大学登録学生団体｜LIVE & TICKET</small></header>',
            '<header class="head"><div class="schedule-head-inner"><div><b>KAWAII LAB.同好会</b><small>慶應義塾大学登録学生団体｜LIVE & TICKET</small></div><a class="schedule-home-link" href="index.html">← 同好会公式サイト</a></div></header>',
            1,
        )

    if "schedule-disclaimer" not in page:
        page = page.replace(
            ".lead,.policy,.status{color:var(--muted);font-size:13px}",
            ".lead,.policy,.status{color:var(--muted);font-size:13px}.schedule-disclaimer{margin:12px 0 16px;padding:14px 16px;border:1px solid #ead79b;border-left:5px solid #c49d36;border-radius:12px;background:#fff8e6;color:#4f482f;font-size:12px;line-height:1.75}.schedule-disclaimer strong{color:#5a4715}.schedule-disclaimer>strong{display:block;font-size:13px;margin-bottom:4px}.schedule-disclaimer p{margin:0}",
            1,
        )
        lead = '<p class="lead">チケットぴあ掲載の受付は、<strong>FC先行・アップグレードを除いて原則すべて採用</strong>します。開始日時が未取得でも、締切が分かる受付は<strong>今日〜締切を申込帯</strong>で表示します。📱シマシマ＝オンライン特典会。</p>'
        if lead not in page:
            raise RuntimeError("could not locate schedule lead for disclaimer")
        page = page.replace(lead, lead + DISCLAIMER_HTML, 1)

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

    page = page.replace("esc(e.venue||(on?'オンライン（SUKISUKI）':'未定'))", "esc(venueText(e))")

    if "function prefecture(v)" not in page:
        needle = "function online(e){return e.eventCategory==='online-benefit'||/オンライン(?:特典会|サイン会)/.test(String(e.title||''))}"
        if needle not in page:
            raise RuntimeError("could not locate online() insertion point")
        page = page.replace(needle, needle + PREFECTURE_JS, 1)
    else:
        page = re.sub(
            r"function prefecture\(v\)\{var s=String\(v\|\|''\).*?return''\}",
            lambda _m: PREFECTURE_JS,
            page,
            count=1,
        )

    if "function bandLocation(e)" not in page:
        needle = "function days(e){return occ(e).map(function(x){return x.date})}"
        if needle not in page:
            raise RuntimeError("could not locate days() for bandLocation")
        page = page.replace(needle, BAND_LOCATION_JS + needle, 1)

    page = re.sub(
        r"function title\(e\)\{return String\(e\.eventTitle\|\|e\.title\|\|'公演'\)\.trim\(\)\}",
        lambda _m: TITLE_JS,
        page,
        count=1,
    )
    if TITLE_JS not in page and "function title(e)" in page:
        page = re.sub(
            r"function title\(e\)\{.*?\}(?=function shortTitle)",
            lambda _m: TITLE_JS,
            page,
            count=1,
            flags=re.S,
        )

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
    page = page.replace(
        "else if(kind==='band'){var r=item.band;b.innerHTML='<strong>'+esc(shortTitle(e))+'</strong><span>'+esc(e.ticketType||'申込')+'｜'+esc(fmt(e.applyEnd))+'まで</span>'}",
        "else if(kind==='band'){var r=item.band,loc=bandLocation(e);b.innerHTML='<strong>'+esc((loc?loc+'｜':'')+shortTitle(e))+'</strong><span>'+esc(e.ticketType||'申込')+'｜'+esc(fmt(e.applyEnd))+'まで</span>'}",
    )

    required = (
        'id="snapshot-data"',
        "schedule-home-link",
        'href="index.html"',
        "schedule-disclaimer",
        "本ページに関するお問い合わせを各関係先へ行わないでください。",
        "function effectiveBand(e)",
        "function lane(items)",
        "function prepare(raw)",
        "function venueText(e)",
        "function prefecture(v)",
        "function bandLocation(e)",
        "function groupedApplicationBands(vis)",
        "location:item.location",
        "cell.textContent=dt<start?'':sd(dt)",
        "dateAndTime=performanceDate(m.date)",
        "perfSeen[pk]",
        "item.prefecture?item.prefecture+'｜':''",
        "loc?loc+'｜':''",
        "KAWAII LAB. Christmas SESSION 2026",
        "FC先行・アップグレードを除いて原則すべて採用",
        "var e=item.event,b=document.createElement('button')",
        "ends[n]=x.end",
        "venueTextHtml(e)",
        "function providerId(e)",
        "function performanceModels(vis)",
        "data-performance-key",
        "providerName(e)+'｜'",
        ".cal{width:100%;min-width:0}",
        "ローチケ・イープラス",
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
        "東京都｜",
        "神奈川県｜",
        "大阪府｜",
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
    print("Schedule shell checked and normalized with navigation and disclaimer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
