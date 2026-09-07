"""Read the v2 network-journey database, including registered source shards."""
import gzip
import json
from pathlib import Path


def read_json(path):
    path = Path(path)
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def load_network_journeys(directory, index=None):
    directory = Path(directory)
    index = read_json(directory / 'index.json') if index is None else index
    files = [index.get('networkJourneys', 'network-journeys.json')]
    files.extend((index.get('networkJourneyFiles') or {}).values())
    journeys = []
    seen = set()
    for filename in dict.fromkeys(files):
        path = (directory / filename).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError('Network database path escapes its directory')
        # Only the legacy optional main file may be absent in a synthetic DB.
        if not path.exists() and filename == files[0]:
            continue
        for journey in read_json(path).get('journeys', []):
            if not journey.get('id') or journey['id'] in seen:
                raise ValueError('Missing or duplicate network journey ID')
            seen.add(journey['id'])
            journeys.append(journey)
    return journeys
