(function(){
  "use strict";

  var statusEl=document.getElementById("route-status");
  var form=document.getElementById("route-form");
  var fromInput=document.getElementById("route-from");
  var toInput=document.getElementById("route-to");
  var datetimeInput=document.getElementById("route-datetime");
  var calendarInput=document.getElementById("route-calendar");
  var swapBtn=document.getElementById("route-swap");
  var submitBtn=document.getElementById("route-submit");
  var stationList=document.getElementById("route-stations");
  var resultEl=document.getElementById("route-result");
  if(!form||!statusEl)return;

  var core=window.RoutePlannerCore;
  var model=null;
  var timetableLines=new Map();
  var timetableCache=new Map();

  function esc(value){return String(value==null?"":value).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
  function safeColor(value){var color=String(value||"").trim();return /^#[0-9a-f]{6}$/i.test(color)?color:"#14386f";}
  function setStatus(text,kind){statusEl.textContent=text;statusEl.className="route-status"+(kind?" is-"+kind:"");}
  function controls(){return[fromInput,toInput,datetimeInput,calendarInput,swapBtn,submitBtn].filter(Boolean);}
  function enableForm(){controls().forEach(function(el){el.disabled=false;});}
  function disableForm(){controls().forEach(function(el){el.disabled=true;});}
  function fetchJson(url){return fetch(url,{cache:"no-store"}).then(function(res){if(!res.ok)throw new Error(url+" : "+res.status);return res.json();});}
  function operatorEntries(manifest){
    if(!manifest||!manifest.operators||Array.isArray(manifest.operators))return[];
    return Object.keys(manifest.operators).map(function(slug){return[slug,manifest.operators[slug]];}).filter(function(pair){return pair[1]&&pair[1].status==="ok";});
  }
  function fillStations(){stationList.innerHTML=model.stations.map(function(station){return'<option value="'+esc(station.label)+'"></option>';}).join("");}
  function localDatetimeValue(date){
    var shifted=new Date(date.getTime()-date.getTimezoneOffset()*60000);
    return shifted.toISOString().slice(0,16);
  }
  function setDefaultDatetime(){
    if(!datetimeInput||datetimeInput.value)return;
    var next=new Date(Date.now()+5*60000);next.setMinutes(Math.ceil(next.getMinutes()/5)*5,0,0);
    datetimeInput.value=localDatetimeValue(next);
  }

  function load(){
    disableForm();setDefaultDatetime();
    if(!core){setStatus("乗換検索プログラムの読み込みに失敗しました。ページを再読み込みしてください。","error");return;}
    fetchJson("./data/transit/manifest.json?v="+Date.now()).then(function(manifest){
      if(manifest&&manifest.status==="waiting-for-odpt-api-key"){
        setStatus("ODPTの初回データ同期待ちです。データ設定が完了すると自動で利用可能になります。","waiting");return;
      }
      var entries=operatorEntries(manifest);
      if(!entries.length){setStatus("利用できる鉄道データがまだありません。ODPTの同期完了後に自動で有効になります。","waiting");return;}
      setStatus("駅・路線・時刻表データを準備しています…","");
      return Promise.all(entries.map(function(pair){
        var slug=pair[0],version=encodeURIComponent(manifest.fetchedAt||Date.now()),base="./data/transit/"+encodeURIComponent(slug)+"/";
        return Promise.all([
          fetchJson(base+"entities.json?v="+version).catch(function(error){console.warn(error);return null;}),
          fetchJson(base+"timetable-index.json?v="+version).catch(function(){return null;})
        ]).then(function(values){return{slug:slug,base:base,entities:values[0],index:values[1]};});
      })).then(function(bundles){
        model=core.createModel(bundles.map(function(bundle){return bundle.entities;}).filter(Boolean));
        if(!model.stations.length)throw new Error("駅データが空です");
        timetableLines.clear();
        bundles.forEach(function(bundle){
          var lines=bundle.index&&bundle.index.lines||{};
          Object.keys(lines).forEach(function(railwayId){
            var line=lines[railwayId];if(line&&line.file)timetableLines.set(railwayId,{url:bundle.base+line.file,info:line});
          });
        });
        fillStations();enableForm();
        var fetched=manifest.fetchedAt?new Date(manifest.fetchedAt):null;
        var suffix=fetched&&!isNaN(fetched.getTime())?"（更新 "+fetched.toLocaleString("ja-JP")+"）":"";
        setStatus("時刻つき乗換検索を使えます。対応駅 "+model.stations.length+"駅・時刻対応 "+timetableLines.size+"路線 "+suffix,"ready");
        applyQuery();
      });
    }).catch(function(error){console.error(error);setStatus("交通データの読み込みに失敗しました。少し時間をおいて再読み込みしてください。","error");});
  }

  function resolve(input){return model?model.resolveInput(input.value):{group:null,ambiguous:false};}
  function showInputError(fromResolved,toResolved){
    if(fromResolved.ambiguous||toResolved.ambiguous)resultEl.innerHTML='<div class="route-empty">同じ名前の駅が複数あります。路線名つきの候補から選んでください。</div>';
    else resultEl.innerHTML='<div class="route-empty">候補にある駅名を選んでください。</div>';
  }
  function selectedDate(){var date=datetimeInput&&datetimeInput.value?new Date(datetimeInput.value):new Date();return isNaN(date.getTime())?new Date():date;}
  function serviceType(date){
    if(calendarInput&&calendarInput.value!=="auto")return calendarInput.value;
    return core.serviceForDate(date);
  }
  function departureMinutes(date){return core.departureMinutesForDate(date);}
  function formatTime(minutes){
    var value=Math.max(0,Math.round(Number(minutes)||0)),day=Math.floor(value/1440),clock=value%1440;
    return(day?"翌":"")+String(Math.floor(clock/60)).padStart(2,"0")+":"+String(clock%60).padStart(2,"0");
  }
  function updateUrl(){
    if(!history.replaceState)return;
    var url=new URL(location.href);url.searchParams.set("from",fromInput.value);url.searchParams.set("to",toInput.value);
    if(datetimeInput&&datetimeInput.value)url.searchParams.set("at",datetimeInput.value);
    if(calendarInput&&calendarInput.value!=="auto")url.searchParams.set("calendar",calendarInput.value);else url.searchParams.delete("calendar");
    history.replaceState(null,"",url);
  }
  function loadTimetables(segments){
    var ids=[];segments.forEach(function(segment){if(ids.indexOf(segment.railway)<0)ids.push(segment.railway);});
    return Promise.all(ids.map(function(railwayId){
      if(timetableCache.has(railwayId))return timetableCache.get(railwayId);
      var entry=timetableLines.get(railwayId);if(!entry)return Promise.resolve([railwayId,null]);
      var promise=fetchJson(entry.url+"?v="+encodeURIComponent(entry.info.trips||"")).then(function(data){return[railwayId,data];});
      timetableCache.set(railwayId,promise);return promise;
    })).then(function(rows){var result={};rows.forEach(function(row){if(row[1])result[row[0]]=row[1];});return result;});
  }
  function trainLabel(segment){
    var parts=[],type=model.displayTrainType(segment.trainType);
    if(type)parts.push(type);if(segment.trainNumber)parts.push(segment.trainNumber+"列車");
    return parts.join("・");
  }
  function renderPath(fromGroup,toGroup,path,timed,warning){
    var segments=timed?timed.segments:model.segmentsFrom(path);
    if(!segments.length){resultEl.innerHTML='<div class="route-empty">同じ駅が選ばれています。</div>';return;}
    var transfers=timed?timed.transfers:Math.max(0,segments.length-1),stops=segments.reduce(function(sum,segment){return sum+segment.stops;},0);
    var arrivalLabel=timed&&timed.estimatedArrival?"着目安":"着";
    var summary=timed?formatTime(timed.departure)+"発 → "+formatTime(timed.arrival)+arrivalLabel+"・"+timed.duration+"分・乗換 "+transfers+"回":stops+"駅・乗換 "+transfers+"回";
    var html='<div class="route-result-card"><div class="route-summary"><strong>'+esc(fromGroup.label)+' → '+esc(toGroup.label)+'</strong><span>'+esc(summary)+'</span></div>';
    if(warning)html+='<div class="route-time-warning">'+esc(warning)+'</div>';
    segments.forEach(function(segment,index){
      if(index>0){
        var transferDetail=timed?"（"+(segment.transferMinutes?"乗換目安 "+segment.transferMinutes+"分・":"")+formatTime(segment.departure)+"発）":"";
        var transferCopy=segment.throughFromPrevious?esc(model.displayStation(segment.from))+"から直通":esc(model.displayStation(segment.from))+"で乗換"+transferDetail;
        html+='<div class="route-transfer">'+transferCopy+'</div>';
      }
      html+='<div class="route-leg" style="--route-line-color:'+safeColor(segment.color)+'"><div class="route-line-rail" aria-hidden="true"></div><div class="route-leg-copy">';
      if(timed)html+='<div class="route-leg-time"><strong>'+formatTime(segment.departure)+' 発</strong><span>→</span><strong>'+formatTime(segment.arrival)+' '+(segment.timeBasis==="station-departure"||segment.timeBasis==="inferred-station-trip"||segment.timeBasis==="estimated-edge-duration"?'着目安':'着')+'</strong></div>';
      html+='<small>'+esc(model.displayStation(segment.from))+' → '+esc(model.displayStation(segment.to))+'</small><strong>'+esc(segment.label)+'</strong><p>'+segment.stops+'駅'+(timed&&trainLabel(segment)?'・'+esc(trainLabel(segment)):'')+'</p></div></div>';
    });
    html+='</div>';resultEl.innerHTML=html;
  }
  function finishSearch(){submitBtn.disabled=false;submitBtn.textContent="時刻を検索";}
  function searchRoute(){
    var fromResolved=resolve(fromInput),toResolved=resolve(toInput);
    if(!fromResolved.group||!toResolved.group){showInputError(fromResolved,toResolved);return;}
    if(fromResolved.group.key===toResolved.group.key){resultEl.innerHTML='<div class="route-empty">出発駅と到着駅が同じです。</div>';return;}
    submitBtn.disabled=true;submitBtn.textContent="検索中…";
    var timedPaths=model.candidatePaths(fromResolved.group,toResolved.group,{allowedRailways:Array.from(timetableLines.keys()),limit:5});
    var timedPath=timedPaths[0]||null;
    var path=timedPath||model.shortestPath(fromResolved.group,toResolved.group);
    if(!path){resultEl.innerHTML='<div class="route-empty">この組み合わせの経路を見つけられませんでした。現在対応している路線の範囲内で試してください。</div>';finishSearch();return;}
    if(!timedPath){renderPath(fromResolved.group,toResolved.group,path,null,"この経路は時刻表データ未対応のため、路線と乗換だけ表示しています。");updateUrl();finishSearch();return;}
    var segments=[];timedPaths.forEach(function(candidate){segments=segments.concat(model.segmentsFrom(candidate));});
    var date=selectedDate(),service=serviceType(date);
    loadTimetables(segments).then(function(timetables){
      var choices=timedPaths.map(function(candidate){return{path:candidate,timed:model.timedItinerary(candidate,timetables,departureMinutes(date),service,5)};}).filter(function(choice){return choice.timed;});
      choices.sort(function(first,second){return first.timed.arrival-second.timed.arrival||second.timed.departure-first.timed.departure||first.timed.transfers-second.timed.transfers;});
      var selected=choices[0],timed=selected&&selected.timed,selectedPath=selected&&selected.path||timedPath;
      if(timed)renderPath(fromResolved.group,toResolved.group,selectedPath,timed,timed.estimatedArrival?"一部路線の到着時刻は、ODPT駅時刻表を駅順に照合して待避・長時間停車を反映した目安です。":"");
      else{
        var departure=model.nextDeparture(timedPath,timetables,departureMinutes(date),service);
        if(departure){
          var type=model.displayTrainType(departure.trainType),copy=departure.label+"は "+formatTime(departure.departure)+" 発"+(type?"（"+type+"）":"")+"です。ODPTの提供データに到着時刻がないため、経路と次の発車時刻を表示しています。";
          renderPath(fromResolved.group,toResolved.group,timedPath,null,copy);
        }else renderPath(fromResolved.group,toResolved.group,timedPath,null,"選んだ時刻・運行日の列車を見つけられませんでした。時刻や平日／土休日を変えて試してください。");
      }
      updateUrl();finishSearch();
    }).catch(function(error){console.error(error);renderPath(fromResolved.group,toResolved.group,path,null,"時刻表の読み込みに失敗したため、路線と乗換だけ表示しています。");finishSearch();});
  }
  function applyQuery(){
    var params=new URLSearchParams(location.search),from=params.get("from"),to=params.get("to"),at=params.get("at"),calendar=params.get("calendar");
    if(from)fromInput.value=from;if(to)toInput.value=to;if(at&&datetimeInput)datetimeInput.value=at;
    if(calendarInput&&(calendar==="weekday"||calendar==="holiday"))calendarInput.value=calendar;
    if(from&&to)searchRoute();
  }

  form.addEventListener("submit",function(event){event.preventDefault();searchRoute();});
  swapBtn.addEventListener("click",function(){var value=fromInput.value;fromInput.value=toInput.value;toInput.value=value;if(fromInput.value&&toInput.value)searchRoute();});
  load();
})();
