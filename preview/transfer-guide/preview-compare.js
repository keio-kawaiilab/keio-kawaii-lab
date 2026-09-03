(function(){
  "use strict";
  var results=document.getElementById("results-section");
  if(!results)return;

  function text(el){return el?String(el.textContent||"").trim():"";}
  function parseNumber(value,re){var m=String(value||"").match(re);return m?Number(m[1]):null;}
  function parseClock(value){var m=String(value||"").match(/(?:翌\s*)?(\d{1,2}):(\d{2})/g)||[];return m.map(function(v){var next=v.indexOf("翌")>=0?1440:0;var p=v.replace(/翌\s*/,"").split(":");return next+Number(p[0])*60+Number(p[1]);});}
  function clock(minutes){if(!Number.isFinite(minutes))return"—";var day=minutes>=1440?"翌 ":"";var value=((minutes%1440)+1440)%1440;return day+String(Math.floor(value/60)).padStart(2,"0")+":"+String(value%60).padStart(2,"0");}
  function safeColor(value){var m=String(value||"").match(/#[0-9a-f]{6}/i);return m?m[0]:"#35598f";}
  function esc(value){return String(value==null?"":value).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
  function clamp(v,min,max){return Math.max(min,Math.min(max,v));}
  function queryMinute(){var input=document.getElementById("route-datetime");var value=input&&input.value||"";var m=value.match(/T(\d{2}):(\d{2})/);return m?Number(m[1])*60+Number(m[2]):null;}

  function dataFromCard(card,index){
    var clocks=parseClock(text(card.querySelector(".result-time strong")));
    var meta=text(card.querySelector(".result-meta"));
    var duration=parseNumber(meta,/(\d+)分/)||0;
    var transfers=parseNumber(meta,/乗換\s*(\d+)回/);
    var fare=parseNumber(card.textContent,/(\d{2,5})円/);
    var segments=[];
    card.querySelectorAll(".route-leg").forEach(function(leg){
      var times=parseClock(text(leg.querySelector(".leg-clock")));
      var line=leg.querySelector(".leg-line");
      var label=text(line&&line.querySelector("span:last-child"))||"鉄道路線";
      var dot=line&&line.querySelector(".line-dot");
      if(times.length>=2&&Number.isFinite(times[0])&&Number.isFinite(times[1]))segments.push({departure:times[0],arrival:times[1],label:label,color:safeColor(dot&&dot.getAttribute("style"))});
    });
    var lines=[];segments.forEach(function(s){if(!lines.some(function(x){return x.label===s.label;}))lines.push({label:s.label,color:s.color});});
    var via=[];card.querySelectorAll(".leg-main h3").forEach(function(h){var value=text(h);if(value)via.push(value);});
    var signature=lines.map(function(line){return line.label;}).join(">")+"|"+(transfers==null?99:transfers)+"|"+via.join(">");
    return{originalIndex:index,departure:clocks[0],arrival:clocks[1],duration:duration,transfers:transfers==null?99:transfers,fare:fare,lines:lines,segments:segments,via:via,signature:signature,variant:0,card:card};
  }

  function prioritize(items){
    var groups=[],bySignature=new Map();
    items.forEach(function(item){var group=bySignature.get(item.signature);if(!group){group=[];bySignature.set(item.signature,group);groups.push(group);}item.variant=group.length;if(group.length<3)group.push(item);});
    var ordered=[];for(var round=0;round<3&&ordered.length<12;round++){groups.forEach(function(group){if(group[round]&&ordered.length<12)ordered.push(group[round]);});}return ordered;
  }

  function timelineHtml(item,start,end){
    var span=Math.max(1,end-start),parts=[];
    for(var q=0;q<=4;q++){var pct=q*25;parts.push('<span class="time-grid-line" style="top:'+pct+'%"></span>');}
    var segments=item.segments.length?item.segments:[{departure:item.departure,arrival:item.arrival,label:(item.lines[0]&&item.lines[0].label)||"鉄道路線",color:(item.lines[0]&&item.lines[0].color)||"#35598f"}];
    segments.forEach(function(seg,i){
      var top=clamp((seg.departure-start)/span*100,0,100),bottom=clamp((seg.arrival-start)/span*100,0,100),height=Math.max(0,bottom-top);
      parts.push('<span class="time-route-segment" style="top:'+top+'%;height:'+height+'%;--segment-color:'+seg.color+'"><b>'+esc(seg.label)+'</b></span>');
      if(i<segments.length-1){var next=segments[i+1],waitTop=clamp((seg.arrival-start)/span*100,0,100),waitBottom=clamp((next.departure-start)/span*100,0,100);if(waitBottom>waitTop)parts.push('<span class="time-transfer-wait" style="top:'+waitTop+'%;height:'+(waitBottom-waitTop)+'%"><i>乗換</i></span>');}
    });
    var depTop=clamp((item.departure-start)/span*100,0,100),arrTop=clamp((item.arrival-start)/span*100,0,100);
    parts.push('<span class="time-point departure" style="top:'+depTop+'%"><strong>'+clock(item.departure)+'</strong><small>発</small></span>');
    parts.push('<span class="time-point arrival" style="top:'+arrTop+'%"><strong>'+clock(item.arrival)+'</strong><small>着</small></span>');
    return '<span class="route-choice-timeaxis">'+parts.join("")+'</span>';
  }

  function summaryButton(item,visualIndex,fastestArrival,leastTransfers,cheapestFare,start,end){
    var flags=[];
    if(item.arrival===fastestArrival)flags.push('<span class="route-flag fast">早</span>');
    if(item.transfers===leastTransfers)flags.push('<span class="route-flag easy">楽</span>');
    if(cheapestFare!=null&&item.fare===cheapestFare)flags.push('<span class="route-flag cheap">安</span>');
    var variant=item.variant>0?'<span class="route-choice-variant">同ルート '+(item.variant+1)+'本目</span>':'<span class="route-choice-variant primary">別経路優先</span>';
    return '<button type="button" class="route-choice" data-route-choice="'+visualIndex+'" aria-pressed="false">'
      +'<span class="route-choice-top"><span class="route-choice-rank">経路 '+(visualIndex+1)+'</span>'+variant+'</span>'
      +'<span class="route-choice-duration"><strong>'+item.duration+'分</strong><small>所要時間</small></span>'
      +timelineHtml(item,start,end)
      +'<span class="route-choice-bottom"><span class="route-choice-transfer">乗換 <strong>'+item.transfers+'回</strong></span><span class="route-choice-fare">'+(item.fare!=null?'<strong>'+item.fare+'円</strong>':'<strong>—</strong><small>運賃未対応</small>')+'</span></span>'
      +'<span class="route-choice-flags">'+flags.join("")+'</span>'
      +'<span class="route-choice-open">タップで詳細 <b>›</b></span>'
      +'</button>';
  }

  function enhance(){
    var list=results.querySelector(".result-list");if(!list||list.dataset.compareEnhanced==="1")return;
    var cards=Array.from(list.querySelectorAll(":scope > .result-card"));if(!cards.length)return;
    list.dataset.compareEnhanced="1";list.classList.add("route-original-results");
    var items=prioritize(cards.map(dataFromCard));
    var distinctCount=new Set(items.map(function(i){return i.signature;})).size;
    var fastestArrival=Math.min.apply(null,items.map(function(i){return Number.isFinite(i.arrival)?i.arrival:99999;}));
    var leastTransfers=Math.min.apply(null,items.map(function(i){return i.transfers;}));
    var fares=items.map(function(i){return i.fare;}).filter(Number.isFinite),cheapestFare=fares.length?Math.min.apply(null,fares):null;
    var minDeparture=Math.min.apply(null,items.map(function(i){return i.departure;})),maxArrival=Math.max.apply(null,items.map(function(i){return i.arrival;}));
    var requested=queryMinute();if(Number.isFinite(requested)){while(requested<minDeparture-720)requested+=1440;while(requested>minDeparture+720)requested-=1440;}
    var scaleStart=Number.isFinite(requested)?Math.min(requested,minDeparture):minDeparture;
    var scaleEnd=Math.max(scaleStart+30,maxArrival+2);
    var shell=document.createElement("div");shell.className="route-comparison";
    shell.innerHTML='<div class="route-comparison-head"><div><strong>'+items.length+'候補を比較</strong><span>'+distinctCount+'種類の経路 / 棒は全候補で共通の時間軸です</span></div><div class="route-comparison-legend"><span class="route-flag fast">早</span><small>最速到着</small><span class="route-flag easy">楽</span><small>乗換最少</small>'+(cheapestFare!=null?'<span class="route-flag cheap">安</span><small>最安</small>':'<span class="route-flag muted">安</span><small>運賃DB準備中</small>')+'</div></div><div class="route-time-scale"><b>'+clock(scaleStart)+'</b><span>共通時間軸</span><b>'+clock(scaleEnd)+'</b></div><div class="route-choice-strip">'+items.map(function(item,index){return summaryButton(item,index,fastestArrival,leastTransfers,cheapestFare,scaleStart,scaleEnd);}).join("")+'</div><div class="route-detail-shell"><div class="route-detail-placeholder">見たい経路をタップすると、乗る列車・乗換駅・各区間の発着時刻を詳しく表示します。</div></div>';
    list.parentNode.insertBefore(shell,list);shell._routeItems=items;
  }

  results.addEventListener("click",function(event){
    var button=event.target.closest("[data-route-choice]");if(!button)return;
    var shell=button.closest(".route-comparison"),index=Number(button.getAttribute("data-route-choice")),item=shell&&shell._routeItems&&shell._routeItems[index];if(!item)return;
    shell.querySelectorAll(".route-choice").forEach(function(node){var active=node===button;node.classList.toggle("is-selected",active);node.setAttribute("aria-pressed",active?"true":"false");});
    var detail=shell.querySelector(".route-detail-shell"),clone=item.card.cloneNode(true);clone.classList.remove("is-best");clone.querySelectorAll(".best-pill").forEach(function(node){node.remove();});
    detail.innerHTML='<div class="route-detail-title"><strong>経路 '+(index+1)+' の詳細</strong><span>'+clock(item.departure)+'発 → '+clock(item.arrival)+'着 / '+item.duration+'分 / 乗換'+item.transfers+'回</span></div>';detail.appendChild(clone);
    if(item.fare==null){var note=document.createElement("div");note.className="fare-pending";note.textContent="運賃比較は準備中です。運賃データを追加した経路から「安」を自動判定します。";detail.appendChild(note);}detail.scrollIntoView({behavior:"smooth",block:"nearest"});
  });

  new MutationObserver(enhance).observe(results,{childList:true,subtree:true});enhance();
})();
