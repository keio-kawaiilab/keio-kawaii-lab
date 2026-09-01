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

  var core=window.RoutePlannerCore;
  var model=null;

  function esc(value){return String(value==null?"":value).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
  function safeColor(value){var color=String(value||"").trim();return /^#[0-9a-f]{6}$/i.test(color)?color:"#14386f";}
  function setStatus(text,kind){statusEl.textContent=text;statusEl.className="route-status"+(kind?" is-"+kind:"");}
  function enableForm(){[fromInput,toInput,swapBtn,submitBtn].forEach(function(el){el.disabled=false;});}
  function disableForm(){[fromInput,toInput,swapBtn,submitBtn].forEach(function(el){el.disabled=true;});}
  function fetchJson(url){return fetch(url,{cache:"no-store"}).then(function(res){if(!res.ok)throw new Error(url+" : "+res.status);return res.json();});}
  function operatorEntries(manifest){
    if(!manifest||!manifest.operators||Array.isArray(manifest.operators))return[];
    return Object.keys(manifest.operators).map(function(slug){return[slug,manifest.operators[slug]];}).filter(function(pair){return pair[1]&&pair[1].status==="ok";});
  }
  function fillStations(){stationList.innerHTML=model.stations.map(function(station){return'<option value="'+esc(station.label)+'"></option>';}).join("");}

  function load(){
    disableForm();
    if(!core){setStatus("乗換検索プログラムの読み込みに失敗しました。ページを再読み込みしてください。","error");return;}
    fetchJson("./data/transit/manifest.json?v="+Date.now()).then(function(manifest){
      if(manifest&&manifest.status==="waiting-for-odpt-api-key"){
        setStatus("ODPTの初回データ同期待ちです。データ設定が完了すると自動で利用可能になります。","waiting");
        return;
      }
      var entries=operatorEntries(manifest);
      if(!entries.length){setStatus("利用できる鉄道データがまだありません。ODPTの同期完了後に自動で有効になります。","waiting");return;}
      setStatus("駅・路線データを準備しています…","");
      return Promise.all(entries.map(function(pair){
        return fetchJson("./data/transit/"+encodeURIComponent(pair[0])+"/entities.json?v="+encodeURIComponent(manifest.fetchedAt||Date.now())).catch(function(error){console.warn(error);return null;});
      })).then(function(payloads){
        model=core.createModel(payloads.filter(Boolean));
        if(!model.stations.length)throw new Error("駅データが空です");
        fillStations();enableForm();
        var fetched=manifest.fetchedAt?new Date(manifest.fetchedAt):null;
        var suffix=fetched&&!isNaN(fetched.getTime())?"（データ更新 "+fetched.toLocaleString("ja-JP")+"）":"";
        setStatus("乗換ルート検索を使えます。対応駅 "+model.stations.length+"駅 "+suffix,"ready");
        applyQuery();
      });
    }).catch(function(error){console.error(error);setStatus("交通データの読み込みに失敗しました。少し時間をおいて再読み込みしてください。","error");});
  }

  function resolve(input){return model?model.resolveInput(input.value):{group:null,ambiguous:false};}
  function showInputError(fromResolved,toResolved){
    if(fromResolved.ambiguous||toResolved.ambiguous)resultEl.innerHTML='<div class="route-empty">同じ名前の駅が複数あります。路線名つきの候補から選んでください。</div>';
    else resultEl.innerHTML='<div class="route-empty">候補にある駅名を選んでください。</div>';
  }
  function updateUrl(){
    if(!history.replaceState)return;
    var url=new URL(location.href);url.searchParams.set("from",fromInput.value);url.searchParams.set("to",toInput.value);history.replaceState(null,"",url);
  }
  function renderPath(fromGroup,toGroup,path){
    var segments=model.segmentsFrom(path);
    if(!segments.length){resultEl.innerHTML='<div class="route-empty">同じ駅が選ばれています。</div>';return;}
    var transfers=Math.max(0,segments.length-1),stops=segments.reduce(function(sum,segment){return sum+segment.stops;},0);
    var html='<div class="route-result-card"><div class="route-summary"><strong>'+esc(fromGroup.label)+' → '+esc(toGroup.label)+'</strong><span>'+stops+'駅・乗換 '+transfers+'回</span></div>';
    segments.forEach(function(segment,index){
      if(index>0)html+='<div class="route-transfer">'+esc(model.displayStation(segment.from))+'で乗換</div>';
      html+='<div class="route-leg" style="--route-line-color:'+safeColor(segment.color)+'"><div class="route-line-rail" aria-hidden="true"></div><div class="route-leg-copy"><small>'+esc(model.displayStation(segment.from))+' → '+esc(model.displayStation(segment.to))+'</small><strong>'+esc(segment.label)+'</strong><p>'+segment.stops+'駅</p></div></div>';
    });
    html+='</div>';resultEl.innerHTML=html;
  }
  function searchRoute(){
    var fromResolved=resolve(fromInput),toResolved=resolve(toInput);
    if(!fromResolved.group||!toResolved.group){showInputError(fromResolved,toResolved);return;}
    if(fromResolved.group.key===toResolved.group.key){resultEl.innerHTML='<div class="route-empty">出発駅と到着駅が同じです。</div>';return;}
    submitBtn.disabled=true;submitBtn.textContent="検索中…";
    window.setTimeout(function(){
      var path=model.shortestPath(fromResolved.group,toResolved.group);
      if(path){renderPath(fromResolved.group,toResolved.group,path);updateUrl();}
      else resultEl.innerHTML='<div class="route-empty">この組み合わせの経路を見つけられませんでした。現在対応している路線の範囲内で試してください。</div>';
      submitBtn.disabled=false;submitBtn.textContent="経路を検索";
    },0);
  }
  function applyQuery(){
    var params=new URLSearchParams(location.search),from=params.get("from"),to=params.get("to");
    if(from)fromInput.value=from;if(to)toInput.value=to;if(from&&to)searchRoute();
  }

  form.addEventListener("submit",function(event){event.preventDefault();searchRoute();});
  swapBtn.addEventListener("click",function(){var value=fromInput.value;fromInput.value=toInput.value;toInput.value=value;if(fromInput.value&&toInput.value)searchRoute();});
  load();
})();
