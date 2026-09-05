#!/usr/bin/env node
import fs from 'node:fs';

const rows=JSON.parse(fs.readFileSync('data/transit/odpt-train-identities.json','utf8')).records||[];
const N='odpt.Railway:TokyoMetro.Namboku';
const M='odpt.Railway:Toei.Mita';
const TM='odpt.Railway:Tokyu.Meguro';
const TS='odpt.Railway:Tokyu.TokyuShinYokohama';
const station=(x)=>String(x?.station||'');
const arr=(v)=>Array.isArray(v)?v.map(String):[];
const ext=(row,needle)=>[...arr(row.origin),...arr(row.destination)].filter(x=>x.includes(needle));
const summary={railwayCounts:{},samples:{},meguro:{namboku:{inbound:0,outbound:0},mita:{inbound:0,outbound:0}},akabaneIwabuchi:{saitamaExternal:0,inbound:0,outbound:0,externalValues:{}},tokyuShinYokohamaMentions:0};
for(const r of rows)summary.railwayCounts[r.railway]=(summary.railwayCounts[r.railway]||0)+1;
const addSample=(k,r,extra={})=>{if(summary.samples[k])return;summary.samples[k]={railway:r.railway,timetableId:r.timetableId,firstStop:r.firstStop,lastStop:r.lastStop,origin:r.origin,destination:r.destination,...extra};};
for(const r of rows){
  if(r.railway===N){
    const first=station(r.firstStop),last=station(r.lastStop);const tok=[...ext(r,'Tokyu.Meguro'),...ext(r,'Tokyu.TokyuShinYokohama'),...ext(r,'Sotetsu.')];
    if(first.endsWith('.Meguro')&&tok.length){summary.meguro.namboku.inbound++;addSample('nambokuInboundMeguro',r,{tok});}
    if(last.endsWith('.Meguro')&&tok.length){summary.meguro.namboku.outbound++;addSample('nambokuOutboundMeguro',r,{tok});}
    const sr=[...arr(r.origin),...arr(r.destination)].filter(x=>/Saitama|UrawaMisono|HigashiKawaguchi|AkabaneIwabuchi/.test(x)&&!x.includes('TokyoMetro.Namboku'));
    if(sr.length){summary.akabaneIwabuchi.saitamaExternal++;for(const x of sr)summary.akabaneIwabuchi.externalValues[x]=(summary.akabaneIwabuchi.externalValues[x]||0)+1;
      if(first.endsWith('.AkabaneIwabuchi')){summary.akabaneIwabuchi.inbound++;addSample('nambokuFromSaitama',r,{sr});}
      if(last.endsWith('.AkabaneIwabuchi')){summary.akabaneIwabuchi.outbound++;addSample('nambokuToSaitama',r,{sr});}
    }
  }
  if(r.railway===M){
    const first=station(r.firstStop),last=station(r.lastStop);const tok=[...ext(r,'Tokyu.Meguro'),...ext(r,'Tokyu.TokyuShinYokohama'),...ext(r,'Sotetsu.')];
    if(first.endsWith('.Meguro')&&tok.length){summary.meguro.mita.inbound++;addSample('mitaInboundMeguro',r,{tok});}
    if(last.endsWith('.Meguro')&&tok.length){summary.meguro.mita.outbound++;addSample('mitaOutboundMeguro',r,{tok});}
  }
  if(JSON.stringify(r).includes('Tokyu.TokyuShinYokohama'))summary.tokyuShinYokohamaMentions++;
}
for(const k of Object.keys(summary.railwayCounts))if(!/(Namboku|Mita|Meguro|Saitama)/.test(k))delete summary.railwayCounts[k];
console.log(JSON.stringify(summary,null,2));
