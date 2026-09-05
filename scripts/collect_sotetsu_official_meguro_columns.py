#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,io,json,re
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
import pdfplumber,requests

PDFS=[
 {'calendar':'weekday','direction':'up','url':'https://cdn.sotetsu.co.jp/media/2026/train/stations/download/timetable-01-260314-jE9.pdf'},
 {'calendar':'weekday','direction':'down','url':'https://cdn.sotetsu.co.jp/media/2026/train/stations/download/timetable-02-260314-L6y.pdf'},
 {'calendar':'holiday','direction':'up','url':'https://cdn.sotetsu.co.jp/media/2026/train/stations/download/timetable-03-260314-nS1.pdf'},
 {'calendar':'holiday','direction':'down','url':'https://cdn.sotetsu.co.jp/media/2026/train/stations/download/timetable-04-260314-uH2.pdf'},
]
HIYOSHI=('大岡山','日吉','新綱島')
M_BRANCH={'西高島平':'mita','高島平':'mita'}
N_BRANCH={'赤羽岩淵':'namboku','浦和美園':'namboku','鳩ヶ谷':'namboku','王子神谷':'namboku','駒込':'namboku','麻布十番':'namboku'}
TERMINALS={**M_BRANCH,**N_BRANCH}
TIME_RE=re.compile(r'^\d{3,4}$')
SESSION=requests.Session();SESSION.headers.update({'User-Agent':'Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/9.0)','Accept':'application/pdf,*/*;q=0.8'})
def norm(v:Any)->str:return re.sub(r'[\s\u3000]+','',str(v or '')).replace('ヶ','ケ')
def stable_id(*parts:Any)->str:return 'sotetsu-meguro-column:'+hashlib.sha256(json.dumps(parts,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:24]
def fetch_pdf(url:str)->bytes:
 r=SESSION.get(url,timeout=(20,90));r.raise_for_status();data=r.content
 if not data.startswith(b'%PDF'):raise RuntimeError(f'Not PDF: {url}')
 return data
def group_rows(words,tol=1.7):
 groups=[];ys=[]
 for w in sorted(words,key=lambda x:(float(x.get('top',0)),float(x.get('x0',0)))):
  y=(float(w.get('top',0))+float(w.get('bottom',w.get('top',0))))/2;near=[(abs(y-e),i) for i,e in enumerate(ys) if abs(y-e)<=tol]
  if near:
   _,i=min(near);groups[i].append(w);n=len(groups[i]);ys[i]=((ys[i]*(n-1))+y)/n
  else:groups.append([w]);ys.append(y)
 out=[]
 for y,items in zip(ys,groups):
  items.sort(key=lambda x:float(x.get('x0',0)));out.append({'y':y,'text':''.join(str(x.get('text') or '') for x in items),'words':items})
 return sorted(out,key=lambda x:x['y'])
def time_cells(row):
 out=[]
 if not row:return out
 for w in row.get('words') or []:
  t=norm(w.get('text'))
  if not TIME_RE.fullmatch(t):continue
  v=int(t);h,m=divmod(v,100)
  if h>29 or m>59:continue
  x0=float(w.get('x0',0));x1=float(w.get('x1',x0));out.append({'text':t,'x':(x0+x1)/2})
 return sorted(out,key=lambda c:c['x'])
def matches(row,s):return norm(s) in norm((row or {}).get('text'))
def best_station_row(rows,s):
 c=[r for r in rows if matches(r,s) and time_cells(r)];return max(c,key=lambda r:len(time_cells(r))) if c else None
def common_columns(cells,anchors):
 if any(not cells.get(s) for s in anchors):return[]
 xs=sorted({round(float(c['x']),2) for s in anchors for c in cells[s]});gaps=sorted(b-a for a,b in zip(xs,xs[1:]) if 3<b-a<60);tol=5.0 if not gaps else max(2.0,min(6.0,gaps[len(gaps)//2]*.30))
 ref=min((cells[s] for s in anchors),key=len);out=[];seen=set()
 for b in ref:
  found={}
  for s in anchors:
   opts=sorted(cells[s],key=lambda c:abs(c['x']-b['x']))
   if not opts or abs(opts[0]['x']-b['x'])>tol:found={};break
   found[s]=opts[0]
  if not found:continue
  sig=tuple(round(found[s]['x'],1) for s in anchors)
  if sig in seen:continue
  seen.add(sig);out.append({'x':round(sum(found[s]['x'] for s in anchors)/len(anchors),2),'tol':round(tol,2),'times':{s:found[s]['text'] for s in anchors}})
 return out
def terminal_cells(row):
 out=[]
 for w in (row or {}).get('words') or []:
  t=norm(w.get('text'));hit=next((name for name in TERMINALS if name in t),None)
  if not hit:continue
  x0=float(w.get('x0',0));x1=float(w.get('x1',x0));out.append({'terminal':hit,'branch':TERMINALS[hit],'x':(x0+x1)/2,'text':t})
 return out
def nearest_terminal_rows(rows,meguro_idx,direction):
 if meguro_idx<0:return[]
 indexes=range(meguro_idx+1,min(len(rows),meguro_idx+7)) if direction=='up' else range(max(0,meguro_idx-6),meguro_idx)
 out=[]
 for i in indexes:out.extend(terminal_cells(rows[i]))
 return out
def build():
 evidence=[];counts=Counter();dirs=defaultdict(Counter);pdfs=[];diag=[]
 for spec in PDFS:
  data=fetch_pdf(spec['url']);local=Counter()
  with pdfplumber.open(io.BytesIO(data)) as pdf:
   for pno,page in enumerate(pdf.pages,start=1):
    if pno==1:continue
    rows=group_rows(page.extract_words(x_tolerance=1,y_tolerance=1,keep_blank_chars=False,use_text_flow=False))
    # Hiyoshi: Meguro-line-specific Oookayama + Hiyoshi + Shin-Tsunashima on one printed train column.
    hrows={s:best_station_row(rows,s) for s in HIYOSHI};hcells={s:time_cells(hrows[s]) for s in HIYOSHI}
    for col in common_columns(hcells,HIYOSHI):
     fr,to=(('odpt.Railway:Tokyu.TokyuShinYokohama','odpt.Railway:Tokyu.Meguro') if spec['direction']=='up' else ('odpt.Railway:Tokyu.Meguro','odpt.Railway:Tokyu.TokyuShinYokohama'))
     stops=list(reversed(HIYOSHI)) if spec['direction']=='up' else list(HIYOSHI)
     evidence.append({'id':stable_id(spec['url'],pno,col['x'],'meguro-tokyushinyokohama-hiyoshi',col['times']),'identityEvidence':'official-same-printed-column','status':'verified','canonicalBoundaryId':'meguro-tokyushinyokohama-hiyoshi','calendar':spec['calendar'],'direction':spec['direction'],'sourceUrl':spec['url'],'pdfPage':pno,'columnX':col['x'],'columnTolerance':col['tol'],'publishedBoundaryStops':stops,'printedTimes':col['times'],'fromRailway':fr,'toRailway':to,'matchPolicy':{'officialSamePrintedColumnRequired':True,'exactPrintedStationTimesRequired':True,'routeSpecificMeguroStationRequired':True,'timeProximityAloneMayEstablishIdentity':False,'trainNumberAloneMayEstablishIdentity':False,'destinationAloneMayEstablishIdentity':False}});counts['meguro-tokyushinyokohama-hiyoshi']+=1;local['meguro-tokyushinyokohama-hiyoshi']+=1;dirs['meguro-tokyushinyokohama-hiyoshi'][spec['direction']]+=1
    # Meguro: branch-specific external origin/destination is printed in the same train column.
    mr=best_station_row(rows,'目黒');mc=time_cells(mr);mi=rows.index(mr) if mr in rows else -1;tc=nearest_terminal_rows(rows,mi,spec['direction'])
    if mc and tc:
     gaps=sorted(b['x']-a['x'] for a,b in zip(mc,mc[1:]) if 8<b['x']-a['x']<60);tol=12.0 if not gaps else max(7.0,min(14.0,gaps[len(gaps)//2]*.48))
     used=set()
     for term in tc:
      m=min(mc,key=lambda c:abs(c['x']-term['x']))
      if abs(m['x']-term['x'])>tol:continue
      key=(round(m['x'],1),term['branch'])
      if key in used:continue
      used.add(key);branch=term['branch'];other='odpt.Railway:Toei.Mita' if branch=='mita' else 'odpt.Railway:TokyoMetro.Namboku';bid='meguro-mita-meguro' if branch=='mita' else 'meguro-namboku-meguro'
      fr,to=(('odpt.Railway:Tokyu.Meguro',other) if spec['direction']=='up' else (other,'odpt.Railway:Tokyu.Meguro'))
      evidence.append({'id':stable_id(spec['url'],pno,m['x'],bid,term['terminal'],m['text']),'identityEvidence':'official-same-printed-column','status':'verified','canonicalBoundaryId':bid,'calendar':spec['calendar'],'direction':spec['direction'],'sourceUrl':spec['url'],'pdfPage':pno,'columnX':round(m['x'],2),'columnTolerance':round(tol,2),'boundaryStation':'目黒','printedMeguroTime':m['text'],'branchSpecificExternalTerminal':term['terminal'],'branch':branch,'fromRailway':fr,'toRailway':to,'matchPolicy':{'officialSamePrintedColumnRequired':True,'exactMeguroTimeRequired':True,'branchSpecificExternalTerminalRequired':True,'timeProximityAloneMayEstablishIdentity':False,'trainNumberAloneMayEstablishIdentity':False,'destinationAloneMayEstablishIdentity':False}});counts[bid]+=1;local[bid]+=1;dirs[bid][spec['direction']]+=1
    elif len(diag)<12:diag.append({'url':spec['url'],'page':pno,'direction':spec['direction'],'meguroTimes':len(mc),'terminalCells':tc[:8]})
   pdfs.append({'url':spec['url'],'calendar':spec['calendar'],'direction':spec['direction'],'pages':len(pdf.pages),'boundaryCounts':dict(local)})
 evidence=list({e['id']:e for e in evidence}.values())
 return {'version':1,'generatedAt':datetime.now(timezone.utc).isoformat(),'source':'Sotetsu official full train timetable PDFs effective 2026-03-14','identityPolicy':{'officialSamePrintedColumnMayEstablishIdentity':True,'branchSpecificExternalTerminalRequiredAtMeguro':True,'timeProximityMayEstablishIdentity':False,'trainNumberAloneMayEstablishIdentity':False,'destinationAloneMayEstablishIdentity':False},'pdfs':pdfs,'summary':{'evidenceRecords':len(evidence),'boundaryCounts':dict(counts),'boundaryDirectionCounts':{k:dict(v) for k,v in dirs.items()},'diagnostics':len(diag)},'authoritativeColumns':evidence,'diagnostics':diag}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',default='data/transit/meguro/sotetsu-official-meguro-columns.json');a=ap.parse_args();r=build();Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('SUMMARY',json.dumps(r['summary'],ensure_ascii=False,indent=2))
 for b in ('meguro-tokyushinyokohama-hiyoshi','meguro-namboku-meguro','meguro-mita-meguro'):
  d=r['summary']['boundaryDirectionCounts'].get(b,{})
  if not(d.get('up',0)>0 and d.get('down',0)>0):raise RuntimeError(f'No bidirectional exact printed-column evidence for {b}: {d}')
if __name__=='__main__':main()
