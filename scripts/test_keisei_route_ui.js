#!/usr/bin/env node
"use strict";

const fs=require("fs");
const path=require("path");
const vm=require("vm");
const core=require("../route-core.js");
const root=path.resolve(__dirname,"..");

function readJson(relative){return JSON.parse(fs.readFileSync(path.join(root,relative),"utf8"));}
function title(item){const value=item&&item["odpt:stationTitle"];return typeof value==="string"?value:value&&typeof value==="object"?(value.ja||value.en||""):String(item&&item["dc:title"]||"");}
function collapse(values){const out=[];for(const value of values)if(value&&out[out.length-1]!==value)out.push(value);return out;}
function same(first,second){first=collapse(first);second=collapse(second);return first.length===second.length&&first.every((value,index)=>value===second[index]);}

const entities=readJson("data/transit/keisei/entities.json");
const index=readJson("data/transit/keisei/timetable-index.json");
const network=readJson("data/transit/keisei/"+index.network.file);
const stationIdByName=new Map((entities.Station||[]).map(item=>[title(item),item["owl:sameAs"]]));
const aoto=stationIdByName.get("青砥");
const shinKamagaya=stationIdByName.get("新鎌ヶ谷");
if(!aoto||!shinKamagaya)throw new Error("Keisei station IDs are missing");
const stationIndexes=new Map((network.stations||[]).map((value,index)=>[value,index]));
const aotoIndex=stationIndexes.get(aoto),shinIndex=stationIndexes.get(shinKamagaya);
const desired=["odpt.Railway:Keisei.Main","odpt.Railway:Keisei.NaritaSkyAccess"];
let fixture=null;
for(const trip of network.trips||[]){
  if(network.calendars[trip[0]]!=="weekday")continue;
  const stops=trip[3]||[],links=trip[4]||[];
  for(let i=0;i<stops.length;i++){
    if(stops[i][0]!==aotoIndex)continue;
    const departure=stops[i][2]!=null?Number(stops[i][2]):Number(stops[i][1]);
    if(!Number.isFinite(departure))continue;
    for(let j=i+1;j<stops.length;j++){
      if(stops[j][0]!==shinIndex)continue;
      const used=[];
      for(let k=i;k<j;k++)for(const railwayIndex of links[k]||[]){const railway=network.railways[railwayIndex];if(railway)used.push(railway);}
      if(!same(used,desired))continue;
      const arrival=stops[j][1]!=null?Number(stops[j][1]):Number(stops[j][2]);
      if(Number.isFinite(arrival)){fixture={departure,arrival,trainNumber:String(trip[2]||"")};break;}
    }
    if(fixture)break;
  }
  if(fixture)break;
}
if(!fixture)throw new Error("No weekday Aoto -> Shin-Kamagaya direct network fixture found");

function element(initial){
  return Object.assign({
    value:"",disabled:false,textContent:"",className:"",innerHTML:"",
    listeners:{},
    addEventListener(type,handler){this.listeners[type]=handler;}
  },initial||{});
}
const elements={
  "route-status":element(),
  "route-form":element(),
  "route-from":element({value:"青砥"}),
  "route-to":element({value:"新鎌ヶ谷"}),
  "route-datetime":element({value:"2026-09-02T00:00"}),
  "route-calendar":element({value:"weekday"}),
  "route-swap":element(),
  "route-submit":element({textContent:"時刻を検索"}),
  "route-stations":element(),
  "route-result":element()
};
const requestedMinute=Math.max(0,fixture.departure-1);
const hour=Math.floor(requestedMinute/60)%24,minute=requestedMinute%60;
elements["route-datetime"].value=`2026-09-02T${String(hour).padStart(2,"0")}:${String(minute).padStart(2,"0")}`;

function fakeFetch(url){
  const clean=String(url).split("?")[0].replace(/^\.\//,"");
  if(clean==="data/transit/manifest.json"){
    const manifest=readJson(clean);
    manifest.operators={keisei:manifest.operators.keisei};
    return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(manifest)});
  }
  const file=path.join(root,clean);
  if(!fs.existsSync(file))return Promise.resolve({ok:false,status:404,json:()=>Promise.reject(new Error("404"))});
  return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(JSON.parse(fs.readFileSync(file,"utf8")))});
}

const context={
  window:{RoutePlannerCore:core},
  document:{getElementById(id){return elements[id]||null;}},
  fetch:fakeFetch,
  history:{replaceState(){}},
  location:{href:"https://example.test/route.html"},
  URL,URLSearchParams,Date,Set,Map,Promise,console,
  setTimeout,clearTimeout
};
context.globalThis=context;
const source=fs.readFileSync(path.join(root,"route.js"),"utf8");
new vm.Script(source,{filename:"route.js"}).runInNewContext(context);

async function waitFor(predicate,label,timeout=10000){
  const started=Date.now();
  while(Date.now()-started<timeout){
    if(predicate())return;
    await new Promise(resolve=>setTimeout(resolve,20));
  }
  throw new Error("Timed out waiting for "+label);
}

(async()=>{
  await waitFor(()=>elements["route-status"].className.includes("is-ready"),"route data load");
  const submit=elements["route-form"].listeners.submit;
  if(typeof submit!=="function")throw new Error("Route form submit handler was not installed");
  submit({preventDefault(){}});
  await waitFor(()=>elements["route-submit"].textContent==="時刻を検索","route search completion");
  const html=elements["route-result"].innerHTML;
  if(!html.includes("乗換 0回"))throw new Error("Expected zero-transfer Keisei direct result: "+html);
  if(!html.includes("（直通）"))throw new Error("Expected network direct label: "+html);
  if(fixture.trainNumber&&!html.includes(fixture.trainNumber+"列車"))throw new Error("Expected exact direct train number "+fixture.trainNumber+": "+html);
  console.log("Keisei through route UI OK",{departure:fixture.departure,arrival:fixture.arrival,trainNumber:fixture.trainNumber});
})().catch(error=>{console.error(error);process.exit(1);});
