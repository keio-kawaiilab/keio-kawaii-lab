(function(){
  "use strict";

  var root=document.getElementById("results-section");
  if(!root)return;

  function numberFrom(text,pattern){
    var match=String(text||"").match(pattern);
    return match?Number(match[1]):null;
  }

  function labelCards(){
    var cards=Array.from(root.querySelectorAll(".result-card"));
    if(!cards.length)return;

    var stats=cards.map(function(card,index){
      var meta=card.querySelector(".result-meta");
      var text=meta?meta.textContent:"";
      var duration=numberFrom(text,/(\d+)分/);
      var transfers=numberFrom(text,/乗換\s*(\d+)回/);
      return{card:card,index:index,duration:duration,transfers:transfers};
    });

    var validDurations=stats.map(function(s){return s.duration;}).filter(Number.isFinite);
    var validTransfers=stats.map(function(s){return s.transfers;}).filter(Number.isFinite);
    var fastest=validDurations.length?Math.min.apply(null,validDurations):null;
    var easiest=validTransfers.length?Math.min.apply(null,validTransfers):null;

    stats.forEach(function(stat){
      var card=stat.card;
      if(card.dataset.comparisonReady==="1")return;
      card.dataset.comparisonReady="1";
      card.classList.add("comparison-card");
      if(stat.index===0)card.classList.add("is-open");

      var head=card.querySelector(".result-head");
      var legs=card.querySelector(".route-legs");
      var warning=card.querySelector(".result-warning");
      if(!head||!legs)return;

      var badges=document.createElement("div");
      badges.className="comparison-badges";
      if(Number.isFinite(stat.duration)&&stat.duration===fastest){
        var fast=document.createElement("span");fast.className="comparison-badge badge-fast";fast.textContent="早";badges.appendChild(fast);
      }
      if(Number.isFinite(stat.transfers)&&stat.transfers===easiest){
        var easy=document.createElement("span");easy.className="comparison-badge badge-easy";easy.textContent="楽";badges.appendChild(easy);
      }
      var fare=document.createElement("span");fare.className="comparison-fare";fare.innerHTML='<b>運賃</b><strong>—</strong><small>料金未対応</small>';
      var chevron=document.createElement("span");chevron.className="comparison-chevron";chevron.setAttribute("aria-hidden","true");chevron.textContent="⌄";

      var summary=document.createElement("div");
      summary.className="comparison-summary";
      summary.appendChild(badges);
      summary.appendChild(fare);
      summary.appendChild(chevron);
      head.appendChild(summary);

      var detail=document.createElement("div");
      detail.className="comparison-detail";
      legs.parentNode.insertBefore(detail,legs);
      detail.appendChild(legs);
      if(warning)detail.appendChild(warning);

      head.setAttribute("role","button");
      head.setAttribute("tabindex","0");
      head.setAttribute("aria-expanded",stat.index===0?"true":"false");
      function toggle(){
        var open=card.classList.toggle("is-open");
        head.setAttribute("aria-expanded",open?"true":"false");
      }
      head.addEventListener("click",toggle);
      head.addEventListener("keydown",function(event){if(event.key==="Enter"||event.key===" "){event.preventDefault();toggle();}});
    });

    var list=root.querySelector(".result-list");
    if(list)list.classList.add("comparison-list");
    var header=root.querySelector(".results-header");
    if(header&&!header.querySelector(".comparison-guide")){
      var guide=document.createElement("div");
      guide.className="comparison-guide";
      guide.innerHTML='<span class="guide-fast">早</span><b>最短時間</b><span class="guide-easy">楽</span><b>乗換最少</b><span class="guide-price">安</span><b>運賃対応後に表示</b>';
      header.appendChild(guide);
    }
  }

  var observer=new MutationObserver(function(){labelCards();});
  observer.observe(root,{childList:true,subtree:true});
  labelCards();
})();
