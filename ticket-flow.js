(function(){
  "use strict";

  var cards=document.getElementById("cards");
  if(!cards)return;

  if(!document.querySelector("style[data-ticket-flow-style]")){
    var style=document.createElement("style");
    style.setAttribute("data-ticket-flow-style","");
    style.textContent='\
.ticket-flow{margin-top:10px;border:1px solid #dfe4f1;border-radius:13px;background:#f7f8fc;overflow:hidden}\
.ticket-flow summary{list-style:none;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 13px;cursor:pointer;color:var(--navy);font-size:12px;font-weight:900;-webkit-tap-highlight-color:transparent}\
.ticket-flow summary::-webkit-details-marker{display:none}\
.ticket-flow summary::after{content:"⌄";font-size:18px;transition:transform .18s ease}\
.ticket-flow[open] summary::after{transform:rotate(180deg)}\
.ticket-flow-inner{padding:0 13px 13px;background:#fff}\
.ticket-flow-note{padding:10px 0 4px;color:var(--muted);font-size:10px;line-height:1.6}\
.ticket-flow-timeline{position:relative;margin:8px 2px 2px 7px;padding-left:24px}\
.ticket-flow-timeline::before{content:"";position:absolute;left:6px;top:9px;bottom:13px;width:2px;background:#dfe3ec}\
.ticket-flow-step{position:relative;margin:0 0 15px;padding-left:7px}\
.ticket-flow-step:last-child{margin-bottom:3px}\
.ticket-flow-dot{position:absolute;left:-24px;top:3px;width:15px;height:15px;border-radius:50%;border:3px solid #9ca4b3;background:#9ca4b3;box-shadow:inset 0 0 0 3px #fff}\
.ticket-flow-step.is-current .ticket-flow-dot{border-color:#2d9950;background:#2d9950;box-shadow:0 0 0 4px rgba(45,153,80,.12),inset 0 0 0 3px #fff}\
.ticket-flow-head{display:flex;align-items:center;justify-content:space-between;gap:8px}\
.ticket-flow-title{color:var(--navy);font-size:12px;font-weight:900}\
.ticket-flow-state{display:inline-flex;padding:3px 7px;border-radius:999px;background:#eef0f3;color:#656b79;font-size:9px;font-weight:900;white-space:nowrap}\
.ticket-flow-step.is-current .ticket-flow-state{background:#e8f6ec;color:#23713a}\
.ticket-flow-period{margin-top:3px;color:var(--muted);font-size:10px}\
.ticket-flow-providers{display:flex;flex-wrap:wrap;gap:5px;margin-top:6px}\
.ticket-flow-provider{display:inline-flex;padding:3px 7px;border-radius:999px;background:#eef0f5;color:#50586f;font-size:9px;font-weight:900}\
.ticket-flow-unknown{margin-top:10px;padding:10px 11px;border:1px dashed #c9ceda;border-radius:10px;background:#faf9f6;color:#666d7c;font-size:10px;line-height:1.55}\
';
    document.head.appendChild(style);
  }

  function clean(value){return String(value||"").replace(/\s+/g," ").trim();}

  function offerInfo(node){
    var provider=clean(node.querySelector(".provider")&&node.querySelector(".provider").textContent);
    var copy=node.querySelector(".ticket-copy");
    var title="";
    var state="";
    var period="";
    if(copy){
      var b=copy.querySelector("b");
      if(b){
        var clone=b.cloneNode(true);
        var stateNode=clone.querySelector(".sale-state");
        if(stateNode){state=clean(stateNode.textContent);stateNode.remove();}
        title=clean(clone.textContent);
      }
      var small=copy.querySelector("small");
      if(small)period=clean(small.textContent);
    }
    var open=!!node.querySelector(".sale-state.open")||/受付中|予定/.test(state);
    return{provider:provider,title:title||"チケット受付",state:state|| (open?"受付中":"受付終了"),period:period,open:open};
  }

  function category(info){
    var text=(info.provider+" "+info.title).normalize("NFKC");
    if(/一般(?:販売|発売)|一般チケット/.test(text))return"一般販売";
    if(/FC|ファンクラブ|すきすき|会員先行/i.test(text))return"FC先行";
    if(/オフィシャル|公式先行/.test(text))return"オフィシャル先行";
    if(/ぴあ|イープラス|e\+|ローチケ|ローソン|プレリザーブ|プレオーダー|プレリク|先行/.test(text))return"プレイガイド先行";
    return info.title||"チケット受付";
  }

  function dateScore(period,index){
    var matches=String(period||"").match(/20\d{2}\/\d{1,2}\/\d{1,2}(?:\s+\d{1,2}:\d{2})?/g);
    if(matches&&matches.length){
      var value=matches[0].replace(/\//g,"-").replace(" ","T");
      var parsed=Date.parse(value);
      if(!Number.isNaN(parsed))return parsed;
    }
    return Number.MAX_SAFE_INTEGER-1000+index;
  }

  function groupOffers(items){
    var groups=[];
    items.forEach(function(item,index){
      item.order=dateScore(item.period,index);
      var key=category(item)+"|"+item.period+"|"+(item.open?"open":"closed");
      var group=groups.find(function(x){return x.key===key;});
      if(!group){
        group={key:key,title:category(item),period:item.period,open:item.open,state:item.open?"受付中":"受付終了",providers:[],details:[],order:item.order};
        groups.push(group);
      }
      if(item.provider&&group.providers.indexOf(item.provider)<0)group.providers.push(item.provider);
      if(item.title&&group.details.indexOf(item.title)<0)group.details.push(item.title);
    });
    groups.sort(function(a,b){return a.order-b.order;});
    return groups;
  }

  function flowHtml(groups){
    return '<details class="ticket-flow">'+
      '<summary>🎫 チケット販売の流れを見る</summary>'+
      '<div class="ticket-flow-inner">'+
      '<div class="ticket-flow-note">発表済みの受付だけを時系列で表示します。今後の販売方法は予測しません。</div>'+
      '<div class="ticket-flow-timeline">'+
      groups.map(function(group){
        var detail=group.details.length===1&&group.details[0]!==group.title?'<div class="ticket-flow-period">'+group.details[0]+'</div>':'';
        var providers=group.providers.length?'<div class="ticket-flow-providers">'+group.providers.map(function(name){return '<span class="ticket-flow-provider">'+name.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")+'</span>';}).join("")+'</div>':'';
        return '<div class="ticket-flow-step'+(group.open?' is-current':'')+'">'+
          '<span class="ticket-flow-dot"></span>'+
          '<div class="ticket-flow-head"><span class="ticket-flow-title">'+group.title.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")+'</span><span class="ticket-flow-state">'+group.state+'</span></div>'+
          detail+
          (group.period?'<div class="ticket-flow-period">'+group.period.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")+'</div>':'')+
          providers+
          '</div>';
      }).join("")+
      '</div>'+
      '<div class="ticket-flow-unknown">この先のチケット販売情報は未発表です。新しい受付が公式発表された場合のみ追加します。</div>'+
      '</div></details>';
  }

  function mountCard(card){
    var tickets=card.querySelector(".ticket-options");
    if(!tickets)return;
    var existing=card.querySelector(".ticket-flow");
    if(existing)existing.remove();
    var items=[].slice.call(tickets.querySelectorAll(".ticket-option")).map(offerInfo);
    if(!items.length)return;
    var groups=groupOffers(items);
    if(!groups.length)return;
    tickets.insertAdjacentHTML("afterend",flowHtml(groups));
  }

  var queued=false;
  function mountAll(){
    queued=false;
    [].slice.call(cards.querySelectorAll(".card")).forEach(mountCard);
  }
  function queue(){
    if(queued)return;
    queued=true;
    window.setTimeout(mountAll,25);
  }

  mountAll();
  new MutationObserver(function(mutations){
    var relevant=mutations.some(function(m){
      return [].slice.call(m.addedNodes||[]).some(function(node){
        return node.nodeType===1&&!node.classList.contains("ticket-flow")&&!node.closest(".ticket-flow");
      });
    });
    if(relevant)queue();
  }).observe(cards,{childList:true,subtree:true});
})();
