(function(){
  "use strict";

  var calendar=document.getElementById("calendar");
  if(!calendar)return;
  var queued=false;

  function text(value){
    return String(value||"").replace(/\s+/g," ").trim();
  }

  function geometry(mark){
    return text(mark.style.left)+"|"+text(mark.style.width);
  }

  function bandIdentity(mark){
    var strong=mark.querySelector("strong");
    var sub=mark.querySelector("span");
    return [geometry(mark),text(strong&&strong.textContent),text(sub&&sub.textContent)].join("|");
  }

  function makeShared(mark,count){
    [].slice.call(mark.classList).forEach(function(name){
      if(/^g-/.test(name))mark.classList.remove(name);
    });
    mark.classList.add("g-LAB");
    mark.setAttribute("data-shared-band-count",String(count));
    if(mark.title&&mark.title.indexOf("複数グループ共通")<0){
      mark.title+="｜複数グループ共通";
    }
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
      makeShared(same[0],same.length);
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

  function apply(){
    queued=false;
    [].slice.call(calendar.querySelectorAll(".week")).forEach(function(week){
      dedupeBands(week);
      repackWeek(week);
    });
  }

  function queue(){
    if(queued)return;
    queued=true;
    window.setTimeout(apply,0);
  }

  queue();
  new MutationObserver(queue).observe(calendar,{childList:true,subtree:true});
  window.addEventListener("resize",queue,{passive:true});
})();
