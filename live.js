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
    "MORE STAR": "group-more"
  };

  const esc = (value = "") => String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const parseDate = (value) => {
    if (!value) return null;
    const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);
    if (!match) return null;
    return new Date(
      Number(match[1]), Number(match[2]) - 1, Number(match[3]),
      Number(match[4] || 0), Number(match[5] || 0), 0, 0
    );
  };

  const dayOnly = (value) => {
    const d = value instanceof Date ? value : parseDate(value);
    return d ? new Date(d.getFullYear(), d.getMonth(), d.getDate()) : null;
  };

  const addDays = (date, amount) => new Date(date.getFullYear(), date.getMonth(), date.getDate() + amount);
  const sameDay = (a, b) => a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  const clampDate = (date, min, max) => date < min ? min : date > max ? max : date;

  const fmt = (value) => {
    const d = parseDate(value);
    if (!d || Number.isNaN(d.getTime())) return "未定";
    const hasTime = String(value).includes("T");
    return new Intl.DateTimeFormat("ja-JP", {
      year: "numeric", month: "numeric", day: "numeric",
      hour: hasTime ? "2-digit" : undefined,
      minute: hasTime ? "2-digit" : undefined
    }).format(d);
  };

  const fmtShortDate = (value) => {
    const d = parseDate(value);
    if (!d) return "日程未定";
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  const getStatus = (event) => {
    const now = new Date();
    const start = parseDate(event.applyStart);
    const end = parseDate(event.applyEnd);
    if (start && now < start) return { label: "受付前", cls: "" };
    if (start && end && now >= start && now <= end) {
      const hours = (end - now) / 36e5;
      return hours <= 24 ? { label: "24時間以内に締切", cls: "soon" } : { label: "受付中", cls: "open" };
    }
    if (end && now > end) return { label: "受付終了", cls: "" };
    return { label: "日程確認中", cls: "" };
  };

  const detailHtml = (event, focus = "") => {
    const eventDate = fmtShortDate(event.eventDate);
    const ticketType = event.ticketType || "チケット受付";
    const focusText = focus ? `<br><span>${esc(focus)}</span>` : "";
    return `<strong>${esc(eventDate)}開催｜${esc(event.title || "ライブ情報")}</strong><span>${esc(event.group || "KAWAII LAB.")}｜${esc(ticketType)}</span>${focusText}`;
  };

  let events = [];
  let isDemo = false;
  try {
    const response = await fetch("./data/live-events.json", { cache: "no-store" });
    if (!response.ok) throw new Error("failed");
    const data = await response.json();
    events = Array.isArray(data.events) ? data.events : [];
    isDemo = Boolean(data.demo);
    if (demoBanner) demoBanner.hidden = !isDemo;
  } catch (_) {
    summary.textContent = "ライブ情報を読み込めませんでした。時間をおいて再度お試しください。";
  }

  let selected = "all";
  const today = new Date();
  let shownYear = today.getFullYear();
  let shownMonth = today.getMonth();

  const filteredEvents = () => selected === "all" ? events : events.filter((e) => e.group === selected);

  const renderList = () => {
    const filtered = filteredEvents();
    const openCount = filtered.filter((e) => ["open", "soon"].includes(getStatus(e).cls)).length;
    summary.textContent = filtered.length
      ? `${filtered.length}件掲載中・うち受付中 ${openCount}件`
      : "現在、掲載中のライブ・チケット受付情報はありません。";

    if (!filtered.length) {
      list.innerHTML = '<div class="live-empty">新しい公式情報を取得すると、ここに自動で追加される予定です。</div>';
      return;
    }

    const sorted = [...filtered].sort((a, b) => {
      const ad = parseDate(a.applyEnd) || parseDate(a.eventDate) || new Date(2999, 0, 1);
      const bd = parseDate(b.applyEnd) || parseDate(b.eventDate) || new Date(2999, 0, 1);
      return ad - bd;
    });

    list.innerHTML = sorted.map((event) => {
      const status = getStatus(event);
      const cls = groupClass[event.group] || "";
      const source = event.url
        ? `<a class="live-link" href="${esc(event.url)}" target="_blank" rel="noopener noreferrer">公式情報を確認する →</a>`
        : "";
      return `
        <article class="live-card ${cls}">
          <div class="live-card-top">
            <div>
              <div class="live-event-date">🎤 ${esc(fmtShortDate(event.eventDate))}開催</div>
              <div class="live-group">${esc(event.group || "KAWAII LAB.")}</div>
              <h3>${esc(event.title || "ライブ情報")}</h3>
            </div>
            <span class="live-status ${status.cls}">${esc(status.label)}</span>
          </div>
          <dl class="live-meta">
            <div><dt>受付種別</dt><dd>${esc(event.ticketType || "未定")}</dd></div>
            <div><dt>公演日</dt><dd>${fmt(event.eventDate)}</dd></div>
            <div><dt>申込開始</dt><dd>${fmt(event.applyStart)}</dd></div>
            <div><dt>申込締切</dt><dd>${fmt(event.applyEnd)}</dd></div>
            <div><dt>当落発表</dt><dd>${fmt(event.resultDate)}</dd></div>
            <div><dt>入金期限</dt><dd>${fmt(event.paymentEnd)}</dd></div>
            <div><dt>会場</dt><dd>${esc(event.venue || "未定")}</dd></div>
          </dl>
          ${source}
        </article>`;
    }).join("");
  };

  const makeButton = (className, text, event, focus) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `${className} ${groupClass[event.group] || ""}`;
    button.innerHTML = text;
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
    const gridStart = addDays(monthStart, -monthStart.getDay());
    const gridEnd = addDays(monthEnd, 6 - monthEnd.getDay());
    const weekCount = Math.round((gridEnd - gridStart) / 86400000 / 7) + 1;
    const filtered = filteredEvents();

    for (let w = 0; w < weekCount; w += 1) {
      const weekStart = addDays(gridStart, w * 7);
      const weekEnd = addDays(weekStart, 6);
      const week = document.createElement("div");
      week.className = "calendar-week";

      for (let d = 0; d < 7; d += 1) {
        const date = addDays(weekStart, d);
        const cell = document.createElement("div");
        cell.className = "calendar-day";
        if (date.getMonth() !== shownMonth) cell.classList.add("is-other");
        if (d === 0) cell.classList.add("is-sun");
        if (d === 6) cell.classList.add("is-sat");
        cell.innerHTML = `<span class="calendar-day-number">${date.getDate()}</span>`;
        week.appendChild(cell);
      }

      const ranges = filtered
        .map((event) => ({ event, start: dayOnly(event.applyStart), end: dayOnly(event.applyEnd) }))
        .filter((item) => item.start && item.end && item.end >= weekStart && item.start <= weekEnd)
        .sort((a, b) => a.start - b.start || a.end - b.end);

      const laneEnds = [];
      ranges.forEach((item) => {
        const visibleStart = clampDate(item.start, weekStart, weekEnd);
        const visibleEnd = clampDate(item.end, weekStart, weekEnd);
        const startIndex = Math.round((visibleStart - weekStart) / 86400000);
        const endIndex = Math.round((visibleEnd - weekStart) / 86400000);
        let lane = laneEnds.findIndex((end) => end < startIndex);
        if (lane < 0) lane = laneEnds.length;
        laneEnds[lane] = endIndex;

        const event = item.event;
        const dateLabel = `${fmtShortDate(event.eventDate)}開催`;
        const title = `${esc(dateLabel)}<span>${esc(event.group || "KAWAII LAB.")}｜${esc(event.title || "ライブ")}｜${esc(event.ticketType || "受付")}</span>`;
        const bar = makeButton("calendar-event-bar", `<strong>${title}</strong>`, event, `${fmt(event.applyStart)} 〜 ${fmt(event.applyEnd)}`);
        bar.style.left = `calc(${(startIndex / 7) * 100}% + 4px)`;
        bar.style.width = `calc(${((endIndex - startIndex + 1) / 7) * 100}% - 8px)`;
        bar.style.top = `${31 + lane * 55}px`;
        bar.setAttribute("aria-label", `${dateLabel} ${event.group || ""} ${event.title || ""} ${event.ticketType || ""}`);
        week.appendChild(bar);
      });

      const milestones = [];
      filtered.forEach((event) => {
        const defs = [
          [event.applyEnd, "⏰", "申込締切"],
          [event.resultDate, "🎫", "当落発表"],
          [event.paymentEnd, "💳", "入金期限"],
          [event.eventDate, "🎤", "公演日"]
        ];
        defs.forEach(([value, icon, label]) => {
          const date = dayOnly(value);
          if (date && date >= weekStart && date <= weekEnd) milestones.push({ event, date, icon, label, value });
        });
      });

      const perDayCount = Array(7).fill(0);
      const milestoneBase = 31 + laneEnds.length * 55;
      milestones.sort((a, b) => a.date - b.date).forEach((item) => {
        const dayIndex = Math.round((item.date - weekStart) / 86400000);
        const row = perDayCount[dayIndex]++;
        const compactName = item.event.title || "ライブ";
        const text = `${item.icon} ${fmtShortDate(item.event.eventDate)}公演 ${item.label}`;
        const button = makeButton("calendar-milestone", esc(text), item.event, `${item.label}: ${fmt(item.value)}`);
        button.title = `${compactName}｜${item.label}`;
        button.style.left = `calc(${(dayIndex / 7) * 100}% + 4px)`;
        button.style.width = `calc(${100 / 7}% - 8px)`;
        button.style.top = `${milestoneBase + row * 29}px`;
        week.appendChild(button);
      });

      const maxMilestones = Math.max(0, ...perDayCount);
      week.style.minHeight = `${Math.max(132, milestoneBase + maxMilestones * 29 + 8)}px`;
      calendar.appendChild(week);
    }
  };

  const renderAll = () => {
    renderCalendar();
    renderList();
  };

  filters.forEach((button) => {
    button.addEventListener("click", () => {
      selected = button.dataset.group || "all";
      filters.forEach((b) => b.classList.toggle("is-active", b === button));
      renderAll();
    });
  });

  prevButton?.addEventListener("click", () => {
    shownMonth -= 1;
    if (shownMonth < 0) { shownMonth = 11; shownYear -= 1; }
    renderCalendar();
  });

  nextButton?.addEventListener("click", () => {
    shownMonth += 1;
    if (shownMonth > 11) { shownMonth = 0; shownYear += 1; }
    renderCalendar();
  });

  renderAll();
});
