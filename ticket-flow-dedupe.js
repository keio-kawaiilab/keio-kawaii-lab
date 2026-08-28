(function(){
  "use strict";
  var cards=document.getElementById("cards");
  if(!cards)return;

  function clean(value){
    return String(value==null?"":value).normalize("NFKC").replace(/[\s　]+/g," ").trim();
  }

  function family(step){
    var title=clean((step.querySelector(".step-title")||{}).textContent).toLowerCase();
    if(/kawaii lab\.?/.test(title)&&/(?:\bfc\b|fanclub|ファンクラブ)/i.test(title))return "kawaii-lab-fc";
    return title;
  }

  function period(step){
    return clean((step.querySelector(".period")||{}).textContent);
  }

  function source(step){
    var link=step.querySelector(".flow-source[href]");
    if(!link)return "";
    try{
      var url=new URL(link.href,location.href);
      return url.hostname.toLowerCase()+url.pathname.replace(/\/+$/g,"");
    }catch(_error){
      return clean(link.getAttribute("href"));
    }
  }

  function dedupeFlow(flow){
    var seen={};
    [].slice.call(flow.querySelectorAll(".timeline .step")).forEach(function(step){
      var fam=family(step),per=period(step),src=source(step);
      if(!fam||!per)return;
      var key=fam+"|"+per;
      if(fam!=="kawaii-lab-fc")key+="|"+src;
      if(seen[key]){
        step.remove();
      }else{
        seen[key]=true;
      }
    });
  }

  function run(){
    [].slice.call(cards.querySelectorAll(".ticket-flow")).forEach(dedupeFlow);
  }

  var queued=false;
  new MutationObserver(function(){
    if(queued)return;
    queued=true;
    setTimeout(function(){queued=false;run();},0);
  }).observe(cards,{childList:true,subtree:true});

  run();
})();
