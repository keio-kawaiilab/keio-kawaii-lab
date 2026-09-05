#!/usr/bin/env node
import fs from 'node:fs';
const read=f=>JSON.parse(fs.readFileSync(f,'utf8')),write=(f,v)=>{fs.mkdirSync('data/transit/meguro',{recursive:true});fs.writeFileSync(f,JSON.stringify(v,null,2)+'\n');};
const TM='odpt.Railway:Tokyu.Meguro',TS='odpt.Railway:Tokyu.TokyuShinYokohama',SSH='odpt.Railway:Sotetsu.SotetsuShinYokohama',SM='odpt.Railway:Sotetsu.Main',SI='odpt.Railway:Sotetsu.Izumino',N='odpt.Railway:TokyoMetro.Namboku',M='odpt.Railway:Toei.Mita',SR='odpt.Railway:SaitamaRailway.SaitamaRailway';
const PAIRS=[
 ['meguro-tokyushinyokohama-hiyoshi','東急目黒線↔東急新横浜線（日吉）',TM,TS],
 ['tokyushinyokohama-sotetsushinyokohama-shinyokohama','東急新横浜線↔相鉄新横浜線（新横浜）',TS,SSH],
 ['sotetsushinyokohama-main-nishiya','相鉄新横浜線↔相鉄本線（西谷）',SSH,SM],
 ['sotetsu-main-izumino-futamatagawa','相鉄本線↔相鉄いずみ野線（二俣川）',SM,SI],
 ['meguro-namboku-meguro','東急目黒線↔東京メトロ南北線（目黒）',TM,N],
 ['meguro-mita-meguro','東急目黒線↔都営三田線（目黒）',TM,M],
 ['namboku-saitamarailway-akabaneiwabuchi','東京メトロ南北線↔埼玉高速鉄道（赤羽岩淵）',N,SR],
];
const exactTypes=new Set(['odpt-train-timetable-link','train-timetable-network','official-single-train-page','official-same-printed-column','odpt-explicit-boundary-endpoint']);
const trips=read('data/transit/through-service-trips.json'),boundaries=read('data/transit/through-service-boundaries.json');const bmap=new Map((boundaries.boundaries||[]).map(x=>[x.id,x]));
if(trips.policy?.runtimeInference!==false||trips.policy?.timeGapMayEstablishTrainIdentity!==false||trips.policy?.trainNumberMayEstablishTrainIdentity!==false||trips.policy?.genericBoundaryChaining!==false)throw new Error('Through DB must remain fail-closed');
function direction(r,a,b){const route=(r.routeRailways||[]).map(String);for(let i=0;i+1<route.length;i++){if(route[i]===a&&route[i+1]===b)return'ab';if(route[i]===b&&route[i+1]===a)return'ba';}const f=String(r.fromRailway||''),t=String(r.toRailway||'');if(f===a&&t===b)return'ab';if(f===b&&t===a)return'ba';return'';}
const rows=[];
for(const [id,label,a,b] of PAIRS){const s={ab:0,ba:0,other:0,types:{},records:new Set()};for(const r of trips.records||[]){const type=String(r.identityType||r.evidenceType||'');if(!exactTypes.has(type))continue;const d=direction(r,a,b);if(d){s[d]++;s.types[type]=(s.types[type]||0)+1;s.records.add(String(r.identityKey||r.id||''));}else if(String(r.canonicalBoundaryId||'')===id)s.other++;}
 const br=bmap.get(id)||{};const ready=br.status==='verified'&&s.ab>0&&s.ba>0&&s.other===0&&s.records.size>0;rows.push({id,label,fromRailway:a,toRailway:b,boundaryStatus:String(br.status||'missing'),boundarySource:String(br.source||''),generatedExactThroughRecords:s.records.size,directions:{ab:s.ab,ba:s.ba,other:s.other},exactBidirectional:s.ab>0&&s.ba>0&&s.other===0,exactIdentityReady:ready,evidenceTypes:s.types});}
const report={version:1,generatedAt:new Date().toISOString(),system:'Tokyu Meguro Line through-service corridor: Sotetsu/Tokyu Shin-Yokohama + Namboku/Mita + Saitama Railway',policy:{runtimeInference:false,timeGapMayEstablishTrainIdentity:false,trainNumberMayEstablishTrainIdentity:false,publishedDestinationAloneMayEstablishIdentity:false,bidirectionalExactEvidenceRequired:true},pairs:rows,summary:{boundaryPairs:rows.length,verifiedBoundaries:rows.filter(r=>r.boundaryStatus==='verified').length,exactIdentityReadyPairs:rows.filter(r=>r.exactIdentityReady).length,generatedExactThroughRecords:rows.reduce((n,r)=>n+r.generatedExactThroughRecords,0),complete:rows.every(r=>r.exactIdentityReady)}};write('data/transit/meguro/identity-coverage-report.json',report);console.log(JSON.stringify(report.summary,null,2));for(const r of rows)console.log(`${r.label}: ${r.directions.ab}/${r.directions.ba}/${r.directions.other} exact=${r.generatedExactThroughRecords} ready=${r.exactIdentityReady}`);
