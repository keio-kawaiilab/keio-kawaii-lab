(function(){
  "use strict";

  var calendar=document.getElementById("calendar");
  if(!calendar)return;
  var cards=document.getElementById("cards");
  var queued=false;

  function text(value){
    return String(value||"").replace(/\s+/g," ").trim();
  }

  function geometry(mark){
    return text(mark.style.left)+"|"+text(mark.style.width);
  }

  function attribute(mark,name){
    return text(mark.getAttribute&&mark.getAttribute(name));
  }

  function groupClass(mark){
    return [].slice.call(mark.classList).filter(function(name){
      return /^g-/.test(name);
    }).sort().join(",");
  }

  function bandIdentity(mark){
    var strong=mark.querySelector("strong");
    var sub=mark.querySelector("span");
    return [
      attribute(mark,"data-band-group")||groupClass(mark),
      attribute(mark,"data-band-provider"),
      attribute(mark,"data-band-ticket-type"),
      attribute(mark,"data-band-apply-start"),
      attribute(mark,"data-band-apply-end"),
      geometry(mark),
      text(strong&&strong.textContent),
      text(sub&&sub.textContent)
    ].join("|");
  }

  function markDeduped(mark,count){
    mark.setAttribute("data-shared-band-count",String(count));
  }

  function dedupeBands(week){
    var groups={};
    [].slice.call(week.querySelectorAll(".band")).forEach(function(mark){
      var key=bandIdentity(mark);
      (groups[key]||(groups[key]=[])).push(mark);
    });
    Object.keys(groups).forEach(function(key){
      var same=groups[key];
      if(same.length<2)return;
      markDeduped(same[0],same.length);
      same.slice(1).forEach(function(mark){mark.remove();});
    });
  }

  function interval(mark,week){
    var left=String(mark.style.left||"").match(/calc\(\s*([\d.]+)%/i);
    var width=String(mark.style.width||"").match(/calc\(\s*([\d.]+)%/i);
    if(left&&width){
      var start=parseFloat(left[1]),span=parseFloat(width[1]);
      return{start:start,end:start+span};
    }
    var ww=week.clientWidth||1;
    return{start:mark.offsetLeft/ww*100,end:(mark.offsetLeft+mark.offsetWidth)/ww*100};
  }

  function placeInLanes(nodes,week,base,step){
    var items=nodes.map(function(mark){
      var x=interval(mark,week);
      return{mark:mark,start:x.start,end:x.end};
    }).sort(function(a,b){return a.start-b.start||a.end-b.end;});
    var ends=[];
    items.forEach(function(item){
      var lane=0;
      while(lane<ends.length&&item.start<ends[lane]-0.0001)lane++;
      item.mark.style.top=(base+lane*step)+"px";
      ends[lane]=item.end;
    });
    return ends.length;
  }

  function repackWeek(week){
    var mobile=window.matchMedia&&window.matchMedia("(max-width:620px)").matches;
    var performance=[].slice.call(week.querySelectorAll(".performance"));
    var bands=[].slice.call(week.querySelectorAll(".band"));
    var milestones=[].slice.call(week.querySelectorAll(".milestone"));
    var pstep=mobile?26:29,bstep=mobile?38:44,pbase=31;
    var pl=placeInLanes(performance,week,pbase,pstep);
    var bbase=pbase+pl*pstep+8;
    var bl=placeInLanes(bands,week,bbase,bstep);
    var mbase=bbase+bl*bstep+8;
    var ml=placeInLanes(milestones,week,mbase,30);
    week.style.minHeight=Math.max(105,mbase+ml*30+10)+"px";
  }

  function cardDate(card){
    var dateText=text((card.querySelector(".performance-date")||{}).textContent||"");
    var match=dateText.match(/(\d{4})\/(\d{1,2})\/(\d{1,2})/);
    if(match)return match[1]+"-"+String(match[2]).padStart(2,"0")+"-"+String(match[3]).padStart(2,"0");
    return"";
  }

  function cardTime(card){
    var meta=text((card.querySelector(".meta")||{}).textContent||"");
    var match=meta.match(/(?:開演|開始)\s*(\d{1,2}):(\d{2})/);
    return match?String(Number(match[1])).padStart(2,"0")+":"+match[2]:"";
  }

  function cardTitle(card){
    return text((card.querySelector("h3")||{}).textContent||"")
      .toLowerCase()
      .replace(/20\d{2}/g,"")
      .replace(/candy tune|cutie street|sweet steady|fruits zipper|more star/g,"")
      .replace(/アップグレード/g,"")
      .replace(/抽選/g,"")
      .replace(/受付/g,"")
      .replace(/お知らせ/g,"")
      .replace(/チケット/g,"")
      .replace(/年会費コース会員先行|月会費コース会員先行|fc先行|ファンクラブ先行/g,"")
      .replace(/[\s　!！・|｜\-–—_【】\[\]()（）『』「」<>＜＞:：./~〜～]/g,"");
  }

  function sameCard(a,b){
    var ag=text(a.getAttribute("data-group")).toUpperCase();
    var bg=text(b.getAttribute("data-group")).toUpperCase();
    var ad=cardDate(a),bd=cardDate(b);
    if(!ag||!ad||ag!==bg||ad!==bd)return false;
    var at=cardTime(a),bt=cardTime(b);
    if(at&&bt)return at===bt;
    var aa=cardTitle(a),bb=cardTitle(b);
    if(!aa||!bb)return false;
    return aa===bb||(aa.length>=5&&bb.indexOf(aa)>=0)||(bb.length>=5&&aa.indexOf(bb)>=0);
  }

  function cardScore(card){
    var score=0;
    var title=text((card.querySelector("h3")||{}).textContent||"");
    var date=cardDate(card);
    var yearMatch=title.match(/20\d{2}/);
    if(yearMatch&&date)score+=yearMatch[0]===date.slice(0,4)?100:-500;
    if(!/アップグレード|先行|受付|チケット/.test(title))score+=60;
    var source=card.querySelector("a.src");
    if(source&&/\/live_information\/detail\//.test(source.href||""))score+=120;
    if(cardTime(card))score+=20;
    return score;
  }

  function ticketKey(option){
    var provider=text((option.querySelector(".provider")||{}).textContent||"");
    var copy=option.querySelector(".ticket-copy");
    var period=text(copy&&copy.querySelector("small")?copy.querySelector("small").textContent:"");
    var link=option.querySelector("a.ticket-link");
    return(provider+"|"+period+"|"+text(link&&link.href)).toLowerCase();
  }

  function dedupeOptions(card){
    var seen={};
    [].slice.call(card.querySelectorAll(".ticket-option")).forEach(function(option){
      var key=ticketKey(option);
      if(seen[key])option.remove();
      else seen[key]=true;
    });
  }

  function mergeCard(target,source){
    var targetOptions=target.querySelector(".ticket-options");
    var sourceOptions=source.querySelector(".ticket-options");
    if(sourceOptions){
      if(!targetOptions){
        targetOptions=document.createElement("div");
        targetOptions.className="ticket-options";
        var noTicket=target.querySelector(".no-ticket");
        if(noTicket)noTicket.replaceWith(targetOptions);
        else target.appendChild(targetOptions);
      }
      [].slice.call(sourceOptions.querySelectorAll(".ticket-option")).forEach(function(option){
        targetOptions.appendChild(option.cloneNode(true));
      });
    }
    dedupeOptions(target);
  }

  function dedupeCards(){
    if(!cards)return;
    var kept=[];
    [].slice.call(cards.querySelectorAll(".card")).forEach(function(card){
      dedupeOptions(card);
      var found=-1;
      for(var i=0;i<kept.length;i++){
        if(sameCard(kept[i],card)){found=i;break;}
      }
      if(found<0){kept.push(card);return;}
      var old=kept[found];
      if(cardScore(card)>cardScore(old)){
        mergeCard(card,old);
        old.remove();
        kept[found]=card;
      }else{
        mergeCard(old,card);
        card.remove();
      }
    });
    var summary=document.getElementById("summary");
    if(summary){
      var suffix=/（[^）]+）/.exec(summary.textContent||"");
      summary.textContent=cards.querySelectorAll(".card").length+"イベントを掲載中"+(suffix?suffix[0]:"");
    }
  }

  function apply(){
    queued=false;
    [].slice.call(calendar.querySelectorAll(".week")).forEach(function(week){
      dedupeBands(week);
      repackWeek(week);
    });
    dedupeCards();
  }

  function queue(){
    if(queued)return;
    queued=true;
    window.setTimeout(apply,0);
  }

  queue();
  new MutationObserver(queue).observe(calendar,{childList:true,subtree:true});
  if(cards)new MutationObserver(queue).observe(cards,{childList:true,subtree:true});
  window.addEventListener("resize",queue,{passive:true});
})();
