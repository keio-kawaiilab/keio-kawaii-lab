(function(){
  "use strict";

  var cards=document.getElementById("cards");
  if(!cards)return;

  var healthUrl="./data/ticket-collection-health.json";
  var historyUrl="./data/ticket-history.json";
  var flowRowsByGroupDate=null;
  var mounted=false;
  var MAX_HEALTH_AGE_MS=3*60*60*1000;

  function esc(value){
    return String(value==null?"":value)
      .replace(/&/g,"&amp;")
      .replace(/</g,"&lt;")
      .replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;");
  }

  function clean(value){return String(value==null?"":value).trim();}

  function titleKey(value,group){
    var text=clean(value).normalize("NFKC").toLowerCase();
    text=text.replace(/^[🎤🎁💿📱]\s*/,"");
    text=text.replace(/^(?:20\d{2}年)?\d{1,2}月\d{1,2}日(?:\([^)]*\)|（[^）]*）)?\s*/,"");
    ["fruits zipper","candy tune","sweet steady","cutie street","more star","kawaii lab.合同","kawaii lab."].forEach(function(name){
      if(text.indexOf(name)===0)text=text.slice(name.length).trim();
    });
    if(group){
      var lower=clean(group).toLowerCase();
      if(text.indexOf(lower)===0)text=text.slice(lower.length).trim();
    }
    text=text.split(/\s*@|開催決定|出演決定|アップグレード抽選受付|一般(?:発売|販売|先行)|fc\s*(?:会員)?先行|ファンクラブ|official fanclub|プレリザーブ|プレイガイド|先行受付|チケット受付|受付のお知らせ/i)[0];
    return text.replace(/[\s　!！・|｜\-–—_\[\]()（）『』「」:：./]/g,"");
  }

  function moment(value,endOfDay){
    var text=clean(value);
    if(!text)return null;
    var match=text.match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);
    if(!match)return null;
    var time=match[4]?(match[4]+":"+match[5]+":00"):(endOfDay?"23:59:59":"00:00:00");
    var date=new Date(match[1]+"-"+match[2]+"-"+match[3]+"T"+time+"+09:00");
    return isNaN(date.getTime())?null:date;
  }

  function fmt(value){
    var text=clean(value);
    var match=text.match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);
    if(!match)return "—";
    var out=Number(match[2])+"/"+Number(match[3]);
    if(match[4])out+=" "+match[4]+":"+match[5];
    return out;
  }

  function freshHealth(health){
    if(!health||health.safeForTicketFlowPublication!==true||health.status!=="healthy")return false;
    var checked=new Date(clean(health.checkedAt));
    if(isNaN(checked.getTime()))return false;
    var age=Date.now()-checked.getTime();
    return age>=0&&age<=MAX_HEALTH_AGE_MS;
  }

  function buildIndex(history){
    var map={};
    (history.entries||[]).forEach(function(row){
      if(!row||row.publishable!==true||row.flowEligible!==true)return;
      if(clean(row.windowCompleteness)==="missing")return;
      var group=clean(row.group),day=clean(row.eventDate).slice(0,10);
      if(!group||!day)return;
      var key=group+"|"+day;
      if(!map[key])map[key]=[];
      map[key].push(row);
    });
    Object.keys(map).forEach(function(key){
      map[key].sort(function(a,b){
        var aa=clean(a.applyStart)||clean(a.applyEnd)||"9999";
        var bb=clean(b.applyStart)||clean(b.applyEnd)||"9999";
        return aa.localeCompare(bb)||clean(a.ticketType).localeCompare(clean(b.ticketType));
      });
    });
    return map;
  }

  function cardIdentity(card){
    var key=clean(card.getAttribute("data-performance-key"));
    var pieces=key.split("|");
    var group=clean(card.getAttribute("data-group"))||clean(pieces[0]);
    var day=pieces.length>=2?clean(pieces[1]).slice(0,10):"";
    var heading=card.querySelector("h3");
    var title=heading?clean(heading.textContent).replace(/^[🎤🎁💿📱]\s*/,""):"";
    return{group:group,day:day,title:title,titleKey:titleKey(title,group)};
  }

  function safeRowsForCard(card){
    if(!flowRowsByGroupDate)return[];
    var id=cardIdentity(card);
    if(!id.group||!id.day||!id.titleKey)return[];
    var rows=(flowRowsByGroupDate[id.group+"|"+id.day]||[]).filter(function(row){
      var rowKey=titleKey(row.eventTitle,id.group);
      if(!rowKey)return false;
      return rowKey===id.titleKey||(Math.min(rowKey.length,id.titleKey.length)>=8&&(rowKey.indexOf(id.titleKey)>=0||id.titleKey.indexOf(rowKey)>=0));
    });
    var seen={};
    return rows.filter(function(row){
      var signature=[row.ticketProvider,row.ticketType,row.applyStart,row.applyEnd,row.sourceUrl].map(clean).join("|");
      if(seen[signature])return false;
      seen[signature]=true;
      return true;
    });
  }

  function providerLabel(row){
    var provider=clean(row.ticketProvider).toLowerCase();
    var names={pia:"チケットぴあ",eplus:"イープラス",lawson:"ローチケ"};
    var ticket=clean(row.ticketType)||"チケット受付";
    return names[provider]?names[provider]+"｜"+ticket:ticket;
  }

  function stateFor(row){
    var now=new Date();
    var start=moment(row.applyStart,false);
    var end=moment(row.applyEnd,true);
    if(start&&start>now)return{label:"受付予定",current:false};
    if(end&&end<now)return{label:"受付終了",current:false};
    return{label:"受付中",current:true};
  }

  function periodFor(row){
    var start=clean(row.applyStart)?fmt(row.applyStart):"開始日時未取得";
    var end=clean(row.applyEnd)?fmt(row.applyEnd):"終了日時未取得";
    return start+" 〜 "+end;
  }

  function flowHtml(rows){
    var steps=rows.map(function(row){
      var state=stateFor(row);
      var source=clean(row.sourceUrl)?'<a class="flow-source" href="'+esc(row.sourceUrl)+'" target="_blank" rel="noopener">'+esc(row.sourceLabel||"情報源")+'を確認 ↗</a>':"";
      return '<div class="step'+(state.current?' current':'')+'"><span class="dot"></span><div class="step-head"><span class="step-title">'+esc(providerLabel(row))+'</span><span class="state">'+esc(state.label)+'</span></div><div class="period">'+esc(periodFor(row))+'</div>'+source+'</div>';
    }).join("");
    return '<details class="ticket-flow"><summary>🎫 チケット販売の流れを見る</summary><div class="flow-inner"><div class="flow-note">公式・プレイガイドで確認できた受付だけを古い順に表示します。</div><div class="timeline">'+steps+'</div><div class="unknown">この先の販売情報は未発表です。新しい受付が公式発表された場合だけ追加します。</div></div></details>';
  }

  function decorateCard(card){
    if(card.querySelector(".ticket-flow"))return;
    var rows=safeRowsForCard(card);
    if(!rows.length)return;
    var anchor=card.querySelector(".ticket-options")||card.querySelector(".no-ticket");
    if(!anchor)return;
    anchor.insertAdjacentHTML("afterend",flowHtml(rows));
  }

  function decorateAll(){
    if(!flowRowsByGroupDate)return;
    [].slice.call(cards.querySelectorAll(".card[data-performance-key]")).forEach(decorateCard);
  }

  function observe(){
    if(mounted)return;
    mounted=true;
    var queued=false;
    new MutationObserver(function(){
      if(queued)return;
      queued=true;
      window.setTimeout(function(){queued=false;decorateAll();},0);
    }).observe(cards,{childList:true});
  }

  function noStoreJson(url){
    var sep=url.indexOf("?")>=0?"&":"?";
    return fetch(url+sep+"ts="+Date.now(),{cache:"no-store"}).then(function(response){
      if(!response.ok)throw new Error("HTTP "+response.status);
      return response.json();
    });
  }

  noStoreJson(healthUrl).then(function(health){
    if(!freshHealth(health))return null;
    return noStoreJson(historyUrl);
  }).then(function(history){
    if(!history)return;
    flowRowsByGroupDate=buildIndex(history);
    observe();
    decorateAll();
  }).catch(function(){
    // Fail closed. If health/history cannot be verified, do not show a ticket flow.
  });
})();
