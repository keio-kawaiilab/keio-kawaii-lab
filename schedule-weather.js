(function(){
  "use strict";

  function load(src,marker){
    if(document.querySelector('script['+marker+']'))return;
    var script=document.createElement("script");
    script.src=src;
    script.async=false;
    script.setAttribute(marker,"");
    document.head.appendChild(script);
  }

  load("./schedule-weather-original.js?v=202608270205","data-schedule-weather-original");
})();
