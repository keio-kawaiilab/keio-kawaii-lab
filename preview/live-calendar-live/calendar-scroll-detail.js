document.addEventListener("DOMContentLoaded", () => {
  const calendar = document.getElementById("live-calendar");
  const list = document.getElementById("live-list");
  if (!calendar || !list) return;

  const normalize = (value) => String(value || "")
    .replace(/^[⏰🎫💳🎤📱]\s*/u, "")
    .replace(/^(FRUITS ZIPPER|CANDY TUNE|SWEET STEADY|CUTIE STREET|MORE STAR|KAWAII LAB\.合同|KAWAII LAB\.)\s*[｜|:\-]?\s*/i, "")
    .replace(/\s*@.+$/u, "")
    .replace(/(?:アップグレード抽選受付|一般(?:発売|販売|先行)|FC\s*(?:会員)?先行|ファンクラブ|OFFICIAL FANCLUB|先行受付|チケット受付|受付のお知らせ).*$/iu, "")
    .replace(/20\d{2}/g, "")
    .replace(/[\s　\-–—｜|「」『』()（）・_.]/g, "")
    .toLowerCase();

  const targetTitle = (button) => {
    const titled = String(button.title || "").replace(/^[⏰🎫💳🎤📱]\s*/u, "").split("｜")[0].trim();
    if (titled) return titled;
    const strong = button.querySelector("strong");
    if (strong?.textContent) return strong.textContent.trim();
    return button.textContent.replace(/^[⏰🎫💳🎤📱]\s*/u, "").split("｜")[0].trim();
  };

  const findCard = (title) => {
    const wanted = normalize(title);
    if (!wanted) return null;
    const cards = [...list.querySelectorAll("article")];
    let best = null;
    let bestScore = 0;
    for (const card of cards) {
      const heading = card.querySelector("h3")?.textContent || "";
      const candidate = normalize(heading);
      if (!candidate) continue;
      let score = 0;
      if (candidate === wanted) score = 100;
      else if (candidate.includes(wanted) || wanted.includes(candidate)) score = 80;
      else {
        const common = [...new Set(wanted)].filter((ch) => candidate.includes(ch)).length;
        score = common / Math.max(1, new Set(wanted).size) * 50;
      }
      if (score > bestScore) {
        best = card;
        bestScore = score;
      }
    }
    return bestScore >= 35 ? best : null;
  };

  calendar.addEventListener("click", (event) => {
    const button = event.target.closest(".event-bar, .milestone, .calendar-event-bar, .calendar-milestone");
    if (!button) return;
    const title = targetTitle(button);
    setTimeout(() => {
      const card = findCard(title);
      if (!card) return;
      card.scrollIntoView({ behavior: "smooth", block: "start" });
      setTimeout(() => window.scrollBy({ top: -84, behavior: "smooth" }), 260);
      card.style.transition = "box-shadow .25s ease, transform .25s ease";
      const oldShadow = card.style.boxShadow;
      card.style.boxShadow = "0 0 0 4px rgba(29, 62, 120, .18), 0 10px 28px rgba(29, 37, 71, .16)";
      card.style.transform = "translateY(-2px)";
      setTimeout(() => {
        card.style.boxShadow = oldShadow;
        card.style.transform = "";
      }, 1600);
    }, 80);
  });
});
