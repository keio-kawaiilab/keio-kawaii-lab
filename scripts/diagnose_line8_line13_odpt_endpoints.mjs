#!/usr/bin/env node
import fs from 'node:fs';
const db=JSON.parse(fs.readFileSync('data/transit/odpt-train-identities.json','utf8'));
const rows=db.records||[];
const Y='odpt.Railway:TokyoMetro.Yurakucho',F='odpt.Railway:TokyoMetro.Fukutoshin',TJ='odpt.Railway:Tobu.Tojo';
const YW='odpt.Station:TokyoMetro.Yurakucho.Wakoshi',FW='odpt.Station:TokyoMetro.Fukutoshin.Wakoshi';
const YK='odpt.Station:TokyoMetro.Yurakucho.KotakeMukaihara',FK='odpt.Station:TokyoMetro.Fukutoshin.KotakeMukaihara';
const TW='odpt.Station:Tobu.Tojo.Wakoshi';
const station=(x)=>String(x?.station||'');
function railwayOfStation(id){const t=String(id||'');const p='odpt.Station:';if(!t.startsWith(p))return'';const x=t.slice(p.length).split('.');return x.length>=2?`odpt.Railway:${x[0]}.${x[1]}`:'';}
function add(map,key){map[key]=(map[key]||0)+1;}
function externalSummary(values){const out={};for(const v of Array.isArray(values)?values:[])add(out,railwayOfStation(v)||String(v));return out;}
function scanMetro(railway,wako,kotake){
 const result={records:0,wakoshiInbound:{},wakoshiOutbound:{},kotakeInbound:{},kotakeOutbound:{},seibuExternalOrigins:{},seibuExternalDestinations:{}};
 for(const r of rows){if(r.railway!==railway)continue;result.records++;const first=station(r.firstStop),last=station(r.lastStop);if(first===wako)for(const [k,n] of Object.entries(externalSummary(r.origin)))result.wakoshiInbound[k]=(result.wakoshiInbound[k]||0)+n;if(last===wako)for(const [k,n] of Object.entries(externalSummary(r.destination)))result.wakoshiOutbound[k]=(result.wakoshiOutbound[k]||0)+n;if(first===kotake)for(const [k,n] of Object.entries(externalSummary(r.origin)))result.kotakeInbound[k]=(result.kotakeInbound[k]||0)+n;if(last===kotake)for(const [k,n] of Object.entries(externalSummary(r.destination)))result.kotakeOutbound[k]=(result.kotakeOutbound[k]||0)+n;for(const v of r.origin||[]){const rw=railwayOfStation(v);if(rw.startsWith('odpt.Railway:Seibu.'))add(result.seibuExternalOrigins,rw);}for(const v of r.destination||[]){const rw=railwayOfStation(v);if(rw.startsWith('odpt.Railway:Seibu.'))add(result.seibuExternalDestinations,rw);}}
 return result;
}
function scanTobu(){const result={records:0,firstWakoshiDestinations:{},lastWakoshiOrigins:{},metroOrigins:{},metroDestinations:{}};for(const r of rows){if(r.railway!==TJ)continue;result.records++;const first=station(r.firstStop),last=station(r.lastStop);if(first===TW)for(const [k,n] of Object.entries(externalSummary(r.origin)))result.lastWakoshiOrigins[k]=(result.lastWakoshiOrigins[k]||0)+n;if(last===TW)for(const [k,n] of Object.entries(externalSummary(r.destination)))result.firstWakoshiDestinations[k]=(result.firstWakoshiDestinations[k]||0)+n;for(const v of r.origin||[]){const rw=railwayOfStation(v);if(rw.startsWith('odpt.Railway:TokyoMetro.'))add(result.metroOrigins,rw);}for(const v of r.destination||[]){const rw=railwayOfStation(v);if(rw.startsWith('odpt.Railway:TokyoMetro.'))add(result.metroDestinations,rw);}}return result;}
console.log(JSON.stringify({yurakucho:scanMetro(Y,YW,YK),fukutoshin:scanMetro(F,FW,FK),tobuTojo:scanTobu()},null,2));
