document.addEventListener("DOMContentLoaded", async () => {
  const calendar = document.getElementById("live-calendar");
  const periodLabel = document.getElementById("calendar-month");
  const detail = document.getElementById("calendar-detail");
  if (!calendar || !periodLabel) return;

  const dataUrl = "https://raw.githubusercontent.com/keio-kawaiilab/keio-kawaii-lab/feature/live-ticket-calendar/data/live-events.json";
  const groupClass = {
    "FRUITS ZIPPER": "group-fruits",
    "CANDY TUNE": "group-candy",
    "SWEET STEADY": "group-sweet",
    "CUTIE STREET": "group-cutie",
    "MORE STAR": "group-more",
    "KAWAII LAB.合同": "group-lab"
  };
  const groupNames = Object.keys(groupClass);
  const esc = (v = "") => String(v)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  const parseDay = (value) => {
    const m = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
  };
  const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
  const cleanTitle = (event) => {
    let title = String(event.title || "ライブ情報").replace(/^20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+/, "").trim();
    const quoted = title.match(/「([^」]+)」/);
    if (quoted) return quoted[1].trim();
    title = title.replace(/^(?:20\d{2}年)?\d{1,2}月\d{1,2}日(?:\([^)]*\)|（[^）]*）)?\s*/, "");
    title = title.split(/\s*@|開催決定|出演決定|アップグレード抽選受付|一般(?:発売|販売|先行)|FC\s*(?:会員)?先行|ファンクラブ|OFFICIAL FANCLUB|先行受付|チケット受付|受付のお知らせ/)[0];
    return title.replace(/[!！\s\-–—｜|]+$/g, "").trim() || String(event.title || "ライブ情報");
  };
  const occurrences = (event) => {
    const rows = [];
    if (Array.isArray(event.schedule) && event.schedule.length) {
      event.schedule.forEach((x) => rows.push({ date: String(x.date || "").slice(0, 10), venue: x.venue || event.venue || null }));
    } else if (Array.isArray(event.eventDates) && event.eventDates.length) {
      event.eventDates.forEach((x) => rows.push({ date: String(x).slice(0, 10), venue: event.venue || null }));
    } else if (event.eventDate) {
      rows.push({ date: String(event.eventDate).slice(0, 10), venue: event.venue || null });
    }
    const seen = new Set();
    return rows.filter((x) => {
      if (!parseDay(x.date) || seen.has(x.date)) return false;
      seen.add(x.date);
      return true;
    });
  };

  let events = [];
  try {
    const response = await fetch(dataUrl + "?performanceDates=" + Date.now(), { cache: "no-store" });
    if (!response.ok) return;
    const data = await response.json();
    events = Array.isArray(data.events) ? data.events : [];
  } catch (_) {
    return;
  }

  const uniquePerformances = [];
  const seenPerformances = new Set();
  for (const event of events) {
    for (const occurrence of occurrences(event)) {
      const key = [event.group, cleanTitle(event), occurrence.date].join("\u001f");
      if (seenPerformances.has(key)) continue;
      seenPerformances.add(key);
      uniquePerformances.push({ event, ...occurrence });
    }
  }

  const getWindow = () => {
    const match = periodLabel.textContent.match(/(\d{1,2})\/(\d{1,2})\s*[〜～]\s*(\d{1,2})\/(\d{1,2})/);
    if (!match) return null;
    const now = new Date();
    let year = now.getFullYear();
    const startMonth = Number(match[1]);
    if (startMonth < now.getMonth() + 1 - 6) year += 1;
    const visibleStart = new Date(year, startMonth - 1, Number(match[2]));
    const gridStart = addDays(visibleStart, -visibleStart.getDay());
    return { visibleStart, gridStart };
  };

  let running = false;
  const enhance = () => {
    if (running) return;
    running = true;
    try {
      const windowInfo = getWindow();
      if (!windowInfo) return;
      calendar.querySelectorAll(".performance-date-marker").forEach((node) => node.remove());
      calendar.querySelectorAll(".milestone").forEach((node) => {
        if (node.textContent.trim().startsWith("🎤")) node.style.display = "none";
      });
      calendar.querySelectorAll(".event-bar span").forEach((span) => {
        let text = span.textContent;
        for (const group of groupNames) text = text.replace(`${group}｜`, "");
        if (text !== span.textContent) span.textContent = text;
      });

      const weeks = [...calendar.querySelectorAll(".week")];
      weeks.forEach((week, weekIndex) => {
        const weekStart = addDays(windowInfo.gridStart, weekIndex * 7);
        const weekEnd = addDays(weekStart, 6);
        let baseTop = 31;
        week.querySelectorAll(".event-bar, .milestone").forEach((node) => {
          if (node.classList.contains("performance-date-marker") || node.style.display === "none") return;
          const top = Number.parseFloat(node.style.top || "0") || 0;
          const height = node.offsetHeight || (node.classList.contains("event-bar") ? 52 : 29);
          baseTop = Math.max(baseTop, top + height + 4);
        });

        const rows = Array(7).fill(0);
        uniquePerformances.forEach((item) => {
          const d = parseDay(item.date);
          if (!d || d < windowInfo.visibleStart || d < weekStart || d > weekEnd) return;
          const dayIndex = Math.round((d - weekStart) / 86400000);
          const row = rows[dayIndex]++;
          const button = document.createElement("button");
          button.type = "button";
          button.className = `milestone performance-date-marker ${groupClass[item.event.group] || ""}`;
          button.textContent = `🎤 ${cleanTitle(item.event)}`;
          button.style.left = `calc(${dayIndex / 7 * 100}% + 4px)`;
          button.style.width = `calc(${100 / 7}% - 8px)`;
          button.style.top = `${baseTop + row * 29}px`;
          button.addEventListener("click", () => {
            if (!detail) return;
            const dText = `${d.getMonth() + 1}/${d.getDate()}`;
            detail.innerHTML = `<strong>${esc(cleanTitle(item.event))}</strong><span>公演日: ${esc(dText)}</span><span>会場: ${esc(item.venue || item.event.venue || "未定")}</span><span>グループ: ${esc(item.event.group || "KAWAII LAB.")}</span>`;
          });
          week.appendChild(button);
        });
        const maxRows = Math.max(0, ...rows);
        if (maxRows) week.style.minHeight = `${Math.max(Number.parseFloat(getComputedStyle(week).minHeight) || 0, baseTop + maxRows * 29 + 8)}px`;
      });
    } finally {
      running = false;
    }
  };

  let timer = null;
  const queueEnhance = () => {
    clearTimeout(timer);
    timer = setTimeout(enhance, 60);
  };
  const calendarObserver = new MutationObserver((mutations) => {
    const hasExternalChange = mutations.some((mutation) => {
      const nodes = [...mutation.addedNodes, ...mutation.removedNodes];
      return nodes.some((node) => node.nodeType === 1 && !node.classList.contains("performance-date-marker"));
    });
    if (hasExternalChange) queueEnhance();
  });
  calendarObserver.observe(calendar, { childList: true, subtree: true });
  new MutationObserver(queueEnhance).observe(periodLabel, { childList: true, characterData: true, subtree: true });
  document.querySelectorAll(".live-filter, #calendar-prev, #calendar-next").forEach((button) => button.addEventListener("click", queueEnhance));
  queueEnhance();
});
