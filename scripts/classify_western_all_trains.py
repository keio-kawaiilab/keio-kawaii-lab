#!/usr/bin/env python3
"""Classify complete Yahoo train pages, never join trains by time proximity.

Line topology interprets the already-published ordered journey. It is not a
journey planner: transfers are limited to through-service boundaries, and
 Railways must have board evidence or at least two stops on the published
 journey; Seibu-Yurakucho is the explicit connecting corridor for S-TRAIN,
 which can skip every station in that short line. All departures match exactly.
"""
import collections,functools,heapq,json,re
import research_western_all_trains as src

def norm(s):
 return re.sub(r'\([^)]*\)|（[^）]*）|<[^>]*>|〈[^〉]*〉','',s).replace('ケ','ヶ').replace('麴','麹')

TOPO={r:list(map(norm,ss)) for r,ss in src.read('line-topology.json',{}).items()}
NAMES={v:k for k,v in src.RAILS.items()}
NAMES.update({'JR.SaikyoSotetsuThrough':'JR埼京・相鉄直通線','JR.Kawagoe':'JR川越線','Chichibu.Chichibu':'秩父鉄道'})
BOUNDARIES=[
 ('和光市','Tobu.Tojo','TokyoMetro.Yurakucho'),('和光市','Tobu.Tojo','TokyoMetro.Fukutoshin'),
 ('練馬','Seibu.Ikebukuro','Seibu.SeibuYurakucho'),('練馬','Seibu.Ikebukuro','Seibu.Toshima'),
 ('小竹向原','Seibu.SeibuYurakucho','TokyoMetro.Yurakucho'),('小竹向原','Seibu.SeibuYurakucho','TokyoMetro.Fukutoshin'),
 ('西所沢','Seibu.Ikebukuro','Seibu.Sayama'),('吾野','Seibu.Ikebukuro','Seibu.SeibuChichibu'),
 ('渋谷','TokyoMetro.Fukutoshin','Tokyu.Toyoko'),('横浜','Tokyu.Toyoko','YokohamaMinatomirai.Minatomirai'),
 ('日吉','Tokyu.Toyoko','Tokyu.TokyuShinYokohama'),('日吉','Tokyu.Meguro','Tokyu.TokyuShinYokohama'),
 ('新横浜','Tokyu.TokyuShinYokohama','Sotetsu.SotetsuShinYokohama'),
 ('西谷','Sotetsu.SotetsuShinYokohama','Sotetsu.Main'),('二俣川','Sotetsu.Main','Sotetsu.Izumino'),
 ('目黒','Tokyu.Meguro','TokyoMetro.Namboku'),('目黒','Tokyu.Meguro','Toei.Mita'),
 ('赤羽岩淵','TokyoMetro.Namboku','SaitamaRailway.SaitamaRailway'),
 ('羽沢横浜国大','Sotetsu.SotetsuShinYokohama','JR.SaikyoSotetsuThrough'),('大宮','JR.SaikyoSotetsuThrough','JR.Kawagoe')]

def compress(xs):
 return tuple(x for i,x in enumerate(xs) if i==0 or x!=xs[i-1])

@functools.lru_cache(None)
def graph(rails):
 g=collections.defaultdict(list)
 for r in rails:
  for a,b in zip(TOPO[r],TOPO[r][1:]):
   g[a,r].append(((b,r),100,r));g[b,r].append(((a,r),100,r))
 for s,a,b in BOUNDARIES:
  s=norm(s)
  if a in rails and b in rails:
   g[s,a].append(((s,b),1,None));g[s,b].append(((s,a),1,None))
 # The through connection bypasses a platform stop at Seibu-Chichibu for
 # Nagatoro trains; its line attribution follows Yokose -> Ohanabatake.
 if 'Chichibu.Chichibu' in rails:
  a=('西武秩父','Seibu.SeibuChichibu');b=('御花畑','Chichibu.Chichibu')
  g[a].append((b,100,'Chichibu.Chichibu'));g[b].append((a,100,'Chichibu.Chichibu'))
 return g

@functools.lru_cache(None)
def paths(rails,start,target):
 g=graph(rails);q=[(0,start,())];best={start:0};answers={}
 while q:
  cost,state,chain=heapq.heappop(q)
  if cost>best[state]:continue
  if state[0]==target:
   key=state,chain
   if key not in answers:answers[key]=cost
  for nxt,w,r in g[state]:
   nc=cost+w;ch=compress(chain+(r,)) if r else chain
   if nc<=best.get(nxt,10**9):
    if nc<best.get(nxt,10**9):best[nxt]=nc
    heapq.heappush(q,(nc,nxt,ch))
 return tuple((st,c,ch) for (st,ch),c in answers.items())

def route(t,occ,enrich=False):
 stops=tuple(norm(s['stationName']) for s in t['stops']);rails={o['railway'] for o in occ}
 observed=set(rails)
 # Some conditional services use different publication IDs on different
 # operators' boards. The complete one-train page still supplies the journey.
 # Do not merge those IDs; derive this page's lines from its own ordered stops.
 if enrich:
  rails.update(r for r,ss in TOPO.items() if len(set(ss).intersection(stops))>=2)
  for r,ss in TOPO.items():
   unique=set(ss)-set(s for other,os in TOPO.items() if other!=r for s in os)
   if unique.intersection(stops):rails.add(r)
 # Parallel tracks have the same station names. Exact line-specific board
 # observations select the track; station names alone cannot decide it.
 for a,b in [('Tokyu.Meguro','Tokyu.Toyoko'),('TokyoMetro.Yurakucho','TokyoMetro.Fukutoshin')]:
  if (a in observed)!=(b in observed):rails.discard(b if a in observed else a)
 if 'TokyoMetro.YurakuchoFukutoshinShared' in rails:
  rails.remove('TokyoMetro.YurakuchoFukutoshinShared')
  if not rails.intersection({'TokyoMetro.Yurakucho','TokyoMetro.Fukutoshin'}):rails.update(['TokyoMetro.Yurakucho','TokyoMetro.Fukutoshin'])
 if 'Seibu.Ikebukuro' in rails and rails.intersection({'TokyoMetro.Yurakucho','TokyoMetro.Fukutoshin'}):rails.add('Seibu.SeibuYurakucho')
 if '西大井' in stops:rails.add('JR.SaikyoSotetsuThrough')
 if '日進' in stops:rails.add('JR.Kawagoe')
 if '御花畑' in stops or '三峰口' in stops:rails.add('Chichibu.Chichibu')
 rails=tuple(sorted(rails));g=graph(rails)
 dp={(st,()):0 for st in g if st[0]==stops[0]}
 for target in stops[1:]:
  new={}
  for (st,chain),cost in dp.items():
   for end,c,ch in paths(rails,st,target):
    k=(end,compress(chain+ch));new[k]=min(new.get(k,10**9),cost+c)
  # Keep all tied minimum routes per railway state; no arbitrary tie break.
  mins={}
  for (st,ch),c in new.items():mins[st]=min(mins.get(st,10**9),c)
  dp={(st,ch):c for (st,ch),c in new.items() if c==mins[st]}
  if not dp:
   if not enrich:return route(t,occ,True)
   return [],{'error':'no-route','target':target,'rails':rails}
 m=min(dp.values());chs=sorted({ch for (st,ch),c in dp.items() if c==m})
 if len(chs)!=1:return chs,{'error':'ambiguous-route','rails':rails}
 return chs,None

def main():
 pages=src.read('train-pages.json.gz',{});occ=src.read('train-occurrences.json.gz',{});boards=src.read('station-boards.json.gz',{});cat=src.read('station-index.json',{})
 assert pages.keys()==occ.keys()
 assert not any('error' in x for collection in [pages,boards,cat] for x in collection.values())
 result={};errors=[];mismatches=[]
 for i,(tid,t) in enumerate(sorted(pages.items()),1):
  events={(s['stationCode'],int(s['departureTime'])//100%24,int(s['departureTime'])%100) for s in t['stops'] if s['departureTime']}
  for o in occ[tid]:
   if (o['stationId'],int(o['hh'])%24,int(o['mm'])) not in events:mismatches.append({'trainId':tid,'occurrence':o})
  routes,error=route(t,occ[tid])
  if error:errors.append(dict(trainId=tid,routes=routes,**error))
  rails=routes[0] if len(routes)==1 else []
  kinds=sorted({o['kind'] for o in occ[tid]});condition=t['calendarCondition']
  result[tid]=dict(trainId=tid,railways=rails,route=[NAMES[r] for r in rails],routeAlternatives=routes if error else [],origin=t['stops'][0]['stationName'],departure=t['stops'][0]['departureTime'],destination=t['stops'][-1]['stationName'],arrival=t['stops'][-1]['arrivalTime'],kinds=kinds,calendarCondition=condition,hasDateRestriction=condition not in ['','毎日運転','平日運転','土曜・休日運転'],boardConditional=any(o['conditional'] for o in occ[tid]),classification='unresolved' if error else ('through' if len(rails)>1 else 'line-only'),trainNumbers=sorted({o['number'] for o in occ[tid] if o['number']}),displayName=t['displayName'],sectionComment=t['sectionComment'],sourceURL=t['url'],sourceSha256=t['sha256'],stopCount=len(t['stops']),observationCount=len(occ[tid]))
  if i%1000==0:print(f'classified {i}/{len(pages)}, errors {len(errors)}',flush=True)
 src.dump('classified-trains.json.gz',result)
 audit=dict(stations=len(cat),boards=len(boards),trainIds=len(pages),departureObservations=sum(len(b['departures']) for b in boards.values()),exactDepartureMismatches=len(mismatches),routeErrors=errors,sourceEngines=dict(collections.Counter(t['engineVersion'] for t in pages.values())),classifications=dict(collections.Counter(t['classification'] for t in result.values())),dateRestrictedTrainIds=sum(t['hasDateRestriction'] for t in result.values()),complete=not errors and not mismatches)
 src.dump('audit.json',audit);src.dump('departure-mismatches.json.gz',mismatches)
 print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
