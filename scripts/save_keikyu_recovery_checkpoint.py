"""Validate and persist the complete recovered boundary inventory and source DB.

Boundary reconciliation completeness is separate from whole-Keikyu coverage
and runtime integration. Neither of the latter is declared complete here.
"""
import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

from verify_keikyu_official_stop_times import verify as verify_stops
from verify_keikyu_cross_page_identity_audit import verify as verify_graph
from verify_keikyu_independent_mother_set_audit import verify as verify_mother

POSITIVE='both-local-published-sequence-singleton'
TRANSFER='official-transfer-via-nishimagome'
RECOVERED=[('1775K',1087,1088),('1681H',1094,1094),('1729N',1098,1100),
           ('1773H',1102,1103),('1805H',1108,1110),('1785H',1114,1114),
           ('1825N',1120,1123),('1983K',1166,1167),('2252H',18,20)]


def verify_boundary(payload, unfiltered):
    results=payload['results']
    counts=Counter(r['publishedSequenceStatus'] for r in results)
    if counts != {POSITIVE:577,TRANSFER:4} or dict(counts)!=payload['statusCounts']:
        raise RuntimeError('Pinned 577-through / 4-transfer boundary inventory changed')
    if len({r['candidateId'] for r in results})!=581 or payload['officialColumnCandidateCount']!=581:
        raise RuntimeError('Missing or duplicate boundary identity')
    if payload['identityPolicy']['runtimeSameTrainPromotions']!=0 or payload['coverageComplete'] is not False:
        raise RuntimeError('Audit cannot claim runtime promotion or whole-system coverage')
    if len(unfiltered['results'])!=581 or unfiltered['outsideHistoricalWindow']:
        raise RuntimeError('Unfiltered source inventory differs; inspect all extra columns')
    sources={(s['calendar'],s['url']):s['sha256'] for s in payload['connectionSources']}
    for u in unfiltered['results']:
        if sources.get((u['calendar'],u['sourceUrl']))!=u['sourceSha256']:
            raise RuntimeError('Unfiltered PDF snapshot differs')
    for r in results:
        hits=[u for u in unfiltered['results'] if u['calendar']==r['calendar'] and u['direction']==r['direction']
              and u['pdfPage']==r['pdfPage'] and abs(u['columnX']-r['columnX'])<.05
              and u['sourceMinute']==r['sourceBoundaryMinute'] and u['targetMinute']==r['targetBoundaryMinute']]
        if len(hits)!=1 or hits[0]['officialBoundaryClassification']['status']!=r['officialBoundaryClassification']['status']:
            raise RuntimeError('Boundary is not uniquely supported by unfiltered source scan')
        if r['publishedSequenceStatus']==POSITIVE:
            b=r['officialBoundaryClassification']
            if b['status']!='official-continuation-arrow' or b['nishimagomeDepartureMinutes']:
                raise RuntimeError('Transfer/unknown marker misclassified as through')
            if len(r['keikyuSequenceMatches'])!=1 or len(r['toeiSequenceMatches'])!=1:
                raise RuntimeError('Local identity not singleton')
        elif len(r['transferToeiSequenceMatches'])!=1:
            raise RuntimeError('Transfer branch-train corroboration absent')
    for field in ('keikyuSequenceMatches','toeiSequenceMatches'):
        ids=[r[field][0] for r in results if r['publishedSequenceStatus']==POSITIVE]
        if len(set(ids))!=len(ids):raise RuntimeError('Duplicate local train consumption')
    recovered=[]
    for number,arrival,departure in RECOVERED:
        tid=f'odpt.TrainTimetable:Toei.Asakusa.{number}.Weekday'
        hits=[r for r in results if r['toeiSequenceMatches']==[tid] and r['sourceBoundaryMinute']==arrival
              and r['targetBoundaryMinute']==departure and r['publishedSequenceStatus']==POSITIVE]
        if len(hits)!=1:raise RuntimeError(f'Recovered user case missing: {number}')
        recovered.append(dict(toeiTimetableId=tid,candidateId=hits[0]['candidateId'],
                              keikyuPublicationGroup=hits[0]['keikyuSequenceMatches'][0]))
    return recovered


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work-dir',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,default=Path('docs/transit'))
    a=p.parse_args()
    def read(name):return json.loads((a.work_dir/name).read_text())
    stops=read('keikyu-recovered-stops.json')
    graph=read('keikyu-recovered-graph.json')
    mother=read('keikyu-recovered-mother.json')
    sequences=read('sengakuji-recovered-sequences.json')
    unfiltered=read('sengakuji-unfiltered-columns.json')
    checks=dict(stops=verify_stops(stops),graph=verify_graph(graph),mother=verify_mother(mother))
    cases=verify_boundary(sequences,unfiltered)
    a.output_dir.mkdir(parents=True,exist_ok=True)
    mapping={
        'keikyu-recovered-mother.json':'keikyu-independent-mother-set-audit.json',
        'keikyu-recovered-graph.json':'keikyu-calendar-cross-page-audit.json',
        'keikyu-recovered-reciprocal.json':'keikyu-reciprocal-publication-audit.json',
        'keikyu-recovered-calendar.json':'keikyu-printed-calendar-audit.json',
        'sengakuji-recovered-baseline.json':'sengakuji-independent-reconciliation-audit.json',
        'sengakuji-recovered-sequences.json':'sengakuji-published-sequence-audit.json',
        'sengakuji-unfiltered-columns.json':'sengakuji-unfiltered-column-audit.json',
    }
    saved={}
    for source,target in mapping.items():
        data=(json.dumps(read(source),ensure_ascii=False,indent=2)+'\n').encode()
        (a.output_dir/target).write_bytes(data)
        saved[target]=hashlib.sha256(data).hexdigest()
    packed=gzip.compress((json.dumps(stops,ensure_ascii=False,separators=(',',':'))+'\n').encode(),mtime=0)
    target='keikyu-independent-stop-times.json.gz'
    (a.output_dir/target).write_bytes(packed)
    saved[target]=hashlib.sha256(packed).hexdigest()
    if json.loads(gzip.decompress(packed))!=stops:raise RuntimeError('Compressed source DB round-trip failed')
    checkpoint=dict(version=1,kind='keikyu-geometry-recovery-checkpoint',sourceSha256=stops['source']['sha256'],
        boundaryReconciliationComplete=True,wholeKeikyuCoverageComplete=False,runtimeIntegrationComplete=False,
        runtimeSameTrainPromotions=0,statusCounts=sequences['statusCounts'],recoveredCases=cases,
        stopCounts=stops['totals'],verification=checks,filesSha256=saved,
        remaining=dict(unresolvedCells=stops['totals']['unresolvedTimeCells'],
            printedPageReferenceCells=sum(u['left']=='前の掲載ページ' for f in stops['fragments'] for u in f['unresolvedCells']),
            nonTimetableCalendarExcludedPages=stops['calendarExcludedPages']))
    (a.output_dir/'keikyu-recovery-checkpoint.json').write_text(json.dumps(checkpoint,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(checkpoint,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
