(function(){
  "use strict";

  var root=document.getElementById("venue-detail");
  if(!root)return;
  var params=new URLSearchParams(location.search);
  var id=params.get("id")||"";
  var requested=params.get("name")||"";
  var today=localDate(new Date());

  function esc(value){
    return String(value==null?"":value)
      .replace(/&/g,"&amp;")
      .replace(/</g,"&lt;")
      .replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;");
  }

  function localDate(date){
    return[
      date.getFullYear(),
      String(date.getMonth()+1).padStart(2,"0"),
      String(date.getDate()).padStart(2,"0")
    ].join("-");
  }

  function fmtDate(value,long){
    var m=String(value||"").match(/^(\d{4})-(\d{2})-(\d{2})/);
    if(!m)return"日程未定";
    return long?(+m[1])+"年"+(+m[2])+"月"+(+m[3])+"日":(+m[1])+"/"+(+m[2])+"/"+(+m[3]);
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

  function venueType(value){
    var text=String(value||"");
    if(/アリーナ|体育館|ドーム|メッセ|A館|ワールド記念|グリーンアリーナ|IGアリーナ|スーパーアリーナ/.test(text))return"アリーナ";
    if(/ライブハウス|Zepp|PIT|Spotify|O-EAST|WWW|LIQUIDROOM/.test(text))return"ライブハウス";
    if(/ホール|会館|劇場|サンプラザ|サンパレス|グランシアタ/.test(text))return"ホール";
    return"ライブ会場";
  }

  function cleanName(value){
    return stripAddress(value)
      .replace(/\u00a0/g," ")
      .replace(/^(北海道|東京都|京都府|大阪府|.{2,3}県)[\s　]*/,"")
      .trim()||String(value||"会場");
  }

  function occurrenceRows(event){
    var rows=[];
    if(Array.isArray(event.schedule)&&event.schedule.length){
      event.schedule.forEach(function(item){
        if(item&&item.venue)rows.push({date:String(item.date||event.eventDate||"").slice(0,10),venue:item.venue});
      });
    }else if(event.venue&&!/複数会場|オンライン/.test(event.venue)){
      (event.eventDates&&event.eventDates.length?event.eventDates:[event.eventDate]).forEach(function(date){
        rows.push({date:String(date||"").slice(0,10),venue:event.venue});
      });
    }
    return rows;
  }

  function eventTitle(event){
    return String(event.eventTitle||event.title||"KAWAII LAB. 公演")
      .replace(/^(FRUITS ZIPPER|CANDY TUNE|SWEET STEADY|CUTIE STREET|MORE STAR)\s*/,"");
  }

  function keysFor(venue){
    return[venue.name].concat(venue.aliases||[]).map(normalize).filter(Boolean);
  }

  function matchesVenue(name,venue){
    var normalized=normalize(name);
    return keysFor(venue).some(function(key){
      return normalized===key||normalized.indexOf(key)>=0||key.indexOf(normalized)>=0;
    });
  }

  function upcomingAt(events,venue){
    var result=[];
    var seen={};
    events.forEach(function(event){
      occurrenceRows(event).forEach(function(row){
        if(row.date&&row.date<today)return;
        if(!matchesVenue(row.venue,venue))return;
        var marker=[row.date,event.group,eventTitle(event)].join("|");
        if(seen[marker])return;
        seen[marker]=true;
        result.push({
          date:row.date,
          group:event.group||"KAWAII LAB.",
          title:eventTitle(event),
          url:event.url||""
        });
      });
    });
    result.sort(function(a,b){return String(a.date).localeCompare(String(b.date));});
    return result;
  }

  function fallbackVenue(name){
    var raw=name||"";
    var prefecture=prefectureOf(raw);
    return{
      id:"",
      name:cleanName(raw)||"会場が指定されていません",
      aliases:[raw],
      prefecture:prefecture,
      area:prefecture==="所在地確認中"?"確認中":prefecture.replace(/[都府県]$/,""),
      type:venueType(raw),
      scale:"公演形式により変動",
      address:"詳細情報を整理中です",
      access:["公演主催者または会場公式サイトの最新案内を確認してください。"],
      capacityNote:"公演形式により変動",
      officialUrl:"",
      mapUrl:"https://www.google.com/maps/search/?api=1&query="+encodeURIComponent(raw||"ライブ会場"),
      tips:[
        "開場・開演時刻と、整理番号・座席番号による入場方法を公演公式ページで確認してください。",
        "終演後の混雑を見込み、帰りの交通手段と終電時刻を事前に確認しておくと安心です。"
      ],
      provisional:true
    };
  }

  function venueUrl(venue){
    if(venue.id)return"venue.html?id="+encodeURIComponent(venue.id);
    return"venue.html?name="+encodeURIComponent((venue.aliases||[])[0]||venue.name);
  }

  function relatedVenues(all,venue){
    return all.filter(function(candidate){
      return candidate.id!==venue.id&&normalize(candidate.name)!==normalize(venue.name)&&(
        candidate.area&&venue.area&&candidate.area===venue.area||
        candidate.prefecture===venue.prefecture
      );
    }).sort(function(a,b){
      if(a.area===venue.area&&b.area!==venue.area)return-1;
      if(a.area!==venue.area&&b.area===venue.area)return 1;
      return a.name.localeCompare(b.name,"ja");
    }).slice(0,3);
  }

  function showToast(message){
    var toast=document.querySelector(".venue-toast");
    if(!toast){
      toast=document.createElement("div");
      toast.className="venue-toast";
      toast.setAttribute("role","status");
      document.body.appendChild(toast);
    }
    toast.textContent=message;
    toast.classList.add("is-visible");
    window.clearTimeout(showToast.timer);
    showToast.timer=window.setTimeout(function(){toast.classList.remove("is-visible");},1800);
  }

  function copyText(text,message){
    if(navigator.clipboard&&navigator.clipboard.writeText){
      navigator.clipboard.writeText(text).then(function(){showToast(message);}).catch(function(){showToast("コピーできませんでした");});
      return;
    }
    var area=document.createElement("textarea");
    area.value=text;
    area.style.position="fixed";
    area.style.opacity="0";
    document.body.appendChild(area);
    area.select();
    try{document.execCommand("copy");showToast(message);}catch(_error){showToast("コピーできませんでした");}
    area.remove();
  }

  function updateMetadata(venue){
    var description=venue.name+"のアクセス・住所・規模・掲載中の公演をまとめたライブ会場ガイドです。";
    document.title=venue.name+"｜会場ガイド｜KAWAII LAB.同好会";
    var meta=document.querySelector('meta[name="description"]');
    if(meta)meta.content=description;
    var ogTitle=document.getElementById("venue-og-title");
    var ogDescription=document.getElementById("venue-og-description");
    if(ogTitle)ogTitle.content=venue.name+"｜会場ガイド";
    if(ogDescription)ogDescription.content=description;
  }

  function render(venue,events,allVenues,updatedAt){
    updateMetadata(venue);
    var upcoming=upcomingAt(events,venue);
    var next=upcoming[0]||null;
    var groups={};
    upcoming.forEach(function(item){groups[item.group]=true;});
    var access=(venue.access||[]).map(function(item){return"<li>"+esc(item)+"</li>";}).join("");
    var tipItems=venue.tips&&venue.tips.length?venue.tips:[
      "駅から会場までの所要時間は混雑や信号待ちで延びることがあります。時間に余裕を持って向かうと安心です。",
      "入場口や座席構成は公演ごとに異なるため、チケットと主催者の案内をあわせて確認してください。"
    ];
    var tips=tipItems.map(function(item){return"<li>"+esc(item)+"</li>";}).join("");
    var eventHtml=upcoming.length?upcoming.map(function(item){
      return '<div class="venue-upcoming-item">'+
        '<time datetime="'+esc(item.date)+'">'+esc(fmtDate(item.date,true))+'</time>'+
        '<div class="venue-upcoming-copy"><span class="venue-badge">'+esc(item.group)+'</span><strong>'+esc(item.title)+'</strong></div>'+
        (item.url?'<a class="venue-upcoming-source" href="'+esc(item.url)+'" target="_blank" rel="noopener">公式情報 ↗</a>':"")+
      '</div>';
    }).join(""):'<p class="venue-upcoming-empty">現在のスケジュールに、この会場の今後の公演は掲載されていません。</p>';
    var related=relatedVenues(allVenues,venue);
    var relatedHtml=related.length?related.map(function(item){
      return '<a class="venue-related-card" href="'+venueUrl(item)+'"><span>'+esc(item.prefecture)+(item.area?"・"+esc(item.area):"")+'</span><strong>'+esc(item.name)+'</strong></a>';
    }).join(""):'<p class="venue-upcoming-empty">近隣会場の詳細情報を準備中です。</p>';
    var address=venue.address||"公式案内を確認";
    var detailLabel=venue.provisional?"基本情報・整理中":"詳細ガイド";

    root.innerHTML=
      '<nav class="venue-breadcrumb" aria-label="パンくず"><a href="index.html">トップ</a><span>›</span><a href="venues.html">会場ガイド</a><span>›</span><span>'+esc(venue.name)+'</span></nav>'+
      '<section class="venue-detail-hero">'+
        '<div class="venue-detail-hero-content">'+
          '<div class="venue-detail-badges"><span class="venue-detail-badge">'+esc(venue.prefecture)+'</span><span class="venue-detail-badge">'+esc(venue.type||"ライブ会場")+'</span><span class="venue-detail-badge">'+detailLabel+'</span></div>'+
          '<h1>'+esc(venue.name)+'</h1>'+
          '<p class="venue-detail-sub">'+esc(venue.area||"エリア確認中")+'｜'+esc(venue.scale||"公演形式により変動")+'</p>'+
          (next?'<div class="venue-detail-next"><span>次の掲載公演</span><div><strong>'+esc(fmtDate(next.date,true)+"　"+next.group)+'</strong><small>'+esc(next.title)+'</small></div></div>':"")+
          '<div class="venue-detail-actions">'+
            (venue.officialUrl?'<a class="venue-action" href="'+esc(venue.officialUrl)+'" target="_blank" rel="noopener">公式サイト ↗</a>':"")+
            '<a class="venue-action" href="'+esc(venue.mapUrl)+'" target="_blank" rel="noopener">地図を開く ↗</a>'+
            '<a class="venue-action secondary" href="schedule.html">スケジュールを見る</a>'+
            '<button class="venue-action secondary" id="venue-share" type="button">共有する</button>'+
          '</div>'+
        '</div>'+
      '</section>'+
      '<div class="venue-detail-summary">'+
        '<div><span>収容人数の目安</span><strong>'+esc(venue.capacityNote||"公式案内を確認")+'</strong></div>'+
        '<div><span>最寄り交通</span><strong>'+esc((venue.access||[])[0]||"公式案内を確認")+'</strong></div>'+
        '<div><span>今後の掲載公演</span><strong>'+upcoming.length+'公演・'+Object.keys(groups).length+'グループ</strong></div>'+
      '</div>'+
      '<div class="venue-detail-grid">'+
        '<section class="venue-info-card">'+
          '<h2>📍 基本情報</h2>'+
          '<dl class="venue-facts">'+
            '<div><dt>住所</dt><dd>'+esc(address)+(venue.provisional?"":'<button class="venue-copy-address" id="copy-address" type="button" data-address="'+esc(address)+'">住所をコピー</button>')+'</dd></div>'+
            '<div><dt>エリア</dt><dd>'+esc(venue.prefecture)+(venue.area?"・"+esc(venue.area):"")+'</dd></div>'+
            '<div><dt>会場タイプ</dt><dd>'+esc(venue.type||"ライブ会場")+'・'+esc(venue.scale||"")+'</dd></div>'+
            '<div><dt>規模の目安</dt><dd>'+esc(venue.capacityNote||"公演形式により変動")+'</dd></div>'+
          '</dl>'+
          (venue.provisional?'<p class="venue-provisional"><strong>情報を整理中です。</strong><br>公演公式ページと会場公式サイトの案内を優先してご確認ください。</p>':"")+
        '</section>'+
        '<section class="venue-info-card"><h2>🚉 アクセス</h2><ul class="venue-access-list">'+access+'</ul></section>'+
        '<section class="venue-info-card wide"><h2>💡 はじめて行くときのメモ</h2><ul class="venue-tip-list">'+tips+'</ul></section>'+
        '<section class="venue-info-card wide" id="upcoming-events">'+
          '<div class="venue-info-card-head"><h2>🎤 この会場の今後の公演</h2><span class="venue-info-count">'+upcoming.length+'件</span></div>'+
          '<div class="venue-upcoming">'+eventHtml+'</div>'+
        '</section>'+
        '<section class="venue-info-card wide"><h2>📌 近く・同じ地域の会場</h2><div class="venue-related-grid">'+relatedHtml+'</div></section>'+
      '</div>'+
      '<aside class="venue-detail-note">掲載内容は公開情報をもとに当会が整理した非公式ガイドです。設備、座席、ロッカー、ドリンク代、入場方法などは公演ごとに異なる場合があります。来場前には、必ず主催者・会場の公式案内をご確認ください。</aside>';

    var share=document.getElementById("venue-share");
    if(share){
      share.addEventListener("click",function(){
        var data={title:venue.name+"｜会場ガイド",text:venue.name+"のライブ会場情報",url:location.href};
        if(navigator.share){
          navigator.share(data).catch(function(){});
        }else{
          copyText(location.href,"ページURLをコピーしました");
        }
      });
    }
    var copy=document.getElementById("copy-address");
    if(copy)copy.addEventListener("click",function(){copyText(copy.getAttribute("data-address")||address,"住所をコピーしました");});
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
    var all=values[0].venues||[];
    var venue=all.find(function(candidate){
      if(id&&candidate.id===id)return true;
      if(!requested)return false;
      var requestedKey=normalize(requested);
      return[candidate.name].concat(candidate.aliases||[]).some(function(name){
        var key=normalize(name);
        return requestedKey===key||requestedKey.indexOf(key)>=0||key.indexOf(requestedKey)>=0;
      });
    });
    if(!venue&&!requested&&!id){
      root.innerHTML='<div class="venue-empty"><strong>会場が指定されていません。</strong><br><a href="venues.html">会場一覧から選んでください。</a></div>';
      return;
    }
    venue=venue||fallbackVenue(requested);
    render(venue,values[1].events||[],all,values[0].updatedAt||"");
  }).catch(function(){
    root.innerHTML='<div class="venue-empty"><strong>会場情報を読み込めませんでした。</strong><br><a href="venues.html">会場一覧へ戻る</a></div>';
  });
})();
