(function(){
  "use strict";

  var cards=document.getElementById("cards");
  if(!cards)return;

  var DATA_URL="./data/event-weather.json";
  var payload=null;
  var queued=false;

  if(!document.querySelector('link[data-schedule-weather]')){
    var style=document.createElement("link");
    style.rel="stylesheet";
    style.href="./schedule-weather.css?v=202608260500";
    style.setAttribute("data-schedule-weather","");
    document.head.appendChild(style);
  }

  function esc(value){
    return String(value==null?"":value)
      .replace(/&/g,"&amp;")
      .replace(/</g,"&lt;")
      .replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;");
  }

  function pad(value){return String(value).padStart(2,"0");}

  function normalizeVenue(value){
    return String(value||"")
      .normalize("NFKC")
      .replace(/^(北海道|東京都|京都府|大阪府|.{2,3}県)[\s　]*/,"")
      .replace(/[\s　・･]/g,"")
      .replace(/(?:メイン)?大ホール|劇場棟/g,"")
      .replace(/[()（）]/g,"")
      .toLowerCase();
  }

  function parseCardDate(card){
    var node=card.querySelector(".performance-date");
    var match=String(node&&node.textContent||"").match(/(20\d{2})\/(\d{1,2})\/(\d{1,2})/);
    return match?[match[1],pad(match[2]),pad(match[3])].join("-"):"";
  }

  function metaItem(card,label){
    var items=[].slice.call(card.querySelectorAll(".meta > div"));
    return items.find(function(item){
      var b=item.querySelector("b");
      return b&&b.textContent.trim()===label;
    })||null;
  }

  function parseCardVenue(card){
    var item=metaItem(card,"会場");
    if(!item)return"";
    var link=item.querySelector("a.venue-link");
    if(link){
      try{
        var url=new URL(link.getAttribute("href")||"",location.href);
        var name=url.searchParams.get("name");
        if(name)return name;
      }catch(_error){}
    }
    var clone=item.cloneNode(true);
    var b=clone.querySelector("b");
    if(b)b.remove();
    return clone.textContent.trim();
  }

  function iconFor(label){
    var text=String(label||"");
    if(/雷/.test(text))return"⛈️";
    if(/雪/.test(text)&&/雨/.test(text))return"🌨️";
    if(/雪/.test(text))return"❄️";
    if(/雨/.test(text)&&/晴/.test(text))return"🌦️";
    if(/雨/.test(text))return"🌧️";
    if(/晴/.test(text)&&/くも|曇/.test(text))return"🌤️";
    if(/晴/.test(text))return"☀️";
    if(/くも|曇/.test(text))return"☁️";
    return"🌤️";
  }

  function cleanTemp(value){
    if(value==null||value==="")return"";
    var number=Number(value);
    if(!Number.isFinite(number))return String(value);
    return Number.isInteger(number)?String(number):number.toFixed(1).replace(/\.0$/,"");
  }

  function weatherHtml(entry,source){
    var mesh=entry.precision==="mesh5km";
    var precisionText=mesh
      ?"会場周辺 約5km"+(entry.meshTime?"｜"+entry.meshTime+"ごろ":"")
      :(entry.areaName?entry.areaName+"｜":"")+"気象庁予報";

    var temps="";
    if(entry.max!=null)temps+='<span class="schedule-weather-high">最高 '+esc(cleanTemp(entry.max))+'℃</span>';
    if(entry.min!=null)temps+='<span class="schedule-weather-low">最低 '+esc(cleanTemp(entry.min))+'℃</span>';

    var sub=[];
    if(mesh&&entry.meshTempBand){
      sub.push('<span class="schedule-weather-mesh-temp">🌡️ '+esc(entry.meshTime||"開演前後")+' '+esc(entry.meshTempBand)+'</span>');
    }
    if(entry.pop!=null&&entry.pop!==""){
      var popArea=entry.areaName?entry.areaName+"・":"";
      sub.push('<span class="schedule-weather-pop">☔ '+esc(popArea+(entry.popLabel||"降水確率"))+' '+esc(entry.pop)+'%</span>');
    }

    return '<section class="schedule-weather" aria-label="開催日の天気">'+
      '<div class="schedule-weather-head"><div><small>開催日の天気</small><strong>'+esc(precisionText)+'</strong></div></div>'+
      '<div class="schedule-weather-main"><span class="schedule-weather-icon" aria-hidden="true">'+iconFor(entry.label)+'</span><strong class="schedule-weather-condition">'+esc(entry.label||"天気予報")+'</strong><div class="schedule-weather-temps">'+temps+'</div></div>'+
      (sub.length?'<div class="schedule-weather-sub">'+sub.join('')+'</div>':"")+
      '<a class="schedule-weather-source" href="'+esc(source&&source.url||"https://www.jma.go.jp/bosai/forecast/")+'" target="_blank" rel="noopener">出典：'+esc(source&&source.name||"気象庁")+' ↗</a>'+
      '</section>';
  }

  function findEntry(card){
    if(!payload||!Array.isArray(payload.entries))return null;
    var day=parseCardDate(card);
    var venueKey=normalizeVenue(parseCardVenue(card));
    if(!day||!venueKey)return null;
    return payload.entries.find(function(entry){
      if(!entry||entry.date!==day)return false;
      var key=String(entry.venueKey||normalizeVenue(entry.venue||""));
      return key===venueKey||key.indexOf(venueKey)>=0||venueKey.indexOf(key)>=0;
    })||null;
  }

  function mountCard(card){
    var old=card.querySelector(".schedule-weather");
    var entry=findEntry(card);
    if(!entry){
      if(old)old.remove();
      return;
    }
    var meta=card.querySelector(".meta");
    if(!meta)return;
    var html=weatherHtml(entry,payload.source||{});
    if(old){
      var holder=document.createElement("div");
      holder.innerHTML=html;
      var fresh=holder.firstElementChild;
      if(fresh&&old.outerHTML!==fresh.outerHTML)old.replaceWith(fresh);
      return;
    }
    meta.insertAdjacentHTML("afterend",html);
  }

  function mountAll(){
    queued=false;
    [].slice.call(cards.querySelectorAll(".card")).forEach(mountCard);
  }

  function queue(){
    if(queued)return;
    queued=true;
    window.setTimeout(mountAll,20);
  }

  fetch(DATA_URL+"?weather="+Date.now(),{cache:"no-store"})
    .then(function(response){if(!response.ok)throw new Error("event-weather");return response.json();})
    .then(function(data){
      payload=data||{};
      mountAll();
      new MutationObserver(queue).observe(cards,{childList:true,subtree:true});
    })
    .catch(function(){
      // 天気JSONを取得できない時は、誤った代替予報を出さず既存ページだけ表示する。
    });

  window.KawaiiScheduleWeather={
    normalizeVenue:normalizeVenue,
    parseCardDate:parseCardDate,
    parseCardVenue:parseCardVenue
  };
})();
