#!/usr/bin/env python3
"""Resumable Yahoo all-station inventory and one-train research. No runtime writes."""
import http.client,urllib.parse,base64
import argparse,concurrent.futures,gzip,hashlib,json,pathlib,re,threading,time,urllib.request,urllib.error
BASE=pathlib.Path(__file__).resolve().parents[1]
OUT=BASE/'data/transit/yahoo-western-research'
CACHE=pathlib.Path('/tmp/yahoo-study/cache');CACHE.mkdir(parents=True,exist_ok=True)
RAILS={'東武東上線':'Tobu.Tojo','西武池袋線':'Seibu.Ikebukuro','西武有楽町線':'Seibu.SeibuYurakucho','西武秩父線':'Seibu.SeibuChichibu','西武狭山線':'Seibu.Sayama','西武豊島線':'Seibu.Toshima','東急東横線':'Tokyu.Toyoko','東急目黒線':'Tokyu.Meguro','東急新横浜線':'Tokyu.TokyuShinYokohama','東京メトロ有楽町線':'TokyoMetro.Yurakucho','東京メトロ副都心線':'TokyoMetro.Fukutoshin','東京メトロ南北線':'TokyoMetro.Namboku','都営地下鉄三田線':'Toei.Mita','相鉄本線':'Sotetsu.Main','相鉄いずみ野線':'Sotetsu.Izumino','相鉄新横浜線':'Sotetsu.SotetsuShinYokohama','みなとみらい線':'YokohamaMinatomirai.Minatomirai','埼玉高速鉄道':'SaitamaRailway.SaitamaRailway'}
def dump(name,x):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
 b=json.dumps(x,ensure_ascii=False,separators=(',',':')).encode();b=gzip.compress(b,mtime=0) if str(p).endswith('.gz') else b
 q=p.with_suffix(p.suffix+'.tmp');q.write_bytes(b);q.replace(p)
def read(name,default):
 p=OUT/name
 if not p.exists():return default
 return json.loads(gzip.decompress(p.read_bytes()) if str(p).endswith('.gz') else p.read_bytes())
POOL=threading.local()
def pooled_get(url):
 target=urllib.parse.urlsplit(url)
 assert target.scheme=='https' and target.hostname=='transit.yahoo.co.jp'
 if not getattr(POOL,'connection',None):
  proxy_url=urllib.request.getproxies().get('https')
  if proxy_url and not urllib.request.proxy_bypass(target.hostname):
   proxy=urllib.parse.urlsplit(proxy_url)
   if proxy.scheme!='http':
    return urllib.request.urlopen(url,timeout=25).read()
   c=http.client.HTTPSConnection(proxy.hostname,proxy.port or 80,timeout=25)
   headers={}
   if proxy.username:
    token=base64.b64encode((urllib.parse.unquote(proxy.username)+':'+urllib.parse.unquote(proxy.password or '')).encode()).decode()
    headers['Proxy-Authorization']='Basic '+token
   c.set_tunnel(target.hostname,443,headers=headers)
  else:c=http.client.HTTPSConnection(target.hostname,443,timeout=25)
  POOL.connection=c
 c=POOL.connection
 try:
  c.request('GET',target.path+('?' + target.query if target.query else ''),headers={'User-Agent':'Python-urllib/3.12','Accept-Encoding':'gzip','Connection':'keep-alive'})
  r=c.getresponse();b=r.read()
  if r.status!=200:raise urllib.error.HTTPError(url,r.status,r.reason,r.headers,None)
  return gzip.decompress(b) if r.getheader('Content-Encoding')=='gzip' else b
 except Exception:
  c.close();POOL.connection=None;raise

def fetch(url):
 p=CACHE/(hashlib.sha256(url.encode()).hexdigest()+'.html')
 if p.exists():raw=p.read_bytes()
 else:
  for attempt in range(3):
   try:
    raw=pooled_get(url);break
   except urllib.error.HTTPError as e:
    if e.code in [401,403,429]:raise
    if attempt==2:raise
   except (TimeoutError,OSError):
    if attempt==2:raise
   time.sleep(0.4*(attempt+1))
  p.write_bytes(raw)
 m=re.search(rb'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',raw,re.S)
 if not m:raise ValueError('Missing page data')
 return json.loads(m.group(1))['props']['pageProps'],hashlib.sha256(raw).hexdigest()
def batch(items,fn,filename,workers):
 saved=read(filename,{})
 todo=[(k,x) for k,x in items if k not in saved or 'error' in saved[k]]
 print(f'{filename}: saved={len(saved)} pending={len(todo)}',flush=True)
 def one(k,x):
  try:return k,fn(x)
  except Exception as e:return k,{'error':str(e),'input':x}
 with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
  fut=[ex.submit(one,k,x) for k,x in todo]
  for i,f in enumerate(concurrent.futures.as_completed(fut),1):
   k,v=f.result();saved[k]=v
   if i%25==0 or i==len(todo):
    dump(filename,saved);print(f'{filename}: processed {i}/{len(todo)}, errors {sum("error" in v for v in saved.values())}',flush=True)
 dump(filename,saved);return saved

RAILS.update({'東京メトロ有楽町線・副都心線':'TokyoMetro.YurakuchoFukutoshinShared','東京メトロ南北線・都営三田線':'TokyoMetro.NambokuMitaShared','相鉄・ＪＲ直通線':'Sotetsu.JRThrough'})
def catalog(workers):
 ts=read('target-stations.json',[]);assert all(t['yahooId'] for t in ts)
 ids=sorted(set(t['yahooId'] for t in ts))
 def index(sid):
  u=f'https://transit.yahoo.co.jp/timetable/{sid}';j,h=fetch(u);d=j['directionDetail'];rs=[]
  for r in d['directionItem']['routeInfos']:
   if r['railName'] in RAILS:
    for g in r['railGroup']:rs.append(dict(railway=RAILS[r['railName']],railName=r['railName'],groupId=g['groupId'],direction=g['direction'],dayKinds=g['driveDayKind']))
  return dict(url=u,sha256=h,stationId=sid,stationName=d['stationName'],directions=rs)
 return batch([(sid,sid) for sid in ids],index,'station-index.json',workers)

def boards(workers):
 cat=read('station-index.json',{});assert not any('error' in v for v in cat.values())
 items=[]
 for sid,st in cat.items():
  for g in st['directions']:
   for kind in [1,2,4]:
    if int(g['dayKinds'])&kind:
     k=f"{sid}/{g['groupId']}?kind={kind}";items.append((k,dict(stationId=sid,kind=kind,**g)))
 def board(x):
  url=f"https://transit.yahoo.co.jp/timetable/{x['stationId']}/{x['groupId']}?kind={x['kind']}";j,h=fetch(url);t=j['timetableItem']
  assert t['railName']==x['railName'],(url,t['railName'],x['railName'])
  ds={r['id']:r['name'] for r in t['master']['destination']};deps=[]
  for hour in t['hourTimeTable']:
   for m in hour['minTimeTable']:
    deps.append(dict(trainId=m['trainId'],hh=hour['hour'],mm=m['minute'],destination=ds[m['destinationId']],number=m.get('vendorTrainId'),trainType=m['trainName'],conditional=m.get('extraTrain')=='true',startsHere=m.get('firstStation')=='true'))
  return dict(**x,url=url,sha256=h,stationName=t['stationName'],departures=deps)
 return batch(items,board,'station-boards.json.gz',workers)

def details(workers):
 bs=read('station-boards.json.gz',{});assert not any('error' in v for v in bs.values())
 items={};occurrences={}
 for key,b in bs.items():
  for d in b['departures']:
   tid=d['trainId'];occurrences.setdefault(tid,[]).append(dict(board=key,stationId=b['stationId'],railway=b['railway'],kind=b['kind'],**d))
   if tid not in items:items[tid]=dict(url=f"https://transit.yahoo.co.jp/timetable/{b['stationId']}/{b['groupId']}/{tid}?kind={b['kind']}&hh={d['hh']}&mm={d['mm']}",trainId=tid)
 dump('train-occurrences.json.gz',occurrences)
 def train(x):
  j,h=fetch(x['url']);r=j['timetableStationTrainResult'];t=r['timetable'];assert str(t['trainId'])==x['trainId'];assert len(t['stopStation'])>=2
  # Retain only timetable evidence. No login, cookie, identifier or ad metadata.
  return dict(**x,sha256=h,engineVersion=r.get('engineInfo',{}).get('version'),displayName=t['displayName'],calendarCondition=t.get('driveComment',''),sectionComment=t.get('guideComment',''),stops=[{k:s.get(k) for k in ['stationCode','stationName','arrivalTime','departureTime']} for s in t['stopStation']])
 return batch(sorted(items.items()),train,'train-pages.json.gz',workers)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--phase',choices=['catalog','boards','details','all'],default='all');p.add_argument('--workers',type=int,default=16);a=p.parse_args()
 for name,fn in [('catalog',catalog),('boards',boards),('details',details)]:
  if a.phase in [name,'all']:fn(a.workers)
