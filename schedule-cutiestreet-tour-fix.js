(function(){
  "use strict";
  var cards=document.getElementById("cards");
  if(!cards)return;

  var TOUR_URL="https://cutiestreet.asobisystem.com/feature/autumntour";
  var START=new Date("2026-08-15T12:00:00+09:00").getTime();
  var END=new Date("2026-09-06T23:59:00+09:00").getTime();
  var PERIOD="2026/8/15 12:00 〜 2026/9/6 23:59";
  var queued=false;

  function clean(v){return String(v==null?"":v).normalize("NFKC").replace(/[\s　]+/g," ").trim();}
  function titleOf(option){
    var node=option.querySelector(".ticket-copy b");
    if(!node)return"";
    var clone=node.cloneNode(true);
    [].slice.call(clone.querySelectorAll(".sale-state")).forEach(function(x){x.remove();});
    return clean(clone.textContent);
  }
  function periodOf(option){var n=option.querySelector(".ticket-copy small");return clean(n?n.textContent:"");}
  function isTour(card){
    return clean(card.getAttribute("data-group"))==="CUTIE STREET"&&/JAPAN ARENA TOUR 2026\s*-?AUTUMN-/i.test(clean((card.querySelector("h3")||{}).textContent||""));
  }
  function removeWrongOffers(card){
    [].slice.call(card.querySelectorAll(".ticket-option")).forEach(function(option){
      var text=titleOf(option)+" "+periodOf(option);
      if((/年会費コース会員先行/.test(text)&&/(?:2026\/)?9\/(?:1|3)/.test(text))||/アップグレード抽選/.test(text))option.remove();
    });
  }
  function makeOffer(){
    var option=document.createElement("div");
    option.className="ticket-option";
    option.setAttribute("data-verified-cutie-tour-offer","1");
    var provider=document.createElement("span");
    provider.className="provider pia";
    provider.textContent="チケットぴあ";
    var copy=document.createElement("span");
    copy.className="ticket-copy";
    var b=document.createElement("b");
    b.textContent="プレイガイド最速先行";
    var state=document.createElement("span");
    state.className="sale-state open";
    state.textContent=Date.now()<START?"受付予定":"受付中";
    b.appendChild(state);
    var small=document.createElement("small");
    small.textContent=PERIOD;
    copy.appendChild(b);copy.appendChild(small);
    var link=document.createElement("a");
    link.className="ticket-link";
    link.href=TOUR_URL;
    link.target="_blank";
    link.rel="noopener";
    link.textContent="公式情報 →";
    option.appendChild(provider);option.appendChild(copy);option.appendChild(link);
    return option;
  }
  function ensureCurrentOffer(card){
    removeWrongOffers(card);
    if(Date.now()>END)return;
    var found=[].slice.call(card.querySelectorAll(".ticket-option")).some(function(o){return /プレイガイド最速先行/.test(titleOf(o));});
    if(found)return;
    var options=card.querySelector(".ticket-options");
    if(!options){
      options=document.createElement("div");options.className="ticket-options";
      var empty=card.querySelector(".no-ticket"),src=card.querySelector(".src");
      if(empty)empty.replaceWith(options);else if(src)card.insertBefore(options,src);else card.appendChild(options);
    }
    options.appendChild(makeOffer());
  }
  function ensureHistory(card){
    var flow=card.querySelector(".ticket-flow");
    if(!flow)return;
    var timeline=flow.querySelector(".timeline");
    if(!timeline){
      timeline=document.createElement("div");timeline.className="timeline";
      var inner=flow.querySelector(".flow-inner")||flow,unknown=flow.querySelector(".unknown");
      if(unknown&&unknown.parentNode)unknown.parentNode.insertBefore(timeline,unknown);else inner.appendChild(timeline);
    }
    [].slice.call(timeline.querySelectorAll(".step")).forEach(function(step){
      var t=clean((step.querySelector(".step-title")||{}).textContent||"")+" "+clean((step.querySelector(".period")||{}).textContent||"");
      if(/年会費コース会員先行/.test(t)&&/(?:2026\/)?9\/(?:1|3)/.test(t))step.remove();
    });
    var exists=[].slice.call(timeline.querySelectorAll(".step")).some(function(step){
      return /プレイガイド最速先行/.test(clean((step.querySelector(".step-title")||{}).textContent||""));
    });
    if(exists)return;
    var now=Date.now(),step=document.createElement("div");
    step.className="step"+(now>=START&&now<=END?" current":"");
    step.innerHTML='<span class="dot"></span><div class="step-head"><span class="step-title">チケットぴあ｜プレイガイド最速先行</span><span class="state">'+(now<START?'受付予定':now<=END?'受付中':'受付終了')+'</span></div><div class="period">'+PERIOD+'</div><a class="flow-source" href="'+TOUR_URL+'" target="_blank" rel="noopener">公式情報を確認 ↗</a>';
    timeline.appendChild(step);
  }
  function apply(){
    queued=false;
    [].slice.call(cards.querySelectorAll(".card")).forEach(function(card){if(isTour(card)){ensureCurrentOffer(card);ensureHistory(card);}});
  }
  function queue(){if(queued)return;queued=true;setTimeout(apply,30);}
  queue();
  new MutationObserver(queue).observe(cards,{childList:true,subtree:true});
})();
