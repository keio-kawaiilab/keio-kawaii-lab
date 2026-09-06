document.addEventListener("DOMContentLoaded", async () => {
  const calendar = document.getElementById("live-calendar");
  const periodLabel = document.getElementById("calendar-month");
  const detail = document.getElementById("calendar-detail");
  if (!calendar || !periodLabel) return;

  const isPreview = location.pathname.includes("/preview/live-calendar-live/");
  const dataUrl = isPreview
    ? "https://raw.githubusercontent.com/keio-kawaiilab/keio-kawaii-lab/feature/live-ticket-calendar/data/live-events.json"
    : "./data/live-events.json";
  const weekSelector = isPreview ? ".week" : ".calendar-week";
  const barSelector = isPreview ? ".event-bar" : ".calendar-event-bar";
  const milestoneSelector = isPreview ? ".milestone" : ".calendar-milestone";
  const milestoneClass = isPreview ? "milestone" : "calendar-milestone";
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
  const participants = (event) => Array.isArray(event.participants) ? event.participants : [];
  const selectedGroup = () => document.querySelector(".live-filter.is-active")?.dataset.group || "all";
  const matchesSelectedGroup = (event) => {
    const selected = selectedGroup();
    return selected === "all" || event.group === selected || participants(event).includes(selected);
  };
  const sourceTitle = (event) => String(event.eventTitle || event.displayTitle || event.title || "ライブ情報");
  const cleanTitle = (event) => {
    let title = sourceTitle(event).replace(/^20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+/, "").trim();
    const quoted = title.match(/「([^」]+)」/);
    if (quoted) return quoted[1].trim();
    title = title.replace(/^(?:20\d{2}年)?\d{1,2}月\d{1,2}日(?:\([^)]*\)|（[^）]*）)?\s*/, "");
    title = title.split(/\s*@|開催決定|出演決定|アップグレード抽選受付|アップグレード受付|一般(?:発売|販売|先行)|FC\s*(?:会員)?先行|ファンクラブ|OFFICIAL FANCLUB|先行受付|チケット受付|受付のお知らせ/)[0];
    return title.replace(/[!！\s\-–—｜|]+$/g, "").trim() || sourceTitle(event);
  };
  const normalizeTitle = (event) => {
    let title = cleanTitle(event);
    if (event.group) title = title.replace(new RegExp(event.group.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), "");
    title = title
      .replace(/[＜<][^＞>]+[＞>]/g, "")
      .replace(/[「」『』【】\[\]()（）♡♥︎❤︎・･!！?？'"`~〜～\s_\-–—｜|:：,.，。/\\]/g, "")
      .toLowerCase();
    return title;
  };
  const birthdayPerson = (event) => {
    let title = cleanTitle(event);
    if (event.group) title = title.replace(event.group, "").trim();
    const match = title.match(/([一-龠々ぁ-んァ-ヶA-Za-z0-9ー・]{2,30})\s*生誕祭/u);
    return match ? match[1].replace(/[\s・]/g, "") : "";
  };
  const officialScheduleUrl = (event) => {
    if (event.officialScheduleUrl) return String(event.officialScheduleUrl);
    const urls = Array.isArray(event.urls) ? event.urls : [];
    return String(urls.find((url) => String(url).includes("asobisystem.com/live_information/detail/")) || "");
  };
  const occurrences = (event) => {
    const rows = [];
    if (Array.isArray(event.schedule) && event.schedule.length) {
      event.schedule.forEach((x) => rows.push({
        date: String(x.date || "").slice(0, 10),
        venue: x.venue || event.venue || null,
        startTime: x.startTime || event.startTime || null
      }));
    } else if (Array.isArray(event.eventDates) && event.eventDates.length) {
      event.eventDates.forEach((x) => rows.push({
        date: String(x).slice(0, 10),
        venue: event.venue || null,
        startTime: event.startTime || null
      }));
    } else if (event.eventDate) {
      rows.push({
        date: String(event.eventDate).slice(0, 10),
        venue: event.venue || null,
        startTime: event.startTime || null
      });
    }
    const seen = new Set();
    return rows.filter((x) => {
      const key = [x.date, x.startTime || "", String(x.venue || "").replace(/\s+/g, "")].join("\u001f");
      if (!parseDay(x.date) || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  };
  const samePerformance = (left, right) => {
    if (left.event.group !== right.event.group || left.date !== right.date) return false;

    // The physical slot is the strongest identity. Ticket source/title variants
    // must never create two cards for one group at the same date and start time.
    if (left.startTime && right.startTime && left.startTime === right.startTime) return true;

    const leftOfficial = officialScheduleUrl(left.event);
    const rightOfficial = officialScheduleUrl(right.event);
    if (leftOfficial && rightOfficial && leftOfficial === rightOfficial) return true;

    const leftBirthday = birthdayPerson(left.event);
    const rightBirthday = birthdayPerson(right.event);
    if (leftBirthday && rightBirthday && leftBirthday === rightBirthday) return true;

    const leftTitle = normalizeTitle(left.event);
    const rightTitle = normalizeTitle(right.event);
    if (!leftTitle || !rightTitle) return false;
    if (leftTitle === rightTitle) return true;
    const shorter = leftTitle.length <= rightTitle.length ? leftTitle : rightTitle;
    const longer = shorter === leftTitle ? rightTitle : leftTitle;
    return shorter.length >= 10 && longer.includes(shorter);
  };
  const performanceScore = (item) => {
    const title = String(item.event.title || "");
    let score = 0;
    if (officialScheduleUrl(item.event)) score += 12;
    if (item.event.eventTitle) score += 5;
    if (item.startTime) score += 4;
    if (item.venue || item.event.venue) score += 2;
    if (/アップグレード|受付|先行|一般発売/.test(title)) score -= 8;
    return score;
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
  for (const event of events) {
    for (const occurrence of occurrences(event)) {
      const candidate = { event, ...occurrence };
      const duplicateIndex = uniquePerformances.findIndex((existing) => samePerformance(existing, candidate));
      if (duplicateIndex < 0) {
        uniquePerformances.push(candidate);
        continue;
      }
      if (performanceScore(candidate) > performanceScore(uniquePerformances[duplicateIndex])) {
        uniquePerformances[duplicateIndex] = candidate;
      }
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
      calendar.querySelectorAll(milestoneSelector).forEach((node) => {
        const text = node.textContent.trim();
        if (text.startsWith("🎤") || text.startsWith("📱")) node.style.display = "none";
      });

      calendar.querySelectorAll(`${barSelector} span`).forEach((span) => {
        let text = span.textContent;
        for (const group of groupNames) text = text.replace(`${group}｜`, "");
        if (text !== span.textContent) span.textContent = text;
      });

      const visiblePerformances = uniquePerformances.filter((item) => matchesSelectedGroup(item.event));
      const weeks = [...calendar.querySelectorAll(weekSelector)];
      weeks.forEach((week, weekIndex) => {
        const weekStart = addDays(windowInfo.gridStart, weekIndex * 7);
        const weekEnd = addDays(weekStart, 6);
        let baseTop = 31;
        week.querySelectorAll(`${barSelector}, ${milestoneSelector}`).forEach((node) => {
          if (node.classList.contains("performance-date-marker") || node.style.display === "none") return;
          const top = Number.parseFloat(node.style.top || "0") || 0;
          const height = node.offsetHeight || (node.matches(barSelector) ? 52 : 29);
          baseTop = Math.max(baseTop, top + height + 4);
        });

        const rows = Array(7).fill(0);
        visiblePerformances.forEach((item) => {
          const d = parseDay(item.date);
          if (!d || d < windowInfo.visibleStart || d < weekStart || d > weekEnd) return;
          const dayIndex = Math.round((d - weekStart) / 86400000);
          const row = rows[dayIndex]++;
          const button = document.createElement("button");
          const isOnline = item.event.eventCategory === "online-benefit";
          const icon = isOnline ? "📱" : "🎤";
          button.type = "button";
          button.className = `${milestoneClass} performance-date-marker ${groupClass[item.event.group] || ""}`;
          button.textContent = `${icon} ${cleanTitle(item.event)}`;
          button.style.left = `calc(${dayIndex / 7 * 100}% + 4px)`;
          button.style.width = `calc(${100 / 7}% - 8px)`;
          button.style.top = `${baseTop + row * 29}px`;
          button.addEventListener("click", () => {
            if (!detail) return;
            const dText = `${d.getMonth() + 1}/${d.getDate()}`;
            const dateLabel = isOnline ? "配信予定日" : "公演日";
            detail.innerHTML = `<strong>${esc(cleanTitle(item.event))}</strong><span>${dateLabel}: ${esc(dText)}</span><span>会場: ${esc(item.venue || item.event.venue || "未定")}</span><span>グループ: ${esc(item.event.group || "KAWAII LAB.")}</span>`;
          });
          week.appendChild(button);
        });

        const maxRows = Math.max(0, ...rows);
        if (maxRows) {
          const needed = baseTop + maxRows * 29 + 8;
          const current = Number.parseFloat(getComputedStyle(week).minHeight) || 0;
          week.style.minHeight = `${Math.max(current, needed)}px`;
        }
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
