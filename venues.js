(function(){
  "use strict";

  var list=document.getElementById("venue-list");
  if(!list)return;

  var search=document.getElementById("venue-search");
  var statusFilter=document.getElementById("venue-status-filter");
  var regionFilter=document.getElementById("venue-region-filter");
  var sortSelect=document.getElementById("venue-sort");
  var resetButton=document.getElementById("venue-reset");
  var count=document.getElementById("venue-count");
  var typeButtons=[].slice.call(document.querySelectorAll("[data-venue-type]"));
  var allVenues=[];
  var activeType="all";
  var today=localDate(new Date());

  function esc(value){
    return String(value==null?"":value)
      .replace(/&/g,"&amp;")
      .replace(/</g,"&lt;")
      .replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;");
  }

  function localDate(date){
    return [
      date.getFullYear(),
      String(date.getMonth()+1).padStart(2,"0"),
      String(date.getDate()).padStart(2,"0")
    ].join("-");
  }

  function fmtDate(value){
    var m=String(value||"").match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m?(+m[2])+"/"+(+m[3]):"日程未定";
  }

  function stripAddress(value){
    return String(value||"").replace(/[（(][^）)]*(?:都|道|府|県|市|区|〒|\d{3}-\d)[^）)]*[）)]/g,"");
  }

  function normalize(value){
    return stripAddress(value)
      .replace(/\u00a0/g," ")
      .replace(/^(北海道|東京都|京都府|大阪府|.{2,3}県)[\s　]*/,"")
      .replace(/[\s　・･]/g,"")
      .replace(/(?:メイン)?大ホール|劇場棟/g,"")
      .toLowerCase();
  }

  function prefectureOf(value){
    var m=String(value||"").match(/北海道|東京都|京都府|大阪府|青森県|岩手県|宮城県|秋田県|山形県|福島県|茨城県|栃木県|群馬県|埼玉県|千葉県|神奈川県|新潟県|富山県|石川県|福井県|山梨県|長野県|岐阜県|静岡県|愛知県|三重県|滋賀県|兵庫県|奈良県|和歌山県|鳥取県|島根県|岡山県|広島県|山口県|徳島県|香川県|愛媛県|高知県|福岡県|佐賀県|長崎県|熊本県|大分県|宮崎県|鹿児島県|沖縄県/);
    if(m)return m[0];
    var text=String(value||"");
    if(/日本武道館|有明|東京ガーデン|Zepp Haneda|Zepp DiverCity|LINE CUBE|代々木|豊洲|Spotify O-/.test(text))return"東京都";
    if(/ぴあアリーナ|横浜|カルッツ|よこすか|厚木|KT Zepp/.test(text))return"神奈川県";
    if(/松戸|幕張/.test(text))return"千葉県";
    if(/戸田|大宮/.test(text))return"埼玉県";
    return"所在地確認中";
  }

  function cleanName(value){
    return stripAddress(value)
      .replace(/\u00a0/g," ")
      .replace(/^(北海道|東京都|京都府|大阪府|.{2,3}県)[\s　]*/,"")
      .trim()||String(value||"会場");
  }

  function venueType(value){
    var text=String(value||"");
    if(/アリーナ|体育館|ドーム|メッセ|A館|ワールド記念|グリーンアリーナ|IGアリーナ|スーパーアリーナ/.test(text))return"アリーナ";
    if(/ライブハウス|Zepp|PIT|Spotify|O-EAST|WWW|LIQUIDROOM/.test(text))return"ライブハウス";
    if(/ホール|会館|劇場|サンプラザ|サンパレス|グランシアタ/.test(text))return"ホール";
    return"その他";
  }

  function venueScale(type,value){
    if(type==="アリーナ")return"大規模";
    if(type==="ライブハウス")return"中規模";
    if(/大ホール|メインホール|フォレストホール|hitaru/.test(String(value||"")))return"大規模ホール";
    if(type==="ホール")return"ホール";
    return"規模確認中";
  }

  function occurrences(event){
    var rows=[];
    if(Array.isArray(event.schedule)&&event.schedule.length){
      event.schedule.forEach(function(item){
        if(item&&item.venue&&!/オンライン|複数会場/.test(item.venue)){
          rows.push({date:String(item.date||event.eventDate||"").slice(0,10),venue:item.venue});
        }
      });
    }else if(event.venue&&!/オンライン|複数会場/.test(event.venue)){
      (event.eventDates&&event.eventDates.length?event.eventDates:[event.eventDate]).forEach(function(date){
        rows.push({date:String(date||"").slice(0,10),venue:event.venue});
      });
    }
    return rows;
  }

  function titleOf(event){
    return String(event.eventTitle||event.title||"KAWAII LAB. 公演")
      .replace(/^(FRUITS ZIPPER|CANDY TUNE|SWEET STEADY|CUTIE STREET|MORE STAR)\s*/,"");
  }

  function buildScheduleIndex(events){
    var index={};
    events.forEach(function(event){
      occurrences(event).forEach(function(row){
        var key=normalize(row.venue);
        if(!key)return;
        if(!index[key])index[key]={key:key,rawName:row.venue,items:[],groups:{},names:{}};
        var entry=index[key];
        entry.names[row.venue]=true;
        entry.groups[event.group||"KAWAII LAB."]=true;
        var marker=[row.date,event.group,titleOf(event)].join("|");
        if(!entry.items.some(function(item){return item.marker===marker;})){
          entry.items.push({
            marker:marker,
            date:row.date,
            group:event.group||"KAWAII LAB.",
            title:titleOf(event),
            url:event.url||""
          });
        }
      });
    });
    Object.keys(index).forEach(function(key){
      var entry=index[key];
      entry.items.sort(function(a,b){return String(a.date).localeCompare(String(b.date));});
      entry.upcoming=entry.items.filter(function(item){return !item.date||item.date>=today;});
      entry.next=entry.upcoming[0]||null;
    });
    return index;
  }

  function combineScheduleInfo(current,additional){
    if(!current)return additional;
    if(!additional)return current;
    var seen={};
    var combined={
      key:current.key,
      rawName:current.rawName,
      items:[],
      groups:Object.assign({},current.groups,additional.groups),
      names:Object.assign({},current.names,additional.names)
    };
    current.items.concat(additional.items).forEach(function(item){
      if(seen[item.marker])return;
      seen[item.marker]=true;
      combined.items.push(item);
    });
    combined.items.sort(function(a,b){return String(a.date).localeCompare(String(b.date));});
    combined.upcoming=combined.items.filter(function(item){return !item.date||item.date>=today;});
    combined.next=combined.upcoming[0]||null;
    return combined;
  }

  function fallbackVenue(entry){
    var raw=entry.rawName;
    var type=venueType(raw);
    var prefecture=prefectureOf(raw);
    return{
      id:"",
      name:cleanName(raw),
      aliases:Object.keys(entry.names),
      prefecture:prefecture,
      area:prefecture==="所在地確認中"?"確認中":prefecture.replace(/[都府県]$/,""),
      type:type,
      scale:venueScale(type,raw),
      address:"詳細情報を整理中です",
      access:["公演公式ページまたは会場公式サイトで最新アクセスを確認"],
      capacityNote:"公演形式により変動",
      mapUrl:"https://www.google.com/maps/search/?api=1&query="+encodeURIComponent(raw),
      officialUrl:"",
      provisional:true,
      featured:false,
      scheduleInfo:entry
    };
  }

  function mergeVenues(curated,events){
    var index=buildScheduleIndex(events);
    var matched={};
    var result=curated.map(function(source){
      var venue=Object.assign({},source);
      var keys=[venue.name].concat(venue.aliases||[]).map(normalize);
      var foundKey=keys.find(function(key){return index[key];});
      if(foundKey){
        venue.scheduleInfo=index[foundKey];
        matched[foundKey]=true;
      }else{
        venue.scheduleInfo=null;
      }
      venue.detailed=!venue.provisional;
      return venue;
    });
    Object.keys(index).forEach(function(key){
      if(matched[key])return;
      var entry=index[key];
      var aliasMatch=result.find(function(venue){
        return [venue.name].concat(venue.aliases||[]).some(function(name){
          var candidate=normalize(name);
          return candidate===key||candidate.indexOf(key)>=0||key.indexOf(candidate)>=0;
        });
      });
      if(aliasMatch){
        aliasMatch.scheduleInfo=combineScheduleInfo(aliasMatch.scheduleInfo,entry);
        matched[key]=true;
        return;
      }
      result.push(fallbackVenue(entry));
    });
    return result;
  }

  function typeKey(venue){
    if(venue.type==="アリーナ"||venue.type==="音楽アリーナ"||venue.type==="イベントホール")return"arena";
    if(venue.type==="ライブハウス")return"livehouse";
    if(venue.type==="ホール"||venue.type==="シアター")return"hall";
    return"other";
  }

  function venueHref(venue){
    if(venue.id)return"venue.html?id="+encodeURIComponent(venue.id);
    return"venue.html?name="+encodeURIComponent((venue.aliases||[])[0]||venue.name);
  }

  function card(venue){
    var scheduled=!!venue.scheduleInfo;
    var next=scheduled&&venue.scheduleInfo.next;
    var groupCount=scheduled?Object.keys(venue.scheduleInfo.groups).length:0;
    var detailLabel=venue.detailed?"詳細ガイド":"基本情報";
    return '<article class="venue-card'+(scheduled?' is-scheduled':'')+(venue.detailed?' is-detailed':' is-provisional')+'">'+
      '<div class="venue-card-badges">'+
        '<span class="venue-badge">'+esc(venue.prefecture)+(venue.area&&venue.area!==venue.prefecture.replace(/[都府県]$/,"")?"・"+esc(venue.area):"")+'</span>'+
        '<span class="venue-badge">'+esc(venue.type)+'</span>'+
        '<span class="venue-badge '+(venue.detailed?"verified":"basic")+'">'+detailLabel+'</span>'+
      '</div>'+
      '<h2>'+esc(venue.name)+'</h2>'+
      (scheduled?'<div class="venue-next"><span>次の掲載公演</span><strong>'+(next?esc(fmtDate(next.date)+" "+next.group):"日程を確認中")+'</strong><small>'+groupCount+'グループ・'+venue.scheduleInfo.upcoming.length+'公演掲載</small></div>':'<p class="venue-card-area">'+esc(venue.scale||"会場")+'</p>')+
      '<dl class="venue-card-meta">'+
        '<div><dt>アクセス</dt><dd>'+esc((venue.access||[])[0]||"公式案内を確認")+'</dd></div>'+
        '<div><dt>規模</dt><dd>'+esc(venue.capacityNote||venue.scale||"公演形式により変動")+'</dd></div>'+
      '</dl>'+
      '<a class="venue-card-link" href="'+venueHref(venue)+'">'+(venue.detailed?"詳しい会場情報を見る":"会場ページを見る")+'</a>'+
    '</article>';
  }

  function sortVenues(items){
    var mode=sortSelect.value;
    return items.sort(function(a,b){
      if(mode==="name")return a.name.localeCompare(b.name,"ja");
      if(mode==="region"){
        var region=a.prefecture.localeCompare(b.prefecture,"ja");
        return region||a.name.localeCompare(b.name,"ja");
      }
      var an=a.scheduleInfo&&a.scheduleInfo.next;
      var bn=b.scheduleInfo&&b.scheduleInfo.next;
      if(an&&!bn)return-1;
      if(!an&&bn)return 1;
      if(an&&bn){
        var date=String(an.date).localeCompare(String(bn.date));
        if(date)return date;
      }
      if(a.detailed!==b.detailed)return a.detailed?-1:1;
      if(!!a.featured!==!!b.featured)return a.featured?-1:1;
      return a.name.localeCompare(b.name,"ja");
    });
  }

  function updateStats(){
    var detailed=allVenues.filter(function(venue){return venue.detailed;}).length;
    var scheduled=allVenues.filter(function(venue){return venue.scheduleInfo;}).length;
    var performances=allVenues.reduce(function(total,venue){
      return total+(venue.scheduleInfo?venue.scheduleInfo.upcoming.length:0);
    },0);
    var regions={};
    allVenues.forEach(function(venue){if(venue.prefecture!=="所在地確認中")regions[venue.prefecture]=true;});
    document.getElementById("venue-stat-detailed").textContent=detailed;
    document.getElementById("venue-stat-scheduled").textContent=scheduled;
    document.getElementById("venue-stat-events").textContent=performances;
    document.getElementById("venue-stat-regions").textContent=Object.keys(regions).length;
  }

  function populateRegions(){
    var regions={};
    allVenues.forEach(function(venue){regions[venue.prefecture]=true;});
    Object.keys(regions).sort(function(a,b){return a.localeCompare(b,"ja");}).forEach(function(region){
      var option=document.createElement("option");
      option.value=region;
      option.textContent=region;
      regionFilter.appendChild(option);
    });
  }

  function readQuery(){
    var params=new URLSearchParams(location.search);
    search.value=params.get("q")||"";
    statusFilter.value=params.get("status")||"all";
    sortSelect.value=params.get("sort")||"recommended";
    activeType=params.get("type")||"all";
    var region=params.get("region");
    if(region&&[].some.call(regionFilter.options,function(option){return option.value===region;}))regionFilter.value=region;
  }

  function writeQuery(){
    var params=new URLSearchParams();
    if(search.value.trim())params.set("q",search.value.trim());
    if(statusFilter.value!=="all")params.set("status",statusFilter.value);
    if(regionFilter.value!=="all")params.set("region",regionFilter.value);
    if(activeType!=="all")params.set("type",activeType);
    if(sortSelect.value!=="recommended")params.set("sort",sortSelect.value);
    var query=params.toString();
    history.replaceState(null,"",location.pathname+(query?"?"+query:""));
  }

  function render(){
    var q=search.value.trim().toLowerCase();
    var status=statusFilter.value;
    var region=regionFilter.value;
    var shown=allVenues.filter(function(venue){
      var hay=[venue.name,venue.prefecture,venue.area,venue.type,venue.address]
        .concat(venue.aliases||[],venue.access||[])
        .join(" ")
        .toLowerCase();
      if(q&&hay.indexOf(q)<0)return false;
      if(status==="scheduled"&&!venue.scheduleInfo)return false;
      if(status==="detailed"&&!venue.detailed)return false;
      if(region!=="all"&&venue.prefecture!==region)return false;
      if(activeType!=="all"&&typeKey(venue)!==activeType)return false;
      return true;
    });
    sortVenues(shown);
    list.innerHTML=shown.length?shown.map(card).join(""):'<div class="venue-empty"><strong>条件に合う会場が見つかりませんでした。</strong><br>検索語や絞り込みを少し変えてみてください。</div>';
    count.innerHTML='<strong>'+shown.length+'</strong>会場を表示中 <span>／ 全'+allVenues.length+'会場</span>';
    typeButtons.forEach(function(button){
      var active=button.getAttribute("data-venue-type")===activeType;
      button.classList.toggle("is-active",active);
      button.setAttribute("aria-pressed",String(active));
    });
    resetButton.hidden=!q&&status==="all"&&region==="all"&&activeType==="all"&&sortSelect.value==="recommended";
    writeQuery();
  }

  Promise.all([
    fetch("./data/venues.json",{cache:"no-store"}).then(function(response){
      if(!response.ok)throw new Error("venues");
      return response.json();
    }),
    fetch("./data/live-events.json",{cache:"no-store"}).then(function(response){
      if(!response.ok)return{events:[]};
      return response.json();
    }).catch(function(){return{events:[]};})
  ]).then(function(values){
    allVenues=mergeVenues(values[0].venues||[],values[1].events||[]);
    updateStats();
    populateRegions();
    readQuery();
    render();
  }).catch(function(){
    list.innerHTML='<div class="venue-empty"><strong>会場情報を読み込めませんでした。</strong><br>時間をおいてもう一度お試しください。</div>';
    count.textContent="";
  });

  search.addEventListener("input",render);
  statusFilter.addEventListener("change",render);
  regionFilter.addEventListener("change",render);
  sortSelect.addEventListener("change",render);
  typeButtons.forEach(function(button){
    button.addEventListener("click",function(){
      activeType=button.getAttribute("data-venue-type")||"all";
      render();
    });
  });
  resetButton.addEventListener("click",function(){
    search.value="";
    statusFilter.value="all";
    regionFilter.value="all";
    sortSelect.value="recommended";
    activeType="all";
    render();
    search.focus();
  });
})();
