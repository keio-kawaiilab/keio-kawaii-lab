from pathlib import Path

path = Path('preview/transfer-guide/preview.js')
text = path.read_text(encoding='utf-8')

replacements = [
    (
        'var cards=choices.slice(0,3).map(function(choice,index){',
        'var cards=choices.slice(0,12).map(function(choice,index){'
    ),
    (
        'var paths=model.candidatePaths(fromResolved.group,toResolved.group,{allowedRailways:Array.from(timetableLines.keys()),limit:8});',
        'var paths=model.candidatePaths(fromResolved.group,toResolved.group,{allowedRailways:Array.from(timetableLines.keys()),limit:24});'
    ),
    (
        'var choices=paths.map(function(path){return{path:path,timed:bestTimedItinerary(path,fromResolved.group,toResolved.group,timetables,start,service)};}).filter(function(choice){return choice.timed;});',
        '''var choices=[];\n        paths.forEach(function(path){\n          var cursor=start;\n          for(var attempt=0;attempt<3;attempt++){\n            var timed=bestTimedItinerary(path,fromResolved.group,toResolved.group,timetables,cursor,service);\n            if(!timed)break;\n            choices.push({path:path,timed:timed});\n            if(!Number.isFinite(timed.departure))break;\n            var nextStart=timed.departure+1;\n            if(nextStart<=cursor)nextStart=cursor+1;\n            cursor=nextStart;\n          }\n        });'''
    ),
]

for old, new in replacements:
    if old not in text:
        raise SystemExit(f'expected snippet missing: {old[:100]}')
    text = text.replace(old, new, 1)

old_header = "<p>候補経路を最大3件まで比較できます。</p>"
# index.html owns this wording; kept here only as a guard note for the upgrade workflow.

path.write_text(text, encoding='utf-8')
print('upgraded preview.js: path limit 24, 3 departures/path, 12 displayed choices')
