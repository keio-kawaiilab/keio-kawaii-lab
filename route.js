(function(){
  "use strict";

  var statusEl=document.getElementById("route-status");
  var form=document.getElementById("route-form");
  var fromInput=document.getElementById("route-from");
  var toInput=document.getElementById("route-to");
  var swapBtn=document.getElementById("route-swap");
  var submitBtn=document.getElementById("route-submit");
  var stationList=document.getElementById("route-stations");
  var resultEl=document.getElementById("route-result");
  if(!form||!statusEl)return;

  var graph=new Map();
  var stationById=new Map();
  var stationGroups=new Map();
  var railwayById=new Map();
  var displayNameToKey=new Map();

  function esc(value){return String(value==null?"":value).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
  function title(value){
    if(typeof value==="string")return value;
    if(value&&typeof value==="object")return value.ja||value.en||Object.values(value)[0]||"";
    return"";
  }
  function norm(value){return String(value||"").normalize("NFKC").replace(/[\s　]/g,"").replace(/駅$/,"").toLowerCase();}
  function idOf(item){return item&&item["owl:sameAs"]||"";}
  function stationName(item){return title(item&&item["odpt:stationTitle"])||item&&item["dc:title"]||idOf(item).split(".").pop()||"駅";}
  function railwayName(item){return title(item&&item["odpt:railwayTitle"])||item&&item["dc:title"]||idOf(item).split(".").pop()||"路線";}
  function addEdge(from,to,edge){
    if(!from||!to||from===to)return;
    if(!graph.has(from))graph.set(from,[]);
    graph.get(from).push(Object.assign({to:to},edge));
  }
  function distanceMeters(a,b){
    var lat1=Number(a&&a["geo:lat"]),lon1=Number(a&&a["geo:long"]),lat2=Number(b&&b["geo:lat"]),lon2=Number(b&&b["geo:long"]);
    if(!isFinite(lat1)||!isFinite(lon1)||!isFinite(lat2)||!isFinite(lon2))return null;
    var r=6371000,rad=Math.PI/180,dLat=(lat2-lat1)*rad,dLon=(lon2-lon1)*rad;
    var x=Math.sin(dLat/2)*Math.sin(dLat/2)+Math.cos(lat1*rad)*Math.cos(lat2*rad)*Math.sin(dLon/2)*Math.sin(dLon/2);
    return 2*r*Math.atan2(Math.sqrt(x),Math.sqrt(1-x));
  }
  function setStatus(text,kind){
    statusEl.textContent=text;
    statusEl.className="route-status"+(kind?" is-"+kind:"");
  }
  function enableForm(){
    [fromInput,toInput,swapBtn,submitBtn].forEach(function(el){el.disabled=false;});
  }
  function disableForm(){
    [fromInput,toInput,swapBtn,submitBtn].forEach(function(el){el.disabled=true;});
  }

  function addEntities(payload){
    var stations=payload&&payload.Station||[];
    var railways=payload&&payload.Railway||[];
    stations.forEach(function(item){
      var id=idOf(item);if(!id)return;
      stationById.set(id,item);
      var name=stationName(item),key=norm(name);if(!key)return;
      if(!stationGroups.has(key))stationGroups.set(key,{name:name,nodes:[]});
      var group=stationGroups.get(key);
      if(group.nodes.indexOf(id)<0)group.nodes.push(id);
      if(String(name).localeCompare(String(group.name),"ja")<0)group.name=name;
    });
    railways.forEach(function(item){var id=idOf(item);if(id)railwayById.set(id,item);});
  }

  function buildRideGraph(){
    railwayById.forEach(function(railway,railwayId){
      var order=Array.isArray(railway["odpt:stationOrder"])?railway["odpt:stationOrder"].slice():[];
      order.sort(function(a,b){return Number(a&&a["odpt:index"]||0)-Number(b&&b["odpt:index"]||0);});
      var lineLabel=railwayName(railway);
      for(var i=0;i<order.length-1;i++){
        var a=order[i]&&order[i]["odpt:station"],b=order[i+1]&&order[i+1]["odpt:station"];
        if(!a||!b)continue;
        addEdge(a,b,{type:"ride",railway:railwayId,label:lineLabel,cost:1});
        addEdge(b,a,{type:"ride",railway:railwayId,label:lineLabel,cost:1});
      }
    });
  }

  function buildTransferGraph(){
    stationGroups.forEach(function(group){
      var nodes=group.nodes;
      for(var i=0;i<nodes.length;i++)for(var j=i+1;j<nodes.length;j++){
        var a=stationById.get(nodes[i]),b=stationById.get(nodes[j]);
        var meters=distanceMeters(a,b);
        if(meters!==null&&meters>850)continue;
        addEdge(nodes[i],nodes[j],{type:"transfer",label:"乗換",cost:4});
        addEdge(nodes[j],nodes[i],{type:"transfer",label:"乗換",cost:4});
      }
    });
  }

  function populateStations(){
    var groups=Array.from(stationGroups.entries()).sort(function(a,b){return a[1].name.localeCompare(b[1].name,"ja");});
    stationList.innerHTML=groups.map(function(pair){return'<option value="'+esc(pair[1].name)+'"></option>';}).join("");
    displayNameToKey.clear();
    groups.forEach(function(pair){displayNameToKey.set(norm(pair[1].name),pair[0]);});
  }

  function operatorEntries(manifest){
    if(!manifest||!manifest.operators||Array.isArray(manifest.operators))return[];
    return Object.keys(manifest.operators).map(function(slug){return[slug,manifest.operators[slug]];}).filter(function(pair){return pair[1]&&pair[1].status==="ok";});
  }

  function fetchJson(url){return fetch(url,{cache:"no-store"}).then(function(res){if(!res.ok)throw new Error(url+" : "+res.status);return res.json();});}

  function load(){
    disableForm();
    fetchJson("./data/transit/manifest.json?v="+Date.now()).then(function(manifest){
      if(manifest&&manifest.status==="waiting-for-odpt-api-key"){
        setStatus("ODPTの初回データ同期待ちです。管理側でアクセストークンを設定すると自動で利用可能になります。","waiting");
        return;
      }
      var entries=operatorEntries(manifest);
      if(!entries.length){
        setStatus("利用できる鉄道データがまだありません。ODPTの同期完了後に自動で有効になります。","waiting");
        return;
      }
      setStatus("駅・路線データを準備しています…","");
      return Promise.all(entries.map(function(pair){
        return fetchJson("./data/transit/"+encodeURIComponent(pair[0])+"/entities.json?v="+encodeURIComponent(manifest.fetchedAt||Date.now())).catch(function(){return null;});
      })).then(function(payloads){
        payloads.filter(Boolean).forEach(addEntities);
        buildRideGraph();
        buildTransferGraph();
        populateStations();
        if(!stationGroups.size)throw new Error("駅データが空です");
        enableForm();
        var fetched=manifest.fetchedAt?new Date(manifest.fetchedAt):null;
        var suffix=fetched&&!isNaN(fetched.getTime())?"（データ更新 "+fetched.toLocaleString("ja-JP")+"）":"";
        setStatus("乗換ルート検索を使えます。対応駅 "+stationGroups.size+"駅 "+suffix,"ready");
        applyQuery();
      });
    }).catch(function(error){
      console.error(error);
      setStatus("交通データの読み込みに失敗しました。少し時間をおいて再読み込みしてください。","error");
    });
  }

  function groupForInput(value){return stationGroups.get(displayNameToKey.get(norm(value))||norm(value))||null;}

  function shortestPath(originGroup,destinationGroup){
    var target=new Set(destinationGroup.nodes),dist=new Map(),prev=new Map(),queue=[];
    originGroup.nodes.forEach(function(node){dist.set(node,0);queue.push({node:node,cost:0});});
    var reached=null;
    while(queue.length){
      queue.sort(function(a,b){return a.cost-b.cost;});
      var current=queue.shift();
      if(current.cost!==dist.get(current.node))continue;
      if(target.has(current.node)){reached=current.node;break;}
      (graph.get(current.node)||[]).forEach(function(edge){
        var nextCost=current.cost+edge.cost;
        if(nextCost<(dist.has(edge.to)?dist.get(edge.to):Infinity)){
          dist.set(edge.to,nextCost);
          prev.set(edge.to,{node:current.node,edge:edge});
          queue.push({node:edge.to,cost:nextCost});
        }
      });
    }
    if(!reached)return null;
    var edges=[],cursor=reached;
    while(prev.has(cursor)){
      var step=prev.get(cursor);
      edges.push({from:step.node,to:cursor,edge:step.edge});
      cursor=step.node;
    }
    edges.reverse();
    return{edges:edges,cost:dist.get(reached)};
  }

  function displayStation(id){return stationName(stationById.get(id)||{"owl:sameAs":id});}

  function segmentsFrom(path){
    var segments=[],pendingTransfer=false;
    path.edges.forEach(function(step){
      if(step.edge.type==="transfer"){
        pendingTransfer=true;
        return;
      }
      var last=segments[segments.length-1];
      if(last&&last.railway===step.edge.railway&&!pendingTransfer){
        last.to=step.to;last.stops+=1;
      }else{
        segments.push({railway:step.edge.railway,label:step.edge.label,from:step.from,to:step.to,stops:1,transferBefore:segments.length>0||pendingTransfer});
      }
      pendingTransfer=false;
    });
    return segments;
  }

  function renderPath(fromName,toName,path){
    var segments=segmentsFrom(path);
    if(!segments.length){resultEl.innerHTML='<div class="route-empty">同じ駅が選ばれています。</div>';return;}
    var transfers=Math.max(0,segments.length-1),stops=segments.reduce(function(sum,s){return sum+s.stops;},0);
    var html='<div class="route-result-card"><div class="route-summary"><strong>'+esc(fromName)+' → '+esc(toName)+'</strong><span>'+stops+'駅・乗換 '+transfers+'回</span></div>';
    segments.forEach(function(seg,index){
      if(index>0)html+='<div class="route-transfer">'+esc(displayStation(seg.from))+'で乗換</div>';
      html+='<div class="route-leg"><div class="route-line-rail" aria-hidden="true"></div><div class="route-leg-copy"><small>'+esc(displayStation(seg.from))+' → '+esc(displayStation(seg.to))+'</small><strong>'+esc(seg.label)+'</strong><p>'+seg.stops+'駅</p></div></div>';
    });
    html+='</div>';
    resultEl.innerHTML=html;
  }

  function searchRoute(){
    var fromGroup=groupForInput(fromInput.value),toGroup=groupForInput(toInput.value);
    if(!fromGroup||!toGroup){resultEl.innerHTML='<div class="route-empty">候補にある駅名を選んでください。</div>';return;}
    if(fromGroup===toGroup){resultEl.innerHTML='<div class="route-empty">出発駅と到着駅が同じです。</div>';return;}
    submitBtn.disabled=true;submitBtn.textContent="検索中…";
    window.setTimeout(function(){
      var path=shortestPath(fromGroup,toGroup);
      if(path)renderPath(fromGroup.name,toGroup.name,path);
      else resultEl.innerHTML='<div class="route-empty">この組み合わせの経路を見つけられませんでした。現在対応している路線の範囲内で試してください。</div>';
      submitBtn.disabled=false;submitBtn.textContent="経路を検索";
    },0);
  }

  function applyQuery(){
    var params=new URLSearchParams(location.search),from=params.get("from"),to=params.get("to");
    if(from)fromInput.value=from;if(to)toInput.value=to;
    if(from&&to)searchRoute();
  }

  form.addEventListener("submit",function(event){event.preventDefault();searchRoute();});
  swapBtn.addEventListener("click",function(){var value=fromInput.value;fromInput.value=toInput.value;toInput.value=value;});
  load();
})();
