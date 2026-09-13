"""Restore reviewed sale observations on their exact existing performance.

This runs after physical-performance normalization. Acquisition refreshes and
Ohanami's legacy two-show correction cannot erase the reviewed sale record.
Newer observations on the same ticket URL take precedence over review status.
"""
from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl

REGISTRY = Path(__file__).resolve().parents[1] / 'data/verified-general-sales.json'


def ticket_key(url):
    parts = urlsplit(str(url or ''))
    params = dict(parse_qsl(parts.query))
    if parts.hostname in ('t.pia.jp', 'ticket.pia.jp'):
        if any(params.get(k) for k in ('eventCd', 'rlsCd', 'lotRlsCd')):
            return tuple(params.get(k, '') for k in ('eventCd', 'rlsCd', 'lotRlsCd'))
    return str(url or '')


def apply_verified_general_sales(events, observations=None):
    observations = observations if observations is not None else json.loads(REGISTRY.read_text())['observations']
    for row in observations:
        matches = [e for e in events if e.get('entityType') == 'performance'
                   and e.get('group') == row['group'] and e.get('eventDate') == row['eventDate']
                   and e.get('startTime') == row['startTime']
                   and row['titleContains'] in str(e.get('eventTitle') or e.get('title') or '')]
        if not matches:
            continue  # Do not invent a performance if collection no longer has it.
        if len(matches) != 1:
            raise ValueError('Ambiguous reviewed general sale: ' + row['id'])
        event = matches[0]
        offers = event.setdefault('offers', [])
        review = deepcopy(row['offer'])
        review['sourceRowId'] = row['id']
        review['sourceChannel'] = 'verified-general-sale'
        existing = next((o for o in offers if o.get('provider') == review['provider']
                         and (ticket_key(o.get('url')) == ticket_key(review['url'])
                              or (o.get('sourceChannel') == 'promoter-general-sale' and o.get('applyStart') == review['applyStart']))), None)
        if existing is None:
            offers.append(review)
        else:
            # Missing facts are filled; a live collector's newer availability is preserved.
            for key, value in review.items():
                if not existing.get(key) and value is not None:
                    existing[key] = value
            if existing.get('sourceChannel') == 'promoter-general-sale':
                existing['url'] = review['url']
                existing['ticketType'] = review['ticketType']
            if str(existing.get('sourceObservedAt') or '') <= review['sourceObservedAt']:
                existing['applicationStatus'] = review['applicationStatus']
                existing['sourceObservedAt'] = review['sourceObservedAt']
        event['ticketType'] = '複数受付' if len(offers) > 1 else offers[0]['ticketType']
        event['applicationDisplayMode'] = 'offers'
        event['applicationStatus'] = 'offers'
    return events
