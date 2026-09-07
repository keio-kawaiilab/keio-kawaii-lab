"""Check every aligned boundary-time column, without a dwell-time cutoff.

This read-only coverage diagnostic checks whether the historical 0..4 minute
candidate filter omitted explicit continuation arrows. It never promotes IDs.
"""
import argparse
import hashlib
import json
import fitz
from pathlib import Path
from collections import Counter

from diagnose_sengakuji_toei_sequence_match import page_words, build_page_cache
from audit_sengakuji_published_sequences import classify_boundary
from keikyu_official_train_evidence import rows, direction, DEFAULT_WEEKDAY_URL, DEFAULT_HOLIDAY_URL


def audit(pdf_dir):
    results=[]
    for calendar,url in (('weekday',DEFAULT_WEEKDAY_URL),('holiday',DEFAULT_HOLIDAY_URL)):
        content=(pdf_dir/f'other_{calendar}.pdf').read_bytes()
        with fitz.open(stream=content,filetype='pdf') as pdf:
            pages=set(range(1,len(pdf)+1))
        for page,words in page_words(content,pages).items():
            rr=rows(words)
            cache=build_page_cache(words)
            for nr in [r for r in rr if '列車番号' in r['text']]:
                before=[r for r in rr if '泉岳寺' in r['text'] and 0<nr['y']-r['y']<70]
                after=[r for r in rr if '泉岳寺' in r['text'] and 0<r['y']-nr['y']<70]
                if not before or not after:continue
                a,b=max(before,key=lambda r:r['y']),min(after,key=lambda r:r['y'])
                travel=direction(a['text'],b['text'])
                if not travel:continue
                for first in cache['timeByY'].get(a['y'],[]):
                    matches=[c for c in cache['timeByY'].get(b['y'],[]) if abs(c['x']-first['x'])<5]
                    if len(matches)!=1:continue
                    second=matches[0]
                    c=dict(direction=travel,columnX=first['x'],
                        rowGeometry=dict(sourceBoundaryY=a['y'],targetBoundaryY=b['y'],boundaryTrainNumberY=nr['y']))
                    boundary=classify_boundary(dict(rows=rr,words=words),c)
                    results.append(dict(calendar=calendar,pdfPage=page,sourceUrl=url,sourceSha256=hashlib.sha256(content).hexdigest(),
                        sourceMinute=first['minute'],targetMinute=second['minute'],
                        dwellMinutes=(second['minute']-first['minute'])%1440,
                        **c,officialBoundaryClassification=boundary))
    return dict(kind='sengakuji-unfiltered-boundary-column-audit',version=1,
        columnCount=len(results),statusCounts=dict(Counter(r['officialBoundaryClassification']['status'] for r in results)),
        outsideHistoricalWindow=[r for r in results if r['dwellMinutes']>4],
        runtimeSameTrainPromotions=0,results=results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pdf-cache-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    r=audit(a.pdf_cache_dir)
    a.output.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k!='results'},ensure_ascii=False,indent=2))
