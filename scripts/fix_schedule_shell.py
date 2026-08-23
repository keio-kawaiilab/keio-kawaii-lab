#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

PAGE = Path("schedule.html")


def main() -> int:
    page = PAGE.read_text(encoding="utf-8")

    # Keep the standalone page wording user-facing and compact.
    page = page.replace(
        "チケットぴあ掲載の受付は、<strong>FC先行・アップグレードを除いて原則すべて採用</strong>します。開始日時が取れない場合も、締切が分かれば<strong>今日〜締切を申込帯</strong>として表示します。📱シマシマ＝オンライン特典会。",
        "チケットぴあ掲載の受付は、<strong>FC先行・アップグレードを除いて原則すべて採用</strong>します。開始日時が未取得でも、締切が分かる受付は<strong>今日〜締切を申込帯</strong>で表示します。📱シマシマ＝オンライン特典会。",
    )
    page = page.replace(
        "色＝グループ ／ 横帯＝申込期間（開始不明時は今日から） ／ 🎫＝当落 ／ 💳＝入金期限 ／ 🎤＝ライブ ／ 📱＝オンライン特典会",
        "色＝グループ ／ 横帯＝申込期間 ／ 🎫＝当落 ／ 💳＝入金期限 ／ 🎤＝ライブ ／ 📱＝オンライン特典会",
    )
    page = page.replace("本日から帯表示（開始日時未取得）", "開始日時未取得")

    # Strict-mode JavaScript must declare the computed week height.
    page = page.replace(
        "mbase=bbase+bl*44+10;height=mbase+ml*30+12;",
        "mbase=bbase+bl*44+10;var height=mbase+ml*30+12;",
    )

    # Critical collision bug: the old object literal used `e` for both the event
    # object and the numeric end column. JavaScript kept only the latter, which
    # caused gray fallback styling and the title `ライブ情報`.
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
    page = page.replace("ends[n]=x.e", "ends[n]=x.end")
    page = page.replace("var e=item.e,b=document.createElement('button')", "var e=item.event,b=document.createElement('button')")
    page = page.replace("((item.e-item.s+1)/7*100)", "((item.end-item.s+1)/7*100)")

    # No generic internal-looking label on the public calendar.
    page = page.replace("e.eventTitle||e.title||'ライブ情報'", "e.eventTitle||e.title||'公演'")

    # The band already starts from today visually when the source start is unknown;
    # do not clutter the band itself with implementation wording.
    page = page.replace(
        "esc(e.ticketType||'申込')+'｜'+(r.synthetic?'今日から表示｜':'')+esc(fmt(e.applyEnd))+'まで'",
        "esc(e.ticketType||'申込')+'｜'+esc(fmt(e.applyEnd))+'まで'",
    )
    page = page.replace(
        "return r&&r.synthetic?'本日から帯表示（開始日時未取得）':fmt(e.applyStart)",
        "return r&&r.synthetic?'開始日時未取得':fmt(e.applyStart)",
    )
    page = page.replace(
        "開始日時は未取得のため、カレンダー上では今日から締切までを申込帯として表示しています。",
        "開始日時は未取得です。カレンダーの帯は今日から締切まで表示しています。",
    )
    page = page.replace(
        "+' ／ ぴあ非FC・非アップグレードは全件採用'",
        "",
    )

    required = (
        'id="snapshot-data"',
        "function effectiveBand(e)",
        "function lane(items)",
        "function prepare(raw)",
        "FC先行・アップグレードを除いて原則すべて採用",
        "perf.push({event:e,s:i,end:i})",
        "var e=item.event,b=document.createElement('button')",
    )
    missing = [token for token in required if token not in page]
    if missing:
        raise RuntimeError(f"schedule shell invariant missing: {missing}")
    if "perf.push({e:e,s:i,e:i})" in page or "var e=item.e,b=" in page:
        raise RuntimeError("legacy duplicate-key calendar item bug is still present")

    # Extract the executable inline script for node --check in CI.
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
