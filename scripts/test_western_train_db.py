#!/usr/bin/env python3
"""Regressions for exact matching, calendar isolation and indexed DB survival."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import import_western_train_db as importer
from transit_network_db import load_network_journeys, read_json
import verify_western_train_db as verifier


class WesternDatabaseTests(unittest.TestCase):
    def test_entire_fragment_and_calendar_are_required(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            f = {'id': 'old', 'railway': 'rail:A', 'calendar': 'weekday',
                 'stops': [['old:A', None, 300], ['old:B', 310, 311], ['old:C', 320, None]]}
            path = root / 'data/transit-v2/fragments/a.json'
            importer.write_json(path, {'fragments': [f]})
            stations = {'stations': [{'id': c, 'aliases': ['old:' + c]} for c in 'ABC'],
                        'railways': [{'id': 'rail:A'}]}
            rules = {'calendars': [{'id': 'cal:w', 'dayKinds': [1]}, {'id': 'cal:h', 'dayKinds': [2, 4]}]}
            good = {'id': 'good', 'railwayPath': ['rail:A'], 'calendar': 'cal:w',
                    'stops': [['A', None, 300], ['B', 310, 311], ['C', 320, None]]}
            near = copy.deepcopy(good); near['id'] = 'near'; near['stops'][1][1] += 1
            other_day = copy.deepcopy(good); other_day.update(id='holiday', calendar='cal:h')
            result = importer.match_legacy_fragments(root, {'journeys': [good, near, other_day]}, stations, rules)
            self.assertEqual(result['matches'][0]['journeyIds'], ['good'])
            twin = copy.deepcopy(good); twin['id'] = 'twin'
            result = importer.match_legacy_fragments(root, {'journeys': [good, twin]}, stations, rules)
            self.assertEqual(result['matches'][0]['status'], 'ambiguous-exact-content-match')
            self.assertFalse(result['policy']['automaticLegacyIdentityPromotion'])

    def test_registered_shard_is_read_and_duplicate_ids_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            index = {'networkJourneys': 'network-journeys.json', 'networkJourneyFiles': {'western-yahoo': 'western/trains.json.gz'}}
            importer.write_json(directory / 'index.json', index)
            importer.write_json(directory / 'network-journeys.json', {'journeys': [{'id': 'legacy'}]})
            importer.write_json(directory / 'western/trains.json.gz', {'journeys': [{'id': 'western'}]})
            self.assertEqual([j['id'] for j in load_network_journeys(directory)], ['legacy', 'western'])
            importer.write_json(directory / 'western/trains.json.gz', {'journeys': [{'id': 'legacy'}]})
            with self.assertRaises(ValueError):
                load_network_journeys(directory)

    def test_full_audit_rejects_missing_train_and_changed_time(self):
        directory = Path('data/transit-v2')
        journeys = load_network_journeys(directory)
        position = next(i for i, j in enumerate(journeys) if j.get('sourceOperator') == 'western-yahoo')
        missing = journeys[:position] + journeys[position + 1:]
        with patch.object(verifier, 'load_network_journeys', return_value=missing):
            with self.assertRaises(AssertionError):
                verifier.verify()
        changed = journeys[:]
        changed[position] = copy.deepcopy(changed[position])
        changed[position]['stops'][0][2] += 1
        with patch.object(verifier, 'load_network_journeys', return_value=changed):
            with self.assertRaises(AssertionError):
                verifier.verify()

    def test_reinstall_restores_registration_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = Path('data/transit/yahoo-western-research').resolve()
            (root / 'data/transit').mkdir(parents=True)
            (root / 'data/transit/yahoo-western-research').symlink_to(source, target_is_directory=True)
            # Entity/fragment inputs are immutable links. Outputs remain isolated.
            for path in Path('data/transit').glob('*/entities.json'):
                directory = root / path.parent
                directory.mkdir(parents=True, exist_ok=True)
                (directory / 'entities.json').symlink_to(path.resolve())
            out = root / 'data/transit-v2'
            out.mkdir()
            (out / 'fragments').symlink_to(Path('data/transit-v2/fragments').resolve(), target_is_directory=True)
            importer.write_json(out / 'index.json', {'networkJourneys': 'network-journeys.json'})
            importer.write_json(out / 'network-journeys.json', {'journeys': [{'id': 'preserved'}]})
            first = importer.install(root)
            self.assertEqual(first['importedTrainIds'], 7898)
            self.assertEqual(len(load_network_journeys(out)), 7899)
            importer.write_json(out / 'index.json', {'networkJourneys': 'network-journeys.json'})
            second = importer.install(root)
            self.assertEqual(first, second)
            self.assertEqual(len(load_network_journeys(out)), 7899)


if __name__ == '__main__':
    unittest.main()
