#!/usr/bin/env node
import fs from 'node:fs';
const ids=JSON.parse(fs.readFileSync('data/transit/odpt-train-identities.json','utf8'));
const trips=JSON.parse(fs.readFileSync('data/transit/through-service-trips.json','utf8'));
const rows=ids.records||[];
const trows=trips.records||[];
const arr=v=>Array.isArray(v)?v.map(String):[];
const st=x=>String(x?.station||'');
const N='odpt.Railway:TokyoMetro.Namboku';
const TY='odpt.Railway:Tokyu.Toyoko';
const SR='odpt.Station:SaitamaRailway.SaitamaRailway.';
const SH='odpt.Station:TokyoMetro.Namboku.ShirokaneTakanawa';
const AK='odpt.Station:TokyoMetro.Namboku.AkabaneIwabuchi';
const namboku=rows.filter(r=>r.railway===N);
const shirokaneToSaitama=namboku.filter(r=>st(r.firstStop)===SH && st(r.lastStop)===AK && arr(r.destination).some(x=>x.startsWith(SR)));
const toyoko=rows.filter(r=>r.railway===TY);
const yok=trows.filter(r=>r.canonicalBoundaryId==='minatomirai-toyoko-yokohama');
const sourceSummary={};
for(const r of yok){
  const k=[r.identityType||'',r.sourceOperator||'',r.sourceTimetableId?String(r.sourceTimetableId).split(':')[1]?.split('.')[0]||'':''].join('|');
  sourceSummary[k]=(sourceSummary[k]||0)+1;
}
const samples=v=>v.slice(0,8).map(r=>({timetableId:r.timetableId||r.sourceTimetableId||'',firstStop:r.firstStop||null,lastStop:r.lastStop||null,origin:r.origin||[],destination:r.destination||[],identityType:r.identityType||'',sourceOperator:r.sourceOperator||'',sourceTrainId:r.sourceTrainId||'',externalStations:r.externalStations||[]}));
console.log(JSON.stringify({identityRailwayCounts:{namboku:namboku.length,toyoko:toyoko.length},shirokaneTakanawaToSaitama:{count:shirokaneToSaitama.length,samples:samples(shirokaneToSaitama)},yokohamaBoundary:{count:yok.length,sourceSummary,samples:samples(yok)}},null,2));
