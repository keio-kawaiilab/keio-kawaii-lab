(function(){
  "use strict";
  if(!document.getElementById("calendar"))return;

  var headActions=document.querySelector(".schedule-head-actions");
  if(headActions&&!headActions.querySelector('[data-ticket-guide-link]')){
    var link=document.createElement("a");
    link.className="schedule-home-link";
    link.href="ticket-guide.html";
    link.setAttribute("data-ticket-guide-link","");
    link.textContent="🎫 チケットガイド";
    headActions.insertBefore(link,headActions.firstChild);
  }

  if(!document.querySelector('style[data-ticket-guide-entry-style]')){
    var style=document.createElement("style");
    style.setAttribute("data-ticket-guide-entry-style","");
    style.textContent=
      '.ticket-guide-entry{margin:0 0 14px;padding:14px 15px;border:1px solid #dfe4f1;border-radius:15px;background:linear-gradient(135deg,#fff 0%,#f7f8fc 65%,#fff7fb 100%);box-shadow:0 5px 18px rgba(34,51,95,.05)}'+
      '.ticket-guide-entry-head{display:flex;align-items:center;justify-content:space-between;gap:10px}'+
      '.ticket-guide-entry h2{margin:0;color:var(--navy);font-size:14px}'+
      '.ticket-guide-entry p{margin:5px 0 0;color:var(--muted);font-size:11px;line-height:1.55}'+
      '.ticket-guide-flow{display:flex;align-items:center;gap:5px;overflow:auto;margin-top:10px;padding-bottom:2px}'+
      '.ticket-guide-flow span{flex:0 0 auto;padding:5px 8px;border-radius:999px;background:#fff;border:1px solid var(--line);color:var(--navy);font-size:10px;font-weight:900}'+
      '.ticket-guide-flow i{flex:0 0 auto;color:#9ca4b7;font-style:normal;font-size:10px}'+
      '.ticket-guide-entry a{flex:0 0 auto;display:inline-flex;align-items:center;min-height:34px;padding:7px 10px;border-radius:999px;background:#a93b4f;color:#fff;text-decoration:none;font-size:11px;font-weight:900}'+
      '@media(max-width:620px){.ticket-guide-entry-head{align-items:flex-start}.ticket-guide-entry a{font-size:10px;padding:6px 9px}.ticket-guide-entry h2{font-size:13px}}';
    document.head.appendChild(style);
  }

  if(document.querySelector(".ticket-guide-entry"))return;
  var target=document.querySelector(".schedule-disclaimer")||document.querySelector(".lead")||document.querySelector(".scope-picker");
  if(!target)return;
  var box=document.createElement("section");
  box.className="ticket-guide-entry";
  box.innerHTML=
    '<div class="ticket-guide-entry-head"><div><h2>🎫 チケット販売って、どんな順番？</h2><p>公演発表から先行・当落・一般発売・電子チケット・入場まで、はじめてでも分かる基本の流れ。</p></div><a href="ticket-guide.html">詳しく見る →</a></div>'+
    '<div class="ticket-guide-flow" aria-label="チケット販売の基本的な流れ"><span>公演発表</span><i>→</i><span>FC先行など</span><i>→</i><span>プレイガイド先行</span><i>→</i><span>一般発売</span><i>→</i><span>発券・入場</span></div>';
  target.insertAdjacentElement("afterend",box);
})();
