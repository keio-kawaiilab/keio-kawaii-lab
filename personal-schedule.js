(function(){
  "use strict";

  if(!document.getElementById("calendar")||!document.getElementById("cards"))return;

  var STORAGE_KEY="kawaiiLabPersonalScheduleV1";
  var BACKUP_KEY="kawaiiLabPersonalScheduleBackupV1";
  var EXPORT_VERSION=1;
  var state={events:[],rangeStart:null};
  var calendar=document.getElementById("calendar");
  var cards=document.getElementById("cards");
  var panel=null;
  var overlay=null;
  var form=null;
  var deleteButton=null;
  var editingId="";
  var renderQueued=false;

  function esc(value){
    return String(value==null?"":value)
      .replace(/&/g,"&amp;")
      .replace(/</g,"&lt;")
      .replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;")
      .replace(/'/g,"&#39;");
  }

  function uid(){
    if(window.crypto&&typeof window.crypto.randomUUID==="function")return window.crypto.randomUUID();
    return"ps-"+Date.now().toString(36)+"-"+Math.random().toString(36).slice(2,9);
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

  function monthDay(date){return(date.getMonth()+1)+"/"+date.getDate();}

  function normalizeEvent(raw){
    if(!raw||typeof raw!=="object")return null;
    var date=String(raw.date||"");
    if(!parseIsoDate(date))return null;
    var title=String(raw.title||"").trim();
    if(!title)return null;
    return{
      id:String(raw.id||uid()),
      title:title.slice(0,120),
      date:date,
      time:/^\d{2}:\d{2}$/.test(String(raw.time||""))?String(raw.time):"",
      place:String(raw.place||"").trim().slice(0,180),
      note:String(raw.note||"").trim().slice(0,1000),
      sourceUrl:String(raw.sourceUrl||"").trim().slice(0,1000),
      sourceType:String(raw.sourceType||"personal").slice(0,40),
      createdAt:String(raw.createdAt||new Date().toISOString()),
      updatedAt:String(raw.updatedAt||new Date().toISOString())
    };
  }

  function decodePayload(text){
    try{
      var parsed=JSON.parse(text||"null");
      var rows=Array.isArray(parsed)?parsed:(parsed&&Array.isArray(parsed.events)?parsed.events:[]);
      return rows.map(normalizeEvent).filter(Boolean);
    }catch(_error){return null;}
  }

  function readLocal(){
    try{
      var primaryText=localStorage.getItem(STORAGE_KEY);
      if(primaryText!==null){
        var primary=decodePayload(primaryText);
        if(primary!==null)return primary;
      }
      var backupText=localStorage.getItem(BACKUP_KEY);
      if(backupText!==null){
        var backup=decodePayload(backupText);
        if(backup!==null)return backup;
      }
    }catch(_error){}
    return null;
  }

  function payload(){
    return JSON.stringify({
      version:EXPORT_VERSION,
      exportedAt:new Date().toISOString(),
      events:state.events
    });
  }

  function openDb(){
    return new Promise(function(resolve,reject){
      if(!window.indexedDB){reject(new Error("IndexedDB unavailable"));return;}
      var request=indexedDB.open("kawaii-lab-personal-schedule",1);
      request.onupgradeneeded=function(){
        var db=request.result;
        if(!db.objectStoreNames.contains("data"))db.createObjectStore("data");
      };
      request.onsuccess=function(){resolve(request.result);};
      request.onerror=function(){reject(request.error||new Error("IndexedDB open failed"));};
    });
  }

  function saveIdb(text){
    openDb().then(function(db){
      var tx=db.transaction("data","readwrite");
      tx.objectStore("data").put(text,"events");
      tx.oncomplete=function(){db.close();};
      tx.onerror=function(){db.close();};
    }).catch(function(){});
  }

  function loadIdb(){
    return openDb().then(function(db){
      return new Promise(function(resolve){
        var tx=db.transaction("data","readonly");
        var req=tx.objectStore("data").get("events");
        req.onsuccess=function(){var value=req.result;db.close();resolve(typeof value==="string"?decodePayload(value):null);};
        req.onerror=function(){db.close();resolve(null);};
      });
    }).catch(function(){return null;});
  }

  function requestPersistentStorage(){
    if(!navigator.storage||typeof navigator.storage.persist!=="function")return;
    navigator.storage.persist().catch(function(){});
  }

  function save(){
    state.events.sort(function(a,b){return a.date.localeCompare(b.date)||a.time.localeCompare(b.time)||a.title.localeCompare(b.title);});
    var text=payload();
    try{
      localStorage.setItem(STORAGE_KEY,text);
      localStorage.setItem(BACKUP_KEY,text);
    }catch(_error){}
    saveIdb(text);
    requestPersistentStorage();
    refreshAll();
  }

  function todayIso(){return isoDate(new Date());}

  function formatDate(value){
    var d=parseIsoDate(value);
    if(!d)return value;
    return(d.getMonth()+1)+"/"+d.getDate()+"（"+"日月火水木金土".charAt(d.getDay())+"）";
  }

  function statusText(){
    var total=state.events.length;
    if(!total)return"まだ予定はありません。公式イベントから1タップで追加もできるよ。";
    var upcoming=state.events.filter(function(event){return event.date>=todayIso();}).length;
    return total+"件保存中"+(upcoming!==total?" ／ 今後 "+upcoming+"件":"")+"。この端末のブラウザに保存されています。";
  }

  function mountPanel(){
    if(document.querySelector(".personal-schedule-panel")){
      panel=document.querySelector(".personal-schedule-panel");
      return;
    }
    panel=document.createElement("section");
    panel.className="personal-schedule-panel";
    panel.setAttribute("aria-label","自分の予定");
    panel.innerHTML=
      '<div class="personal-schedule-head">'+
        '<div><span class="personal-schedule-kicker">MY SCHEDULE</span><h2>🩷 自分の予定</h2><p class="personal-schedule-status" id="personal-schedule-status"></p></div>'+
        '<button class="personal-primary" type="button" data-personal-action="add">＋ 予定を追加</button>'+
      '</div>'+
      '<div class="personal-schedule-tools">'+
        '<button type="button" data-personal-action="export">バックアップを書き出す</button>'+
        '<button type="button" data-personal-action="import">バックアップを復元</button>'+
        '<input class="personal-import-input" type="file" accept="application/json,.json" hidden>'+
      '</div>'+
      '<p class="personal-storage-note">会員登録なし・この端末だけに保存。別端末への自動同期はありません。ブラウザのサイトデータ削除に備えて、たまにバックアップしておくと安心です。</p>'+
      '<div class="personal-upcoming" id="personal-upcoming"></div>';
    var anchor=document.querySelector(".scope-picker")||document.querySelector(".schedule-disclaimer");
    if(anchor)anchor.insertAdjacentElement("afterend",panel);else document.querySelector("main").prepend(panel);
    panel.addEventListener("click",onPanelClick);
    panel.querySelector(".personal-import-input").addEventListener("change",importFile);
  }

  function renderPanel(){
    if(!panel)return;
    var status=panel.querySelector("#personal-schedule-status");
    if(status)status.textContent=statusText();
    var upcoming=panel.querySelector("#personal-upcoming");
    if(!upcoming)return;
    var rows=state.events.filter(function(event){return event.date>=todayIso();}).slice(0,6);
    if(!rows.length){
      upcoming.innerHTML='<div class="personal-empty">カレンダーに自分だけの予定を重ねられるよ ✨</div>';
      return;
    }
    upcoming.innerHTML='<div class="personal-upcoming-title">これからの予定</div>'+rows.map(function(event){
      return '<button class="personal-upcoming-row" type="button" data-personal-edit="'+esc(event.id)+'">'+
        '<span class="personal-upcoming-date">'+esc(formatDate(event.date))+'</span>'+
        '<span class="personal-upcoming-main"><strong>'+esc(event.title)+'</strong><small>'+esc((event.time?event.time:"時間未設定")+(event.place?" ／ "+event.place:""))+'</small></span>'+
        '<span aria-hidden="true">›</span>'+
      '</button>';
    }).join("");
  }

  function mountModal(){
    if(overlay)return;
    overlay=document.createElement("div");
    overlay.className="personal-modal";
    overlay.hidden=true;
    overlay.innerHTML=
      '<div class="personal-modal-card" role="dialog" aria-modal="true" aria-labelledby="personal-modal-title">'+
        '<div class="personal-modal-head"><div><span class="personal-schedule-kicker">MY SCHEDULE</span><h2 id="personal-modal-title">予定を追加</h2></div><button class="personal-close" type="button" aria-label="閉じる">×</button></div>'+
        '<form class="personal-form">'+
          '<label><span>予定名 *</span><input name="title" maxlength="120" required placeholder="例：ライブに行く"></label>'+
          '<div class="personal-form-grid">'+
            '<label><span>日付 *</span><input name="date" type="date" required></label>'+
            '<label><span>開始時刻</span><input name="time" type="time"></label>'+
          '</div>'+
          '<label><span>場所</span><input name="place" maxlength="180" placeholder="例：有明アリーナ"></label>'+
          '<label><span>メモ</span><textarea name="note" maxlength="1000" rows="4" placeholder="集合時間、持ち物、交通など"></textarea></label>'+
          '<div class="personal-form-actions">'+
            '<button class="personal-danger" type="button" data-personal-action="delete" hidden>削除</button>'+
            '<span></span><button type="button" data-personal-action="cancel">キャンセル</button><button class="personal-primary" type="submit">保存</button>'+
          '</div>'+
        '</form>'+
      '</div>';
    document.body.appendChild(overlay);
    form=overlay.querySelector("form");
    deleteButton=overlay.querySelector('[data-personal-action="delete"]');
    overlay.querySelector(".personal-close").addEventListener("click",closeModal);
    overlay.querySelector('[data-personal-action="cancel"]').addEventListener("click",closeModal);
    overlay.addEventListener("click",function(event){if(event.target===overlay)closeModal();});
    deleteButton.addEventListener("click",deleteEditing);
    form.addEventListener("submit",submitForm);
    document.addEventListener("keydown",function(event){if(event.key==="Escape"&&!overlay.hidden)closeModal();});
  }

  function openModal(seed){
    mountModal();
    var event=seed||{};
    editingId=String(event.id||"");
    overlay.querySelector("#personal-modal-title").textContent=editingId?"予定を編集":"予定を追加";
    form.elements.title.value=event.title||"";
    form.elements.date.value=event.date||todayIso();
    form.elements.time.value=event.time||"";
    form.elements.place.value=event.place||"";
    form.elements.note.value=event.note||"";
    form.dataset.sourceUrl=event.sourceUrl||"";
    form.dataset.sourceType=event.sourceType||"personal";
    deleteButton.hidden=!editingId;
    overlay.hidden=false;
    document.documentElement.classList.add("personal-modal-open");
    window.setTimeout(function(){form.elements.title.focus();},0);
  }

  function closeModal(){
    if(!overlay)return;
    overlay.hidden=true;
    document.documentElement.classList.remove("personal-modal-open");
    editingId="";
  }

  function submitForm(event){
    event.preventDefault();
    var current=state.events.find(function(item){return item.id===editingId;});
    var next=normalizeEvent({
      id:editingId||uid(),
      title:form.elements.title.value,
      date:form.elements.date.value,
      time:form.elements.time.value,
      place:form.elements.place.value,
      note:form.elements.note.value,
      sourceUrl:form.dataset.sourceUrl||"",
      sourceType:form.dataset.sourceType||"personal",
      createdAt:current?current.createdAt:new Date().toISOString(),
      updatedAt:new Date().toISOString()
    });
    if(!next)return;
    if(current)state.events=state.events.map(function(item){return item.id===editingId?next:item;});
    else state.events.push(next);
    save();
    closeModal();
  }

  function deleteEditing(){
    if(!editingId)return;
    state.events=state.events.filter(function(item){return item.id!==editingId;});
    save();
    closeModal();
  }

  function onPanelClick(event){
    var action=event.target.closest("[data-personal-action]");
    if(action){
      var name=action.getAttribute("data-personal-action");
      if(name==="add")openModal();
      if(name==="export")exportBackup();
      if(name==="import")panel.querySelector(".personal-import-input").click();
      return;
    }
    var edit=event.target.closest("[data-personal-edit]");
    if(edit){
      var item=state.events.find(function(row){return row.id===edit.getAttribute("data-personal-edit");});
      if(item)openModal(item);
    }
  }

  function exportBackup(){
    var blob=new Blob([payload()],{type:"application/json"});
    var url=URL.createObjectURL(blob);
    var link=document.createElement("a");
    link.href=url;
    link.download="kawaii-lab-my-schedule-"+todayIso()+".json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(function(){URL.revokeObjectURL(url);},1000);
  }

  function importFile(event){
    var input=event.target;
    var file=input.files&&input.files[0];
    if(!file)return;
    var reader=new FileReader();
    reader.onload=function(){
      var rows=decodePayload(String(reader.result||""));
      input.value="";
      if(!rows){window.alert("このバックアップは読み込めませんでした。");return;}
      var map={};
      state.events.concat(rows).forEach(function(item){
        var key=item.id||[item.date,item.time,item.title].join("|");
        map[key]=item;
      });
      state.events=Object.keys(map).map(function(key){return map[key];});
      save();
      window.alert("バックアップを復元しました。");
    };
    reader.readAsText(file,"utf-8");
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
    var visible=state.events.filter(function(event){var d=parseIsoDate(event.date);return d&&d>=rangeStart&&d<=rangeEnd;});
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
        var mark=document.createElement("button");
        mark.type="button";
        mark.className="mark personal-calendar-mark";
        mark.style.left="calc("+(item.col/7*100)+"% + 2px)";
        mark.style.width="calc("+(1/7*100)+"% - 4px)";
        mark.style.top=(base+lane*25)+"px";
        mark.textContent="♡ "+(item.event.time?item.event.time+" ":"")+item.event.title;
        mark.title=(item.event.time?item.event.time+"｜":"")+item.event.title+(item.event.place?"｜"+item.event.place:"");
        mark.addEventListener("click",function(){openModal(item.event);});
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
    return normalizeEvent({
      title:title||"KAWAII LAB. イベント",
      date:date,
      time:time,
      place:place,
      note:"公式スケジュールから追加",
      sourceUrl:source?source.href:"",
      sourceType:"official"
    });
  }

  function alreadyAdded(seed){
    return state.events.some(function(item){
      if(seed.sourceUrl&&item.sourceUrl)return item.sourceUrl===seed.sourceUrl&&item.date===seed.date;
      return item.date===seed.date&&item.title===seed.title;
    });
  }

  function bindCards(){
    [].slice.call(cards.querySelectorAll(".card")).forEach(function(card){
      var existing=card.querySelector(".personal-card-add");
      var seed=extractCardSeed(card);
      if(!seed)return;
      if(existing){
        var added=alreadyAdded(seed);
        existing.disabled=added;
        existing.textContent=added?"✓ 自分の予定に追加済み":"＋ 自分の予定に追加";
        return;
      }
      var button=document.createElement("button");
      button.type="button";
      button.className="personal-card-add";
      var isAdded=alreadyAdded(seed);
      button.disabled=isAdded;
      button.textContent=isAdded?"✓ 自分の予定に追加済み":"＋ 自分の予定に追加";
      button.addEventListener("click",function(){
        var fresh=extractCardSeed(card);
        if(!fresh||alreadyAdded(fresh))return;
        state.events.push(fresh);
        save();
      });
      card.appendChild(button);
    });
  }

  function refreshAll(){renderPanel();overlayCalendar();bindCards();}

  function queueRender(){
    if(renderQueued)return;
    renderQueued=true;
    window.setTimeout(function(){renderQueued=false;refreshAll();},0);
  }

  function observeDynamicContent(){
    var calendarObserver=new MutationObserver(queueRender);
    calendarObserver.observe(calendar,{childList:true});
    var cardsObserver=new MutationObserver(function(){window.setTimeout(bindCards,0);});
    cardsObserver.observe(cards,{childList:true});
    var range=document.getElementById("range");
    if(range){
      new MutationObserver(function(){window.setTimeout(overlayCalendar,0);}).observe(range,{childList:true,characterData:true,subtree:true});
    }
  }

  function boot(rows){
    state.events=rows||[];
    mountPanel();
    mountModal();
    refreshAll();
    observeDynamicContent();
  }

  var local=readLocal();
  if(local!==null){boot(local);}
  else{
    loadIdb().then(function(rows){boot(rows||[]);});
  }

  window.addEventListener("storage",function(event){
    if(event.key!==STORAGE_KEY)return;
    var rows=decodePayload(event.newValue||"");
    if(rows){state.events=rows;refreshAll();}
  });
})();
