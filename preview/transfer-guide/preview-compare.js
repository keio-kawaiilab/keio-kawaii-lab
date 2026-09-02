(function(){
  "use strict";
  var results=document.getElementById("results-section");
  if(!results)return;

  function text(el){return el?String(el.textContent||"").trim():"";}
  function parseNumber(value,re){var m=String(value||"").match(re);return m?Number(m[1]):null;}
  function parseClock(value){var m=String(value||"").match(/(?:翌\s*)?(\d{1,2}):(\d{2})/g)||[];return m.map(function(v){var next=v.indexOf("翌")>=0?1440:0;var p=v.replace(/翌\s*/,"").split(":");return next+Number(p[0])*60+Number(p[1]);});}
  function safeColor(value){var m=String(value||"").match(/#[0-9a-f]{6}/i);return m?m[0]:"#35598f";}
  function esc(value){return String(value==null?"":value).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}

  function dataFromCard(card,index){
    var timeText=text(card.querySelector(".result-time strong"));
    var clocks=parseClock(timeText);
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
    return{index:index,departure:clocks[0]||0,arrival:clocks[1]||0,duration:duration,transfers:transfers==null?99:transfers,fare:fare,lines:lines,card:card};
  }

  function summaryButton(item,fastestArrival,leastTransfers,cheapestFare){
    var flags=[];
    if(item.arrival===fastestArrival)flags.push('<span class="route-flag fast">早</span>');
    if(item.transfers===leastTransfers)flags.push('<span class="route-flag easy">楽</span>');
    if(cheapestFare!=null&&item.fare===cheapestFare)flags.push('<span class="route-flag cheap">安</span>');
    var lineHtml=item.lines.slice(0,3).map(function(line,i){return(i?'<span class="route-choice-arrow">›</span>':'')+'<span class="route-choice-line"><i style="background:'+line.color+'"></i><span>'+esc(line.label)+'</span></span>';}).join("");
    var departText=item.departure?String(Math.floor(item.departure%1440/60)).padStart(2,"0")+":"+String(item.departure%60).padStart(2,"0"):"—";
    var arriveText=item.arrival?String(Math.floor(item.arrival%1440/60)).padStart(2,"0")+":"+String(item.arrival%60).padStart(2,"0"):"—";
    return'<button type="button" class="route-choice" data-route-choice="'+item.index+'" aria-pressed="false"><span class="route-choice-top"><span class="route-choice-rank">経路 '+(item.index+1)+'</span><span class="route-choice-flags">'+flags.join("")+'</span></span><span class="route-choice-time">'+departText+'<span>→</span>'+arriveText+'</span><span class="route-choice-stats"><span class="route-choice-stat"><strong>'+item.duration+'分</strong><small>所要時間</small></span><span class="route-choice-stat"><strong>'+item.transfers+'回</strong><small>乗換</small></span><span class="route-choice-stat"><strong>'+(item.fare!=null?item.fare+'円':'—')+'</strong><small>運賃</small></span></span><span class="route-choice-lines">'+lineHtml+'</span><span class="route-choice-open"><span>タップして詳細</span><b>›</b></span></button>';
  }

  function enhance(){
    var list=results.querySelector(".result-list");
    if(!list||list.dataset.compareEnhanced==="1")return;
    var cards=Array.from(list.querySelectorAll(":scope > .result-card"));
    if(!cards.length)return;
    list.dataset.compareEnhanced="1";
    list.classList.add("route-original-results");
    var items=cards.map(dataFromCard);
    var fastestArrival=Math.min.apply(null,items.map(function(i){return i.arrival||99999;}));
    var leastTransfers=Math.min.apply(null,items.map(function(i){return i.transfers;}));
    var fares=items.map(function(i){return i.fare;}).filter(function(v){return Number.isFinite(v);});
    var cheapestFare=fares.length?Math.min.apply(null,fares):null;
    var shell=document.createElement("div");
    shell.className="route-comparison";
    shell.innerHTML='<div class="route-comparison-head"><div class="route-comparison-legend"><span class="route-flag fast">早</span><span class="route-flag easy">楽</span>'+(cheapestFare!=null?'<span class="route-flag cheap">安</span>':'<span class="route-flag muted">安</span>')+'</div><div class="route-comparison-note">早＝最速到着 / 楽＝乗換最少'+(cheapestFare==null?' / 安＝運賃DB準備中':' / 安＝最安')+'</div></div><div class="route-choice-strip">'+items.map(function(item){return summaryButton(item,fastestArrival,leastTransfers,cheapestFare);}).join("")+'</div><div class="route-detail-shell"><div class="route-detail-placeholder">見たい経路をタップすると、ここに詳しい乗換内容が出ます。</div></div>';
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
    var label='<div class="route-detail-title"><strong>経路 '+(index+1)+' の詳細</strong><span>もう一度別の経路をタップすると切替</span></div>';
    detail.innerHTML=label;
    detail.appendChild(clone);
    if(item.fare==null){var note=document.createElement("div");note.className="fare-pending";note.textContent="運賃比較は現在準備中です。運賃DBを追加後、この画面で「安」も自動判定します。";detail.appendChild(note);}
    detail.scrollIntoView({behavior:"smooth",block:"nearest"});
  });

  var observer=new MutationObserver(function(){enhance();});
  observer.observe(results,{childList:true,subtree:true});
  enhance();
})();
