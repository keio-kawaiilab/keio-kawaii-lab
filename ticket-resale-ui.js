(function(){
  "use strict";
  var cards=document.getElementById("cards");
  if(!cards)return;

  function clean(value){return String(value==null?"":value).normalize("NFKC").trim();}

  function decorateOption(option){
    var copy=option.querySelector(".ticket-copy b");
    var provider=option.querySelector(".provider");
    var link=option.querySelector(".ticket-link");
    var state=option.querySelector(".sale-state");
    var text=clean((copy&&copy.textContent)||"")+" "+clean((provider&&provider.textContent)||"");
    if(!/リセール|resale/i.test(text))return;

    option.classList.add("resale-ticket-option");
    if(provider){
      provider.textContent="公式リセール";
      provider.classList.add("resale");
    }
    if(link)link.textContent="リセールページ →";
    if(state){
      var label=clean(state.textContent);
      if(label==="受付終了")state.textContent="リセール終了";
      else if(/受付中/.test(label))state.textContent="リセール受付中";
      else if(/予定/.test(label))state.textContent="リセール予定";
    }
  }

  function run(){
    Array.prototype.slice.call(cards.querySelectorAll(".ticket-option")).forEach(decorateOption);
  }

  var queued=false;
  new MutationObserver(function(){
    if(queued)return;
    queued=true;
    setTimeout(function(){queued=false;run();},0);
  }).observe(cards,{childList:true,subtree:true});

  run();
})();
