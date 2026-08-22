document.addEventListener("DOMContentLoaded", () => {
  const list = document.getElementById("live-list");
  if (!list) return;

  const processCard = (card) => {
    const title = card.querySelector("h3")?.textContent || "";
    if (!/オンライン(?:特典会|サイン会)/.test(title)) return;

    const dateBadge = card.querySelector(".event-date, .live-event-date");
    if (dateBadge) dateBadge.textContent = dateBadge.textContent.replace(/^🎤\s*/, "📱 ");

    let reception = "";
    card.querySelectorAll("dl > div").forEach((row) => {
      const dt = row.querySelector("dt");
      const dd = row.querySelector("dd");
      if (!dt || !dd) return;
      if (dt.textContent.trim() === "受付名") reception = dd.textContent.trim();
    });

    card.querySelectorAll("dl > div").forEach((row) => {
      const dt = row.querySelector("dt");
      const dd = row.querySelector("dd");
      if (!dt || !dd) return;
      const label = dt.textContent.trim();
      if (label === "販売区分") {
        if (/抽選/.test(reception)) dd.textContent = "オンライン特典会（抽選販売）";
        else if (/先着/.test(reception)) dd.textContent = "オンライン特典会（先着販売）";
        else dd.textContent = "オンライン特典会";
      }
      if (label === "対象") dd.textContent = "商品により一般 / FC会員限定";
      if (label === "公演" || label === "公演日") dt.textContent = "配信予定日";
    });
  };

  const processAll = () => list.querySelectorAll("article").forEach(processCard);
  new MutationObserver(processAll).observe(list, { childList: true, subtree: true });
  processAll();
});
