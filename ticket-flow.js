(function(){
  "use strict";

  var cards=document.getElementById("cards");
  if(!cards)return;

  var payload=null;
  var queued=false;
  var DATA_URL="./data/live-events.json";

  if(!document.querySelector("style[data-ticket-flow-style]")){
    var style=document.createElement("style");
    style.setAttribute("data-ticket-flow-style","");
    style.textContent='\
.ticket-flow{margin-top:10px;border:1px solid #dfe4f1;border-radius:13px;background:#f7f8fc;overflow:hidden}\
.ticket-flow summary{list-style:none;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 13px;cursor:pointer;color:var(--navy);font-size:12px;font-weight:900;-webkit-tap-highlight-color:transparent}\
.ticket-flow summary::-webkit-details-marker{display:none}\
.ticket-flow summary::after{content:"⌄";font-size:18px;transition:transform .18s ease}\
.ticket-flow[open] summary::after{transform:rotate(180deg)}\
.ticket-flow-inner{padding:0 13px 13px;background:#fff}\
.ticket-flow-note{padding:10px 0 5px;color:var(--muted);font-size:10px;line-height:1.65}\
.ticket-flow-timeline{position:relative;margin:8px 2px 2px 7px;padding-left:24px}\
.ticket-flow-timeline::before{content:"";position:absolute;left:6px;top:9px;bottom:13px;width:2px;background:#dfe3ec}\
.ticket-flow-step{position:relative;margin:0 0 16px;padding-left:7px}\
.ticket-flow-step:last-child{margin-bottom:3px}\
.ticket-flow-dot{position:absolute;left:-24px;top:3px;width:15px;height:15px;border-radius:50%;border:3px solid #9ca4b3;background:#9ca4b3;box-shadow:inset 0 0 0 3px #fff}\
.ticket-flow-step.is-open .ticket-flow-dot{border-color:#2d9950;background:#2d9950;box-shadow:0 0 0 4px rgba(45,153,80,.12),inset 0 0 0 3px #fff}\
.ticket-flow-step.is-upcoming .ticket-flow-dot{border-color:#c19b46;background:#fff}\
.ticket-flow-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}\
.ticket-flow-title{color:var(--navy);font-size:12px;font-weight:900;line-height:1.45}\
.ticket-flow-state{display:inline-flex;flex:0 0 auto;padding:3px 7px;border-radius:999px;background:#eef0f3;color:#656b79;font-size:9px;font-weight:900;white-space:nowrap}\
.ticket-flow-step.is-open .ticket-flow-state{background:#e8f6ec;color:#23713a}\
.ticket-flow-step.is-upcoming .ticket-flow-state{background:#fff4d8;color:#795f13}\
.ticket-flow-period{margin-top:4px;color:var(--muted);font-size:10px;line-height:1.5}\
.ticket-flow-meta{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-top:7px}\
.ticket-flow-provider{display:inline-flex;padding:3px 7px;border-radius:999px;background:#eef0f5;color:#50586f;font-size:9px;font-weight:900}\
.ticket-flow-source{font-size:9px;font-weight:800;color:var(--navy);text-underline-offset:2px}\
.ticket-flow-empty,.ticket-flow-guard{margin-top:8px;padding:10px 11px;border:1px dashed #c9ceda;border-radius:10px;background:#faf9f6;color:#666d7c;font-size:10px;line-height:1.65}\
+';
    document.head.appendChild(style);
  }

  function esc(value){
    return String(value==null?"":value)
      .replace(/&/g,"&amp;")
      .replace(/</g,"&lt;")
      .replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;");
  }

  function clean(value){return String(value==null?"":value).replace(/\s+/g," ").trim();}
  function pad(value){return String(value).padStart(2,"0");}

  function norm(value){
    return clean(value).normalize("NFKC").toLowerCase()
      .replace(/^[🎤🎫🎪🎉⭐🌟💻📺🛍️🏟️\s]+/u,"")
      .replace(/[\s　・･:：/／\\()（）\[\]【】「」『』"'’‘.,。!?！？\-‐‑–—―ー]/g,"");
  }

  function normVenue(value){
    return norm(value)
      .replace(/^(北海道|東京都|京都府|大阪府|.{2,3}県)/,"")
      .replace(/メインホール|大ホール|ホール|劇場棟/g,"");
  }

  function metaText(card,label){
    var item=[].slice.call(card.querySelectorAll(".meta > div")).find(function(node){
      var b=node.querySelector("b");
      return b&&clean(b.textContent)===label;
    });
    if(!item)return"";
    var clone=item.cloneNode(true);
    var b=clone.querySelector("b");
    if(b)b.remove();
    return clean(clone.textContent);
  }

  function cardInfo(card){
    var dateText=clean(card.querySelector(".performance-date")&&card.querySelector(".performance-date").textContent);
    var m=dateText.match(/(20\d{2})\/(\d{1,2})\/(\d{1,2})/);
    return{
      group:metaText(card,"グループ"),
      date:m?[m[1],pad(m[2]),pad(m[3])].join("-"):"",
      venue:metaText(card,"会場"),
      title:clean(card.querySelector("h3")&&card.querySelector("h3").textContent)
    };
  }

  function eventDates(event){
    var out=[];
    function add(value){var d=clean(value).slice(0,10);if(/^20\d{2}-\d{2}-\d{2}$/.test(d)&&out.indexOf(d)<0)out.push(d);}
    add(event.eventDate);
    (Array.isArray(event.eventDates)?event.eventDates:[]).forEach(add);
    (Array.isArray(event.schedule)?event.schedule:[]).forEach(function(row){if(row)add(row.date);});
    return out;
  }

  function eventVenueForDate(event,date){
    var rows=Array.isArray(event.schedule)?event.schedule:[];
    var row=rows.find(function(x){return x&&clean(x.date).slice(0,10)===date&&x.venue;});
    return clean(row&&row.venue||event.venue||"");
  }

  function titleMatches(event,card){
    var groupNorm=norm(card.group);
    var cardNorm=norm(card.title);
    var candidates=[event.displayTitle,event.eventTitle,event.title].map(norm).filter(Boolean);
    return candidates.some(function(candidate){
      if(candidate===groupNorm)return false;
      if(candidate===cardNorm)return true;
      var shorter=Math.min(candidate.length,cardNorm.length);
      return shorter>=12&&(candidate.indexOf(cardNorm)>=0||cardNorm.indexOf(candidate)>=0);
    });
  }

  function venueMatches(event,card){
    var a=normVenue(eventVenueForDate(event,card.date));
    var b=normVenue(card.venue);
    if(!a||!b)return false;
    if(a===b)return true;
    var shorter=Math.min(a.length,b.length);
    return shorter>=6&&(a.indexOf(b)>=0||b.indexOf(a)>=0);
  }

  function isTicketOffer(event){
    if(!event||typeof event!=="object")return false;
    if(clean(event.ticketType)==="現在受付なし")return false;
    if(!event.applyStart&&!event.applyEnd)return false;
    if(event.applicationWindowVerified!==true&&event.deadlineVerified!==true)return false;
    if(/release-event|benefit-event/.test(clean(event.eventCategory)))return false;
    return true;
  }

  function relatedOffers(card){
    if(!payload||!Array.isArray(payload.events))return[];
    var info=cardInfo(card);
    if(!info.group||!info.date)return[];
    return payload.events.filter(function(event){
      if(!isTicketOffer(event))return false;
      if(clean(event.group)!==info.group)return false;
      if(eventDates(event).indexOf(info.date)<0)return false;
      return titleMatches(event,info)||venueMatches(event,info);
    });
  }

  function providerName(event){
    var id=clean(event.ticketProvider||event.primarySource||event.sourceType).toLowerCase();
    var names={pia:"チケットぴあ",eplus:"イープラス",lawson:"ローチケ",official:"公式 / FC",sukisuki:"SUKISUKI",rakuten:"楽天チケット",hmv:"HMV",tower:"タワーレコード","kawaii-store":"KAWAII LAB. STORE"};
    return names[id]||clean(event.ticketProvider||event.primarySource||event.sourceType||"受付元");
  }

  function sourceUrl(event){
    return clean(event.applicationWindowSource||event.deadlineSource||event.url||"");
  }

  function parseMoment(value){
    var text=clean(value);
    if(!text)return null;
    if(/^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(text))text+="+09:00";
    var d=new Date(text);
    return Number.isNaN(d.getTime())?null:d;
  }

  function stateFor(event){
    var now=new Date();
    var start=parseMoment(event.applyStart),end=parseMoment(event.applyEnd);
    if(start&&start>now)return{label:"受付予定",cls:"is-upcoming"};
    if(end&&end<now)return{label:"受付終了",cls:"is-closed"};
    if(end&&end>=now)return{label:"受付中",cls:"is-open"};
    return{label:"期間確認",cls:"is-closed"};
  }

  function fmt(value){
    var text=clean(value);
    if(!text)return"開始日時未取得";
    var m=text.match(/(20\d{2})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);
    if(!m)return text;
    return m[1]+"/"+Number(m[2])+"/"+Number(m[3])+(m[4]?" "+m[4]+":"+m[5]:"");
  }

  function dedupe(offers){
    var map={};
    offers.forEach(function(event){
      var key=[providerName(event),clean(event.ticketType),clean(event.applyStart),clean(event.applyEnd)].join("|");
      if(!map[key])map[key]=event;
      else if(!sourceUrl(map[key])&&sourceUrl(event))map[key]=event;
    });
    return Object.keys(map).map(function(key){return map[key];}).sort(function(a,b){
      var am=parseMoment(a.applyStart)||parseMoment(a.applyEnd),bm=parseMoment(b.applyStart)||parseMoment(b.applyEnd);
      return (am?am.getTime():Number.MAX_SAFE_INTEGER)-(bm?bm.getTime():Number.MAX_SAFE_INTEGER);
    });
  }

  function flowHtml(offers){
    var unique=dedupe(offers);
    var body="";
    if(unique.length){
      body='<div class="ticket-flow-timeline">'+unique.map(function(event){
        var state=stateFor(event);
        var source=sourceUrl(event);
        return '<div class="ticket-flow-step '+state.cls+'">'+
          '<span class="ticket-flow-dot"></span>'+
          '<div class="ticket-flow-head"><span class="ticket-flow-title">'+esc(clean(event.ticketType)||"チケット受付")+'</span><span class="ticket-flow-state">'+state.label+'</span></div>'+
          '<div class="ticket-flow-period">'+esc(fmt(event.applyStart))+' 〜 '+esc(event.applyEnd?fmt(event.applyEnd):"終了日時未取得")+'</div>'+
          '<div class="ticket-flow-meta"><span class="ticket-flow-provider">'+esc(providerName(event))+'</span>'+
          (source?'<a class="ticket-flow-source" href="'+esc(source)+'" target="_blank" rel="noopener">元情報 ↗</a>':'')+
          '</div></div>';
      }).join("")+'</div>';
    }else{
      body='<div class="ticket-flow-empty">この公演について、現在のデータに確認済みの販売履歴はありません。販売がなかったことを意味するものではありません。</div>';
    }
    return '<details class="ticket-flow">'+
      '<summary>🎫 チケット販売の流れを見る</summary>'+
      '<div class="ticket-flow-inner">'+
      '<div class="ticket-flow-note">実際に取得・確認できた受付だけを表示します。FC先行→一般販売などの段階は推測しません。</div>'+
      body+
      '<div class="ticket-flow-guard">今後の販売方法も予測せず、公式・プレイガイドで確認できた情報だけを追加します。</div>'+
      '</div></details>';
  }

  function mountCard(card){
    if(card.classList.contains("release-card")||card.classList.contains("benefit-card"))return;
    var old=card.querySelector(".ticket-flow");
    if(old)old.remove();
    var offers=relatedOffers(card);
    var ticketOptions=card.querySelector(".ticket-options");
    var noTicket=card.querySelector(".no-ticket");
    var src=card.querySelector(".src");
    var html=flowHtml(offers);
    if(ticketOptions){ticketOptions.insertAdjacentHTML("afterend",html);return;}
    if(noTicket){noTicket.insertAdjacentHTML("afterend",html);return;}
    if(src){src.insertAdjacentHTML("beforebegin",html);return;}
    card.insertAdjacentHTML("beforeend",html);
  }

  function mountAll(){
    queued=false;
    if(!payload)return;
    [].slice.call(cards.querySelectorAll(".card")).forEach(mountCard);
  }

  function queue(){
    if(queued)return;
    queued=true;
    window.setTimeout(mountAll,30);
  }

  fetch(DATA_URL+"?ticketFlow="+Date.now(),{cache:"no-store"})
    .then(function(response){if(!response.ok)throw new Error("live-events");return response.json();})
    .then(function(data){payload=data||{};mountAll();new MutationObserver(function(mutations){
      var relevant=mutations.some(function(m){return [].slice.call(m.addedNodes||[]).some(function(node){return node.nodeType===1&&!node.classList.contains("ticket-flow")&&!node.closest(".ticket-flow");});});
      if(relevant)queue();
    }).observe(cards,{childList:true,subtree:true});})
    .catch(function(){
      // 履歴データを取得できない時は、誤った代替情報を表示しない。
    });
})();
