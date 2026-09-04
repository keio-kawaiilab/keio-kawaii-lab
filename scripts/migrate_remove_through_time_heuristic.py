from pathlib import Path

path = Path('route-core.js')
text = path.read_text(encoding='utf-8')

helper_start = text.find('    var destinationGroupCache=new Map(),destinationRailwayCache=new Map();')
helper_end = text.find('    function timedItinerary(', helper_start)
if helper_start < 0 or helper_end < 0:
    raise SystemExit('destination inference helper block not found')
text = text[:helper_start] + text[helper_end:]

old = '''        var previous=i>0?timed[i-1]:null;\n        var sameCompany=previous&&sameOperator(railwayById.get(previous.railway),railwayById.get(segment.railway));\n        var destinationContinues=Boolean(previous&&previous.destination&&fromNodes.indexOf(previous.destination)<0);\n        var throughCandidate=Boolean(destinationContinues&&(sameCompany||destinationUsesRailway(previous.destination,fromGroup,segment.railway)));\n        var interchangeBuffer=buffer,transferRule=null;'''
new = '''        var previous=i>0?timed[i-1]:null;\n        // Through-service identity must come from precomputed train identity data.\n        // Destination similarity or a short timetable gap is never sufficient proof.\n        var interchangeBuffer=buffer,transferRule=null;'''
if old not in text:
    raise SystemExit('throughCandidate prelude not found')
text = text.replace(old, new, 1)

old = '''        var earliest=current+(i>0&&!throughCandidate?interchangeBuffer:0);\n        var throughLatest=throughCandidate?current+3:null;\n        var requiredDestination=throughCandidate&&table&&table.timeBasis==="station-departure-only"?previous.destination:"";\n        var trip=table&&table.timeBasis==="station-departure-only"?stationDepartureTrip(table,fromNodes,toNodes,earliest,service,throughLatest,requiredDestination):timetableTrip(table,fromNodes,toNodes,earliest,service,throughLatest);\n        if(throughCandidate){\n          if(trip){\n            var sameDestination=!trip.destination||trip.destination===previous.destination;\n            var sameType=!sameCompany||!previous.trainType||!trip.trainType||previous.trainType===trip.trainType;\n            if(trip.departure>=current&&trip.departure-current<=3&&sameDestination&&sameType){\n              trip.throughFromPrevious=true;trip.throughByDestination=true;\n              if(!trip.destination)trip.destination=previous.destination;\n            }else trip=null;\n          }\n          if(!trip){\n            earliest=current+interchangeBuffer;\n            trip=table&&table.timeBasis==="station-departure-only"?stationDepartureTrip(table,fromNodes,toNodes,earliest,service):timetableTrip(table,fromNodes,toNodes,earliest,service);\n          }\n        }'''
new = '''        var earliest=current+(i>0?interchangeBuffer:0);\n        var trip=table&&table.timeBasis==="station-departure-only"?stationDepartureTrip(table,fromNodes,toNodes,earliest,service):timetableTrip(table,fromNodes,toNodes,earliest,service);'''
if old not in text:
    raise SystemExit('three-minute through-service heuristic block not found')
text = text.replace(old, new, 1)

if 'throughLatest=throughCandidate?current+3' in text or 'trip.departure-current<=3' in text:
    raise SystemExit('unsafe through-service time heuristic still present')

path.write_text(text, encoding='utf-8')
print('Removed destination/time-gap through-service inference from route-core.js')
