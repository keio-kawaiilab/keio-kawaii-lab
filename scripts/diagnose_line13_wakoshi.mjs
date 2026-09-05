#!/usr/bin/env node
import fs from 'node:fs';
const data=JSON.parse(fs.readFileSync('data/transit/odpt-train-identities.json','utf8'));
const F='odpt.Railway:TokyoMetro.Fukutoshin';
const TJ='odpt.Railway:Tobu.Tojo';
const rows=(data.records||[]).filter(r=>r&&[F,TJ].includes(String(r.railway||'')));
const suffix=v=>String(v||'').split('.').pop();
const externalTo=(r,railway)=>{
  const vals=[...(r.destination||[]),...(r.origin||[])];
  return vals.filter(v=>{
    const s=String(v||'');
    return railway===F ? /Tobu\.Tojo\./.test(s) : /TokyoMetro\.Fukutoshin\./.test(s);
  });
};
const summary={};
for(const railway of [F,TJ]){
  const rr=rows.filter(r=>r.railway===railway);
  summary[railway]={
    records:rr.length,
    withOrigin:rr.filter(r=>(r.origin||[]).length).length,
    withDestination:rr.filter(r=>(r.destination||[]).length).length,
    externalDestination:rr.filter(r=>r.externalDestination).length,
    previousRefs:rr.reduce((n,r)=>n+(r.previousTrainTimetables||[]).length,0),
    nextRefs:rr.reduce((n,r)=>n+(r.nextTrainTimetables||[]).length,0),
    explicitOtherOperatorStationIds:rr.filter(r=>externalTo(r,railway).length).length,
  };
}
console.log('SUMMARY',JSON.stringify(summary,null,2));
for(const railway of [F,TJ]){
  console.log('\nRAILWAY',railway);
  const samples=rows.filter(r=>r.railway===railway).filter(r=>
    r.externalDestination || (r.origin||[]).length || (r.destination||[]).length ||
    (r.previousTrainTimetables||[]).length || (r.nextTrainTimetables||[]).length
  ).slice(0,40);
  for(const r of samples){
    console.log(JSON.stringify({
      timetableId:r.timetableId,
      trainId:r.trainId,
      calendars:r.calendars,
      trainNumber:r.trainNumber,
      trainType:r.trainType,
      direction:r.direction,
      origin:r.origin,
      destination:r.destination,
      externalDestination:r.externalDestination,
      firstStop:r.firstStop,
      lastStop:r.lastStop,
      previous:r.previousTrainTimetables,
      next:r.nextTrainTimetables,
      otherOperatorStationIds:externalTo(r,railway),
    }));
  }
}
