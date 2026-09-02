(function(){
  "use strict";
  var results=document.getElementById("results-section");
  if(!results)return;

  function text(el){return el?String(el.textContent||"").trim():"";}
  function parseNumber(value,re){var m=String(value||"").match(re);return m?Number(m[1]):null;}
  function parseClock(value){var m=String(value||"").match(/(?:翌\s*)?(\d{1,2}):(\d{2})/g)||[];return m.map(function(v){var next=v.indexOf("翌")>=0?1440:0;var p=v.replace(/翌\s*/,"").split(":");return next+Number(p[0])*60+Number(p[1]);});}
  function clock(minutes){if(!Number.isFinite(minutes))return"—";var day=minutes>=1440?"翌 ":"";var value=minutes%1440;return day+String(Math.floor(value/60)).padStart(2,"0")+":"+String(value%60).padStart(2,"0");}
  function safeColor(value){var m=String(value||"").match(/#[0-9a-f]{6}/i);return m?m[0]:"#35598f";}
  function esc(value){return String(value==null?"":value).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}

  function dataFromCard(card,index){
    var clocks=parseClock(text(card.querySelector(".result-time strong")));
    var meta=text(card.querySelector(".result-meta"));
    var duration=parseNumber(meta,/(\d+)分/)||0;
    var transfers=parseNumber(meta,/乗換\s*(\d+)回/);
    var fare=parseNumber(card.textContent,/(\d{2,5})円/);
    var lines=[];
    card.querySelectorAll(".leg-line").forEach(function(line){
      var label=text(line.querySelector("span:last-child"));
      var dot=line.querySelector(".line-dot");
      var color=safeColor(dot&&dot.getAttribute("style"));
      if(label&&!lines.some(function(item){return item.label===label;}))lines.push({label:label,color:color});
    });
    return{index:index,departure:clocks[0],arrival:clocks[1],duration:duration,transfers:transfers==null?99:transfers,fare:fare,lines:lines,card:card};
  }

  function railDiagram(item){
    var lines=item.lines.length?item.lines:[{label:"鉄道路線",color:"#35598f"}];
    var html='<span class="compare-node start"></span>';
    lines.slice(0,4).forEach(function(line,i){
      html+='<span class="compare-rail" style="--compare-line:'+line.color+'"><i></i><b>'+esc(line.label)+'</b></span>';
      if(i<Math.min(lines.length,4)-1)html+='<span class="compare-transfer-dot">乗換</span>';
    });
    html+='<span class="compare-node end"></span>';
    return html;
  }

  function summaryButton(item,fastestArrival,leastTransfers,cheapestFare){
    var flags=[];
    if(item.arrival===fastestArrival)flags.push('<span class="route-flag fast">早</span>');
    if(item.transfers===leastTransfers)flags.push('<span class="route-flag easy">楽</span>');
    if(cheapestFare!=null&&item.fare===cheapestFare)flags.push('<span class="route-flag cheap">安</span>');
    return '<button type="button" class="route-choice" data-route-choice="'+item.index+'" aria-pressed="false">'
      +'<span class="route-choice-rank">経路 '+(item.index+1)+'</span>'
      +'<span class="route-choice-duration"><strong>'+item.duration+'分</strong><small>所要時間</small></span>'
      +'<span class="route-choice-clock"><small>出発</small><strong>'+clock(item.departure)+'</strong></span>'
      +'<span class="route-choice-railmap">'+railDiagram(item)+'</span>'
      +'<span class="route-choice-clock arrive"><small>到着</small><strong>'+clock(item.arrival)+'</strong></span>'
      +'<span class="route-choice-bottom"><span class="route-choice-transfer">乗換 <strong>'+item.transfers+'回</strong></span><span class="route-choice-fare">'+(item.fare!=null?'<strong>'+item.fare+'円</strong>':'<strong>—</strong><small>運賃未対応</small>')+'</span></span>'
      +'<span class="route-choice-flags">'+flags.join("")+'</span>'
      +'<span class="route-choice-open">詳細を見る <b>›</b></span>'
      +'</button>';
  }

  function enhance(){
    var list=results.querySelector(".result-list");
    if(!list||list.dataset.compareEnhanced==="1")return;
    var cards=Array.from(list.querySelectorAll(":scope > .result-card"));
    if(!cards.length)return;
    list.dataset.compareEnhanced="1";
    list.classList.add("route-original-results");
    var items=cards.map(dataFromCard);
    var fastestArrival=Math.min.apply(null,items.map(function(i){return Number.isFinite(i.arrival)?i.arrival:99999;}));
    var leastTransfers=Math.min.apply(null,items.map(function(i){return i.transfers;}));
    var fares=items.map(function(i){return i.fare;}).filter(function(v){return Number.isFinite(v);});
    var cheapestFare=fares.length?Math.min.apply(null,fares):null;
    var shell=document.createElement("div");
    shell.className="route-comparison";
    shell.innerHTML='<div class="route-comparison-head"><div><strong>'+items.length+'経路を比較</strong><span>左右にスワイプして比較できます</span></div><div class="route-comparison-legend"><span class="route-flag fast">早</span><small>最速到着</small><span class="route-flag easy">楽</span><small>乗換最少</small>'+(cheapestFare!=null?'<span class="route-flag cheap">安</span><small>最安</small>':'<span class="route-flag muted">安</span><small>運賃DB準備中</small>')+'</div></div><div class="route-choice-strip">'+items.map(function(item){return summaryButton(item,fastestArrival,leastTransfers,cheapestFare);}).join("")+'</div><div class="route-detail-shell"><div class="route-detail-placeholder">経路をタップすると、乗る列車・乗換駅・各区間の時刻を詳しく表示します。</div></div>';
    list.parentNode.insertBefore(shell,list);
    shell._routeItems=items;
  }

  results.addEventListener("click",function(event){
    var button=event.target.closest("[data-route-choice]");
    if(!button)return;
    var shell=button.closest(".route-comparison");
    var index=Number(button.getAttribute("data-route-choice"));
    var item=shell&&shell._routeItems&&shell._routeItems[index];
    if(!item)return;
    shell.querySelectorAll(".route-choice").forEach(function(node){var active=node===button;node.classList.toggle("is-selected",active);node.setAttribute("aria-pressed",active?"true":"false");});
    var detail=shell.querySelector(".route-detail-shell");
    var clone=item.card.cloneNode(true);
    clone.classList.remove("is-best");
    clone.querySelectorAll(".best-pill").forEach(function(node){node.remove();});
    detail.innerHTML='<div class="route-detail-title"><strong>経路 '+(index+1)+' の詳細</strong><span>'+clock(item.departure)+'発 → '+clock(item.arrival)+'着</span></div>';
    detail.appendChild(clone);
    if(item.fare==null){var note=document.createElement("div");note.className="fare-pending";note.textContent="運賃比較は準備中です。運賃データを追加した経路から「安」を自動判定します。";detail.appendChild(note);}
    detail.scrollIntoView({behavior:"smooth",block:"nearest"});
  });

  new MutationObserver(enhance).observe(results,{childList:true,subtree:true});
  enhance();
})();
