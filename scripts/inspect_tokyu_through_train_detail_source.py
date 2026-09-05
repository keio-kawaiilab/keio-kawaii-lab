#!/usr/bin/env python3
"""Inspect Tokyu's current official-linked per-train timetable source.

The Tokyu website links users to transfer.navitime.biz/tokyu for timetable details.
A TrainRouteTimetable page publishes one physical train as one ordered stop list,
including through-running outside Tokyu when applicable. This inspector discovers
its backlink/listing structure without inferring identity from time, train number,
or destination similarity.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

SAMPLE = (
    "https://transfer.navitime.biz/tokyu/pc/diagram/TrainRouteTimetable"
    "?day=15&hour=07&kind=%E6%9D%B1%E6%80%A5%E6%9D%B1%E6%A8%AA%E7%B7%9A%E5%90%84%E5%81%9C"
    "&minutes=04&month=08&posType=1&rrCd=00000790&stCd=00007443&trCd=01ab0195&updown=0&year=2026"
)
OUT = Path("data/transit/fukutoshin/tokyu-through-source-report.json")
ALLOWED_HOST = "transfer.navitime.biz"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict] = []
        self._href: str | None = None
        self._text: list[str] = []
        self.title: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        amap = dict(attrs)
        if tag.lower() == "a" and amap.get("href"):
            self._href = amap["href"]
            self._text = []
        if tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.links.append({"href": self._href, "text": re.sub(r"\s+", " ", "".join(self._text)).strip()})
            self._href = None
            self._text = []
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)
        if self._in_title:
            self.title.append(data)


def curl(url: str) -> bytes:
    proc = subprocess.run(
        [
            "curl", "-fLsS", "--retry", "3", "--retry-delay", "1",
            "--connect-timeout", "15", "--max-time", "45",
            "-A", "Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/1.0)",
            "-H", "Accept: text/html,application/xhtml+xml,*/*;q=0.8",
            url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"curl failed ({proc.returncode}) for {url}: {proc.stderr.decode('utf-8','replace')[-500:]}")
    return proc.stdout


def decode(raw: bytes) -> str:
    for enc in ("utf-8", "cp932", "shift_jis"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def parse(url: str, raw: bytes) -> dict:
    text = decode(raw)
    parser = LinkParser()
    parser.feed(text)
    links = []
    for row in parser.links:
        absolute = urljoin(url, row["href"])
        if urlparse(absolute).hostname != ALLOWED_HOST:
            continue
        links.append({"url": absolute, "text": row["text"]})
    unique = []
    seen = set()
    for row in links:
        key = (row["url"], row["text"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return {
        "url": url,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "title": re.sub(r"\s+", " ", "".join(parser.title)).strip(),
        "links": unique,
        "trainRouteLinks": [r for r in unique if "TrainRouteTimetable" in r["url"]],
        "diagramLinks": [r for r in unique if "/diagram/" in r["url"]],
        "returnLinks": [r for r in unique if "時刻表" in r["text"] or "戻る" in r["text"]],
        "containsThroughStations": {name: (name in text) for name in ("横浜", "渋谷", "小竹向原", "練馬", "所沢")},
    }


def main() -> None:
    sample_raw = curl(SAMPLE)
    sample = parse(SAMPLE, sample_raw)

    # Inspect a very small set of same-host links that look like timetable/listing
    # back-links. Do not crawl the site recursively.
    candidate_urls = []
    for row in sample["returnLinks"] + sample["diagramLinks"]:
        url = row["url"]
        if "TrainRouteTimetable" in url or url == SAMPLE:
            continue
        if url not in candidate_urls:
            candidate_urls.append(url)
        if len(candidate_urls) >= 8:
            break

    candidates = []
    errors = []
    for url in candidate_urls:
        try:
            candidates.append(parse(url, curl(url)))
        except Exception as exc:
            errors.append({"url": url, "error": str(exc)})

    best = None
    for row in candidates:
        score = len(row["trainRouteLinks"])
        if best is None or score > best[0]:
            best = (score, row["url"])

    report = {
        "version": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "Tokyu official-linked timetable provider per-train route detail",
        "sampleTrainUrl": SAMPLE,
        "identityPolicy": {
            "singleTrainDetailPageMayEstablishIdentity": True,
            "timeProximityMayEstablishIdentity": False,
            "trainNumberAloneMayEstablishIdentity": False,
            "destinationAloneMayEstablishIdentity": False,
            "listingLinkAloneMayEstablishIdentity": False,
        },
        "sample": sample,
        "candidatePages": candidates,
        "errors": errors,
        "summary": {
            "sampleFetched": True,
            "sampleTitle": sample["title"],
            "sampleCrossesYokohamaShibuyaKotake": all(sample["containsThroughStations"].get(x) for x in ("横浜", "渋谷", "小竹向原")),
            "candidatePagesFetched": len(candidates),
            "maxTrainRouteLinksOnCandidate": best[0] if best else 0,
            "bestCandidateUrl": best[1] if best else "",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if not report["summary"]["sampleCrossesYokohamaShibuyaKotake"]:
        raise SystemExit("The retained sample did not expose the expected exact through stop sequence")


if __name__ == "__main__":
    main()
