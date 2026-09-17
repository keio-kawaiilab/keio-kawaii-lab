(function(){
  "use strict";

  var calendar=document.getElementById("calendar");
  if(!calendar)return;

  var GROUPS=["FRUITS ZIPPER","CANDY TUNE","SWEET STEADY","CUTIE STREET","MORE STAR"];
  var queued=false;

  function text(value){
    return String(value==null?"":value).replace(/\s+/g," ").trim();
  }

  function titleOf(mark){
    return text(mark&&mark.title).toUpperCase();
  }

  function geometry(mark){
    return text(mark&&mark.style&&mark.style.left)+"|"+text(mark&&mark.style&&mark.style.width);
  }

  function isBenefit(mark){
    return /大特典会/.test(titleOf(mark))||/大特典会/.test(text(mark&&mark.textContent));
  }

  function isJointBenefit(mark){
    var title=titleOf(mark);
    return isBenefit(mark)&&(/合同/.test(title)||/JOINT/.test(title));
  }

  function partnerGroups(mark){
    var title=titleOf(mark);
    return GROUPS.filter(function(group){return title.indexOf(group)>=0;}).sort();
  }

  function interval(mark,week){
    var left=String(mark.style.left||"").match(/calc\(\s*([\d.]+)%/i);
    var width=String(mark.style.width||"").match(/calc\(\s*([\d.]+)%/i);
    if(left&&width){
      var start=parseFloat(left[1]);
      var span=parseFloat(width[1]);
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
    var performances=[].slice.call(week.querySelectorAll(".performance"));
    var bands=[].slice.call(week.querySelectorAll(".band"));
    var milestones=[].slice.call(week.querySelectorAll(".milestone"));
    var pstep=mobile?26:29;
    var bstep=mobile?38:44;
    var pbase=31;
    var pl=placeInLanes(performances,week,pbase,pstep);
    var bbase=pbase+pl*pstep+8;
    var bl=placeInLanes(bands,week,bbase,bstep);
    var mbase=bbase+bl*bstep+8;
    var ml=placeInLanes(milestones,week,mbase,30);
    week.style.minHeight=Math.max(105,mbase+ml*30+10)+"px";
  }

  function dedupeWeek(week){
    var marks=[].slice.call(week.querySelectorAll(".performance"));
    var joints=marks.filter(isJointBenefit);
    if(!joints.length){
      if(week.getAttribute("data-shared-benefit-deduped")==="1")repackWeek(week);
      return;
    }

    var canonical={};
    var changed=false;

    joints.forEach(function(joint){
      if(!joint.isConnected)return;
      var partners=partnerGroups(joint);
      if(partners.length<2)return;
      var geom=geometry(joint);
      if(!geom||geom==="|")return;
      var key=geom+"|"+partners.join("+");

      if(canonical[key]){
        joint.remove();
        changed=true;
        return;
      }
      canonical[key]=joint;

      marks.forEach(function(mark){
        if(mark===joint||!mark.isConnected||!isBenefit(mark)||isJointBenefit(mark))return;
        if(geometry(mark)!==geom)return;
        var markTitle=titleOf(mark);
        if(partners.some(function(group){return markTitle.indexOf(group)>=0;})){
          mark.remove();
          changed=true;
        }
      });
    });

    if(changed){
      week.setAttribute("data-shared-benefit-deduped","1");
      repackWeek(week);
    }else if(week.getAttribute("data-shared-benefit-deduped")==="1"){
      repackWeek(week);
    }
  }

  function apply(){
    queued=false;
    [].slice.call(calendar.querySelectorAll(".week")).forEach(dedupeWeek);
  }

  function queue(){
    if(queued)return;
    queued=true;
    window.requestAnimationFrame(apply);
  }

  queue();
  new MutationObserver(queue).observe(calendar,{childList:true,subtree:true});
  window.addEventListener("resize",queue,{passive:true});
})();
