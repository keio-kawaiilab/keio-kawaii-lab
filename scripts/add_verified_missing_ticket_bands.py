#!/usr/bin/env python3
"""Install ticket bands verified on 2026-09-22.

The Lawson collector was timing out, so these rows preserve the verified direct
sales pages in the normal acquisition-row format.  The script is intentionally
idempotent so it can be replayed after a collector refresh if necessary.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


DATA_PATH = Path("data/live-events.json")
JST = ZoneInfo("Asia/Tokyo")
LEGACY_LAWSON_PLACEHOLDER_ID = "1d39bd5dbf1e137a"
TOUR_URL = "https://candytune.asobisystem.com/feature/candytune_nationwide_tour2026"


def stable_id(row: dict) -> str:
    parts = (
        row["group"],
        row["eventDate"],
        row["title"],
        row["ticketType"],
        row["ticketProvider"],
        row["url"],
    )
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def ticket_row(*, now: str, **values) -> dict:
    row = {
        "resultDate": None,
        "paymentEnd": None,
        "openTime": None,
        "startTime": None,
        "sourceType": "manual-verified",
        "sourceCandidates": [values["ticketProvider"]],
        "applicationWindowVerified": True,
        "deadlineVerified": True,
        "applicationDisplayMode": "band",
        "applicationWindowSource": values["url"],
        "deadlineSource": values["url"],
        "sourceObservedAt": now,
        **values,
    }
    row["urls"] = list(dict.fromkeys([row["url"], *(row.get("urls") or [])]))
    row["id"] = stable_id(row)
    return row


def verified_rows(now: str) -> list[dict]:
    candy_official = "https://candytune.asobisystem.com/feature/candytune_nationwide_tour2026"
    maguro_url = (
        "https://l-tike.com/order/?gBaseVenueCd=49216&gCarrierCd=08&gEntryMthd=02"
        "&gLcode=73933&gPfKey=20260708000002246943%2C20260708000002246935"
        "&gPfName=%E3%83%9E%E3%82%B0%E3%83%AD%E3%83%83%E3%82%AF%EF%BC%86"
        "%E3%83%9D%E3%83%83%E3%83%97%E3%80%80%EF%BC%92%EF%BC%90%EF%BC%92"
        "%EF%BC%96&gScheduleNo=3"
    )
    chikappa_url = (
        "https://l-tike.com/order/?gBaseVenueCd=81158&gCarrierCd=08&gEntryMthd=02"
        "&gLcode=82718&gPfKey=20260902000002288974"
        "&gPfName=%E3%81%A1%E3%81%8B%E3%81%A3%E3%81%B1%E7%A5%AD%EF%BC%92"
        "%EF%BC%90%EF%BC%92%EF%BC%96&gScheduleNo=2"
    )
    happiness_url = (
        "https://l-tike.com/order/?gBaseVenueCd=81620&gCarrierCd=08&gEntryMthd=02"
        "&gLcode=82218&gPfKey=20260820000002275623"
        "&gPfName=%E9%95%B7%E5%B4%8E%E3%82%B9%E3%82%BF%E3%82%B8%E3%82%A2"
        "%E3%83%A0%E3%82%B7%E3%83%86%E3%82%A3%E9%96%8B%E6%A5%AD%EF%BC%92"
        "%E5%91%A8%E5%B9%B4%E8%A8%98%E5%BF%B5%E3%80%80%E3%80%8C%EF%BC%A8"
        "%EF%BC%A1%EF%BC%B0%EF%BC%B0%EF%BC%A9%EF%BC%AE%EF%BC%A5%EF%BC%B3"
        "%EF%BC%B3%E3%80%80%EF%BC%AA%EF%BC%A1%EF%BC%AD%E3%80%80%EF%BC%92"
        "%EF%BC%90%EF%BC%92%EF%BC%96%E3%80%8D&gScheduleNo=3"
    )

    rows = [
        ticket_row(
            now=now,
            group="KAWAII LAB.合同",
            participants=["FRUITS ZIPPER", "CANDY TUNE", "SWEET STEADY", "CUTIE STREET", "MORE STAR"],
            title="KAWAII LAB. COLLECTION produced by TGC ~KAWAIIっちゃ in KITAKYUSHU~",
            eventTitle="KAWAII LAB. COLLECTION produced by TGC ~KAWAIIっちゃ in KITAKYUSHU~",
            ticketType="アップグレードチケット第2弾（抽選）",
            ticketProvider="official",
            applyStart="2026-09-18T18:00",
            applyEnd="2026-09-23T23:59",
            eventDate="2026-10-12",
            venue="北九州メッセ(〒802-0001 福岡県北九州市小倉北区浅野3-8-1)",
            openTime="14:00",
            startTime="16:00",
            url="https://kawaiilab.asobisystem.com/news/detail/89950",
            urls=["https://kawaiilab.asobisystem.com/news/detail/87217"],
            sourceType="official-news",
            sourceChannel="recent-official-body",
            sourcePublishedAt="2026-09-18",
            discoverySourceUrl="https://kawaiilab.asobisystem.com/news/detail/89950",
            primarySource="official",
            applicationStatus="open",
            eventScope="external",
            eventScopeCorrectionId="P2-external-kawacolle-tgc",
            eventScopeSource="verified-organizer",
            eventScopeSourceUrl="https://tgc.girlswalker.com/kawacolle/",
            organizer="KAWAII LAB. COLLECTION実行委員会",
        ),
        ticket_row(
            now=now,
            group="CANDY TUNE",
            title="CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            eventTitle="CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            ticketType="一般発売（先着）",
            ticketProvider="lawson",
            applyStart="2026-09-05T10:00",
            applyEnd="2026-10-08T23:59",
            eventDate="2026-10-08",
            venue="宮城県 仙台サンプラザホール",
            openTime="17:30",
            startTime="18:30",
            url="https://l-tike.com/order/?gBaseVenueCd=26694&gCarrierCd=08&gEntryMthd=02&gLcode=21640&gPfKey=20260803000002265622&gScheduleNo=1",
            urls=[candy_official],
            primarySource="lawson",
            applicationStatus="open",
            eventScope="kawaii-lab",
            officialTourUrl=TOUR_URL,
            officialScheduleUrl=TOUR_URL,
            performanceMatchedToOfficial=True,
        ),
        ticket_row(
            now=now,
            group="CANDY TUNE",
            title="LIVEAZUMA 2026",
            eventTitle="LIVEAZUMA 2026",
            ticketType="一般発売（先着）",
            ticketProvider="lawson",
            applyStart="2026-08-29T10:00",
            applyEnd="2026-10-06T22:00",
            eventDate="2026-10-17",
            venue="福島県 福島あづま球場/あづま総合運動公園",
            url="https://l-tike.com/order/?gLcode=29000",
            urls=["https://candytune.asobisystem.com/live_information/detail/45207"],
            primarySource="lawson",
            applicationStatus="open",
            eventScope="external",
            officialScheduleUrl="https://candytune.asobisystem.com/live_information/detail/45207",
        ),
        ticket_row(
            now=now,
            group="CANDY TUNE",
            title="「atmoscon 2026」-夜- 3rd LIVE STAGE",
            eventTitle="「atmoscon 2026」-夜- 3rd LIVE STAGE",
            ticketType="一般発売（先着）",
            ticketProvider="lawson",
            applyStart="2026-08-20T10:00",
            applyEnd="2026-10-30T23:59",
            eventDate="2026-11-01",
            venue="東京都 新宿住友ビル三角広場",
            url="https://l-tike.com/order/?gBaseVenueCd=35489&gCarrierCd=08&gEntryMthd=02&gLcode=34897&gPfKey=20260731000002263521%2C20260731000002263519%2C20260731000002263520&gScheduleNo=18",
            urls=["https://candytune.asobisystem.com/live_information/detail/43493"],
            primarySource="lawson",
            applicationStatus="open",
            eventScope="external",
            officialScheduleUrl="https://candytune.asobisystem.com/live_information/detail/43493",
        ),
        ticket_row(
            now=now,
            group="CANDY TUNE",
            title="CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            eventTitle="CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            ticketType="一般発売（先着）",
            ticketProvider="lawson",
            applyStart="2026-09-19T10:00",
            applyEnd="2026-11-12T23:00",
            eventDate="2026-11-17",
            venue="新潟県 新潟県民会館",
            openTime="17:30",
            startTime="18:30",
            url="https://l-tike.com/order/?gBaseVenueCd=36839&gCarrierCd=08&gEntryMthd=02&gLcode=70492&gPfKey=20260803000002265589&gScheduleNo=2",
            urls=[candy_official],
            primarySource="lawson",
            applicationStatus="open",
            eventScope="kawaii-lab",
            officialTourUrl=TOUR_URL,
            officialScheduleUrl=TOUR_URL,
            performanceMatchedToOfficial=True,
        ),
        ticket_row(
            now=now,
            group="CANDY TUNE",
            title="CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            eventTitle="CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            ticketType="一般発売（先着）",
            ticketProvider="lawson",
            applyStart="2026-09-19T10:00",
            applyEnd="2026-11-12T22:00",
            eventDate="2026-11-19",
            venue="石川県 本多の森北電ホール",
            openTime="17:30",
            startTime="18:30",
            url="https://l-tike.com/order/?gBaseVenueCd=51230&gCarrierCd=08&gEntryMthd=02&gLcode=53526&gPfKey=20260804000002266658&gScheduleNo=1",
            urls=[candy_official],
            primarySource="lawson",
            applicationStatus="open",
            eventScope="kawaii-lab",
            officialTourUrl=TOUR_URL,
            officialScheduleUrl=TOUR_URL,
            performanceMatchedToOfficial=True,
        ),
        ticket_row(
            now=now,
            group="CANDY TUNE",
            title="CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            eventTitle="CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            ticketType="プレリク先行（抽選）",
            ticketProvider="lawson",
            applyStart="2026-09-04T12:00",
            applyEnd="2026-09-23T23:59",
            resultDate="2026-09-25T15:00",
            eventDate="2026-11-30",
            venue="福岡県 福岡サンパレス",
            openTime="17:30",
            startTime="18:30",
            url="https://l-tike.com/order/?gBaseVenueCd=84423&gCarrierCd=08&gEntryMthd=03&gLcode=93496&gPfKey=20260814000002271718&gScheduleNo=2",
            urls=[candy_official],
            primarySource="lawson",
            applicationStatus="open",
            eventScope="kawaii-lab",
            officialTourUrl=TOUR_URL,
            officialScheduleUrl=TOUR_URL,
            performanceMatchedToOfficial=True,
        ),
        ticket_row(
            now=now,
            group="CANDY TUNE",
            title="CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            eventTitle="CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",
            ticketType="プレリク先行（抽選）",
            ticketProvider="lawson",
            applyStart="2026-09-04T12:00",
            applyEnd="2026-09-23T23:59",
            resultDate="2026-09-25T15:00",
            eventDate="2026-12-01",
            venue="大分県 大分iichikoグランシアタ",
            openTime="17:30",
            startTime="18:30",
            url="https://l-tike.com/order/?gBaseVenueCd=88097&gCarrierCd=08&gEntryMthd=03&gLcode=93496&gPfKey=20260814000002271719&gScheduleNo=2",
            urls=[candy_official],
            primarySource="lawson",
            applicationStatus="open",
            eventScope="kawaii-lab",
            officialTourUrl=TOUR_URL,
            officialScheduleUrl=TOUR_URL,
            performanceMatchedToOfficial=True,
        ),
    ]

    for day, open_time in (("2026-10-03", None), ("2026-10-04", "10:00")):
        rows.append(ticket_row(
            now=now,
            group="SWEET STEADY",
            title="マグロック&ポップ 2026",
            eventTitle="マグロック&ポップ 2026",
            ticketType="一般発売（先着）",
            ticketProvider="lawson",
            applyStart="2026-08-29T10:00",
            applyEnd="2026-09-24T23:00",
            eventDate=day,
            venue="清水マリンパーク",
            openTime=open_time,
            startTime="11:00",
            url=maguro_url,
            primarySource="lawson",
            applicationStatus="open",
            eventScope="external",
        ))

    rows.extend([
        ticket_row(
            now=now,
            group="MORE STAR",
            title="ちかっぱ祭 2026",
            eventTitle="ちかっぱ祭 2026",
            ticketType="一般発売（先着）",
            ticketProvider="lawson",
            applyStart="2026-09-05T12:00",
            applyEnd="2026-10-23T23:59",
            eventDate="2026-11-23",
            venue="マリンメッセ福岡B館",
            openTime="10:00",
            startTime="11:00",
            url=chikappa_url,
            urls=["https://kawaiilab.asobisystem.com/live_information/detail/43936"],
            primarySource="lawson",
            applicationStatus="open",
            eventScope="external",
            officialScheduleUrl="https://kawaiilab.asobisystem.com/live_information/detail/43936",
        ),
        ticket_row(
            now=now,
            group="SWEET STEADY",
            title="長崎スタジアムシティ開業2周年記念 「HAPPINESS JAM 2026」",
            eventTitle="長崎スタジアムシティ開業2周年記念 「HAPPINESS JAM 2026」",
            ticketType="一般発売（先着）",
            ticketProvider="lawson",
            applyStart="2026-09-23T10:00",
            applyEnd="2026-10-08T23:00",
            eventDate="2026-10-17",
            venue="HAPPINESS ARENA",
            openTime="13:00",
            startTime="14:00",
            url=happiness_url,
            urls=["https://sweetsteady.asobisystem.com/live_information/detail/44459"],
            primarySource="lawson",
            applicationStatus="upcoming",
            eventScope="external",
            officialScheduleUrl="https://sweetsteady.asobisystem.com/live_information/detail/44459",
        ),
    ])
    return rows


def main() -> int:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    events = [
        row for row in payload.get("events", [])
        if isinstance(row, dict) and row.get("id") != LEGACY_LAWSON_PLACEHOLDER_ID
    ]
    now = datetime.now(JST).isoformat(timespec="seconds")
    rows = verified_rows(now)
    replacements = {row["id"]: row for row in rows}
    events = [replacements.pop(row.get("id"), row) for row in events]
    events.extend(replacements.values())
    payload["events"] = events
    payload["checkedAt"] = now
    payload["updatedAt"] = now
    payload.pop("publicEvents", None)
    payload.pop("publicEventModelReport", None)
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"installed": len(rows), "removedLegacyPlaceholder": True, "updatedAt": now}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
