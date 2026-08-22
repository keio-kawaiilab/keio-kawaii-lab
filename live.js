document.addEventListener("DOMContentLoaded", async () => {
  const list = document.getElementById("live-list");
  const summary = document.getElementById("live-summary");
  const filters = [...document.querySelectorAll(".live-filter")];
  const calendar = document.getElementById("live-calendar");
  const periodLabel = document.getElementById("calendar-month");
  const calendarDetail = document.getElementById("calendar-detail");
  const prevButton = document.getElementById("calendar-prev");
  const nextButton = document.getElementById("calendar-next");
  const demoBanner = document.getElementById("live-demo-banner");
  if (!list || !summary || !calendar || !periodLabel) return;

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
  const shortDay = (d) => `${d.getMonth() + 1}/${d.getDate()}`;

  const displayTitle = (event) => {
    let title = String(event.title || "ライブ情報").replace(/^20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+/, "").trim();
    const quoted = title.match(/「([^」]+)」/);
    if (quoted) return quoted[1].trim();
    title = title.replace(/^(?:20\d{2}年)?\d{1,2}月\d{1,2}日(?:\([^)]*\)|（[^）]*）)?\s*/, "");
    title = title.split(/\s*@|開催決定|出演決定|アップグレード抽選受付|一般(?:発売|販売|先行)|FC\s*(?:会員)?先行|ファンクラブ|OFFICIAL FANCLUB|先行受付|チケット受付|受付のお知らせ/)[0];
    return title.replace(/[!！\s\-–—｜|]+$/g, "").trim() || String(event.title || "ライブ情報");
  };

  const shortRange = (event) => {
    const a = parseDate(event.eventDate);
    const b = parseDate(event.eventEndDate);
    if (!a) return "日程未定";
    if (!b || sameDay(a, b)) return shortDay(a);
    if (a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth()) return `${shortDay(a)}–${b.getDate()}`;
    return `${shortDay(a)}–${shortDay(b)}`;
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
  const noCurrentSale = (event) => event.applicationStatus === "none" || event.ticketType === "現在受付なし";

  const saleCategory = (event) => {
    if (noCurrentSale(event)) return "現在受付なし";
    const text = `${event.ticketType || ""} ${event.title || ""}`;
    if (/アップグレード/.test(text)) return "アップグレード抽選";
    if (/一般(?:発売|販売|先着)/.test(text)) return "一般販売";
    if (/年会費コース/.test(text)) return "FC年会費コース会員先行";
    if (/(?:KAWAII LAB\.\s*FC|OFFICIAL FANCLUB|ファンクラブ|\bFC\b|FC会員)/i.test(text)) return "ファンクラブ先行";
    if (/プレリク|プレイガイド/.test(text)) return "プレイガイド先行";
    if (/先行/.test(text)) return "先行受付";
    return "チケット受付";
  };
  const audienceLabel = (event) => {
    if (noCurrentSale(event)) return "—";
    const text = `${event.ticketType || ""} ${event.title || ""}`;
    if (/年会費コース/.test(text)) return "FC年会費コース会員";
    if (/(?:KAWAII LAB\.\s*FC|OFFICIAL FANCLUB|ファンクラブ|\bFC\b|FC会員)/i.test(text)) return "FC会員";
    if (/一般(?:発売|販売|先着)/.test(text)) return "一般";
    if (/アップグレード/.test(text)) return "対象チケット保有者向け（公式条件を確認）";
    return "公式条件を確認";
  };

  const status = (event) => {
    if (noCurrentSale(event)) return { label: "現在受付なし", cls: "" };
    const now = new Date();
    const start = parseDate(event.applyStart);
    const end = parseDate(event.applyEnd);
    if (start && now < start) return { label: "受付前", cls: "" };
    if (start && end && now >= start && now <= end) {
      return (end - now) / 36e5 <= 24 ? { label: "24時間以内に締切", cls: "soon" } : { label: "受付中", cls: "open" };
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
    return `<strong>${esc(eventLabel(event))}｜${esc(displayTitle(event))}</strong>
      <span>販売区分: ${esc(saleCategory(event))}</span>
      <span>受付名: ${esc(event.ticketType || "未定")}</span>
      <span>対象: ${esc(audienceLabel(event))}</span>
      <span>会場: ${esc(event.venue || "未定")}</span>
      ${p.length ? `<span>参加: ${esc(p.join(" / "))}</span>` : ""}
      ${schedule ? `<span>全日程: ${esc(schedule)}</span>` : ""}
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
  const initialGridStart = addDays(today, -today.getDay());
  let windowStart = today;
  let selected = "all";
  const filteredEvents = () => events.filter((event) => matchesGroup(event, selected));

  const renderList = () => {
    const filtered = filteredEvents();
    const openCount = filtered.filter((event) => ["open", "soon"].includes(status(event).cls)).length;
    summary.textContent = filtered.length ? `${filtered.length}件掲載中・うち受付中 ${openCount}件` : "現在、掲載中のライブ・チケット情報はありません。";
    if (!filtered.length) {
      list.innerHTML = '<div class="live-empty">現在、掲載中の未来公演はありません。</div>';
      return;
    }
    const sorted = [...filtered].sort((a, b) => (parseDate(a.applyEnd) || parseDate(a.eventDate)) - (parseDate(b.applyEnd) || parseDate(b.eventDate)));
    list.innerHTML = sorted.map((event) => {
      const st = status(event);
      const urls = sourceUrls(event);
      const p = participants(event);
      const noSale = noCurrentSale(event);
      return `<article class="live-card ${groupClass[event.group] || ""}">
        <div class="live-card-top"><div>
          <div class="live-event-date">🎤 ${esc(eventLabel(event))}</div>
          <div class="live-group">${esc(event.group || "KAWAII LAB.")}</div>
          <h3>${esc(displayTitle(event))}</h3>
        </div><span class="live-status ${st.cls}">${esc(st.label)}</span></div>
        <dl class="live-meta">
          <div><dt>販売区分</dt><dd>${esc(saleCategory(event))}</dd></div>
          <div><dt>受付名</dt><dd>${esc(event.ticketType || "未定")}</dd></div>
          <div><dt>対象</dt><dd>${esc(audienceLabel(event))}</dd></div>
          <div><dt>公演日</dt><dd>${esc(longRange(event))}</dd></div>
          ${p.length ? `<div><dt>参加グループ</dt><dd>${esc(p.join(" / "))}</dd></div>` : ""}
          <div><dt>申込開始</dt><dd>${esc(noSale ? "現在受付なし" : fmt(event.applyStart))}</dd></div>
          <div><dt>申込締切</dt><dd>${esc(noSale ? "現在受付なし" : fmt(event.applyEnd))}</dd></div>
          <div><dt>当落発表</dt><dd>${esc(noSale ? "—" : fmt(event.resultDate))}</dd></div>
          <div><dt>入金期限</dt><dd>${esc(noSale ? "—" : fmt(event.paymentEnd))}</dd></div>
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
    calendar.innerHTML = "";
    const gridStart = addDays(windowStart, -windowStart.getDay());
    const gridEnd = addDays(gridStart, 34);
    const visibleStart = windowStart;
    periodLabel.textContent = `${shortDay(visibleStart)} 〜 ${shortDay(gridEnd)}（5週間）`;
    const filtered = filteredEvents();

    for (let w = 0; w < 5; w += 1) {
      const weekStart = addDays(gridStart, w * 7);
      const weekEnd = addDays(weekStart, 6);
      const week = document.createElement("div");
      week.className = "calendar-week";

      for (let d = 0; d < 7; d += 1) {
        const date = addDays(weekStart, d);
        const cell = document.createElement("div");
        cell.className = "calendar-day";
        if (d === 0) cell.classList.add("is-sun");
        if (d === 6) cell.classList.add("is-sat");
        if (date < visibleStart) {
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
        .filter((x) => x.start && x.end && x.end >= maxDate(weekStart, visibleStart) && x.start <= weekEnd && x.start <= gridEnd)
        .sort((a, b) => a.start - b.start || a.end - b.end);
      const laneEnds = [];
      ranges.forEach((item) => {
        const start = maxDate(item.start, maxDate(weekStart, visibleStart));
        const end = minDate(item.end, minDate(weekEnd, gridEnd));
        if (start > end) return;
        const startIndex = Math.round((start - weekStart) / 86400000);
        const endIndex = Math.round((end - weekStart) / 86400000);
        let lane = laneEnds.findIndex((x) => x < startIndex);
        if (lane < 0) lane = laneEnds.length;
        laneEnds[lane] = endIndex;
        const label = eventLabel(item.event);
        const bar = makeButton(
          "calendar-event-bar",
          `<strong>${esc(label)}</strong><span>${esc(displayTitle(item.event))}｜${esc(saleCategory(item.event))}</span>`,
          item.event,
          `申込期間: ${fmt(item.event.applyStart)} 〜 ${fmt(item.event.applyEnd)}`
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
          if (date && date >= visibleStart && date >= weekStart && date <= weekEnd && date <= gridEnd) milestones.push({ event, date, icon, label, value });
        });
      });
      const perDay = Array(7).fill(0);
      const baseTop = 31 + laneEnds.length * 55;
      milestones.sort((a, b) => a.date - b.date).forEach((item) => {
        const index = Math.round((item.date - weekStart) / 86400000);
        const row = perDay[index]++;
        const button = makeButton(
          "calendar-milestone",
          esc(`${item.icon} ${displayTitle(item.event)}｜${item.label}`),
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
    if (prevButton) prevButton.disabled = gridStart.getTime() === initialGridStart.getTime();
  };

  const renderAll = () => { renderCalendar(); renderList(); };
  filters.forEach((button) => button.addEventListener("click", () => {
    selected = button.dataset.group || "all";
    filters.forEach((b) => b.classList.toggle("is-active", b === button));
    renderAll();
  }));
  prevButton?.addEventListener("click", () => {
    const currentGridStart = addDays(windowStart, -windowStart.getDay());
    const previousGridStart = addDays(currentGridStart, -35);
    if (previousGridStart < initialGridStart) {
      windowStart = today;
    } else {
      windowStart = previousGridStart;
    }
    renderCalendar();
  });
  nextButton?.addEventListener("click", () => {
    const currentGridStart = addDays(windowStart, -windowStart.getDay());
    windowStart = addDays(currentGridStart, 35);
    renderCalendar();
  });
  renderAll();
});