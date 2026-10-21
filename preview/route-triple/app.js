(function(){
"use strict";
var core=window.RoutePlannerCore,planner=window.RouteTriPlanner;
var from=document.getElementById("from"),to=document.getElementById("to"),form=document.getElementById("search"),submit=document.getElementById("submit"),status=document.getElementById("status"),root=document.getElementById("results");
var model=null,rules=null,failed=[];
function safe(s){return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
function getJSON(url){return fetch(url).then(function(response){if(!response.ok)throw Error(response.status+" "+url);return response.json();});}
function display(items){if(!items.length){root.innerHTML='<div class="empty">経路を見つけられませんでした。取得できなかった事業者の路線が必要な可能性もあります。</div>';return;}
root.innerHTML='<div class="cards">'+items.map(function(item){
var legs=item.legs.map(function(leg){return'<li><b>'+safe(leg.label)+'</b><small>'+safe(model.displayStation(leg.from))+' → '+safe(model.displayStation(leg.to))+' / '+leg.stops+'駅'+(leg.transfer?' / '+safe(leg.transfer.station)+'で路線切替（徒歩目安 '+leg.transfer.minutes+'分）':'')+'</small></li>';}).join("");
return'<article class="card"><div class="card-head"><span class="tag '+(item.category.indexOf("早い")>=0?"fast":item.category.indexOf("楽")>=0?"easy":"")+'">'+safe(item.category)+'</span><span class="sub">経路比較候補</span></div><strong class="metric">'+item.estimatedMinutes+'分前後</strong><div class="sub">概算 / 路線切替 '+item.lineChanges+'回・移動目安 '+Math.round(item.walkMinutes)+'分</div><ol class="route-list">'+legs+'</ol><div class="fare-warning">運賃：未判定。直通・接続・急行は未反映</div></article>';
}).join("")+'</div>';
}
function findRoute(){if(!model)return;
var a=model.resolveInput(from.value),b=model.resolveInput(to.value);
if(!a.group||!b.group){root.innerHTML='<div class="empty">駅名を候補から選んでね。同名駅がある場合は区別して入力してください。</div>';return;}
if(a.group.key===b.group.key){root.innerHTML='<div class="empty">異なる駅を選んでね。</div>';return;}
submit.disabled=true;submit.textContent="候補を計算中...";
try{var routes=planner.compare(model,a.group,b.group,rules);display(routes);var q=new URL(location.href);q.searchParams.set("from",from.value);q.searchParams.set("to",to.value);history.replaceState(null,"",q.pathname+q.search);}
catch(error){console.error(error);root.innerHTML='<div class="empty">経路計算に失敗しました。開発ログの確認が必要です。</div>';}
finally{submit.disabled=false;submit.textContent="3観点で比較する";}
}
document.getElementById("swap").addEventListener("click",function(){var x=from.value;from.value=to.value;to.value=x;});
form.addEventListener("submit",function(e){e.preventDefault();findRoute();});
async function boot(){
if(!core||!planner){status.textContent="検索モジュールが読み込めませんでした。";return;}
try{
var manifest=await getJSON("../../data/transit/manifest.json");
var operators=Object.keys(manifest.operators).filter(function(k){return manifest.operators[k].status==="ok";});
var jobs=operators.map(function(operator){return getJSON("../../data/transit/"+operator+"/entities.json").catch(function(e){failed.push(operator);console.warn("Missing topology:",operator,e);return null;});});
var all=await Promise.all([Promise.all(jobs),getJSON("../../data/transit/transfer-rules.json").catch(function(){return null;}),getJSON("../../data/transit/transfer-blocks.json").catch(function(){return null;})]);
rules=all[1];var blocks=all[2];
model=core.createModel(all[0].filter(Boolean),{blockedStationPairs:blocks&&blocks.blockedStationPairs||[]});
if(!model.stations.length)throw Error("駅データがありません");
document.getElementById("station-list").innerHTML=model.stations.map(x=>'<option value="'+safe(x.label)+'"></option>').join("");
status.textContent="駅候補 "+model.stations.length.toLocaleString("ja-JP")+"件 / 読込事業者 "+(operators.length-failed.length)+"/"+operators.length+"。運賃未対応・時刻表非依存の試作です。"+(failed.length?" 未取得: "+failed.join(", "):"");
submit.disabled=false;submit.textContent="3観点で比較する";
var args=new URLSearchParams(location.search);from.value=args.get("from")||"八潮";to.value=args.get("to")||"日吉";findRoute();
}catch(e){console.error(e);status.textContent="読み込みに失敗しました。通信環境を確認して再読み込みしてください。";root.innerHTML='<div class="empty">データ読み込みエラー</div>';}
}
boot();
})();