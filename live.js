document.addEventListener("DOMContentLoaded", async () => {
  const list = document.getElementById("live-list");
  const summary = document.getElementById("live-summary");
  const filters = [...document.querySelectorAll(".live-filter")];
  const calendar = document.getElementById("live-calendar");
  const calendarMonth = document.getElementById("calendar-month");
  const calendarDetail = document.getElementById("calendar-detail");
  const prevButton = document.getElementById("calendar-prev");
  const nextButton = document.getElementById("calendar-next");
  const demoBanner = document.getElementById("live-demo-banner");
  if (!list || !summary || !calendar || !calendarMonth) return;

  const groupClass = {
    "FRUITS ZIPPER": "group-fruits",
    "CANDY TUNE": "group-candy",
    "SWEET STEADY": "group-sweet",
    "CUTIE STREET": "group-cutie",
    "MORE STAR": "group-more",
    "KAWAII LAB.合同": "group-lab"
  };

  const esc = (v = "") => String(v)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");

  const parseDate = (value) => {
    const m = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);
    if (!m) return null;
    return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0));
  };
  const dayOnly = (value) => {
    const d = value instanceof Date ? value : parseDate(value);
    return d ? new Date(d.getFullYear(), d.getMonth(), d.getDate()) : null;
  };
  const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
  const maxDate = (a, b) => a > b ? a : b;
  const minDate = (a, b) => a < b ? a : b;
  const sameDay = (a, b) => a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

  const fmt = (value) => {
    const d = parseDate(value);
    if (!d) return "未定";
    const hasTime = String(value).includes("T");
    return new Intl.DateTimeFormat("ja-JP", {
      year: "numeric", month: "numeric", day: "numeric",
      hour: hasTime ? "2-digit" : undefined,
      minute: hasTime ? "2-digit" : undefined
    }).format(d);
  };

  const shortRange = (event) => {
    const a = parseDate(event.eventDate);
    const b = parseDate(event.eventEndDate);
    if (!a) return "日程未定";
    if (!b || sameDay(a, b)) return `${a.getMonth() + 1}/${a.getDate()}`;
    if (a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth()) {
      return `${a.getMonth() + 1}/${a.getDate()}–${b.getDate()}`;
    }
    return `${a.getMonth() + 1}/${a.getDate()}–${b.getMonth() + 1}/${b.getDate()}`;
  };
  const eventLabel = (event) => {
    const count = Number(event.eventCount || 0);
    const base = shortRange(event);
    return count > 1 ? `${base}・全${count}公演` : base;
  };
  const longRange = (event) => {
    const count = Number(event.eventCount || 0);
    const base = event.eventEndDate ? `${fmt(event.eventDate)} 〜 ${fmt(event.eventEndDate)}` : fmt(event.eventDate);
    return count > 1 ? `${base}（全${count}公演）` : base;
  };
  const participants = (event) => Array.isArray(event.participants) ? event.participants : [];
  const matchesGroup = (event, group) => group === "all" || event.group === group || participants(event).includes(group);
  const sourceUrls = (event) => {
    const urls = Array.isArray(event.urls) ? [...event.urls.filter(Boolean)] : [];
    if (event.url && !urls.includes(event.url)) urls.unshift(event.url);
    return urls;
  };
  const status = (event) => {
    const now = new Date();
    const start = parseDate(event.applyStart);
    const end = parseDate(event.applyEnd);
    if (start && now < start) return { label: "受付前", cls: "" };
    if (start && end && now >= start && now <= end) {
      return (end - now) / 36e5 <= 24
        ? { label: "24時間以内に締切", cls: "soon" }
        : { label: "受付中", cls: "open" };
    }
    if (end && now > end) return { label: "受付終了", cls: "" };
    return { label: "日程確認中", cls: "" };
  };

  const scheduleText = (event) => {
    const schedule = Array.isArray(event.schedule) ? event.schedule : [];
    if (schedule.length <= 1) return "";
    return schedule.map((x) => `${String(x.date || "").slice(5).replace("-", "/")} ${x.venue || "会場未定"}`).join(" / ");
  };

  const detailHtml = (event, focus = "") => {
    const p = participants(event);
    const urls = sourceUrls(event);
    const schedule = scheduleText(event);
    return `<strong>${esc(eventLabel(event))}｜${esc(event.title || "ライブ情報")}</strong>
      <span>${esc(event.group || "KAWAII LAB.")}｜${esc(event.ticketType || "チケット受付")}</span>
      ${p.length ? `<span>参加: ${esc(p.join(" / "))}</span>` : ""}
      ${schedule ? `<span>日程: ${esc(schedule)}</span>` : ""}
      ${focus ? `<span>${esc(focus)}</span>` : ""}
      ${urls.length ? `<a href="${esc(urls[0])}" target="_blank" rel="noopener noreferrer">公式情報を確認する →</a>` : ""}`;
  };

  let events = [];
  try {
    const response = await fetch("./data/live-events.json", { cache: "no-store" });
    if (!response.ok) throw new Error("failed");
    const data = await response.json();
    const today = dayOnly(new Date());
    events = (Array.isArray(data.events) ? data.events : []).filter((event) => {
      const last = dayOnly(event.eventEndDate) || dayOnly(event.eventDate);
      return !last || last >= today;
    });
    if (demoBanner) demoBanner.hidden = !Boolean(data.demo);
  } catch (_) {
    summary.textContent = "ライブ情報を読み込めませんでした。時間をおいて再度お試しください。";
  }

  const today = dayOnly(new Date());
  let selected = "all";
  let shownYear = today.getFullYear();
  let shownMonth = today.getMonth();
  const filteredEvents = () => events.filter((event) => matchesGroup(event, selected));

  const renderList = () => {
    const filtered = filteredEvents();
    const openCount = filtered.filter((event) => ["open", "soon"].includes(status(event).cls)).length;
    summary.textContent = filtered.length ? `${filtered.length}件掲載中・うち受付中 ${openCount}件` : "現在、掲載中のライブ・チケット受付情報はありません。";
    if (!filtered.length) {
      list.innerHTML = '<div class="live-empty">現在、掲載中の未来公演はありません。</div>';
      return;
    }
    const sorted = [...filtered].sort((a, b) => (parseDate(a.applyEnd) || parseDate(a.eventDate)) - (parseDate(b.applyEnd) || parseDate(b.eventDate)));
    list.innerHTML = sorted.map((event) => {
      const st = status(event);
      const urls = sourceUrls(event);
      const p = participants(event);
      return `<article class="live-card ${groupClass[event.group] || ""}">
        <div class="live-card-top"><div>
          <div class="live-event-date">🎤 ${esc(eventLabel(event))}</div>
          <div class="live-group">${esc(event.group || "KAWAII LAB.")}</div>
          <h3>${esc(event.title || "ライブ情報")}</h3>
        </div><span class="live-status ${st.cls}">${esc(st.label)}</span></div>
        <dl class="live-meta">
          <div><dt>受付種別</dt><dd>${esc(event.ticketType || "未定")}</dd></div>
          <div><dt>公演日</dt><dd>${esc(longRange(event))}</dd></div>
          ${p.length ? `<div><dt>参加グループ</dt><dd>${esc(p.join(" / "))}</dd></div>` : ""}
          <div><dt>申込開始</dt><dd>${esc(fmt(event.applyStart))}</dd></div>
          <div><dt>申込締切</dt><dd>${esc(fmt(event.applyEnd))}</dd></div>
          <div><dt>当落発表</dt><dd>${esc(fmt(event.resultDate))}</dd></div>
          <div><dt>入金期限</dt><dd>${esc(fmt(event.paymentEnd))}</dd></div>
          <div><dt>会場</dt><dd>${esc(event.venue || "未定")}</dd></div>
        </dl>
        ${urls.length ? `<a class="live-link" href="${esc(urls[0])}" target="_blank" rel="noopener noreferrer">公式情報を確認する →</a>` : ""}
      </article>`;
    }).join("");
  };

  const makeButton = (cls, html, event, focus) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `${cls} ${groupClass[event.group] || ""}`;
    button.innerHTML = html;
    button.addEventListener("click", () => {
      if (calendarDetail) calendarDetail.innerHTML = detailHtml(event, focus);
    });
    return button;
  };

  const renderCalendar = () => {
    calendarMonth.textContent = `${shownYear}年${shownMonth + 1}月`;
    calendar.innerHTML = "";

    const monthStart = new Date(shownYear, shownMonth, 1);
    const monthEnd = new Date(shownYear, shownMonth + 1, 0);
    const isCurrentMonth = shownYear === today.getFullYear() && shownMonth === today.getMonth();
    const visibleStart = isCurrentMonth ? today : monthStart;
    const gridStart = addDays(visibleStart, -visibleStart.getDay());
    const gridEnd = addDays(monthEnd, 6 - monthEnd.getDay());
    const weekCount = Math.floor((gridEnd - gridStart) / 604800000) + 1;
    const filtered = filteredEvents();

    for (let w = 0; w < weekCount; w += 1) {
      const weekStart = addDays(gridStart, w * 7);
      const weekEnd = addDays(weekStart, 6);
      if (weekEnd < visibleStart) continue;
      const week = document.createElement("div");
      week.className = "calendar-week";

      for (let d = 0; d < 7; d += 1) {
        const date = addDays(weekStart, d);
        const cell = document.createElement("div");
        cell.className = "calendar-day";
        if (d === 0) cell.classList.add("is-sun");
        if (d === 6) cell.classList.add("is-sat");
        const hidden = date < visibleStart || date.getMonth() !== shownMonth;
        if (hidden) {
          cell.classList.add("is-other");
          cell.innerHTML = "";
        } else {
          if (sameDay(date, today)) cell.classList.add("is-today");
          const label = date.getDate() === 1 ? `${date.getMonth() + 1}/1` : `${date.getDate()}`;
          cell.innerHTML = `<span class="calendar-day-number">${label}</span>`;
        }
        week.appendChild(cell);
      }

      const ranges = filtered.map((event) => ({ event, start: dayOnly(event.applyStart), end: dayOnly(event.applyEnd) }))
        .filter((x) => x.start && x.end && x.end >= maxDate(weekStart, visibleStart) && x.start <= minDate(weekEnd, monthEnd))
        .sort((a, b) => a.start - b.start || a.end - b.end);
      const laneEnds = [];
      ranges.forEach((item) => {
        const start = maxDate(item.start, maxDate(weekStart, visibleStart));
        const end = minDate(item.end, minDate(weekEnd, monthEnd));
        if (start > end) return;
        const startIndex = Math.round((start - weekStart) / 86400000);
        const endIndex = Math.round((end - weekStart) / 86400000);
        let lane = laneEnds.findIndex((x) => x < startIndex);
        if (lane < 0) lane = laneEnds.length;
        laneEnds[lane] = endIndex;
        const label = eventLabel(item.event);
        const bar = makeButton(
          "calendar-event-bar",
          `<strong>${esc(label)}</strong><span>${esc(item.event.group || "KAWAII LAB.")}｜${esc(item.event.title || "ライブ")}｜${esc(item.event.ticketType || "受付")}</span>`,
          item.event,
          `${fmt(item.event.applyStart)} 〜 ${fmt(item.event.applyEnd)}`
        );
        bar.style.left = `calc(${startIndex / 7 * 100}% + 4px)`;
        bar.style.width = `calc(${(endIndex - startIndex + 1) / 7 * 100}% - 8px)`;
        bar.style.top = `${31 + lane * 55}px`;
        week.appendChild(bar);
      });

      const milestones = [];
      filtered.forEach((event) => {
        const defs = [
          [event.applyEnd, "⏰", "申込締切"],
          [event.resultDate, "🎫", "当落発表"],
          [event.paymentEnd, "💳", "入金期限"],
          [event.eventDate, "🎤", Number(event.eventCount || 0) > 1 ? "公演初日" : "公演日"]
        ];
        defs.forEach(([value, icon, label]) => {
          const date = dayOnly(value);
          if (date && date >= visibleStart && date >= weekStart && date <= weekEnd && date <= monthEnd) {
            milestones.push({ event, date, icon, label, value });
          }
        });
      });
      const perDay = Array(7).fill(0);
      const baseTop = 31 + laneEnds.length * 55;
      milestones.sort((a, b) => a.date - b.date).forEach((item) => {
        const index = Math.round((item.date - weekStart) / 86400000);
        const row = perDay[index]++;
        const button = makeButton(
          "calendar-milestone",
          esc(`${item.icon} ${eventLabel(item.event)} ${item.label}`),
          item.event,
          `${item.label}: ${fmt(item.value)}`
        );
        button.style.left = `calc(${index / 7 * 100}% + 4px)`;
        button.style.width = `calc(${100 / 7}% - 8px)`;
        button.style.top = `${baseTop + row * 29}px`;
        week.appendChild(button);
      });
      const maxRows = Math.max(0, ...perDay);
      week.style.minHeight = `${Math.max(132, baseTop + maxRows * 29 + 8)}px`;
      calendar.appendChild(week);
    }
  };

  const renderAll = () => { renderCalendar(); renderList(); };
  filters.forEach((button) => button.addEventListener("click", () => {
    selected = button.dataset.group || "all";
    filters.forEach((b) => b.classList.toggle("is-active", b === button));
    renderAll();
  }));
  prevButton?.addEventListener("click", () => {
    shownMonth -= 1;
    if (shownMonth < 0) { shownMonth = 11; shownYear -= 1; }
    if (shownYear < today.getFullYear() || (shownYear === today.getFullYear() && shownMonth < today.getMonth())) {
      shownYear = today.getFullYear(); shownMonth = today.getMonth();
    }
    renderCalendar();
  });
  nextButton?.addEventListener("click", () => {
    shownMonth += 1;
    if (shownMonth > 11) { shownMonth = 0; shownYear += 1; }
    renderCalendar();
  });
  renderAll();
});
