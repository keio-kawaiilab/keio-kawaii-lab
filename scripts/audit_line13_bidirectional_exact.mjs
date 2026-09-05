#!/usr/bin/env node
import fs from 'node:fs';

const trips=JSON.parse(fs.readFileSync('data/transit/through-service-trips.json','utf8'));
const MM='manual.Railway:YokohamaMinatomirai.Minatomirai';
const TY='odpt.Railway:Tokyu.Toyoko';
const TSH='odpt.Railway:Tokyu.TokyuShinYokohama';
const SSH='odpt.Railway:Sotetsu.SotetsuShinYokohama';
const SM='odpt.Railway:Sotetsu.Main';
const SIZ='odpt.Railway:Sotetsu.Izumino';
const F='odpt.Railway:TokyoMetro.Fukutoshin';
const SY='odpt.Railway:Seibu.SeibuYurakucho';
const TJ='odpt.Railway:Tobu.Tojo';
const PAIRS=[
  {id:'minatomirai-toyoko-yokohama',label:'横浜',a:MM,b:TY},
  {id:'toyoko-tokyushinyokohama-hiyoshi',label:'日吉',a:TY,b:TSH},
  {id:'tokyushinyokohama-sotetsushinyokohama-shinyokohama',label:'新横浜',a:TSH,b:SSH},
  {id:'sotetsushinyokohama-main-nishiya',label:'西谷',a:SSH,b:SM},
  {id:'sotetsu-main-izumino-futamatagawa',label:'二俣川',a:SM,b:SIZ},
  {id:'toyoko-fukutoshin-shibuya',label:'渋谷',a:TY,b:F},
  {id:'fukutoshin-seibuyurakucho-kotakemukaihara',label:'小竹向原',a:F,b:SY},
  {id:'fukutoshin-tojo-wakoshi',label:'和光市',a:F,b:TJ},
];
const exactTypes=new Set(['odpt-train-timetable-link','train-timetable-network','official-single-train-page','official-same-printed-column','odpt-explicit-boundary-endpoint']);
const counts=Object.fromEntries(PAIRS.map(p=>[p.id,{ab:0,ba:0,other:0,types:{}}]));
const pairById=new Map(PAIRS.map(p=>[p.id,p]));
for(const row of trips.records||[]){
  const type=String(row.identityType||row.evidenceType||'');
  if(!exactTypes.has(type))continue;
  const id=String(row.canonicalBoundaryId||'');
  const p=pairById.get(id);
  if(!p)continue;
  const c=counts[id];
  c.types[type]=(c.types[type]||0)+1;
  const from=String(row.fromRailway||'');
  const to=String(row.toRailway||'');
  if(from===p.a&&to===p.b)c.ab++;
  else if(from===p.b&&to===p.a)c.ba++;
  else c.other++;
}
let failed=false;
const result={};
for(const p of PAIRS){
  const c=counts[p.id];
  const bidirectional=c.ab>0&&c.ba>0&&c.other===0;
  result[p.id]={label:p.label,fromRailway:p.a,toRailway:p.b,...c,bidirectional};
  if(!bidirectional)failed=true;
}
console.log(JSON.stringify(result,null,2));
if(failed)throw new Error('At least one Line 13 boundary lacks exact evidence in both directions');
console.log('All eight Line 13 boundaries have exact evidence in both directions');
