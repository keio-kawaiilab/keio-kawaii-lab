(function(){
  "use strict";
  var cards=document.getElementById("cards");
  if(!cards)return;

  if(!document.querySelector("style[data-ticket-resale-ui]")){
    var style=document.createElement("style");
    style.setAttribute("data-ticket-resale-ui","");
    style.textContent=
      '.ticket-option .provider.resale{background:#2d7d62!important}'+
      '.resale-ticket-option{border-color:#cfe5dc!important;background:#f8fcfa!important}'+
      '.ticket-flow .step.resale .dot{border-color:#2d7d62!important}'+
      '.ticket-flow .step.resale.current .dot{background:#2d7d62!important;box-shadow:0 0 0 6px #e0f2ea!important}';
    document.head.appendChild(style);
  }

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

  function decorateStep(step){
    var title=step.querySelector(".step-title");
    if(!title||!/リセール|resale/i.test(clean(title.textContent)))return;
    step.classList.add("resale");
    title.textContent="♻️ 公式リセール";
    var state=step.querySelector(".state");
    if(state){
      var label=clean(state.textContent);
      if(label==="受付終了")state.textContent="リセール終了";
      else if(label==="受付中"||label==="受付中・予定")state.textContent="リセール受付中";
      else if(label==="受付予定")state.textContent="リセール予定";
    }
    var source=step.querySelector(".flow-source");
    if(source)source.textContent="公式リセール案内を確認 ↗";
  }

  function run(){
    Array.prototype.slice.call(cards.querySelectorAll(".ticket-option")).forEach(decorateOption);
    Array.prototype.slice.call(cards.querySelectorAll(".ticket-flow .step")).forEach(decorateStep);
  }

  var queued=false;
  new MutationObserver(function(){
    if(queued)return;
    queued=true;
    setTimeout(function(){queued=false;run();},0);
  }).observe(cards,{childList:true,subtree:true});

  run();
})();
