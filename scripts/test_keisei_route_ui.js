#!/usr/bin/env node
"use strict";

const fs=require("fs");
const path=require("path");
const vm=require("vm");
const core=require("../route-core.js");
const root=path.resolve(__dirname,"..");

function readJson(relative){return JSON.parse(fs.readFileSync(path.join(root,relative),"utf8"));}
function title(item){const value=item&&item["odpt:stationTitle"];return typeof value==="string"?value:value&&typeof value==="object"?(value.ja||value.en||""):String(item&&item["dc:title"]||"");}
function normalizeName(value){
  const text=String(value||"").normalize("NFKC").replace(/\s+/g,"").trim();
  const aliases={
    "成田空港(成田第1ターミナル)":"成田空港",
    "空港第2ビル(成田第2・第3ターミナル)":"空港第2ビル",
    "空港第2ビル(成田第2・3ターミナル)":"空港第2ビル",
    "新鎌ケ谷":"新鎌ヶ谷",
    "羽田空港第1・第2ターミナル駅":"羽田空港第1・第2ターミナル",
    "羽田空港第3ターミナル駅":"羽田空港第3ターミナル",
    "逗子・葉山駅":"逗子・葉山",
    "井土ケ谷":"井土ヶ谷"
  };
  return aliases[text]||text;
}
function collapse(values){const out=[];for(const value of values)if(value&&out[out.length-1]!==value)out.push(value);return out;}
function same(first,second){first=collapse(first);second=collapse(second);return first.length===second.length&&first.every((value,index)=>value===second[index]);}

const keiseiEntities=readJson("data/transit/keisei/entities.json");
const toeiEntities=readJson("data/transit/toei/entities.json");
const keikyuEntities=readJson("data/transit/keikyu/entities.json");
const hokusoEntities=readJson("data/transit/hokuso/entities.json");
const shibayamaEntities=readJson("data/transit/shibayama/entities.json");
const allEntities=[keiseiEntities,toeiEntities,keikyuEntities,hokusoEntities,shibayamaEntities];
const index=readJson("data/transit/keisei/timetable-index.json");
const network=readJson("data/transit/keisei/"+index.network.file);
const stationIdsByName=new Map();
const displayNameByNormalized=new Map();
for(const entities of allEntities){
  for(const item of entities.Station||[]){
    const rawName=title(item),name=normalizeName(rawName),id=item["owl:sameAs"];
    if(!name||!id)continue;
    if(!stationIdsByName.has(name))stationIdsByName.set(name,new Set());
    stationIdsByName.get(name).add(id);
    if(!displayNameByNormalized.has(name))displayNameByNormalized.set(name,rawName);
  }
}
const stationIndexes=new Map((network.stations||[]).map((value,index)=>[value,index]));

function indexesForName(name){
  const ids=stationIdsByName.get(normalizeName(name))||new Set();
  const indexes=new Set();
  for(const id of ids){const index=stationIndexes.get(id);if(index!=null)indexes.add(index);}
  return indexes;
}
function displayName(name){return displayNameByNormalized.get(normalizeName(name))||name;}

function findFixture(fromName,toName,desired){
  const fromIndexes=indexesForName(fromName),toIndexes=indexesForName(toName);
  if(!fromIndexes.size||!toIndexes.size)throw new Error(`Network station indexes are missing for ${fromName} -> ${toName}`);
  for(const desiredCalendar of ["weekday","holiday"]){
    const candidates=[];
    for(const trip of network.trips||[]){
      if(network.calendars[trip[0]]!==desiredCalendar)continue;
      const stops=trip[3]||[],links=trip[4]||[];
      for(let i=0;i<stops.length;i++){
        if(!fromIndexes.has(stops[i][0]))continue;
        const departure=stops[i][2]!=null?Number(stops[i][2]):Number(stops[i][1]);
        if(!Number.isFinite(departure))continue;
        for(let j=i+1;j<stops.length;j++){
          if(!toIndexes.has(stops[j][0]))continue;
          const used=[];
          for(let k=i;k<j;k++)for(const railwayIndex of links[k]||[]){const railway=network.railways[railwayIndex];if(railway)used.push(railway);}
          if(!same(used,desired))continue;
          const arrival=stops[j][1]!=null?Number(stops[j][1]):Number(stops[j][2]);
          if(Number.isFinite(arrival))candidates.push({departure,arrival,trainNumber:String(trip[2]||""),desired,calendar:desiredCalendar,singleLine:desired.length===1});
        }
      }
    }
    if(candidates.length){
      candidates.sort((a,b)=>a.departure-b.departure||a.arrival-b.arrival||a.trainNumber.localeCompare(b.trainNumber,"ja"));
      return candidates[0];
    }
  }
  throw new Error(`No ${fromName} -> ${toName} direct network fixture found for ${desired.join(" -> ")}`);
}

function element(initial){
  return Object.assign({
    value:"",disabled:false,textContent:"",className:"",innerHTML:"",
    listeners:{},
    addEventListener(type,handler){this.listeners[type]=handler;}
  },initial||{});
}

async function runRouteCase(fromName,toName,fixture){
  const fromLabel=displayName(fromName),toLabel=displayName(toName);
  const baseDate=fixture.calendar==="holiday"?"2026-09-06":"2026-09-02";
  const elements={
    "route-status":element(),
    "route-form":element(),
    "route-from":element({value:fromLabel}),
    "route-to":element({value:toLabel}),
    "route-datetime":element({value:baseDate+"T00:00"}),
    "route-calendar":element({value:fixture.calendar||"weekday"}),
    "route-swap":element(),
    "route-submit":element({textContent:"時刻を検索"}),
    "route-stations":element(),
    "route-result":element()
  };
  const requestedMinute=Math.max(0,fixture.departure-1);
  const hour=Math.floor(requestedMinute/60)%24,minute=requestedMinute%60;
  elements["route-datetime"].value=`${baseDate}T${String(hour).padStart(2,"0")}:${String(minute).padStart(2,"0")}`;

  function fakeFetch(url){
    const clean=String(url).split("?")[0].replace(/^\.\//,"");
    if(clean==="data/transit/manifest.json"){
      const manifest=readJson(clean);
      manifest.operators={
        keisei:manifest.operators.keisei,
        toei:manifest.operators.toei,
        keikyu:manifest.operators.keikyu,
        hokuso:manifest.operators.hokuso,
        shibayama:manifest.operators.shibayama
      };
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

  async function waitFor(predicate,label,timeout=15000){
    const started=Date.now();
    while(Date.now()-started<timeout){
      if(predicate())return;
      await new Promise(resolve=>setTimeout(resolve,20));
    }
    throw new Error("Timed out waiting for "+label);
  }

  await waitFor(()=>elements["route-status"].className.includes("is-ready"),"route data load");
  const submit=elements["route-form"].listeners.submit;
  if(typeof submit!=="function")throw new Error("Route form submit handler was not installed");
  submit({preventDefault(){}});
  await waitFor(()=>elements["route-submit"].textContent==="時刻を検索","route search completion");
  const html=elements["route-result"].innerHTML;
  if(!html.includes("乗換 0回"))throw new Error(`Expected zero-transfer ${fromName} -> ${toName} result: `+html);
  if(!html.includes("（直通）")&&!fixture.singleLine)throw new Error(`Expected direct label for ${fromName} -> ${toName}: `+html);
  if(fixture.trainNumber&&!html.includes(fixture.trainNumber+"列車"))throw new Error("Expected exact direct train number "+fixture.trainNumber+": "+html);
  console.log("Exact route UI OK",{fromName,toName,calendar:fixture.calendar,departure:fixture.departure,arrival:fixture.arrival,trainNumber:fixture.trainNumber,railways:fixture.desired});
}

async function directCase(fromName,toName,desired){
  const fixture=findFixture(fromName,toName,desired);
  await runRouteCase(fromName,toName,fixture);
}

(async()=>{
  await directCase("青砥","新鎌ヶ谷",[
    "odpt.Railway:Keisei.Main",
    "odpt.Railway:Keisei.NaritaSkyAccess"
  ]);

  await directCase("青砥","品川",[
    "odpt.Railway:Keisei.Oshiage",
    "odpt.Railway:Toei.Asakusa",
    "odpt.Railway:Keikyu.Main"
  ]);

  await directCase("成田空港","羽田空港第1・第2ターミナル",[
    "odpt.Railway:Keisei.NaritaSkyAccess",
    "odpt.Railway:Keisei.Main",
    "odpt.Railway:Keisei.Oshiage",
    "odpt.Railway:Toei.Asakusa",
    "odpt.Railway:Keikyu.Main",
    "odpt.Railway:Keikyu.Airport"
  ]);

  await directCase("羽田空港第1・第2ターミナル","成田空港",[
    "odpt.Railway:Keikyu.Airport",
    "odpt.Railway:Keikyu.Main",
    "odpt.Railway:Toei.Asakusa",
    "odpt.Railway:Keisei.Oshiage",
    "odpt.Railway:Keisei.Main",
    "odpt.Railway:Keisei.NaritaSkyAccess"
  ]);

  await directCase("印西牧の原","羽田空港第1・第2ターミナル",[
    "manual.Railway:Hokuso.Hokuso",
    "odpt.Railway:Keisei.Main",
    "odpt.Railway:Keisei.Oshiage",
    "odpt.Railway:Toei.Asakusa",
    "odpt.Railway:Keikyu.Main",
    "odpt.Railway:Keikyu.Airport"
  ]);

  await directCase("羽田空港第1・第2ターミナル","印西牧の原",[
    "odpt.Railway:Keikyu.Airport",
    "odpt.Railway:Keikyu.Main",
    "odpt.Railway:Toei.Asakusa",
    "odpt.Railway:Keisei.Oshiage",
    "odpt.Railway:Keisei.Main",
    "manual.Railway:Hokuso.Hokuso"
  ]);

  await directCase("芝山千代田","京成成田",[
    "manual.Railway:Shibayama.Shibayama",
    "odpt.Railway:Keisei.HigashiNarita"
  ]);

  await directCase("京成成田","芝山千代田",[
    "odpt.Railway:Keisei.HigashiNarita",
    "manual.Railway:Shibayama.Shibayama"
  ]);

  // Keisei's internal branches also need exact no-transfer coverage.
  await directCase("松戸","京成千葉",[
    "odpt.Railway:Keisei.Matsudo",
    "odpt.Railway:Keisei.Chiba"
  ]);

  await directCase("ちはら台","京成千葉",[
    "odpt.Railway:Keisei.Chihara",
    "odpt.Railway:Keisei.Chiba"
  ]);

  // Long cross-operator branches beyond the airports.
  await directCase("芝山千代田","羽田空港第1・第2ターミナル",[
    "manual.Railway:Shibayama.Shibayama",
    "odpt.Railway:Keisei.HigashiNarita",
    "odpt.Railway:Keisei.Main",
    "odpt.Railway:Keisei.Oshiage",
    "odpt.Railway:Toei.Asakusa",
    "odpt.Railway:Keikyu.Main",
    "odpt.Railway:Keikyu.Airport"
  ]);

  await directCase("青砥","京急久里浜",[
    "odpt.Railway:Keisei.Oshiage",
    "odpt.Railway:Toei.Asakusa",
    "odpt.Railway:Keikyu.Main",
    "odpt.Railway:Keikyu.Kurihama"
  ]);

  await directCase("青砥","逗子・葉山",[
    "odpt.Railway:Keisei.Oshiage",
    "odpt.Railway:Toei.Asakusa",
    "odpt.Railway:Keikyu.Main",
    "odpt.Railway:Keikyu.Zushi"
  ]);

  // Explicitly protect the official spelling mismatch normalized by the exact builder.
  await directCase("井土ヶ谷","品川",[
    "odpt.Railway:Keikyu.Main"
  ]);
})().catch(error=>{console.error(error);process.exit(1);});