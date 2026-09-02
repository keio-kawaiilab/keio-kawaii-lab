(function(){
  "use strict";

  var ROOT="../../";
  var ACCESS_HASH="66123e797f83aea1aff82dbb374efbdf2e6f6565f9cb5116cfd383005e1d6a5b";
  var lock=document.getElementById("preview-lock");
  var lockMessage=document.getElementById("preview-lock-message");
  var app=document.getElementById("preview-app");

  function hex(buffer){return Array.from(new Uint8Array(buffer)).map(function(b){return b.toString(16).padStart(2,"0");}).join("");}
  function authorize(){
    if(sessionStorage.getItem("routePreviewAuthorized")==="1")return Promise.resolve(true);
    var params=new URLSearchParams(location.hash.replace(/^#/,""));
    var key=params.get("key")||"";
    if(!key||!window.crypto||!crypto.subtle)return Promise.resolve(false);
    return crypto.subtle.digest("SHA-256",new TextEncoder().encode(key)).then(function(buf){
      var ok=hex(buf)===ACCESS_HASH;
      if(ok){sessionStorage.setItem("routePreviewAuthorized","1");history.replaceState(null,"",location.pathname+location.search+"#preview");}
      return ok;
    }).catch(function(){return false;});
  }

  authorize().then(function(ok){
    if(!ok){lockMessage.textContent="このプレビューを開くにはオーナー用の閲覧リンクが必要です。";return;}
    lock.hidden=true;app.hidden=false;boot();
  });

  function boot(){
    var core=window.RoutePlannerCore;
    var statusEl=document.getElementById("route-status");
    var form=document.getElementById("route-form");
    var fromInput=document.getElementById("route-from");
    var toInput=document.getElementById("route-to");
    var datetimeInput=document.getElementById("route-datetime");
    var calendarInput=document.getElementById("route-calendar");
    var priorityInput=document.getElementById("route-priority");
    var swapBtn=document.getElementById("route-swap");
    var submitBtn=document.getElementById("route-submit");
    var stationList=document.getElementById("route-stations");
    var resultsSection=document.getElementById("results-section");
    var recentSection=document.getElementById("recent-section");
    var recentSearches=document.getElementById("recent-searches");
    var clearHistory=document.getElementById("clear-history");
    var model=null;
    var manifest=null;
    var timetableLines=new Map();
    var timetableCache=new Map();
    var timetableNetworks=[];
    var timetableNetworkCache=new Map();

    function esc(value){return String(value==null?"":value).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
    function safeColor(value){var color=String(value||"").trim();return /^#[0-9a-f]{6}$/i.test(color)?color:"#35598f";}
    function setStatus(text,kind){statusEl.className="route-status is-"+(kind||"loading");statusEl.innerHTML='<span class="status-dot"></span><span>'+esc(text)+'</span>';}
    function controls(){return[fromInput,toInput,datetimeInput,calendarInput,priorityInput,swapBtn,submitBtn].filter(Boolean);}
    function enableForm(){controls().forEach(function(el){el.disabled=false;});}
    function disableForm(){controls().forEach(function(el){el.disabled=true;});}
    function fetchJson(url){return fetch(url,{cache:"no-store"}).then(function(res){if(!res.ok)throw new Error(url+" : "+res.status);return res.json();});}
    function operatorEntries(data){if(!data||!data.operators||Array.isArray(data.operators))return[];return Object.keys(data.operators).map(function(slug){return[slug,data.operators[slug]];}).filter(function(pair){return pair[1]&&pair[1].status==="ok";});}
    function localDatetimeValue(date){var shifted=new Date(date.getTime()-date.getTimezoneOffset()*60000);return shifted.toISOString().slice(0,16);}
    function setDefaultDatetime(){if(datetimeInput.value)return;var next=new Date(Date.now()+5*60000);next.setMinutes(Math.ceil(next.getMinutes()/5)*5,0,0);datetimeInput.value=localDatetimeValue(next);}
    function formatTime(minutes){var value=Math.max(0,Math.round(Number(minutes)||0)),day=Math.floor(value/1440),clock=value%1440;return(day?"翌 ":"")+String(Math.floor(clock/60)).padStart(2,"0")+":"+String(clock%60).padStart(2,"0");}
    function selectedDate(){var date=datetimeInput.value?new Date(datetimeInput.value):new Date();return isNaN(date.getTime())?new Date():date;}
    function serviceType(date){return calendarInput.value!=="auto"?calendarInput.value:core.serviceForDate(date);}
    function departureMinutes(date){return core.departureMinutesForDate(date);}

    function updateCoverage(){
      var entries=operatorEntries(manifest),lines=0,stations=0;
      entries.forEach(function(pair){lines+=Number(pair[1].timetableLines)||0;stations+=Number(pair[1].stations)||0;});
      document.getElementById("coverage-operators").textContent=entries.length.toLocaleString("ja-JP");
      document.getElementById("coverage-lines").textContent=lines.toLocaleString("ja-JP");
      document.getElementById("coverage-stations").textContent=stations.toLocaleString("ja-JP");
    }

    function fillStations(){stationList.innerHTML=model.stations.map(function(station){return'<option value="'+esc(station.label)+'"></option>';}).join("");}

    function load(){
      disableForm();setDefaultDatetime();
      if(!core){setStatus("乗換検索プログラムを読み込めませんでした。","error");return;}
      fetchJson(ROOT+"data/transit/manifest.json?v="+Date.now()).then(function(data){
        manifest=data;updateCoverage();
        var entries=operatorEntries(data);if(!entries.length)throw new Error("交通データが空です");
        setStatus("駅・路線・時刻表データを準備しています…","loading");
        return Promise.all(entries.map(function(pair){
          var slug=pair[0],version=encodeURIComponent((pair[1]&&pair[1].timetableBuiltAt)||data.fetchedAt||Date.now()),base=ROOT+"data/transit/"+encodeURIComponent(slug)+"/";
          return Promise.all([
            fetchJson(base+"entities.json?v="+version).catch(function(error){console.warn(error);return null;}),
            fetchJson(base+"timetable-index.json?v="+version).catch(function(){return null;})
          ]).then(function(values){return{slug:slug,base:base,entities:values[0],index:values[1]};});
        }));
      }).then(function(bundles){
        model=core.createModel(bundles.map(function(bundle){return bundle.entities;}).filter(Boolean));
        if(!model.stations.length)throw new Error("駅データが空です");
        timetableLines.clear();timetableNetworks=[];timetableCache.clear();timetableNetworkCache.clear();
        bundles.forEach(function(bundle){
          var lines=bundle.index&&bundle.index.lines||{};
          Object.keys(lines).forEach(function(railwayId){var line=lines[railwayId];if(line&&line.file)timetableLines.set(railwayId,{url:bundle.base+line.file,info:line});});
          var network=bundle.index&&bundle.index.network;
          if(network&&network.file&&Array.isArray(network.railways)&&network.railways.length){timetableNetworks.push({id:String(network.id||bundle.slug+"-network"),url:bundle.base+network.file,info:network,railways:new Set(network.railways)});}
        });
        fillStations();enableForm();
        setStatus("検索できます。時刻対応 "+timetableLines.size+"路線 / 駅候補 "+model.stations.length.toLocaleString("ja-JP")+"件","ready");
        applyQuery();renderHistory();
      }).catch(function(error){console.error(error);setStatus("交通データの読み込みに失敗しました。再読み込みしてください。","error");});
    }

    function resolve(input){return model?model.resolveInput(input.value):{group:null,ambiguous:false};}
    function calendarMatches(value,service){var text=String(value||"").toLowerCase();if(!text)return true;if(service==="weekday")return text.indexOf("weekday")>=0||text.indexOf("平日")>=0;return text.indexOf("saturdayholiday")>=0||text.indexOf("saturdayandholiday")>=0||text.indexOf("weekend")>=0||text.indexOf("saturday")>=0||text.indexOf("sunday")>=0||text.indexOf("holiday")>=0||text.indexOf("土休日")>=0||text.indexOf("土曜")>=0||text.indexOf("休日")>=0;}
    function collapseRailways(values){var result=[];(values||[]).forEach(function(value){if(value&&result[result.length-1]!==value)result.push(value);});return result;}
    function sameRailwaySequence(first,second){first=collapseRailways(first);second=collapseRailways(second);if(first.length!==second.length)return false;for(var i=0;i<first.length;i++)if(first[i]!==second[i])return false;return true;}

    function loadTimetables(paths){
      var ids=[];paths.forEach(function(path){model.segmentsFrom(path).forEach(function(segment){if(ids.indexOf(segment.railway)<0)ids.push(segment.railway);});});
      var linePromises=ids.map(function(railwayId){
        if(timetableCache.has(railwayId))return timetableCache.get(railwayId);
        var entry=timetableLines.get(railwayId);if(!entry)return Promise.resolve([railwayId,null]);
        var promise=fetchJson(entry.url+"?v="+encodeURIComponent(entry.info.inferredTrips||entry.info.trips||entry.info.departures||"")).then(function(data){return[railwayId,data];});
        timetableCache.set(railwayId,promise);return promise;
      });
      var networkPromises=timetableNetworks.filter(function(entry){return ids.filter(function(id){return entry.railways.has(id);}).length>=2;}).map(function(entry){
        if(timetableNetworkCache.has(entry.id))return timetableNetworkCache.get(entry.id);
        var promise=fetchJson(entry.url+"?v="+encodeURIComponent(entry.info.trips||"")).then(function(data){return{entry:entry,data:data};});
        timetableNetworkCache.set(entry.id,promise);return promise;
      });
      return Promise.all([Promise.all(linePromises),Promise.all(networkPromises)]).then(function(groups){var result={};groups[0].forEach(function(row){if(row[1])result[row[0]]=row[1];});result.__networks=groups[1];return result;});
    }

    function networkTrip(table,fromNodes,toNodes,earliest,service,desiredRailways){
      if(!table||table.timeBasis!=="train-timetable-network"||!Array.isArray(table.trips))return null;
      var stations=table.stations||[],calendars=table.calendars||[],types=table.trainTypes||[],railways=table.railways||[];
      var fromSet=new Set(fromNodes||[]),toSet=new Set(toNodes||[]),best=null;
      table.trips.forEach(function(trip){
        if(!Array.isArray(trip)||!calendarMatches(calendars[trip[0]],service))return;
        var stops=trip[3]||[],links=trip[4]||[],boarding=-1,departure=null;
        for(var i=0;i<stops.length;i++){var stop=stops[i]||[],stationId=stations[stop[0]],dep=stop[2]!=null?Number(stop[2]):Number(stop[1]);if(fromSet.has(stationId)&&Number.isFinite(dep)&&dep>=earliest){boarding=i;departure=dep;break;}}
        if(boarding<0)return;
        for(var j=boarding+1;j<stops.length;j++){
          var next=stops[j]||[],nextStation=stations[next[0]],arrival=next[1]!=null?Number(next[1]):Number(next[2]);if(!toSet.has(nextStation)||!Number.isFinite(arrival)||arrival<departure)continue;
          var used=[];for(var linkIndex=boarding;linkIndex<j;linkIndex++){(links[linkIndex]||[]).forEach(function(railwayIndex){var id=railways[railwayIndex];if(id)used.push(id);});}
          used=collapseRailways(used);if(!sameRailwaySequence(used,desiredRailways))continue;
          var candidate={departure:departure,arrival:arrival,trainType:types[trip[1]]||"",trainNumber:String(trip[2]||""),timeBasis:"train-timetable-network",routeRailways:used,observedStops:j-boarding+1};
          if(!best||candidate.arrival<best.arrival||(candidate.arrival===best.arrival&&candidate.departure>best.departure))best=candidate;break;
        }
      });return best;
    }

    function networkTimedItinerary(path,fromGroup,toGroup,timetables,earliest,service){
      var segments=model.segmentsFrom(path);if(segments.length<2)return null;
      var desired=collapseRailways(segments.map(function(segment){return segment.railway;})),networks=timetables&&timetables.__networks||[],best=null;
      networks.forEach(function(row){
        if(!row||!row.entry||!row.data||!desired.every(function(railwayId){return row.entry.railways.has(railwayId);}))return;
        var trip=networkTrip(row.data,fromGroup.nodes,toGroup.nodes,earliest,service,desired);if(!trip)return;
        var labels=[];segments.forEach(function(segment){if(segment.label&&labels.indexOf(segment.label)<0)labels.push(segment.label);});
        var composite={railway:segments[0].railway,label:labels.join("・")+"（直通）",color:segments[0].color,from:segments[0].from,to:segments[segments.length-1].to,stops:Math.max(1,trip.observedStops-1),transferBefore:false,departure:trip.departure,arrival:trip.arrival,trainType:trip.trainType,trainNumber:trip.trainNumber,timeBasis:trip.timeBasis,networkDirect:true};
        var timed={segments:[composite],departure:trip.departure,arrival:trip.arrival,duration:trip.arrival-trip.departure,transfers:0,estimatedArrival:false,networkDirect:true};
        if(!best||timed.arrival<best.arrival||(timed.arrival===best.arrival&&timed.departure>best.departure))best=timed;
      });return best;
    }

    function bestTimedItinerary(path,fromGroup,toGroup,timetables,earliest,service){
      var normal=model.timedItinerary(path,timetables,earliest,service,5);
      var direct=networkTimedItinerary(path,fromGroup,toGroup,timetables,earliest,service);
      if(!normal)return direct;if(!direct)return normal;
      if(direct.arrival<normal.arrival)return direct;if(direct.arrival===normal.arrival&&direct.transfers<normal.transfers)return direct;if(direct.arrival===normal.arrival&&direct.transfers===normal.transfers&&direct.departure>normal.departure)return direct;return normal;
    }

    function trainLabel(segment){var parts=[],type=model.displayTrainType(segment.trainType);if(type)parts.push(type);if(segment.trainNumber)parts.push(segment.trainNumber+"列車");return parts.join("・");}
    function stationLabel(id){return model.displayStation(id)||String(id||"").split(".").pop();}
    function isEstimated(segment){return segment.timeBasis==="station-departure"||segment.timeBasis==="inferred-station-trip"||segment.timeBasis==="estimated-edge-duration";}
    function routeSignature(choice){return choice.timed.segments.map(function(s){return[s.railway,s.from,s.to].join("|");}).join(">");}

    function renderLeg(segment,index,total){
      var color=safeColor(segment.color),label=esc(segment.label||"鉄道路線"),train=esc(trainLabel(segment)),from=esc(stationLabel(segment.from)),to=esc(stationLabel(segment.to));
      var detail=[];if(train)detail.push("<strong>"+train+"</strong>");if(segment.stops)detail.push(segment.stops+"駅");if(segment.networkDirect)detail.push("直通運転");if(isEstimated(segment))detail.push("到着時刻は目安");
      var html='<div class="route-leg"><div class="leg-clock"><span>発</span>'+formatTime(segment.departure)+'<span style="margin-top:42px">着</span>'+formatTime(segment.arrival)+'</div><div class="leg-rail" style="--route-color:'+color+'"></div><div class="leg-main"><h3>'+from+' → '+to+'</h3><div class="leg-line"><span class="line-dot" style="--route-color:'+color+'"></span><span>'+label+'</span></div><div class="leg-detail">'+detail.map(function(d){return'<span>'+d+'</span>';}).join("")+'</div></div></div>';
      if(index<total-1&&!segment.throughFromPrevious)html+='<div class="transfer-row">↳ 乗換'+(segment.transferMinutes?"・目安 "+segment.transferMinutes+"分":"")+'</div>';
      return html;
    }

    function renderChoices(fromGroup,toGroup,choices,service,date){
      if(!choices.length){resultsSection.innerHTML='<div class="route-empty-state"><h2>この条件では時刻つき経路が見つかりませんでした</h2><p>日時や駅名を変えてもう一度試してください。</p></div>';return;}
      var dayLabel=service==="weekday"?"平日ダイヤ":"土休日ダイヤ";
      var header='<div class="results-header"><div><p class="section-kicker">RESULT</p><h2>'+esc(fromGroup.label)+' → '+esc(toGroup.label)+'</h2><p>'+date.toLocaleString("ja-JP",{month:"numeric",day:"numeric",weekday:"short",hour:"2-digit",minute:"2-digit"})+' 出発・'+dayLabel+'</p></div><div></div></div>';
      var cards=choices.slice(0,3).map(function(choice,index){
        var timed=choice.timed,arrivalLabel=timed.estimatedArrival?"着目安":"着";
        var meta='<span>'+timed.duration+'分</span><span>乗換 '+timed.transfers+'回</span>'+(index===0?'<span class="best-pill">おすすめ</span>':'');
        var warning=timed.estimatedArrival?'<div class="result-warning">この経路には駅時刻表から算出した到着目安が含まれます。</div>':'';
        return'<article class="result-card '+(index===0?'is-best':'')+'"><div class="result-head"><div class="result-rank">'+(index+1)+'</div><div class="result-time"><strong>'+formatTime(timed.departure)+'<span>→</span>'+formatTime(timed.arrival)+'</strong><small>'+arrivalLabel+' / '+(timed.networkDirect?'直通列車を優先':'予定時刻表ベース')+'</small></div><div class="result-meta">'+meta+'</div></div><div class="route-legs">'+timed.segments.map(function(segment,i){return renderLeg(segment,i,timed.segments.length);}).join("")+'</div>'+warning+'</article>';
      }).join("");
      resultsSection.innerHTML=header+'<div class="result-list">'+cards+'</div>';
    }

    function sortChoices(choices){
      var mode=priorityInput.value;
      choices.sort(function(a,b){
        if(mode==="transfers")return a.timed.transfers-b.timed.transfers||a.timed.arrival-b.timed.arrival||a.timed.duration-b.timed.duration;
        return a.timed.arrival-b.timed.arrival||a.timed.transfers-b.timed.transfers||a.timed.duration-b.timed.duration||b.timed.departure-a.timed.departure;
      });
      var seen=new Set();return choices.filter(function(choice){var key=routeSignature(choice)+"|"+choice.timed.departure+"|"+choice.timed.arrival;if(seen.has(key))return false;seen.add(key);return true;});
    }

    function showInputError(fromResolved,toResolved){var msg=(fromResolved.ambiguous||toResolved.ambiguous)?"同名駅が複数あります。候補から選び直してください。":"候補にある駅名を選んでください。";resultsSection.innerHTML='<div class="route-empty-state"><h2>駅名を確認してください</h2><p>'+esc(msg)+'</p></div>';}
    function setSearching(active){submitBtn.disabled=active;submitBtn.innerHTML=active?'<span class="route-submit-icon">…</span><span>検索中</span>':'<span class="route-submit-icon">⌕</span><span>乗換を検索</span>';}

    function searchRoute(){
      var fromResolved=resolve(fromInput),toResolved=resolve(toInput);if(!fromResolved.group||!toResolved.group){showInputError(fromResolved,toResolved);return;}
      if(fromResolved.group.key===toResolved.group.key){resultsSection.innerHTML='<div class="route-empty-state"><h2>同じ駅が選ばれています</h2><p>出発駅と到着駅を変えてください。</p></div>';return;}
      setSearching(true);
      var paths=model.candidatePaths(fromResolved.group,toResolved.group,{allowedRailways:Array.from(timetableLines.keys()),limit:8});
      if(!paths.length){resultsSection.innerHTML='<div class="route-empty-state"><h2>経路を見つけられませんでした</h2><p>現在の対応エリア内で別の駅を試してください。</p></div>';setSearching(false);return;}
      var date=selectedDate(),service=serviceType(date),start=departureMinutes(date);
      loadTimetables(paths).then(function(timetables){
        var choices=paths.map(function(path){return{path:path,timed:bestTimedItinerary(path,fromResolved.group,toResolved.group,timetables,start,service)};}).filter(function(choice){return choice.timed;});
        choices=sortChoices(choices);renderChoices(fromResolved.group,toResolved.group,choices,service,date);saveHistory(fromGroupLabel(fromResolved.group),fromGroupLabel(toResolved.group));updateUrl();
      }).catch(function(error){console.error(error);resultsSection.innerHTML='<div class="route-empty-state"><h2>検索中にエラーが起きました</h2><p>ページを再読み込みしてもう一度試してください。</p></div>';}).finally(function(){setSearching(false);});
    }

    function fromGroupLabel(group){return group&&group.label||"";}
    function updateUrl(){if(!history.replaceState)return;var url=new URL(location.href);url.searchParams.set("from",fromInput.value);url.searchParams.set("to",toInput.value);if(datetimeInput.value)url.searchParams.set("at",datetimeInput.value);if(calendarInput.value!=="auto")url.searchParams.set("calendar",calendarInput.value);else url.searchParams.delete("calendar");if(priorityInput.value!=="fastest")url.searchParams.set("priority",priorityInput.value);else url.searchParams.delete("priority");history.replaceState(null,"",url.pathname+url.search+"#preview");}
    function applyQuery(){var params=new URLSearchParams(location.search);if(params.get("from"))fromInput.value=params.get("from");if(params.get("to"))toInput.value=params.get("to");if(params.get("at"))datetimeInput.value=params.get("at");if(["weekday","holiday"].indexOf(params.get("calendar"))>=0)calendarInput.value=params.get("calendar");if(["fastest","transfers"].indexOf(params.get("priority"))>=0)priorityInput.value=params.get("priority");if(fromInput.value&&toInput.value)setTimeout(searchRoute,0);}

    var HISTORY_KEY="routePreviewRecent";
    function readHistory(){try{return JSON.parse(localStorage.getItem(HISTORY_KEY)||"[]").filter(function(x){return x&&x.from&&x.to;}).slice(0,6);}catch(e){return[];}}
    function saveHistory(from,to){var items=readHistory().filter(function(x){return!(x.from===from&&x.to===to);});items.unshift({from:from,to:to,at:Date.now()});localStorage.setItem(HISTORY_KEY,JSON.stringify(items.slice(0,6)));renderHistory();}
    function renderHistory(){var items=readHistory();recentSection.hidden=!items.length;if(!items.length){recentSearches.innerHTML="";return;}recentSearches.innerHTML=items.map(function(item,index){var date=new Date(item.at);return'<button class="recent-chip" type="button" data-history="'+index+'"><strong>'+esc(item.from)+' → '+esc(item.to)+'</strong><span>'+date.toLocaleDateString("ja-JP",{month:"numeric",day:"numeric"})+' に検索</span></button>';}).join("");}

    form.addEventListener("submit",function(event){event.preventDefault();searchRoute();});
    swapBtn.addEventListener("click",function(){var value=fromInput.value;fromInput.value=toInput.value;toInput.value=value;});
    priorityInput.addEventListener("change",function(){if(fromInput.value&&toInput.value)searchRoute();});
    document.querySelectorAll("[data-clear]").forEach(function(button){button.addEventListener("click",function(){var input=document.getElementById(button.getAttribute("data-clear"));if(input){input.value="";input.focus();}});});
    document.querySelectorAll(".route-shortcuts button[data-from]").forEach(function(button){button.addEventListener("click",function(){fromInput.value=button.dataset.from;toInput.value=button.dataset.to;searchRoute();});});
    recentSearches.addEventListener("click",function(event){var button=event.target.closest("[data-history]");if(!button)return;var item=readHistory()[Number(button.dataset.history)];if(!item)return;fromInput.value=item.from;toInput.value=item.to;searchRoute();});
    clearHistory.addEventListener("click",function(){localStorage.removeItem(HISTORY_KEY);renderHistory();});
    load();
  }
})();
