#!/usr/bin/env node
import fs from 'node:fs';
const evidenceFile='data/transit/meguro/sotetsu-official-meguro-columns.json',tripsFile='data/transit/through-service-trips.json',coverageFile='data/transit/through-service-coverage.json';
const read=f=>JSON.parse(fs.readFileSync(f,'utf8')),write=(f,v)=>fs.writeFileSync(f,JSON.stringify(v,null,2)+'\n');
if(!fs.existsSync(evidenceFile)){console.log('No Meguro printed-column evidence; unchanged');process.exit(0);}
const e=read(evidenceFile),trips=read(tripsFile),coverage=read(coverageFile),p=e.identityPolicy||{};
if(p.officialSamePrintedColumnMayEstablishIdentity!==true||p.timeProximityMayEstablishIdentity!==false||p.trainNumberAloneMayEstablishIdentity!==false||p.destinationAloneMayEstablishIdentity!==false)throw new Error('Meguro PDF evidence policy is not fail-closed');
const TM='odpt.Railway:Tokyu.Meguro',TS='odpt.Railway:Tokyu.TokyuShinYokohama',N='odpt.Railway:TokyoMetro.Namboku',M='odpt.Railway:Toei.Mita';
const specs={
 'meguro-tokyushinyokohama-hiyoshi':{station:'日吉',railways:new Set([TM,TS]),kind:'stations'},
 'meguro-namboku-meguro':{station:'目黒',railways:new Set([TM,N]),kind:'terminal',branch:'namboku'},
 'meguro-mita-meguro':{station:'目黒',railways:new Set([TM,M]),kind:'terminal',branch:'mita'},
};
const map=new Map((trips.records||[]).map(r=>[String(r.id||''),r]));let added=0;const counts={},dirs={};
for(const row of e.authoritativeColumns||[]){
 if(row.identityEvidence!=='official-same-printed-column'||row.status!=='verified')throw new Error('Only verified same-column evidence allowed');
 const bid=String(row.canonicalBoundaryId||''),s=specs[bid];if(!s)throw new Error(`Unexpected Meguro PDF boundary ${bid}`);
 const fr=String(row.fromRailway||''),to=String(row.toRailway||'');if(fr===to||!s.railways.has(fr)||!s.railways.has(to))throw new Error(`Wrong railway pair ${bid}`);
 if(!String(row.sourceUrl||'').startsWith('https://cdn.sotetsu.co.jp/'))throw new Error('Unexpected source URL');
 const mp=row.matchPolicy||{};if(mp.officialSamePrintedColumnRequired!==true||mp.timeProximityAloneMayEstablishIdentity!==false||mp.trainNumberAloneMayEstablishIdentity!==false||mp.destinationAloneMayEstablishIdentity!==false)throw new Error(`Weak evidence ${bid}`);
 if(s.kind==='stations'){
   const stops=(row.publishedBoundaryStops||[]).map(String),ok=JSON.stringify(stops)===JSON.stringify(['大岡山','日吉','新綱島'])||JSON.stringify(stops)===JSON.stringify(['新綱島','日吉','大岡山']);
   if(!ok||mp.exactPrintedStationTimesRequired!==true||mp.routeSpecificMeguroStationRequired!==true)throw new Error('Hiyoshi exact Meguro-route anchors missing');
   for(const x of stops)if(!String((row.printedTimes||{})[x]||''))throw new Error(`Missing printed time ${x}`);
 }else{
   if(String(row.branch||'')!==s.branch||!String(row.branchSpecificExternalTerminal||'')||!String(row.printedMeguroTime||''))throw new Error(`Branch-specific Meguro terminal evidence missing ${bid}`);
   if(mp.exactMeguroTimeRequired!==true||mp.branchSpecificExternalTerminalRequired!==true)throw new Error(`Meguro terminal positive requirements missing ${bid}`);
 }
 const id=String(row.id||'');if(!id)throw new Error('Evidence identity missing');
 const rec={id,identityKey:id,identityType:'official-same-printed-column',status:'verified',corridor:'meguro',fromRailway:fr,toRailway:to,routeRailways:[fr,to],transitions:[{fromRailway:fr,toRailway:to,boundaryStation:s.station}],classification:'through',canonicalBoundaryId:bid,sourceUrl:row.sourceUrl,pdfPage:Number(row.pdfPage),columnX:Number(row.columnX),calendar:String(row.calendar||''),direction:String(row.direction||''),publishedBoundaryStops:row.publishedBoundaryStops||[],printedTimes:row.printedTimes||{},printedMeguroTime:row.printedMeguroTime||'',branchSpecificExternalTerminal:row.branchSpecificExternalTerminal||'',evidence:'operator-official-full-train-timetable+same-printed-column+route-specific-anchor',matchPolicy:mp,runtimeRule:{requiredMatch:['identityKey','fromRailway','toRailway']}};
 counts[bid]=(counts[bid]||0)+1;dirs[bid]??={};dirs[bid][rec.direction]=(dirs[bid][rec.direction]||0)+1;if(!map.has(id)){map.set(id,rec);added++;}
}
for(const bid of Object.keys(specs)){const d=dirs[bid]||{};if(!(d.up>0&&d.down>0))throw new Error(`Meguro PDF boundary is not bidirectional ${bid}: ${JSON.stringify(d)}`);}
trips.version=Math.max(Number(trips.version)||0,10);trips.policy={...(trips.policy||{}),runtimeInference:false,timeGapMayEstablishTrainIdentity:false,trainNumberMayEstablishTrainIdentity:false,genericBoundaryChaining:false};trips.records=[...map.values()].sort((a,b)=>String(a.id||'').localeCompare(String(b.id||'')));trips.meguroOfficialColumnEvidence={sourceFile:evidenceFile,inputColumns:(e.authoritativeColumns||[]).length,addedRecords:added,boundaries:counts,directions:dirs};write(tripsFile,trips);
coverage.version=Math.max(Number(coverage.version)||0,10);coverage.summary={...(coverage.summary||{}),throughRecords:trips.records.length,officialSamePrintedColumnThroughRecords:trips.records.filter(r=>r.identityType==='official-same-printed-column').length};coverage.meguroOfficialColumnEvidence={sourceFile:evidenceFile,inputColumns:(e.authoritativeColumns||[]).length,addedRecords:added,boundaries:counts,directions:dirs};write(coverageFile,coverage);console.log(JSON.stringify({inputColumns:(e.authoritativeColumns||[]).length,addedRecords:added,boundaries:counts,directions:dirs,totalThroughRecords:trips.records.length},null,2));
