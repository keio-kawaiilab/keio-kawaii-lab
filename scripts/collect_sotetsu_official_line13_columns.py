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

PDFS=[
 {'calendar':'weekday','direction':'up','url':'https://cdn.sotetsu.co.jp/media/2026/train/stations/download/timetable-01-260314-jE9.pdf'},
 {'calendar':'weekday','direction':'down','url':'https://cdn.sotetsu.co.jp/media/2026/train/stations/download/timetable-02-260314-L6y.pdf'},
 {'calendar':'holiday','direction':'up','url':'https://cdn.sotetsu.co.jp/media/2026/train/stations/download/timetable-03-260314-nS1.pdf'},
 {'calendar':'holiday','direction':'down','url':'https://cdn.sotetsu.co.jp/media/2026/train/stations/download/timetable-04-260314-uH2.pdf'},
]
HIYOSHI_ANCHORS=('自由が丘','日吉','新綱島')
SHINYOKOHAMA_ANCHORS=('新綱島','新横浜','羽沢横浜国大')
TIME_RE=re.compile(r'^\d{3,4}$')
SESSION=requests.Session(); SESSION.headers.update({'User-Agent':'Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/8.3)','Accept':'application/pdf,*/*;q=0.8'})

def norm(v:Any)->str:return re.sub(r'[\s\u3000]+','',str(v or '')).replace('ヶ','ケ')
def stable_id(*parts:Any)->str:
 raw=json.dumps(parts,ensure_ascii=False,sort_keys=True,separators=(',',':')); return 'sotetsu-official-column:'+hashlib.sha256(raw.encode()).hexdigest()[:24]
def fetch_pdf(url:str)->bytes:
 r=SESSION.get(url,timeout=(20,90)); r.raise_for_status(); data=r.content
 if not data.startswith(b'%PDF'):raise RuntimeError(f'Not a PDF: {url}')
 return data

def group_rows(words:list[dict[str,Any]],tol:float=1.7)->list[dict[str,Any]]:
 groups=[]; ys=[]
 for w in sorted(words,key=lambda x:(float(x.get('top',0)),float(x.get('x0',0)))):
  y=(float(w.get('top',0))+float(w.get('bottom',w.get('top',0))))/2
  near=[(abs(y-existing),i) for i,existing in enumerate(ys) if abs(y-existing)<=tol]
  if near:
   _,i=min(near); groups[i].append(w); n=len(groups[i]); ys[i]=((ys[i]*(n-1))+y)/n
  else:groups.append([w]);ys.append(y)
 out=[]
 for y,items in zip(ys,groups):
  items.sort(key=lambda x:float(x.get('x0',0))); out.append({'y':y,'text':''.join(str(x.get('text') or '') for x in items),'words':items})
 return sorted(out,key=lambda x:x['y'])

def time_cells(row:dict[str,Any]|None)->list[dict[str,Any]]:
 if not row:return[]
 out=[]
 for w in row.get('words') or []:
  text=norm(w.get('text'))
  if not TIME_RE.fullmatch(text):continue
  value=int(text);hh,mm=divmod(value,100)
  if hh>29 or mm>59:continue
  x0=float(w.get('x0',0));x1=float(w.get('x1',x0));out.append({'text':text,'minute':hh*60+mm,'x':(x0+x1)/2})
 return sorted(out,key=lambda x:x['x'])

def matches(row:dict[str,Any],station:str)->bool:return norm(station) in norm(row.get('text'))
def best_station_row(rows:list[dict[str,Any]],station:str)->dict[str,Any]|None:
 candidates=[r for r in rows if matches(r,station) and time_cells(r)]
 return max(candidates,key=lambda r:(len(time_cells(r)),-len(norm(r.get('text'))))) if candidates else None

def first_station_after(rows:list[dict[str,Any]],station:str,start:int)->tuple[int,dict[str,Any]|None]:
 for i in range(max(0,start),len(rows)):
  if matches(rows[i],station) and time_cells(rows[i]):return i,rows[i]
 return -1,None

def shin_yokohama_block(rows:list[dict[str,Any]])->dict[str,dict[str,Any]|None]:
 # The official table has Shin-Yokohama and Hazawa as separate arrival/departure
 # rows and Nishiya appears again later in the Main-line section. Select the
 # first chronological station rows inside the Shin-Yokohama-line block rather
 # than choosing among duplicate station names globally.
 tsuna_candidates=[(i,r) for i,r in enumerate(rows) if matches(r,'新綱島') and time_cells(r)]
 if not tsuna_candidates:return {s:None for s in SHINYOKOHAMA_ANCHORS}
 i_tsuna,r_tsuna=max(tsuna_candidates,key=lambda p:len(time_cells(p[1])))
 i_shin,r_shin=first_station_after(rows,'新横浜',i_tsuna+1)
 i_hazawa,r_hazawa=first_station_after(rows,'羽沢横浜国大',(i_shin+1 if i_shin>=0 else i_tsuna+1))
 return {'新綱島':r_tsuna,'新横浜':r_shin,'羽沢横浜国大':r_hazawa}

def column_tolerance(cell_rows:list[list[dict[str,Any]]])->float:
 xs=sorted({round(float(c['x']),2) for cells in cell_rows for c in cells});gaps=sorted(b-a for a,b in zip(xs,xs[1:]) if 3<b-a<60)
 return 5.0 if not gaps else max(2.0,min(6.0,gaps[len(gaps)//2]*0.30))
def common_columns(cells:dict[str,list[dict[str,Any]]],anchors:tuple[str,...])->list[dict[str,Any]]:
 if any(not cells.get(s) for s in anchors):return[]
 tol=column_tolerance([cells[s] for s in anchors]);reference=min((cells[s] for s in anchors),key=len);out=[];seen=set()
 for base in reference:
  found={}
  for s in anchors:
   options=sorted(cells[s],key=lambda c:abs(float(c['x'])-float(base['x'])))
   if not options or abs(float(options[0]['x'])-float(base['x']))>tol:found={};break
   found[s]=options[0]
  if not found:continue
  sig=tuple(int(round(float(found[s]['x'])*10)) for s in anchors)
  if sig in seen:continue
  seen.add(sig);out.append({'columnX':round(sum(float(found[s]['x']) for s in anchors)/len(anchors),2),'tolerance':round(tol,2),'times':{s:found[s]['text'] for s in anchors}})
 return sorted(out,key=lambda x:x['columnX'])
def orient(direction:str,anchors:tuple[str,...])->list[str]:return list(reversed(anchors)) if direction=='up' else list(anchors)

def build_report()->dict[str,Any]:
 pdf_rows=[];evidence=[];diagnostics=[];counts=Counter()
 for spec in PDFS:
  data=fetch_pdf(spec['url']);local=Counter();parsed=0
  with pdfplumber.open(io.BytesIO(data)) as pdf:
   if len(pdf.pages)<2:raise RuntimeError('Unexpected Sotetsu timetable page count')
   for page_no,page in enumerate(pdf.pages,start=1):
    if page_no==1:continue
    rows=group_rows(page.extract_words(x_tolerance=1,y_tolerance=1,keep_blank_chars=False,use_text_flow=False))
    hrows={s:best_station_row(rows,s) for s in HIYOSHI_ANCHORS};srows=shin_yokohama_block(rows)
    hcells={s:time_cells(r) for s,r in hrows.items()};scells={s:time_cells(r) for s,r in srows.items()}
    parsed+=1
    for boundary,anchors,station_cells in [('toyoko-tokyushinyokohama-hiyoshi',HIYOSHI_ANCHORS,hcells),('tokyushinyokohama-sotetsushinyokohama-shinyokohama',SHINYOKOHAMA_ANCHORS,scells)]:
     cols=common_columns(station_cells,anchors)
     if boundary.endswith('shinyokohama') and not cols and len(diagnostics)<12:
      diagnostics.append({'url':spec['url'],'page':page_no,'boundary':boundary,'cellCounts':{s:len(station_cells.get(s) or []) for s in anchors},'rowTexts':{s:norm((srows.get(s) or {}).get('text'))[:180] for s in anchors},'xSamples':{s:[round(float(c['x']),2) for c in (station_cells.get(s) or [])[:8]] for s in anchors}})
     for col in cols:
      if boundary=='toyoko-tokyushinyokohama-hiyoshi':fr,to=(('odpt.Railway:Tokyu.TokyuShinYokohama','odpt.Railway:Tokyu.Toyoko') if spec['direction']=='up' else ('odpt.Railway:Tokyu.Toyoko','odpt.Railway:Tokyu.TokyuShinYokohama'))
      else:fr,to=(('odpt.Railway:Sotetsu.SotetsuShinYokohama','odpt.Railway:Tokyu.TokyuShinYokohama') if spec['direction']=='up' else ('odpt.Railway:Tokyu.TokyuShinYokohama','odpt.Railway:Sotetsu.SotetsuShinYokohama'))
      stops=orient(spec['direction'],anchors);row={'id':stable_id(spec['url'],page_no,col['columnX'],boundary,col['times']),'identityEvidence':'official-same-printed-column','status':'verified','canonicalBoundaryId':boundary,'calendar':spec['calendar'],'direction':spec['direction'],'sourceUrl':spec['url'],'pdfPage':page_no,'columnX':col['columnX'],'columnTolerance':col['tolerance'],'publishedBoundaryStops':stops,'printedTimes':col['times'],'fromRailway':fr,'toRailway':to,'matchPolicy':{'officialSamePrintedColumnRequired':True,'exactPrintedStationTimesRequired':True,'timeProximityAloneMayEstablishIdentity':False,'trainNumberAloneMayEstablishIdentity':False,'destinationAloneMayEstablishIdentity':False}}
      evidence.append(row);counts[boundary]+=1;local[boundary]+=1
  pdf_rows.append({'url':spec['url'],'calendar':spec['calendar'],'direction':spec['direction'],'bytes':len(data),'pageCount':len(pdf.pages),'parsedTimetablePages':parsed,'boundaryCounts':dict(local)})
 evidence=list({r['id']:r for r in evidence}.values());evidence.sort(key=lambda r:(r['calendar'],r['direction'],r['pdfPage'],r['columnX'],r['canonicalBoundaryId']))
 return {'version':2,'generatedAt':datetime.now(timezone.utc).isoformat(),'source':'Sotetsu official full train timetable PDFs effective 2026-03-14','officialEntryPage':'https://www.sotetsu.co.jp/train/stations/','identityPolicy':{'officialSamePrintedColumnMayEstablishIdentity':True,'exactPrintedStationTimesRequired':True,'timeProximityMayEstablishIdentity':False,'trainNumberAloneMayEstablishIdentity':False,'destinationAloneMayEstablishIdentity':False,'stationTimetableRowAloneMayEstablishIdentity':False},'pdfs':pdf_rows,'summary':{'pdfsFetched':len(pdf_rows),'evidenceRecords':len(evidence),'boundaryCounts':dict(counts),'diagnostics':len(diagnostics)},'authoritativeColumns':evidence,'diagnostics':diagnostics}

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--output',default='data/transit/fukutoshin/sotetsu-official-line13-columns.json');args=ap.parse_args();report=build_report();out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('SUMMARY',json.dumps(report['summary'],ensure_ascii=False,indent=2))
 for r in report['pdfs']:print('PDF',json.dumps(r,ensure_ascii=False))
 for r in report['authoritativeColumns'][:12]:print('SAMPLE',json.dumps(r,ensure_ascii=False))
 for r in report['diagnostics'][:12]:print('DIAGNOSTIC',json.dumps(r,ensure_ascii=False))
 c=report['summary']['boundaryCounts']
 if int(c.get('toyoko-tokyushinyokohama-hiyoshi',0))<1:raise RuntimeError('No exact Hiyoshi same-column evidence')
 if int(c.get('tokyushinyokohama-sotetsushinyokohama-shinyokohama',0))<1:raise RuntimeError('No exact Shin-Yokohama same-column evidence')
 return 0
if __name__=='__main__':raise SystemExit(main())
