(function(){
  "use strict";

  var cards=document.getElementById("cards");
  if(!cards)return;

  var supplemental=[
    {
      name:"アーバンドック ららぽーと豊洲 シーサイドデッキ メインステージ",
      aliases:["ららぽーと豊洲 シーサイドデッキ メインステージ","東京都 ららぽーと豊洲 シーサイドデッキ メインステージ","アーバンドックららぽーと豊洲"],
      address:"東京都江東区豊洲2-4-9",
      access:["東京メトロ有楽町線「豊洲駅」2b出口直結","ゆりかもめ「豊洲駅」直結"],
      officialUrl:"https://mitsui-shopping-park.com/lalaport/toyosu/access/train-bus.html"
    },
    {
      name:"ららぽーと立川立飛 2Fイベント広場",
      aliases:["ららぽーと立川立飛2Fイベント広場","東京都 ららぽーと立川立飛 2Fイベント広場"],
      address:"東京都立川市泉町935-1",
      access:["多摩モノレール「立飛駅」直結","JR「立川駅」から多摩モノレール「立川北駅」へ乗り換え、2駅約4分"],
      officialUrl:"https://mitsui-shopping-park.com/lalaport/tachikawa/access/train_bus.html"
    },
    {
      name:"animate hall BLACK（アニメイト池袋本店 北館9F）",
      aliases:["animate hall BLACK(アニメイト池袋本店 北館9F)","animate hall BLACK（アニメイト池袋本店 北館9F）","アニメイト池袋本店 北館9F"],
      address:"東京都豊島区東池袋1-20-7 アニメイト池袋本店 北館9F",
      access:["JR・東京メトロ・西武池袋線・東武東上線「池袋駅」東口から徒歩約5分"],
      officialUrl:"https://www.animate.co.jp/shop/ikebukuro/access/"
    },
    {
      name:"テラスモール松戸 2Fこもれびステージ",
      aliases:["テラスモール松戸2Fこもれびステージ","千葉県 テラスモール松戸 2Fこもれびステージ"],
      address:"千葉県松戸市八ヶ崎2-8-1",
      access:["JR常磐線・武蔵野線「新松戸駅」から京成バス千葉ウエスト約15分、「テラスモール松戸北口」下車すぐ","JR常磐線「北小金駅」から京成バス千葉ウエスト約5分、「テラスモール松戸北口」下車すぐ"],
      officialUrl:"https://terracemall.com/matsudo/access/"
    },
    {
      name:"ところざわサクラタウン 千人テラス",
      aliases:["埼玉県 ところざわサクラタウン 千人テラス"],
      address:"埼玉県所沢市東所沢和田3-31-3",
      access:["JR武蔵野線「東所沢駅」から徒歩約10分"],
      officialUrl:"https://tokorozawa-sakuratown.com/access.html"
    },
    {
      name:"エミテラス所沢 2F TOKOROZAWA e-CUBE",
      aliases:["エミテラス所沢2F TOKOROZAWA e-CUBE","埼玉県 エミテラス所沢2F TOKOROZAWA e-CUBE","TOKOROZAWA e-CUBE"],
      address:"埼玉県所沢市東住吉10-1",
      access:["西武池袋線・西武新宿線「所沢駅」西口から徒歩約4分"],
      officialUrl:"https://et-ge-tokorozawa.com/emiterrace/access/"
    },
    {
      name:"ベルサール汐留",
      aliases:["東京都 ベルサール汐留"],
      address:"東京都中央区銀座8-21-1 住友不動産汐留浜離宮ビル B1・1F・2F",
      access:["都営大江戸線「汐留駅」5番出口から徒歩約4分","JR「新橋駅」汐留口から徒歩約7分"],
      officialUrl:"https://www.bellesalle.co.jp/shisetsu/higashiginza/bs_shiodome/"
    },
    {
      name:"東京流通センター 第二展示場 Fホール",
      aliases:["東京都 東京流通センター 第二展示場 Fホール","大特典会 東京流通センター 第二展示場 Fホール","東京流通センター第二展示場Fホール"],
      address:"東京都大田区平和島6-1-1 東京流通センター 第二展示場 Fホール",
      access:["東京モノレール「流通センター駅」から徒歩約1分（駅正面の2階建て・第二展示場）"],
      officialUrl:"https://www.trc-event.jp/access/index.html"
    }
  ];

  function esc(value){
    return String(value==null?"":value)
      .replace(/&/g,"&amp;")
      .replace(/</g,"&lt;")
      .replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;");
  }

  function normalize(value){
    return String(value||"")
      .normalize("NFKC")
      .replace(/^(北海道|東京都|京都府|大阪府|.{2,3}県)[\s　]*/,"")
      .replace(/[\s　・･,，()（）\[\]［］]/g,"")
      .replace(/アーバンドック/g,"")
      .toLowerCase();
  }

  function isPlaceholder(value){
    return /詳細情報を整理中|公式案内を確認|確認中|未定/.test(String(value||""));
  }

  function resolveVenue(name,venues){
    var key=normalize(name);
    if(!key)return null;
    var exact=venues.find(function(venue){
      return[venue.name].concat(venue.aliases||[]).some(function(candidate){return normalize(candidate)===key;});
    });
    if(exact)return exact;
    return venues.find(function(venue){
      return[venue.name].concat(venue.aliases||[]).some(function(candidate){
        var candidateKey=normalize(candidate);
        return candidateKey.length>=6&&(key.indexOf(candidateKey)>=0||candidateKey.indexOf(key)>=0);
      });
    })||null;
  }

  function venueText(card){
    var rows=[].slice.call(card.querySelectorAll(".meta > div"));
    var row=rows.find(function(item){return String((item.querySelector("b")||{}).textContent||"").trim()==="会場";});
    if(!row)return"";
    return String(row.textContent||"").replace(/^会場\s*/,"").trim();
  }

  function isSpecial(card){
    return card.classList.contains("release-card")||card.classList.contains("benefit-card")||/リリースイベント|大特典会/.test(card.textContent||"");
  }

  function pendingVenue(name){
    return /某所|会場未定|未発表|詳細発表待ち/.test(name);
  }

  function insertStyles(){
    if(document.querySelector("style[data-special-venue-info]"))return;
    var style=document.createElement("style");
    style.setAttribute("data-special-venue-info","");
    style.textContent=
      '.meta .special-venue-address,.meta .special-venue-access{background:#fbfcff;border-radius:9px;padding:8px 10px;border-top:0!important}'+
      '.meta .special-venue-access{grid-column:span 2}'+
      '.special-venue-access-list{display:grid;gap:3px;margin:0;padding:0;list-style:none}'+
      '.special-venue-access-list li{line-height:1.55}'+
      '.special-venue-source{display:inline-flex;margin-top:5px;color:var(--navy);font-size:10px;font-weight:900;text-decoration:underline;text-underline-offset:2px}'+
      '.special-venue-pending{color:var(--muted);font-weight:700}'+
      '@media(max-width:620px){.meta .special-venue-access{grid-column:auto}}';
    document.head.appendChild(style);
  }

  function mountCard(card,venues){
    if(!isSpecial(card))return;
    var meta=card.querySelector(".meta");
    if(!meta)return;
    var name=venueText(card);
    if(!name||/オンライン/.test(name))return;

    [].slice.call(meta.querySelectorAll(".special-venue-address,.special-venue-access")).forEach(function(node){node.remove();});

    var venue=resolveVenue(name,venues);
    var address=venue&&!isPlaceholder(venue.address)?venue.address:"";
    var access=venue&&Array.isArray(venue.access)?venue.access.filter(function(item){return item&&!isPlaceholder(item);}):[];
    var official=venue&&venue.officialUrl?venue.officialUrl:"";
    var pending=pendingVenue(name);

    var addressRow=document.createElement("div");
    addressRow.className="special-venue-address";
    addressRow.innerHTML='<b>住所</b>'+(address?esc(address):'<span class="special-venue-pending">'+(pending?'会場発表待ち':'住所情報を確認中')+'</span>');

    var accessRow=document.createElement("div");
    accessRow.className="special-venue-access";
    accessRow.innerHTML='<b>アクセス</b>'+(access.length?'<ul class="special-venue-access-list">'+access.slice(0,3).map(function(item){return'<li>'+esc(item)+'</li>';}).join("")+'</ul>':'<span class="special-venue-pending">'+(pending?'会場発表待ち':'アクセス情報を確認中')+'</span>')+(official?'<a class="special-venue-source" href="'+esc(official)+'" target="_blank" rel="noopener">会場公式のアクセスを確認 →</a>':'');

    meta.appendChild(addressRow);
    meta.appendChild(accessRow);
  }

  function mountAll(venues){
    [].slice.call(cards.querySelectorAll(".card")).forEach(function(card){mountCard(card,venues);});
  }

  insertStyles();
  fetch("./data/venues.json",{cache:"no-store"})
    .then(function(response){return response.ok?response.json():{venues:[]};})
    .catch(function(){return{venues:[]};})
    .then(function(data){
      var venues=(data.venues||[]).concat(supplemental);
      mountAll(venues);
      var queued=false;
      new MutationObserver(function(){
        if(queued)return;
        queued=true;
        window.setTimeout(function(){queued=false;mountAll(venues);},0);
      }).observe(cards,{childList:true});
    });
})();
