(function(){
  "use strict";

  var cards=document.getElementById("cards");
  if(!cards)return;

  function clean(value){
    return String(value==null?"":value).normalize("NFKC").replace(/[\s　]+/g," ").trim();
  }

  function safeUrl(value){
    var text=clean(value);
    return /^https?:\/\//i.test(text)?text:"";
  }

  function hostOf(value){
    var text=safeUrl(value);
    if(!text)return"";
    try{return new URL(text,location.href).hostname.toLowerCase();}catch(_error){return"";}
  }

  function saleFamily(title,provider,url){
    var text=(clean(title)+" "+clean(provider)).toLowerCase();
    var host=hostOf(url);

    if(/kawaii\s*lab\.?/.test(text)&&/(?:\bfc\b|fanclub|ファンクラブ)/i.test(text))return"kawaii-lab-fc";
    if(/チケットぴあ|\bpia\b/.test(text)||host==="t.pia.jp")return"pia";
    if(/イープラス|eplus/.test(text)||host==="eplus.jp"||host.endsWith(".eplus.jp"))return"eplus";
    if(/ローチケ|lawson/.test(text)||host==="l-tike.com"||host.endsWith(".l-tike.com"))return"lawson";
    if(/年会費|月会費|official fanclub|ファンクラブ|\bfc\b/i.test(text))return"group-fc";
    if(host)return host;
    return text.replace(/[\s　・|｜/]/g,"")||"unknown";
  }

  function periodKey(value){
    var text=clean(value);
    var tokens=[];
    var re=/(?:(20\d{2})[\/-])?(\d{1,2})[\/-](\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?/g;
    var match;
    while((match=re.exec(text))){
      var token=String(Number(match[2])).padStart(2,"0")+"-"+String(Number(match[3])).padStart(2,"0");
      if(match[4])token+="T"+String(Number(match[4])).padStart(2,"0")+":"+match[5];
      tokens.push(token);
    }
    if(tokens.length)return tokens.join("|");
    return text.replace(/[\s　]/g,"").replace(/[〜～]/g,"~");
  }

  function semanticKey(title,provider,period,url){
    return saleFamily(title,provider,url)+"|"+periodKey(period);
  }

  function stepInfo(step){
    var titleNode=step.querySelector(".step-title");
    var periodNode=step.querySelector(".period");
    var source=step.querySelector(".flow-source[href]");
    var title=titleNode?clean(titleNode.textContent):"";
    var period=periodNode?clean(periodNode.textContent):"";
    var url=source?safeUrl(source.href):"";
    return{key:semanticKey(title,"",period,url),title:title,period:period,url:url};
  }

  function currentTitle(option){
    var node=option.querySelector(".ticket-copy b");
    if(!node)return"";
    var clone=node.cloneNode(true);
    Array.prototype.slice.call(clone.querySelectorAll(".sale-state")).forEach(function(item){item.remove();});
    return clean(clone.textContent);
  }

  function currentInfo(option){
    var providerNode=option.querySelector(".provider");
    var periodNode=option.querySelector(".ticket-copy small");
    var link=option.querySelector(".ticket-link[href]");
    var state=option.querySelector(".sale-state");
    var provider=providerNode?clean(providerNode.textContent):"";
    var title=currentTitle(option)||provider||"現在の受付";
    var period=periodNode?clean(periodNode.textContent):"";
    var url=link?safeUrl(link.href):"";
    var stateLabel=state?clean(state.textContent):"受付中";
    return{
      key:semanticKey(title,provider,period,url),
      title:title,
      provider:provider,
      period:period,
      url:url,
      stateLabel:stateLabel
    };
  }

  function makeStep(info){
    var step=document.createElement("div");
    step.className="step"+(\/受付中\/.test(info.stateLabel)?" current":"");

    var dot=document.createElement("span");
    dot.className="dot";
    step.appendChild(dot);

    var head=document.createElement("div");
    head.className="step-head";

    var title=document.createElement("span");
    title.className="step-title";
    title.textContent=info.title;
    head.appendChild(title);

    var state=document.createElement("span");
    state.className="state";
    state.textContent=info.stateLabel||"受付中";
    head.appendChild(state);
    step.appendChild(head);

    var period=document.createElement("div");
    period.className="period";
    period.textContent=info.period||"受付期間は申込ページで確認";
    step.appendChild(period);

    if(info.url){
      var source=document.createElement("a");
      source.className="flow-source";
      source.href=info.url;
      source.target="_blank";
      source.rel="noopener";
      source.textContent="申込ページを確認 ↗";
      step.appendChild(source);
    }

    step.setAttribute("data-ticket-flow-current","1");
    return step;
  }

  function ensureTimeline(flow){
    var timeline=flow.querySelector(".timeline");
    if(timeline)return timeline;
    timeline=document.createElement("div");
    timeline.className="timeline";
    var unknown=flow.querySelector(".unknown");
    if(unknown&&unknown.parentNode)unknown.parentNode.insertBefore(timeline,unknown);
    else{
      var inner=flow.querySelector(".flow-inner")||flow;
      inner.appendChild(timeline);
    }
    return timeline;
  }

  function updateExistingStep(step,info){
    if(\/受付中\/.test(info.stateLabel))step.classList.add("current");
    var state=step.querySelector(".state");
    if(state&&info.stateLabel)state.textContent=info.stateLabel;
    if(info.url){
      var source=step.querySelector(".flow-source");
      if(!source){
        source=document.createElement("a");
        source.className="flow-source";
        step.appendChild(source);
      }
      source.href=info.url;
      source.target="_blank";
      source.rel="noopener";
      source.textContent="申込ページを確認 ↗";
    }
  }

  function dedupeTimeline(timeline){
    var seen={};
    Array.prototype.slice.call(timeline.querySelectorAll(".step")).forEach(function(step){
      var info=stepInfo(step);
      if(!info.key)return;
      if(seen[info.key]){
        var kept=seen[info.key];
        if(step.classList.contains("current"))kept.classList.add("current");
        step.remove();
      }else{
        seen[info.key]=step;
      }
    });
    return seen;
  }

  function sortTimeline(timeline){
    var steps=Array.prototype.slice.call(timeline.querySelectorAll(".step"));
    steps.sort(function(a,b){
      var aa=periodKey((a.querySelector(".period")||{}).textContent||"");
      var bb=periodKey((b.querySelector(".period")||{}).textContent||"");
      return aa.localeCompare(bb);
    });
    steps.forEach(function(step){timeline.appendChild(step);});
  }

  function syncCard(card){
    var flow=card.querySelector(".ticket-flow");
    if(!flow)return;
    var timeline=ensureTimeline(flow);
    var seen=dedupeTimeline(timeline);
    var currentCount=0;

    Array.prototype.slice.call(card.querySelectorAll(".ticket-options .ticket-option")).forEach(function(option){
      var info=currentInfo(option);
      if(!info.url)return;
      currentCount+=1;
      if(seen[info.key]){
        updateExistingStep(seen[info.key],info);
      }else{
        var step=makeStep(info);
        timeline.appendChild(step);
        seen[info.key]=step;
      }
    });

    dedupeTimeline(timeline);
    sortTimeline(timeline);

    if(currentCount){
      var note=flow.querySelector(".flow-note");
      if(note&&/一部の情報源|収集状態/.test(note.textContent||"")){
        note.textContent="過去の履歴には抜けがある可能性があります。現在この公演に表示中の受付は、上の申込情報と同期しています。";
      }
    }
  }

  function run(){
    Array.prototype.slice.call(cards.querySelectorAll(".card")).forEach(syncCard);
  }

  var queued=false;
  new MutationObserver(function(){
    if(queued)return;
    queued=true;
    setTimeout(function(){queued=false;run();},0);
  }).observe(cards,{childList:true,subtree:true});

  run();
})();
