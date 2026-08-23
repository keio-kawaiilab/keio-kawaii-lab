(function(){
  function onReady(fn){
    if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',fn,{once:true});}else{fn();}
  }
  onReady(function(){
    var calendar=document.getElementById('live-calendar');
    var list=document.getElementById('live-list');
    var summary=document.getElementById('live-summary');
    var detail=document.getElementById('calendar-detail');
    var period=document.getElementById('calendar-month');
    var filters=[].slice.call(document.querySelectorAll('.live-filter'));
    var prev=document.getElementById('calendar-prev');
    var next=document.getElementById('calendar-next');
    if(!calendar||!list||!summary||!period)return;

    var GROUP_CLASS={
      'FRUITS ZIPPER':'group-fruits','CANDY TUNE':'group-candy','SWEET STEADY':'group-sweet',
      'CUTIE STREET':'group-cutie','MORE STAR':'group-more','KAWAII LAB.合同':'group-lab'
    };
    var FALLBACK=[
      {id:'fb-sweet-0823',group:'SWEET STEADY',title:'STAEDY→REVOLUTION',ticketType:'現在受付なし',eventDate:'2026-08-23',venue:'ぴあアリーナMM',applicationStatus:'none',url:'https://sweetsteady.asobisystem.com/news/detail/79979'},
      {id:'fb-candy-online-0824',group:'CANDY TUNE',title:'CANDY TUNE オンライン特典会',ticketType:'オンライン特典会',eventDate:'2026-08-24',venue:'オンライン（SUKISUKI）',eventCategory:'online-benefit',applicationStatus:'none',url:'https://sukisuki-shop.com/goods/6500000003995'},
      {id:'fb-cutie-anniv',group:'CUTIE STREET',title:'CUTIE STREET 2nd ANNIVERSARY LIVE 2026',ticketType:'現在受付なし',eventDate:'2026-08-25',eventEndDate:'2026-08-26',eventDates:['2026-08-25','2026-08-26'],schedule:[{date:'2026-08-25',venue:'日本武道館'},{date:'2026-08-26',venue:'日本武道館'}],eventCount:2,venue:'日本武道館',applicationStatus:'none',url:'https://cutiestreet.asobisystem.com/news/detail/84129'},
      {id:'fb-candy-tour',group:'CANDY TUNE',title:'CANDY TUNE JAPAN TOUR 2026 - AUTUMN -',ticketType:'現在受付なし',eventDate:'2026-08-29',eventEndDate:'2026-12-09',eventDates:['2026-08-29','2026-08-30','2026-09-04','2026-09-09','2026-09-10','2026-09-19'],schedule:[{date:'2026-08-29',venue:'戸田市文化会館'},{date:'2026-08-30',venue:'戸田市文化会館'},{date:'2026-09-04',venue:'カルッツかわさき 大ホール'},{date:'2026-09-09',venue:'グランキューブ大阪 メインホール'},{date:'2026-09-10',venue:'グランキューブ大阪 メインホール'},{date:'2026-09-19',venue:'松戸・森のホール21 大ホール'}],eventCount:23,venue:'複数会場（全23公演）',applicationStatus:'none',url:'https://candytune.asobisystem.com/news/detail/82537'},
      {id:'fb-fruits-tour',group:'FRUITS ZIPPER',title:'FRUITS ZIPPER JAPAN TOUR 2026 - AUTUMN -',ticketType:'現在受付なし',eventDate:'2026-09-03',eventEndDate:'2026-11-22',eventDates:['2026-09-03','2026-09-16','2026-09-18','2026-09-21'],schedule:[{date:'2026-09-03',venue:'よこすか芸術劇場'},{date:'2026-09-16',venue:'大宮ソニックシティ 大ホール'},{date:'2026-09-18',venue:'松戸・森のホール21 大ホール'},{date:'2026-09-21',venue:'三重県文化会館 大ホール'}],eventCount:23,venue:'複数会場（全23公演）',applicationStatus:'none',url:'https://fruitszipper.asobisystem.com/news/detail/85854'},
      {id:'fb-ogawa',group:'CANDY TUNE',title:'小川奈々子 生誕祭 2026',ticketType:'現在受付なし',eventDate:'2026-10-01',venue:'SGCホール有明',applicationStatus:'none'},
      {id:'fb-star',group:'CUTIE STREET',title:'STARフェス',ticketType:'FC先行',applyStart:'2026-08-12T13:00',applyEnd:'2026-08-23T23:59',resultDate:'2026-08-29',eventDate:'2026-10-11',venue:'ぴあアリーナ MM',url:'https://cutiestreet.asobisystem.com/news/detail/86976'},
      {id:'fb-xmas',group:'KAWAII LAB.合同',participants:['FRUITS ZIPPER','CANDY TUNE','SWEET STEADY','CUTIE STREET','MORE STAR'],title:'KAWAII LAB. Christmas SESSION 2026',ticketType:'アップグレード抽選',applyStart:'2026-08-22T12:00',applyEnd:'2026-08-30T23:59',eventDate:'2026-12-12',eventEndDate:'2026-12-13',eventDates:['2026-12-12','2026-12-13'],schedule:[{date:'2026-12-12',venue:'有明アリーナ'},{date:'2026-12-13',venue:'有明アリーナ'}],eventCount:2,venue:'有明アリーナ',url:'https://candytune.asobisystem.com/news/detail/87780'}
    ];

    function esc(v){return String(v==null?'':v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');}
    function parse(v){var m=String(v||'').match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);return m?new Date(+m[1],+m[2]-1,+m[3],+(m[4]||0),+(m[5]||0)):null;}
    function day(v){var d=v instanceof Date?v:parse(v);return d?new Date(d.getFullYear(),d.getMonth(),d.getDate()):null;}
    function add(d,n){return new Date(d.getFullYear(),d.getMonth(),d.getDate()+n);}
    function same(a,b){return a&&b&&a.getFullYear()===b.getFullYear()&&a.getMonth()===b.getMonth()&&a.getDate()===b.getDate();}
    function short(d){return (d.getMonth()+1)+'/'+d.getDate();}
    function online(e){return e.eventCategory==='online-benefit'||/オンライン(?:特典会|サイン会)/.test(String(e.title||''));}
    function participants(e){return Array.isArray(e.participants)?e.participants:[];}
    function matches(e,g){return g==='all'||e.group===g||participants(e).indexOf(g)>=0;}
    function occ(e){
      var rows=[],seen={};
      if(Array.isArray(e.schedule)&&e.schedule.length){e.schedule.forEach(function(x){if(x&&x.date)rows.push({date:String(x.date).slice(0,10),venue:x.venue||e.venue||null});});}
      else if(Array.isArray(e.eventDates)&&e.eventDates.length){e.eventDates.forEach(function(x){rows.push({date:String(x).slice(0,10),venue:e.venue||null});});}
      else if(e.eventDate){rows.push({date:String(e.eventDate).slice(0,10),venue:e.venue||null});}
      return rows.filter(function(x){if(!parse(x.date)||seen[x.date])return false;seen[x.date]=1;return true;});
    }
    function cleanTitle(e){
      var t=String(e.title||'ライブ情報').replace(/^20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+/,'').trim();
      var q=t.match(/「([^」]+)」/);if(q)t=q[1];
      t=t.replace(/^(FRUITS ZIPPER|CANDY TUNE|SWEET STEADY|CUTIE STREET|MORE STAR|KAWAII LAB\.)\s*/i,'');
      if(/JAPAN ARENA TOUR/i.test(t))return 'ARENA TOUR';
      if(/JAPAN TOUR/i.test(t))return 'JAPAN TOUR';
      if(/Christmas SESSION/i.test(t))return 'Christmas SESSION';
      if(/2nd ANNIVERSARY LIVE/i.test(t))return '2nd ANNIVERSARY';
      if(online(e))return 'オンライン特典会';
      return t.split(/開催決定|出演決定|アップグレード抽選受付|一般(?:発売|販売|先行)|FC\s*(?:会員)?先行|受付のお知らせ/)[0].trim()||'ライブ';
    }
    function fmt(v){var d=parse(v);if(!d)return '—';return d.getFullYear()+'/'+(d.getMonth()+1)+'/'+d.getDate()+(String(v).indexOf('T')>=0?' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0'):'');}
    function sale(e){
      if(e.applicationStatus==='none'||e.ticketType==='現在受付なし')return '現在受付なし';
      if(online(e))return 'オンライン特典会';
      var t=String(e.ticketType||'')+' '+String(e.title||'');
      if(/アップグレード/.test(t))return 'アップグレード抽選';
      if(/一般/.test(t))return '一般販売';
      if(/年会費コース/.test(t))return 'FC年会費コース先行';
      if(/FC|ファンクラブ/i.test(t))return 'ファンクラブ先行';
      if(/プレリザーブ|プレイガイド/.test(t))return 'プレイガイド先行';
      return e.ticketType||'チケット受付';
    }
    function lastDate(e){var o=occ(e);return o.length?day(o[o.length-1].date):(day(e.eventEndDate)||day(e.eventDate));}
    function idFor(e,i){return String(e.id||('runtime-'+i)).replace(/[^a-zA-Z0-9_-]/g,'_');}

    var today=day(new Date());
    var selected='all';
    var pageOffset=0;
    var events=FALLBACK.slice();

    function visibleEvents(){return events.filter(function(e){var l=lastDate(e);return (!l||l>=today)&&matches(e,selected);});}
    function eventRange(e){var o=occ(e);if(!o.length)return '日程未定';var a=parse(o[0].date),b=parse(o[o.length-1].date);if(!b||same(a,b))return short(a);return short(a)+'–'+short(b)+(Number(e.eventCount||0)>1?'・全'+e.eventCount+'公演':'');}

    function renderList(){
      var data=visibleEvents().sort(function(a,b){return (day(a.eventDate)||new Date(8640000000000000))-(day(b.eventDate)||new Date(8640000000000000));});
      summary.textContent=data.length?data.length+'件掲載中':'現在、掲載中の未来公演はありません。';
      list.innerHTML='';
      data.forEach(function(e,i){
        var article=document.createElement('article');
        article.className='live-card '+(GROUP_CLASS[e.group]||'')+(online(e)?' online-benefit':'');
        article.id='runtime-card-'+idFor(e,i);
        if(online(e))article.style.backgroundImage='repeating-linear-gradient(135deg,rgba(255,255,255,.35) 0 10px,rgba(0,0,0,.05) 10px 16px)';
        article.innerHTML='<div class="live-card-top"><div><div class="live-event-date">'+(online(e)?'📱 ':'🎤 ')+esc(eventRange(e))+'</div><div class="live-group">'+esc(e.group||'KAWAII LAB.')+'</div><h3>'+esc(cleanTitle(e))+'</h3></div><span class="live-status">'+esc(sale(e))+'</span></div>'+
          '<dl class="live-meta"><div><dt>受付名</dt><dd>'+esc(e.ticketType||'未定')+'</dd></div><div><dt>公演日</dt><dd>'+esc(eventRange(e))+'</dd></div><div><dt>申込開始</dt><dd>'+esc(fmt(e.applyStart))+'</dd></div><div><dt>申込締切</dt><dd>'+esc(fmt(e.applyEnd))+'</dd></div><div><dt>当落発表</dt><dd>'+esc(fmt(e.resultDate))+'</dd></div><div><dt>入金期限</dt><dd>'+esc(fmt(e.paymentEnd))+'</dd></div><div><dt>会場</dt><dd>'+esc(e.venue||'未定')+'</dd></div></dl>'+
          (e.url?'<a class="live-link" href="'+esc(e.url)+'" target="_blank" rel="noopener noreferrer">公式情報を確認する →</a>':'');
        list.appendChild(article);
      });
    }

    function renderCalendar(){
      calendar.innerHTML='';
      var start=add(today,-today.getDay()+pageOffset*35);
      var end=add(start,34);
      period.textContent=short(start)+' 〜 '+short(end)+'（5週間）';
      var data=visibleEvents();
      for(var w=0;w<5;w++){
        var weekStart=add(start,w*7);
        var week=document.createElement('div');
        week.className='calendar-week';
        week.style.minHeight='150px';
        for(var d=0;d<7;d++){
          var dt=add(weekStart,d);
          var cell=document.createElement('div');cell.className='calendar-day'+(d===0?' is-sun':'')+(d===6?' is-sat':'');
          cell.innerHTML='<span class="calendar-day-number">'+(dt.getDate()===1?(dt.getMonth()+1)+'/1':dt.getDate())+'</span>';week.appendChild(cell);
        }
        var perDay=[0,0,0,0,0,0,0];
        data.forEach(function(e,ei){
          occ(e).forEach(function(o){
            var dt=day(o.date);if(!dt||dt<weekStart||dt>add(weekStart,6))return;
            var idx=Math.round((dt-weekStart)/86400000);var row=perDay[idx]++;
            var b=document.createElement('button');b.type='button';b.className='calendar-milestone '+(GROUP_CLASS[e.group]||'')+(online(e)?' online-benefit':'');
            b.textContent=(online(e)?'📱 ':'🎤 ')+cleanTitle(e);b.style.left='calc('+(idx/7*100)+'% + 4px)';b.style.width='calc('+(100/7)+'% - 8px)';b.style.top=(34+row*30)+'px';
            if(online(e))b.style.backgroundImage='repeating-linear-gradient(135deg,#fff 0 7px,#d9dce2 7px 12px)';
            b.addEventListener('click',function(){
              if(detail)detail.innerHTML='<strong>'+esc(cleanTitle(e))+'</strong><span>公演日: '+esc(fmt(o.date))+'</span><span>会場: '+esc(o.venue||e.venue||'未定')+'</span><span>受付: '+esc(e.ticketType||'未定')+'</span>';
              var card=document.getElementById('runtime-card-'+idFor(e,ei));if(card){card.scrollIntoView({behavior:'smooth',block:'center'});card.style.outline='3px solid #c39b3f';setTimeout(function(){card.style.outline='';},1400);}
            });
            week.appendChild(b);
          });
        });
        week.style.minHeight=(Math.max.apply(Math,perDay)*30+72)+'px';calendar.appendChild(week);
      }
      if(prev)prev.disabled=pageOffset<=0;
    }
    function renderAll(){window.__LIVE_EVENTS__=events;renderCalendar();renderList();}

    function takeover(){
      var hasCalendar=calendar.querySelector('.calendar-week');
      var hasCards=list.querySelector('.live-card');
      if(hasCalendar&&hasCards)return;
      renderAll();
      filters.forEach(function(btn){btn.addEventListener('click',function(){selected=btn.getAttribute('data-group')||'all';filters.forEach(function(x){x.classList.toggle('is-active',x===btn);});renderAll();});});
      if(prev)prev.addEventListener('click',function(){if(pageOffset>0){pageOffset--;renderCalendar();}});
      if(next)next.addEventListener('click',function(){pageOffset++;renderCalendar();});

      try{
        var xhr=new XMLHttpRequest();xhr.open('GET','./data/live-events.json?t='+Date.now(),true);xhr.timeout=5000;
        xhr.onreadystatechange=function(){if(xhr.readyState===4&&xhr.status>=200&&xhr.status<300){try{var data=JSON.parse(xhr.responseText);if(data&&Array.isArray(data.events)&&data.events.length){events=data.events;renderAll();}}catch(_e){}}};
        xhr.send();
      }catch(_err){}
    }
    setTimeout(takeover,800);
  });
})();
