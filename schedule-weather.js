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

  load("./schedule-shared-mark-dedupe.js?v=202608301149","data-schedule-shared-mark-dedupe");
  load("./schedule-weather-original.js?v=202608282355","data-schedule-weather-original");
})();
