(function(){
  "use strict";
  var list=document.getElementById("venue-list");
  if(!list)return;
  var search=document.getElementById("venue-search");
  var filter=document.getElementById("venue-filter");
  var count=document.getElementById("venue-count");
  var venues=[];
  var scheduled={};

  function esc(value){return String(value==null?"":value).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}
  function normalize(value){return String(value||"").replace(/\u00a0/g," ").replace(/^(東京都|神奈川県|千葉県|埼玉県|北海道|京都府|大阪府|.{2,3}県)\s*/,"").replace(/[\s　]+/g,"").replace(/[（(][^）)]*(?:都|道|府|県|市|区)[^）)]*[）)]$/g,"").replace(/大ホール/g,"").toLowerCase()}
  function venueNames(event){var out=[];(event.schedule||[]).forEach(function(item){if(item&&item.venue)out.push(item.venue)});if(!out.length&&event.venue&&!/複数会場|オンライン/.test(event.venue))out.push(event.venue);return out}
  function markScheduled(events){events.forEach(function(event){venueNames(event).forEach(function(name){scheduled[normalize(name)]=true})})}
  function isScheduled(venue){return [venue.name].concat(venue.aliases||[]).some(function(name){return scheduled[normalize(name)]})}
  function card(venue){var active=isScheduled(venue);return '<article class="venue-card'+(active?' is-scheduled':'')+'">'+
    '<div class="venue-card-badges"><span class="venue-badge">'+esc(venue.prefecture)+'・'+esc(venue.area)+'</span><span class="venue-badge">'+esc(venue.type)+'</span>'+(active?'<span class="venue-badge schedule">掲載中の公演あり</span>':'')+'</div>'+
    '<h2>'+esc(venue.name)+'</h2><p class="venue-card-area">'+esc(venue.scale||'会場')+'</p>'+
    '<dl class="venue-card-meta"><div><dt>最寄り</dt><dd>'+esc((venue.access||[])[0]||'公式案内を確認')+'</dd></div><div><dt>規模</dt><dd>'+esc(venue.capacityNote||'公演形式により変動')+'</dd></div></dl>'+
    '<a class="venue-card-link" href="venue.html?id='+encodeURIComponent(venue.id)+'">会場情報を見る</a></article>'}
  function render(){var q=String(search.value||"").trim().toLowerCase();var mode=filter.value;var shown=venues.filter(function(venue){var hay=[venue.name,venue.prefecture,venue.area,venue.type].concat(venue.aliases||[],venue.access||[]).join(" ").toLowerCase();if(q&&hay.indexOf(q)<0)return false;if(mode==="scheduled"&&!isScheduled(venue))return false;if(mode==="tokyo"&&venue.prefecture!=="東京都")return false;if(mode==="kanagawa"&&venue.prefecture!=="神奈川県")return false;if(mode==="other"&&(venue.prefecture==="東京都"||venue.prefecture==="神奈川県"))return false;return true});list.innerHTML=shown.length?shown.map(card).join(""):'<div class="venue-empty">条件に合う会場が見つかりませんでした。検索語を短くしてみてください。</div>';count.textContent=shown.length+'会場を表示中'}
  Promise.all([
    fetch('./data/venues.json',{cache:'no-store'}).then(function(r){if(!r.ok)throw new Error('venues');return r.json()}),
    fetch('./data/live-events.json',{cache:'no-store'}).then(function(r){if(!r.ok)return{events:[]};return r.json()}).catch(function(){return{events:[]}})
  ]).then(function(values){venues=values[0].venues||[];markScheduled(values[1].events||[]);render()}).catch(function(){list.innerHTML='<div class="venue-empty">会場情報を読み込めませんでした。時間をおいてもう一度お試しください。</div>';count.textContent=''});
  search.addEventListener('input',render);filter.addEventListener('change',render);
})();
