#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PAGES = [
    'https://seibu.ekitan.com/norikae/timetable/station/232-1/d1?dw=0',
    'https://seibu.ekitan.com/norikae/timetable/station/232-1/d1?dw=1',
]
NEEDLES = ('onetraintimetable', 'tx=', 'sf=', 'time=', 'onclick', 'train', 'diagram', 'timetable')


def clean(value: str) -> str:
    return re.sub(r'\s+', ' ', value or '').strip()


def inspect(url: str) -> dict:
    r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; KeioKawaiiLabTransitDB/6.1)'}, timeout=(20, 60))
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding or 'utf-8'
    text = r.text
    soup = BeautifulSoup(text, 'html.parser')

    scripts = []
    for tag in soup.find_all('script'):
        src = tag.get('src')
        body = clean(tag.get_text(' ', strip=True))
        scripts.append({
            'src': urljoin(url, src) if src else '',
            'inlineSample': body[:1000] if body else '',
            'needleHits': [n for n in NEEDLES if n.lower() in (body or '').lower()],
        })

    forms = []
    for form in soup.find_all('form'):
        inputs = []
        for inp in form.find_all(['input', 'button', 'select']):
            inputs.append({
                'tag': inp.name,
                'type': inp.get('type', ''),
                'name': inp.get('name', ''),
                'value': inp.get('value', ''),
                'id': inp.get('id', ''),
                'class': inp.get('class', []),
                'data': {k: v for k, v in inp.attrs.items() if str(k).startswith('data-')},
                'onclick': inp.get('onclick', ''),
                'text': clean(inp.get_text(' ', strip=True))[:100],
            })
        forms.append({
            'action': urljoin(url, form.get('action', '')),
            'method': form.get('method', ''),
            'id': form.get('id', ''),
            'class': form.get('class', []),
            'inputs': inputs[:120],
        })

    clickable = []
    for tag in soup.find_all(['a', 'button', 'li', 'span', 'div']):
        attrs = tag.attrs or {}
        body = clean(tag.get_text(' ', strip=True))
        interesting = (
            bool(tag.get('onclick')) or
            any(str(k).startswith('data-') for k in attrs) or
            bool(re.search(r'\b\d{1,2}:\d{2}\b', body)) or
            'train' in str(attrs).lower()
        )
        if not interesting:
            continue
        clickable.append({
            'tag': tag.name,
            'href': urljoin(url, tag.get('href')) if tag.get('href') else '',
            'id': tag.get('id', ''),
            'class': tag.get('class', []),
            'onclick': tag.get('onclick', ''),
            'data': {k: v for k, v in attrs.items() if str(k).startswith('data-')},
            'text': body[:220],
        })
        if len(clickable) >= 240:
            break

    contexts = []
    lower = text.lower()
    for needle in NEEDLES:
        start = 0
        for _ in range(8):
            pos = lower.find(needle.lower(), start)
            if pos < 0:
                break
            contexts.append({'needle': needle, 'sample': clean(text[max(0, pos-400):pos+800])[:1400]})
            start = pos + len(needle)

    return {
        'url': url,
        'bytes': len(text.encode('utf-8')),
        'title': clean(soup.title.get_text(' ', strip=True) if soup.title else ''),
        'scripts': scripts,
        'forms': forms,
        'clickable': clickable,
        'contexts': contexts,
    }


def main() -> None:
    report = {'pages': [inspect(url) for url in PAGES]}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
