(function(){
  "use strict";

  if(!document.getElementById("cards"))return;

  var AREA_URL="https://www.jma.go.jp/bosai/common/const/area.json";
  var FORECAST_BASE="https://www.jma.go.jp/bosai/forecast/data/forecast/";
  var SOURCE_URL="https://www.jma.go.jp/bosai/forecast/";
  var CACHE_TTL=20*60*1000;
  var HORIZON_DAYS=7;
  var officeForecastCache={};

  if(!document.querySelector('link[data-schedule-weather]')){
    var style=document.createElement("link");
    style.rel="stylesheet";
    style.href="./schedule-weather.css?v=202608260300";
    style.setAttribute("data-schedule-weather","");
    document.head.appendChild(style);
  }

  function esc(value){
    return String(value==null?"":value)
      .replace(/&/g,"&amp;")
      .replace(/</g,"&lt;")
      .replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;");
  }

  function pad(value){return String(value).padStart(2,"0");}

  function localDate(date){
    return date.getFullYear()+"-"+pad(date.getMonth()+1)+"-"+pad(date.getDate());
  }

  function addDays(date,days){
    return new Date(date.getFullYear(),date.getMonth(),date.getDate()+days);
  }

  function parseCardDate(card){
    var node=card.querySelector(".performance-date");
    var match=String(node&&node.textContent||"").match(/(20\d{2})\/(\d{1,2})\/(\d{1,2})/);
    if(!match)return"";
    return match[1]+"-"+pad(match[2])+"-"+pad(match[3]);
  }

  function metaItem(card,label){
    var items=[].slice.call(card.querySelectorAll(".meta > div"));
    return items.find(function(item){
      var b=item.querySelector("b");
      return b&&b.textContent.trim()===label;
    })||null;
  }

  function parseCardVenue(card){
    var item=metaItem(card,"会場");
    if(!item)return"";
    var link=item.querySelector("a.venue-link");
    if(link){
      try{
        var url=new URL(link.getAttribute("href")||"",location.href);
        var name=url.searchParams.get("name");
        if(name)return name;
      }catch(_error){}
    }
    var clone=item.cloneNode(true);
    var b=clone.querySelector("b");
    if(b)b.remove();
    return clone.textContent.trim();
  }

  function parseCardStartTime(card){
    var item=metaItem(card,"開催日時");
    var text=String(item&&item.textContent||"");
    var match=text.match(/(?:開演|開始)\s*(\d{1,2}):(\d{2})/);
    if(!match)return null;
    return Number(match[1])*60+Number(match[2]);
  }

  function normalizeVenue(value){
    return String(value||"")
      .normalize("NFKC")
      .replace(/^(北海道|東京都|京都府|大阪府|.{2,3}県)[\s　]*/,"")
      .replace(/[\s　・･]/g,"")
      .replace(/(?:メイン)?大ホール|劇場棟/g,"")
      .replace(/[()（）]/g,"")
      .toLowerCase();
  }

  function resolveVenue(name,venues){
    var requested=normalizeVenue(name);
    if(!requested)return null;
    return venues.find(function(venue){
      return[venue.name].concat(venue.aliases||[]).some(function(candidate){
        var key=normalizeVenue(candidate);
        return key&&(requested===key||requested.indexOf(key)>=0||key.indexOf(requested)>=0);
      });
    })||null;
  }

  function cachedJson(key,url){
    try{
      var raw=sessionStorage.getItem(key);
      if(raw){
        var cached=JSON.parse(raw);
        if(cached&&Date.now()-cached.savedAt<CACHE_TTL)return Promise.resolve(cached.data);
      }
    }catch(_error){}
    return fetch(url,{cache:"no-store"}).then(function(response){
      if(!response.ok)throw new Error("weather fetch failed: "+response.status);
      return response.json();
    }).then(function(data){
      try{sessionStorage.setItem(key,JSON.stringify({savedAt:Date.now(),data:data}));}catch(_error){}
      return data;
    });
  }

  function officeCodeForPrefecture(prefecture,areaMap){
    var offices=areaMap.offices||{};
    return Object.keys(offices).find(function(code){
      return offices[code]&&offices[code].name===prefecture;
    })||"";
  }

  function class10ForVenue(venue,areaMap,officeCode){
    var address=String(venue.address||"");
    var class20s=areaMap.class20s||{};
    var class15s=areaMap.class15s||{};
    var class10s=areaMap.class10s||{};
    var candidates=[];

    Object.keys(class20s).forEach(function(code){
      var area=class20s[code];
      if(!area||!area.name||address.indexOf(area.name)<0)return;
      var p15=class15s[area.parent];
      var p10=p15&&class10s[p15.parent];
      if(!p10||p10.parent!==officeCode)return;
      candidates.push({code:p15.parent,name:area.name.length});
    });

    candidates.sort(function(a,b){return b.name-a.name;});
    if(candidates.length)return candidates[0].code;

    var office=(areaMap.offices||{})[officeCode];
    return office&&Array.isArray(office.children)&&office.children[0]||"";
  }

  function areaIndex(series,class10Code){
    var areas=series&&Array.isArray(series.areas)?series.areas:[];
    var exact=areas.findIndex(function(item){return item.area&&item.area.code===class10Code;});
    return exact;
  }

  function weatherLabel(code,raw){
    var text=String(raw||"").replace(/[\s　]+/g," ").trim();
    if(text)return text;
    var labels={
      "100":"晴れ","101":"晴れ時々くもり","102":"晴れ一時雨","103":"晴れ時々雨","104":"晴れ一時雪","105":"晴れ時々雪","106":"晴れ一時雨か雪","107":"晴れ時々雨か雪","108":"晴れ一時雨か雷雨","110":"晴れのち時々くもり","111":"晴れのちくもり","112":"晴れのち一時雨","113":"晴れのち時々雨","114":"晴れのち雨","115":"晴れのち一時雪","116":"晴れのち時々雪","117":"晴れのち雪","118":"晴れのち雨か雪","119":"晴れのち雨か雷雨","120":"晴れ朝夕一時雨","121":"晴れ朝の内一時雨","122":"晴れ夕方一時雨","123":"晴れ山沿い雷雨","124":"晴れ山沿い雪","125":"晴れ午後は雷雨","126":"晴れ昼頃から雨","127":"晴れ夕方から雨","128":"晴れ夜は雨","130":"朝の内霧のち晴れ","131":"晴れ明け方霧","132":"晴れ朝夕くもり","140":"晴れ時々雨で雷を伴う",
      "200":"くもり","201":"くもり時々晴れ","202":"くもり一時雨","203":"くもり時々雨","204":"くもり一時雪","205":"くもり時々雪","206":"くもり一時雨か雪","207":"くもり時々雨か雪","208":"くもり一時雨か雷雨","209":"霧","210":"くもりのち時々晴れ","211":"くもりのち晴れ","212":"くもりのち一時雨","213":"くもりのち時々雨","214":"くもりのち雨","215":"くもりのち一時雪","216":"くもりのち時々雪","217":"くもりのち雪","218":"くもりのち雨か雪","219":"くもりのち雨か雷雨","220":"くもり朝夕一時雨","221":"くもり朝の内一時雨","222":"くもり夕方一時雨","223":"くもり日中時々晴れ","224":"くもり昼頃から雨","225":"くもり夕方から雨","226":"くもり夜は雨","228":"くもり昼頃から雪","229":"くもり夕方から雪","230":"くもり夜は雪","231":"くもり海上海岸は霧か霧雨","240":"くもり時々雨で雷を伴う","250":"くもり時々雪で雷を伴う",
      "300":"雨","301":"雨時々晴れ","302":"雨時々止む","303":"雨時々雪","304":"雨か雪","306":"大雨","308":"雨で暴風を伴う","309":"雨一時雪","311":"雨のち晴れ","313":"雨のちくもり","314":"雨のち時々雪","315":"雨のち雪","316":"雨か雪のち晴れ","317":"雨か雪のちくもり","320":"朝の内雨のち晴れ","321":"朝の内雨のちくもり","322":"雨朝晩一時雪","323":"雨昼頃から晴れ","324":"雨夕方から晴れ","325":"雨夜は晴れ","326":"雨夕方から雪","327":"雨夜は雪","328":"雨一時強く降る","329":"雨一時みぞれ","340":"雪か雨","350":"雨で雷を伴う",
      "400":"雪","401":"雪時々晴れ","402":"雪時々止む","403":"雪時々雨","405":"大雪","406":"風雪強い","407":"暴風雪","409":"雪一時雨","411":"雪のち晴れ","413":"雪のちくもり","414":"雪のち雨","420":"朝の内雪のち晴れ","421":"朝の内雪のちくもり","422":"雪昼頃から雨","423":"雪夕方から雨","425":"雪一時強く降る","426":"雪のちみぞれ","427":"雪一時みぞれ","450":"雪で雷を伴う"
    };
    return labels[String(code||"")]||({"1":"晴れ","2":"くもり","3":"雨","4":"雪"}[String(code||"").charAt(0)]||"天気予報");
  }

  function iconFor(code,label){
    var text=String(label||"");
    if(/雷/.test(text))return"⛈️";
    if(/雪/.test(text)&&/雨/.test(text))return"🌨️";
    if(/雪/.test(text))return"❄️";
    if(/雨/.test(text)&&/晴/.test(text))return"🌦️";
    if(/雨/.test(text))return"🌧️";
    if(/晴/.test(text)&&/くも|曇/.test(text))return"🌤️";
    if(/晴/.test(text))return"☀️";
    if(/くも|曇/.test(text))return"☁️";
    return{"1":"☀️","2":"☁️","3":"🌧️","4":"❄️"}[String(code||"").charAt(0)]||"🌤️";
  }

  function sameDate(iso,date){return String(iso||"").slice(0,10)===date;}

  function shortForecast(report,class10Code,date,startMinutes){
    if(!report||!Array.isArray(report.timeSeries))return null;
    var weatherSeries=report.timeSeries[0];
    var wi=areaIndex(weatherSeries,class10Code);
    if(wi<0)return null;
    var weatherArea=weatherSeries.areas[wi];
    var wIndex=(weatherSeries.timeDefines||[]).findIndex(function(x){return sameDate(x,date);});
    if(wIndex<0)return null;
    var code=(weatherArea.weatherCodes||[])[wIndex]||"";
    var raw=(weatherArea.weathers||[])[wIndex]||"";
    var result={
      areaName:weatherArea.area&&weatherArea.area.name||"",
      code:code,
      label:weatherLabel(code,raw),
      min:null,
      max:null,
      pop:null,
      popLabel:""
    };

    var tempSeries=report.timeSeries[2];
    if(tempSeries&&Array.isArray(tempSeries.areas)&&tempSeries.areas[wi]){
      var values=[];
      (tempSeries.timeDefines||[]).forEach(function(time,index){
        if(!sameDate(time,date))return;
        var value=Number((tempSeries.areas[wi].temps||[])[index]);
        if(Number.isFinite(value))values.push(value);
      });
      if(values.length){
        result.min=Math.min.apply(Math,values);
        result.max=Math.max.apply(Math,values);
      }
    }

    var popSeries=report.timeSeries[1];
    var pi=areaIndex(popSeries,class10Code);
    if(pi>=0){
      var candidates=[];
      (popSeries.timeDefines||[]).forEach(function(time,index){
        if(!sameDate(time,date))return;
        var d=new Date(time);
        var mins=d.getHours()*60+d.getMinutes();
        var value=(popSeries.areas[pi].pops||[])[index];
        if(value!==""&&value!=null)candidates.push({mins:mins,value:String(value)});
      });
      if(candidates.length){
        var chosen=null;
        if(startMinutes!=null){
          candidates.forEach(function(item){if(item.mins<=startMinutes)chosen=item;});
          if(!chosen)chosen=candidates[0];
          var end=(chosen.mins+6*60)%(24*60);
          result.pop=chosen.value;
          result.popLabel=pad(Math.floor(chosen.mins/60))+"〜"+pad(Math.floor(end/60))+"時";
        }else{
          chosen=candidates.reduce(function(best,item){return Number(item.value)>Number(best.value)?item:best;},candidates[0]);
          result.pop=chosen.value;
          result.popLabel="日中最大";
        }
      }
    }
    return result;
  }

  function weeklyForecast(report,class10Code,date){
    if(!report||!Array.isArray(report.timeSeries))return null;
    var weatherSeries=report.timeSeries[0];
    var wi=areaIndex(weatherSeries,class10Code);
    if(wi<0)return null;
    var index=(weatherSeries.timeDefines||[]).findIndex(function(x){return sameDate(x,date);});
    if(index<0)return null;
    var weatherArea=weatherSeries.areas[wi];
    var code=(weatherArea.weatherCodes||[])[index]||"";
    var result={
      areaName:weatherArea.area&&weatherArea.area.name||"",
      code:code,
      label:weatherLabel(code,""),
      min:null,
      max:null,
      pop:(weatherArea.pops||[])[index]||null,
      popLabel:"1日"
    };
    var tempSeries=report.timeSeries[1];
    if(tempSeries&&Array.isArray(tempSeries.areas)&&tempSeries.areas[wi]){
      var tempArea=tempSeries.areas[wi];
      var min=Number((tempArea.tempsMin||[])[index]);
      var max=Number((tempArea.tempsMax||[])[index]);
      if(Number.isFinite(min))result.min=min;
      if(Number.isFinite(max))result.max=max;
    }
    return result;
  }

  function forecastFor(officeCode,class10Code,date,startMinutes){
    if(!officeForecastCache[officeCode]){
      officeForecastCache[officeCode]=cachedJson(
        "kawaii-weather-forecast-"+officeCode,
        FORECAST_BASE+encodeURIComponent(officeCode)+".json"
      );
    }
    return officeForecastCache[officeCode].then(function(payload){
      var short=shortForecast(payload&&payload[0],class10Code,date,startMinutes);
      if(short)return short;
      return weeklyForecast(payload&&payload[1],class10Code,date);
    });
  }

  function weatherHtml(data,updatedAt){
    var temps="";
    if(data.max!=null)temps+='<span class="schedule-weather-high">最高 '+esc(data.max)+'℃</span>';
    if(data.min!=null)temps+='<span class="schedule-weather-low">最低 '+esc(data.min)+'℃</span>';
    var pop=data.pop!=null?'<span class="schedule-weather-pop">☔ '+esc(data.popLabel||"降水確率")+' '+esc(data.pop)+'%</span>':"";
    return '<section class="schedule-weather" aria-label="公演日の天気">'+
      '<div class="schedule-weather-head"><div><small>当日の天気</small><strong>'+esc(data.areaName||"気象庁予報区域")+'</strong></div><span>'+esc(updatedAt||"")+'</span></div>'+
      '<div class="schedule-weather-main"><span class="schedule-weather-icon" aria-hidden="true">'+iconFor(data.code,data.label)+'</span><strong class="schedule-weather-condition">'+esc(data.label)+'</strong><div class="schedule-weather-temps">'+temps+'</div></div>'+
      (pop?'<div class="schedule-weather-sub">'+pop+'</div>':"")+
      '<a class="schedule-weather-source" href="'+SOURCE_URL+'" target="_blank" rel="noopener">出典：気象庁 ↗</a>'+
      '</section>';
  }

  function inHorizon(date){
    var today=new Date();
    today=new Date(today.getFullYear(),today.getMonth(),today.getDate());
    var target=new Date(date+"T00:00:00");
    return target>=today&&target<=addDays(today,HORIZON_DAYS);
  }

  function mountCard(card,venues,areaMap){
    if(card.querySelector(".schedule-weather"))return Promise.resolve();
    var date=parseCardDate(card);
    if(!date||!inHorizon(date))return Promise.resolve();
    var venueName=parseCardVenue(card);
    if(!venueName||/オンライン|未定|複数会場/.test(venueName))return Promise.resolve();
    var venue=resolveVenue(venueName,venues);
    if(!venue||!venue.prefecture)return Promise.resolve();
    var officeCode=officeCodeForPrefecture(venue.prefecture,areaMap);
    if(!officeCode)return Promise.resolve();
    var class10Code=class10ForVenue(venue,areaMap,officeCode);
    if(!class10Code)return Promise.resolve();
    var startMinutes=parseCardStartTime(card);

    return forecastFor(officeCode,class10Code,date,startMinutes).then(function(data){
      if(!data||card.querySelector(".schedule-weather"))return;
      var meta=card.querySelector(".meta");
      if(!meta)return;
      var now=new Date();
      var stamp=pad(now.getHours())+":"+pad(now.getMinutes())+"取得";
      meta.insertAdjacentHTML("afterend",weatherHtml(data,stamp));
    }).catch(function(){
      // 気象庁データを取得できない場合は何も表示しない。既存カードを壊さない。
    });
  }

  function mountAll(venues,areaMap){
    var cards=[].slice.call(document.querySelectorAll("#cards .card"));
    return Promise.all(cards.map(function(card){return mountCard(card,venues,areaMap);}));
  }

  function observe(venues,areaMap){
    var root=document.getElementById("cards");
    if(!root)return;
    var queued=false;
    var observer=new MutationObserver(function(){
      if(queued)return;
      queued=true;
      setTimeout(function(){queued=false;mountAll(venues,areaMap);},0);
    });
    observer.observe(root,{childList:true,subtree:true});
  }

  Promise.all([
    cachedJson("kawaii-weather-venues","./data/venues.json"),
    cachedJson("kawaii-weather-area-map",AREA_URL)
  ]).then(function(values){
    var venues=values[0]&&values[0].venues||[];
    var areaMap=values[1]||{};
    mountAll(venues,areaMap);
    observe(venues,areaMap);
  }).catch(function(){
    // 取得失敗時は天気欄を出さず、従来ページをそのまま表示する。
  });

  window.KawaiiScheduleWeather={
    normalizeVenue:normalizeVenue,
    resolveVenue:resolveVenue,
    weatherLabel:weatherLabel,
    shortForecast:shortForecast,
    weeklyForecast:weeklyForecast
  };
})();
