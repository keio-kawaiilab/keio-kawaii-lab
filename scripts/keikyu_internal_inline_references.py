#!/usr/bin/env python3
"""Read reciprocal inline continuation notes from Keikyu's official PDF.

The inline 「Nページから / 以下Nページ」 boxes are distinct from the
previous/next-publication headers. Require reciprocal printed-page references
AND both explicit origin/departure and destination/arrival annotations. Times
only validate those page-directed references; they never discover identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from keikyu_official_pdf import bbox_words
from keikyu_schedule_all_zushi_evidence import minute_of_hhmm, station_suffix_map
from keikyu_internal_official_evidence import parser


def extract_notes(stops, pdf_path, metadata):
    if hashlib.sha256(pdf_path.read_bytes()).hexdigest() != stops['source']['sha256']:
        raise ValueError('PDF bytes do not match source dataset')
    by_page = defaultdict(list)
    for f in stops['fragments']:
        by_page[f['page']].append(f)
    meta = {r['id']: r for r in metadata}
    names = station_suffix_map()
    names.update({'羽田空港': '.HanedaAirportTerminal1and2'})
    notes, rejected = [], []
    for page, fragments in sorted(by_page.items()):
        _, _, words = bbox_words(pdf_path, page)
        for word in words:
            if word.text != 'ページ':
                continue
            candidates = [f for f in fragments if f['sectionYMin'] < word.y < f['sectionYMax']
                          and abs(f['columnCenterX'] - word.x) < 3]
            if len(candidates) != 1:
                continue
            f = candidates[0]
            # A literal page number directly above the horizontal ページ label.
            pages = [w for w in words if re.fullmatch(r'\d{1,3}', w.text)
                     and abs(w.x-word.x) < .8 and 4 < word.y-w.y < 9]
            if len(pages) != 1:
                rejected.append({'fragment': f['id'], 'noteY': word.y, 'reason': 'page-number-not-singleton'})
                continue
            for side, lo, hi, event in [('origin', word.y+8, word.y+50, 'departure'),
                                      ('destination', word.y-65, word.y-12, 'arrival')]:
                chars = [w for w in words if lo < w.y < hi and 1.5 < w.x-word.x < 5
                         and re.fullmatch(r'[一-龥々・ＹＲＰA-Z]+', w.text)]
                label = ''.join(w.text for w in sorted(chars, key=lambda w:w.y))
                marker = '発' if side == 'origin' else '着'
                if not label.endswith(marker) or parser.norm(label[:-1]) not in names:
                    continue
                if not chars:
                    continue
                times = [w for w in words if min(c.y for c in chars)-4 < w.y < max(c.y for c in chars)+4
                         and -5 < w.x-word.x < -1.5 and re.fullmatch(r'\d{3,4}', w.text)
                         and minute_of_hhmm(w.text) is not None]
                if len(times) != 1:
                    rejected.append({'fragment': f['id'], 'noteY': word.y, 'label':label,
                                     'reason':'annotation-time-not-singleton'})
                    continue
                notes.append({'fragment': f['id'], 'page':page, 'printedPage':meta[f['id']]['printedPage'],
                              'calendar':f['calendar'], 'referencedPrintedPage':int(pages[0].text),
                              'side':side, 'station':label[:-1], 'suffix':names[parser.norm(label[:-1])],
                              'event':event, 'time':times[0].text, 'minute':minute_of_hhmm(times[0].text),
                              'noteY':round(word.y,3), 'columnX':round(word.x,3),
                              'pageNumberY':round(pages[0].y,3),
                              'literalLabel':label, 'literalPageToken':pages[0].text,
                              'timeX':round(times[0].x,3),'timeY':round(times[0].y,3)})
    return notes, rejected


def has_endpoint(f, note):
    suffixes = station_suffix_map()
    points = [p for p in f['stopTimes'] if suffixes.get(parser.norm(p['station'])) == note['suffix']
              and p['event'] == note['event'] and minute_of_hhmm(p['time']) == note['minute']]
    return len(points) == 1


def resolve_notes(stops, notes):
    by_id = {f['id']: f for f in stops['fragments']}
    origins = [n for n in notes if n['side']=='origin']
    destinations = [n for n in notes if n['side']=='destination']
    candidates=[]
    for dest in destinations:
        for origin in origins:
            if (origin['calendar'] != dest['calendar']
                or origin['printedPage'] != dest['referencedPrintedPage']
                or dest['printedPage'] != origin['referencedPrintedPage']):
                continue
            if not has_endpoint(by_id[dest['fragment']], origin) or not has_endpoint(by_id[origin['fragment']], dest):
                continue
            candidates.append({'fromFragment':dest['fragment'],'toFragment':origin['fragment'],
                               'calendar':dest['calendar'],'originNote':origin,'destinationNote':dest,
                               'evidence':'reciprocal-inline-pages-and-both-printed-endpoints'})
    outgoing=Counter(x['fromFragment'] for x in candidates)
    incoming=Counter(x['toFragment'] for x in candidates)
    links=[x for x in candidates if outgoing[x['fromFragment']]==1 and incoming[x['toFragment']]==1]
    rejected=[x for x in candidates if x not in links]
    # Every cycle is rejected; do not erase the source inventory.
    nxt={x['fromFragment']:x['toFragment'] for x in links}
    cyclic=set()
    for node in nxt:
        seen=set(); cursor=node
        while cursor in nxt:
            if cursor in seen:
                cyclic.update(seen); break
            seen.add(cursor); cursor=nxt[cursor]
    rejected += [x for x in links if x['fromFragment'] in cyclic]
    links=[x for x in links if x['fromFragment'] not in cyclic]
    return links,rejected


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--stops',required=True);ap.add_argument('--pdf',required=True)
    ap.add_argument('--metadata',default='docs/transit/keikyu-reciprocal-publication-audit.json')
    ap.add_argument('--output',required=True)
    a=ap.parse_args()
    stops=json.loads(Path(a.stops).read_text());m=json.loads(Path(a.metadata).read_text())
    if m['sourceSha256'] != stops['source']['sha256']:
        raise ValueError('metadata/source hash mismatch')
    notes,rejected=extract_notes(stops,Path(a.pdf),m['metadata'])
    links,ambiguous=resolve_notes(stops,notes)
    out={'version':1,'kind':'keikyu-internal-inline-page-reference-audit',
         'sourceSha256':stops['source']['sha256'],'notes':notes,'links':links,
         'rejectedExtraction':rejected,'rejectedLinks':ambiguous,
         'summary':{'notes':len(notes),'links':len(links),'rejectedExtraction':len(rejected),
                    'rejectedLinks':len(ambiguous),'noteSides':dict(Counter(n['side'] for n in notes))},
         'policy':{'reciprocalInlinePageReferencesRequired':True,'bothPrintedEndpointAnnotationsRequired':True,
                   'singletonEndpointsRequired':True,'clockTimeAloneProvesIdentity':False,
                   'trainNumberAloneProvesIdentity':False,'runtimeSameTrainPromotions':0}}
    Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out['summary'],ensure_ascii=False))

if __name__=='__main__':main()
