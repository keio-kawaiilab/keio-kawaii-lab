(function(){
  "use strict";

  var head=document.head;
  if(head){
    function ensureLink(rel,href,attrs){
      if(head.querySelector('link[rel="'+rel+'"]'))return;
      var link=document.createElement("link");
      link.rel=rel;
      link.href=href;
      Object.keys(attrs||{}).forEach(function(key){link.setAttribute(key,attrs[key]);});
      head.appendChild(link);
    }
    function ensureMeta(name,content){
      if(head.querySelector('meta[name="'+name+'"]'))return;
      var meta=document.createElement("meta");
      meta.name=name;
      meta.content=content;
      head.appendChild(meta);
    }
    ensureLink("icon","./favicon-32.png",{type:"image/png",sizes:"32x32"});
    ensureLink("apple-touch-icon","./site-icon.svg");
    ensureLink("manifest","./site.webmanifest");
    ensureMeta("theme-color","#26305c");
    ensureMeta("application-name","慶應カワラボ同好会");
    ensureMeta("apple-mobile-web-app-title","慶應カワラボ");
    ensureMeta("apple-mobile-web-app-capable","yes");
    ensureMeta("mobile-web-app-capable","yes");
  }

  function localDate(date){
    return[
      date.getFullYear(),
      String(date.getMonth()+1).padStart(2,"0"),
      String(date.getDate()).padStart(2,"0")
    ].join("-");
  }

  function esc(value){
    return String(value==null?"":value)
      .replace(/&/g,"&amp;")
      .replace(/</g,"&lt;")
      .replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;");
  }

  function normalizeVenue(value){
    return String(value||"")
      .replace(/^(北海道|東京都|京都府|大阪府|.{2,3}県)[\s　]*/,"")
      .replace(/[\s　・･]/g,"")
      .replace(/(?:メイン)?大ホール|劇場棟/g,"")
      .toLowerCase();
  }

  function normalizeLine(value){
    return String(value||"")
      .normalize("NFKC")
      .replace(/[\[［(（].*?[\]］)）]/g,"")
      .replace(/JR(?:北海道|東日本|東海|西日本|四国|九州)?/g,"")
      .replace(/京浜急行電鉄/g,"京急")
      .replace(/相模鉄道/g,"相鉄")
      .replace(/小田急電鉄/g,"小田急")
      .replace(/東急電鉄/g,"東急")
      .replace(/東武鉄道/g,"東武")
      .replace(/西武鉄道/g,"西武")
      .replace(/京王電鉄/g,"京王")
      .replace(/京阪電気鉄道/g,"京阪")
      .replace(/南海電気鉄道/g,"南海")
      .replace(/阪神電気鉄道/g,"阪神")
      .replace(/近畿日本鉄道/g,"近鉄")
      .replace(/名古屋鉄道/g,"名鉄")
      .replace(/高松琴平電気鉄道/g,"高松琴平電鉄")
      .replace(/東京臨海高速鉄道|横浜高速鉄道|東京臨海新交通|広島高速交通/g,"")
      .replace(/都営地下鉄/g,"都営")
      .replace(/地下鉄|市内電車|各線|ほか/g,"")
      .replace(/本線/g,"線")
      .replace(/[\s　・･／/〜～\-]/g,"")
      .toLowerCase();
  }

  function lineKeys(value){
    var key=normalizeLine(value);
    var keys=key?[key]:[];
    if(key.indexOf("京浜東北根岸線")>=0)keys.push("京浜東北線","根岸線");
    if(key.indexOf("埼京川越線")>=0)keys.push("埼京線","川越線");
    if(key.indexOf("中央総武線")>=0)keys.push("中央線","総武線");
    if(key.indexOf("ポートアイランド線")>=0)keys.push("ポートライナー");
    if(key.indexOf("沖縄都市モノレール線")>=0)keys.push("ゆいレール");
    return keys.filter(function(item,index,list){return item&&list.indexOf(item)===index;});
  }

  function venueLineKeys(venue){
    var raw=(venue.railLineAliases||[]).slice();
    (venue.access||[]).forEach(function(item){
      var prefix=String(item||"").split("「")[0];
      prefix.split(/[／/・]/).forEach(function(part){
        if(/線|ライン|ゆりかもめ|モノレール|市電|アストラム|ポートライナー|ニューシャトル/.test(part)&&!/各線(?:ほか)?$/.test(part.trim()))raw.push(part);
      });
    });
    var result=[];
    raw.forEach(function(item){
      lineKeys(item).forEach(function(key){if(key.length>=3&&result.indexOf(key)<0)result.push(key);});
    });
    return result;
  }

  function routeMatchesVenue(route,venue){
    var routeKeys=lineKeys(route.name);
    var venueKeys=venueLineKeys(venue);
    return routeKeys.some(function(routeKey){
      return venueKeys.some(function(venueKey){
        return routeKey===venueKey||routeKey.indexOf(venueKey)>=0||venueKey.indexOf(routeKey)>=0;
      });
    });
  }

  function resolveVenue(name,venues){
    var requested=normalizeVenue(name);
    return venues.find(function(venue){
      return[venue.name].concat(venue.aliases||[]).some(function(candidate){
        var key=normalizeVenue(candidate);
        return key&&(requested===key||requested.indexOf(key)>=0||key.indexOf(requested)>=0);
      });
    })||null;
  }

  function occurrenceRows(event){
    var rows=[];
    if(Array.isArray(event.schedule)&&event.schedule.length){
      event.schedule.forEach(function(item){
        if(item&&item.venue)rows.push({date:String(item.date||event.eventDate||"").slice(0,10),venue:item.venue});
      });
    }else if(event.venue&&!/オンライン|複数会場|会場未定/.test(event.venue)){
      (event.eventDates&&event.eventDates.length?event.eventDates:[event.eventDate]).forEach(function(date){
        rows.push({date:String(date||"").slice(0,10),venue:event.venue});
      });
    }
    return rows;
  }

  function disruptionsForEvent(event,today,venues,routes){
    var found=[];
    occurrenceRows(event).forEach(function(row){
      if(row.date!==today)return;
      var venue=resolveVenue(row.venue,venues);
      if(!venue)return;
      routes.forEach(function(route){
        if(routeMatchesVenue(route,venue)&&!found.some(function(item){return item.url===route.url;}))found.push(route);
      });
    });
    return found;
  }

  function alertHtml(routes,sourceName){
    var items=routes.map(function(route){
      return '<li><div><strong>'+esc(route.name)+'</strong><span>'+esc(route.status||"運行情報あり")+'</span></div><a href="'+esc(route.url)+'" target="_blank" rel="noopener">最新情報 ↗</a></li>';
    }).join("");
    return '<aside class="train-status-alert" role="alert" aria-label="公演当日の鉄道運行情報">'+
      '<div class="train-status-alert-head"><span aria-hidden="true">!</span><div><small>公演当日の交通情報</small><strong>最寄り路線に運行情報があります</strong></div></div>'+
      '<ul>'+items+'</ul><p>'+esc(sourceName||"運行情報提供元")+'の掲載状況です。移動前にリンク先で最新情報を確認してください。</p></aside>';
  }

  function scheduleEvents(){
    var snapshot=document.getElementById("snapshot-data");
    if(!snapshot)return null;
    try{return(JSON.parse(snapshot.textContent||"{}").events||[]);}catch(_error){return null;}
  }

  function mountScheduleAlerts(today,events,venues,status){
    document.querySelectorAll(".card[data-event-id]").forEach(function(card){
      if(card.querySelector(".train-status-alert"))return;
      var id=card.getAttribute("data-event-id")||"";
      var event=events.find(function(item){return String(item.id||"")===id;});
      if(!event)return;
      var routes=disruptionsForEvent(event,today,venues,status.routes||[]);
      if(!routes.length)return;
      var meta=card.querySelector(".meta");
      if(meta)meta.insertAdjacentHTML("afterend",alertHtml(routes,status.source&&status.source.name));
    });
  }

  function mountScheduleSummary(today,events,venues,status){
    var cards=document.getElementById("cards");
    if(!cards||document.querySelector(".train-status-summary"))return;
    var routes=[];
    events.forEach(function(event){
      disruptionsForEvent(event,today,venues,status.routes||[]).forEach(function(route){
        if(!routes.some(function(item){return item.url===route.url;}))routes.push(route);
      });
    });
    if(!routes.length)return;
    var target=document.querySelector(".schedule-disclaimer")||document.querySelector(".lead");
    if(!target)return;
    target.insertAdjacentHTML("afterend",alertHtml(routes,status.source&&status.source.name).replace('class="train-status-alert"','class="train-status-alert train-status-summary"'));
  }

  function observeScheduleAlerts(today,events,venues,status){
    var cards=document.getElementById("cards");
    if(!cards)return;
    var queued=false;
    var observer=new MutationObserver(function(){
      if(queued)return;
      queued=true;
      window.setTimeout(function(){queued=false;mountScheduleAlerts(today,events,venues,status);},0);
    });
    observer.observe(cards,{childList:true,subtree:true});
  }

  function currentDetailVenue(venues){
    var params=new URLSearchParams(location.search);
    var id=params.get("id")||"";
    var name=params.get("name")||"";
    return venues.find(function(venue){return id&&venue.id===id;})||resolveVenue(name,venues);
  }

  function detailRoutes(today,events,venue,routes){
    if(!venue)return[];
    var hasToday=events.some(function(event){
      return occurrenceRows(event).some(function(row){
        var candidate=resolveVenue(row.venue,[venue]);
        return row.date===today&&!!candidate;
      });
    });
    return hasToday?routes.filter(function(route){return routeMatchesVenue(route,venue);}):[];
  }

  function mountDetailAlert(today,events,venues,status){
    var venue=currentDetailVenue(venues);
    var routes=detailRoutes(today,events,venue,status.routes||[]);
    if(!routes.length)return;
    var root=document.getElementById("venue-detail");
    if(!root)return;
    function insert(){
      var hero=root.querySelector(".venue-detail-hero");
      if(!hero||root.querySelector(".train-status-alert"))return false;
      hero.insertAdjacentHTML("afterend",alertHtml(routes,status.source&&status.source.name));
      return true;
    }
    if(insert())return;
    var observer=new MutationObserver(function(){if(insert())observer.disconnect();});
    observer.observe(root,{childList:true,subtree:true});
    window.setTimeout(function(){observer.disconnect();},8000);
  }

  var today=localDate(new Date());
  var embedded=scheduleEvents();
  var eventsRequest=fetch("./data/live-events.json",{cache:"no-store"})
    .then(function(response){if(!response.ok)throw new Error("events");return response.json();})
    .catch(function(){return{events:embedded||[]};});
  Promise.all([
    fetch("./data/venues.json",{cache:"no-store"}).then(function(response){if(!response.ok)throw new Error("venues");return response.json();}),
    fetch("./data/train-status.json",{cache:"no-store"}).then(function(response){if(!response.ok)throw new Error("status");return response.json();}),
    eventsRequest
  ]).then(function(values){
    var venues=values[0].venues||[];
    var status=values[1]||{};
    var events=values[2].events||[];
    if(status.date!==today||!Array.isArray(status.routes)||!status.routes.length)return;
    mountScheduleSummary(today,events,venues,status);
    mountScheduleAlerts(today,events,venues,status);
    observeScheduleAlerts(today,events,venues,status);
    mountDetailAlert(today,events,venues,status);
  }).catch(function(){
    // 取得失敗時に「平常運転」とは表示しない。警告欄自体を追加せず、既存ページを保つ。
  });

  window.KawaiiTrainStatus={
    normalizeLine:normalizeLine,
    lineKeys:lineKeys,
    venueLineKeys:venueLineKeys,
    routeMatchesVenue:routeMatchesVenue,
    occurrenceRows:occurrenceRows,
    disruptionsForEvent:disruptionsForEvent
  };
})();

(function(){
  "use strict";
  if(!document.getElementById("calendar"))return;

  if(!document.querySelector('link[data-personal-schedule]')){
    var style=document.createElement("link");
    style.rel="stylesheet";
    style.href="./personal-schedule.css?v=202608250110";
    style.setAttribute("data-personal-schedule","");
    document.head.appendChild(style);
  }

  if(!document.querySelector('script[data-personal-schedule]')){
    var script=document.createElement("script");
    script.src="./personal-schedule.js?v=202608250110";
    script.setAttribute("data-personal-schedule","");
    document.body.appendChild(script);
  }

  if(!document.querySelector('script[data-going-highlight-fix]')){
    var fix=document.createElement("script");
    fix.src="./going-highlight-fix.js?v=202608250110";
    fix.setAttribute("data-going-highlight-fix","");
    document.body.appendChild(fix);
  }

  if(!document.querySelector('script[data-going-highlight-soften]')){
    var soften=document.createElement("script");
    soften.src="./going-highlight-soften.js?v=202608300300";
    soften.setAttribute("data-going-highlight-soften","");
    document.body.appendChild(soften);
  }
})();

(function(){
  "use strict";
  if(!document.getElementById("calendar")||!document.getElementById("cards"))return;
  import("./special-venue-info.js?v=202608250046").catch(function(){});
})();
