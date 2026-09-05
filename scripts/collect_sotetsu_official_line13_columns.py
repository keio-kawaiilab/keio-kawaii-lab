#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pdfplumber
import requests

PDFS = [
    {'calendar':'weekday','direction':'up','url':'https://cdn.sotetsu.co.jp/media/2026/train/stations/download/timetable-01-260314-jE9.pdf'},
    {'calendar':'weekday','direction':'down','url':'https://cdn.sotetsu.co.jp/media/2026/train/stations/download/timetable-02-260314-L6y.pdf'},
    {'calendar':'holiday','direction':'up','url':'https://cdn.sotetsu.co.jp/media/2026/train/stations/download/timetable-03-260314-nS1.pdf'},
    {'calendar':'holiday','direction':'down','url':'https://cdn.sotetsu.co.jp/media/2026/train/stations/download/timetable-04-260314-uH2.pdf'},
]
HIYOSHI_ANCHORS=('自由が丘','日吉','新綱島')
SHINYOKOHAMA_ANCHORS=('新綱島','新横浜','羽沢横浜国大')
TIME_RE=re.compile(r'^\d{3,4}$')
SESSION=requests.Session()
SESSION.headers.update({'User-Agent':'Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/8.1)','Accept':'application/pdf,*/*;q=0.8'})

def norm(value:Any)->str:
    return re.sub(r'[\s\u3000]+','',str(value or '')).replace('ヶ','ケ')

def stable_id(*parts:Any)->str:
    raw=json.dumps(parts,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return 'sotetsu-official-column:'+hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]

def fetch_pdf(url:str)->bytes:
    r=SESSION.get(url,timeout=(20,90)); r.raise_for_status(); data=r.content
    if not data.startswith(b'%PDF'): raise RuntimeError(f'Official timetable did not return a PDF: {url}')
    return data

def group_rows(words:list[dict[str,Any]],tolerance:float=1.7)->list[dict[str,Any]]:
    ordered=sorted(words,key=lambda w:(float(w.get('top',0)),float(w.get('x0',0))))
    groups:list[list[dict[str,Any]]]=[]; ys:list[float]=[]
    for word in ordered:
        y=(float(word.get('top',0))+float(word.get('bottom',word.get('top',0))))/2
        candidates=[(abs(y-existing),i) for i,existing in enumerate(ys) if abs(y-existing)<=tolerance]
        if candidates:
            _,i=min(candidates); groups[i].append(word); n=len(groups[i]); ys[i]=((ys[i]*(n-1))+y)/n
        else:
            groups.append([word]); ys.append(y)
    out=[]
    for y,items in zip(ys,groups):
        items.sort(key=lambda w:float(w.get('x0',0)))
        out.append({'y':y,'text':''.join(str(w.get('text') or '') for w in items),'words':items})
    return sorted(out,key=lambda row:row['y'])

def time_cells(row:dict[str,Any]|None)->list[dict[str,Any]]:
    if not row:return[]
    cells=[]
    for word in row.get('words') or []:
        text=norm(word.get('text'))
        if not TIME_RE.fullmatch(text):continue
        value=int(text); hh,mm=divmod(value,100)
        if hh>29 or mm>59:continue
        x0=float(word.get('x0',0)); x1=float(word.get('x1',x0))
        cells.append({'text':text,'minute':hh*60+mm,'x':(x0+x1)/2})
    return sorted(cells,key=lambda cell:cell['x'])

def find_station_row(rows:list[dict[str,Any]],station:str)->dict[str,Any]|None:
    needle=norm(station); matches=[row for row in rows if needle in norm(row.get('text'))]
    if not matches:return None
    return max(matches,key=lambda row:(len(time_cells(row)),-len(norm(row.get('text')))))

def column_tolerance(cell_rows:list[list[dict[str,Any]]])->float:
    xs=sorted({round(float(c['x']),2) for cells in cell_rows for c in cells})
    gaps=sorted(b-a for a,b in zip(xs,xs[1:]) if 3.0<b-a<60.0)
    if not gaps:return 5.0
    median=gaps[len(gaps)//2]
    return max(2.0,min(6.0,median*0.30))

def common_columns(station_cells:dict[str,list[dict[str,Any]]],anchors:tuple[str,...])->list[dict[str,Any]]:
    if any(not station_cells.get(s) for s in anchors):return[]
    tolerance=column_tolerance([station_cells[s] for s in anchors])
    reference=min((station_cells[s] for s in anchors),key=len)
    out=[]; seen=set()
    for base in reference:
        matched={}
        for station in anchors:
            candidates=sorted(station_cells[station],key=lambda c:abs(float(c['x'])-float(base['x'])))
            if not candidates or abs(float(candidates[0]['x'])-float(base['x']))>tolerance:
                matched={};break
            matched[station]=candidates[0]
        if not matched:continue
        signature=tuple(int(round(float(matched[s]['x'])*10)) for s in anchors)
        if signature in seen:continue
        seen.add(signature)
        out.append({'columnX':round(sum(float(matched[s]['x']) for s in anchors)/len(anchors),2),'tolerance':round(tolerance,2),'times':{s:matched[s]['text'] for s in anchors},'minutes':{s:int(matched[s]['minute']) for s in anchors}})
    return sorted(out,key=lambda row:row['columnX'])

def orient_stops(direction:str,anchors:tuple[str,...])->list[str]:
    return list(reversed(anchors)) if direction=='up' else list(anchors)

def build_report()->dict[str,Any]:
    pdf_rows=[]; evidence=[]; diagnostics=[]; boundary_counts=Counter()
    for spec in PDFS:
        url=spec['url']; calendar=spec['calendar']; direction=spec['direction']; data=fetch_pdf(url)
        parsed_pages=0; local=Counter()
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            page_count=len(pdf.pages)
            if page_count<2:raise RuntimeError(f'Unexpected Sotetsu timetable page count: {page_count} {url}')
            for page_number,page in enumerate(pdf.pages,start=1):
                if page_number==1:continue
                words=page.extract_words(x_tolerance=1,y_tolerance=1,keep_blank_chars=False,use_text_flow=False)
                rows=group_rows(words)
                stations=set(HIYOSHI_ANCHORS+SHINYOKOHAMA_ANCHORS)
                station_rows={s:find_station_row(rows,s) for s in stations}
                station_cells={s:time_cells(row) for s,row in station_rows.items()}
                if not all(station_rows.values()):
                    if len(diagnostics)<20:diagnostics.append({'url':url,'page':page_number,'missingStations':[s for s,row in station_rows.items() if not row],'stationRowSamples':{s:(row or {}).get('text','') for s,row in station_rows.items()}})
                    continue
                parsed_pages+=1
                for boundary_id,anchors in (('toyoko-tokyushinyokohama-hiyoshi',HIYOSHI_ANCHORS),('tokyushinyokohama-sotetsushinyokohama-shinyokohama',SHINYOKOHAMA_ANCHORS)):
                    for column in common_columns(station_cells,anchors):
                        stops=orient_stops(direction,anchors)
                        if boundary_id=='toyoko-tokyushinyokohama-hiyoshi':
                            from_railway,to_railway=(('odpt.Railway:Tokyu.TokyuShinYokohama','odpt.Railway:Tokyu.Toyoko') if direction=='up' else ('odpt.Railway:Tokyu.Toyoko','odpt.Railway:Tokyu.TokyuShinYokohama'))
                        else:
                            from_railway,to_railway=(('odpt.Railway:Sotetsu.SotetsuShinYokohama','odpt.Railway:Tokyu.TokyuShinYokohama') if direction=='up' else ('odpt.Railway:Tokyu.TokyuShinYokohama','odpt.Railway:Sotetsu.SotetsuShinYokohama'))
                        row={'id':stable_id(url,page_number,column['columnX'],boundary_id,column['times']),'identityEvidence':'official-same-printed-column','status':'verified','canonicalBoundaryId':boundary_id,'calendar':calendar,'direction':direction,'sourceUrl':url,'pdfPage':page_number,'columnX':column['columnX'],'columnTolerance':column['tolerance'],'publishedBoundaryStops':stops,'printedTimes':column['times'],'fromRailway':from_railway,'toRailway':to_railway,'matchPolicy':{'officialSamePrintedColumnRequired':True,'exactPrintedStationTimesRequired':True,'timeProximityAloneMayEstablishIdentity':False,'trainNumberAloneMayEstablishIdentity':False,'destinationAloneMayEstablishIdentity':False}}
                        evidence.append(row); boundary_counts[boundary_id]+=1; local[boundary_id]+=1
        pdf_rows.append({'url':url,'calendar':calendar,'direction':direction,'bytes':len(data),'pageCount':page_count,'parsedTimetablePages':parsed_pages,'boundaryCounts':dict(local)})
    unique={row['id']:row for row in evidence}; evidence=sorted(unique.values(),key=lambda row:(row['calendar'],row['direction'],row['pdfPage'],row['columnX'],row['canonicalBoundaryId']))
    return {'version':1,'generatedAt':datetime.now(timezone.utc).isoformat(),'source':'Sotetsu official full train timetable PDFs effective 2026-03-14','officialEntryPage':'https://www.sotetsu.co.jp/train/stations/','identityPolicy':{'officialSamePrintedColumnMayEstablishIdentity':True,'exactPrintedStationTimesRequired':True,'timeProximityMayEstablishIdentity':False,'trainNumberAloneMayEstablishIdentity':False,'destinationAloneMayEstablishIdentity':False,'stationTimetableRowAloneMayEstablishIdentity':False},'pdfs':pdf_rows,'summary':{'pdfsFetched':len(pdf_rows),'evidenceRecords':len(evidence),'boundaryCounts':dict(boundary_counts),'diagnostics':len(diagnostics)},'authoritativeColumns':evidence,'diagnostics':diagnostics}

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--output',default='data/transit/fukutoshin/sotetsu-official-line13-columns.json'); args=ap.parse_args()
    report=build_report(); out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('SUMMARY',json.dumps(report['summary'],ensure_ascii=False,indent=2))
    for row in report['pdfs']:print('PDF',json.dumps(row,ensure_ascii=False))
    for row in report['authoritativeColumns'][:12]:print('SAMPLE',json.dumps(row,ensure_ascii=False))
    for row in report['diagnostics'][:8]:print('DIAGNOSTIC',json.dumps(row,ensure_ascii=False))
    counts=report['summary']['boundaryCounts']
    if int(counts.get('toyoko-tokyushinyokohama-hiyoshi',0))<1:raise RuntimeError('No exact Toyoko <-> Tokyu Shin-Yokohama same-column evidence was extracted')
    if int(counts.get('tokyushinyokohama-sotetsushinyokohama-shinyokohama',0))<1:raise RuntimeError('No exact Tokyu <-> Sotetsu Shin-Yokohama same-column evidence was extracted')
    return 0
if __name__=='__main__':raise SystemExit(main())
