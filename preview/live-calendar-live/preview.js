document.addEventListener("DOMContentLoaded", async () => {
  const DATA_URL = "https://raw.githubusercontent.com/keio-kawaiilab/keio-kawaii-lab/feature/live-ticket-calendar/data/live-events.json";
  const calendar = document.getElementById("live-calendar");
  const monthLabel = document.getElementById("calendar-month");
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
  const range = (e) => { const a=parse(e.eventDate),b=parse(e.eventEndDate); if(!a)return"日程未定"; if(!b||sameDay(a,b))return`${a.getMonth()+1}/${a.getDate()}`; return a.getMonth()===b.getMonth()?`${a.getMonth()+1}/${a.getDate()}–${b.getDate()}`:`${a.getMonth()+1}/${a.getDate()}–${b.getMonth()+1}/${b.getDate()}`; };
  const eventLabel = (e) => Number(e.eventCount||0)>1?`${range(e)}・全${e.eventCount}公演`:range(e);
  const participants = (e) => Array.isArray(e.participants)?e.participants:[];
  const matches = (e,g) => g==="all"||e.group===g||participants(e).includes(g);
  const urls = (e) => { const a=Array.isArray(e.urls)?[...e.urls.filter(Boolean)]:[]; if(e.url&&!a.includes(e.url))a.unshift(e.url); return a; };
  const status = (e) => { const s=parse(e.applyStart),x=parse(e.applyEnd),n=new Date(); if(s&&n<s)return"受付前"; if(s&&x&&n>=s&&n<=x)return"受付中"; if(x&&n>x)return"受付終了"; return"日程確認中"; };

  let events=[];
  try {
    const r=await fetch(DATA_URL+"?t="+Date.now(),{cache:"no-store"});
    if(!r.ok) throw new Error();
    const data=await r.json();
    const today=day(new Date());
    events=(Array.isArray(data.events)?data.events:[]).filter(e=>{const last=day(e.eventEndDate)||day(e.eventDate);return !last||last>=today;});
    sourceNote.innerHTML=`<strong>公式公開情報から自動取得</strong>　${esc(data.updatedAt||"")} 更新 / ${events.length}件`;
  } catch (_) { sourceNote.textContent="データを読み込めませんでした。"; }

  const today=day(new Date());
  let selected="all", y=today.getFullYear(), m=today.getMonth();
  const filtered=()=>events.filter(e=>matches(e,selected));

  const showDetail=(e,focus="")=>{
    const p=participants(e),u=urls(e),schedule=Array.isArray(e.schedule)?e.schedule:[];
    const scheduleText=schedule.length>1?schedule.map(x=>`${String(x.date||"").slice(5).replace("-","/")} ${x.venue||"会場未定"}`).join(" / "):"";
    detail.innerHTML=`<strong>${esc(eventLabel(e))}｜${esc(e.title||"ライブ情報")}</strong><span>${esc(e.group||"KAWAII LAB.")}｜${esc(e.ticketType||"チケット受付")}</span>${p.length?`<span>参加: ${esc(p.join(" / "))}</span>`:""}${scheduleText?`<span>日程: ${esc(scheduleText)}</span>`:""}${focus?`<span>${esc(focus)}</span>`:""}${u.length?`<a href="${esc(u[0])}" target="_blank" rel="noopener">公式情報を確認する →</a>`:""}`;
  };
  const makeButton=(className,html,e,focus)=>{const b=document.createElement("button");b.type="button";b.className=`${className} ${cls[e.group]||""}`;b.innerHTML=html;b.onclick=()=>showDetail(e,focus);return b;};

  function renderCalendar(){
    monthLabel.textContent=`${y}年${m+1}月`;
    calendar.innerHTML="";
    const monthStart=new Date(y,m,1),monthEnd=new Date(y,m+1,0);
    const isCurrent=y===today.getFullYear()&&m===today.getMonth();
    const visibleStart=isCurrent?today:monthStart;
    const gridStart=add(visibleStart,-visibleStart.getDay()),gridEnd=add(monthEnd,6-monthEnd.getDay());
    const weeks=Math.floor((gridEnd-gridStart)/604800000)+1,F=filtered();

    for(let w=0;w<weeks;w++){
      const ws=add(gridStart,w*7),we=add(ws,6); if(we<visibleStart)continue;
      const week=document.createElement("div"); week.className="week";
      for(let i=0;i<7;i++){
        const d=add(ws,i),cell=document.createElement("div"); cell.className="day";
        const hidden=d<visibleStart||d.getMonth()!==m;
        if(hidden){cell.classList.add("other");cell.innerHTML="";}
        else{if(sameDay(d,today))cell.classList.add("today");const label=d.getDate()===1?`${d.getMonth()+1}/1`:`${d.getDate()}`;cell.innerHTML=`<span class="num">${label}</span>`;}
        week.appendChild(cell);
      }

      const ranges=F.map(e=>({e,s:day(e.applyStart),x:day(e.applyEnd)})).filter(z=>z.s&&z.x&&z.x>=maxDate(ws,visibleStart)&&z.s<=minDate(we,monthEnd)).sort((a,b)=>a.s-b.s||a.x-b.x),lanes=[];
      ranges.forEach(z=>{
        const s=maxDate(z.s,maxDate(ws,visibleStart)),x=minDate(z.x,minDate(we,monthEnd)); if(s>x)return;
        const si=Math.round((s-ws)/86400000),xi=Math.round((x-ws)/86400000); let lane=lanes.findIndex(v=>v<si);if(lane<0)lane=lanes.length;lanes[lane]=xi;
        const b=makeButton("event-bar",`<strong>${esc(eventLabel(z.e))}</strong><span>${esc(z.e.group||"")}｜${esc(z.e.title||"")}｜${esc(z.e.ticketType||"受付")}</span>`,z.e,`${fmt(z.e.applyStart)} 〜 ${fmt(z.e.applyEnd)}`);
        b.style.left=`calc(${si/7*100}% + 4px)`;b.style.width=`calc(${(xi-si+1)/7*100}% - 8px)`;b.style.top=`${31+lane*55}px`;week.appendChild(b);
      });

      const milestones=[];
      F.forEach(e=>[[e.applyEnd,"⏰","申込締切"],[e.resultDate,"🎫","当落"],[e.paymentEnd,"💳","入金期限"],[e.eventDate,"🎤",Number(e.eventCount||0)>1?"公演初日":"公演日"]].forEach(([v,icon,label])=>{const d=day(v);if(d&&d>=visibleStart&&d>=ws&&d<=we&&d<=monthEnd)milestones.push({e,d,v,icon,label});}));
      const counts=Array(7).fill(0),base=31+lanes.length*55;
      milestones.sort((a,b)=>a.d-b.d).forEach(item=>{const idx=Math.round((item.d-ws)/86400000),row=counts[idx]++;const b=makeButton("milestone",esc(`${item.icon} ${eventLabel(item.e)} ${item.label}`),item.e,`${item.label}: ${fmt(item.v)}`);b.style.left=`calc(${idx/7*100}% + 4px)`;b.style.width=`calc(${100/7}% - 8px)`;b.style.top=`${base+row*29}px`;week.appendChild(b);});
      week.style.minHeight=`${Math.max(132,base+Math.max(0,...counts)*29+8)}px`;calendar.appendChild(week);
    }
    prev.disabled=y===today.getFullYear()&&m===today.getMonth();
  }

  function renderList(){
    const F=filtered(); summary.textContent=`${F.length}件掲載中・うち受付中 ${F.filter(e=>status(e)==="受付中").length}件`;
    list.innerHTML=F.sort((a,b)=>(parse(a.applyEnd)||parse(a.eventDate))-(parse(b.applyEnd)||parse(b.eventDate))).map(e=>{const u=urls(e),p=participants(e);return `<article class="card ${cls[e.group]||""}"><div class="card-top"><div><div class="event-date">🎤 ${esc(eventLabel(e))}</div><div class="group">${esc(e.group||"")}</div><h3>${esc(e.title||"")}</h3></div><span class="status">${esc(status(e))}</span></div><dl class="meta"><div><dt>受付種別</dt><dd>${esc(e.ticketType||"未定")}</dd></div><div><dt>申込期間</dt><dd>${esc(fmt(e.applyStart))} 〜 ${esc(fmt(e.applyEnd))}</dd></div><div><dt>公演</dt><dd>${esc(eventLabel(e))}</dd></div><div><dt>会場</dt><dd>${esc(e.venue||"未定")}</dd></div>${p.length?`<div><dt>参加グループ</dt><dd>${esc(p.join(" / "))}</dd></div>`:""}</dl>${u.length?`<a class="source-link" href="${esc(u[0])}" target="_blank" rel="noopener">公式情報を確認する →</a>`:""}</article>`;}).join("");
  }

  const render=()=>{renderCalendar();renderList();};
  filters.forEach(b=>b.onclick=()=>{selected=b.dataset.group||"all";filters.forEach(x=>x.classList.toggle("is-active",x===b));render();});
  prev.onclick=()=>{if(prev.disabled)return;m--;if(m<0){m=11;y--;}renderCalendar();};
  next.onclick=()=>{m++;if(m>11){m=0;y++;}renderCalendar();};
  render();
});
