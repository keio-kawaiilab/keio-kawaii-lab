// =========================================
// KAWAII LAB.同好会 公式サイト 共通スクリプト
// =========================================

document.addEventListener("DOMContentLoaded", () => {
  // ---- モバイルナビ開閉 ----
  const toggle = document.querySelector(".nav-toggle");
  const nav = document.querySelector(".global-nav");

  if (toggle && nav) {
    toggle.addEventListener("click", () => {
      const isOpen = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(isOpen));
      toggle.textContent = isOpen ? "✕" : "☰";
    });

    // ナビ内リンクを押したら閉じる
    nav.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        nav.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
        toggle.textContent = "☰";
      });
    });
  }

  // ---- スクロールで要素をふわっと表示 ----
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const targets = document.querySelectorAll(".reveal");

  if (reduceMotion || !("IntersectionObserver" in window)) {
    targets.forEach((el) => el.classList.add("is-visible"));
  } else {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12 }
    );
    targets.forEach((el) => observer.observe(el));
  }

  // ---- ホームのお知らせ：プレスリリースPDFへの導線を明示 ----
  const pressLink = document.querySelector('a[href*="press/20260824-live-ticket-calendar.pdf"]');
  if (pressLink) {
    pressLink.href = "https://keio-kawaiilab.github.io/keio-kawaii-lab/press/20260824-live-ticket-calendar.pdf";
    pressLink.target = "_blank";
    pressLink.rel = "noopener";
    pressLink.textContent = "【プレスリリースPDF】ファン向け情報インフラ第1弾「LIVE & TICKET カレンダー」を公開しました。";
  }

  // ---- フッターの年を自動更新 ----
  const yearEl = document.getElementById("year");
  if (yearEl) yearEl.textContent = new Date().getFullYear();
});
