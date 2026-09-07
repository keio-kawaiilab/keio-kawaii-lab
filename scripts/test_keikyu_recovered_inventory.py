import copy
import gzip
import hashlib
import json
import unittest
from pathlib import Path

from save_keikyu_recovery_checkpoint import verify_boundary, POSITIVE
from verify_keikyu_official_stop_times import verify

ROOT=Path(__file__).resolve().parents[1]/'docs/transit'


class RecoveredInventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload=json.loads((ROOT/'sengakuji-published-sequence-audit.json').read_text())
        cls.unfiltered=json.loads((ROOT/'sengakuji-unfiltered-column-audit.json').read_text())

    def test_all_nine_previously_missing_trains_are_recovered(self):
        self.assertEqual(len(verify_boundary(self.payload,self.unfiltered)),9)

    def test_missing_column_rejected(self):
        p=copy.deepcopy(self.payload);p['results'].pop()
        with self.assertRaises(RuntimeError):verify_boundary(p,self.unfiltered)

    def test_unfiltered_snapshot_change_rejected(self):
        u=copy.deepcopy(self.unfiltered);u['results'][0]['sourceSha256']='0'*64
        with self.assertRaises(RuntimeError):verify_boundary(self.payload,u)

    def test_unknown_marker_never_counts_as_through(self):
        p=copy.deepcopy(self.payload)
        next(r for r in p['results'] if r['publishedSequenceStatus']==POSITIVE)['officialBoundaryClassification']['status']='unknown'
        with self.assertRaises(RuntimeError):verify_boundary(p,self.unfiltered)

    def test_runtime_promotion_rejected(self):
        p=copy.deepcopy(self.payload);p['identityPolicy']['runtimeSameTrainPromotions']=1
        with self.assertRaises(RuntimeError):verify_boundary(p,self.unfiltered)

    def test_duplicate_local_identity_rejected(self):
        p=copy.deepcopy(self.payload)
        positives=[r for r in p['results'] if r['publishedSequenceStatus']==POSITIVE]
        positives[1]['keikyuSequenceMatches']=positives[0]['keikyuSequenceMatches']
        with self.assertRaises(RuntimeError):verify_boundary(p,self.unfiltered)

    def test_compressed_full_source_is_available_and_verifies(self):
        p=json.loads(gzip.decompress((ROOT/'keikyu-independent-stop-times.json.gz').read_bytes()))
        self.assertTrue(verify(p)['verified'])
        a=next(f for f in p['fragments'] if f['id']=='keikyu-official-pdf:p056:s00:c11')
        self.assertEqual(a['printedTrainNumber'],'1773SH')

    def test_all_saved_file_hashes_match_checkpoint(self):
        c=json.loads((ROOT/'keikyu-recovery-checkpoint.json').read_text())
        for name,digest in c['filesSha256'].items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)


if __name__=='__main__':unittest.main()
