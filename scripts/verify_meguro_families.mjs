#!/usr/bin/env node
import fs from 'node:fs';
const file='data/transit/through-service-families.json';const data=JSON.parse(fs.readFileSync(file,'utf8'));const list=data.families||[];const byId=new Map(list.map(x=>[String(x.id||''),x]));
const upsert=(s)=>{const c=byId.get(s.id);if(c)Object.assign(c,s);else{list.push(s);byId.set(s.id,s);}};
const TM='odpt.Railway:Tokyu.Meguro',N='odpt.Railway:TokyoMetro.Namboku',SR='odpt.Railway:SaitamaRailway.SaitamaRailway',TS='odpt.Railway:Tokyu.TokyuShinYokohama',SS='odpt.Railway:Sotetsu.SotetsuShinYokohama',SM='odpt.Railway:Sotetsu.Main',SI='odpt.Railway:Sotetsu.Izumino';
upsert({id:'meguro-namboku-saitamarailway',status:'verified',sourceUrls:['https://www.tokyu.co.jp/area/meguro/station/','https://www.s-rail.co.jp/line/new-timetable/new-urawamisono.pdf'],paths:[[TM,N,SR]],notes:'東急目黒線―東京メトロ南北線―埼玉高速鉄道の相互直通。specific train identityはexact endpoint/official printed columnのみで確定。'});
upsert({id:'sotetsu-tokyushinyokohama-meguro-namboku-saitamarailway',status:'verified',sourceUrls:['https://www.sotetsu.co.jp/train/stations/shinyokohama/','https://www.s-rail.co.jp/line/new-timetable/new-urawamisono.pdf'],paths:[[SM,SS,TS,TM,N,SR],[SI,SM,SS,TS,TM,N,SR]],notes:'相鉄―東急新横浜線―目黒線―南北線―埼玉高速鉄道系統。'});
data.version=Math.max(Number(data.version)||0,2);data.updatedAt=new Date().toISOString().slice(0,10);data.families=list;fs.writeFileSync(file,JSON.stringify(data,null,2)+'\n');console.log(JSON.stringify({added:['meguro-namboku-saitamarailway','sotetsu-tokyushinyokohama-meguro-namboku-saitamarailway'],familyCount:list.length},null,2));
