(function(root){
  "use strict";
  var core=root&&root.RoutePlannerCore;
  if(!core||core.__diversityEnhanced)return;
  var originalCreateModel=core.createModel;

  function collapse(values){
    var result=[];
    (values||[]).forEach(function(value){if(value&&result[result.length-1]!==value)result.push(value);});
    return result;
  }
  function edgeKey(from,edge){return[from,edge.to,edge.type,edge.railway||""].join("\u0001");}

  core.createModel=function(){
    var model=originalCreateModel.apply(core,arguments);
    var originalCandidatePaths=model.candidatePaths;

    function segments(path){return model.segmentsFrom(path)||[];}
    function pathSignature(path){return segments(path).map(function(s){return[s.railway,s.from,s.to].join("\u0002");}).join("\u0003");}
    function familySignature(path){return collapse(segments(path).map(function(s){return s.railway;})).join("\u0003");}

    function diverseCandidatePaths(originGroup,destinationGroup,options){
      options=options||{};
      var requested=Math.max(1,Math.min(18,Number(options.limit)||8));
      if(requested<=8)return originalCandidatePaths(originGroup,destinationGroup,options);
      var allowed=options.allowedRailways?Array.from(options.allowedRailways):null;
      var base=model.shortestPath(originGroup,destinationGroup,{allowedRailways:allowed});
      if(!base)return[];
      var maxCost=base.cost+Math.max(20,Math.ceil(base.cost*0.95));
      var results=[],seen=new Set(),pool=new Map(),expanded=new Set(),familyCounts=new Map(),expansionCount=0;

      function accept(path){
        var sig=pathSignature(path);if(!sig||seen.has(sig))return false;
        seen.add(sig);results.push(path);
        var family=familySignature(path);familyCounts.set(family,(familyCounts.get(family)||0)+1);
        return true;
      }
      function add(path){
        if(!path||path.cost>maxCost)return;
        var sig=pathSignature(path);if(!sig||seen.has(sig))return;
        var old=pool.get(sig);if(!old||path.cost<old.cost)pool.set(sig,path);
      }
      function alternate(params){
        add(model.shortestPath(originGroup,destinationGroup,Object.assign({allowedRailways:allowed},params||{})));
      }
      function expand(path){
        var sig=pathSignature(path);if(expanded.has(sig)||expansionCount>=10)return;
        expanded.add(sig);expansionCount++;
        var segs=segments(path),railways=Array.from(new Set(segs.map(function(s){return s.railway;}).filter(Boolean)));
        railways.forEach(function(railway){alternate({blockedRailways:[railway]});});

        var edges=path.edges||[],indexes=[],edgeCount=edges.length,stride=Math.max(1,Math.ceil(edgeCount/10));
        edges.forEach(function(step,index){
          var prev=edges[index-1],next=edges[index+1];
          if(index===0||index===edgeCount-1||step.edge.type==="transfer"||index%stride===0||
             (prev&&prev.edge.railway!==step.edge.railway)||(next&&next.edge.railway!==step.edge.railway))indexes.push(index);
        });
        Array.from(new Set(indexes)).slice(0,14).forEach(function(index){
          var step=edges[index];if(step)alternate({blockedEdges:[edgeKey(step.from,step.edge)]});
        });
      }
      function selectNext(){
        var candidates=Array.from(pool.values());if(!candidates.length)return null;
        candidates.sort(function(a,b){
          var fa=familySignature(a),fb=familySignature(b),ca=familyCounts.get(fa)||0,cb=familyCounts.get(fb)||0;
          var ua=ca===0?0:1,ub=cb===0?0:1;
          return ua-ub||ca-cb||a.cost-b.cost||pathSignature(a).localeCompare(pathSignature(b));
        });
        var chosen=candidates[0];pool.delete(pathSignature(chosen));return chosen;
      }

      accept(base);
      while(results.length<requested){
        var source=results.find(function(path){return!expanded.has(pathSignature(path));});
        if(source)expand(source);
        var next=selectNext();
        if(!next){if(!source||expansionCount>=10)break;continue;}
        accept(next);
      }
      return results;
    }

    model.candidatePaths=diverseCandidatePaths;
    model.routeFamilySignature=familySignature;
    return model;
  };
  core.__diversityEnhanced=true;
})(typeof window!=="undefined"?window:globalThis);
