(function(root,factory){
  var api=factory();
  if(typeof module==="object"&&module.exports)module.exports=api;
  else root.RoutePlannerCore=api;
})(typeof globalThis!=="undefined"?globalThis:this,function(){
  "use strict";

  function title(value){
    if(typeof value==="string")return value;
    if(value&&typeof value==="object")return value.ja||value.en||Object.values(value)[0]||"";
    return"";
  }
  function normalize(value){var text=String(value||"").normalize("NFKC").replace(/[\s　]/g,"");if(text.endsWith("駅"))text=text.slice(0,-1);return text.toLowerCase();}
  function idOf(item){return item&&item["owl:sameAs"]||"";}
  function stationName(item){return title(item&&item["odpt:stationTitle"])||item&&item["dc:title"]||idOf(item).split(".").pop()||"駅";}
  function railwayName(item){return title(item&&item["odpt:railwayTitle"])||item&&item["dc:title"]||idOf(item).split(".").pop()||"路線";}
  function trainTypeName(item){return title(item&&item["odpt:trainTypeTitle"])||item&&item["dc:title"]||idOf(item).split(".").pop()||"";}
  function asArray(value){return Array.isArray(value)?value:(value?[value]:[]);}
  function distanceMeters(a,b){
    var lat1=Number(a&&a["geo:lat"]),lon1=Number(a&&a["geo:long"]),lat2=Number(b&&b["geo:lat"]),lon2=Number(b&&b["geo:long"]);
    if(!Number.isFinite(lat1)||!Number.isFinite(lon1)||!Number.isFinite(lat2)||!Number.isFinite(lon2))return null;
    var r=6371000,rad=Math.PI/180,dLat=(lat2-lat1)*rad,dLon=(lon2-lon1)*rad;
    var x=Math.sin(dLat/2)*Math.sin(dLat/2)+Math.cos(lat1*rad)*Math.cos(lat2*rad)*Math.sin(dLon/2)*Math.sin(dLon/2);
    return 2*r*Math.atan2(Math.sqrt(x),Math.sqrt(1-x));
  }

  var japaneseHolidayCache=new Map();
  function dateKey(date){return[date.getFullYear(),String(date.getMonth()+1).padStart(2,"0"),String(date.getDate()).padStart(2,"0")].join("-");}
  function japaneseHolidaySet(year){
    if(japaneseHolidayCache.has(year))return japaneseHolidayCache.get(year);
    var holidays=new Set();
    function add(month,day){holidays.add([year,String(month).padStart(2,"0"),String(day).padStart(2,"0")].join("-"));}
    function nthMonday(month,nth){var first=new Date(year,month-1,1),offset=(8-first.getDay())%7;return 1+offset+(nth-1)*7;}
    add(1,1);add(1,nthMonday(1,2));add(2,11);add(2,23);
    add(3,Math.floor(20.8431+0.242194*(year-1980)-Math.floor((year-1980)/4)));
    add(4,29);add(5,3);add(5,4);add(5,5);add(7,nthMonday(7,3));add(8,11);
    add(9,nthMonday(9,3));add(9,Math.floor(23.2488+0.242194*(year-1980)-Math.floor((year-1980)/4)));
    add(10,nthMonday(10,2));add(11,3);add(11,23);
    for(var cursor=new Date(year,0,2);cursor.getFullYear()===year;cursor.setDate(cursor.getDate()+1)){
      if(holidays.has(dateKey(cursor)))continue;
      var before=new Date(cursor);before.setDate(before.getDate()-1);var after=new Date(cursor);after.setDate(after.getDate()+1);
      if(holidays.has(dateKey(before))&&holidays.has(dateKey(after)))holidays.add(dateKey(cursor));
    }
    Array.from(holidays).sort().forEach(function(key){
      var parts=key.split("-").map(Number),holiday=new Date(parts[0],parts[1]-1,parts[2]);
      if(holiday.getDay()!==0)return;
      var substitute=new Date(holiday);substitute.setDate(substitute.getDate()+1);
      while(holidays.has(dateKey(substitute)))substitute.setDate(substitute.getDate()+1);
      holidays.add(dateKey(substitute));
    });
    japaneseHolidayCache.set(year,holidays);return holidays;
  }
  function serviceDate(date){var result=new Date(date);if(result.getHours()<3)result.setDate(result.getDate()-1);return result;}
  function serviceForDate(date){var service=serviceDate(date),day=service.getDay();return day===0||day===6||japaneseHolidaySet(service.getFullYear()).has(dateKey(service))?"holiday":"weekday";}
  function departureMinutesForDate(date){var hour=date.getHours();return(hour<3?hour+24:hour)*60+date.getMinutes();}

  function MinHeap(){this.items=[];}
  MinHeap.prototype.push=function(item){
    var a=this.items;a.push(item);var i=a.length-1;
    while(i>0){var p=(i-1)>>1;if(a[p].cost<=item.cost)break;a[i]=a[p];i=p;}a[i]=item;
  };
  MinHeap.prototype.pop=function(){
    var a=this.items;if(!a.length)return null;var first=a[0],last=a.pop();
    if(a.length){var i=0;while(true){var left=i*2+1,right=left+1;if(left>=a.length)break;var child=right<a.length&&a[right].cost<a[left].cost?right:left;if(a[child].cost>=last.cost)break;a[i]=a[child];i=child;}a[i]=last;}
    return first;
  };

  function stationPairKey(a,b){return a<b?a+"\u0001"+b:b+"\u0001"+a;}
  function createModel(payloads,options){
    var blockedStationPairs=new Set(options&&options.blockedStationPairs||[]);
    var graph=new Map(),stationById=new Map(),railwayById=new Map(),trainTypeById=new Map(),railwaysByStation=new Map();
    function addEdge(from,to,edge){if(!from||!to||from===to)return;if(!graph.has(from))graph.set(from,[]);graph.get(from).push(Object.assign({to:to},edge));}
    (payloads||[]).forEach(function(payload){
      (payload&&payload.Station||[]).forEach(function(item){var id=idOf(item);if(id)stationById.set(id,item);});
      (payload&&payload.Railway||[]).forEach(function(item){var id=idOf(item);if(id)railwayById.set(id,item);});
      (payload&&payload.TrainType||[]).forEach(function(item){var id=idOf(item);if(id)trainTypeById.set(id,item);});
    });

    railwayById.forEach(function(railway,railwayId){
      var order=asArray(railway["odpt:stationOrder"]).slice();
      order.sort(function(a,b){return Number(a&&a["odpt:index"]||0)-Number(b&&b["odpt:index"]||0);});
      var label=railwayName(railway),color=String(railway["odpt:color"]||"");
      order.forEach(function(row){var station=row&&row["odpt:station"];if(!station)return;if(!railwaysByStation.has(station))railwaysByStation.set(station,[]);if(railwaysByStation.get(station).indexOf(railwayId)<0)railwaysByStation.get(station).push(railwayId);});
      for(var i=0;i<order.length-1;i++){
        var from=order[i]&&order[i]["odpt:station"],to=order[i+1]&&order[i+1]["odpt:station"];
        if(!from||!to)continue;
        var meters=distanceMeters(stationById.get(from),stationById.get(to));
        var rideCost=meters===null?1:Math.max(1,Math.ceil(meters/2000));
        addEdge(from,to,{type:"ride",railway:railwayId,label:label,color:color,cost:rideCost});
        addEdge(to,from,{type:"ride",railway:railwayId,label:label,color:color,cost:rideCost});
      }
    });

    stationById.forEach(function(station,stationId){
      asArray(station["odpt:railway"]).forEach(function(railwayId){
        if(!railwaysByStation.has(stationId))railwaysByStation.set(stationId,[]);
        if(railwaysByStation.get(stationId).indexOf(railwayId)<0)railwaysByStation.get(stationId).push(railwayId);
      });
    });

    var buckets=new Map();
    stationById.forEach(function(station,id){
      var name=stationName(station),key=normalize(name);if(!key)return;
      if(!buckets.has(key))buckets.set(key,{name:name,nodes:[]});
      buckets.get(key).nodes.push(id);
    });

    function samePlace(aId,bId){
      var a=stationById.get(aId),b=stationById.get(bId),meters=distanceMeters(a,b);
      if(meters!==null)return meters<=850;
      return asArray(a&&a["odpt:connectingStation"]).indexOf(bId)>=0||asArray(b&&b["odpt:connectingStation"]).indexOf(aId)>=0;
    }
    function operatorIds(item){return asArray(item&&item["odpt:operator"]);}
    function sameOperator(a,b){
      var first=operatorIds(a),second=new Set(operatorIds(b));
      return first.some(function(id){return second.has(id);});
    }
    function transferCost(aId,bId){return sameOperator(stationById.get(aId),stationById.get(bId))?1:6;}
    function railwaySwitchCost(aId,bId){return sameOperator(railwayById.get(aId),railwayById.get(bId))?1:6;}
    function lineLabels(nodes){
      var labels=[];
      nodes.forEach(function(node){(railwaysByStation.get(node)||[]).forEach(function(id){var label=railwayName(railwayById.get(id)||{"owl:sameAs":id});if(label&&labels.indexOf(label)<0)labels.push(label);});});
      return labels.sort(function(a,b){return a.localeCompare(b,"ja");});
    }

    var stationGroups=new Map(),groupsByName=new Map(),displayNameToKey=new Map(),groupByNode=new Map();
    buckets.forEach(function(bucket,nameKey){
      var clusters=[];
      bucket.nodes.forEach(function(node){
        var matches=clusters.filter(function(candidate){return candidate.some(function(other){return samePlace(node,other);});});
        if(!matches.length){clusters.push([node]);return;}
        var primary=matches[0];primary.push(node);
        matches.slice(1).forEach(function(extra){
          extra.forEach(function(other){if(primary.indexOf(other)<0)primary.push(other);});
          clusters.splice(clusters.indexOf(extra),1);
        });
      });
      var groups=clusters.map(function(nodes,index){
        var labels=lineLabels(nodes),label=bucket.name;
        if(clusters.length>1)label+="（"+(labels.slice(0,2).join("・")||"路線を確認")+"）";
        var key=nameKey+"::"+index,group={key:key,name:bucket.name,label:label,nodes:nodes,railways:labels};
        stationGroups.set(key,group);nodes.forEach(function(node){groupByNode.set(node,group);});displayNameToKey.set(normalize(label),key);return group;
      });
      groupsByName.set(nameKey,groups);
      if(groups.length===1)displayNameToKey.set(nameKey,groups[0].key);
    });

    stationGroups.forEach(function(group){
      for(var i=0;i<group.nodes.length;i++)for(var j=i+1;j<group.nodes.length;j++){
        if(blockedStationPairs.has(stationPairKey(group.nodes[i],group.nodes[j])))continue;
        var cost=transferCost(group.nodes[i],group.nodes[j]);
        addEdge(group.nodes[i],group.nodes[j],{type:"transfer",label:"乗換",cost:cost});
        addEdge(group.nodes[j],group.nodes[i],{type:"transfer",label:"乗換",cost:cost});
      }
    });
    stationById.forEach(function(station,stationId){
      asArray(station["odpt:connectingStation"]).forEach(function(connectedId){
        if(!stationById.has(connectedId))return;
        var cost=transferCost(stationId,connectedId);
        addEdge(stationId,connectedId,{type:"transfer",label:"乗換",cost:cost});
        addEdge(connectedId,stationId,{type:"transfer",label:"乗換",cost:cost});
      });
    });

    function resolveInput(value){
      var normalized=normalize(value),key=displayNameToKey.get(normalized);
      if(key)return{group:stationGroups.get(key),ambiguous:false};
      var matches=groupsByName.get(normalized)||[];
      return{group:matches.length===1?matches[0]:null,ambiguous:matches.length>1};
    }
    function stateKey(node,railway){return node+"\u0001"+(railway||"");}
    function graphEdgeKey(from,edge){return[from,edge.to,edge.type,edge.railway||""].join("\u0001");}
    function shortestPath(originGroup,destinationGroup,options){
      var allowed=options&&options.allowedRailways?new Set(options.allowedRailways):null;
      var blockedEdges=new Set(options&&options.blockedEdges||[]),blockedRailways=new Set(options&&options.blockedRailways||[]);
      var targets=new Set(destinationGroup.nodes),dist=new Map(),prev=new Map(),heap=new MinHeap(),reached=null;
      originGroup.nodes.forEach(function(node){var key=stateKey(node,"");dist.set(key,0);heap.push({key:key,node:node,railway:"",cost:0});});
      while(heap.items.length){
        var current=heap.pop();if(current.cost!==dist.get(current.key))continue;
        if(targets.has(current.node)){reached=current;break;}
        (graph.get(current.node)||[]).forEach(function(edge){
          if(allowed&&edge.type==="ride"&&!allowed.has(edge.railway))return;
          if(edge.type==="ride"&&blockedRailways.has(edge.railway))return;
          if(blockedEdges.has(graphEdgeKey(current.node,edge)))return;
          var nextRailway=edge.type==="ride"?edge.railway:"";
          var switchPenalty=edge.type==="ride"&&current.railway&&current.railway!==edge.railway?railwaySwitchCost(current.railway,edge.railway):0;
          var nextCost=current.cost+edge.cost+switchPenalty,nextKey=stateKey(edge.to,nextRailway);
          if(nextCost<(dist.has(nextKey)?dist.get(nextKey):Infinity)){
            dist.set(nextKey,nextCost);prev.set(nextKey,{previousKey:current.key,from:current.node,to:edge.to,edge:edge});
            heap.push({key:nextKey,node:edge.to,railway:nextRailway,cost:nextCost});
          }
        });
      }
      if(!reached)return null;
      var edges=[],cursor=reached.key;
      while(prev.has(cursor)){var step=prev.get(cursor);edges.push({from:step.from,to:step.to,edge:step.edge});cursor=step.previousKey;}
      edges.reverse();return{edges:edges,cost:reached.cost};
    }
    function candidatePaths(originGroup,destinationGroup,options){
      var limit=Math.max(1,Math.min(8,Number(options&&options.limit)||5));
      var allowed=options&&options.allowedRailways?Array.from(options.allowedRailways):null;
      var base=shortestPath(originGroup,destinationGroup,{allowedRailways:allowed});
      if(!base)return[];
      var results=[base],resultSignatures=new Set(),pool=new Map(),expandedSignatures=new Set();
      function signature(path){return segmentsFrom(path).map(function(segment){return[segment.railway,segment.from,segment.to].join("\u0002");}).join("\u0003");}
      function addCandidate(path){
        if(!path||path.cost>base.cost+Math.max(12,Math.ceil(base.cost*0.8)))return;
        var key=signature(path);if(!key||resultSignatures.has(key))return;
        var existing=pool.get(key);if(!existing||path.cost<existing.cost)pool.set(key,path);
      }
      resultSignatures.add(signature(base));
      while(results.length<limit){
        var source=results.find(function(path){return!expandedSignatures.has(signature(path));});
        if(source){
          expandedSignatures.add(signature(source));
          var edgeIndexes=[],edgeCount=source.edges.length,stride=Math.max(1,Math.ceil(edgeCount/20));
          source.edges.forEach(function(step,index){
            if(step.edge.type==="transfer"||index===0||index===edgeCount-1||index%stride===0)edgeIndexes.push(index);
            var previous=source.edges[index-1];
            if(previous&&previous.edge.railway!==step.edge.railway)edgeIndexes.push(index-1,index);
          });
          Array.from(new Set(edgeIndexes)).forEach(function(index){
            var step=source.edges[index];if(!step)return;
            addCandidate(shortestPath(originGroup,destinationGroup,{allowedRailways:allowed,blockedEdges:[graphEdgeKey(step.from,step.edge)]}));
          });
          var railways=Array.from(new Set(segmentsFrom(source).map(function(segment){return segment.railway;})));
          railways.forEach(function(railway){
            addCandidate(shortestPath(originGroup,destinationGroup,{allowedRailways:allowed,blockedRailways:[railway]}));
          });
        }
        var ranked=Array.from(pool.entries()).sort(function(first,second){return first[1].cost-second[1].cost;});
        if(!ranked.length){
          if(!source)break;
          continue;
        }
        var selected=ranked[0];pool.delete(selected[0]);
        if(resultSignatures.has(selected[0]))continue;
        resultSignatures.add(selected[0]);results.push(selected[1]);
      }
      return results;
    }
    function segmentsFrom(path){
      var segments=[],pendingTransfer=false;
      (path&&path.edges||[]).forEach(function(step){
        if(step.edge.type==="transfer"){pendingTransfer=true;return;}
        var last=segments[segments.length-1];
        if(last&&last.railway===step.edge.railway&&!pendingTransfer){last.to=step.to;last.stops+=1;}
        else segments.push({railway:step.edge.railway,label:step.edge.label,color:step.edge.color,from:step.from,to:step.to,stops:1,transferBefore:segments.length>0||pendingTransfer});
        pendingTransfer=false;
      });
      return segments;
    }

    function calendarMatches(value,service){
      var text=String(value||"").toLowerCase();
      if(!text)return true;
      if(service==="weekday")return text.indexOf("weekday")>=0||text.indexOf("平日")>=0;
      return text.indexOf("saturdayholiday")>=0||text.indexOf("saturdayandholiday")>=0||text.indexOf("weekend")>=0||text.indexOf("saturday")>=0||text.indexOf("sunday")>=0||text.indexOf("holiday")>=0||text.indexOf("土休日")>=0||text.indexOf("土曜")>=0||text.indexOf("休日")>=0;
    }
    function timetableTrip(timetable,fromNodes,toNodes,earliest,service,latest){
      if(!timetable||!Array.isArray(timetable.trips))return null;
      var stations=timetable.stations||[],calendars=timetable.calendars||[],types=timetable.trainTypes||[];
      var fromSet=new Set(fromNodes),toSet=new Set(toNodes),best=null;
      timetable.trips.forEach(function(trip){
        if(!Array.isArray(trip)||!calendarMatches(calendars[trip[0]],service))return;
        var stops=trip[3]||[],boarding=-1,departure=null;
        for(var i=0;i<stops.length;i++){
          var stop=stops[i]||[],stationId=stations[stop[0]],dep=stop[2]!=null?Number(stop[2]):Number(stop[1]);
          if(fromSet.has(stationId)&&Number.isFinite(dep)&&dep>=earliest&&(!Number.isFinite(latest)||dep<=latest)){boarding=i;departure=dep;break;}
        }
        if(boarding<0)return;
        for(var j=boarding+1;j<stops.length;j++){
          var next=stops[j]||[],nextStation=stations[next[0]],arrival=next[1]!=null?Number(next[1]):Number(next[2]);
          if(!toSet.has(nextStation)||!Number.isFinite(arrival)||arrival<departure)continue;
          var candidate={departure:departure,arrival:arrival,trainType:types[trip[1]]||"",trainNumber:String(trip[2]||""),destination:timetable.destinationAuthoritative===false?"":(trip.length>4?trip[4]:""),destinationAuthoritative:timetable.destinationAuthoritative!==false,timeBasis:timetable.timeBasis||"train-timetable"};
          var windowed=Number.isFinite(latest);
          if(!best||(windowed&&(candidate.departure<best.departure||(candidate.departure===best.departure&&candidate.arrival<best.arrival)))||(!windowed&&(candidate.arrival<best.arrival||(candidate.arrival===best.arrival&&candidate.departure<best.departure))))best=candidate;
          break;
        }
      });
      return best;
    }
    function stationDepartureTrip(table,fromNodes,toNodes,earliest,service,latest,requiredDestination){
      if(!table||table.timeBasis!=="station-departure-only"||!Array.isArray(table.boards))return null;
      var order=table.order||[],fromOrder=-1,toOrder=-1;
      for(var i=0;i<order.length;i++){
        if(fromOrder<0&&fromNodes.indexOf(order[i])>=0)fromOrder=i;
        if(toOrder<0&&toNodes.indexOf(order[i])>=0)toOrder=i;
      }
      var desiredDirection="";
      if(fromOrder>=0&&toOrder>=0&&fromOrder!==toOrder)desiredDirection=toOrder>fromOrder?table.ascendingDirection:table.descendingDirection;
      var stations=table.stations||[],calendars=table.calendars||[],directions=table.directions||[],types=table.trainTypes||[],destinations=table.destinations||[],destinationAuthoritative=table.destinationAuthoritative!==false,best=null;
      var stationIndexes=new Map();stations.forEach(function(station,index){stationIndexes.set(station,index);});
      var observedTrips=new Map();
      (table.inferredTrips||[]).forEach(function(trip){
        if(!Array.isArray(trip)||!calendarMatches(calendars[trip[0]],service))return;
        var direction=directions[trip[1]]||"";
        if(desiredDirection&&direction&&direction!==desiredDirection)return;
        var stops=trip[5]||[],boarding=-1,departure=null;
        for(var stopIndex=0;stopIndex<stops.length;stopIndex++){
          var stop=stops[stopIndex]||[],stationId=stations[stop[0]],dep=Number(stop[2]);
          if(fromNodes.indexOf(stationId)>=0&&Number.isFinite(dep)&&dep>=earliest&&(!Number.isFinite(latest)||dep<=latest)){boarding=stopIndex;departure=dep;break;}
        }
        if(boarding<0)return;
        for(var destinationStop=boarding+1;destinationStop<stops.length;destinationStop++){
          var next=stops[destinationStop]||[],nextStation=stations[next[0]],arrival=next[1]!=null?Number(next[1]):Number(next[2]);
          if(toNodes.indexOf(nextStation)<0||!Number.isFinite(arrival)||arrival<departure)continue;
          var key=[trip[0],trip[1],trip[2],trip[3],departure].join("\u0001");
          var candidate={departure:departure,arrival:arrival,trainType:types[trip[2]]||"",destination:destinationAuthoritative?(destinations[trip[3]]||""):"",destinationAuthoritative:destinationAuthoritative,trainNumber:"",confidence:Number(trip[4])||0,timeBasis:"inferred-station-trip"};
          if(requiredDestination&&candidate.destination!==requiredDestination)continue;
          var existing=observedTrips.get(key);
          if(!existing||candidate.arrival<existing.arrival)observedTrips.set(key,candidate);
          break;
        }
      });
      var edges=new Map();
      (table.edgeMinutes||[]).forEach(function(row){
        if(Array.isArray(row))edges.set(String(stations[row[0]])+"\u0001"+String(stations[row[1]]),Number(row[2]));
      });
      function edgeSum(startOrder,endOrder){
        if(startOrder===endOrder)return 0;
        var step=endOrder>startOrder?1:-1,total=0;
        for(var index=startOrder;index!==endOrder;index+=step){
          var minutes=edges.get(String(order[index])+"\u0001"+String(order[index+step]));
          if(!Number.isFinite(minutes)||minutes<=0){
            var meters=distanceMeters(stationById.get(order[index]),stationById.get(order[index+step]));
            if(meters===null)return null;
            minutes=Math.max(2,Math.ceil(meters/750));
          }
          total+=minutes;
        }
        return total;
      }
      function minimumMinutes(startOrder,endOrder){
        var fromStation=stationById.get(order[startOrder]),toStation=stationById.get(order[endOrder]),meters=distanceMeters(fromStation,toStation);
        return meters===null?1:Math.max(1,Math.ceil(meters/2000));
      }
      function consistentProfile(typeIndex,destinationIndex,allowAnyDestination){
        var fromIndex=stationIndexes.get(order[fromOrder]),step=toOrder>fromOrder?1:-1,states=[],latest=null;
        for(var checkpoint=fromOrder+step;;checkpoint+=step){
          var checkpointIndex=stationIndexes.get(order[checkpoint]),minimum=minimumMinutes(fromOrder,checkpoint),maximum=edgeSum(fromOrder,checkpoint),rows=[];
          (table.typeDurations||[]).forEach(function(row){
            if(!Array.isArray(row)||row[0]!==fromIndex||row[1]!==checkpointIndex||row[2]!==typeIndex)return;
            if(!allowAnyDestination&&row[3]!==destinationIndex)return;
            var duration=Number(row[4]),support=Number(row[5]);
            if(!Number.isFinite(duration)||duration<minimum||(maximum!==null&&duration>maximum+5)||!Number.isFinite(support)||support<=0)return;
            rows.push({row:row,order:checkpoint,minutes:duration,support:support,score:support});
          });
          if(rows.length){
            rows.forEach(function(candidate){
              var predecessor=null;
              states.forEach(function(state){
                if(allowAnyDestination&&state.row[3]!==candidate.row[3])return;
                if(candidate.minutes<state.minutes+minimumMinutes(state.order,checkpoint))return;
                if(!predecessor||state.score>predecessor.score||(state.score===predecessor.score&&state.minutes<predecessor.minutes))predecessor=state;
              });
              if(predecessor)candidate.score+=predecessor.score;
            });
            states=states.concat(rows);
            latest=rows.reduce(function(bestState,state){
              if(!bestState||state.score>bestState.score||(state.score===bestState.score&&state.minutes<bestState.minutes))return state;
              return bestState;
            },null);
          }
          if(checkpoint===toOrder)break;
        }
        return latest;
      }
      function partialRemainder(profile){
        if(!profile||profile.order===toOrder)return 0;
        var generic=edgeSum(profile.order,toOrder),minimum=minimumMinutes(profile.order,toOrder);
        var originStation=stationById.get(order[fromOrder]),profileStation=stationById.get(order[profile.order]),destinationStation=stationById.get(order[toOrder]);
        var travelled=distanceMeters(originStation,profileStation),remaining=distanceMeters(profileStation,destinationStation),estimate=null;
        if(travelled!==null&&remaining!==null&&travelled>0)estimate=Math.ceil(profile.minutes*remaining/travelled);
        if(!Number.isFinite(estimate))return generic;
        estimate=Math.max(minimum,estimate);
        return generic===null?estimate:Math.min(generic,estimate);
      }
      var journeyCache=new Map();
      function journeyMinutes(typeIndex,destinationIndex){
        var cacheKey=String(typeIndex)+"\u0001"+String(destinationIndex);
        if(journeyCache.has(cacheKey))return journeyCache.get(cacheKey);
        var result=null;
        if(fromOrder<0||toOrder<0||fromOrder===toOrder)return null;
        var typeLabel=trainTypeName(trainTypeById.get(types[typeIndex])||{"owl:sameAs":types[typeIndex]}).toLowerCase();
        var isLocal=typeLabel.indexOf("local")>=0||typeLabel.indexOf("普通")>=0||typeLabel.indexOf("各停")>=0||typeLabel.indexOf("各駅")>=0;
        if(isLocal)result=edgeSum(fromOrder,toOrder);
        else{
          var profile=consistentProfile(typeIndex,destinationIndex,false)||consistentProfile(typeIndex,destinationIndex,true);
          if(profile){
            var remainder=partialRemainder(profile);
            if(remainder!==null)result=profile.minutes+remainder;
          }
        }
        journeyCache.set(cacheKey,result);
        return result;
      }
      table.boards.forEach(function(board){
        if(!Array.isArray(board)||fromNodes.indexOf(stations[board[0]])<0||!calendarMatches(calendars[board[1]],service))return;
        var direction=directions[board[2]]||"";
        if(desiredDirection&&direction&&direction!==desiredDirection)return;
        (board[3]||[]).forEach(function(row){
          var minute=Number(row&&row[0]);if(!Number.isFinite(minute)||minute<earliest||(Number.isFinite(latest)&&minute>latest))return;
          var typeIndex=Number(row[1]),destinationIndex=row.length>2?Number(row[2]):-1;
          var observedKey=[board[1],board[2],typeIndex,destinationIndex,minute].join("\u0001");
          var candidate=observedTrips.get(observedKey);
          if(!candidate){
            var duration=journeyMinutes(typeIndex,destinationIndex);
            candidate={departure:minute,arrival:Number.isFinite(duration)?minute+duration:null,trainType:types[typeIndex]||"",destination:destinationAuthoritative?(destinations[destinationIndex]||""):"",destinationAuthoritative:destinationAuthoritative,trainNumber:"",timeBasis:"estimated-edge-duration"};
          }
          if(requiredDestination&&candidate.destination!==requiredDestination)return;
          var windowed=Number.isFinite(latest);
          if(!best||(windowed&&(candidate.departure<best.departure||(candidate.departure===best.departure&&Number.isFinite(candidate.arrival)&&(!Number.isFinite(best.arrival)||candidate.arrival<best.arrival))))||(!windowed&&((Number.isFinite(candidate.arrival)&&(!Number.isFinite(best.arrival)||candidate.arrival<best.arrival))||(candidate.arrival===best.arrival&&candidate.departure<best.departure)||(!Number.isFinite(candidate.arrival)&&!Number.isFinite(best.arrival)&&candidate.departure<best.departure))))best=candidate;
        });
      });
      return best;
    }
    function timedItinerary(path,timetablesByRailway,departureMinutes,service,transferMinutes,transferResolver){
      var segments=segmentsFrom(path),current=Number(departureMinutes),buffer=Number(transferMinutes==null?5:transferMinutes),timed=[];
      if(!Number.isFinite(current)||!segments.length)return null;
      for(var i=0;i<segments.length;i++){
        var segment=segments[i],fromGroup=groupByNode.get(segment.from),toGroup=groupByNode.get(segment.to);
        var table=timetablesByRailway&&timetablesByRailway[segment.railway];
        var fromNodes=fromGroup?fromGroup.nodes:[segment.from],toNodes=toGroup?toGroup.nodes:[segment.to];
        var previous=i>0?timed[i-1]:null;
        // Through-service identity must come from precomputed train identity data.
        // Destination similarity or a short timetable gap is never sufficient proof.
        var interchangeBuffer=buffer,transferRule=null;
        if(previous){
          var interchangeMeters=distanceMeters(stationById.get(previous.to),stationById.get(segment.from));
          if(interchangeMeters!==null)interchangeBuffer=Math.max(buffer,Math.min(15,Math.ceil(interchangeMeters/75)+2));
          if(typeof transferResolver==="function"){
            var resolvedTransfer=transferResolver({
              fromStationId:previous.to,toStationId:segment.from,
              fromStationName:stationName(stationById.get(previous.to)),toStationName:stationName(stationById.get(segment.from)),
              fromRailway:previous.railway,toRailway:segment.railway,
              fromRailwayName:railwayName(railwayById.get(previous.railway)||{"owl:sameAs":previous.railway}),
              toRailwayName:railwayName(railwayById.get(segment.railway)||{"owl:sameAs":segment.railway}),
              fallbackMinutes:interchangeBuffer
            });
            if(resolvedTransfer&&Number.isFinite(Number(resolvedTransfer.minutes))){
              interchangeBuffer=Math.max(0,Number(resolvedTransfer.minutes));
              transferRule=resolvedTransfer;
            }
          }
        }
        var earliest=current+(i>0?interchangeBuffer:0);
        var trip=table&&table.timeBasis==="station-departure-only"?stationDepartureTrip(table,fromNodes,toNodes,earliest,service):timetableTrip(table,fromNodes,toNodes,earliest,service);
        if(!trip||!Number.isFinite(trip.arrival))return null;
        if(i>0&&!trip.throughFromPrevious){
          trip.transferMinutes=interchangeBuffer;
          if(transferRule){
            trip.transferRule=String(transferRule.id||"");
            trip.transferRuleLabel=String(transferRule.label||"");
            trip.transferSamePlatform=Boolean(transferRule.samePlatform);
          }
        }
        timed.push(Object.assign({},segment,trip));current=trip.arrival;
      }
      return{segments:timed,departure:timed[0].departure,arrival:timed[timed.length-1].arrival,duration:timed[timed.length-1].arrival-timed[0].departure,transfers:timed.slice(1).filter(function(segment){return!segment.throughFromPrevious;}).length,estimatedArrival:timed.some(function(segment){return segment.timeBasis==="station-departure"||segment.timeBasis==="inferred-station-trip"||segment.timeBasis==="estimated-edge-duration";})};
    }

    function nextDeparture(path,timetablesByRailway,departureMinutes,service){
      var segments=segmentsFrom(path),segment=segments[0];
      if(!segment)return null;
      var table=timetablesByRailway&&timetablesByRailway[segment.railway];
      var fromGroup=groupByNode.get(segment.from),toGroup=groupByNode.get(segment.to);
      var fromNodes=fromGroup?fromGroup.nodes:[segment.from],toNodes=toGroup?toGroup.nodes:[segment.to];
      var best=stationDepartureTrip(table,fromNodes,toNodes,Number(departureMinutes),service);
      return best?Object.assign(best,{railway:segment.railway,label:segment.label,from:segment.from,to:segment.to}):null;
    }

    return{
      graph:graph,stationById:stationById,railwayById:railwayById,trainTypeById:trainTypeById,stationGroups:stationGroups,
      stations:Array.from(stationGroups.values()).sort(function(a,b){return a.label.localeCompare(b.label,"ja");}),
      resolveInput:resolveInput,shortestPath:shortestPath,candidatePaths:candidatePaths,segmentsFrom:segmentsFrom,timedItinerary:timedItinerary,nextDeparture:nextDeparture,
      displayStation:function(id){return stationName(stationById.get(id)||{"owl:sameAs":id});},
      displayTrainType:function(id){return trainTypeName(trainTypeById.get(id)||{"owl:sameAs":id});}
    };
  }

  return{createModel:createModel,normalize:normalize,distanceMeters:distanceMeters,serviceForDate:serviceForDate,departureMinutesForDate:departureMinutesForDate};
});
