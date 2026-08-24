(function(){
  "use strict";

  var cards=document.getElementById("cards");
  if(!cards)return;

  var loadedEvents=null;
  var officialEntries=[];
  var officialIndexLoaded=false;
  var queued=false;

  function clean(value){return String(value||"").replace(/\s+/g," ").trim();}
  function canon(value){
    return clean(value).toLowerCase()
      .replace(/^(?:🎤|📱|🎁|💿)\s*/,"")
      .replace(/\s+/g,"")
      .replace(/[!！・|｜\-–—_\[\]()（）『』「」]/g,"");
  }
  function cardDate(card){
    var text=clean((card.querySelector(".performance-date")||{}).textContent||"");
    var m=text.match(/(\d{4})\/(\d{1,2})\/(\d{1,2})/);
    return m?[m[1],String(m[2]).padStart(2,"0"),String(m[3]).padStart(2,"0")].join("-"):"";
  }
  function eventDates(event){
    var out=[];
    if(Array.isArray(event.schedule))event.schedule.forEach(function(row){if(row&&row.date)out.push(String(row.date).slice(0,10));});
    if(Array.isArray(event.eventDates))event.eventDates.forEach(function(date){if(date)out.push(String(date).slice(0,10));});
    if(event.eventDate)out.push(String(event.eventDate).slice(0,10));
    return out.filter(function(date,index,list){return date&&list.indexOf(date)===index;});
  }
  function urls(event){
    var raw=[];
    if(event.url)raw.push(event.url);
    if(Array.isArray(event.urls))raw=raw.concat(event.urls);
    return raw.filter(function(url,index,list){return url&&list.indexOf(url)===index;});
  }
  function isOfficial(url){return /https?:\/\/[^/]*asobisystem\.com\//i.test(String(url||""));}

  function indexScore(card,entry){
    var score=0;
    var eventId=card.getAttribute("data-event-id")||"";
    var title=canon((card.querySelector("h3")||{}).textContent||"");
    var got=canon(entry.title||"");
    if(eventId&&entry.representedBy===eventId)score+=1000;
    if(title&&got){
      if(title===got)score+=300;
      else if(got.indexOf(title)>=0||title.indexOf(got)>=0)score+=180;
      else{
        var tourWords=["japantour","arenatour","anniversary","生誕祭","collection"];
        if(tourWords.some(function(word){return title.indexOf(word)>=0&&got.indexOf(word)>=0;}))score+=90;
      }
    }
    if(entry.category==="LIVE")score+=20;
    if(/\/live_information\/detail\//.test(String(entry.url||"")))score+=40;
    return score;
  }

  function bestIndexedOfficialUrl(card){
    if(!officialIndexLoaded)return"";
    var group=card.getAttribute("data-group")||"";
    var date=cardDate(card);
    if(!group||!date)return"";
    var candidates=officialEntries.filter(function(entry){
      return entry&&entry.group===group&&String(entry.date||"").slice(0,10)===date&&isOfficial(entry.url);
    });
    if(!candidates.length)return"";
    var eventId=card.getAttribute("data-event-id")||"";
    var represented=eventId?candidates.filter(function(entry){return entry.representedBy===eventId;}):[];
    if(represented.length)candidates=represented;
    if(candidates.length===1)return candidates[0].url||"";
    var best="",bestScore=-Infinity;
    candidates.forEach(function(entry){
      var score=indexScore(card,entry);
      if(score>bestScore){bestScore=score;best=entry.url||"";}
    });
    return bestScore>=80?best:"";
  }

  function sourceScore(event,date,wantedTitle,url){
    var dates=eventDates(event);
    if(dates.indexOf(date)<0)return-Infinity;
    var score=0;
    var rawTitle=clean(event.displayTitle||event.eventTitle||event.title||"");
    var rawMeta=clean((event.ticketType||"")+" "+(event.title||""));
    var got=canon(rawTitle);
    if(got&&wantedTitle&&(got===wantedTitle||got.indexOf(wantedTitle)>=0||wantedTitle.indexOf(got)>=0))score+=70;
    if(String(event.sourceType||"")==="official-schedule")score+=160;
    else if(/^official/.test(String(event.sourceType||"")))score+=90;
    if(String(event.primarySource||"")==="official")score+=35;
    if(dates.length===1)score+=80;
    if(String(event.eventDate||"").slice(0,10)===date)score+=35;
    if(/\/live_information\/detail\//.test(url))score+=140;
    else if(/\/feature\//.test(url))score+=85;
    else if(/\/news\/detail\//.test(url))score+=15;
    if(/アップグレード|FC\s*(?:会員)?先行|ファンクラブ|年会費コース|月会費コース/i.test(rawMeta))score-=260;
    return score;
  }
  function legacyOfficialUrl(card){
    if(!loadedEvents)return"";
    var group=card.getAttribute("data-group")||"";
    var date=cardDate(card);
    var title=canon((card.querySelector("h3")||{}).textContent||"");
    if(!group||!date)return"";
    var best="",bestScore=-Infinity;
    loadedEvents.forEach(function(event){
      if(!event||event.group!==group)return;
      urls(event).forEach(function(url){
        if(!isOfficial(url))return;
        var score=sourceScore(event,date,title,url);
        if(score>bestScore){bestScore=score;best=url;}
      });
    });
    return bestScore>=220?best:"";
  }
  function bestOfficialUrl(card){
    var indexed=bestIndexedOfficialUrl(card);
    if(indexed)return indexed;
    // Once the authoritative per-date index has loaded, fail closed rather than
    // guessing from a tour-wide URL list. A missing correction is safer than
    // sending a user to another performance's page.
    if(officialIndexLoaded)return"";
    return legacyOfficialUrl(card);
  }

  function ticketIdentity(option){
    var provider=clean((option.querySelector(".provider")||{}).textContent||"");
    var copy=option.querySelector(".ticket-copy");
    var type="",period="";
    if(copy){
      var typeNode=copy.querySelector("b");
      if(typeNode){
        var clone=typeNode.cloneNode(true);
        [].slice.call(clone.querySelectorAll(".sale-state")).forEach(function(node){node.remove();});
        type=clean(clone.textContent||"");
      }
      period=clean((copy.querySelector("small")||{}).textContent||"");
    }
    return[provider,type,period].join("|").toLowerCase();
  }
  function dedupeOffers(card){
    var seen={};
    [].slice.call(card.querySelectorAll(".ticket-option")).forEach(function(option){
      var key=ticketIdentity(option);
      if(!key)return;
      if(seen[key]){option.remove();return;}
      seen[key]=true;
    });
  }
  function fixSource(card){
    if(card.classList.contains("release-card")||card.classList.contains("benefit-card"))return;
    var link=card.querySelector("a.src");
    if(!link)return;
    var best=bestOfficialUrl(card);
    if(!best)return;
    link.href=best;
    link.textContent="公演公式ページを確認 →";
  }
  function apply(){
    queued=false;
    [].slice.call(cards.querySelectorAll(".card")).forEach(function(card){
      dedupeOffers(card);
      fixSource(card);
    });
  }
  function queue(){
    if(queued)return;
    queued=true;
    window.setTimeout(apply,20);
  }

  var embedded=[];
  var snapshot=document.getElementById("snapshot-data");
  if(snapshot){try{embedded=(JSON.parse(snapshot.textContent||"{}").events||[]);}catch(_error){embedded=[];}}
  loadedEvents=embedded;
  queue();

  Promise.all([
    fetch("./data/live-events.json?cardfix="+Date.now(),{cache:"no-store"})
      .then(function(response){if(!response.ok)throw new Error("events");return response.json();})
      .then(function(data){loadedEvents=Array.isArray(data.events)?data.events:embedded;})
      .catch(function(){loadedEvents=embedded;}),
    fetch("./data/official-schedule-index.json?cardfix="+Date.now(),{cache:"no-store"})
      .then(function(response){if(!response.ok)throw new Error("official-index");return response.json();})
      .then(function(data){officialEntries=Array.isArray(data.entries)?data.entries:[];officialIndexLoaded=true;})
      .catch(function(){officialEntries=[];officialIndexLoaded=false;})
  ]).then(queue);

  new MutationObserver(queue).observe(cards,{childList:true,subtree:true});
})();
