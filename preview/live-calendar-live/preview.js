document.addEventListener("DOMContentLoaded", async () => {
  const RAW_URL = "https://raw.githubusercontent.com/keio-kawaiilab/keio-kawaii-lab/feature/live-ticket-calendar/data/live-events.json";
  const calendar = document.getElementById("live-calendar");
  const periodLabel = document.getElementById("calendar-month");
  const detail = document.getElementById("calendar-detail");
  const list = document.getElementById("live-list");
  const summary = document.getElementById("live-summary");
  const sourceNote = document.getElementById("source-note");
  const prev = document.getElementById("calendar-prev");
  const next = document.getElementById("calendar-next");
  const filters = [...document.querySelectorAll(".live-filter")];
  if (!calendar || !periodLabel || !list || !summary || !sourceNote) return;

  const style = document.createElement("style");
  style.textContent = `
    .event-bar.online-benefit{background:repeating-linear-gradient(135deg,rgba(255,255,255,0) 0 9px,rgba(255,255,255,.48) 9px 13px),var(--group)!important}
    .milestone.online-benefit{background:repeating-linear-gradient(135deg,#fff 0 8px,#eef1f5 8px 12px)!important}
    .card.online-benefit{background:repeating-linear-gradient(135deg,#fff 0 14px,#f5f7fa 14px 21px)!important}
  `;
  document.head.appendChild(style);

  const cls = {
    "FRUITS ZIPPER":"group-fruits","CANDY TUNE":"group-candy","SWEET STEADY":"group-sweet",
    "CUTIE STREET":"group-cutie","MORE STAR":"group-more","KAWAII LAB.合同":"group-lab"
  };
  const FALLBACK = [
    {group:"SWEET STEADY",title:"STAEDY→REVOLUTION",ticketType:"現在受付なし",eventDate:"2026-08-23",venue:"ぴあアリーナMM",url:"https://sweetsteady.asobisystem.com/news/detail/79979",applicationStatus:"none"},
    {group:"CANDY TUNE",title:"CANDY TUNE オンライン特典会",ticketType:"現在受付なし",eventDate:"2026-08-24",venue:"オンライン（SUKISUKI）",url:"https://sukisuki-shop.com/goods/6500000003995",applicationStatus:"none",eventCategory:"online-benefit"},
    {group:"CUTIE STREET",title:"CUTIE STREET 2nd ANNIVERSARY LIVE 2026",ticketType:"現在受付なし",eventDate:"2026-08-25",eventEndDate:"2026-08-26",eventDates:["2026-08-25","2026-08-26"],schedule:[{date:"2026-08-25",venue:"日本武道館"},{date:"2026-08-26",venue:"日本武道館"}],eventCount:2,venue:"日本武道館",url:"https://cutiestreet.asobisystem.com/news/detail/84129",applicationStatus:"none"},
    {group:"CANDY TUNE",title:"CANDY TUNE JAPAN TOUR 2026 - AUTUMN -",ticketType:"現在受付なし",eventDate:"2026-08-29",eventEndDate:"2026-12-09",eventDates:["2026-08-29","2026-08-30","2026-09-04","2026-09-09","2026-09-10","2026-09-19"],schedule:[{date:"2026-08-29",venue:"戸田市文化会館"},{date:"2026-08-30",venue:"戸田市文化会館"},{date:"2026-09-04",venue:"カルッツかわさき 大ホール"},{date:"2026-09-09",venue:"グランキューブ大阪 メインホール"},{date:"2026-09-10",venue:"グランキューブ大阪 メインホール"},{date:"2026-09-19",venue:"松戸・森のホール21 大ホール"}],eventCount:23,venue:"複数会場（全23公演）",url:"https://candytune.asobisystem.com/news/detail/82537",applicationStatus:"none"},
    {group:"FRUITS ZIPPER",title:"FRUITS ZIPPER JAPAN TOUR 2026 - AUTUMN -",ticketType:"現在受付なし",eventDate:"2026-09-03",eventEndDate:"2026-11-22",eventDates:["2026-09-03","2026-09-16","2026-09-18","2026-09-21"],schedule:[{date:"2026-09-03",venue:"よこすか芸術劇場"},{date:"2026-09-16",venue:"大宮ソニックシティ 大ホール"},{date:"2026-09-18",venue:"松戸・森のホール21 大ホール"},{date:"2026-09-21",venue:"三重県文化会館 大ホール"}],eventCount:23,venue:"複数会場（全23公演）",url:"https://fruitszipper.asobisystem.com/news/detail/85854",applicationStatus:"none"},
    {group:"FRUITS ZIPPER",title:"CDTVライブ！ライブ！秋の大感謝祭2026",ticketType:"現在受付なし",eventDate:"2026-09-11",venue:"東京ガーデンシアター",url:"https://fruitszipper.asobisystem.com/news/detail/84998",applicationStatus:"none"},
    {group:"CUTIE STREET",title:"CUTIE STREET 梅田みゆ 生誕祭 2026",ticketType:"現在受付なし",eventDate:"2026-09-14",venue:"SGCホール有明",url:"https://cutiestreet.asobisystem.com/news/detail/86338",applicationStatus:"none"},
    {group:"CUTIE STREET",title:"CUTIE STREET JAPAN ARENA TOUR 2026 -AUTUMN-",ticketType:"現在受付なし",eventDate:"2026-09-23",eventEndDate:"2026-11-29",eventDates:["2026-09-23","2026-09-29","2026-09-30"],schedule:[{date:"2026-09-23",venue:"横浜アリーナ"},{date:"2026-09-29",venue:"有明アリーナ"},{date:"2026-09-30",venue:"有明アリーナ"}],eventCount:13,venue:"複数会場（全13公演）",url:"https://cutiestreet.asobisystem.com/news/detail/80640",applicationStatus:"none"},
    {group:"CUTIE STREET",title:"STARフェス",ticketType:"FC先行",applyStart:"2026-08-12T13:00",applyEnd:"2026-08-23T23:59",resultDate:"2026-08-29",eventDate:"2026-10-11",venue:"ぴあアリーナ MM",url:"https://cutiestreet.asobisystem.com/news/detail/86976"},
    {group:"KAWAII LAB.合同",participants:["FRUITS ZIPPER","CANDY TUNE","SWEET STEADY","CUTIE STREET","MORE STAR"],title:"KAWAII LAB. Christmas SESSION 2026",ticketType:"アップグレード抽選",applyStart:"2026-08-22T12:00",applyEnd:"2026-08-30T23:59",eventDate:"2026-12-12",eventEndDate:"2026-12-13",eventDates:["2026-12-12","2026-12-13"],schedule:[{date:"2026-12-12",venue:"有明アリーナ"},{date:"2026-12-13",venue:"有明アリーナ"}],eventCount:2,venue:"有明アリーナ",url:"https://candytune.asobisystem.com/news/detail/87780"}
  ];

  const esc=(v="")=>String(v).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");
  const parse=(v)=>{const m=String(v||"").match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);return m?new Date(+m[1],+m[2]-1,+m[3],+(m[4]||0),+(m[5]||0)):null};
  const day=(v)=>{const d=v instanceof Date?v:parse(v);return d?new Date(d.getFullYear(),d.getMonth(),d.getDate()):null};
  const add=(d,n)=>new Date(d.getFullYear(),d.getMonth(),d.getDate()+n);
  const same=(a,b)=>a&&b&&a.getFullYear()===b.getFullYear()&&a.getMonth()===b.getMonth()&&a.getDate()===b.getDate();
  const short=(d)=>`${d.getMonth()+1}/${d.getDate()}`;
  const participants=(e)=>Array.isArray(e.participants)?e.participants:[];
  const matches=(e,g)=>g==="all"||e.group===g||participants(e).includes(g);
  const online=(e)=>e.eventCategory==="online-benefit"||/オンライン(?:特典会|サイン会)/.test(String(e.title||""));
  const title=(e)=>{
    let t=String(e.title||"ライブ情報").replace(/^20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+/,"").trim();
    const q=t.match(/「([^」]+)」/);if(q)t=q[1];
    t=t.replace(/^(?:\d{1,2}月\d{1,2}日\s*)?(FRUITS ZIPPER|CANDY TUNE|SWEET STEADY|CUTIE STREET|MORE STAR|KAWAII LAB\.)\s*/i,"");
    if(/JAPAN ARENA TOUR/i.test(t))return"ARENA TOUR";
    if(/JAPAN TOUR/i.test(t))return"JAPAN TOUR";
    if(/Christmas SESSION/i.test(t))return"Christmas SESSION";
    if(/2nd ANNIVERSARY LIVE/i.test(t))return"2nd ANNIVERSARY";
    if(online(e))return"オンライン特典会";
    return t.split(/\s*@|開催決定|出演決定|アップグレード抽選受付|一般(?:発売|販売|先行)|FC\s*(?:会員)?先行|受付のお知らせ/)[0].replace(/\s*2026\s*$/i,"").trim()||"ライブ";
  };
  const fullTitle=(e)=>String(e.title||"ライブ情報").replace(/^20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+/,"").trim();
  const occurrences=(e)=>{
    const rows=[];
    if(Array.isArray(e.schedule)&&e.schedule.length)e.schedule.forEach(x=>rows.push({date:String(x.date||"").slice(0,10),venue:x.venue||e.venue||null}));
    else if(Array.isArray(e.eventDates)&&e.eventDates.length)e.eventDates.forEach(x=>rows.push({date:String(x).slice(0,10),venue:e.venue||null}));
    else if(e.eventDate)rows.push({date:String(e.eventDate).slice(0,10),venue:e.venue||null});
    const seen=new Set();return rows.filter(x=>parse(x.date)&&!seen.has(x.date)&&seen.add(x.date));
  };
  const fmt=(v)=>{const d=parse(v);if(!d)return"未定";return `${d.getFullYear()}/${d.getMonth()+1}/${d.getDate()}${String(v).includes("T")?` ${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`:""}`};
  const status=(e)=>{if(e.applicationStatus==="none"||e.ticketType==="現在受付なし")return"現在受付なし";const s=parse(e.applyStart),x=parse(e.applyEnd),n=new Date();if(s&&n<s)return"受付前";if(x&&n>x)return"受付終了";if(s&&x&&n>=s&&n<=x)return"受付中";return"日程確認中"};
  const sale=(e)=>{if(online(e))return /抽選/.test(e.ticketType||"")?"オンライン特典会（抽選販売）":/先着/.test(e.ticketType||"")?"オンライン特典会（先着販売）":"オンライン特典会";const t=`${e.ticketType||""} ${e.title||""}`;if(/アップグレード/.test(t))return"アップグレード抽選";if(/一般/.test(t))return"一般販売";if(/年会費コース/.test(t))return"FC年会費コース会員先行";if(/FC|ファンクラブ/i.test(t))return"ファンクラブ先行";if(/先行/.test(t))return"先行受付";return e.ticketType||"チケット受付"};
  const eventLabel=(e)=>{const occ=occurrences(e),a=occ[0]?.date?parse(occ[0].date):parse(e.eventDate),b=occ.length>1?parse(occ[occ.length-1].date):parse(e.eventEndDate);if(!a)return"日程未定";if(!b||same(a,b))return short(a);return `${short(a)}–${short(b)}${Number(e.eventCount||0)>1?`・全${e.eventCount}公演`:""}`};
  const staleYearlessOnline=(e,today)=>{
    if(!online(e)||e.sourceType!=="sukisuki")return false;
    if(/20\d{2}年/.test(String(e.title||"")))return false;
    const d=day(e.eventDate);if(!d)return true;
    return (d-today)/86400000>60;
  };

  async function loadData(){
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),5000);
    try{
      const r=await fetch(RAW_URL+"?t="+Date.now(),{cache:"no-store",signal:controller.signal});
      if(!r.ok)throw new Error(`HTTP ${r.status}`);const data=await r.json();
      if(!Array.isArray(data.events)||!data.events.length)throw new Error("empty");
      return {events:data.events,updatedAt:data.updatedAt||"",fallback:false};
    }catch(err){return {events:FALLBACK,updatedAt:"2026-08-23 11:43",fallback:true};}
    finally{clearTimeout(timer);}
  }

  sourceNote.innerHTML="<strong>データを初期化しています…</strong>";
  const loaded=await loadData();
  const today=day(new Date());
  let events=loaded.events.filter(e=>{
    if(staleYearlessOnline(e,today))return false;
    const occ=occurrences(e);const last=occ.length?day(occ[occ.length-1].date):(day(e.eventEndDate)||day(e.eventDate));
    return !last||last>=today;
  });
  window.__LIVE_EVENTS__=events;
  sourceNote.innerHTML=loaded.fallback?`<strong>表示用バックアップデータで起動しました</strong>　通信が回復すると最新データに戻ります。`:`<strong>公式公開情報 + SUKISUKIから取得</strong>　${esc(loaded.updatedAt)} 更新 / ${events.length}件`;

  const initialGridStart=add(today,-today.getDay());
  let windowStart=today,selected="all";
  const filtered=()=>events.filter(e=>matches(e,selected));

  const showDetail=(e,focus="")=>{
    const occ=occurrences(e);const schedule=occ.length>1?occ.map(x=>`${String(x.date).slice(5).replace("-","/")} ${x.venue||"会場未定"}`).join(" / "):"";
    detail.innerHTML=`<strong>${esc(fullTitle(e))}</strong><span>販売区分: ${esc(sale(e))}</span><span>受付名: ${esc(e.ticketType||"未定")}</span><span>${online(e)?"配信予定日":"公演日"}: ${esc(eventLabel(e))}</span><span>会場: ${esc(e.venue||"未定")}</span>${participants(e).length?`<span>参加: ${esc(participants(e).join(" / "))}</span>`:""}${schedule?`<span>全日程: ${esc(schedule)}</span>`:""}${focus?`<span>${esc(focus)}</span>`:""}${e.url?`<a href="${esc(e.url)}" target="_blank" rel="noopener">情報元を確認する →</a>`:""}`;
  };
  const make=(className,text,e,focus)=>{const b=document.createElement("button");b.type="button";b.className=`${className} ${cls[e.group]||""}${online(e)?" online-benefit":""}`;b.innerHTML=text;b.onclick=()=>showDetail(e,focus);return b};

  function renderCalendar(){
    calendar.innerHTML="";const gridStart=add(windowStart,-windowStart.getDay()),gridEnd=add(gridStart,34),visibleStart=windowStart,F=filtered();periodLabel.textContent=`${short(visibleStart)} 〜 ${short(gridEnd)}（5週間）`;
    for(let w=0;w<5;w++){
      const ws=add(gridStart,w*7),we=add(ws,6),week=document.createElement("div");week.className="week";
      for(let i=0;i<7;i++){const d=add(ws,i),cell=document.createElement("div");cell.className="day";if(d<visibleStart){cell.classList.add("other");cell.innerHTML=""}else{if(same(d,today))cell.classList.add("today");cell.innerHTML=`<span class="num">${d.getDate()===1?`${d.getMonth()+1}/1`:d.getDate()}</span>`}week.appendChild(cell)}
      const ranges=F.map(e=>({e,s:day(e.applyStart),x:day(e.applyEnd)})).filter(z=>z.s&&z.x&&z.x>=ws&&z.s<=we&&z.x>=visibleStart),lanes=[];
      ranges.forEach(z=>{const s=z.s<visibleStart?visibleStart:z.s<ws?ws:z.s,x=z.x>we?we:z.x;if(s>x)return;const si=Math.round((s-ws)/86400000),xi=Math.round((x-ws)/86400000);let lane=lanes.findIndex(v=>v<si);if(lane<0)lane=lanes.length;lanes[lane]=xi;const b=make("event-bar",`<strong>${esc(title(z.e))}</strong><span>${esc(sale(z.e))}</span>`,z.e,`申込期間: ${fmt(z.e.applyStart)} 〜 ${fmt(z.e.applyEnd)}`);b.style.left=`calc(${si/7*100}% + 4px)`;b.style.width=`calc(${(xi-si+1)/7*100}% - 8px)`;b.style.top=`${31+lane*55}px`;week.appendChild(b)});
      const marks=[];F.forEach(e=>{[[e.applyEnd,"⏰","申込締切"],[e.resultDate,"🎫","当落"],[e.paymentEnd,"💳","入金期限"]].forEach(([v,icon,label])=>{const d=day(v);if(d&&d>=visibleStart&&d>=ws&&d<=we&&d<=gridEnd)marks.push({e,d,v,icon,label})});occurrences(e).forEach(o=>{const d=day(o.date);if(d&&d>=visibleStart&&d>=ws&&d<=we&&d<=gridEnd)marks.push({e,d,v:o.date,icon:online(e)?"📱":"🎤",label:online(e)?"オンライン特典会":"公演日",venue:o.venue})})});
      const counts=Array(7).fill(0),base=31+lanes.length*55;marks.sort((a,b)=>a.d-b.d).forEach(m=>{const idx=Math.round((m.d-ws)/86400000),row=counts[idx]++;const b=make("milestone",esc(`${m.icon} ${title(m.e)}`),m.e,`${m.label}: ${fmt(m.v)}${m.venue?` / ${m.venue}`:""}`);b.style.left=`calc(${idx/7*100}% + 4px)`;b.style.width=`calc(${100/7}% - 8px)`;b.style.top=`${base+row*29}px`;week.appendChild(b)});week.style.minHeight=`${Math.max(145,base+Math.max(0,...counts)*29+8)}px`;calendar.appendChild(week)
    }
    if(prev)prev.disabled=gridStart.getTime()===initialGridStart.getTime();
  }

  function renderList(){
    const F=filtered();summary.textContent=`${F.length}件掲載中・うち受付中 ${F.filter(e=>status(e)==="受付中").length}件`;
    list.innerHTML=F.slice().sort((a,b)=>(parse(a.applyEnd)||parse(a.eventDate)||new Date(2999,0,1))-(parse(b.applyEnd)||parse(b.eventDate)||new Date(2999,0,1))).map(e=>`<article class="card ${cls[e.group]||""}${online(e)?" online-benefit":""}"><div class="card-top"><div><div class="event-date">${online(e)?"📱":"🎤"} ${esc(eventLabel(e))}</div><div class="group">${esc(e.group||"")}</div><h3>${esc(fullTitle(e))}</h3></div><span class="status">${esc(status(e))}</span></div><dl class="meta"><div><dt>販売区分</dt><dd>${esc(sale(e))}</dd></div><div><dt>受付名</dt><dd>${esc(e.ticketType||"未定")}</dd></div><div><dt>申込期間</dt><dd>${e.applyStart||e.applyEnd?`${esc(fmt(e.applyStart))} 〜 ${esc(fmt(e.applyEnd))}`:"現在受付なし"}</dd></div><div><dt>${online(e)?"配信予定日":"公演"}</dt><dd>${esc(eventLabel(e))}</dd></div><div><dt>会場</dt><dd>${esc(e.venue||"未定")}</dd></div></dl>${e.url?`<a class="source-link" href="${esc(e.url)}" target="_blank" rel="noopener">情報元を確認する →</a>`:""}</article>`).join("");
  }

  const render=()=>{renderCalendar();renderList()};
  filters.forEach(b=>b.onclick=()=>{selected=b.dataset.group||"all";filters.forEach(x=>x.classList.toggle("is-active",x===b));render()});
  if(prev)prev.onclick=()=>{const gs=add(windowStart,-windowStart.getDay()),p=add(gs,-35);windowStart=p<initialGridStart?today:p;renderCalendar()};
  if(next)next.onclick=()=>{const gs=add(windowStart,-windowStart.getDay());windowStart=add(gs,35);renderCalendar()};
  render();
});