(function(){
  "use strict";

  var calendar=document.getElementById("calendar");
  if(!calendar)return;

  var STORAGE_KEY="kawaiiLabGoingEventsV1";
  var rangeStart=null;
  var queued=false;
  var groupClasses={
    "FRUITS ZIPPER":"g-FRUITS",
    "CANDY TUNE":"g-CANDY",
    "SWEET STEADY":"g-SWEET",
    "CUTIE STREET":"g-CUTIE",
    "MORE STAR":"g-MORE",
    "KAWAII LAB.合同":"g-LAB"
  };

  function installStyle(){
    if(document.querySelector("style[data-going-highlight-fix]"))return;
    var style=document.createElement("style");
    style.setAttribute("data-going-highlight-fix","");
    style.textContent=
      '.personal-going-highlight{z-index:12!important;animation:going-highlight-fixed 1.25s cubic-bezier(.35,0,.2,1) infinite!important;transform-origin:center!important;will-change:transform,filter,box-shadow}'+
      '@keyframes going-highlight-fixed{0%,100%{filter:brightness(1) saturate(1);transform:scale(1);box-shadow:0 1px 5px rgba(0,0,0,.12)}46%,54%{filter:brightness(1.7) saturate(1.55);transform:scale(1.08);box-shadow:0 0 0 3px rgba(255,255,255,1),0 0 0 7px var(--gc,var(--navy)),0 0 34px 12px var(--gc,var(--navy)),0 8px 20px rgba(0,0,0,.3)}}'+
      '@media(prefers-reduced-motion:reduce){.personal-going-highlight{animation:none!important;filter:brightness(1.3) saturate(1.2)!important;transform:none!important;box-shadow:0 0 0 3px #fff,0 0 0 7px var(--gc,var(--navy)),0 0 28px 10px var(--gc,var(--navy))!important}}';
    document.head.appendChild(style);
  }

  function clean(value){return String(value||"").replace(/\s+/g," ").trim();}
  function canon(value){
    return clean(value).toLowerCase().replace(/\s+/g,"").replace(/[!！・|｜\-–—_\[\]()（）『』「」]/g,"");
  }
  function parseDate(value){
    var m=String(value||"").match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if(!m)return null;
    var d=new Date(+m[1],+m[2]-1,+m[3]);
    return d.getFullYear()===+m[1]&&d.getMonth()===+m[2]-1&&d.getDate()===+m[3]?d:null;
  }
  function readEvents(){
    try{
      var value=JSON.parse(localStorage.getItem(STORAGE_KEY)||"[]");
      return Array.isArray(value)?value:[];
    }catch(_error){return[];}
  }
  function keyParts(event){
    var raw=String(event&&event.performanceKey||"");
    var parts=raw.split("|");
    if(parts.length<4)return null;
    return{group:parts[0],date:parts[1],kind:parts[2],canon:parts.slice(3).join("|")};
  }
  function resolveRangeStart(){
    var range=document.getElementById("range");
    var match=range&&String(range.textContent||"").match(/(\d{1,2})\/(\d{1,2})\s*〜/);
    if(!match)return rangeStart||new Date();
    var month=+match[1],day=+match[2];
    if(rangeStart){
      var plus=new Date(rangeStart);plus.setDate(plus.getDate()+35);
      var minus=new Date(rangeStart);minus.setDate(minus.getDate()-35);
      if(plus.getMonth()+1===month&&plus.getDate()===day){rangeStart=plus;return plus;}
      if(minus.getMonth()+1===month&&minus.getDate()===day){rangeStart=minus;return minus;}
    }
    var now=new Date(),best=null,bestDistance=Infinity;
    for(var year=now.getFullYear()-1;year<=now.getFullYear()+5;year++){
      var candidate=new Date(year,month-1,day);
      if(candidate.getMonth()+1!==month||candidate.getDate()!==day)continue;
      var distance=Math.abs(candidate-now);
      if(candidate<new Date(now.getFullYear(),now.getMonth(),now.getDate()-10))distance+=180*86400000;
      if(distance<bestDistance){best=candidate;bestDistance=distance;}
    }
    rangeStart=best||now;
    return rangeStart;
  }
  function markColumn(mark){
    var m=String(mark.style.left||"").match(/calc\(\s*([\d.]+)%/);
    if(!m)return-1;
    return Math.max(0,Math.min(6,Math.round((parseFloat(m[1])||0)*7/100)));
  }
  function markTitle(mark){return clean(String(mark.getAttribute("title")||"").replace(/｜イベント詳細$/,""));}

  function apply(){
    queued=false;
    [].slice.call(calendar.querySelectorAll(".personal-going-highlight")).forEach(function(mark){
      mark.classList.remove("personal-going-highlight");
      mark.removeAttribute("data-going-event");
    });

    var events=readEvents();
    var weeks=[].slice.call(calendar.querySelectorAll(".week"));
    if(!events.length||!weeks.length)return;

    var start=resolveRangeStart();
    var end=new Date(start);end.setDate(end.getDate()+34);
    var gridStart=new Date(start);gridStart.setDate(gridStart.getDate()-gridStart.getDay());

    events.forEach(function(event){
      var date=parseDate(event.date);
      if(!date||date<start||date>end)return;
      var delta=Math.round((date-gridStart)/86400000);
      var weekIndex=Math.floor(delta/7);
      if(weekIndex<0||weekIndex>=weeks.length)return;
      var week=weeks[weekIndex],col=date.getDay();
      var candidates=[].slice.call(week.querySelectorAll(".mark.performance"));
      var parts=keyParts(event),matches=[];

      if(event.performanceKey){
        matches=candidates.filter(function(mark){return mark.getAttribute("data-performance-key")===event.performanceKey;});
      }

      if(!matches.length){
        matches=candidates.filter(function(mark){
          if(markColumn(mark)!==col)return false;
          if(parts&&groupClasses[parts.group]&&!mark.classList.contains(groupClasses[parts.group]))return false;
          return true;
        });
        if(matches.length>1){
          var wanted=parts&&parts.canon?canon(parts.canon):canon(event.title);
          var titled=matches.filter(function(mark){
            var got=canon(markTitle(mark));
            return got&&wanted&&(got===wanted||got.indexOf(wanted)>=0||wanted.indexOf(got)>=0);
          });
          if(titled.length)matches=titled;
        }
      }

      if(!matches.length){
        var wantedTitle=canon(event.title);
        matches=candidates.filter(function(mark){
          var got=canon(markTitle(mark));
          return markColumn(mark)===col&&got&&wantedTitle&&(got===wantedTitle||got.indexOf(wantedTitle)>=0||wantedTitle.indexOf(got)>=0);
        });
      }

      matches.forEach(function(mark){
        mark.classList.add("personal-going-highlight");
        mark.setAttribute("data-going-event","true");
      });
    });
  }

  function queue(){
    if(queued)return;
    queued=true;
    window.setTimeout(apply,20);
  }

  installStyle();
  queue();
  new MutationObserver(queue).observe(calendar,{childList:true});
  var range=document.getElementById("range");
  if(range)new MutationObserver(queue).observe(range,{childList:true,characterData:true,subtree:true});
  document.addEventListener("click",function(event){
    if(event.target.closest(".personal-card-add")||event.target.closest(".personal-remove"))window.setTimeout(apply,60);
  });
  window.addEventListener("storage",function(event){if(event.key===STORAGE_KEY)queue();});
})();
