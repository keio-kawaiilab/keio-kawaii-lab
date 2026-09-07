#!/usr/bin/env python3
"""Assemble route-ready Keikyu trains only from explicit official identities."""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict, deque
from pathlib import Path

from audit_sengakuji_published_sequences import publication_groups, verify_metadata_matches_stops
from keikyu_internal_inline_references import resolve_notes
from keikyu_internal_inline_references import has_endpoint
from keikyu_official_pdf import bbox_words, cluster_by_y, _label_span
from keikyu_schedule_all_zushi_evidence import station_suffix_map, minute_of_hhmm
from keikyu_internal_official_evidence import parser
from verify_keikyu_official_stop_times import verify as verify_stops

CORE={'odpt.Railway:Keikyu.'+x for x in ['Main','Airport','Kurihama','Zushi']}
REVIEWED_SHA='e10b1c6efd92f40b0dae6d712b65c2391584b9134cd653c74fe78548ad681b63'


def reviewed_terminal_label(stops, inline, pdf):
    """Resolve the literal p88 terminal-label typo from two inline endpoints.

    The PDF prints 羽田第１・第３ in the terminal row. Its two reciprocal
    continuation notes explicitly identify that row's 14:26 and 14:46 cells
    as 羽田空港着. The raw typo and former parser assignment are retained.
    This correction is bound to the reviewed PDF bytes and exact row geometry.
    """
    if stops['source']['sha256']!=REVIEWED_SHA:
        raise ValueError('new PDF revision requires review of terminal-label discrepancy')
    _,_,words=bbox_words(pdf,93)
    if not any(w.text=='羽田第１・第３' and abs(w.y-277.62)<.05 for w in words):
        raise ValueError('reviewed literal terminal typo not present')
    by_id={f['id']:f for f in stops['fragments']}
    for target,source,minute in [('keikyu-official-pdf:p093:s00:c03','keikyu-official-pdf:p119:s00:c20',866),
                                 ('keikyu-official-pdf:p093:s00:c16','keikyu-official-pdf:p120:s00:c08',886)]:
        orig=[n for n in inline['notes'] if n['fragment']==target and n['side']=='origin']
        dest=[n for n in inline['notes'] if n['fragment']==source and n['side']=='destination']
        if (len(orig)!=1 or len(dest)!=1 or dest[0]['minute']!=minute
            or dest[0]['suffix']!='.HanedaAirportTerminal1and2'
            or orig[0]['referencedPrintedPage']!=dest[0]['printedPage']
            or dest[0]['referencedPrintedPage']!=orig[0]['printedPage']
            or not has_endpoint(by_id[source],orig[0])):
            raise ValueError('terminal-label corroborating notes do not match')
    corrections=[]
    for f in stops['fragments']:
        if f['page']!=93:continue
        for cell in f['stopTimes']:
            if abs(cell['rowY']-277.32)<.05:
                if cell['station']!='雑色' or cell['event']!='arrival':
                    raise ValueError('unexpected former terminal-row interpretation')
                old=copy.deepcopy(cell)
                cell['station']='羽田空港第１・第２ターミナル'
                cell['resolution']='same-row-station-title'
                cell['reviewedCorrection']='p088-terminal-label-confirmed-by-two-inline-arrivals'
                corrections.append({'fragment':f['id'],'literalLabel':'羽田第１・第３',
                                    'formerRecord':old,'correctedRecord':copy.deepcopy(cell)})
    if len(corrections)!=6:raise ValueError('terminal typo population changed')
    stops['reviewedSourceCorrections']=corrections


def reviewed_forward_reference(stops, inline):
    """One conflicting return page is resolved by an explicit forward page.

    Printed p116 directs this train to p89, with arrival 15:26. The p89
    column prints the exact same origin 14:25, Kamata arrival 15:13 and
    departure 15:14, and terminal arrival 15:26; its return-page note says
    115. Keep that discrepancy. Never make an unrestricted time-based fallback.
    """
    if stops['source']['sha256']!=REVIEWED_SHA:raise ValueError('unreviewed source revision')
    source='keikyu-official-pdf:p121:s00:c06';target='keikyu-official-pdf:p094:s00:c17'
    by_id={f['id']:f for f in stops['fragments']}
    a=[n for n in inline['notes'] if n['fragment']==source and n['side']=='destination']
    b=[n for n in inline['notes'] if n['fragment']==target and n['side']=='origin']
    if len(a)!=1 or len(b)!=1:raise ValueError('reviewed page-note population changed')
    a,b=a[0],b[0]
    if (a['printedPage'],a['referencedPrintedPage'],b['printedPage'],b['referencedPrintedPage'],a['minute'],b['minute'])!=(116,89,89,115,926,865):
        raise ValueError('reviewed literal forward/return note changed')
    if not has_endpoint(by_id[source],b) or not has_endpoint(by_id[target],a):
        raise ValueError('forward reference endpoint mismatch')
    points=[('arrival',913),('departure',914)]
    for f in [by_id[source],by_id[target]]:
        for event,minute in points:
            if not has_endpoint(f,{'suffix':'.KeikyuKamata','event':event,'minute':minute}):
                raise ValueError('reviewed exact Kamata sequence mismatch')
    return {'fromFragment':source,'toFragment':target,'calendar':'holiday',
            'evidence':'reviewed-explicit-forward-page-and-four-exact-published-events',
            'originNote':b,'destinationNote':a,'boundaryEvents':points,
            'returnPageConflict':{'printed':115,'sourcePrintedPage':116},'sourceSha256':REVIEWED_SHA}


def clean_annotations(stops, inline):
    """A note's printed time/page number is metadata, never a station event."""
    out=copy.deepcopy(stops)
    by_id={f['id']:f for f in out['fragments']}
    removed=[]
    for note in inline['notes']:
        f=by_id[note['fragment']]
        for token,y,kind in [(note['time'],note['timeY'],'inline-endpoint'),
                             (note['literalPageToken'],note['pageNumberY'],'inline-page-reference')]:
            hits=[p for p in f['stopTimes'] if p['time']==token and abs(p['rowY']-y)<=1.9]
            if len(hits)>1:raise ValueError('ambiguous annotation cell')
            for hit in hits:
                f['stopTimes'].remove(hit)
                f['unresolvedCells'].append({'time':token,'rowY':hit['rowY'],'left':'',
                    'marker':None,'stationMatches':[], 'classification':kind,
                    'annotationEvidence':note,'formerStationAssignment':hit})
                removed.append({'fragment':f['id'],'record':hit,'classification':kind})
        f['unresolvedCells'].sort(key=lambda p:p['rowY'])
    for page in out['pages']:
        for section in page['sections']:
            fs=[f for f in by_id.values() if f['page']==page['page'] and f['section']==section['section']]
            section['resolvedTimeCells']=sum(len(f['stopTimes']) for f in fs)
            section['unresolvedTimeCells']=sum(len(f['unresolvedCells']) for f in fs)
        for key in ['resolvedTimeCells','unresolvedTimeCells']:
            page[key]=sum(s[key] for s in page['sections'])
    for key in ['resolvedTimeCells','unresolvedTimeCells']:
        out['totals'][key]=sum(p[key] for p in out['pages'])
    out['annotationReclassification']=removed
    verify_stops(out)
    return out


def classify_remaining_cells(stops,inline,pdf):
    notes=defaultdict(list)
    for n in inline['notes']:
        notes[n['fragment']].extend([(n['time'],n['timeY'],'inline-endpoint'),
                                    (n['literalPageToken'],n['pageNumberY'],'inline-page-reference')])
    cache={};counts=Counter();unclassified=[]
    for f in stops['fragments']:
        if not f['unresolvedCells']:continue
        if f['page'] not in cache:
            _,_,ws=bbox_words(pdf,f['page'])
            labels=[]
            for row in cluster_by_y(ws):
                for label in ['始発','終着']:
                    span=_label_span(row,label)
                    if span and span[1]<140:
                        labels.append((sum(w.y for w in row)/len(row),label))
            cache[f['page']]=(ws,labels)
        ws,labels=cache[f['page']]
        for c in f['unresolvedCells']:
            kind=c.get('classification')
            proof={}
            if not kind and c.get('left')=='前の掲載ページ':kind='previous-page-reference'
            if not kind:
                hits=[k for t,y,k in notes[f['id']] if t==c['time'] and abs(y-c['rowY'])<=1.9]
                if len(hits)==1:kind=hits[0]
            if not kind:
                hits=[(y,label)for y,label in labels if abs(y-c['rowY'])<4]
                if len(hits)==1:
                    kind='printed-origin-or-terminal-header';proof={'labelRowY':hits[0][0],'label':hits[0][1]}
            if not kind:
                x=f['columnCenterX'];y=c['rowY']
                times=[w for w in ws if w.text==c['time'] and -5<w.x-x<-1.5 and abs(w.y-y)<=1.9]
                chars=[w for w in ws if y-16<w.y<y+16 and 1.5<w.x-x<5
                       and re.fullmatch(r'[一-龥々・ＹＲＰA-Z]+',w.text)]
                label=''.join(w.text for w in sorted(chars,key=lambda w:w.y))
                if len(times)==1 and len(label)>=3 and label.endswith(('発','着')):
                    kind='inline-external-endpoint';proof={'literalLabel':label,'timeX':times[0].x,'timeY':times[0].y}
            if not kind:kind='unclassified';unclassified.append({'fragment':f['id'],'cell':c})
            c['classification']=kind
            if proof:c['classificationEvidence']=proof
            counts[kind]+=1
    return {'counts':dict(counts),'unclassified':unclassified}


def groups_for(stops, mother, reciprocal, inline):
    verify_metadata_matches_stops(reciprocal, stops)
    _,groups=publication_groups(mother,reciprocal)
    links,rejected=resolve_notes(stops,inline['notes'])
    if rejected:raise ValueError('ambiguous inline link candidates')
    links.append(reviewed_forward_reference(stops,inline))
    member={fid:g for g,ids in groups.items() for fid in ids}
    parent={g:g for g in groups}
    def find(g):
        while parent[g]!=g:parent[g]=parent[parent[g]];g=parent[g]
        return g
    for link in links:
        a,b=find(member[link['fromFragment']]),find(member[link['toFragment']])
        parent[max(a,b)]=min(a,b)
    merged=defaultdict(list)
    for g,ids in groups.items():merged[find(g)].extend(ids)
    return {g:sorted(ids) for g,ids in sorted(merged.items())},links


def assemble(stops,groups):
    fs={f['id']:f for f in stops['fragments']};suffixes=station_suffix_map();results=[]
    for g,ids in groups.items():
        events=defaultdict(lambda:defaultdict(set));adj=defaultdict(set);before=defaultdict(set)
        calendars={fs[fid]['calendar'] for fid in ids}
        if len(calendars)!=1:raise ValueError('mixed service calendars')
        for fid in ids:
            last=None
            for st in fs[fid]['stopTimes']:
                suffix=suffixes.get(parser.norm(st['station']))
                if not suffix:continue
                minute=minute_of_hhmm(st['time']);minute+=1440 if minute<180 else 0
                events[suffix][st['event']].add(minute)
                if last and last!=suffix:adj[last].add(suffix);before[suffix].add(last)
                last=suffix
        bad=[['conflicting-station-event',k,ev,sorted(v)] for k,vals in events.items() for ev,v in vals.items() if len(v)>1]
        incoming={k:set(before[k]) for k in events};order=[];ready=sorted(k for k in events if not incoming[k])
        while ready:
            if len(ready)!=1:bad.append(['ambiguous-printed-order',list(ready)])
            k=ready.pop(0);order.append(k)
            for nxt in adj[k]:
                incoming[nxt].discard(k)
                if not incoming[nxt] and nxt not in order and nxt not in ready:ready.append(nxt)
            ready.sort()
        if len(order)!=len(events):bad.append(['cyclic-printed-order'])
        seq=[];last=-1
        for st in order:
            arr=sorted(events[st]['arrival']);dep=sorted(events[st]['departure'])
            row=[st,arr[0]if arr else None,dep[0]if dep else None];seq.append(row)
            for t in row[1:]:
                if t is not None:
                    if t<last:bad.append(['time-regression',st,last,t])
                    last=t
        results.append({'group':g,'members':ids,'calendar':next(iter(calendars)),
                        'stops':seq,'issues':bad})
    return results


def topology(entities):
    station_by_id={s['owl:sameAs']:s for s in entities['Station']}
    ids_by_suffix=defaultdict(set);graph=defaultdict(list)
    for line in entities['Railway']:
        rail=line['owl:sameAs']
        if rail not in CORE:continue
        order=[s['odpt:station'] for s in sorted(line['odpt:stationOrder'],key=lambda x:x['odpt:index'])]
        for sid in order:ids_by_suffix['.'+sid.rsplit('.',1)[-1]].add(sid)
        for a,b in zip(order,order[1:]):
            a,b='.'+a.rsplit('.',1)[-1],'.'+b.rsplit('.',1)[-1]
            graph[a].append((b,rail));graph[b].append((a,rail))
    # This four-line network is a tree; no shortest-time or ambiguous routing.
    if sum(len(v) for v in graph.values())//2 != len(graph)-1:
        raise ValueError('Keikyu internal topology is no longer a tree')
    return graph,{k:sorted(v)[0]for k,v in ids_by_suffix.items()}


def station_path(graph,source,target):
    queue=deque([(source,[],[source])]);seen={source}
    while queue:
        node,rails,nodes=queue.popleft()
        if node==target:return rails,nodes
        for nxt,rail in graph[node]:
            if nxt not in seen:seen.add(nxt);queue.append((nxt,rails+[rail],nodes+[nxt]))
    raise ValueError('disconnected station pair')


def materialize(assembled,entities):
    graph,station_ids=topology(entities)
    railways=sorted(CORE);stations=sorted(station_ids.values());station_idx={s:i for i,s in enumerate(stations)}
    trips=[];reports=[]
    for row in assembled:
        if row['issues'] or len(row['stops'])<2:continue
        links=[];nodes_seen=set();issues=[]
        for a,b in zip(row['stops'],row['stops'][1:]):
            rails,nodes=station_path(graph,a[0],b[0])
            if set(nodes[1:]) & nodes_seen:issues.append('route-revisits-station')
            nodes_seen.update(nodes)
            compact=[]
            for rail in rails:
                if not compact or compact[-1]!=rail:compact.append(rail)
            links.append([railways.index(r)for r in compact])
        if issues:
            row['issues'].extend([[issue]for issue in issues]);continue
        seq=[[station_idx[station_ids[st]],arr,dep]for st,arr,dep in row['stops']]
        tripid='keikyu-official:'+hashlib.sha256(row['group'].encode()).hexdigest()[:24]
        trips.append([0 if row['calendar']=='weekday' else 1,0,'',seq,links,tripid])
        path=[]
        for ls in links:
            for i in ls:
                if not path or path[-1]!=railways[i]:path.append(railways[i])
        reports.append({'id':tripid,'group':row['group'],'calendar':row['calendar'],
                        'railwayPath':path,'members':row['members'],'stopCount':len(seq)})
    return {'version':1,'timeBasis':'train-timetable-network','source':'Keikyu official full timetable',
            'calendars':['odpt.Calendar:Weekday','odpt.Calendar:SaturdayHoliday'],
            'trainTypes':[''],'railways':railways,'stations':stations,'trips':trips,
            'journeyEvidence':reports},reports


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--stops',required=True);ap.add_argument('--inline',required=True)
    ap.add_argument('--output',required=True);ap.add_argument('--report',required=True)
    ap.add_argument('--pdf',required=True);ap.add_argument('--clean-stops',required=True)
    a=ap.parse_args();load=lambda p:json.loads(Path(p).read_text())
    raw=load(a.stops);inline=load(a.inline);stops=clean_annotations(raw,inline)
    if hashlib.sha256(Path(a.pdf).read_bytes()).hexdigest()!=stops['source']['sha256']:
        raise ValueError('PDF source mismatch')
    reviewed_terminal_label(stops,inline,Path(a.pdf))
    cell_audit=classify_remaining_cells(stops,inline,Path(a.pdf))
    mother=load('docs/transit/keikyu-independent-mother-set-audit.json')
    reciprocal=load('docs/transit/keikyu-reciprocal-publication-audit.json')
    groups,links=groups_for(stops,mother,reciprocal,inline)
    assembled=assemble(stops,groups);network,trips=materialize(assembled,load('data/transit/keikyu/entities.json'))
    used_origins=Counter(link['toFragment']for link in links)
    used_destinations=Counter(link['fromFragment']for link in links)
    unmatched_notes=[n for n in inline['notes'] if
        (used_origins if n['side']=='origin' else used_destinations)[n['fragment']]!=1]
    eligible=[r for r in assembled if len(r['stops'])>=2]
    complete=(not cell_audit['unclassified'] and not unmatched_notes
              and not any(r['issues']for r in assembled) and len(eligible)==len(trips))
    network.update({'sourceSha256':stops['source']['sha256'],'internalCoverageComplete':complete,
                    'identityPolicy':{'clockTimeAloneProvesIdentity':False,'trainNumberAloneProvesIdentity':False,
                                      'allPublishedColumnsAccountedFor':True,'explicitPageReferencesRequired':True}})
    report={'version':1,'sourceSha256':stops['source']['sha256'],'summary':{
        'groups':len(groups),'routeTrips':len(trips),'throughTrips':sum(len(r['railwayPath'])>1 for r in trips),
        'inlineLinks':len(links),'reclassifiedAnnotationCells':len(stops['annotationReclassification']),
        'unclassifiedCells':len(cell_audit['unclassified']),
        'unassembledGroups':sum(bool(r['issues'])for r in assembled)},
        'groups':assembled,'trips':trips,'inlineLinks':links,'cellAudit':cell_audit,
        'unmatchedInlineNotes':unmatched_notes,
        'coverageComplete':complete,'runtimeIntegrated':False,
        'scope':'Keikyu internal Main/Airport/Kurihama/Zushi only; external continuations remain separate'}
    Path(a.output).write_text(json.dumps(network,ensure_ascii=False,separators=(',',':'))+'\n')
    Path(a.report).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    Path(a.clean_stops).write_text(json.dumps(stops,ensure_ascii=False))
    print(json.dumps(report['summary'],ensure_ascii=False))
    for r in assembled:
        if r['issues']:print(r['group'],r['issues'][:3])

if __name__=='__main__':main()
