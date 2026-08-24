(function(){
  "use strict";

  if(!document.getElementById("calendar")||!document.getElementById("cards"))return;

  var STORAGE_KEY="kawaiiLabGoingEventsV1";
  var state={events:[],rangeStart:null};
  var calendar=document.getElementById("calendar");
  var cards=document.getElementById("cards");
  var panel=null;
  var renderQueued=false;

  function esc(value){
    return String(value==null?"":value)
      .replace(/&/g,"&amp;")
      .replace(/</g,"&lt;")
      .replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;")
      .replace(/'/g,"&#39;");
  }

  function parseIsoDate(value){
    var m=String(value||"").match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if(!m)return null;
    var d=new Date(+m[1],+m[2]-1,+m[3]);
    if(d.getFullYear()!==+m[1]||d.getMonth()!==+m[2]-1||d.getDate()!==+m[3])return null;
    return d;
  }

  function isoDate(date){
    return[
      date.getFullYear(),
      String(date.getMonth()+1).padStart(2,"0"),
      String(date.getDate()).padStart(2,"0")
    ].join("-");
  }

  function cleanText(value){return String(value||"").replace(/\s+/g," ").trim();}

  function normalizeEvent(raw){
    if(!raw||typeof raw!=="object")return null;
    var date=String(raw.date||"");
    var title=cleanText(raw.title);
    if(!parseIsoDate(date)||!title)return null;
    return{
      key:String(raw.key||"").slice(0,1200),
      performanceKey:String(raw.performanceKey||"").slice(0,1200),
      title:title.slice(0,180),
      date:date,
      time:/^\d{2}:\d{2}$/.test(String(raw.time||""))?String(raw.time):"",
      place:cleanText(raw.place).slice(0,220),
      sourceUrl:String(raw.sourceUrl||"").trim().slice(0,1000)
    };
  }

  function eventKey(event){
    if(event.key)return event.key;
    return[event.sourceUrl||"",event.date,event.title].join("|");
  }

  function readLocal(){
    try{
      var parsed=JSON.parse(localStorage.getItem(STORAGE_KEY)||"[]");
      if(!Array.isArray(parsed))return[];
      return parsed.map(normalizeEvent).filter(Boolean);
    }catch(_error){return[];}
  }

  function save(){
    state.events.sort(function(a,b){
      return a.date.localeCompare(b.date)||a.time.localeCompare(b.time)||a.title.localeCompare(b.title);
    });
    try{localStorage.setItem(STORAGE_KEY,JSON.stringify(state.events));}catch(_error){}
    refreshAll();
  }

  function todayIso(){return isoDate(new Date());}

  function formatDate(value){
    var d=parseIsoDate(value);
    if(!d)return value;
    return(d.getMonth()+1)+"/"+d.getDate()+"（"+"日月火水木金土".charAt(d.getDay())+"）";
  }

  function mountPanel(){
    if(document.querySelector(".personal-schedule-panel")){
      panel=document.querySelector(".personal-schedule-panel");
      return;
    }
    panel=document.createElement("section");
    panel.className="personal-schedule-panel";
    panel.setAttribute("aria-label","行く予定");
    panel.innerHTML=
      '<div class="personal-schedule-head">'+
        '<div><span class="personal-schedule-kicker">MY EVENTS</span><h2>🩷 行く予定</h2><p class="personal-schedule-status" id="personal-schedule-status"></p></div>'+
      '</div>'+
      '<p class="personal-storage-note">公式スケジュールのイベントだけを「行く予定」としてこの端末のブラウザに保存します。自由入力や個人的なメモは保存しません。</p>'+
      '<div class="personal-upcoming" id="personal-upcoming"></div>';
    var anchor=document.querySelector(".scope-picker")||document.querySelector(".schedule-disclaimer");
    if(anchor)anchor.insertAdjacentElement("afterend",panel);else document.querySelector("main").prepend(panel);
    panel.addEventListener("click",onPanelClick);
  }

  function renderPanel(){
    if(!panel)return;
    var upcoming=state.events.filter(function(event){return event.date>=todayIso();});
    var status=panel.querySelector("#personal-schedule-status");
    if(status)status.textContent=upcoming.length?"今後 "+upcoming.length+"件を行く予定にしています。":"まだ行く予定にしたイベントはありません。";
    var container=panel.querySelector("#personal-upcoming");
    if(!container)return;
    if(!upcoming.length){
      container.innerHTML='<div class="personal-empty">公式イベントの詳細にある「＋ 行く予定に追加」から登録できます ✨</div>';
      return;
    }
    container.innerHTML='<div class="personal-upcoming-title">これから行く予定</div>'+upcoming.slice(0,8).map(function(event){
      return '<div class="personal-upcoming-row">'+
        '<span class="personal-upcoming-date">'+esc(formatDate(event.date))+'</span>'+
        '<span class="personal-upcoming-main"><strong>'+esc(event.title)+'</strong><small>'+esc((event.time?event.time:"時間未発表")+(event.place?" ／ "+event.place:""))+'</small></span>'+
        '<button type="button" class="personal-remove" data-personal-remove="'+esc(eventKey(event))+'" aria-label="行く予定から外す">×</button>'+
      '</div>';
    }).join("");
  }

  function onPanelClick(event){
    var button=event.target.closest("[data-personal-remove]");
    if(!button)return;
    var key=button.getAttribute("data-personal-remove");
    state.events=state.events.filter(function(item){return eventKey(item)!==key;});
    save();
  }

  function resolveRangeStart(){
    var range=document.getElementById("range");
    var match=range&&String(range.textContent||"").match(/(\d{1,2})\/(\d{1,2})\s*〜/);
    if(!match)return state.rangeStart||new Date();
    var month=+match[1],day=+match[2];
    if(state.rangeStart){
      var plus=new Date(state.rangeStart);plus.setDate(plus.getDate()+35);
      var minus=new Date(state.rangeStart);minus.setDate(minus.getDate()-35);
      if(plus.getMonth()+1===month&&plus.getDate()===day){state.rangeStart=plus;return plus;}
      if(minus.getMonth()+1===month&&minus.getDate()===day){state.rangeStart=minus;return minus;}
    }
    var now=new Date(),best=null,bestDistance=Infinity;
    for(var year=now.getFullYear()-1;year<=now.getFullYear()+5;year++){
      var candidate=new Date(year,month-1,day);
      if(candidate.getMonth()+1!==month||candidate.getDate()!==day)continue;
      var distance=Math.abs(candidate-now);
      if(candidate<new Date(now.getFullYear(),now.getMonth(),now.getDate()-10))distance+=180*86400000;
      if(distance<bestDistance){best=candidate;bestDistance=distance;}
    }
    state.rangeStart=best||now;
    return state.rangeStart;
  }

  function markColumn(mark){
    var m=String(mark.style.left||"").match(/calc\(\s*([\d.]+)%/);
    if(!m)return-1;
    return Math.max(0,Math.min(6,Math.round((parseFloat(m[1])||0)*7/100)));
  }

  function markEventTitle(mark){
    return cleanText(String(mark.getAttribute("title")||"").replace(/｜イベント詳細$/,""));
  }

  function highlightCalendarItems(){
    [].slice.call(calendar.querySelectorAll(".personal-calendar-mark")).forEach(function(mark){mark.remove();});
    [].slice.call(calendar.querySelectorAll(".personal-going-highlight")).forEach(function(mark){
      mark.classList.remove("personal-going-highlight");
      mark.removeAttribute("data-going-event");
    });

    var weeks=[].slice.call(calendar.querySelectorAll(".week"));
    if(!weeks.length||!state.events.length)return;

    var rangeStart=resolveRangeStart();
    var rangeEnd=new Date(rangeStart);rangeEnd.setDate(rangeEnd.getDate()+34);
    var gridStart=new Date(rangeStart);gridStart.setDate(gridStart.getDate()-gridStart.getDay());

    state.events.forEach(function(event){
      var date=parseIsoDate(event.date);
      if(!date||date<rangeStart||date>rangeEnd)return;
      var delta=Math.round((date-gridStart)/86400000);
      var weekIndex=Math.floor(delta/7);
      if(weekIndex<0||weekIndex>=weeks.length)return;
      var week=weeks[weekIndex];
      var col=date.getDay();
      var candidates=[].slice.call(week.querySelectorAll(".mark.performance"));
      var matches=[];

      if(event.performanceKey){
        matches=candidates.filter(function(mark){
          return mark.getAttribute("data-performance-key")===event.performanceKey;
        });
      }

      if(!matches.length){
        matches=candidates.filter(function(mark){
          return markColumn(mark)===col&&markEventTitle(mark)===cleanText(event.title);
        });
      }

      matches.forEach(function(mark){
        mark.classList.add("personal-going-highlight");
        mark.setAttribute("data-going-event","true");
      });
    });
  }

  function extractCardSeed(card){
    var dateEl=card.querySelector(".performance-date");
    var dateMatch=dateEl&&String(dateEl.textContent||"").match(/(\d{4})\/(\d{1,2})\/(\d{1,2})/);
    if(!dateMatch)return null;
    var date=[dateMatch[1],String(dateMatch[2]).padStart(2,"0"),String(dateMatch[3]).padStart(2,"0")].join("-");
    var title=cleanText((card.querySelector("h3")||{}).textContent||"").replace(/^\s*[🎤📱🎁💿]\s*/,"").trim();
    var place="",time="";
    [].slice.call(card.querySelectorAll(".meta > div")).forEach(function(row){
      var label=cleanText((row.querySelector("b")||{}).textContent||"");
      var value=cleanText(row.textContent||"").replace(label,"").trim();
      if(label==="会場")place=value;
      if(label==="開催日時"){
        var m=value.match(/(?:開演|開始)\s*(\d{1,2}:\d{2})/);
        if(m)time=m[1].padStart(5,"0");
      }
    });
    var source=card.querySelector("a.src");
    var seed=normalizeEvent({
      performanceKey:card.getAttribute("data-performance-key")||"",
      title:title||"KAWAII LAB. イベント",
      date:date,
      time:time,
      place:place,
      sourceUrl:source?source.href:""
    });
    if(!seed)return null;
    seed.key=eventKey(seed);
    return seed;
  }

  function isAdded(seed){
    var key=eventKey(seed);
    return state.events.some(function(item){return eventKey(item)===key;});
  }

  function bindCards(){
    [].slice.call(cards.querySelectorAll(".card")).forEach(function(card){
      var seed=extractCardSeed(card);
      if(!seed)return;
      var button=card.querySelector(".personal-card-add");
      if(!button){
        button=document.createElement("button");
        button.type="button";
        button.className="personal-card-add";
        button.addEventListener("click",function(){
          var fresh=extractCardSeed(card);
          if(!fresh)return;
          if(isAdded(fresh)){
            state.events=state.events.filter(function(item){return eventKey(item)!==eventKey(fresh);});
          }else{
            state.events.push(fresh);
          }
          save();
        });
        card.appendChild(button);
      }
      var added=isAdded(seed);
      button.classList.toggle("is-added",added);
      button.textContent=added?"✓ 行く予定に追加済み（外す）":"＋ 行く予定に追加";
    });
  }

  function refreshAll(){renderPanel();highlightCalendarItems();bindCards();}

  function queueRender(){
    if(renderQueued)return;
    renderQueued=true;
    window.setTimeout(function(){renderQueued=false;refreshAll();},0);
  }

  function observeDynamicContent(){
    new MutationObserver(queueRender).observe(calendar,{childList:true});
    new MutationObserver(function(){window.setTimeout(function(){bindCards();highlightCalendarItems();},0);}).observe(cards,{childList:true});
    var range=document.getElementById("range");
    if(range)new MutationObserver(function(){window.setTimeout(highlightCalendarItems,0);}).observe(range,{childList:true,characterData:true,subtree:true});
  }

  state.events=readLocal();
  mountPanel();
  refreshAll();
  observeDynamicContent();

  window.addEventListener("storage",function(event){
    if(event.key!==STORAGE_KEY)return;
    state.events=readLocal();
    refreshAll();
  });
})();
