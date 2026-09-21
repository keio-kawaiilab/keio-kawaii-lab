#!/usr/bin/env python3
"""Verify that an ID's full journey is invariant on every listed calendar."""
import hashlib,json,urllib.parse
import research_western_all_trains as src

def signature(t):
 return hashlib.sha256(json.dumps({k:t[k] for k in ['displayName','calendarCondition','sectionComment','stops']},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def main():
 pages=src.read('train-pages.json.gz',{});occ=src.read('train-occurrences.json.gz',{});items=[]
 for tid,os in occ.items():
  first=int(urllib.parse.parse_qs(urllib.parse.urlsplit(pages[tid]['url']).query)['kind'][0])
  for kind in sorted({o['kind'] for o in os}-{first}):
   o=next(o for o in os if o['kind']==kind);path=o['board'].split('?')[0]
   items.append((f'{tid}/{kind}',dict(trainId=tid,kind=kind,url=f"https://transit.yahoo.co.jp/timetable/{path}/{tid}?kind={kind}&hh={o['hh']}&mm={o['mm']}")))
 def check(x):
  j,h=src.fetch(x['url']);r=j['timetableStationTrainResult'];t=r['timetable'];assert str(t['trainId'])==x['trainId']
  clean=dict(displayName=t['displayName'],calendarCondition=t.get('driveComment',''),sectionComment=t.get('guideComment',''),stops=[{k:s.get(k) for k in ['stationCode','stationName','arrivalTime','departureTime']} for s in t['stopStation']])
  a=signature(clean);b=signature(pages[x['trainId']])
  return dict(**x,sha256=h,engineVersion=r.get('engineInfo',{}).get('version'),journeySignature=a,referenceSignature=b,matches=a==b,**({'differentJourney':clean} if a!=b else {}))
 result=src.batch(items,check,'calendar-checks.json.gz',16)
 audit=dict(expected=len(items),checked=len(result),errors=sum('error' in x for x in result.values()),mismatches=sum(x.get('matches') is False for x in result.values()))
 src.dump('calendar-audit.json',audit);print(audit)

if __name__=='__main__':main()
