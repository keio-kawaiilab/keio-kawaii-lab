(function(){
  "use strict";

  var cards=document.getElementById("cards");
  if(!cards)return;
  var queued=false;

  function clean(value){return String(value||"").replace(/\s+/g," ").trim();}

  function cardDate(card){
    var text=clean((card.querySelector(".performance-date")||{}).textContent||"");
    var match=text.match(/(\d{4})\/(\d{1,2})\/(\d{1,2})/);
    return match?[match[1],String(match[2]).padStart(2,"0"),String(match[3]).padStart(2,"0")].join("-"):"";
  }

  function provider(option){
    return clean((option.querySelector(".provider")||{}).textContent||"").toLowerCase();
  }

  function period(option){
    var copy=option.querySelector(".ticket-copy");
    return clean(copy&&copy.querySelector("small")?copy.querySelector("small").textContent:"").toLowerCase();
  }

  function normalizedUrl(option){
    var link=option.querySelector("a.ticket-link");
    if(!link||!link.href)return"";
    try{
      var url=new URL(link.href,location.href);
      url.hash="";
      var host=url.hostname.toLowerCase();
      var drop=[];
      url.searchParams.forEach(function(_value,key){
        if(/^utm_/i.test(key)||/^(fbclid|gclid|yclid|mc_cid|mc_eid)$/i.test(key))drop.push(key);
        if(/eplus\.jp$/i.test(host)&&/^p1$/i.test(key))drop.push(key);
      });
      drop.forEach(function(key){url.searchParams.delete(key);});
      var params=[];
      url.searchParams.forEach(function(value,key){params.push([key,value]);});
      params.sort(function(a,b){return a[0].localeCompare(b[0])||a[1].localeCompare(b[1]);});
      url.search="";
      params.forEach(function(pair){url.searchParams.append(pair[0],pair[1]);});
      var path=url.pathname.replace(/\/+$/,"/");
      var query=url.searchParams.toString();
      return url.protocol.toLowerCase()+"//"+host+path+(query?"?"+query:"");
    }catch(_error){return String(link.href||"").replace(/#.*$/,"");}
  }

  function strongIdentity(card,option){
    var p=provider(option),r=period(option),u=normalizedUrl(option),d=cardDate(card);
    if(!p||!r||!u)return"";
    return[d,p,r,u].join("|");
  }

  function dedupeCard(card){
    var seen={};
    [].slice.call(card.querySelectorAll(".ticket-option")).forEach(function(option){
      var key=strongIdentity(card,option);
      if(!key)return;
      if(seen[key]){option.remove();return;}
      seen[key]=true;
    });
  }

  function apply(){
    queued=false;
    [].slice.call(cards.querySelectorAll(".card")).forEach(dedupeCard);
  }

  function queue(){
    if(queued)return;
    queued=true;
    window.setTimeout(apply,25);
  }

  queue();
  new MutationObserver(queue).observe(cards,{childList:true,subtree:true});
})();
