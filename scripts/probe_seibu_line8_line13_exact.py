#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = 'https://seibu.ekitan.com'
SOURCE_PAGES = [
    f'{BASE}/norikae/timetable/station/232-1/d1?dw=0',
    f'{BASE}/norikae/timetable/station/232-1/d1?dw=1',
    f'{BASE}/norikae/timetable/station/232-1/d2?dw=0',
    f'{BASE}/norikae/timetable/station/232-1/d2?dw=1',
]
ONE_TRAIN_CALL_RE = re.compile(
    r"openOneTrainTimetable\(\s*['\"]([^'\"]+)['\"]\s*,\s*"
    r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*"
    r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)", re.I,
)
YURAKUCHO_MARKERS = {
    '東池袋','護国寺','江戸川橋','飯田橋','市ケ谷','市ヶ谷','麹町','永田町','桜田門',
    '有楽町','銀座一丁目','新富町','月島','豊洲','辰巳','新木場',
}
FUKUTOSHIN_MARKERS = {
    '雑司が谷','西早稲田','東新宿','新宿三丁目','北参道','明治神宮前','明治神宮前〈原宿〉','渋谷',
}
SEIBU_YURAKUCHO_SIDE = {'新桜台','練馬'}
SEIBU_IKEBUKURO_WEST = {
    '中村橋','富士見台','練馬高野台','石神井公園','大泉学園','保谷','ひばりヶ丘','東久留米',
    '清瀬','秋津','所沢','西所沢','小手指','狭山ヶ丘','武蔵藤沢','稲荷山公園','入間市','仏子','元加治','飯能',
}
SOUTH_PATTERNS = {
    'metro-tokyu-shibuya': (
        ('明治神宮前','渋谷','代官山'),('明治神宮前〈原宿〉','渋谷','代官山'),
        ('代官山','渋谷','明治神宮前'),('代官山','渋谷','明治神宮前〈原宿〉'),
    ),
    'tokyu-minatomirai-yokohama': (('反町','横浜','新高島'),('新高島','横浜','反町')),
}
SESSION = requests.Session()
SESSION.headers.update({'User-Agent':'Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/10.0)','Accept':'text/html,application/xhtml+xml,*/*;q=0.8'})


def clean(v: Any) -> str:
    return re.sub(r'\s+', ' ', str(v or '')).strip()


def fetch(url: str) -> str:
    r = SESSION.get(url, timeout=(20,60)); r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding or 'utf-8'
    return r.text


def one_train_url(tx: str, sf: str, date: str, time: str, dw: str) -> str:
    return f"{BASE}/norikae/timetable/onetraintimetable/?{urlencode({'date':date,'dw':dw,'sf':sf,'time':time,'tx':tx})}"


def metadata(url: str) -> dict[str,str]:
    q=parse_qs(urlparse(url).query)
    return {k:(q.get(k) or [''])[0] for k in ('date','dw','sf','time','tx')}


def discover(source_url: str, text: str) -> list[str]:
    soup=BeautifulSoup(text,'html.parser'); urls=[]
    for tx,sf,date,time,dw in ONE_TRAIN_CALL_RE.findall(text): urls.append(one_train_url(tx,sf,date,time,dw))
    for tag in soup.find_all(['a','form']):
        target=tag.get('href') or tag.get('action') or ''
        if 'onetraintimetable' in target: urls.append(urljoin(source_url,html.unescape(target)))
    out=[]; seen=set()
    for url in urls:
        if url.startswith(BASE+'/norikae/timetable/onetraintimetable') and url not in seen:
            seen.add(url); out.append(url)
    return out


def branch_of(names: list[str]) -> tuple[str,list[str]]:
    s=set(names); y=sorted(s&YURAKUCHO_MARKERS); f=sorted(s&FUKUTOSHIN_MARKERS)
    if y and not f: return 'yurakucho',y
    if f and not y: return 'fukutoshin',f
    if y and f: return 'conflict',sorted(set(y+f))
    return 'ambiguous',[]


def closest_span(names: list[str], left: set[str], right: set[str], boundary: str,
                 left_rw: str, right_rw: str) -> dict[str,Any] | None:
    lh=[(i,n) for i,n in enumerate(names) if n in left]
    rh=[(i,n) for i,n in enumerate(names) if n in right]
    if not lh or not rh: return None
    _,li,ln,ri,rn=min((abs(li-ri),li,ln,ri,rn) for li,ln in lh for ri,rn in rh)
    if li==ri: return None
    return {
        'proofType':'same-published-one-train-page+verified-unique-route-span',
        'boundaryStation':boundary,
        'fromRailway':left_rw if li<ri else right_rw,
        'toRailway':right_rw if li<ri else left_rw,
        'publishedLeftMarker':ln,'publishedRightMarker':rn,
        'publishedLeftMarkerIndex':li,'publishedRightMarkerIndex':ri,
        'publishedSideMarkers':[ln,rn],
        'adjacentPublishedBoundaryStopsRequired':False,
        'verifiedUniqueRouteSpanRequired':True,
    }


def adjacent(names: list[str], pattern: tuple[str,...]) -> bool:
    return any(tuple(names[i:i+len(pattern)])==pattern for i in range(max(0,len(names)-len(pattern)+1)))


def parse_detail(url: str, text: str) -> dict[str,Any]:
    soup=BeautifulSoup(text,'html.parser'); stops=[]
    for tr in soup.find_all('tr'):
        cells=[clean(c.get_text(' ',strip=True)) for c in tr.find_all(['th','td'])]
        if len(cells)<3 or cells[0] in {'駅','駅名','着時刻','発時刻'}: continue
        if not cells[0]: continue
        joined=' '.join(cells[1:])
        if re.search(r'\d{1,2}:\d{2}',joined) or 'レ' in joined or any(c=='' for c in cells[1:3]):
            stops.append({'station':cells[0],'arrival':cells[1],'departure':cells[2]})
    names=[r['station'] for r in stops]; name_set=set(names); branch,markers=branch_of(names)
    boundaries=[]; proofs={}
    if branch in {'yurakucho','fukutoshin'}:
        metro=YURAKUCHO_MARKERS if branch=='yurakucho' else FUKUTOSHIN_MARKERS
        metro_rw='odpt.Railway:TokyoMetro.Yurakucho' if branch=='yurakucho' else 'odpt.Railway:TokyoMetro.Fukutoshin'
        if '小竹向原' in name_set:
            p=closest_span(names,metro,SEIBU_YURAKUCHO_SIDE,'小竹向原',metro_rw,'odpt.Railway:Seibu.SeibuYurakucho')
            if p:
                bid=f'{branch}-seibu-kotake-mukaihara'; boundaries.append(bid); proofs[bid]=p
        # IMPORTANT: the left marker set can contain Metro stations, but the
        # operational boundary being proved is SeibuYurakucho <-> Ikebukuro at
        # Nerima. Keep the original east/west marker indexes; do not reorder and
        # then infer direction from the reordered values.
        east=metro|{'小竹向原','新桜台'}
        p=closest_span(names,east,SEIBU_IKEBUKURO_WEST,'練馬','odpt.Railway:Seibu.SeibuYurakucho','odpt.Railway:Seibu.Ikebukuro')
        if p:
            bid='seibuyurakucho-ikebukuro-nerima'; boundaries.append(bid); proofs[bid]=p
    for bid,patterns in SOUTH_PATTERNS.items():
        match=next((pat for pat in patterns if adjacent(names,pat)),None)
        if not match: continue
        if branch!='fukutoshin': raise RuntimeError(f'Line 13 south boundary without Fukutoshin marker: {url}')
        boundaries.append(bid)
        proofs[bid]={'proofType':'same-published-one-train-page+adjacent-published-boundary-stops','publishedSideMarkers':list(match),'adjacentPublishedBoundaryStopsRequired':True,'verifiedUniqueRouteSpanRequired':False}
    return {
        'url':url,'sourceParameters':metadata(url),'title':clean(soup.title.get_text(' ',strip=True) if soup.title else ''),
        'headings':[clean(x.get_text(' ',strip=True)) for x in soup.find_all(['h1','h2','h3'])][:8],
        'stops':stops,'stationCount':len(stops),'metroBranch':branch,'metroBranchPublishedMarkers':markers,
        'boundaries':boundaries,'boundaryProofs':proofs,'identityEvidence':'single-published-one-train-page',
    }


def build_report() -> dict[str,Any]:
    source_rows=[]; urls=[]; seen=set()
    for source in SOURCE_PAGES:
        try:
            text=fetch(source); found=discover(source,text)
            source_rows.append({'url':source,'fetched':True,'bytes':len(text.encode()),'detailUrlCount':len(found)})
            for url in found:
                if url not in seen: seen.add(url); urls.append(url)
        except Exception as exc: source_rows.append({'url':source,'fetched':False,'error':f'{type(exc).__name__}: {exc}'})
    rows=[]; errors=[]
    with ThreadPoolExecutor(max_workers=12) as pool:
        jobs={pool.submit(fetch,url):url for url in urls}
        for job in as_completed(jobs):
            url=jobs[job]
            try: rows.append(parse_detail(url,job.result()))
            except Exception as exc: errors.append({'url':url,'error':f'{type(exc).__name__}: {exc}'})
    rows.sort(key=lambda r:r['url']); exact=[r for r in rows if r['boundaries']]
    ids=['yurakucho-seibu-kotake-mukaihara','fukutoshin-seibu-kotake-mukaihara','seibuyurakucho-ikebukuro-nerima','metro-tokyu-shibuya','tokyu-minatomirai-yokohama']
    bc={bid:sum(bid in r['boundaries'] for r in exact) for bid in ids}
    branches={k:sum(r['metroBranch']==k for r in rows) for k in ('yurakucho','fukutoshin','ambiguous','conflict')}
    kotake={k:sum(r['metroBranch']==k and f'{k}-seibu-kotake-mukaihara' in r['boundaries'] for r in rows) for k in ('yurakucho','fukutoshin')}
    nerima_dir={'seibuyurakucho-to-ikebukuro':0,'ikebukuro-to-seibuyurakucho':0}
    for r in exact:
        p=r['boundaryProofs'].get('seibuyurakucho-ikebukuro-nerima')
        if not p: continue
        if p['fromRailway']=='odpt.Railway:Seibu.SeibuYurakucho': nerima_dir['seibuyurakucho-to-ikebukuro']+=1
        elif p['fromRailway']=='odpt.Railway:Seibu.Ikebukuro': nerima_dir['ikebukuro-to-seibuyurakucho']+=1
    return {
        'version':10,'generatedAt':datetime.now(timezone.utc).isoformat(),
        'source':'Seibu Railway official-linked timetable service / one-train timetable pages',
        'officialEntryEvidence':'https://www.seiburailway.jp/railway/station/shin-sakuradai/timetable/',
        'identityPolicy':{'singlePublishedOneTrainPageMayEstablishIdentity':True,'samePublishedTrainPageWithVerifiedUniqueRouteSpanMayEstablishInternalBoundary':True,'metroLineRequiresPublishedRouteSpecificStation':True,'ambiguousMetroBranchMayEstablishLineIdentity':False,'timeProximityMayEstablishIdentity':False,'trainNumberAloneMayEstablishIdentity':False,'destinationAloneMayEstablishIdentity':False},
        'summary':{'sourcePagesFetched':sum(bool(r.get('fetched')) for r in source_rows),'discoveredTrainDetailUrls':len(urls),'trainDetailPagesFetched':len(rows),'exactThroughTrainPages':len(exact),'metroBranchCounts':branches,'branchKotakeCounts':kotake,'boundaryCounts':bc,'nerimaDirectionCounts':nerima_dir,'errors':len(errors)},
        'sourcePages':source_rows,'authoritativeThroughTrains':exact,'detailErrors':errors,
    }


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--output',default='data/transit/line8-line13/seibu-official-exact-through-trains.json'); args=ap.parse_args()
    report=build_report(); out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('SUMMARY',json.dumps(report['summary'],ensure_ascii=False,indent=2))
    s=report['summary']
    if s['sourcePagesFetched']!=4 or s['trainDetailPagesFetched']<=0 or s['errors']!=0: raise RuntimeError('Current Seibu one-train collection incomplete')
    if s['metroBranchCounts']['conflict']!=0: raise RuntimeError('Conflicting Metro branch marker detected')
    for b in ('yurakucho','fukutoshin'):
        if s['branchKotakeCounts'][b]!=s['metroBranchCounts'][b]: raise RuntimeError(f'Not every {b} train classified at Kotake')
    total=s['metroBranchCounts']['yurakucho']+s['metroBranchCounts']['fukutoshin']
    if s['boundaryCounts']['seibuyurakucho-ikebukuro-nerima']!=total: raise RuntimeError('Not every Line 8/13 Seibu through page classified at Nerima')
    if not all(v>0 for v in s['nerimaDirectionCounts'].values()): raise RuntimeError(f'Nerima exact evidence not bidirectional: {s["nerimaDirectionCounts"]}')
    return 0

if __name__=='__main__': raise SystemExit(main())
