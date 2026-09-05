#!/usr/bin/env python3
import io, json, requests, pdfplumber
URL='https://www.seiburailway.jp/railway/reservedtrain/file/20260314_S-TRAIN_timetable.pdf'
r=requests.get(URL,timeout=(20,90),headers={'User-Agent':'Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/9.0)'})
r.raise_for_status()
with pdfplumber.open(io.BytesIO(r.content)) as pdf:
    p=pdf.pages[0]
    words=p.extract_words(x_tolerance=2,y_tolerance=2,keep_blank_chars=False)
    targets={'西武秩父','飯能','入間市','所沢','石神井公園','池袋','新宿三丁目','渋谷','自由が丘','横浜','みなとみらい','元町・中華街','豊洲','有楽町','飯田橋','練馬','小手指'}
    hits=[{k:w[k] for k in ('text','x0','x1','top','bottom')} for w in words if w.get('text') in targets or 'S-TRAIN' in w.get('text','') or '土曜' in w.get('text','') or '休日' in w.get('text','') or ':' in w.get('text','')]
    print('PAGE',p.width,p.height,'WORDS',len(words),'HITS',len(hits))
    print(json.dumps(hits,ensure_ascii=False,indent=2))
    tables=p.extract_tables() or []
    print('TABLE_COUNT',len(tables))
    for i,t in enumerate(tables):
        print('TABLE',i,'ROWS',len(t),'COLS',max((len(r) for r in t),default=0))
        print(json.dumps(t[:8],ensure_ascii=False))
