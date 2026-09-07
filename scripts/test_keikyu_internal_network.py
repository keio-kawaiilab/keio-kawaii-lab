import copy
import json
import tempfile
import unittest
from pathlib import Path

from audit_keikyu_station_time_resolution import resolve_ditto_markers
from probe_keikyu_station_rows import station_matches
from keikyu_internal_inline_references import resolve_notes
from build_keikyu_internal_network import assemble
from keikyu_internal_runtime import projections, apply, CORE


class RowSemantics(unittest.TestCase):
    def test_ditto_inherits_arrival_and_resets_on_departure(self):
        rows=[{'left':x,'y':i*6,'marker':m}for i,(x,m) in enumerate([
            ('羽田第３着','arrival'),('羽田第１・第２〃','departure'),
            ('雑色発','departure'),('六郷土手〃','departure')])]
        resolve_ditto_markers(rows)
        self.assertEqual([r['marker']for r in rows],['arrival','arrival','departure','departure'])

    def test_unanchored_ditto_does_not_invent_departure(self):
        rows=[{'left':'神武寺〃','y':10,'marker':'departure'}]
        resolve_ditto_markers(rows);self.assertIsNone(rows[0]['marker'])

    def test_station_aliases_do_not_become_another_station(self):
        titles=['屏風浦','屛風浦','杉田','YRP野比','ＹＲＰ野比']
        self.assertEqual(station_matches('屛風浦〃',titles),['屏風浦'])
        self.assertEqual(station_matches('ＹＲＰ野比〃',titles),['YRP野比'])


class OfficialIdentity(unittest.TestCase):
    def fixture(self):
        stops={'fragments':[
            {'id':'a','calendar':'weekday','stopTimes':[{'station':'逗子・葉山','event':'departure','time':'1000'},
                                                       {'station':'京急蒲田','event':'arrival','time':'1100'}]},
            {'id':'b','calendar':'weekday','stopTimes':[{'station':'京急蒲田','event':'departure','time':'1101'},
                                                       {'station':'羽田空港第１・第２ターミナル','event':'arrival','time':'1112'}]}]}
        notes=[{'fragment':'a','side':'destination','calendar':'weekday','printedPage':33,'referencedPrintedPage':4,
                'suffix':'.HanedaAirportTerminal1and2','event':'arrival','minute':672},
               {'fragment':'b','side':'origin','calendar':'weekday','printedPage':4,'referencedPrintedPage':33,
                'suffix':'.ZushiHayama','event':'departure','minute':600}]
        return stops,notes

    def test_reciprocal_notes_and_both_endpoints_prove_link(self):
        s,n=self.fixture();links,rejected=resolve_notes(s,n)
        self.assertEqual(len(links),1);self.assertFalse(rejected)

    def test_same_times_without_reciprocal_page_are_not_identity(self):
        s,n=self.fixture();n[1]['referencedPrintedPage']=34
        self.assertFalse(resolve_notes(s,n)[0])

    def test_endpoint_mismatch_is_rejected(self):
        s,n=self.fixture();n[1]['minute']+=1
        self.assertFalse(resolve_notes(s,n)[0])

    def test_matching_number_and_clock_do_not_join_unlinked_columns(self):
        s,_=self.fixture()
        for f in s['fragments']:f['printedTrainNumber']='100D'
        rows=assemble(s,{'first':['a'],'second':['b']})
        self.assertEqual(len(rows),2)
        self.assertTrue(all(len(r['members'])==1 for r in rows))

    def test_conflicting_published_times_block_assembly(self):
        s,_=self.fixture();s['fragments'][1]['stopTimes'].append({'station':'逗子・葉山','event':'departure','time':'1001'})
        rows=assemble(s,{'combined':['a','b']})
        self.assertTrue(rows[0]['issues'])


class RuntimeProjection(unittest.TestCase):
    def fixture(self):
        rails=sorted(CORE);main=rails.index('odpt.Railway:Keikyu.Main');airport=rails.index('odpt.Railway:Keikyu.Airport')
        return {'timeBasis':'train-timetable-network','internalCoverageComplete':True,'sourceSha256':'test',
                'railways':rails,'stations':['sengakuji','shinagawa','haneda3','haneda12'],
                'calendars':['weekday'],'trainTypes':[''],
                'trips':[[0,0,'',[[0,None,600],[1,602,603],[2,614,None],[3,617,None]],
                          [[main],[main,airport],[airport]],'official:test']]}

    def test_passed_junction_gets_no_fabricated_stop_or_time(self):
        tables,identities=projections(self.fixture())
        self.assertEqual(len(identities[0]['parts']),2)
        self.assertEqual([len(t['trips'][0][3])for t in tables.values()],[2,2])
        self.assertEqual([p['stops']for p in identities[0]['parts']],
                         [[[0,None,600],[1,602,603]],[[2,614,None],[3,617,None]]])

    def test_stale_projection_cannot_be_promoted(self):
        n=self.fixture();_,identities=projections(n);fs=[]
        for p in identities[0]['parts']:
            fs.append({'id':p['timetableId'],'timetableId':p['timetableId'],'railway':p['railway'],
                       'calendar':'weekday','stops':[[n['stations'][s[0]],s[1],s[2]]for s in p['stops']]})
        with tempfile.TemporaryDirectory()as d:
            path=Path(d)/'n.json';path.write_text(json.dumps(n))
            self.assertEqual(len(apply(fs,[],path)),1)
            fs[0]['stops'][0][2]+=1
            with self.assertRaises(ValueError):apply(fs,[],path)

if __name__=='__main__':unittest.main()
