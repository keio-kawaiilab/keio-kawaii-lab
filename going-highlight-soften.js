(function(){
  "use strict";
  if(!document.getElementById("calendar"))return;
  if(document.querySelector("style[data-going-highlight-soften]"))return;

  var style=document.createElement("style");
  style.setAttribute("data-going-highlight-soften","");
  style.textContent=
    '.personal-going-highlight{z-index:10!important;animation:going-highlight-softened 1.8s ease-in-out infinite!important;transform-origin:center!important;will-change:transform,filter,box-shadow}'+
    '@keyframes going-highlight-softened{0%,100%{filter:brightness(1) saturate(1);transform:scale(1);box-shadow:0 1px 5px rgba(0,0,0,.10)}50%{filter:brightness(1.35) saturate(1.18);transform:scale(1.025);box-shadow:0 0 0 1px rgba(255,255,255,.9),0 0 0 3px var(--gc,var(--navy)),0 0 14px 4px var(--gc,var(--navy)),0 4px 10px rgba(0,0,0,.16)}}'+
    '@media(prefers-reduced-motion:reduce){.personal-going-highlight{animation:none!important;filter:brightness(1.10) saturate(1.05)!important;transform:none!important;box-shadow:0 0 0 2px var(--gc,var(--navy)),0 0 8px 2px var(--gc,var(--navy))!important}}';
  document.head.appendChild(style);
})();

(function(){
  "use strict";
  if(!document.getElementById("cards"))return;
  if(!document.querySelector('script[data-schedule-card-fixes]')){
    var script=document.createElement("script");
    script.src="./schedule-card-fixes.js?v=202608250246";
    script.setAttribute("data-schedule-card-fixes","");
    document.body.appendChild(script);
  }
  if(!document.querySelector('script[data-schedule-card-dedupe-v2]')){
    var dedupe=document.createElement("script");
    dedupe.src="./schedule-card-dedupe-v2.js?v=202608250220";
    dedupe.setAttribute("data-schedule-card-dedupe-v2","");
    document.body.appendChild(dedupe);
  }
})();

(function(){
  "use strict";
  if(!document.getElementById("cards"))return;
  if(document.querySelector('script[data-schedule-weather]'))return;
  var weather=document.createElement("script");
  weather.src="./schedule-weather.js?v=202608260300";
  weather.setAttribute("data-schedule-weather","");
  document.body.appendChild(weather);
})();

(function(){
  "use strict";
  if(!document.getElementById("calendar")||!document.getElementById("cards"))return;
  var version="202608300300";

  if(!document.querySelector('link[data-ticket-flow]')){
    var style=document.createElement("link");
    style.rel="stylesheet";
    style.href="./ticket-flow.css?v="+version;
    style.setAttribute("data-ticket-flow","");
    document.head.appendChild(style);
  }

  if(!document.querySelector('script[data-ticket-flow]')){
    var flow=document.createElement("script");
    flow.src="./ticket-flow.js?v="+version;
    flow.defer=true;
    flow.setAttribute("data-ticket-flow","");
    document.body.appendChild(flow);
  }

  if(!document.querySelector('script[data-ticket-flow-sync]')){
    var sync=document.createElement("script");
    sync.src="./ticket-flow-sync.js?v="+version;
    sync.defer=true;
    sync.setAttribute("data-ticket-flow-sync","");
    document.body.appendChild(sync);
  }

  if(!document.querySelector('script[data-ticket-resale-ui]')){
    var resale=document.createElement("script");
    resale.src="./ticket-resale-ui.js?v="+version;
    resale.defer=true;
    resale.setAttribute("data-ticket-resale-ui","");
    document.body.appendChild(resale);
  }
})();
