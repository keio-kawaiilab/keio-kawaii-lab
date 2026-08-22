document.addEventListener("DOMContentLoaded", () => {
  const calendar = document.getElementById("live-calendar");
  if (!calendar) return;

  const groupNames = [
    "FRUITS ZIPPER",
    "CANDY TUNE",
    "SWEET STEADY",
    "CUTIE STREET",
    "MORE STAR",
    "KAWAII LAB.合同"
  ];

  const stripGroups = (value) => {
    let text = String(value || "").trim();
    for (const group of groupNames) {
      text = text.replace(new RegExp(`^${group.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&")}\\s*[｜|:-]?\\s*`, "i"), "");
    }
    return text.trim();
  };

  const shortTitle = (value) => {
    const original = String(value || "ライブ").trim();
    let text = original
      .replace(/^20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+/, "")
      .replace(/^(?:20\d{2}年)?\d{1,2}月\d{1,2}日(?:\([^)]*\)|（[^）]*）)?\s*/, "")
      .trim();

    const quoted = text.match(/「([^」]+)」/);
    if (quoted && quoted[1].length >= 3) text = quoted[1].trim();

    if (/KAWAII LAB\.\s*Christmas SESSION\s*2026/i.test(text)) return "Christmas SESSION";
    if (/JAPAN ARENA TOUR\s*2026\s*-?\s*AUTUMN\s*-/i.test(text)) return "ARENA TOUR";
    if (/JAPAN TOUR\s*2026\s*-?\s*AUTUMN\s*-/i.test(text)) return "JAPAN TOUR";
    if (/2nd ANNIVERSARY LIVE\s*2026/i.test(text)) return "2nd ANNIVERSARY";

    text = stripGroups(text)
      .replace(/\s*@.+$/, "")
      .replace(/(?:開催決定|出演決定).*$/u, "")
      .replace(/(?:アップグレード抽選受付|一般(?:発売|販売|先行)|FC\s*(?:会員)?先行|ファンクラブ|OFFICIAL FANCLUB|先行受付|チケット受付|受付のお知らせ).*$/iu, "")
      .replace(/\s*2026\s*$/i, "")
      .replace(/[!！\s\-–—｜|]+$/g, "")
      .trim();

    text = text
      .replace(/JAPAN ARENA TOUR/i, "ARENA TOUR")
      .replace(/JAPAN TOUR/i, "JAPAN TOUR")
      .replace(/ANNIVERSARY LIVE/i, "ANNIVERSARY")
      .replace(/KAWAII LAB\.\s*/i, "");

    if (!text) text = "ライブ";
    const chars = Array.from(text);
    return chars.length > 18 ? `${chars.slice(0, 18).join("")}…` : text;
  };

  const processBar = (bar) => {
    if (bar.dataset.readableLabel === "1") return;
    const strong = bar.querySelector("strong");
    const span = bar.querySelector("span");
    if (!strong || !span) return;

    const performanceLabel = strong.textContent.trim();
    let line = stripGroups(span.textContent.trim());
    const parts = line.split("｜").map((x) => x.trim()).filter(Boolean);
    const fullTitle = parts[0] || "ライブ";
    const ticketLabel = parts.slice(1).join("｜");

    strong.textContent = shortTitle(fullTitle);
    span.textContent = [ticketLabel, performanceLabel ? `公演 ${performanceLabel}` : ""].filter(Boolean).join("｜");
    bar.title = [fullTitle, ticketLabel, performanceLabel ? `公演 ${performanceLabel}` : ""].filter(Boolean).join("｜");
    bar.dataset.readableLabel = "1";
  };

  const processMilestone = (node) => {
    if (node.dataset.readableLabel === "1") return;
    const original = node.textContent.trim();
    const match = original.match(/^([⏰🎫💳🎤📱])\s*(.+)$/u);
    if (!match) return;

    const icon = match[1];
    let body = stripGroups(match[2]);
    let suffix = "";
    const separator = body.lastIndexOf("｜");
    if (separator >= 0) {
      suffix = body.slice(separator + 1).trim();
      body = body.slice(0, separator).trim();
    }

    const fullTitle = body;
    const compact = shortTitle(body);
    node.textContent = `${icon} ${compact}${suffix ? `｜${suffix}` : ""}`;
    node.title = `${icon} ${fullTitle}${suffix ? `｜${suffix}` : ""}`;
    node.dataset.readableLabel = "1";
  };

  const processAll = () => {
    calendar.querySelectorAll(".event-bar, .calendar-event-bar").forEach(processBar);
    calendar.querySelectorAll(".milestone, .calendar-milestone").forEach(processMilestone);
  };

  const observer = new MutationObserver(() => processAll());
  observer.observe(calendar, { childList: true, subtree: true });
  processAll();
});
