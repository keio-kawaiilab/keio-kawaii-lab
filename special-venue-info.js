(function(){
  "use strict";

  var cards=document.getElementById("cards");
  if(!cards)return;

  var supplemental=[];

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
    if(!name||/オンライン|YouTube|当選者のみ|https?:\/\//i.test(name))return;

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
