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

  function normalizeEvent(raw){
    if(!raw||typeof raw!=="object")return null;
    var date=String(raw.date||"");
    if(!parseIsoDate(date))return null;
    var title=String(raw.title||"").trim();
    if(!title)return null;
    return{
      key:String(raw.key||"").slice(0,1200),
      title:title.slice(0,180),
      date:date,
      time:/^\d{2}:\d{2}$/.test(String(raw.time||""))?String(raw.time):"",
      place:String(raw.place||"").trim().slice(0,220),
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

  function overlayCalendar(){
    var weeks=[].slice.call(calendar.querySelectorAll(".week"));
    if(!weeks.length)return;
    weeks.forEach(function(week){
      if(!week.dataset.personalBaseMinHeight)week.dataset.personalBaseMinHeight=week.style.minHeight||"";
      else week.style.minHeight=week.dataset.personalBaseMinHeight;
      [].slice.call(week.querySelectorAll(".personal-calendar-mark")).forEach(function(mark){mark.remove();});
    });

    var rangeStart=resolveRangeStart();
    var rangeEnd=new Date(rangeStart);rangeEnd.setDate(rangeEnd.getDate()+34);
    var gridStart=new Date(rangeStart);gridStart.setDate(gridStart.getDate()-gridStart.getDay());
    var visible=state.events.filter(function(event){
      var d=parseIsoDate(event.date);return d&&d>=rangeStart&&d<=rangeEnd;
    });
    var byWeek={};
    visible.forEach(function(event){
      var date=parseIsoDate(event.date);
      var delta=Math.round((date-gridStart)/86400000);
      var weekIndex=Math.floor(delta/7);
      if(weekIndex<0||weekIndex>=weeks.length)return;
      (byWeek[weekIndex]||(byWeek[weekIndex]=[])).push({event:event,col:date.getDay()});
    });

    Object.keys(byWeek).forEach(function(key){
      var week=weeks[+key];
      var base=31;
      [].slice.call(week.querySelectorAll(".mark:not(.personal-calendar-mark)")).forEach(function(mark){
        var top=parseFloat(mark.style.top||"0")||0;
        var height=parseFloat(getComputedStyle(mark).height)||mark.offsetHeight||24;
        base=Math.max(base,top+height+5);
      });
      var laneByCol={};
      byWeek[key].sort(function(a,b){return a.event.time.localeCompare(b.event.time)||a.event.title.localeCompare(b.event.title);}).forEach(function(item){
        var lane=laneByCol[item.col]||0;laneByCol[item.col]=lane+1;
        var mark=document.createElement("div");
        mark.className="mark personal-calendar-mark";
        mark.style.left="calc("+(item.col/7*100)+"% + 2px)";
        mark.style.width="calc("+(1/7*100)+"% - 4px)";
        mark.style.top=(base+lane*25)+"px";
        mark.textContent="♡ "+(item.event.time?item.event.time+" ":"")+item.event.title;
        mark.title="行く予定｜"+(item.event.time?item.event.time+"｜":"")+item.event.title+(item.event.place?"｜"+item.event.place:"");
        week.appendChild(mark);
        var needed=base+lane*25+33;
        var current=parseFloat(week.style.minHeight||"0")||week.offsetHeight;
        if(needed>current)week.style.minHeight=needed+"px";
      });
    });
  }

  function extractCardSeed(card){
    var dateEl=card.querySelector(".performance-date");
    var dateMatch=dateEl&&String(dateEl.textContent||"").match(/(\d{4})\/(\d{1,2})\/(\d{1,2})/);
    if(!dateMatch)return null;
    var date=[dateMatch[1],String(dateMatch[2]).padStart(2,"0"),String(dateMatch[3]).padStart(2,"0")].join("-");
    var title=String((card.querySelector("h3")||{}).textContent||"").replace(/^\s*[🎤📱🎁💿]\s*/,"").trim();
    var place="",time="";
    [].slice.call(card.querySelectorAll(".meta > div")).forEach(function(row){
      var label=String((row.querySelector("b")||{}).textContent||"").trim();
      var value=String(row.textContent||"").replace(label,"").trim();
      if(label==="会場")place=value;
      if(label==="開催日時"){
        var m=value.match(/(?:開演|開始)\s*(\d{1,2}:\d{2})/);
        if(m)time=m[1].padStart(5,"0");
      }
    });
    var source=card.querySelector("a.src");
    var seed=normalizeEvent({
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

  function refreshAll(){renderPanel();overlayCalendar();bindCards();}

  function queueRender(){
    if(renderQueued)return;
    renderQueued=true;
    window.setTimeout(function(){renderQueued=false;refreshAll();},0);
  }

  function observeDynamicContent(){
    new MutationObserver(queueRender).observe(calendar,{childList:true});
    new MutationObserver(function(){window.setTimeout(bindCards,0);}).observe(cards,{childList:true});
    var range=document.getElementById("range");
    if(range)new MutationObserver(function(){window.setTimeout(overlayCalendar,0);}).observe(range,{childList:true,characterData:true,subtree:true});
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
