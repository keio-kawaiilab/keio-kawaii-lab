(function(){
  "use strict";

  var root=document.getElementById("venue-detail");
  if(!root)return;

  function norm(value){
    return String(value||"")
      .replace(/[\s　・･「」『』【】()（）\-–—_]/g,"")
      .toLowerCase();
  }

  function sourceRank(item){
    var link=item.querySelector(".venue-upcoming-source");
    if(!link)return 0;
    var label=String(link.textContent||"");
    var href=String(link.getAttribute("href")||"");
    if(label.indexOf("ツアー公式")>=0)return 4;
    if(label.indexOf("公演公式")>=0)return 3;
    if(/\.asobisystem\.com\//.test(href))return 2;
    return 1;
  }

  function cleanDuplicates(){
    var rows=Array.prototype.slice.call(root.querySelectorAll(".venue-upcoming-item"));
    if(rows.length<2)return;

    var buckets={};
    rows.forEach(function(item){
      var time=item.querySelector("time");
      var badge=item.querySelector(".venue-badge");
      var key=[
        time?time.getAttribute("datetime")||time.textContent:"",
        badge?badge.textContent:""
      ].join("|");
      (buckets[key]||(buckets[key]=[])).push(item);
    });

    Object.keys(buckets).forEach(function(key){
      var items=buckets[key];
      if(items.length<2)return;

      var official=items.filter(function(item){return sourceRank(item)>=2;});
      if(!official.length)return;

      var officialTitles={};
      official.forEach(function(item){
        var title=item.querySelector("strong");
        var value=norm(title?title.textContent:"");
        if(value)officialTitles[value]=true;
      });

      items.forEach(function(item){
        if(sourceRank(item)>=2)return;
        var badge=item.querySelector(".venue-badge");
        var title=item.querySelector("strong");
        var group=norm(badge?badge.textContent:"");
        var value=norm(title?title.textContent:"");
        var generic=!value||value===group||value==="公演"||value===group+"公演";
        if(generic||officialTitles[value])item.remove();
      });
    });

    var count=root.querySelectorAll(".venue-upcoming-item").length;
    var countEl=root.querySelector(".venue-info-count");
    if(countEl)countEl.textContent=count+"件";
  }

  var observer=new MutationObserver(function(){cleanDuplicates();});
  observer.observe(root,{childList:true,subtree:true});
  cleanDuplicates();
})();
