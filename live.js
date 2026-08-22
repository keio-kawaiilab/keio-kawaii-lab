document.addEventListener("DOMContentLoaded", async () => {
  const list = document.getElementById("live-list");
  const summary = document.getElementById("live-summary");
  const filters = [...document.querySelectorAll(".live-filter")];
  if (!list || !summary) return;

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

  const parseDate = (value) => value ? new Date(value) : null;
  const fmt = (value) => {
    const d = parseDate(value);
    if (!d || Number.isNaN(d.getTime())) return "未定";
    return new Intl.DateTimeFormat("ja-JP", {
      year: "numeric", month: "numeric", day: "numeric",
      hour: value.includes("T") ? "2-digit" : undefined,
      minute: value.includes("T") ? "2-digit" : undefined
    }).format(d);
  };

  const getStatus = (event) => {
    const now = new Date();
    const start = parseDate(event.applyStart);
    const end = parseDate(event.applyEnd);
    if (start && now < start) return { label: "受付前", cls: "" };
    if (start && end && now >= start && now <= end) {
      const hours = (end - now) / 36e5;
      return hours <= 24 ? { label: "本日〜24時間以内に締切", cls: "soon" } : { label: "受付中", cls: "open" };
    }
    if (end && now > end) return { label: "受付終了", cls: "" };
    return { label: "日程確認中", cls: "" };
  };

  let events = [];
  try {
    const response = await fetch("./data/live-events.json", { cache: "no-store" });
    if (!response.ok) throw new Error("failed");
    const data = await response.json();
    events = Array.isArray(data.events) ? data.events : [];
  } catch (_) {
    summary.textContent = "ライブ情報を読み込めませんでした。時間をおいて再度お試しください。";
  }

  let selected = "all";

  const render = () => {
    const filtered = selected === "all" ? events : events.filter((e) => e.group === selected);
    const openCount = filtered.filter((e) => getStatus(e).cls === "open" || getStatus(e).cls === "soon").length;
    summary.textContent = filtered.length
      ? `${filtered.length}件掲載中・うち受付中 ${openCount}件`
      : "現在、掲載中のライブ・チケット受付情報はありません。";

    if (!filtered.length) {
      list.innerHTML = '<div class="live-empty">新しい公式情報を取得すると、ここに自動で追加される予定です。</div>';
      return;
    }

    const sorted = [...filtered].sort((a, b) => {
      const ad = parseDate(a.applyEnd) || parseDate(a.eventDate) || new Date("2999-12-31");
      const bd = parseDate(b.applyEnd) || parseDate(b.eventDate) || new Date("2999-12-31");
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
              <div class="live-group">${esc(event.group || "KAWAII LAB.")}</div>
              <h3>${esc(event.title || "ライブ情報")}</h3>
            </div>
            <span class="live-status ${status.cls}">${esc(status.label)}</span>
          </div>
          <dl class="live-meta">
            <div><dt>申込開始</dt><dd>${fmt(event.applyStart)}</dd></div>
            <div><dt>申込締切</dt><dd>${fmt(event.applyEnd)}</dd></div>
            <div><dt>当落発表</dt><dd>${fmt(event.resultDate)}</dd></div>
            <div><dt>入金期限</dt><dd>${fmt(event.paymentEnd)}</dd></div>
            <div><dt>公演日</dt><dd>${fmt(event.eventDate)}</dd></div>
            <div><dt>会場</dt><dd>${esc(event.venue || "未定")}</dd></div>
          </dl>
          ${source}
        </article>`;
    }).join("");
  };

  filters.forEach((button) => {
    button.addEventListener("click", () => {
      selected = button.dataset.group || "all";
      filters.forEach((b) => b.classList.toggle("is-active", b === button));
      render();
    });
  });

  render();
});
