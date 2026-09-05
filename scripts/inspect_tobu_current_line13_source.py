#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = 'https://transfer.navitime.biz/tokyu/pc/diagram/'
CURRENT_FOREST_PARK = BASE + 'TrainDiagram?rrCd=00000808&stCd=00004399&updown=0'
KNOWN_THROUGH = BASE + 'TrainRouteTimetable?day=09&hour=16&kind=%E6%9D%B1%E6%AD%A6%E6%9D%B1%E4%B8%8A%E7%B7%9A%E5%BF%AB%E9%80%9F%E6%80%A5%E8%A1%8C%E3%80%94F%E3%83%A9%E3%82%A4%E3%83%8A%E3%83%BC%E3%80%95&minutes=37&month=08&posType=1&rrCd=00000808&stCd=00005189&trCd=01bc0056&updown=0&year=2026'


def clean(value: str) -> str:
    return re.sub(r'\s+', ' ', value or '').strip()


def request(url: str) -> tuple[int, str, str]:
    try:
        r = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/6.2)',
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
        }, timeout=(20, 60), allow_redirects=True)
        r.encoding = r.apparent_encoding or r.encoding or 'utf-8'
        return r.status_code, r.url, r.text
    except Exception as exc:
        return 0, url, f'{type(exc).__name__}: {exc}'


def summarize(url: str) -> dict:
    status, final_url, text = request(url)
    row = {
        'url': url,
        'finalUrl': final_url,
        'status': status,
        'bytes': len(text.encode('utf-8', 'replace')),
    }
    if status != 200:
        row['sample'] = clean(text)[:800]
        return row
    soup = BeautifulSoup(text, 'html.parser')
    row['title'] = clean(soup.title.get_text(' ', strip=True) if soup.title else '')
    links = []
    for a in soup.find_all('a', href=True):
        href = urljoin(final_url, a['href'])
        if 'TrainRouteTimetable' in href:
            links.append({'url': href, 'text': clean(a.get_text(' ', strip=True))[:160]})
    uniq=[]; seen=set()
    for link in links:
        if link['url'] in seen: continue
        seen.add(link['url']); uniq.append(link)
    row['trainRouteLinks'] = uniq[:400]
    row['trainRouteLinkCount'] = len(uniq)
    page_text = clean(soup.get_text(' ', strip=True))
    row['currentDateMarkers'] = re.findall(r'2026年\d{1,2}月\d{1,2}日現在', page_text)[:4]
    row['stationHits'] = {name: name in page_text for name in ('森林公園','朝霞台','和光市','小竹向原','渋谷','横浜','元町・中華街')}
    row['sample'] = page_text[:1200]
    return row


def main() -> None:
    report = {
        'version': 1,
        'identityPolicy': {
            'sourceReachabilityMayEstablishIdentity': False,
            'singlePublishedTrainRoutePageMayEstablishIdentity': True,
            'timeProximityMayEstablishIdentity': False,
            'trainNumberAloneMayEstablishIdentity': False,
            'destinationAloneMayEstablishIdentity': False,
        },
        'currentStation': summarize(CURRENT_FOREST_PARK),
        'knownThroughTrain': summarize(KNOWN_THROUGH),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
