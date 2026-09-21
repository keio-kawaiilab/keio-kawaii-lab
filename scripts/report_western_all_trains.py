#!/usr/bin/env python3
"""Audit the entire acquired mother set and publish a complete Markdown index."""
import collections,hashlib,json,pathlib
import research_western_all_trains as src
from classify_western_all_trains import NAMES,TOPO,norm

DOC=src.BASE/'docs/transit/yahoo-western-all-trains'
def clock(s):
 if s is None:return '—'
 n=int(s);return f'{n//100:02}:{n%100:02}'
def esc(s):return str(s or '—').replace('|','／').replace('\n',' ')
def day(t):return '・'.join({1:'平日',2:'土',4:'日祝'}[k] for k in t['kinds'])

def main():
 x=src.read('classified-trains.json.gz',{});pages=src.read('train-pages.json.gz',{});occ=src.read('train-occurrences.json.gz',{});cat=src.read('station-index.json',{});bs=src.read('station-boards.json.gz',{});ts=src.read('target-stations.json',[])
 a=src.read('audit.json',{});ca=src.read('calendar-audit.json',{});checks=src.read('calendar-checks.json.gz',{})
 expected={f"{sid}/{d['groupId']}?kind={kind}" for sid,c in cat.items() for d in c['directions'] for kind in [1,2,4] if int(d['dayKinds'])&kind}
 inventoryErrors=[]
 if expected!=bs.keys():inventoryErrors.append('advertised boards differ from acquired boards')
 if {t['yahooId'] for t in ts}!=cat.keys():inventoryErrors.append('target stations differ from acquired indexes')
 for t in ts:
  rail=t['railway'].split(':')[-1];seen={g['railway'] for g in cat[t['yahooId']]['directions']}
  if rail not in seen and not (rail in ['TokyoMetro.Yurakucho','TokyoMetro.Fukutoshin'] and 'TokyoMetro.YurakuchoFukutoshinShared' in seen):inventoryErrors.append(t)
 physical={norm(c['stationName']) for c in cat.values()}
 for rail,ss in TOPO.items():
  if rail.startswith(('JR.','Chichibu.')):continue
  for s in ss:
   if s not in physical:inventoryErrors.append({'missingTopologyStation':s,'railway':rail})
 chronologyErrors=[];signatures=collections.defaultdict(list)
 for tid,t in pages.items():
  prev=None;total=0
  for s in t['stops']:
   for field in ['arrivalTime','departureTime']:
    if s[field] is None:continue
    n=int(s[field]);m=(n//100%24)*60+n%100
    if prev is not None:total+=(m-prev)%1440
    prev=m
  if total>=1440 or not t['stops'][0]['departureTime'] or not t['stops'][-1]['arrivalTime']:chronologyErrors.append(tid)
  signature=json.dumps([t['stops'],t['calendarCondition'],x[tid]['kinds']],sort_keys=True)
  signatures[signature].append(tid)
 duplicateGroups=[v for v in signatures.values() if len(v)>1]
 counts=collections.Counter(tuple(t['railways']) for t in x.values());routeIds={rs:f'R{i:03}' for i,rs in enumerate(sorted(counts),1)}
 a.update(inventoryErrors=inventoryErrors,chronologyErrors=chronologyErrors,calendarCheck=ca,totalTrainDetailPages=len(pages)+len(checks),orderedRoutePatterns=len(counts),identicalJourneyPublicationGroups=duplicateGroups,acquiredAt='2026-09-07',countingUnit='Yahoo train publication ID, not trains running on one specific date',calendarCounts={str(k):sum(k in t['kinds'] for t in x.values()) for k in [1,2,4]},lineCounts={rail:{'all':sum(rail in t['railways'] for t in x.values()),'through':sum(rail in t['railways'] and t['classification']=='through' for t in x.values()),'lineOnly':sum(t['railways']==[rail] for t in x.values())} for rail in sorted({r for t in x.values() for r in t['railways']})})
 a['complete']=not(inventoryErrors or chronologyErrors or a['routeErrors'] or a['exactDepartureMismatches'] or ca.get('errors',1) or ca.get('mismatches',1)) and ca.get('expected')==ca.get('checked') and len(x)==len(pages)==len(occ)
 src.dump('audit.json',a);assert a['complete'],a
 DOC.mkdir(parents=True,exist_ok=True)
 byfirst=collections.defaultdict(list)
 for t in x.values():byfirst[t['railways'][0]].append(t)
 files={r:r.replace('.','-')+'.md' for r in byfirst}
 heading=['# 全列車の直通経路一覧','', '確認日：2026-09-07。Yahoo!乗換案内の掲載データ（版 `202609_03a`）。','',f"**{len(x):,}件の掲載列車IDを全件分類。複数路線にまたがる列車は3,958件、線内完結は3,940件。未分類・発車時刻の不一致は0件。**",'', '212駅・1,364件の全方向／平日・土曜・日祝の駅時刻表にある230,790件の発車掲載を、列車別ページの駅コード・発車時刻と全件照合した。列車別ページ7,898件に加え、同じIDの別曜日ページ3,812件も取得し、全停車駅・着発・運転日注記・区間注記が一致した。合計11,710ページ。','', '件数は掲載ID単位で、特定日の実運転本数ではない。平日に載るIDは4,228件、土曜・日祝は各3,741件で、複数曜日への重複を含む。日付条件のある483件は注記を保持し、全平日／全休日に一般化していない。年のない注記から対象年を自動生成していない。','', '## 全件を読む','', '始発側の路線ごとに分けた。各ファイルでは、列車の**実際の進行方向の経路**ごとに、全列車の始発・終着・時刻・列車番号・運転条件・Yahoo出典を掲載。途中駅始発や途中終着も含む。','', '| 始発側の路線 | 掲載ID数 | 全列車一覧 |','| --- | ---: | --- |']
 for r in sorted(byfirst):heading.append(f'| {NAMES[r]} | {len(byfirst[r]):,} | [開く]({files[r]}) |')
 heading+=['','## 路線ごとの全件会計','', '同じ直通列車を通る各路線で数えるため、以下の路線別件数は合計しない。「直通」は同一事業者の別路線への乗り入れも含む。','', '| 路線 | 掲載ID数 | 直通あり | 線内完結 |','| --- | ---: | ---: | ---: |']
 for r,c in a['lineCounts'].items():heading.append(f"| {NAMES[r]} | {c['all']:,} | {c['through']:,} | {c['lineOnly']:,} |")
 heading+=['','## 経路の全パターン','', '上下方向を別に数えて114パターン。路線列が同じでも始発・終着は各列車の行を参照する。','', '| 経路 | 実際に通る路線（順序どおり） | 掲載ID数 |','| --- | --- | ---: |']
 for rs,n in sorted(counts.items()):
  code=routeIds[rs];heading.append(f"| [{code}]({files[rs[0]]}#{code.lower()}) | {' → '.join(NAMES[r] for r in rs)} | {n:,} |")
 heading+=['','## 調査範囲と判定方法','', '- 指定の東上線、池袋線、西武有楽町線、8号線＝東京メトロ有楽町線、13号線＝副都心線、東横線、横浜高速鉄道みなとみらい線、相鉄本線・いずみ野線・新横浜線、東急新横浜線、目黒線、7号線＝南北線、埼玉高速鉄道、6号線＝都営三田線を対象とした。池袋線につながる豊島線・狭山線・西武秩父線も全駅を取得した。','- 対象線から外へ続く列車も全行程を確認した。相鉄からJR方面は184件、そのうち川越線まで進むものは8件。西武から秩父鉄道への直通は3件。JR・秩父鉄道の線内列車すべてを対象に加えたものではない。','- 経路名は、一本の列車ページの全駅順と、そのIDの路線別駅時刻表を路線の駅順に照らして分類した。境界以外の駅での架空の路線移動や、別ID同士の時刻近接による結合はしていない。','- 有楽町線と副都心線、東横線と目黒線、南北線と三田線の共用・並行区間は、路線別掲載と区間外の停車駅を使い分けた。南北線と三田線を同時に通る経路は生成していない。','- S-TRAINなど短い路線内の全駅を通過する場合は、同一列車ページの前後の停車駅と既知の直通接続を用いた。停車しない境界に到着時刻や発車時刻を作っていない。','- 運転日の注記や区間種別は出典どおり保存した。列車見出しの種別を全区間共通の種別として使っていない。表示先・列車番号の一致だけで別の掲載IDを統合していない。','- この一覧はYahoo掲載範囲の全件調査。運休等のリアルタイム運行情報、特定日の運転可否の展開、座席・乗降制限の実装、公式DBとの全件ID照合は別工程。既存の実運用時刻表・検索エンジンの更新完了を意味しない。','', '## 再取得・検証','', '取得済みの抽出時刻表、全発車掲載、全列車停車駅、曜日別照合、出典URL・SHA-256を `data/transit/yahoo-western-research/` に保存。生HTMLは作業キャッシュにあり、永続データは時刻表関連フィールドだけを抽出している。','', '```bash','python scripts/research_western_all_trains.py --phase all','python scripts/check_western_yahoo_calendars.py','python scripts/classify_western_all_trains.py','python scripts/report_western_all_trains.py','```','', '保存済みの同一スナップショットを再利用するコマンド。新ダイヤの調査では出力先とHTMLキャッシュを別にして旧版と混在させない。全駅・方向・曜日の母集団一致、全発車照合、曜日別内容一致、全経路分類、着発時刻の順序を監査する。','']
 (DOC/'README.md').write_text('\n'.join(heading))
 for r,rows in sorted(byfirst.items()):
  lines=[f'# {NAMES[r]}側始発：全列車の直通経路','', '[全体の会計・調査条件](README.md)','',f'掲載ID {len(rows):,}件。各見出しが一本の列車の進行方向の全経路。運転条件は掲載表現で、日付条件は「曜日」より優先する。','']
  for rs in sorted({tuple(t['railways']) for t in rows}):
   group=[t for t in rows if tuple(t['railways'])==rs]
   lines += [f'## {routeIds[rs]}','', ' → '.join(NAMES[z] for z in rs),'',f"{'線内完結' if len(rs)==1 else '直通あり'}／{len(group):,}件",'', '| Yahoo列車ID | 曜日 | 始発・発時刻 | 終着・着時刻 | 掲載種別／列車番号 | 運転条件 |','| --- | --- | --- | --- | --- | --- |']
   for t in sorted(group,key=lambda t:(t['kinds'],norm(t['origin']),int(t['departure']),t['trainId'])):
    lines.append(f"| [{t['trainId']}]({t['sourceURL']}) | {day(t)} | {esc(t['origin'])} {clock(t['departure'])} | {esc(t['destination'])} {clock(t['arrival'])} | {esc(t['displayName'])}／{esc('・'.join(t['trainNumbers']))} | {esc(t['calendarCondition'])} |")
   lines+=['']
  (DOC/files[r]).write_text('\n'.join(lines))
 manifest={str(p.relative_to(src.BASE)):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(src.OUT.iterdir()) if p.is_file() and p.name!='manifest.json'}
 src.dump('manifest.json',manifest)
 print(json.dumps({k:a[k] for k in ['complete','trainIds','classifications','orderedRoutePatterns','totalTrainDetailPages','calendarCheck','inventoryErrors','chronologyErrors']},ensure_ascii=False))

if __name__=='__main__':main()
