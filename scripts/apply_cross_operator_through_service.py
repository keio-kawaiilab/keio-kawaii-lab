from pathlib import Path

path = Path("route-core.js")
text = path.read_text(encoding="utf-8")

replacements = [
    (
        'function timetableTrip(timetable,fromNodes,toNodes,earliest,service){',
        'function timetableTrip(timetable,fromNodes,toNodes,earliest,service,latest){',
    ),
    (
        'if(fromSet.has(stationId)&&Number.isFinite(dep)&&dep>=earliest){boarding=i;departure=dep;break;}',
        'if(fromSet.has(stationId)&&Number.isFinite(dep)&&dep>=earliest&&(!Number.isFinite(latest)||dep<=latest)){boarding=i;departure=dep;break;}',
    ),
    (
        'if(!best||candidate.arrival<best.arrival||(candidate.arrival===best.arrival&&candidate.departure<best.departure))best=candidate;',
        'var windowed=Number.isFinite(latest);\n          if(!best||(windowed&&(candidate.departure<best.departure||(candidate.departure===best.departure&&candidate.arrival<best.arrival)))||(!windowed&&(candidate.arrival<best.arrival||(candidate.arrival===best.arrival&&candidate.departure<best.departure))))best=candidate;',
    ),
    (
        'function stationDepartureTrip(table,fromNodes,toNodes,earliest,service){',
        'function stationDepartureTrip(table,fromNodes,toNodes,earliest,service,latest,requiredDestination){',
    ),
    (
        'if(fromNodes.indexOf(stationId)>=0&&Number.isFinite(dep)&&dep>=earliest){boarding=stopIndex;departure=dep;break;}',
        'if(fromNodes.indexOf(stationId)>=0&&Number.isFinite(dep)&&dep>=earliest&&(!Number.isFinite(latest)||dep<=latest)){boarding=stopIndex;departure=dep;break;}',
    ),
    (
        'var candidate={departure:departure,arrival:arrival,trainType:types[trip[2]]||"",destination:destinations[trip[3]]||"",trainNumber:"",confidence:Number(trip[4])||0,timeBasis:"inferred-station-trip"};\n          var existing=observedTrips.get(key);',
        'var candidate={departure:departure,arrival:arrival,trainType:types[trip[2]]||"",destination:destinations[trip[3]]||"",trainNumber:"",confidence:Number(trip[4])||0,timeBasis:"inferred-station-trip"};\n          if(requiredDestination&&candidate.destination!==requiredDestination)continue;\n          var existing=observedTrips.get(key);',
    ),
    (
        'var minute=Number(row&&row[0]);if(!Number.isFinite(minute)||minute<earliest)return;',
        'var minute=Number(row&&row[0]);if(!Number.isFinite(minute)||minute<earliest||(Number.isFinite(latest)&&minute>latest))return;',
    ),
    (
        'if(!best||(Number.isFinite(candidate.arrival)&&(!Number.isFinite(best.arrival)||candidate.arrival<best.arrival))||(candidate.arrival===best.arrival&&candidate.departure<best.departure)||(!Number.isFinite(candidate.arrival)&&!Number.isFinite(best.arrival)&&candidate.departure<best.departure))best=candidate;',
        'if(requiredDestination&&candidate.destination!==requiredDestination)return;\n          var windowed=Number.isFinite(latest);\n          if(!best||(windowed&&(candidate.departure<best.departure||(candidate.departure===best.departure&&Number.isFinite(candidate.arrival)&&(!Number.isFinite(best.arrival)||candidate.arrival<best.arrival))))||(!windowed&&((Number.isFinite(candidate.arrival)&&(!Number.isFinite(best.arrival)||candidate.arrival<best.arrival))||(candidate.arrival===best.arrival&&candidate.departure<best.departure)||(!Number.isFinite(candidate.arrival)&&!Number.isFinite(best.arrival)&&candidate.departure<best.departure))))best=candidate;',
    ),
]

for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one match, found {count}: {old[:100]}")
    text = text.replace(old, new, 1)

marker = '    function timedItinerary(path,timetablesByRailway,departureMinutes,service,transferMinutes,transferResolver){'
helper = '''    var destinationGroupCache=new Map(),destinationRailwayCache=new Map();
    function destinationGroupFor(reference){
      reference=String(reference||"");if(!reference)return null;
      if(destinationGroupCache.has(reference))return destinationGroupCache.get(reference);
      var direct=groupByNode.get(reference);if(direct){destinationGroupCache.set(reference,direct);return direct;}
      var suffix=reference.split(".").pop(),matched=null,ambiguous=false;
      stationById.forEach(function(station,stationId){
        if(String(stationId).split(".").pop()!==suffix)return;
        var group=groupByNode.get(stationId);if(!group)return;
        if(!matched)matched=group;else if(matched.key!==group.key)ambiguous=true;
      });
      var result=ambiguous?null:matched;destinationGroupCache.set(reference,result);return result;
    }
    function destinationUsesRailway(destinationId,boundaryGroup,railwayId){
      if(!destinationId||!boundaryGroup||!railwayId)return false;
      var cacheKey=[destinationId,boundaryGroup.key,railwayId].join("\\u0001");
      if(destinationRailwayCache.has(cacheKey))return destinationRailwayCache.get(cacheKey);
      var destinationGroup=destinationGroupFor(destinationId),result=false;
      if(destinationGroup&&destinationGroup.key!==boundaryGroup.key){
        var onward=shortestPath(boundaryGroup,destinationGroup),onwardSegments=onward?segmentsFrom(onward):[];
        result=Boolean(onwardSegments.length&&onwardSegments[0].railway===railwayId);
      }
      destinationRailwayCache.set(cacheKey,result);return result;
    }
'''
if text.count(marker) != 1:
    raise SystemExit("timedItinerary marker not found exactly once")
text = text.replace(marker, helper + marker, 1)

old_candidate = '''        var previous=i>0?timed[i-1]:null;
        var sameCompany=previous&&sameOperator(railwayById.get(previous.railway),railwayById.get(segment.railway));
        var throughCandidate=Boolean(sameCompany&&previous.destination&&fromNodes.indexOf(previous.destination)<0);'''
new_candidate = '''        var previous=i>0?timed[i-1]:null;
        var sameCompany=previous&&sameOperator(railwayById.get(previous.railway),railwayById.get(segment.railway));
        var destinationContinues=Boolean(previous&&previous.destination&&fromNodes.indexOf(previous.destination)<0);
        var throughCandidate=Boolean(destinationContinues&&(sameCompany||destinationUsesRailway(previous.destination,fromGroup,segment.railway)));'''
if text.count(old_candidate) != 1:
    raise SystemExit("throughCandidate block mismatch")
text = text.replace(old_candidate, new_candidate, 1)

old_trip = '''        var earliest=current+(i>0&&!throughCandidate?interchangeBuffer:0);
        var trip=table&&table.timeBasis==="station-departure-only"?stationDepartureTrip(table,fromNodes,toNodes,earliest,service):timetableTrip(table,fromNodes,toNodes,earliest,service);
        if(throughCandidate&&trip){
          var sameDestination=trip.destination&&trip.destination===previous.destination;
          var sameType=!previous.trainType||!trip.trainType||previous.trainType===trip.trainType;
          if(trip.departure>=current&&trip.departure-current<=3&&sameDestination&&sameType)trip.throughFromPrevious=true;
          else{
            earliest=current+interchangeBuffer;
            trip=table&&table.timeBasis==="station-departure-only"?stationDepartureTrip(table,fromNodes,toNodes,earliest,service):timetableTrip(table,fromNodes,toNodes,earliest,service);
          }
        }'''
new_trip = '''        var earliest=current+(i>0&&!throughCandidate?interchangeBuffer:0);
        var throughLatest=throughCandidate?current+3:null;
        var requiredDestination=throughCandidate&&table&&table.timeBasis==="station-departure-only"?previous.destination:"";
        var trip=table&&table.timeBasis==="station-departure-only"?stationDepartureTrip(table,fromNodes,toNodes,earliest,service,throughLatest,requiredDestination):timetableTrip(table,fromNodes,toNodes,earliest,service,throughLatest);
        if(throughCandidate){
          if(trip){
            var sameDestination=!trip.destination||trip.destination===previous.destination;
            var sameType=!sameCompany||!previous.trainType||!trip.trainType||previous.trainType===trip.trainType;
            if(trip.departure>=current&&trip.departure-current<=3&&sameDestination&&sameType){
              trip.throughFromPrevious=true;trip.throughByDestination=true;
              if(!trip.destination)trip.destination=previous.destination;
            }else trip=null;
          }
          if(!trip){
            earliest=current+interchangeBuffer;
            trip=table&&table.timeBasis==="station-departure-only"?stationDepartureTrip(table,fromNodes,toNodes,earliest,service):timetableTrip(table,fromNodes,toNodes,earliest,service);
          }
        }'''
if text.count(old_trip) != 1:
    raise SystemExit("through trip block mismatch")
text = text.replace(old_trip, new_trip, 1)

path.write_text(text, encoding="utf-8")
print("route-core.js patched")
