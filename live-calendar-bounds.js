document.addEventListener("DOMContentLoaded", async () => {
  const monthLabel = document.getElementById("calendar-month");
  const prev = document.getElementById("calendar-prev");
  const next = document.getElementById("calendar-next");
  if (!monthLabel || !prev || !next) return;

  const parseDate = (value) => {
    const m = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null;
  };
  const ym = (date) => date.getFullYear() * 12 + date.getMonth();

  let events = [];
  try {
    const response = await fetch("./data/live-events.json", { cache: "no-store" });
    if (!response.ok) return;
    const data = await response.json();
    events = Array.isArray(data.events) ? data.events : [];
  } catch (_) {
    return;
  }

  const allRelevantDates = [];
  const showEndDates = [];
  events.forEach((event) => {
    [event.applyStart, event.applyEnd, event.resultDate, event.paymentEnd, event.eventDate, event.eventEndDate]
      .map(parseDate)
      .filter(Boolean)
      .forEach((date) => allRelevantDates.push(date));
    const showEnd = parseDate(event.eventEndDate) || parseDate(event.eventDate);
    if (showEnd) showEndDates.push(showEnd);
  });
  if (!allRelevantDates.length || !showEndDates.length) return;

  const minMonth = Math.min(...allRelevantDates.map(ym));
  const maxMonth = Math.max(...showEndDates.map(ym));

  const refresh = () => {
    const m = monthLabel.textContent.match(/(\d{4})年(\d{1,2})月/);
    if (!m) return;
    const current = Number(m[1]) * 12 + Number(m[2]) - 1;
    prev.disabled = current <= minMonth;
    next.disabled = current >= maxMonth;
    prev.title = prev.disabled ? "これより前に表示する情報はありません" : "前の月を表示";
    next.title = next.disabled ? "現在発表済みの最も先の公演月です" : "次の月を表示";
  };

  new MutationObserver(refresh).observe(monthLabel, { childList: true, characterData: true, subtree: true });
  refresh();
});
