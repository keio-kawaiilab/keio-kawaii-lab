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

  function createModel(payloads){
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
        addEdge(from,to,{type:"ride",railway:railwayId,label:label,color:color,cost:1});
        addEdge(to,from,{type:"ride",railway:railwayId,label:label,color:color,cost:1});
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
        addEdge(group.nodes[i],group.nodes[j],{type:"transfer",label:"乗換",cost:6});
        addEdge(group.nodes[j],group.nodes[i],{type:"transfer",label:"乗換",cost:6});
      }
    });
    stationById.forEach(function(station,stationId){
      asArray(station["odpt:connectingStation"]).forEach(function(connectedId){
        if(!stationById.has(connectedId))return;
        addEdge(stationId,connectedId,{type:"transfer",label:"乗換",cost:6});
        addEdge(connectedId,stationId,{type:"transfer",label:"乗換",cost:6});
      });
    });

    function resolveInput(value){
      var normalized=normalize(value),key=displayNameToKey.get(normalized);
      if(key)return{group:stationGroups.get(key),ambiguous:false};
      var matches=groupsByName.get(normalized)||[];
      return{group:matches.length===1?matches[0]:null,ambiguous:matches.length>1};
    }
    function stateKey(node,railway){return node+"\u0001"+(railway||"");}
    function shortestPath(originGroup,destinationGroup,options){
      var allowed=options&&options.allowedRailways?new Set(options.allowedRailways):null;
      var targets=new Set(destinationGroup.nodes),dist=new Map(),prev=new Map(),heap=new MinHeap(),reached=null;
      originGroup.nodes.forEach(function(node){var key=stateKey(node,"");dist.set(key,0);heap.push({key:key,node:node,railway:"",cost:0});});
      while(heap.items.length){
        var current=heap.pop();if(current.cost!==dist.get(current.key))continue;
        if(targets.has(current.node)){reached=current;break;}
        (graph.get(current.node)||[]).forEach(function(edge){
          if(allowed&&edge.type==="ride"&&!allowed.has(edge.railway))return;
          var nextRailway=edge.type==="ride"?edge.railway:"";
          var switchPenalty=edge.type==="ride"&&current.railway&&current.railway!==edge.railway?6:0;
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
    function timetableTrip(timetable,fromNodes,toNodes,earliest,service){
      if(!timetable||!Array.isArray(timetable.trips))return null;
      var stations=timetable.stations||[],calendars=timetable.calendars||[],types=timetable.trainTypes||[];
      var fromSet=new Set(fromNodes),toSet=new Set(toNodes),best=null;
      timetable.trips.forEach(function(trip){
        if(!Array.isArray(trip)||!calendarMatches(calendars[trip[0]],service))return;
        var stops=trip[3]||[],boarding=-1,departure=null;
        for(var i=0;i<stops.length;i++){
          var stop=stops[i]||[],stationId=stations[stop[0]],dep=stop[2]!=null?Number(stop[2]):Number(stop[1]);
          if(fromSet.has(stationId)&&Number.isFinite(dep)&&dep>=earliest){boarding=i;departure=dep;break;}
        }
        if(boarding<0)return;
        for(var j=boarding+1;j<stops.length;j++){
          var next=stops[j]||[],nextStation=stations[next[0]],arrival=next[1]!=null?Number(next[1]):Number(next[2]);
          if(!toSet.has(nextStation)||!Number.isFinite(arrival)||arrival<departure)continue;
          var candidate={departure:departure,arrival:arrival,trainType:types[trip[1]]||"",trainNumber:String(trip[2]||""),timeBasis:timetable.timeBasis||"train-timetable"};
          if(!best||candidate.arrival<best.arrival||(candidate.arrival===best.arrival&&candidate.departure<best.departure))best=candidate;
          break;
        }
      });
      return best;
    }
    function stationDepartureTrip(table,fromNodes,toNodes,earliest,service){
      if(!table||table.timeBasis!=="station-departure-only"||!Array.isArray(table.boards))return null;
      var order=table.order||[],fromOrder=-1,toOrder=-1;
      for(var i=0;i<order.length;i++){
        if(fromOrder<0&&fromNodes.indexOf(order[i])>=0)fromOrder=i;
        if(toOrder<0&&toNodes.indexOf(order[i])>=0)toOrder=i;
      }
      var desiredDirection="";
      if(fromOrder>=0&&toOrder>=0&&fromOrder!==toOrder)desiredDirection=toOrder>fromOrder?table.ascendingDirection:table.descendingDirection;
      var stations=table.stations||[],calendars=table.calendars||[],directions=table.directions||[],types=table.trainTypes||[],best=null;
      var stationIndexes=new Map();stations.forEach(function(station,index){stationIndexes.set(station,index);});
      var edges=new Map();
      (table.edgeMinutes||[]).forEach(function(row){
        if(Array.isArray(row))edges.set(String(stations[row[0]])+"\u0001"+String(stations[row[1]]),Number(row[2]));
      });
      function edgeSum(startOrder,endOrder){
        if(startOrder===endOrder)return 0;
        var step=endOrder>startOrder?1:-1,total=0;
        for(var index=startOrder;index!==endOrder;index+=step){
          var minutes=edges.get(String(order[index])+"\u0001"+String(order[index+step]));
          if(!Number.isFinite(minutes)||minutes<=0)return null;
          total+=minutes;
        }
        return total;
      }
      function profileFor(startOrder,endOrder,typeIndex,destinationIndex,allowAnyDestination){
        var fromIndex=stationIndexes.get(order[startOrder]),toIndex=stationIndexes.get(order[endOrder]),found=null;
        (table.typeDurations||[]).forEach(function(row){
          if(!Array.isArray(row)||row[0]!==fromIndex||row[1]!==toIndex||row[2]!==typeIndex)return;
          if(!allowAnyDestination&&row[3]!==destinationIndex)return;
          if(!found||Number(row[5])>Number(found[5]))found=row;
        });
        return found;
      }
      function journeyMinutes(typeIndex,destinationIndex){
        if(fromOrder<0||toOrder<0||fromOrder===toOrder)return null;
        var direct=profileFor(fromOrder,toOrder,typeIndex,destinationIndex,false)||profileFor(fromOrder,toOrder,typeIndex,destinationIndex,true);
        if(direct)return Number(direct[4]);
        var step=toOrder>fromOrder?1:-1,bestPartial=null;
        for(var checkpoint=fromOrder+step;checkpoint!==toOrder;checkpoint+=step){
          var profile=profileFor(fromOrder,checkpoint,typeIndex,destinationIndex,false)||profileFor(fromOrder,checkpoint,typeIndex,destinationIndex,true);
          if(profile)bestPartial={order:checkpoint,minutes:Number(profile[4])};
        }
        if(bestPartial){
          var remainder=edgeSum(bestPartial.order,toOrder);
          if(remainder!==null)return bestPartial.minutes+remainder;
        }
        var typeLabel=trainTypeName(trainTypeById.get(types[typeIndex])||{"owl:sameAs":types[typeIndex]}).toLowerCase();
        if(typeLabel.indexOf("local")<0&&typeLabel.indexOf("普通")<0&&typeLabel.indexOf("各停")<0&&typeLabel.indexOf("各駅")<0)return null;
        return edgeSum(fromOrder,toOrder);
      }
      table.boards.forEach(function(board){
        if(!Array.isArray(board)||fromNodes.indexOf(stations[board[0]])<0||!calendarMatches(calendars[board[1]],service))return;
        var direction=directions[board[2]]||"";
        if(desiredDirection&&direction&&direction!==desiredDirection)return;
        (board[3]||[]).forEach(function(row){
          var minute=Number(row&&row[0]);if(!Number.isFinite(minute)||minute<earliest)return;
          var typeIndex=Number(row[1]),destinationIndex=row.length>2?Number(row[2]):-1,duration=journeyMinutes(typeIndex,destinationIndex);
          var candidate={departure:minute,arrival:Number.isFinite(duration)?minute+duration:null,trainType:types[typeIndex]||"",trainNumber:"",timeBasis:"estimated-edge-duration"};
          if(!best||(Number.isFinite(candidate.arrival)&&(!Number.isFinite(best.arrival)||candidate.arrival<best.arrival))||(candidate.arrival===best.arrival&&candidate.departure<best.departure)||(!Number.isFinite(candidate.arrival)&&!Number.isFinite(best.arrival)&&candidate.departure<best.departure))best=candidate;
        });
      });
      return best;
    }
    function timedItinerary(path,timetablesByRailway,departureMinutes,service,transferMinutes){
      var segments=segmentsFrom(path),current=Number(departureMinutes),buffer=Number(transferMinutes==null?5:transferMinutes),timed=[];
      if(!Number.isFinite(current)||!segments.length)return null;
      for(var i=0;i<segments.length;i++){
        var segment=segments[i],fromGroup=groupByNode.get(segment.from),toGroup=groupByNode.get(segment.to);
        var earliest=current+(i>0?buffer:0);
        var table=timetablesByRailway&&timetablesByRailway[segment.railway];
        var fromNodes=fromGroup?fromGroup.nodes:[segment.from],toNodes=toGroup?toGroup.nodes:[segment.to];
        var trip=table&&table.timeBasis==="station-departure-only"?stationDepartureTrip(table,fromNodes,toNodes,earliest,service):timetableTrip(table,fromNodes,toNodes,earliest,service);
        if(!trip||!Number.isFinite(trip.arrival))return null;
        timed.push(Object.assign({},segment,trip));current=trip.arrival;
      }
      return{segments:timed,departure:timed[0].departure,arrival:timed[timed.length-1].arrival,duration:timed[timed.length-1].arrival-timed[0].departure,transfers:Math.max(0,timed.length-1),estimatedArrival:timed.some(function(segment){return segment.timeBasis==="station-departure"||segment.timeBasis==="estimated-edge-duration";})};
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
      resolveInput:resolveInput,shortestPath:shortestPath,segmentsFrom:segmentsFrom,timedItinerary:timedItinerary,nextDeparture:nextDeparture,
      displayStation:function(id){return stationName(stationById.get(id)||{"owl:sameAs":id});},
      displayTrainType:function(id){return trainTypeName(trainTypeById.get(id)||{"owl:sameAs":id});}
    };
  }

  return{createModel:createModel,normalize:normalize,distanceMeters:distanceMeters};
});
