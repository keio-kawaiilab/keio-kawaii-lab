(function(){
  "use strict";

  if(!window.__KAWAII_GA4_INSTALLED__){
    window.__KAWAII_GA4_INSTALLED__=true;
    var measurementId="G-FLWTMG3S7R";
    window.dataLayer=window.dataLayer||[];
    window.gtag=window.gtag||function(){window.dataLayer.push(arguments);};
    window.gtag("js",new Date());
    window.gtag("config",measurementId);
    var ga=document.createElement("script");
    ga.async=true;
    ga.src="https://www.googletagmanager.com/gtag/js?id="+encodeURIComponent(measurementId);
    document.head.appendChild(ga);
  }

  function load(src,marker){
    if(document.querySelector('script['+marker+']'))return;
    var script=document.createElement("script");
    script.src=src;
    script.async=false;
    script.setAttribute(marker,"");
    document.head.appendChild(script);
  }

  function placeCalendarReturnButtonAtCorner(){
    if(document.querySelector("style[data-calendar-return-placement]"))return;
    var style=document.createElement("style");
    style.setAttribute("data-calendar-return-placement","");
    style.textContent='\
.calendar-return-btn{left:auto!important;right:max(12px,env(safe-area-inset-right))!important;bottom:calc(12px + env(safe-area-inset-bottom))!important;width:auto!important;max-width:min(210px,calc(100vw - 24px))!important;min-height:42px!important;padding:9px 13px!important;font-size:12px!important;transform:translateY(18px)!important}\
.calendar-return-btn.is-visible{transform:translateY(0)!important}\
@media(max-width:620px){.calendar-return-btn{left:auto!important;right:max(10px,env(safe-area-inset-right))!important;width:auto!important;max-width:190px!important;min-height:40px!important;padding:8px 11px!important;font-size:11px!important}}';
    document.head.appendChild(style);
  }

  placeCalendarReturnButtonAtCorner();
  load("./schedule-shared-mark-dedupe.js?v=2026090621","data-schedule-shared-mark-dedupe");
  load("./schedule-weather-original.js?v=202608282355","data-schedule-weather-original");
})();
