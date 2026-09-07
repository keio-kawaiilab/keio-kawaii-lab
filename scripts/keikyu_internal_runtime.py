#!/usr/bin/env python3
"""Project verified official network journeys without inventing junction times."""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

NETWORK=Path('data/transit/keikyu/timetables/official-internal-network.json')
CORE={'odpt.Railway:Keikyu.'+s for s in ['Main','Airport','Kurihama','Zushi']}


def projections(network):
    if network.get('timeBasis')!='train-timetable-network':raise ValueError('wrong network schema')
    if set(network['railways'])!=CORE:raise ValueError('internal network scope changed')
    by_line=defaultdict(list);identities=[]
    for trip in network['trips']:
        if len(trip)!=6 or len(trip[4])!=len(trip[3])-1:raise ValueError('malformed official trip')
        parts=[]
        for i,rails in enumerate(trip[4]):
            # Passing an un-timed junction does not create a boarding stop.
            if len(rails)!=1:continue
            rail=network['railways'][rails[0]]
            if parts and parts[-1]['railway']==rail and parts[-1]['end']==i:
                parts[-1]['end']=i+1
            else:parts.append({'railway':rail,'start':i,'end':i+1})
        refs=[]
        for ordinal,part in enumerate(parts):
            tid=trip[5]+':'+part['railway'].rsplit('.',1)[-1]+':'+str(ordinal)
            st=trip[3][part['start']:part['end']+1]
            encoded=[trip[0],trip[1],trip[2],st,'',trip[5],tid]
            by_line[part['railway']].append(encoded)
            refs.append({'timetableId':tid,'railway':part['railway'],'stops':st})
        identities.append({'journeyId':trip[5],'parts':refs})
    tables={rail:{'version':1,'railway':rail,'timeBasis':'train-timetable','destinationAuthoritative':False,
                  'calendars':network['calendars'],'trainTypes':network['trainTypes'],
                  'stations':network['stations'],'trips':rows,'identityBasis':'official-keikyu-network-projection',
                  'sourceSha256':network['sourceSha256']} for rail,rows in by_line.items()}
    return tables,identities


def install(network_path=NETWORK):
    if not network_path.exists():return
    network=json.loads(network_path.read_text())
    if network.get('internalCoverageComplete') is not True:
        raise ValueError('unverified internal network cannot replace line timetables')
    tables,_=projections(network)
    folder=network_path.parent.parent
    idxpath=folder/'timetable-index.json';index=json.loads(idxpath.read_text())
    for railway,table in tables.items():
        filename='timetables/official-internal-'+railway.rsplit('.',1)[-1].lower()+'.json'
        (folder/filename).write_text(json.dumps(table,ensure_ascii=False,separators=(',',':'))+'\n')
        index['lines'][railway]={'file':filename,'trips':len(table['trips']),
              'connections':sum(len(t[3])-1 for t in table['trips']),
              'timeBasis':'train-timetable','source':'official-full-timetable',
              'identityBasis':'official-keikyu-network-projection'}
    index['network']={'id':'keikyu-official-internal-network','file':'timetables/'+network_path.name,
                     'railways':network['railways'],'trips':len(network['trips']),
                     'timeBasis':'train-timetable-network','identityBasis':'explicit-official-column-and-page-references'}
    index['version']=max(2,index.get('version',1))
    idxpath.write_text(json.dumps(index,ensure_ascii=False,separators=(',',':'))+'\n')


def apply(fragments,edges,network_path=NETWORK):
    if not network_path.exists():return edges
    network=json.loads(network_path.read_text())
    if network.get('internalCoverageComplete') is not True:raise ValueError('incomplete internal network')
    _,identities=projections(network)
    by_tt={f.get('timetableId'):f for f in fragments if f.get('timetableId')}
    out=list(edges);seen={(e['fromFragment'],e['toFragment'])for e in edges}
    for identity in identities:
        parts=identity['parts']
        for part in parts:
            f=by_tt.get(part['timetableId'])
            expected=[[network['stations'][s[0]],s[1],s[2]]for s in part['stops']]
            if not f or f['railway']!=part['railway'] or f['stops']!=expected:
                raise ValueError('official network projection is stale: '+part['timetableId'])
        for a,b in zip(parts,parts[1:]):
            if a['railway']==b['railway']:continue
            source,target=by_tt[a['timetableId']],by_tt[b['timetableId']]
            if source['calendar']!=target['calendar']:raise ValueError('cross-calendar identity')
            pair=(source['id'],target['id'])
            if pair in seen:continue
            seen.add(pair)
            out.append({'fromFragment':pair[0],'toFragment':pair[1],'classification':'same-train',
                        'identityLevel':'evidence-backed','evidence':['keikyu-official-complete-internal-network',identity['journeyId']],
                        'sourceUrls':['https://www.keikyu.co.jp/ride/kakueki/pdf/schedule_all.pdf'],
                        'boundary':{'fromRailway':a['railway'],'toRailway':b['railway']}})
    return retain_verified_external(fragments,out,network,identities,network_path)


def retain_verified_external(fragments,edges,network,identities,network_path):
    # Fixture networks do not opt into the saved, independently reconciled
    # external inventory. Production uses the full independently verified inventory.
    if 'journeyEvidence' not in network:return edges
    from keikyu_published_station_names import station_suffix_map, norm, PDF_TO_ODPT_SUFFIX
    audit=json.loads(Path('docs/transit/sengakuji-published-sequence-audit.json').read_text())
    if audit['sourceSha256']!=network['sourceSha256']:raise ValueError('external/internal source revision mismatch')
    from save_keikyu_recovery_checkpoint import verify_boundary
    unfiltered=json.loads(Path('docs/transit/sengakuji-unfiltered-column-audit.json').read_text())
    verify_boundary(audit, unfiltered)
    toei_raw=Path('data/transit/toei/timetables/899209dea5fc3a.json').read_bytes()
    if hashlib.sha256(toei_raw).hexdigest()!=audit['toeiSourceSha256']:
        raise ValueError('Toei source revision changed; independent reconciliation required')
    requested={(r['toeiSequenceMatches'][0],r['direction'])for r in audit['results']
               if r['publishedSequenceStatus']=='both-local-published-sequence-singleton'}
    if len(requested)!=577:raise ValueError('Incomplete full Sengakuji inventory')
    by_tt={f.get('timetableId'):f for f in fragments if f.get('timetableId')}
    member={fid:r['id']for r in network['journeyEvidence']for fid in r['members']}
    parts={r['journeyId']:r['parts']for r in identities}
    trips={r[5]:r for r in network['trips']}
    suffixes=station_suffix_map();out=list(edges);seen=set()
    for r in audit['results']:
        if r['publishedSequenceStatus']!='both-local-published-sequence-singleton':continue
        if len(r['toeiSequenceMatches'])!=1:raise ValueError('ambiguous external timetable')
        key=(r['toeiSequenceMatches'][0],r['direction'])
        if key not in requested:continue
        if r['officialBoundaryClassification']['status']!='official-continuation-arrow':
            raise ValueError('transfer column cannot become retained direct service')
        columns=r['supportingOfficialColumns'][r['keikyuSequenceMatches'][0]]
        journeys={member.get(fid)for fid in columns}
        if len(journeys)!=1 or None in journeys:raise ValueError('ambiguous updated Keikyu journey')
        jid=next(iter(journeys));toei=by_tt.get(key[0])
        if not toei:raise ValueError('stale Toei source')
        for point in r['toeiFingerprint']:
            suffix='.'+PDF_TO_ODPT_SUFFIX[point['station']]
            if not any(s[0].endswith(suffix) and point['minute'] in [t%1440 for t in s[1:3]if t is not None]
                       for s in toei['stops']):raise ValueError('Toei source sequence changed')
        for point in r['keikyuFingerprint']:
            suffix=suffixes[norm(point['station'])]
            if not any(network['stations'][s[0]].endswith(suffix) and point['minute'] in [t%1440 for t in s[1:3]if t is not None]
                       for s in trips[jid][3]):raise ValueError('Keikyu published sequence changed')
        main=[p for p in parts[jid]if p['railway']=='odpt.Railway:Keikyu.Main'
              and any(network['stations'][s[0]].endswith('.Sengakuji')for s in p['stops'])]
        if len(main)!=1:raise ValueError('missing retained Main projection')
        keikyu=by_tt[main[0]['timetableId']]
        source,target=(toei,keikyu)if r['direction']=='toei-to-keikyu'else(keikyu,toei)
        out.append({'fromFragment':source['id'],'toFragment':target['id'],'classification':'same-train',
                    'identityLevel':'evidence-backed','evidence':['keikyu-official-sengakuji-exact-sequence',r['candidateId']],
                    'sourceUrls':[r['sourceUrl']],
                    'boundary':{'station':'泉岳寺','fromRailway':source['railway'],'toRailway':target['railway']}})
        seen.add(key)
    if seen!=requested:raise ValueError('retained external inventory is incomplete')
    return out


if __name__=='__main__':install()
