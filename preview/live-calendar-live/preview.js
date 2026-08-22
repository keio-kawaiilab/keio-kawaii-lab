document.addEventListener("DOMContentLoaded", async () => {
  const DATA_URL = "https://raw.githubusercontent.com/keio-kawaiilab/keio-kawaii-lab/feature/live-ticket-calendar/data/live-events.json";
  const calendar = document.getElementById("live-calendar");
  const periodLabel = document.getElementById("calendar-month");
  const detail = document.getElementById("calendar-detail");
  const list = document.getElementById("live-list");
  const summary = document.getElementById("live-summary");
  const sourceNote = document.getElementById("source-note");
  const prev = document.getElementById("calendar-prev");
  const next = document.getElementById("calendar-next");
  const filters = [...document.querySelectorAll(".live-filter")];

  const cls = {
    "FRUITS ZIPPER":"group-fruits","CANDY TUNE":"group-candy","SWEET STEADY":"group-sweet",
    "CUTIE STREET":"group-cutie","MORE STAR":"group-more","KAWAII LAB.合同":"group-lab"
  };
  const esc = (v="") => String(v).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");
  const parse = (v) => { const m=String(v||"").match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/); return m?new Date(+m[1],+m[2]-1,+m[3],+(m[4]||0),+(m[5]||0)):null; };
  const day = (v) => { const d=v instanceof Date?v:parse(v); return d?new Date(d.getFullYear(),d.getMonth(),d.getDate()):null; };
  const add = (d,n) => new Date(d.getFullYear(),d.getMonth(),d.getDate()+n);
  const sameDay = (a,b) => a&&b&&a.getFullYear()===b.getFullYear()&&a.getMonth()===b.getMonth()&&a.getDate()===b.getDate();
  const maxDate = (a,b) => a>b?a:b, minDate=(a,b)=>a<b?a:b;
  const fmt = (v) => { const d=parse(v); if(!d)return"未定"; const t=String(v).includes("T"); return new Intl.DateTimeFormat("ja-JP",{year:"numeric",month:"numeric",day:"numeric",hour:t?"2-digit":undefined,minute:t?"2-digit":undefined}).format(d); };
  const shortDay=(d)=>`${d.getMonth()+1}/${d.getDate()}`;

  const displayTitle=(e)=>{
    let t=String(e.title||"ライブ情報").replace(/^20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+/,"").trim();
    const q=t.match(/「([^」]+)」/);if(q)return q[1].trim();
    t=t.replace(/^(?:20\d{2}年)?\d{1,2}月\d{1,2}日(?:\([^)]*\)|（[^）]*）)?\s*/,"");
    t=t.split(/\s*@|開催決定|出演決定|アップグレード抽選受付|一般(?:発売|販売|先行)|FC\s*(?:会員)?先行|ファンクラブ|OFFICIAL FANCLUB|先行受付|チケット受付|受付のお知らせ/)[0];
    return t.replace(/[!！\s\-–—｜|]+$/g,"").trim()||String(e.title||"ライブ情報");
  };
  const range = (e) => { const a=parse(e.eventDate),b=parse(e.eventEndDate); if(!a)return"日程未定"; if(!b||sameDay(a,b))return shortDay(a); return a.getMonth()===b.getMonth()?`${shortDay(a)}–${b.getDate()}`:`${shortDay(a)}–${shortDay(b)}`; };
  const eventLabel = (e) => Number(e.eventCount||0)>1?`${range(e)}・全${e.eventCount}公演`:range(e);
  const participants = (e) => Array.isArray(e.participants)?e.participants:[];
  const matches = (e,g) => g==="all"||e.group===g||participants(e).includes(g);
  const urls = (e) => { const a=Array.isArray(e.urls)?[...e.urls.filter(Boolean)]:[]; if(e.url&&!a.includes(e.url))a.unshift(e.url); return a; };
  const noCurrentSale = (e) => e.applicationStatus==="none" || e.ticketType==="現在受付なし";
  const status = (e) => { if(noCurrentSale(e))return"現在受付なし"; const s=parse(e.applyStart),x=parse(e.applyEnd),n=new Date(); if(s&&n<s)return"受付前"; if(s&&x&&n>=s&&n<=x)return"受付中"; if(x&&n>x)return"受付終了"; return"日程確認中"; };
  const saleCategory=(e)=>{if(noCurrentSale(e))return"現在受付なし";const t=`${e.ticketType||""} ${e.title||""}`;if(/アップグレード/.test(t))return"アップグレード抽選";if(/一般(?:発売|販売|先着)/.test(t))return"一般販売";if(/年会費コース/.test(t))return"FC年会費コース会員先行";if(/(?:KAWAII LAB\.\s*FC|OFFICIAL FANCLUB|ファンクラブ|\bFC\b|FC会員)/i.test(t))return"ファンクラブ先行";if(/プレリク|プレイガイド/.test(t))return"プレイガイド先行";if(/先行/.test(t))return"先行受付";return"チケット受付";};
  const audience=(e)=>{if(noCurrentSale(e))return"—";const t=`${e.ticketType||""} ${e.title||""}`;if(/年会費コース/.test(t))return"FC年会費コース会員";if(/(?:KAWAII LAB\.\s*FC|OFFICIAL FANCLUB|ファンクラブ|\bFC\b|FC会員)/i.test(t))return"FC会員";if(/一般(?:発売|販売|先着)/.test(t))return"一般";if(/アップグレード/.test(t))return"対象チケット保有者向け（公式条件を確認）";return"公式条件を確認";};
  const neutralTitle=(v)=>{const t=String(v||"").replace(/^20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+/,"").trim();const q=t.match(/「([^」]+)」/);if(q)return q[1].trim();return t.split(/開催決定|FC\s*先行|ファンクラブ|OFFICIAL FANCLUB|先行受付|チケット受付/)[0].replace(/[!！\-–—｜|　]+$/g,"").trim()||t;};

  const collapseSameWindow = (items) => {
    const buckets = new Map();
    const titleKey = (v) => String(v||"").replace(/^20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+/,"").replace(/\s+/g," ").trim();
    for (const e of items) { const key=[e.group,participants(e).join("|"),titleKey(e.title),e.ticketType,e.applyStart,e.applyEnd,e.resultDate,e.paymentEnd].join("\u001f"); if(!buckets.has(key))buckets.set(key,[]); buckets.get(key).push(e); }
    const out=[];
    for (const group of buckets.values()) {
      const schedule=[]; for(const e of group){if(Array.isArray(e.schedule)&&e.schedule.length)e.schedule.forEach(x=>schedule.push({date:String(x.date||"").slice(0,10),venue:x.venue||null}));else if(Array.isArray(e.eventDates)&&e.eventDates.length)e.eventDates.forEach(x=>schedule.push({date:String(x).slice(0,10),venue:e.venue||null}));else if(e.eventDate)schedule.push({date:String(e.eventDate).slice(0,10),venue:e.venue||null});}
      const seen=new Set(),uniq=[];schedule.sort((a,b)=>a.date.localeCompare(b.date)).forEach(x=>{const k=`${x.date}|${x.venue||""}`;if(!seen.has(k)&&parse(x.date)){seen.add(k);uniq.push(x);}});
      const dates=[...new Set(uniq.map(x=>x.date))].sort();if(dates.length<=1){out.push(...group);continue;}
      const first={...group[0]},venueList=[...new Set(uniq.map(x=>x.venue).filter(Boolean))];first.eventDate=dates[0];first.eventEndDate=dates.at(-1);first.eventDates=dates;first.eventCount=dates.length;first.schedule=uniq;first.venue=venueList.length===1?venueList[0]:`複数会場（全${dates.length}公演）`;first.urls=[...new Set(group.flatMap(urls))];if(first.urls.length)first.url=first.urls[0];out.push(first);
    } return out;
  };
  const scheduleIdentity=(e)=>{const s=Array.isArray(e.schedule)&&e.schedule.length?e.schedule.map(x=>`${String(x.date||"").slice(0,10)}@${String(x.venue||"").replace(/\s+/g,"")}`).join("|"):(Array.isArray(e.eventDates)&&e.eventDates.length?e.eventDates.join("|"):`${String(e.eventDate||"").slice(0,10)}@${String(e.venue||"").replace(/\s+/g,"")}`);return[e.group,participants(e).join("|"),s].join("\u001f");};
  const collapseExpired=(items,today)=>{const buckets=new Map();items.forEach(e=>{const k=scheduleIdentity(e);if(!buckets.has(k))buckets.set(k,[]);buckets.get(k).push(e);});const out=[];for(const group of buckets.values()){const current=[],expired=[],scheduleOnly=[];for(const e of group){if(noCurrentSale(e)||(!e.applyStart&&!e.applyEnd)){scheduleOnly.push(e);continue;}const dates=[e.applyEnd,e.resultDate,e.paymentEnd].map(day).filter(Boolean).sort((a,b)=>a-b),last=dates.length?dates.at(-1):null;(last&&last>=today?current:expired).push(e);}if(current.length){out.push(...current);continue;}if(scheduleOnly.length){out.push(scheduleOnly.sort((a,b)=>String(b.sourcePublishedAt||"").localeCompare(String(a.sourcePublishedAt||"")))[0]);continue;}if(!expired.length)continue;const latest=[...expired].sort((a,b)=>String(b.applyEnd||"").localeCompare(String(a.applyEnd||""))||String(b.sourcePublishedAt||"").localeCompare(String(a.sourcePublishedAt||"")))[0];const e={...latest,title:neutralTitle(latest.title),ticketType:"現在受付なし",applicationStatus:"none",applyStart:null,applyEnd:null,resultDate:null,paymentEnd:null};e.urls=[...new Set(expired.flatMap(urls))];if(e.urls.length)e.url=e.urls[0];out.push(e);}return out;};

  let events=[];
  try {
    const r=await fetch(DATA_URL+"?t="+Date.now(),{cache:"no-store"});if(!r.ok)throw new Error();const data=await r.json();const today=day(new Date());
    const raw=(Array.isArray(data.events)?data.events:[]).filter(e=>!/(?:チケット.*まとめ|まとめ.*チケット)/.test(String(e.title||""))).filter(e=>{const last=day(e.eventEndDate)||day(e.eventDate);return !last||last>=today;});
    events=collapseExpired(collapseSameWindow(raw),today);sourceNote.innerHTML=`<strong>公式公開情報から自動取得</strong>　${esc(data.updatedAt||"")} 更新 / ${events.length}件`;
  } catch (_) { sourceNote.textContent="データを読み込めませんでした。"; }

  const today=day(new Date()),initialGridStart=add(today,-today.getDay());let windowStart=today,selected="all";const filtered=()=>events.filter(e=>matches(e,selected));

  const showDetail=(e,focus="")=>{const p=participants(e),u=urls(e),schedule=Array.isArray(e.schedule)?e.schedule:[],scheduleText=schedule.length>1?schedule.map(x=>`${String(x.date||"").slice(5).replace("-","/")} ${x.venue||"会場未定"}`).join(" / "):"";detail.innerHTML=`<strong>${esc(eventLabel(e))}｜${esc(displayTitle(e))}</strong><span>販売区分: ${esc(saleCategory(e))}</span><span>受付名: ${esc(e.ticketType||"未定")}</span><span>対象: ${esc(audience(e))}</span><span>会場: ${esc(e.venue||"未定")}</span>${p.length?`<span>参加: ${esc(p.join(" / "))}</span>`:""}${scheduleText?`<span>全日程: ${esc(scheduleText)}</span>`:""}${focus?`<span>${esc(focus)}</span>`:""}${u.length?`<a href="${esc(u[0])}" target="_blank" rel="noopener">公式情報を確認する →</a>`:""}`;};
  const makeButton=(className,html,e,focus)=>{const b=document.createElement("button");b.type="button";b.className=`${className} ${cls[e.group]||""}`;b.innerHTML=html;b.onclick=()=>showDetail(e,focus);return b;};

  function renderCalendar(){
    calendar.innerHTML="";const gridStart=add(windowStart,-windowStart.getDay()),gridEnd=add(gridStart,34),visibleStart=windowStart,F=filtered();periodLabel.textContent=`${shortDay(visibleStart)} 〜 ${shortDay(gridEnd)}（5週間）`;
    for(let w=0;w<5;w++){
      const ws=add(gridStart,w*7),we=add(ws,6),week=document.createElement("div");week.className="week";
      for(let i=0;i<7;i++){const d=add(ws,i),cell=document.createElement("div");cell.className="day";if(d<visibleStart){cell.classList.add("other");cell.innerHTML="";}else{if(sameDay(d,today))cell.classList.add("today");const label=d.getDate()===1?`${d.getMonth()+1}/1`:`${d.getDate()}`;cell.innerHTML=`<span class="num">${label}</span>`;}week.appendChild(cell);}
      const ranges=F.map(e=>({e,s:day(e.applyStart),x:day(e.applyEnd)})).filter(z=>z.s&&z.x&&z.x>=maxDate(ws,visibleStart)&&z.s<=we&&z.s<=gridEnd).sort((a,b)=>a.s-b.s||a.x-b.x),lanes=[];
      ranges.forEach(z=>{const s=maxDate(z.s,maxDate(ws,visibleStart)),x=minDate(z.x,minDate(we,gridEnd));if(s>x)return;const si=Math.round((s-ws)/86400000),xi=Math.round((x-ws)/86400000);let lane=lanes.findIndex(v=>v<si);if(lane<0)lane=lanes.length;lanes[lane]=xi;const b=makeButton("event-bar",`<strong>${esc(eventLabel(z.e))}</strong><span>${esc(displayTitle(z.e))}｜${esc(saleCategory(z.e))}</span>`,z.e,`申込期間: ${fmt(z.e.applyStart)} 〜 ${fmt(z.e.applyEnd)}`);b.style.left=`calc(${si/7*100}% + 4px)`;b.style.width=`calc(${(xi-si+1)/7*100}% - 8px)`;b.style.top=`${31+lane*55}px`;week.appendChild(b);});
      const milestones=[];F.forEach(e=>[[e.applyEnd,"⏰","申込締切"],[e.resultDate,"🎫","当落"],[e.paymentEnd,"💳","入金期限"],[e.eventDate,"🎤",Number(e.eventCount||0)>1?"公演初日":"公演日"]].forEach(([v,icon,label])=>{const d=day(v);if(d&&d>=visibleStart&&d>=ws&&d<=we&&d<=gridEnd)milestones.push({e,d,v,icon,label});}));
      const counts=Array(7).fill(0),base=31+lanes.length*55;milestones.sort((a,b)=>a.d-b.d).forEach(item=>{const idx=Math.round((item.d-ws)/86400000),row=counts[idx]++;const b=makeButton("milestone",esc(`${item.icon} ${displayTitle(item.e)}｜${item.label}`),item.e,`${item.label}: ${fmt(item.v)}`);b.style.left=`calc(${idx/7*100}% + 4px)`;b.style.width=`calc(${100/7}% - 8px)`;b.style.top=`${base+row*29}px`;week.appendChild(b);});week.style.minHeight=`${Math.max(132,base+Math.max(0,...counts)*29+8)}px`;calendar.appendChild(week);
    } prev.disabled=gridStart.getTime()===initialGridStart.getTime();
  }

  function renderList(){const F=filtered();summary.textContent=`${F.length}件掲載中・うち受付中 ${F.filter(e=>status(e)==="受付中").length}件`;list.innerHTML=F.sort((a,b)=>(parse(a.applyEnd)||parse(a.eventDate))-(parse(b.applyEnd)||parse(b.eventDate))).map(e=>{const u=urls(e),p=participants(e),application=noCurrentSale(e)?"現在受付なし":`${fmt(e.applyStart)} 〜 ${fmt(e.applyEnd)}`;return `<article class="card ${cls[e.group]||""}"><div class="card-top"><div><div class="event-date">🎤 ${esc(eventLabel(e))}</div><div class="group">${esc(e.group||"")}</div><h3>${esc(displayTitle(e))}</h3></div><span class="status">${esc(status(e))}</span></div><dl class="meta"><div><dt>販売区分</dt><dd>${esc(saleCategory(e))}</dd></div><div><dt>受付名</dt><dd>${esc(e.ticketType||"未定")}</dd></div><div><dt>対象</dt><dd>${esc(audience(e))}</dd></div><div><dt>申込期間</dt><dd>${esc(application)}</dd></div><div><dt>公演</dt><dd>${esc(eventLabel(e))}</dd></div><div><dt>会場</dt><dd>${esc(e.venue||"未定")}</dd></div>${p.length?`<div><dt>参加グループ</dt><dd>${esc(p.join(" / "))}</dd></div>`:""}</dl>${u.length?`<a class="source-link" href="${esc(u[0])}" target="_blank" rel="noopener">公式情報を確認する →</a>`:""}</article>`;}).join("");}

  const render=()=>{renderCalendar();renderList();};filters.forEach(b=>b.onclick=()=>{selected=b.dataset.group||"all";filters.forEach(x=>x.classList.toggle("is-active",x===b));render();});prev.onclick=()=>{const gs=add(windowStart,-windowStart.getDay()),prevStart=add(gs,-35);windowStart=prevStart<initialGridStart?today:prevStart;renderCalendar();};next.onclick=()=>{const gs=add(windowStart,-windowStart.getDay());windowStart=add(gs,35);renderCalendar();};render();
});