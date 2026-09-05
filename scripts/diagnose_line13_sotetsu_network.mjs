#!/usr/bin/env node
import fs from 'node:fs';
const t=JSON.parse(fs.readFileSync('data/transit/through-service-trips.json','utf8'));
const SSH='odpt.Railway:Sotetsu.SotetsuShinYokohama';
const SM='odpt.Railway:Sotetsu.Main';
const SIZ='odpt.Railway:Sotetsu.Izumino';
const pairs=[
  {id:'sotetsushinyokohama-main-nishiya',a:SSH,b:SM},
  {id:'sotetsu-main-izumino-futamatagawa',a:SM,b:SIZ},
];
const types=new Set(['odpt-train-timetable-link','train-timetable-network']);
for(const p of pairs){
  const counts={ab:0,ba:0,topLevelAB:0,topLevelBA:0,records:0,types:{}};
  const samples=[];
  for(const r of t.records||[]){
    const type=String(r.identityType||r.evidenceType||'');
    if(!types.has(type))continue;
    const route=Array.isArray(r.routeRailways)?r.routeRailways.map(String):[];
    let matched=false;
    for(let i=0;i+1<route.length;i++){
      if(route[i]===p.a&&route[i+1]===p.b){counts.ab++;matched=true;}
      if(route[i]===p.b&&route[i+1]===p.a){counts.ba++;matched=true;}
    }
    if(!matched)continue;
    counts.records++;
    counts.types[type]=(counts.types[type]||0)+1;
    if(String(r.fromRailway||'')===p.a&&String(r.toRailway||'')===p.b)counts.topLevelAB++;
    if(String(r.fromRailway||'')===p.b&&String(r.toRailway||'')===p.a)counts.topLevelBA++;
    if(samples.length<12)samples.push({id:r.id,identityType:type,canonicalBoundaryId:r.canonicalBoundaryId||'',fromRailway:r.fromRailway||'',toRailway:r.toRailway||'',routeRailways:route,transitions:r.transitions||[],sourceTimetableId:r.sourceTimetableId||'',targetTimetableId:r.targetTimetableId||''});
  }
  console.log('PAIR',p.id,JSON.stringify(counts));
  for(const s of samples)console.log('SAMPLE',p.id,JSON.stringify(s));
}
