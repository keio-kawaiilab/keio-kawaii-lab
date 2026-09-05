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

function directionForPair(row,p){
  // ODPT link/network records can intentionally leave top-level
  // fromRailway/toRailway blank and express direction in routeRailways.
  // Inspect the exact adjacent route segment first.
  const route=Array.isArray(row.routeRailways)?row.routeRailways.map(String):[];
  for(let i=0;i+1<route.length;i++){
    if(route[i]===p.a&&route[i+1]===p.b)return 'ab';
    if(route[i]===p.b&&route[i+1]===p.a)return 'ba';
  }
  // Direct official evidence records use top-level endpoints.
  const from=String(row.fromRailway||'');
  const to=String(row.toRailway||'');
  if(from===p.a&&to===p.b)return 'ab';
  if(from===p.b&&to===p.a)return 'ba';
  return '';
}

for(const row of trips.records||[]){
  const type=String(row.identityType||row.evidenceType||'');
  if(!exactTypes.has(type))continue;
  for(const p of PAIRS){
    const direction=directionForPair(row,p);
    if(!direction)continue;
    const c=counts[p.id];
    c[direction]++;
    c.types[type]=(c.types[type]||0)+1;
  }

  // If a record explicitly claims one of these canonical boundaries but does
  // not encode the claimed adjacent railway direction, flag it instead of
  // silently accepting malformed evidence.
  const canonical=String(row.canonicalBoundaryId||'');
  const p=PAIRS.find(candidate=>candidate.id===canonical);
  if(p&&!directionForPair(row,p))counts[p.id].other++;
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
