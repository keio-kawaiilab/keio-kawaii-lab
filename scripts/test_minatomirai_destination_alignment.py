#!/usr/bin/env python3
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('m', Path(__file__).with_name('enrich_minatomirai_destinations.py'))
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

mm = {
    'stations': [m.MM_YOKOHAMA, 'MM.Moto'],
    'calendars': ['odpt.Calendar:Weekday'],
    'directions': ['out', 'in'],
    'trainTypes': ['local'],
    'destinations': ['MM.Moto', m.MM_YOKOHAMA],
    'inferredTrips': [[0, 1, 0, 1, 95, [[1, None, 595], [0, 600, None]]]],
    'boards': [[1, 0, 1, [[595, 0, 1]]]],
}
tokyu = {
    'stations': [m.TOKYU_YOKOHAMA, 'T.Shibuya'],
    'calendars': ['odpt.Calendar:Weekday'],
    'directions': ['up'],
    'trainTypes': ['local'],
    'destinations': ['odpt.Station:Tobu.Tojo.Kawagoeshi'],
    'boards': [[0, 0, 0, [[601, 0, 0]]]],
}

out, report = m.enrich_table(mm, tokyu)
assert report['assignedTrips'] == 1
assert report['unresolvedTrips'] == 0
assert out['destinations'][out['inferredTrips'][0][3]] == 'odpt.Station:Tobu.Tojo.Kawagoeshi'
assert out['boards'][0][3][0][2] == out['inferredTrips'][0][3]
assert out['destinationAuthoritative'] is True
print('Minatomirai destination alignment test passed')
