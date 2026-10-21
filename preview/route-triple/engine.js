(function(root,factory){
var api=factory();if(typeof module==="object"&&module.exports)module.exports=api;else root.RouteTriPlanner=api;
})(typeof window!=="undefined"?window:globalThis,function(){
"use strict";
function km(a,b){var v=[a&&a["geo:lat"],a&&a["geo:long"],b&&b["geo:lat"],b&&b["geo:long"]].map(Number);if(v.some(x=>!Number.isFinite(x)))return null;var r=Math.PI/180,la=v[0]*r,lb=v[2]*r,dx=(v[2]-v[0])*r,dy=(v[3]-v[1])*r;return 12742000*Math.asin(Math.min(1,Math.sqrt(Math.sin(dx/2)**2+Math.cos(la)*Math.cos(lb)*Math.sin(dy/2)**2)));}
function rideTime(model,a,b){var d=km(model.stationById.get(a),model.stationById.get(b));return d===null?2.1:Math.max(1.1,d/650+.42);}
function Heap(){this.items=[];}
Heap.prototype.push=function(x){var a=this.items,i=a.length;a.push(x);while(i){var p=(i-1)>>1;if(a[p].cost<=x.cost)break;a[i]=a[p];i=p;}a[i]=x;};
Heap.prototype.pop=function(){var a=this.items,x=a[0],last=a.pop();if(a.length){var i=0;while(i*2+1<a.length){var c=i*2+1;if(c+1<a.length&&a[c+1].cost<a[c].cost)c++;if(a[c].cost>=last.cost)break;a[i]=a[c];i=c;}a[i]=last;}return x;};
function state(node,line){return node+"\u0001"+line;}
function search(model,start,end,weight,blocked){
var dist=new Map(),previous=new Map(),heap=new Heap(),targets=new Set(end.nodes),reached=null;
start.nodes.forEach(function(node){var k=state(node,"");dist.set(k,0);heap.push({node:node,line:"",key:k,cost:0});});
while(heap.items.length){var cur=heap.pop();if(cur.cost!==dist.get(cur.key))continue;if(targets.has(cur.node)){reached=cur;break;}
(model.graph.get(cur.node)||[]).forEach(function(edge){if(edge.type==="ride"&&blocked&&blocked.has(edge.railway))return;
var change=edge.type==="ride"&&cur.line&&cur.line!==edge.railway;
var travel=edge.type==="ride"?rideTime(model,cur.node,edge.to):0,walk=edge.type==="transfer"?Math.max(1,Number(edge.cost)||4):0;
var cost=cur.cost+travel*weight.ride+walk*weight.walk+(change?weight.change:0);
var line=edge.type==="ride"?edge.railway:cur.line,k=state(edge.to,line);
if(cost<(dist.has(k)?dist.get(k):Infinity)){dist.set(k,cost);previous.set(k,{parent:cur.key,step:{from:cur.node,to:edge.to,edge:edge}});heap.push({node:edge.to,line:line,key:k,cost:cost});}
});}
if(!reached)return null;var edges=[],cursor=reached.key;while(previous.has(cursor)){var step=previous.get(cursor);edges.push(step.step);cursor=step.parent;}return{edges:edges.reverse(),cost:reached.cost};
}
function rulesIndex(data){var map=new Map();function key(a,b,c,d){return[a||"",b||"",c||"",d||""].join("\u0001");}
(data&&data.rules||[]).forEach(function(r){if(!r.fromRailway||!r.toRailway||!Number.isFinite(Number(r.minutes)))return;map.set(key(r.fromStation,r.toStation,r.fromRailway,r.toRailway),r);if(r.bidirectional)map.set(key(r.toStation,r.fromStation,r.toRailway,r.fromRailway),r);});
return function(a,b,c,d){return map.get(key(a,b,c,d))||null;};
}
function measure(model,path,getRule){
var legs=[],ride=0,walk=0,changes=0,pendingWalk=0;
path.edges.forEach(function(step){var e=step.edge;if(e.type==="transfer"){pendingWalk+=Math.max(1,Number(e.cost)||4);return;}
ride+=rideTime(model,step.from,step.to);var last=legs[legs.length-1];
if(last&&last.railway===e.railway&&!pendingWalk){last.to=step.to;last.stops++;return;}
var transfer=null;if(last){changes++;var rule=getRule(last.to,step.from,last.railway,e.railway);var min=rule?Number(rule.minutes):(pendingWalk||4);walk+=min;transfer={station:model.displayStation(last.to),minutes:min,verified:!!(rule&&rule.verifiedAt),label:rule?String(rule.label||"乗換移動"):"暫定の乗換移動"};}else if(pendingWalk){walk+=pendingWalk;}
legs.push({railway:e.railway,label:e.label||e.railway,color:e.color||"#36558b",from:step.from,to:step.to,stops:1,transfer:transfer});pendingWalk=0;});
walk+=pendingWalk;
return{legs:legs,changes:changes,walking:walk,riding:ride,minutes:Math.round(ride+walk+changes*4+4)};
}
function signature(model,path){return model.segmentsFrom(path).map(s=>s.railway).filter((x,i,a)=>i===0||x!==a[i-1]).join(">");}
function corridor(model,path){return model.segmentsFrom(path).map(s=>String(s.railway).split(":").pop().split(".")[0]).filter((x,i,a)=>i===0||x!==a[i-1]).join(">");}
function compare(model,start,end,rules){
if(!model||!start||!end||!start.nodes||!end.nodes)return[];
var settings=[{ride:1,walk:1,change:5},{ride:.33,walk:1.4,change:21},{ride:.7,walk:2,change:9},{ride:1,walk:1.5,change:14},{ride:.12,walk:1.5,change:32}];
var map=new Set(),paths=[],base=[],lookup=rulesIndex(rules);
function add(path){if(!path||!path.edges.length)return;var sig=signature(model,path);if(map.has(sig))return;map.add(sig);paths.push({path:path,id:sig,corridor:corridor(model,path),stats:measure(model,path,lookup)});}
settings.forEach(function(w){var p=search(model,start,end,w);base.push(p);add(p);});
base.filter(Boolean).forEach(function(path){Array.from(new Set(model.segmentsFrom(path).map(s=>s.railway))).forEach(function(line){settings.forEach(function(w){add(search(model,start,end,w,new Set([line])));});});});
if(!paths.length)return[];
var quickest=Math.min.apply(null,paths.map(x=>x.stats.minutes));
paths=paths.filter(x=>x.stats.minutes<=quickest+Math.max(24,Math.round(quickest*.42)));
function effort(x){return x.stats.changes*18+x.stats.walking*1.5+x.stats.minutes*.18;}
paths.sort((a,b)=>a.stats.minutes-b.stats.minutes||effort(a)-effort(b));
var picked=[],used=new Set(),corridors=new Set();
function take(x,tag){if(!x||used.has(x.id))return;picked.push(Object.assign({},x,{tag:tag}));used.add(x.id);corridors.add(x.corridor);}
take(paths[0],"早い");take(paths.slice().sort((a,b)=>effort(a)-effort(b)||a.stats.minutes-b.stats.minutes)[0],"楽");
var candidates=paths.slice().sort((a,b)=>(a.stats.minutes-quickest)+effort(a)*.22-(corridors.has(a.corridor)?0:10)-((b.stats.minutes-quickest)+effort(b)*.22-(corridors.has(b.corridor)?0:10)));
candidates.forEach(x=>{if(picked.length<6&&!corridors.has(x.corridor))take(x,"別ルート");});
candidates.forEach(x=>{if(picked.length<4)take(x,"別ルート");});
return picked.map(x=>({category:x.tag,estimatedMinutes:x.stats.minutes,lineChanges:x.stats.changes,walkMinutes:x.stats.walking,legs:x.stats.legs,signature:x.id,fareYen:null,estimateOnly:true}));
}
return{search:search,measure:measure,compare:compare,rulesIndex:rulesIndex};
});